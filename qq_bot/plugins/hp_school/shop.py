"""对角巷商店：购买（花加隆进背包）、吃零食（回体力值）、恶作剧道具。

扫帚的装备动作不在这里——扫帚买回来放在背包里，真正"装备"生效是
hp_events 的 /装备扫帚，因为魁地奇属性表(quidditch_players)归 hp_events 管，
这边不反向依赖它，保持 hp_events 依赖 hp_school 单向的关系。

宠物/零食池子铺得比较大，每次只随机开放一部分，每3小时刷新——用时间桶当随机种子
现算现得，不用额外存"这一轮开放了什么"的状态，也不用另开定时任务。
"""

import random

from plugins.hp_core import storage as core_storage

from . import shop_catalog, storage

ROTATION_INTERVAL_SECONDS = 3 * 3600
ROTATION_SIZE = {"零食": 6, "宠物": 5}
GIFT_RESTOCK_INTERVAL_SECONDS = 2 * 3600  # 礼物全服库存每2小时补货一轮


class ShopError(Exception):
    pass


def _rotation_bucket() -> int:
    return core_storage.now() // ROTATION_INTERVAL_SECONDS


def seconds_to_next_rotation() -> int:
    return ROTATION_INTERVAL_SECONDS - (core_storage.now() % ROTATION_INTERVAL_SECONDS)


def _restock_bucket() -> int:
    return core_storage.now() // GIFT_RESTOCK_INTERVAL_SECONDS


def seconds_to_next_restock() -> int:
    return GIFT_RESTOCK_INTERVAL_SECONDS - (core_storage.now() % GIFT_RESTOCK_INTERVAL_SECONDS)


def gift_remaining(item_key: str, capacity: int) -> int:
    return max(0, capacity - storage.get_gift_sold(item_key, _restock_bucket()))


def current_offerings(category: str) -> list[tuple]:
    """扫帚/装备/恶作剧常驻全部返回；零食/宠物按3小时轮换只返回一部分。"""
    pool = shop_catalog.list_by_category(category)
    if category not in shop_catalog.ROTATING_CATEGORIES:
        return pool
    size = min(ROTATION_SIZE.get(category, len(pool)), len(pool))
    rng = random.Random(f"{category}:{_rotation_bucket()}")
    return rng.sample(pool, k=size)


def buy(uid: str, item_input: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise ShopError("你还没有分院，先发「/入学」完成入学测试。")

    item = shop_catalog.find(item_input.strip())
    if not item:
        raise ShopError("对角巷没有这件东西，检查一下名字。")
    key, name, category, price, desc, effect = item

    if category in shop_catalog.ROTATING_CATEGORIES:
        if item not in current_offerings(category):
            raise ShopError(f"「{name}」现在没有在卖，等下一轮刷新（用「/对角巷 {category}」看当前在卖什么）。")

    # 库存占用、扣钱和写入背包必须同成同败，避免进程在步骤之间退出时丢钱/丢货。
    purchase = storage.buy_item_atomic(
        uid,
        key,
        price,
        gift_bucket=_restock_bucket() if category == "礼物" else None,
        gift_capacity=effect["stock"] if category == "礼物" else None,
    )
    if purchase == "sold_out":
        wait_min = seconds_to_next_restock() // 60 + 1
        raise ShopError(f"「{name}」本轮已经被抢光了，还有约{wait_min}分钟补货。")
    if purchase == "insufficient_funds":
        player = core_storage.get_player(uid)
        raise ShopError(f"加隆不够。当前{player['galleons']}，「{name}」要{price}加隆。")

    return {"name": name, "category": category, "price": price, "desc": desc}


def eat_snack(uid: str, item_input: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise ShopError("你还没有分院，先发「/入学」完成入学测试。")

    item = shop_catalog.find(item_input.strip())
    if not item:
        raise ShopError("没有这个东西。")
    key, name, category, price, desc, effect = item
    if category != "零食":
        raise ShopError(f"「{name}」不是零食，吃不了。")

    if not storage.remove_item(uid, key, 1):
        raise ShopError(f"背包里没有「{name}」，先去「/对角巷购买 {name}」。")

    restore = effect.get("restore_stamina", 0)
    player = core_storage.sync_stamina(uid)
    before = player["stamina"]
    new_stamina = min(core_storage.STAMINA_MAX, before + restore)
    actual_restored = new_stamina - before
    if actual_restored > 0:
        core_storage.spend_stamina(uid, -actual_restored)  # 负数=增加，复用同一个函数

    return {"name": name, "restored": actual_restored, "new_stamina": new_stamina}


def use_prank(uid: str, item_input: str, target_uid: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise ShopError("你还没有分院，先发「/入学」完成入学测试。")
    if target_uid == uid:
        raise ShopError("不能对自己用，没意思。")
    target = core_storage.get_player(target_uid)
    if not target or not target["house"]:
        raise ShopError("对方还没有分院，整不了。")

    item = shop_catalog.find(item_input.strip())
    if not item or item[2] != "恶作剧":
        raise ShopError("这不是恶作剧道具。")
    key, name, category, price, desc, effect = item

    if not storage.remove_item(uid, key, 1):
        raise ShopError(f"背包里没有「{name}」，先去「/对角巷购买 {name}」。")

    duration_seconds = effect["duration_hours"] * 3600
    core_storage.add_active_effect(target_uid, key, effect["status_label"], duration_seconds)
    return {"name": name, "target": target_uid, "label": effect["status_label"], "hours": effect["duration_hours"]}


def _find_material(key_or_name: str):
    """禁林材料的目录在 hp_events 里。延迟导入避免和 hp_events→hp_school 的依赖成环。"""
    try:
        from plugins.hp_events import forest_catalog

        return forest_catalog.find_material(key_or_name)
    except Exception:
        return None


def get_bag(uid: str) -> list[dict]:
    rows = storage.get_inventory(uid)
    result = []
    for row in rows:
        item = shop_catalog.find(row["item_key"])
        if item:
            _, name, category, price, desc, effect = item
            result.append({"name": name, "category": category, "quantity": row["quantity"]})
            continue
        material = _find_material(row["item_key"])
        if material:
            result.append({"name": material[1], "category": "魔药材料", "quantity": row["quantity"]})
    return result


def sell(uid: str, item_input: str, quantity: int = 1) -> dict:
    """目前只有禁林带回来的魔药材料能卖。等以后做熬药系统，这些材料会变成原料。"""
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise ShopError("你还没有分院，先发「/入学 你的名字」完成入学测试。")
    if quantity < 1:
        raise ShopError("数量至少是1。")

    material = _find_material(item_input.strip())
    if not material:
        if shop_catalog.find(item_input.strip()):
            raise ShopError("这个东西不收，目前只回收禁林带回来的魔药材料。")
        raise ShopError("没有这个东西。")
    key, name, unit_price, min_depth = material

    if not storage.remove_item(uid, key, quantity):
        have = storage.get_item_quantity(uid, key)
        raise ShopError(f"你只有{have}份「{name}」，卖不了{quantity}份。")

    total = unit_price * quantity
    core_storage.add_galleons(uid, total)
    return {"name": name, "quantity": quantity, "unit_price": unit_price, "total": total}
