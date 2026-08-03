from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from plugins.changri_core import PLATFORM
from plugins.changri_core.api import is_admin

from . import api

MODE_MAP = {"复盘": "review", "不复盘": "no_review"}

create_season_cmd = on_command("创建新季度")


@create_season_cmd.handle()
async def handle_create_season(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await create_season_cmd.finish("权限不足，仅管理员可用")
    parts = args.extract_plain_text().strip().split()
    if len(parts) not in (3, 4) or parts[1] not in MODE_MAP or "-" not in parts[2]:
        await create_season_cmd.finish(
            "用法：/创建新季度 名字 复盘/不复盘 MMDD-MMDD [补档MMDD]\n"
            "示例：创建新季度 测试恋综 复盘 0726-0727"
        )
        return
    name, mode_label, schedule = parts[0], parts[1], parts[2]
    start, _, end = schedule.partition("-")
    supplement = parts[3] if len(parts) == 4 else ""
    ok, msg = await api.create_season(PLATFORM, name, MODE_MAP[mode_label], start, end, supplement)
    await create_season_cmd.finish(msg)


update_schedule_cmd = on_command("修改档期")


@update_schedule_cmd.handle()
async def handle_update_schedule(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await update_schedule_cmd.finish("权限不足，仅管理员可用")
    parts = args.extract_plain_text().strip().split()
    if len(parts) not in (1, 2) or "-" not in parts[0]:
        await update_schedule_cmd.finish(
            "用法：/修改档期 MMDD-MMDD [补档MMDD]\n示例：修改档期 0726-0727"
        )
        return
    start, _, end = parts[0].partition("-")
    supplement = parts[1] if len(parts) == 2 else ""
    ok, msg = await api.update_schedule(PLATFORM, start, end, supplement)
    await update_schedule_cmd.finish(msg)


end_season_cmd = on_command("结束季度")


@end_season_cmd.handle()
async def handle_end_season(event: MessageEvent):
    if not is_admin(PLATFORM, event.get_user_id()):
        await end_season_cmd.finish("权限不足，仅管理员可用")
    ok, msg = await api.end_season(PLATFORM)
    await end_season_cmd.finish(msg)


season_status_cmd = on_command("季度状态")


@season_status_cmd.handle()
async def handle_season_status(event: MessageEvent):
    info = api.get_season_info(PLATFORM)
    if not info["active"]:
        await season_status_cmd.finish("现在没有进行中的季度")
        return
    lines = [
        f"季度：{info['name']}（{'复盘' if info['mode'] == 'review' else '不复盘'}）",
        f"档期：{info['schedule_start']}-{info['schedule_end']}",
    ]
    if info["supplement_end"]:
        lines.append(f"补档截止：{info['supplement_end']}")
    await season_status_cmd.finish("\n".join(lines))
