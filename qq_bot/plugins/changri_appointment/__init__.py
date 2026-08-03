import nonebot
from nonebot import get_driver, logger, on_command, on_message, on_notice
from nonebot.adapters.qq import Bot, GroupMessageCreateEvent, MessageEvent, MessageSegment
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

from plugins.changri_core import CHANGRI_BOT_SELF_ID, PLATFORM
from plugins.changri_core.api import (
    get_role_name,
    get_setting_int,
    get_uid_by_role_name,
    is_admin,
    is_feature_enabled,
    set_setting,
)

from . import api

nonebot.require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

TIMELINE_DAYS_PER_PAGE = 3
MONITOR_POLL_INTERVAL_SECONDS = 300
DEFAULT_MONITOR_TIMEOUT_MINUTES = 180


def _timeline_button(label: str, base_args: str, page: int):
    return Button(
        id="timeline_page",
        render_data=RenderData(label=label, visited_label=label, style=1),
        action=Action(
            type=1,
            data=f"{base_args}|{page}",
            unsupport_tips="请直接发送「/时间线」",
            permission=Permission(type=2),
        ),
    )


def _render_timeline(display_name: str, groups: list[dict], page: int, total_pages: int, base_args: str):
    lines = [f"# 📅 时间线 · {display_name}", ""]
    if not groups:
        lines.append("还没有任何记录")
    for g in groups:
        lines.append(f"**{g['day']}** ｜ {len(g['items'])}场")
        for item in g["items"]:
            place_desc = f"　地点：{item['place']}" if item["place"] else ""
            status_tag = "（进行中）" if item["status"] == "active" else ""
            lines.append(f"> 【{item['subtype']}】与 {item['partner_role']}　{item['time_range']}{place_desc}{status_tag}")
        lines.append("")
    lines.append(f"— 第{page}/{total_pages}页 —")
    message = MessageSegment.markdown("\n".join(lines))

    buttons = []
    if page > 1:
        buttons.append(_timeline_button("⬅️ 上一页", base_args, page - 1))
    if page < total_pages:
        buttons.append(_timeline_button("➡️ 下一页", base_args, page + 1))
    if buttons:
        message = message + MessageSegment.keyboard(
            MessageKeyboard(content=InlineKeyboard(rows=[InlineKeyboardRow(buttons=buttons)]))
        )
    return message


async def _resolve_timeline_target(uid: str, base_args: str):
    """返回 (target_uid, display_name, error_msg)。"""
    if base_args:
        if not is_admin(PLATFORM, uid):
            return None, None, "权限不足，仅管理员可查看别人的时间线"
        target_uid = get_uid_by_role_name(PLATFORM, base_args)
        if target_uid is None:
            return None, None, f"找不到角色「{base_args}」"
        return target_uid, base_args, None
    return uid, get_role_name(PLATFORM, uid) or "我", None


COMMAND_START = tuple(get_driver().config.command_start) or ("/",)


def _is_group_event(event) -> bool:
    return isinstance(event, GroupMessageCreateEvent)


def _is_plain_group_text(event: GroupMessageCreateEvent) -> bool:
    text = event.get_plaintext().strip()
    return bool(text) and not text.startswith(COMMAND_START)


rp_reply_cmd = on_message(rule=Rule(_is_group_event) & Rule(_is_plain_group_text), priority=50, block=False)


@rp_reply_cmd.handle()
async def handle_rp_reply(event: GroupMessageCreateEvent):
    await api.record_rp_reply(PLATFORM, event.group_openid, event.get_user_id(), event.get_plaintext())


register_group_cmd = on_command("注册戏群", rule=_is_group_event)


@register_group_cmd.handle()
async def handle_register_group(event: GroupMessageCreateEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await register_group_cmd.finish("权限不足，仅管理员可用")
    label = args.extract_plain_text().strip()
    if not label:
        await register_group_cmd.finish("用法：/注册戏群 标签名（要在目标群里发这条指令）")
        return
    api.register_group(PLATFORM, event.group_openid, label)
    await register_group_cmd.finish(f"本群已注册为戏群「{label}」")


group_pool_cmd = on_command("戏群列表")


@group_pool_cmd.handle()
async def handle_group_pool(event: MessageEvent):
    if not is_admin(PLATFORM, event.get_user_id()):
        await group_pool_cmd.finish("权限不足，仅管理员可用")
    groups = api.list_groups(PLATFORM)
    if not groups:
        await group_pool_cmd.finish("戏群池是空的，先在目标群里用「/注册戏群」加一个")
        return
    lines = ["🎬 戏群池"]
    for g in groups:
        lines.append(f"- {g['label']}：{'占用中' if g['occupied'] else '空闲'}")
    await group_pool_cmd.finish("\n".join(lines))


def _make_appointment_cmd(cmd_name: str, subtype: str, needs_place: bool):
    cmd = on_command(cmd_name)

    @cmd.handle()
    async def handle_appointment(bot: Bot, event: MessageEvent, args=CommandArg()):
        if not is_feature_enabled("appointment"):
            await cmd.finish("私约系统现在关闭中")
            return
        parts = args.extract_plain_text().strip().split()
        if needs_place:
            if len(parts) != 3:
                await cmd.finish(f"用法：/{cmd_name} 角色名 地点 时段（如 11:00-12:00）")
                return
            partner_role, place, time_range = parts
        else:
            if len(parts) != 2:
                await cmd.finish(f"用法：/{cmd_name} 角色名 时段（如 11:00-12:00）")
                return
            partner_role, time_range = parts
            place = None
        ok, msg, extra = api.create_appointment(
            PLATFORM, event.get_user_id(), partner_role, None, time_range, subtype, place
        )
        if not ok:
            await cmd.finish(msg)
            return
        try:
            await bot.send_to_group(group_openid=extra["group_openid"], message=extra["announce"])
        except Exception:
            pass
        await cmd.finish(msg)

    return cmd


phone_cmd = _make_appointment_cmd("电话", "电话", needs_place=False)
private_appt_cmd = _make_appointment_cmd("私约", "私约", needs_place=True)
battle_appt_cmd = _make_appointment_cmd("约战", "约战", needs_place=True)


my_appointments_cmd = on_command("时间线")


@my_appointments_cmd.handle()
async def handle_my_appointments(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    uid = event.get_user_id()
    base_args = ""
    page = 1

    if len(parts) == 1 and parts[0].isdigit():
        page = int(parts[0])
    elif len(parts) == 1:
        base_args = parts[0]
    elif len(parts) == 2 and parts[1].isdigit():
        base_args = parts[0]
        page = int(parts[1])
    elif len(parts) > 0:
        await my_appointments_cmd.finish("用法：/时间线 [页码] 或 /时间线 角色名 [页码]（查看别人仅限管理员）")
        return

    target_uid, display_name, error_msg = await _resolve_timeline_target(uid, base_args)
    if error_msg:
        await my_appointments_cmd.finish(error_msg)
        return

    groups, total_pages, page = api.get_role_timeline(PLATFORM, target_uid, page, TIMELINE_DAYS_PER_PAGE)
    await my_appointments_cmd.finish(_render_timeline(display_name, groups, page, total_pages, base_args))


timeline_page_interaction = on_notice(
    rule=Rule(
        lambda event: isinstance(event, InteractionCreateEvent)
        and event.data.resolved.button_id == "timeline_page"
    )
)


@timeline_page_interaction.handle()
async def handle_timeline_page_interaction(bot: Bot, event: InteractionCreateEvent):
    await bot.put_interaction(interaction_id=event.id, code=0)
    payload = event.data.resolved.button_data or "|1"
    base_args, _, page_str = payload.rpartition("|")
    page = int(page_str) if page_str.isdigit() else 1
    uid = event.get_user_id()

    target_uid, display_name, error_msg = await _resolve_timeline_target(uid, base_args)
    if error_msg:
        if event.group_openid:
            await bot.send_to_group(group_openid=event.group_openid, message=error_msg)
        return

    groups, total_pages, page = api.get_role_timeline(PLATFORM, target_uid, page, TIMELINE_DAYS_PER_PAGE)
    message = _render_timeline(display_name, groups, page, total_pages, base_args)
    if event.group_openid:
        await bot.send_to_group(group_openid=event.group_openid, message=message)


end_appointment_cmd = on_command("结束私约")


@end_appointment_cmd.handle()
async def handle_end_appointment(bot: Bot, event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    text = args.extract_plain_text().strip()
    appointments = api.get_my_active_appointments(PLATFORM, uid)
    if not appointments:
        await end_appointment_cmd.finish("你现在没有进行中的约会")
        return
    if text.isdigit():
        target_id = int(text)
    elif len(appointments) == 1:
        target_id = appointments[0]["id"]
    else:
        ids = "、".join(f"#{a['id']}" for a in appointments)
        await end_appointment_cmd.finish(f"你有多场进行中的约会（{ids}），用「/结束私约 编号」指定要结束哪一场")
        return
    ok, msg, group_openid = await api.end_appointment(PLATFORM, target_id)
    if ok and group_openid:
        try:
            await bot.send_to_group(group_openid=group_openid, message="这场戏已经结束，本群释放，请自行退群")
        except Exception:
            pass
    await end_appointment_cmd.finish(msg)


force_end_cmd = on_command("强结私约")


@force_end_cmd.handle()
async def handle_force_end(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await force_end_cmd.finish("权限不足，仅管理员可用")
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await force_end_cmd.finish("用法：/强结私约 编号")
        return
    ok, msg, group_openid = await api.end_appointment(PLATFORM, int(text), forced=True)
    if ok and group_openid:
        try:
            await bot.send_to_group(group_openid=group_openid, message="管理员已强制结束这场戏，本群释放，请自行退群")
        except Exception:
            pass
    await force_end_cmd.finish(msg)


apply_join_cmd = on_command("申请加入", rule=_is_group_event)


@apply_join_cmd.handle()
async def handle_apply_join(bot: Bot, event: GroupMessageCreateEvent):
    ok, msg, request_id = api.apply_join(PLATFORM, event.group_openid, event.get_user_id())
    if ok:
        # 场内角色需要自己用「同意加入/拒绝加入」处理，机器人没法主动推送通知
        await apply_join_cmd.finish(f"{msg}，申请编号 {request_id}")
        return
    await apply_join_cmd.finish(msg)


accept_join_cmd = on_command("同意加入")


@accept_join_cmd.handle()
async def handle_accept_join(bot: Bot, event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await accept_join_cmd.finish("用法：/同意加入 申请编号")
        return
    ok, msg = api.respond_join(PLATFORM, event.get_user_id(), int(text), accept=True)
    await accept_join_cmd.finish(msg)


reject_join_cmd = on_command("拒绝加入")


@reject_join_cmd.handle()
async def handle_reject_join(event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await reject_join_cmd.finish("用法：/拒绝加入 申请编号")
        return
    ok, msg = api.respond_join(PLATFORM, event.get_user_id(), int(text), accept=False)
    await reject_join_cmd.finish(msg)


# ── 戏群监听（超时提醒）──────────────────────────────────────────────────


monitor_settings_cmd = on_command("监听设置")


@monitor_settings_cmd.handle()
async def handle_monitor_settings(event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        minutes = get_setting_int("monitor_timeout_minutes", DEFAULT_MONITOR_TIMEOUT_MINUTES)
        await monitor_settings_cmd.finish(f"当前超时提醒时长：{minutes}分钟")
        return
    if not is_admin(PLATFORM, event.get_user_id()):
        await monitor_settings_cmd.finish("权限不足，仅管理员可用")
        return
    if not text.isdigit() or int(text) <= 0:
        await monitor_settings_cmd.finish("用法：/监听设置 分钟数")
        return
    set_setting("monitor_timeout_minutes", text)
    await monitor_settings_cmd.finish(f"超时提醒时长已设为 {text} 分钟")


@scheduler.scheduled_job("interval", seconds=MONITOR_POLL_INTERVAL_SECONDS, id="changri_appointment_monitor")
async def _poll_stale_appointments():
    timeout_minutes = get_setting_int("monitor_timeout_minutes", DEFAULT_MONITOR_TIMEOUT_MINUTES)
    stale = api.get_stale_appointments(PLATFORM, timeout_minutes * 60)
    if not stale:
        return
    bots = nonebot.get_bots()
    bot = bots.get(CHANGRI_BOT_SELF_ID) or next(iter(bots.values()), None)
    if bot is None:
        logger.warning("[戏群监听] 有超时的戏但没有已连接的Bot实例，本轮跳过")
        return
    text = (
        f"⏰ 温馨提示：\n本群已经 {timeout_minutes // 60} 小时没有新进展了～\n\n"
        f"如果互动已经结束，请用「/结束私约」\n"
        f"还在进行的话，看到请随手回复一下～"
    )
    for appt in stale:
        if not appt["group_openid"]:
            continue
        try:
            await bot.send_to_group(group_openid=appt["group_openid"], message=text)
            api.mark_reminded(appt["id"])
        except Exception as e:
            logger.warning(f"[戏群监听] 提醒 群{appt['group_openid']} 失败：{e}")
