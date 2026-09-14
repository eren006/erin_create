import asyncio

import httpx
import nonebot
from nonebot import logger, on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from . import storage
from ..changri_core import api as changri_api

storage.init_db()

nonebot.require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

YUCA_BOT_SELF_ID = "102254477"
PLATFORM = "qq"
POLL_MINUTES = 30

# 九霄仙门和qq_bot同机部署，两边走本机回环地址，不走公网——地址本身也走配置，不写死，
# 免得哪天改了部署方式还要动代码。
#
# qq_bot 有独立的 Windows 计划任务每3小时重启一次进程(ChangriQQBot_PeriodicRestart)，
# 之前 POLL_MINUTES=180 正好跟重启周期撞在一起——每次重启都会把 APScheduler 的间隔计时
# 清零重算，导致这个轮询任务实际上从没等到触发就被杀掉重来，永远发不出播报。改成30分钟，
# 让它在重启间隙里能真正跑起来。
#
# 另外给 interval job 塞 next_run_time 让它一启动就立即跑一次这个思路实测在这个进程里不生效
# (单独写最小复现脚本验证 APScheduler 本身没问题，但在真实 nonebot 进程里那个job就是不触发，
# 原因未查清，不值得为这个继续深挖)，改成更直接的方式：driver.on_startup 里手动await一次，
# 外加一个手动指令，管理员可以随时立即拉取一次，不用等轮询也不用等重启。


async def _poll_and_announce() -> str:
    """返回本轮结果说明，供手动指令直接回复管理员，不用去翻日志猜。"""
    base_url, token = storage.get_config()
    if not base_url or not token:
        return "尚未配置九霄仙门接口地址/token，先用 /设置九霄接口 配置"
    group_openid = storage.get_group_openid()
    if not group_openid:
        return "尚未设置九霄通知群，先在目标群里发 /设为九霄通知群"

    last_id = storage.get_last_id()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base_url}/api/chronicle/major",
                params={"since_id": last_id},
                headers={"X-Jiuxiao-Token": token},
            )
        if resp.status_code != 200:
            msg = f"[九霄仙门播报] 接口返回 {resp.status_code}，本轮跳过"
            logger.warning(msg)
            return msg
        body = resp.json()
    except httpx.HTTPError as e:
        msg = f"[九霄仙门播报] 请求失败：{e}"
        logger.warning(msg)
        return msg

    entries = body.get("entries") or []
    if not entries:
        return "接口正常，但没有新的大事记条目"

    bots = nonebot.get_bots()
    bot = bots.get(YUCA_BOT_SELF_ID) or next(iter(bots.values()), None)
    if bot is None:
        msg = "[九霄仙门播报] 有新条目但没有已连接的Bot实例，本轮跳过（下轮不会重复丢失，last_id未推进）"
        logger.warning(msg)
        return msg

    lines = ["九霄仙门宗务简报："] + [f"▪ {e['text']}" for e in entries]
    try:
        await bot.send_to_group(group_openid=group_openid, message="\n".join(lines))
        storage.set_last_id(body.get("latest_id", last_id))
        return f"已推送 {len(entries)} 条大事记到通知群"
    except Exception as e:
        msg = f"[九霄仙门播报] 发送失败，本轮不推进进度：{e}"
        logger.warning(msg)
        return msg


@scheduler.scheduled_job("interval", minutes=POLL_MINUTES, id="jiuxiao_notify_tick")
async def _tick() -> None:
    await _poll_and_announce()


driver = nonebot.get_driver()


@driver.on_startup
async def _startup_poll() -> None:
    # 进程一启动就等QQ adapter连上(实测2~3秒)再补跑一轮，不用干等下一个30分钟周期。
    await asyncio.sleep(8)
    await _poll_and_announce()


poll_now_cmd = on_command("立即推送九霄播报")


@poll_now_cmd.handle()
async def handle_poll_now(event: MessageEvent):
    if not changri_api.is_admin(PLATFORM, event.get_user_id()):
        await poll_now_cmd.finish("权限不足，仅管理员可用")
        return
    result = await _poll_and_announce()
    await poll_now_cmd.finish(result)


# ── 配置指令：私聊/群聊均可，仅长日机器人的管理员名单可用（复用changri_core的admins表） ──

config_cmd = on_command("设置九霄接口")


@config_cmd.handle()
async def handle_config(event: MessageEvent, args=CommandArg()):
    if not changri_api.is_admin(PLATFORM, event.get_user_id()):
        await config_cmd.finish("权限不足，仅管理员可用")
        return
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await config_cmd.finish("用法：/设置九霄接口 九霄仙门地址 api_token")
        return
    base_url, token = parts
    storage.set_config(base_url, token)
    await config_cmd.finish("九霄仙门接口地址和token已保存")


set_notify_group_cmd = on_command("设为九霄通知群")


@set_notify_group_cmd.handle()
async def handle_set_notify_group(event: MessageEvent):
    from nonebot.adapters.qq import GroupMessageCreateEvent

    if not changri_api.is_admin(PLATFORM, event.get_user_id()):
        await set_notify_group_cmd.finish("权限不足，仅管理员可用")
        return
    if not isinstance(event, GroupMessageCreateEvent):
        await set_notify_group_cmd.finish("这条指令要在群里发。")
        return
    storage.set_group_openid(event.group_openid)
    await set_notify_group_cmd.finish(
        f"本群已设为九霄仙门通知群，每{POLL_MINUTES}分钟核对一次宗门大事记，只报全宗级大事，不报日常琐事。"
    )
