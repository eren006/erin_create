import time

from nonebot import logger, on_command, on_notice
from nonebot.adapters.qq import Bot, MessageEvent, MessageSegment
from nonebot.adapters.qq.event import InteractionCreateEvent
from nonebot.adapters.qq.models import (
    Action,
    Button,
    InlineKeyboard,
    InlineKeyboardRow,
    MessageKeyboard,
    Permission,
    RenderData,
)
from nonebot.params import CommandArg
from nonebot.rule import Rule

from plugins.changri_core import PLATFORM
from plugins.changri_core.api import (
    get_role_group,
    get_role_name,
    get_uid_by_role_name,
    is_admin,
    is_feature_enabled,
    list_role_names,
)
from plugins.changri_rpg.api import add_item, find_item_by_name

from . import api

CONFIG_KEYS = {
    "日限": "letter_daily_limit",
    "赏金": "letter_reward",
    "最小字数": "letter_min_chars",
    "冷却秒": "letter_cooldown_seconds",
}


def _require_role(uid: str) -> str | None:
    return get_role_name(PLATFORM, uid)


init_letter_item_cmd = on_command("注册写信道具")


@init_letter_item_cmd.handle()
async def handle_init_letter_item(event: MessageEvent):
    if not is_admin(PLATFORM, event.get_user_id()):
        await init_letter_item_cmd.finish("权限不足，仅管理员可用")
    if find_item_by_name(PLATFORM, "写信币") is None:
        add_item(PLATFORM, "写信币", "写信攒下的零花钱", "currency", can_resell=False)
    await init_letter_item_cmd.finish("写信币已就绪")


send_letter_cmd = on_command("发送信件")


@send_letter_cmd.handle()
async def handle_send_letter(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("letters"):
        await send_letter_cmd.finish("写信系统现在关闭中")
        return
    uid = event.get_user_id()
    if _require_role(uid) is None:
        await send_letter_cmd.finish("你还没有角色，先用「/创建新角色 <角色名>」创建一个")
    parts = args.extract_plain_text().strip().split(maxsplit=1)
    if len(parts) != 2:
        await send_letter_cmd.finish("用法：/发送信件 收件人角色名 内容")
        return
    to_role, content = parts
    to_uid = get_uid_by_role_name(PLATFORM, to_role)
    if to_uid is None:
        await send_letter_cmd.finish(f"找不到角色「{to_role}」")
        return
    ok, msg = await api.send_letter(PLATFORM, uid, to_uid, content)
    await send_letter_cmd.finish(msg)


inbox_cmd = on_command("我的信箱")


@inbox_cmd.handle()
async def handle_inbox(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    show_all = args.extract_plain_text().strip() == "全部"
    letters = api.get_inbox(PLATFORM, uid, unread_only=not show_all)
    if not letters:
        await inbox_cmd.finish("没有新信件" if not show_all else "信箱是空的")
        return
    lines = ["📮 信箱"]
    for letter in letters:
        from_role = get_role_name(PLATFORM, letter["from_uid"]) or "未知"
        when = time.strftime("%m-%d %H:%M", time.localtime(letter["created_at"]))
        lines.append(f"[{when}] {from_role}：{letter['content']}")
    api.mark_read([letter["id"] for letter in letters])
    await inbox_cmd.finish("\n".join(lines))


letter_status_cmd = on_command("写信额度")


@letter_status_cmd.handle()
async def handle_letter_status(event: MessageEvent):
    config = api.get_config()
    ok, msg = api.can_send_letter(PLATFORM, event.get_user_id())
    day_count = api.get_day_count(PLATFORM, event.get_user_id())
    await letter_status_cmd.finish(
        f"今日已发：{day_count['count']}/{config['letter_daily_limit']}\n"
        f"满 {config['letter_min_chars']} 字奖励 {config['letter_reward']} 写信币\n"
        f"发信冷却：{config['letter_cooldown_seconds']} 秒\n"
        + ("现在可以发信" if ok else f"暂时不能发信：{msg}")
    )


letter_settings_cmd = on_command("信件设置")


@letter_settings_cmd.handle()
async def handle_letter_settings(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await letter_settings_cmd.finish("权限不足，仅管理员可用")
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2 or parts[0] not in CONFIG_KEYS or not parts[1].isdigit():
        await letter_settings_cmd.finish("用法：/信件设置 日限/赏金/最小字数/冷却秒 数值")
        return
    api.set_config(**{CONFIG_KEYS[parts[0]]: int(parts[1])})
    await letter_settings_cmd.finish(f"{parts[0]} 已设为 {parts[1]}")


def _role_pick_buttons(role_names: list[str], button_id: str):
    rows = []
    for i in range(0, min(len(role_names), 25), 5):
        chunk = role_names[i : i + 5]
        buttons = [
            Button(
                id=button_id,
                render_data=RenderData(label=name, visited_label=name, style=1),
                action=Action(
                    type=1,
                    data=name,
                    unsupport_tips="请直接发送「/短信选人 角色名」",
                    permission=Permission(type=2),
                ),
            )
            for name in chunk
        ]
        rows.append(InlineKeyboardRow(buttons=buttons))
    return MessageSegment.keyboard(MessageKeyboard(content=InlineKeyboard(rows=rows)))


async def _finalize_sms(bot: Bot, from_uid: str, to_role: str, content: str) -> str:
    to_uid = get_uid_by_role_name(PLATFORM, to_role)
    if to_uid is None:
        return f"找不到角色「{to_role}」"
    ok, msg = await api.send_sms(PLATFORM, from_uid, to_uid, content)
    if ok:
        target_gid = get_role_group(PLATFORM, to_uid)
        if target_gid:
            from_role = get_role_name(PLATFORM, from_uid) or "未知"
            when = time.strftime("%H:%M")
            quoted_content = "\n".join(f"> {line}" for line in content.split("\n"))
            notice = (
                f"# 📨 短信\n\n"
                f"{to_role}，你收到 **{from_role}** 的消息\n"
                f"{quoted_content}\n\n"
                f"{when}"
            )
            try:
                await bot.send_to_group(
                    group_openid=target_gid,
                    message=MessageSegment.markdown(notice),
                )
            except Exception as e:
                logger.warning(f"[短信] 推送到 {to_role} 所在群失败：{e}")
    return msg


sms_cmd = on_command("短信")


@sms_cmd.handle()
async def handle_sms(bot: Bot, event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if not text or text == "全部":
        show_all = text == "全部"
        messages = api.get_sms_inbox(PLATFORM, uid, unread_only=not show_all)
        if not messages:
            await sms_cmd.finish("没有新短信" if not show_all else "短信箱是空的")
            return
        lines = ["📱 短信"]
        for sms in messages:
            from_role = sms["signature"] or get_role_name(PLATFORM, sms["from_uid"]) or "未知"
            when = time.strftime("%m-%d %H:%M", time.localtime(sms["created_at"]))
            lines.append(f"[{when}] {from_role}：{sms['content']}")
        api.mark_sms_read([sms["id"] for sms in messages])
        await sms_cmd.finish("\n".join(lines))
        return

    if get_role_name(PLATFORM, uid) is None:
        await sms_cmd.finish("你还没有角色，先用「/创建新角色 <角色名>」创建一个")
        return
    candidates = list_role_names(PLATFORM, exclude_uid=uid)
    if not candidates:
        await sms_cmd.finish("现在还没有其他角色可以发短信")
        return
    api.set_pending_sms(PLATFORM, uid, text)
    reply = MessageSegment.markdown("发给谁？点一个：") + _role_pick_buttons(candidates, "sms_pick")
    await sms_cmd.finish(reply)


sms_pick_cmd = on_command("短信选人")


@sms_pick_cmd.handle()
async def handle_sms_pick(bot: Bot, event: MessageEvent, args=CommandArg()):
    to_role = args.extract_plain_text().strip()
    if not to_role:
        await sms_pick_cmd.finish("用法：/短信选人 角色名（先发「/短信 内容」再选人）")
        return
    content = api.pop_pending_sms(PLATFORM, event.get_user_id())
    if content is None:
        await sms_pick_cmd.finish("没有待发送的短信内容了（超过5分钟会失效），先重新发「/短信 内容」")
        return
    await sms_pick_cmd.finish(await _finalize_sms(bot, event.get_user_id(), to_role, content))


sms_pick_interaction = on_notice(
    rule=Rule(
        lambda event: isinstance(event, InteractionCreateEvent)
        and event.data.resolved.button_id == "sms_pick"
    )
)


@sms_pick_interaction.handle()
async def handle_sms_pick_interaction(bot: Bot, event: InteractionCreateEvent):
    await bot.put_interaction(interaction_id=event.id, code=0)
    to_role = event.data.resolved.button_data
    uid = event.get_user_id()
    if not to_role:
        return
    content = api.pop_pending_sms(PLATFORM, uid)
    if content is None:
        result = "没有待发送的短信内容了（超过5分钟会失效），先重新发「/短信 内容」"
    else:
        result = await _finalize_sms(bot, uid, to_role, content)
    if event.group_openid:
        await bot.send_to_group(group_openid=event.group_openid, message=result)
