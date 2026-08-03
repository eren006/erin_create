from datetime import datetime

import nonebot
from nonebot import logger, on_command
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.params import CommandArg

nonebot.require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

from plugins.changri_core import CHANGRI_BOT_SELF_ID
from plugins.changri_core import api as core_api  # noqa: E402

from . import api
from .timeparse import TimeParseError, compute_next_trigger, parse_reminder_time

PLATFORM = "qq"
POLL_INTERVAL_SECONDS = 60
MAX_FAIL_COUNT = 5


def _group_only_reject(event: BaseEvent) -> str | None:
    if not isinstance(event, GroupMessageCreateEvent):
        return "这个指令目前只能在群聊里用（机器人还没过审进群前，群聊场景本身也用不了，先等一等）"
    return None


set_reminder_cmd = on_command("提醒")


@set_reminder_cmd.handle()
async def handle_set_reminder(event: BaseEvent, args=CommandArg()):
    if (reject := _group_only_reject(event)) is not None:
        await set_reminder_cmd.finish(reject)
    text = args.extract_plain_text().strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await set_reminder_cmd.finish(
            "用法：/提醒 <时间> <内容>，时间支持：10分钟后 / 2小时后 / 18:30 / 每天8:00 / 每周一20:00"
        )
    time_expr, content = parts
    uid = event.get_user_id()
    if api.count_reminders(PLATFORM, uid) >= api.MAX_REMINDERS_PER_USER:
        await set_reminder_cmd.finish(f"提醒太多了（上限{api.MAX_REMINDERS_PER_USER}条），先删几条")
    try:
        trigger_at, repeat = parse_reminder_time(time_expr)
    except TimeParseError as e:
        await set_reminder_cmd.finish(str(e))
    group_openid = event.group_openid  # type: ignore[attr-defined]
    reminder_id = api.add_reminder(
        PLATFORM, uid, group_openid, int(trigger_at.timestamp()), content, repeat
    )
    await set_reminder_cmd.finish(
        f"提醒已设置（#{reminder_id}）：{trigger_at.strftime('%m-%d %H:%M')} {content}"
    )


list_reminders_cmd = on_command("闹钟")


@list_reminders_cmd.handle()
async def handle_list_reminders(event: BaseEvent):
    if (reject := _group_only_reject(event)) is not None:
        await list_reminders_cmd.finish(reject)
    rows = api.list_reminders(PLATFORM, event.get_user_id())
    if not rows:
        await list_reminders_cmd.finish("你还没有设置任何提醒")
    lines = [
        f"#{row['id']} {datetime.fromtimestamp(row['trigger_at']).strftime('%m-%d %H:%M')} "
        f"[{row['repeat']}] {row['content']}"
        for row in rows
    ]
    await list_reminders_cmd.finish("你的提醒：\n" + "\n".join(lines))


delete_reminder_cmd = on_command("取消提醒")


@delete_reminder_cmd.handle()
async def handle_delete_reminder(event: BaseEvent, args=CommandArg()):
    if (reject := _group_only_reject(event)) is not None:
        await delete_reminder_cmd.finish(reject)
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await delete_reminder_cmd.finish("用法：/取消提醒 <编号>（编号看「/闹钟」）")
    if api.delete_reminder(PLATFORM, event.get_user_id(), int(text)):
        await delete_reminder_cmd.finish("已删除")
    await delete_reminder_cmd.finish("没找到这条提醒，检查一下编号")


remind_again_cmd = on_command("再提醒我")


@remind_again_cmd.handle()
async def handle_remind_again(event: BaseEvent, args=CommandArg()):
    if (reject := _group_only_reject(event)) is not None:
        await remind_again_cmd.finish(reject)
    uid = event.get_user_id()
    last = api.get_last_fired(PLATFORM, uid)
    if last is None:
        await remind_again_cmd.finish("还没有触发过的提醒可以重复")
    minutes_text = args.extract_plain_text().strip()
    minutes = int(minutes_text) if minutes_text.isdigit() else 10
    trigger_at = datetime.now()
    from datetime import timedelta

    trigger_at += timedelta(minutes=minutes)
    reminder_id = api.add_reminder(
        PLATFORM, uid, last["group_openid"], int(trigger_at.timestamp()), last["content"], "none"
    )
    await remind_again_cmd.finish(f"好，{minutes}分钟后再提醒你（#{reminder_id}）：{last['content']}")


@scheduler.scheduled_job("interval", seconds=POLL_INTERVAL_SECONDS, id="changri_alarm_poll")
async def _poll_reminders():
    now_ts = int(datetime.now().timestamp())
    due = api.get_due_reminders(now_ts)
    if not due:
        return
    bots = nonebot.get_bots()
    bot = bots.get(CHANGRI_BOT_SELF_ID) or next(iter(bots.values()), None)
    if bot is None:
        logger.warning("[长日闹钟] 有到期提醒但没有已连接的Bot实例，本轮跳过")
        return
    for row in due:
        role_name = core_api.get_role_name(row["platform"], row["uid"]) or "朋友"
        text = f"⏰ 提醒 {role_name}：{row['content']}"
        sent = False
        try:
            await bot.send_to_group(group_openid=row["group_openid"], message=text)
            sent = True
        except Exception as e:
            fail_count = api.increment_fail_count(row["id"])
            logger.warning(
                f"[长日闹钟] 提醒 id={row['id']} 发送失败（第{fail_count}次）"
                f"（大概率是机器人还没过审进群/群主没开主动发言开关）：{e}"
            )
            if fail_count >= MAX_FAIL_COUNT:
                api.remove_reminder_by_id(row["id"])
                logger.warning(f"[长日闹钟] 提醒 id={row['id']} 连续失败{MAX_FAIL_COUNT}次，已放弃并删除")
        if not sent:
            continue
        api.reset_fail_count(row["id"])
        api.set_last_fired(row["platform"], row["uid"], row["group_openid"], row["content"])
        next_trigger = compute_next_trigger(datetime.fromtimestamp(row["trigger_at"]), row["repeat"])
        if next_trigger:
            api.reschedule_reminder(row["id"], int(next_trigger.timestamp()))
        else:
            api.remove_reminder_by_id(row["id"])
