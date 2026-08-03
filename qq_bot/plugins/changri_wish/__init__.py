from nonebot import on_command
from nonebot.adapters.qq import Bot, MessageEvent
from nonebot.params import CommandArg

from plugins.changri_core import PLATFORM
from plugins.changri_core.api import get_role_name, is_feature_enabled

from . import api

post_wish_cmd = on_command("挂心愿")


@post_wish_cmd.handle()
async def handle_post_wish(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("wish"):
        await post_wish_cmd.finish("心愿系统现在关闭中")
        return
    parts = args.extract_plain_text().strip().split(maxsplit=2)
    if len(parts) != 3:
        await post_wish_cmd.finish("用法：/挂心愿 地点 时段 内容（如 挂心愿 咖啡厅 15:00-16:00 想找人聊聊天）")
        return
    place, time_range, content = parts
    ok, msg = api.post_wish(PLATFORM, event.get_user_id(), place, time_range, content)
    await post_wish_cmd.finish(msg)


bounty_wish_cmd = on_command("悬赏心愿")


@bounty_wish_cmd.handle()
async def handle_bounty_wish(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("wish"):
        await bounty_wish_cmd.finish("心愿系统现在关闭中")
        return
    parts = args.extract_plain_text().strip().split(maxsplit=4)
    if len(parts) != 5 or not parts[3].isdigit():
        await bounty_wish_cmd.finish("用法：/悬赏心愿 地点 时段 物品名 数量 内容")
        return
    place, time_range, item_name, count_s, content = parts
    ok, msg = api.post_wish(
        PLATFORM, event.get_user_id(), place, time_range, content,
        reward_item_name=item_name, reward_count=int(count_s),
    )
    await bounty_wish_cmd.finish(msg)


view_wishes_cmd = on_command("看心愿")


@view_wishes_cmd.handle()
async def handle_view_wishes(event: MessageEvent):
    wishes = api.list_wishes(PLATFORM)
    if not wishes:
        await view_wishes_cmd.finish("心愿板空空如也")
        return
    lines = ["🌠 心愿板"]
    for w in wishes:
        from_role = get_role_name(PLATFORM, w["from_uid"]) or "未知"
        reward = f"　🎁悬赏{w['reward_count']}" if w["reward_code"] else ""
        lines.append(f"#{w['id']} 【{from_role}】{w['day']} {w['time_range']}　{w['place']}{reward}\n　{w['content']}")
    await view_wishes_cmd.finish("\n".join(lines))


pick_wish_cmd = on_command("摘心愿")


@pick_wish_cmd.handle()
async def handle_pick_wish(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("wish"):
        await pick_wish_cmd.finish("心愿系统现在关闭中")
        return
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await pick_wish_cmd.finish("用法：/摘心愿 编号")
        return
    ok, msg, extra = await api.pick_wish(PLATFORM, event.get_user_id(), int(text))
    if ok and extra:
        try:
            await bot.send_to_group(group_openid=extra["group_openid"], message=extra["announce"])
        except Exception:
            pass
    await pick_wish_cmd.finish(msg)


withdraw_wish_cmd = on_command("撤心愿")


@withdraw_wish_cmd.handle()
async def handle_withdraw_wish(event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await withdraw_wish_cmd.finish("用法：/撤心愿 编号")
        return
    ok, msg = api.withdraw_wish(PLATFORM, event.get_user_id(), int(text))
    await withdraw_wish_cmd.finish(msg)
