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

from . import api

gift_shop_cmd = on_command("礼品店")


@gift_shop_cmd.handle()
async def handle_gift_shop(event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    if text.startswith("添加"):
        if not is_admin(PLATFORM, event.get_user_id()):
            await gift_shop_cmd.finish("权限不足，仅管理员可用")
            return
        rest = text[len("添加"):].strip()
        name, _, desc = rest.replace("：", ":").partition(":")
        name = name.strip()
        if not name:
            await gift_shop_cmd.finish("用法：/礼品店 添加 名字:描述")
            return
        api.add_preset_gift(PLATFORM, name, desc.strip())
        await gift_shop_cmd.finish(f"礼品「{name}」已加入礼品店")
        return

    gifts = api.list_preset_gifts(PLATFORM)
    if not gifts:
        await gift_shop_cmd.finish("礼品店空空如也")
        return
    lines = ["🎁 礼品店"]
    for g in gifts:
        desc = f"（{g['desc']}）" if g["desc"] else ""
        lines.append(f"- {g['name']}{desc}　已送出{g['usage_count']}次")
    await gift_shop_cmd.finish("\n".join(lines))


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
                    unsupport_tips="请直接发送「/送礼选人 角色名」",
                    permission=Permission(type=2),
                ),
            )
            for name in chunk
        ]
        rows.append(InlineKeyboardRow(buttons=buttons))
    return MessageSegment.keyboard(MessageKeyboard(content=InlineKeyboard(rows=rows)))


async def _finalize_gift(bot: Bot, from_uid: str, to_role: str, content: str) -> str:
    ok, msg = await api.send_gift(PLATFORM, from_uid, to_role, content)
    if ok:
        to_uid = get_uid_by_role_name(PLATFORM, to_role)
        target_gid = get_role_group(PLATFORM, to_uid) if to_uid else None
        if target_gid:
            from_role = get_role_name(PLATFORM, from_uid) or "未知"
            when = time.strftime("%H:%M")
            quoted_content = "\n".join(f"> {line}" for line in content.split("\n"))
            notice = (
                f"# 🎁 礼物\n\n"
                f"{to_role}，你收到 **{from_role}** 的礼物\n"
                f"{quoted_content}\n\n"
                f"{when}"
            )
            try:
                await bot.send_to_group(
                    group_openid=target_gid,
                    message=MessageSegment.markdown(notice),
                )
            except Exception as e:
                logger.warning(f"[送礼] 推送到 {to_role} 所在群失败：{e}")
    return msg


send_gift_cmd = on_command("送礼")


@send_gift_cmd.handle()
async def handle_send_gift(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("gift"):
        await send_gift_cmd.finish("礼物系统现在关闭中")
        return
    content = args.extract_plain_text().strip()
    if not content:
        await send_gift_cmd.finish("用法：/送礼 礼物内容")
        return
    uid = event.get_user_id()
    if get_role_name(PLATFORM, uid) is None:
        await send_gift_cmd.finish("你还没有角色，先用「/创建新角色 <角色名>」创建一个")
        return
    candidates = list_role_names(PLATFORM, exclude_uid=uid)
    if not candidates:
        await send_gift_cmd.finish("现在还没有其他角色可以送礼")
        return
    api.set_pending_gift(PLATFORM, uid, content)
    reply = MessageSegment.markdown("送给谁？点一个：") + _role_pick_buttons(candidates, "gift_pick")
    await send_gift_cmd.finish(reply)


gift_pick_cmd = on_command("送礼选人")


@gift_pick_cmd.handle()
async def handle_gift_pick(bot: Bot, event: MessageEvent, args=CommandArg()):
    to_role = args.extract_plain_text().strip()
    if not to_role:
        await gift_pick_cmd.finish("用法：/送礼选人 角色名（先发「/送礼 内容」再选人）")
        return
    content = api.pop_pending_gift(PLATFORM, event.get_user_id())
    if content is None:
        await gift_pick_cmd.finish("没有待发送的礼物了（超过5分钟会失效），先重新发「/送礼 内容」")
        return
    await gift_pick_cmd.finish(await _finalize_gift(bot, event.get_user_id(), to_role, content))


gift_pick_interaction = on_notice(
    rule=Rule(
        lambda event: isinstance(event, InteractionCreateEvent)
        and event.data.resolved.button_id == "gift_pick"
    )
)


@gift_pick_interaction.handle()
async def handle_gift_pick_interaction(bot: Bot, event: InteractionCreateEvent):
    await bot.put_interaction(interaction_id=event.id, code=0)
    to_role = event.data.resolved.button_data
    uid = event.get_user_id()
    if not to_role:
        return
    content = api.pop_pending_gift(PLATFORM, uid)
    if content is None:
        result = "没有待发送的礼物了（超过5分钟会失效），先重新发「/送礼 内容」"
    else:
        result = await _finalize_gift(bot, uid, to_role, content)
    if event.group_openid:
        await bot.send_to_group(group_openid=event.group_openid, message=result)


my_catalog_cmd = on_command("我的图鉴")


@my_catalog_cmd.handle()
async def handle_my_catalog(event: MessageEvent):
    catalog = api.get_catalog(PLATFORM, event.get_user_id())
    if not catalog:
        await my_catalog_cmd.finish("你的图鉴还是空的")
        return
    lines = ["📖 我的图鉴"] + [f"- {g['gift_name']}" for g in catalog]
    await my_catalog_cmd.finish("\n".join(lines))


view_catalog_cmd = on_command("图鉴")


@view_catalog_cmd.handle()
async def handle_view_catalog(event: MessageEvent, args=CommandArg()):
    role_name = args.extract_plain_text().strip()
    if not role_name:
        await view_catalog_cmd.finish("用法：/图鉴 角色名（查自己用「/我的图鉴」）")
        return
    from plugins.changri_core.api import get_uid_by_role_name

    uid = get_uid_by_role_name(PLATFORM, role_name)
    if uid is None:
        await view_catalog_cmd.finish(f"找不到角色「{role_name}」")
        return
    catalog = api.get_catalog(PLATFORM, uid)
    if not catalog:
        await view_catalog_cmd.finish(f"{role_name} 的图鉴还是空的")
        return
    lines = [f"📖 {role_name} 的图鉴"] + [f"- {g['gift_name']}" for g in catalog]
    await view_catalog_cmd.finish("\n".join(lines))
