import time

from nonebot import get_driver, on_command, require
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from plugins.changri_core import PLATFORM
from plugins.changri_core.api import get_role_name, get_uid_by_role_name, is_admin

from . import api

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402


@scheduler.scheduled_job("interval", minutes=5, id="rpg_expire_sweep")
async def _sweep_expired_items():
    api.remove_expired_items(PLATFORM)

TYPE_NAMES = {"item": "道具", "interact": "互动道具", "currency": "货币", "preset": "预设道具"}


def _require_role(uid: str) -> str | None:
    return get_role_name(PLATFORM, uid)


init_preset_cmd = on_command("初始化预设物品")


@init_preset_cmd.handle()
async def handle_init_preset(event: MessageEvent):
    if not is_admin(PLATFORM, event.get_user_id()):
        await init_preset_cmd.finish("权限不足，仅管理员可用")
    api.init_preset_items(PLATFORM)
    await init_preset_cmd.finish("预设物品已初始化")


upload_item_cmd = on_command("上载")


@upload_item_cmd.handle()
async def handle_upload_item(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await upload_item_cmd.finish("权限不足，仅管理员可用")
    text = args.extract_plain_text().strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or parts[0] not in ("道具", "互动道具", "货币"):
        await upload_item_cmd.finish("用法：/上载 道具/互动道具/货币 名字:描述")
    type_map = {"道具": "item", "互动道具": "interact", "货币": "currency"}
    name, _, desc = parts[1].replace("：", ":").partition(":")
    name = name.strip()
    if not name:
        await upload_item_cmd.finish("用法：/上载 道具/互动道具/货币 名字:描述")
    code = api.add_item(PLATFORM, name, desc.strip(), type_map[parts[0]])
    await upload_item_cmd.finish(f"已添加「{name}」，编号 {code}")


inventory_cmd = on_command("背包")


@inventory_cmd.handle()
async def handle_inventory(event: MessageEvent):
    uid = event.get_user_id()
    if _require_role(uid) is None:
        await inventory_cmd.finish("你还没有角色，先用「/创建新角色 <角色名>」创建一个")
    items = api.get_inventory(PLATFORM, uid)
    if not items:
        await inventory_cmd.finish("背包空空如也")
    lines = ["🎒 背包"]
    for it in items:
        extra = f"（剩余{it['remaining_uses']}次）" if it["remaining_uses"] is not None else ""
        if it["expires_at"] is not None:
            remaining_min = max(0, (it["expires_at"] - int(time.time())) // 60)
            extra += f"（{remaining_min}分钟后失效）"
        lines.append(f"- {it['name']} x{it['count']}{extra}")
    await inventory_cmd.finish("\n".join(lines))


give_item_cmd = on_command("赠送道具")


@give_item_cmd.handle()
async def handle_give_item(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3 or not parts[2].isdigit():
        await give_item_cmd.finish("用法：/赠送道具 角色名 物品名 数量")
    target_role, item_name, count_s = parts
    count = int(count_s)
    target_uid = get_uid_by_role_name(PLATFORM, target_role)
    if target_uid is None:
        await give_item_cmd.finish(f"找不到角色「{target_role}」")
    item = api.find_item_by_name(PLATFORM, item_name)
    if item is None:
        await give_item_cmd.finish(f"找不到物品「{item_name}」")
    if api.transfer_item(PLATFORM, uid, target_uid, item["code"], count):
        await give_item_cmd.finish(f"已赠送 {item_name} x{count} 给 {target_role}")
    await give_item_cmd.finish("背包里没有这么多")


adjust_cmd = on_command("调整")


@adjust_cmd.handle()
async def handle_adjust(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await adjust_cmd.finish("权限不足，仅管理员可用")
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3:
        await adjust_cmd.finish("用法：/调整 角色名 物品名 正负数量")
    target_role, item_name, delta_s = parts
    try:
        delta = int(delta_s)
    except ValueError:
        await adjust_cmd.finish("数量必须是整数")
        return
    target_uid = get_uid_by_role_name(PLATFORM, target_role)
    if target_uid is None:
        await adjust_cmd.finish(f"找不到角色「{target_role}」")
    item = api.find_item_by_name(PLATFORM, item_name)
    if item is None:
        await adjust_cmd.finish(f"找不到物品「{item_name}」")
    if delta >= 0:
        api.add_to_inventory(PLATFORM, target_uid, item["code"], delta)
        await adjust_cmd.finish(f"已给 {target_role} 增加 {item_name} x{delta}")
    else:
        if api.remove_from_inventory(PLATFORM, target_uid, item["code"], -delta):
            await adjust_cmd.finish(f"已扣除 {target_role} 的 {item_name} x{-delta}")
        await adjust_cmd.finish("对方背包里没有这么多，扣除失败")


list_shop_listing_cmd = on_command("上架商城")


@list_shop_listing_cmd.handle()
async def handle_list_shop(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await list_shop_listing_cmd.finish("权限不足，仅管理员可用")
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3 or not parts[1].isdigit():
        await list_shop_listing_cmd.finish("用法：/上架商城 物品名 价格 货币名")
    item_name, price_s, currency_name = parts
    item = api.find_item_by_name(PLATFORM, item_name)
    currency = api.find_item_by_name(PLATFORM, currency_name)
    if item is None:
        await list_shop_listing_cmd.finish(f"找不到物品「{item_name}」")
    if currency is None or currency["type"] != "currency":
        await list_shop_listing_cmd.finish(f"找不到货币「{currency_name}」")
    api.add_shop_listing(PLATFORM, item["code"], int(price_s), currency["code"], currency["name"])
    await list_shop_listing_cmd.finish(f"「{item_name}」已上架商城，价格 {price_s} {currency_name}")


unlist_shop_cmd = on_command("商城下架")


@unlist_shop_cmd.handle()
async def handle_unlist_shop(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await unlist_shop_cmd.finish("权限不足，仅管理员可用")
    item_name = args.extract_plain_text().strip()
    item = api.find_item_by_name(PLATFORM, item_name)
    if item is None or not api.remove_shop_listing(PLATFORM, item["code"]):
        await unlist_shop_cmd.finish(f"商城里没有「{item_name}」")
    await unlist_shop_cmd.finish(f"「{item_name}」已下架")


shop_cmd = on_command("商城")


@shop_cmd.handle()
async def handle_shop(event: MessageEvent):
    listings = api.list_shop(PLATFORM)
    if not listings:
        await shop_cmd.finish("商城空空如也")
    lines = ["🏪 商城"]
    for it in listings:
        lines.append(f"- {it['name']}：{it['price']} {it['currency_name']}")
    await shop_cmd.finish("\n".join(lines))


buy_cmd = on_command("购买")


@buy_cmd.handle()
async def handle_buy(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    if _require_role(uid) is None:
        await buy_cmd.finish("你还没有角色，先用「/创建新角色 <角色名>」创建一个")
    parts = args.extract_plain_text().strip().split()
    if not parts:
        await buy_cmd.finish("用法：/购买 物品名 [数量]")
    item_name = parts[0]
    count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    item = api.find_item_by_name(PLATFORM, item_name)
    if item is None:
        await buy_cmd.finish(f"找不到物品「{item_name}」")
    ok, msg = api.buy_from_shop(PLATFORM, uid, item["code"], count)
    await buy_cmd.finish(msg)


sell_cmd = on_command("售卖")


@sell_cmd.handle()
async def handle_sell(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    if _require_role(uid) is None:
        await sell_cmd.finish("你还没有角色，先用「/创建新角色 <角色名>」创建一个")
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 4 or not parts[1].isdigit() or not parts[2].isdigit():
        await sell_cmd.finish("用法：/售卖 物品名 数量 价格 货币名")
    item_name, count_s, price_s, currency_name = parts
    currency = api.find_item_by_name(PLATFORM, currency_name)
    if currency is None or currency["type"] != "currency":
        await sell_cmd.finish(f"找不到货币「{currency_name}」")
    item = api.find_item_by_name(PLATFORM, item_name)
    if item is None:
        await sell_cmd.finish(f"找不到物品「{item_name}」")
    ok, msg, listing_id = api.create_market_listing(
        PLATFORM, uid, item["code"], int(count_s), int(price_s), currency["code"], currency["name"]
    )
    if ok:
        await sell_cmd.finish(f"{msg}，挂单编号 {listing_id}")
    await sell_cmd.finish(msg)


market_cmd = on_command("二手市场")


@market_cmd.handle()
async def handle_market(event: MessageEvent):
    listings = api.list_market(PLATFORM)
    if not listings:
        await market_cmd.finish("二手市场空空如也")
    lines = ["🛒 二手市场"]
    for it in listings:
        seller_role = get_role_name(PLATFORM, it["seller_uid"]) or "未知"
        lines.append(f"#{it['id']} {it['name']} x{it['count']}：{it['price']} {it['currency_name']}（卖家：{seller_role}）")
    await market_cmd.finish("\n".join(lines))


market_buy_cmd = on_command("二手买")


@market_buy_cmd.handle()
async def handle_market_buy(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await market_buy_cmd.finish("用法：/二手买 编号")
    ok, msg = api.buy_market_listing(PLATFORM, uid, int(text))
    await market_buy_cmd.finish(msg)


cancel_listing_cmd = on_command("撤销卖单")


@cancel_listing_cmd.handle()
async def handle_cancel_listing(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await cancel_listing_cmd.finish("用法：/撤销卖单 编号")
    ok, msg = api.cancel_market_listing(PLATFORM, uid, int(text))
    await cancel_listing_cmd.finish(msg)
