from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from plugins.changri_core import PLATFORM
from plugins.changri_core.api import get_setting, is_admin, is_feature_enabled, set_setting
from plugins.changri_rpg.api import find_item_by_name

from . import api


def _is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _default_currency() -> dict | None:
    name = get_setting("auction_currency_name")
    if not name:
        return None
    return find_item_by_name(PLATFORM, name)


auction_settings_cmd = on_command("拍卖设置")


@auction_settings_cmd.handle()
async def handle_auction_settings(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await auction_settings_cmd.finish("权限不足，仅管理员可用")
    currency_name = args.extract_plain_text().strip()
    currency = find_item_by_name(PLATFORM, currency_name)
    if currency is None or currency["type"] != "currency":
        await auction_settings_cmd.finish(f"找不到货币「{currency_name}」")
    set_setting("auction_currency_name", currency_name)
    await auction_settings_cmd.finish(f"拍卖默认货币已设为「{currency_name}」")


add_auction_cmd = on_command("添加拍卖物品")


@add_auction_cmd.handle()
async def handle_add_auction(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await add_auction_cmd.finish("权限不足，仅管理员可用")
    if not is_feature_enabled("auction"):
        await add_auction_cmd.finish("拍卖系统现在关闭中")
        return
    parts = args.extract_plain_text().strip().split()
    if len(parts) < 4:
        await add_auction_cmd.finish("用法：/添加拍卖物品 物品名 起拍价 最低加价 时长小时 [货币名] [失效小时]")
        return
    item_name, start_price_s, min_inc_s, duration_s = parts[:4]
    rest = parts[4:]
    currency_name = None
    expire_hours = None
    if rest and not _is_float(rest[0]):
        currency_name = rest[0]
        rest = rest[1:]
    if rest:
        try:
            expire_hours = float(rest[0])
        except ValueError:
            await add_auction_cmd.finish("失效小时必须是数字")
            return
    if not (start_price_s.isdigit() and min_inc_s.isdigit()):
        await add_auction_cmd.finish("起拍价和最低加价必须是整数")
        return
    try:
        duration = float(duration_s)
    except ValueError:
        await add_auction_cmd.finish("时长必须是数字（小时）")
        return
    item = find_item_by_name(PLATFORM, item_name)
    if item is None:
        await add_auction_cmd.finish(f"找不到物品「{item_name}」")
        return
    currency = find_item_by_name(PLATFORM, currency_name) if currency_name else _default_currency()
    if currency is None or currency["type"] != "currency":
        await add_auction_cmd.finish("找不到货币，请指定货币名或先用「拍卖设置」配置默认货币")
        return
    ok, msg, auction_id = api.add_auction(
        PLATFORM, item["code"], int(start_price_s), int(min_inc_s), duration, currency["code"], currency["name"],
        expire_hours=expire_hours,
    )
    if ok:
        await add_auction_cmd.finish(f"{msg}，编号 {auction_id}")
    await add_auction_cmd.finish(msg)


remove_auction_cmd = on_command("删除拍卖物品")


@remove_auction_cmd.handle()
async def handle_remove_auction(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await remove_auction_cmd.finish("权限不足，仅管理员可用")
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await remove_auction_cmd.finish("用法：/删除拍卖物品 编号")
        return
    if api.remove_auction(PLATFORM, int(text)):
        await remove_auction_cmd.finish("已删除")
        return
    await remove_auction_cmd.finish("找不到这个拍卖")


settle_auction_cmd = on_command("结算拍卖")


@settle_auction_cmd.handle()
async def handle_settle_auction(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await settle_auction_cmd.finish("权限不足，仅管理员可用")
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await settle_auction_cmd.finish("用法：/结算拍卖 编号")
        return
    ok, msg = api.force_settle(PLATFORM, int(text))
    await settle_auction_cmd.finish(msg)


view_auctions_cmd = on_command("查看拍卖")


@view_auctions_cmd.handle()
async def handle_view_auctions(event: MessageEvent):
    results = api.settle_expired_auctions(PLATFORM)
    auctions = api.list_active_auctions(PLATFORM)
    lines = []
    if results:
        lines.append("【刚刚结算】\n" + "\n".join(results))
    if not auctions:
        lines.append("目前没有进行中的拍卖")
    else:
        lines.append("🔨 进行中的拍卖")
        for a in auctions:
            bid_info = f"当前最高 {a['top_bid']['amount']} {a['currency_name']}" if a["top_bid"] else f"起拍价 {a['start_price']} {a['currency_name']}"
            lines.append(f"#{a['id']} {a['name']}：{bid_info}")
    await view_auctions_cmd.finish("\n".join(lines))


def _make_bid_cmd(cmd_name: str, is_anon: bool):
    cmd = on_command(cmd_name)

    @cmd.handle()
    async def handle_bid(event: MessageEvent, args=CommandArg()):
        parts = args.extract_plain_text().strip().split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await cmd.finish(f"用法：/{cmd_name} 价格 编号")
            return
        amount, auction_id = int(parts[0]), int(parts[1])
        ok, msg = api.place_bid(PLATFORM, event.get_user_id(), auction_id, amount, is_anon)
        await cmd.finish(msg)

    return cmd


named_bid_cmd = _make_bid_cmd("实名出价", False)
anon_bid_cmd = _make_bid_cmd("匿名出价", True)
