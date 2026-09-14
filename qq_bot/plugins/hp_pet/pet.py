"""宠物养成：领养、装备、喂食、玩耍、遛、训练。

可以养很多只（对角巷宠物道具本来就铺了一大堆品种），但同一时间只有"装备"中的
那只是活的：心情/饱食度只对它衰减，互动指令也只对它生效，跨系统加成只读它的
羁绊等级。没装备的宠物相当于养在箱子里，状态定格，换回来再接着养。

心情/饱食度会随时间自然衰减（懒惰结算，思路照抄 core_storage.sync_stamina），
所以不理宠物是真的会掉状态的——这是跟"喂一次挂个被动增益"最大的区别。
饿到0之后心情掉得更快，逼着玩家不能只顾着刷羁绊经验不喂饭。

羁绊等级由训练/互动积累的 bond_exp 决定，解锁的加成直接读 bond_level()，
不分"档位跳变"，等级越高效果线性变强，写法最简单。
"""

from __future__ import annotations

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_school import shop_catalog
from plugins.hp_school import storage as school_storage

from . import catalog, storage

MOOD_MAX = 100
SATIETY_MAX = 100

# 衰减：每20分钟结算一轮；吃饱的时候心情掉得慢，饿着（饱食度到0）掉得快一倍
DECAY_INTERVAL_SECONDS = 20 * 60
SATIETY_DECAY_AMOUNT = 2
MOOD_DECAY_AMOUNT = 1
MOOD_DECAY_AMOUNT_HUNGRY = 2

FEED_DAILY_LIMIT = 8
FEED_SATIETY_GAIN = 25
FEED_MOOD_GAIN = 5
FEED_BOND_GAIN = 3

PLAY_COOLDOWN_SECONDS = 20 * 60
PLAY_MOOD_GAIN = 8
PLAY_BOND_GAIN = 2

WALK_STAMINA_COST = 6
WALK_DAILY_LIMIT = 3
WALK_MOOD_GAIN = 10
WALK_BOND_GAIN = 4
WALK_GALLEONS_RANGE = (3, 8)
WALK_SPOOKED_SATIETY_PENALTY = 5

TRAIN_STAMINA_COST = 5
TRAIN_DAILY_LIMIT = 2
TRAIN_BOND_GAIN = 7
TRAIN_MOOD_COST = 3
TRAIN_SATIETY_COST = 3

PET_NAME_MAX_LEN = 10

# 猫头鹰羁绊到2级，女巫周刊每日投稿上限固定+2（不随等级继续叠加）
GOSSIP_LIMIT_BONUS = 2
GOSSIP_LIMIT_UNLOCK_LEVEL = 2

# (达到这个bond_exp, 羁绊等级)
BOND_LEVELS = ((0, 1), (15, 2), (40, 3), (80, 4), (140, 5))


class PetError(Exception):
    pass


def bond_level(bond_exp: int) -> int:
    level = 1
    for threshold, lv in BOND_LEVELS:
        if bond_exp >= threshold:
            level = lv
    return level


def _next_level_threshold(bond_exp: int) -> int | None:
    for threshold, lv in BOND_LEVELS:
        if bond_exp < threshold:
            return threshold
    return None


def _require_enrolled(uid: str) -> None:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise PetError("你还没有分院，先发「/入学」完成入学测试。")


def _sync(row):
    """按经过的时间结算心情/饱食度衰减，结算到读的这一刻为止。row必须是装备中的宠物。"""
    elapsed = core_storage.now() - row["synced_at"]
    ticks = elapsed // DECAY_INTERVAL_SECONDS
    if ticks <= 0:
        return row
    satiety = row["satiety"]
    mood = row["mood"]
    for _ in range(ticks):
        satiety = max(0, satiety - SATIETY_DECAY_AMOUNT)
        rate = MOOD_DECAY_AMOUNT_HUNGRY if satiety <= 0 else MOOD_DECAY_AMOUNT
        mood = max(0, mood - rate)
    new_synced_at = row["synced_at"] + ticks * DECAY_INTERVAL_SECONDS
    storage.update_pet(row["id"], mood=mood, satiety=satiety, synced_at=new_synced_at)
    return storage.get_equipped_pet(row["uid"])


def _require_equipped(uid: str):
    row = storage.get_equipped_pet(uid)
    if not row:
        if storage.list_pets(uid):
            raise PetError("你还没装备宠物。用「/我的宠物们」看看养了哪些，再用「/装备宠物 名字」选一只。")
        raise PetError("你还没有宠物。先去对角巷「/购买」一只，再用「/领养宠物 名字」养起来。")
    return _sync(row)


# ======================== 领养 / 装备 / 改名 / 放生 ========================


def adopt(uid: str, item_input: str) -> dict:
    _require_enrolled(uid)

    item_input = item_input.strip()
    item = shop_catalog.find(item_input)
    if not item or item[2] not in ("宠物", "限定宠物"):
        raise PetError(f"「{item_input}」不是一件宠物道具。去对角巷「/购买 宠物名」买一只吧。")
    item_key, breed_name = item[0], item[1]
    family = catalog.family_of(item_key)
    if not family:
        raise PetError("这只宠物认不出是什么品种，没法领养。")

    if not school_storage.remove_item(uid, item_key, 1):
        raise PetError(f"你的背包里没有「{breed_name}」，先去对角巷「/购买 {breed_name}」。")

    existing = storage.list_pets(uid)
    pet_name = breed_name
    existing_names = {p["pet_name"] for p in existing}
    if pet_name in existing_names:
        n = 2
        while f"{breed_name}{n}" in existing_names:
            n += 1
        pet_name = f"{breed_name}{n}"

    personality = catalog.random_personality()
    is_first = not existing
    storage.create_pet(
        uid, item_key, family, breed_name, pet_name, personality,
        mood=70, satiety=70, equipped=is_first,
    )
    return {
        "breed_name": breed_name,
        "pet_name": pet_name,
        "family_name": catalog.FAMILY_NAMES[family],
        "personality": personality,
        "equipped": is_first,
    }


def my_pets(uid: str) -> list[dict]:
    rows = storage.list_pets(uid)
    return [
        {
            "pet_name": r["pet_name"],
            "breed_name": r["breed_name"],
            "family_name": catalog.FAMILY_NAMES[r["family"]],
            "bond_level": bond_level(r["bond_exp"]),
            "equipped": bool(r["equipped"]),
        }
        for r in rows
    ]


def equip(uid: str, name_input: str) -> dict:
    name_input = name_input.strip()
    if not name_input:
        raise PetError("用法：/装备宠物 名字")
    row = storage.get_pet_by_name(uid, name_input)
    if not row:
        raise PetError(f"你名下没有叫「{name_input}」的宠物，用「/我的宠物们」看看有哪些。")
    if row["equipped"]:
        raise PetError(f"「{name_input}」已经是当前装备的宠物了。")
    storage.equip_pet(uid, row["id"])
    return {"pet_name": row["pet_name"]}


def status(uid: str) -> dict:
    row = _require_equipped(uid)
    level = bond_level(row["bond_exp"])
    return {
        "pet_name": row["pet_name"],
        "breed_name": row["breed_name"],
        "family_name": catalog.FAMILY_NAMES[row["family"]],
        "personality": row["personality"],
        "mood": row["mood"],
        "satiety": row["satiety"],
        "bond_exp": row["bond_exp"],
        "bond_level": level,
        "next_level_at": _next_level_threshold(row["bond_exp"]),
        "perk": _perk_text(row["family"], level),
    }


def rename(uid: str, new_name: str) -> dict:
    row = _require_equipped(uid)
    new_name = new_name.strip()
    if not new_name:
        raise PetError("名字不能是空的。")
    if len(new_name) > PET_NAME_MAX_LEN:
        raise PetError(f"名字最多{PET_NAME_MAX_LEN}个字。")
    if storage.get_pet_by_name(uid, new_name):
        raise PetError(f"你已经有一只叫「{new_name}」的宠物了，换个名字吧。")
    storage.update_pet(row["id"], pet_name=new_name)
    return {"old_name": row["pet_name"], "pet_name": new_name}


def release(uid: str, name_input: str) -> dict:
    name_input = name_input.strip()
    if not name_input:
        raise PetError("用法：/放生宠物 名字")
    row = storage.get_pet_by_name(uid, name_input)
    if not row:
        raise PetError(f"你名下没有叫「{name_input}」的宠物。")
    storage.delete_pet(row["id"])
    return {"pet_name": row["pet_name"], "was_equipped": bool(row["equipped"])}


# ======================== 互动（只对装备中的宠物生效） ========================


def _resolve_food(item_input: str) -> tuple[str, str]:
    from plugins.hp_school import kitchen

    if item_input in kitchen.KITCHEN_MATERIALS:
        return item_input, kitchen.KITCHEN_MATERIALS[item_input][0]
    for key, (name, _category) in kitchen.KITCHEN_MATERIALS.items():
        if name == item_input:
            return key, name
    item = shop_catalog.find(item_input)
    if item and item[2] == "零食":
        return item[0], item[1]
    return "", ""


def feed(uid: str, food_input: str) -> dict:
    row = _require_equipped(uid)
    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(uid, day)
    if daily["feeds"] >= FEED_DAILY_LIMIT:
        raise PetError(f"今天已经喂过{FEED_DAILY_LIMIT}次了，{row['pet_name']}已经吃得很饱了。")

    item_key, item_name = _resolve_food(food_input.strip())
    if not item_key:
        raise PetError(f"找不到「{food_input.strip()}」这个吃的，食材和零食都可以拿来喂。")
    if not school_storage.remove_item(uid, item_key, 1):
        raise PetError(f"你的背包里没有「{item_name}」。")

    new_satiety = min(SATIETY_MAX, row["satiety"] + FEED_SATIETY_GAIN)
    new_mood = min(MOOD_MAX, row["mood"] + FEED_MOOD_GAIN)
    new_bond = row["bond_exp"] + FEED_BOND_GAIN
    storage.update_pet(row["id"], satiety=new_satiety, mood=new_mood, bond_exp=new_bond)
    storage.increment_daily(uid, day, "feeds")

    return {
        "pet_name": row["pet_name"],
        "item_name": item_name,
        "line": catalog.feed_line(row["personality"], row["pet_name"]),
        "mood": new_mood,
        "satiety": new_satiety,
        "level_up": _level_up(row["bond_exp"], new_bond),
    }


def play(uid: str) -> dict:
    row = _require_equipped(uid)
    elapsed = core_storage.now() - row["last_play_at"]
    if elapsed < PLAY_COOLDOWN_SECONDS:
        wait_min = (PLAY_COOLDOWN_SECONDS - elapsed) // 60 + 1
        raise PetError(f"{row['pet_name']}刚玩过，有点累，约{wait_min}分钟后再来找它玩。")

    new_mood = min(MOOD_MAX, row["mood"] + PLAY_MOOD_GAIN)
    new_bond = row["bond_exp"] + PLAY_BOND_GAIN
    storage.update_pet(row["id"], mood=new_mood, bond_exp=new_bond, last_play_at=core_storage.now())

    return {
        "pet_name": row["pet_name"],
        "line": catalog.play_line(row["personality"], row["pet_name"]),
        "mood": new_mood,
        "level_up": _level_up(row["bond_exp"], new_bond),
    }


def _random_common_material() -> tuple[str, str]:
    from plugins.hp_school import kitchen

    pool = [(key, info[0]) for key, info in kitchen.KITCHEN_MATERIALS.items() if info[1] == "基础材料"]
    return random.choice(pool)


def walk(uid: str) -> dict:
    row = _require_equipped(uid)
    player = core_storage.sync_stamina(uid)
    if player["stamina"] < WALK_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise PetError(
            f"你自己的体力不够遛宠物了（{player['stamina']}/{core_storage.STAMINA_MAX}），"
            f"约{wait_min}分钟后再来。"
        )
    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(uid, day)
    if daily["walks"] >= WALK_DAILY_LIMIT:
        raise PetError(f"今天已经遛过{WALK_DAILY_LIMIT}次了，明天再带{row['pet_name']}出去。")

    core_storage.spend_stamina(uid, WALK_STAMINA_COST)
    storage.increment_daily(uid, day, "walks")

    outcome = catalog.roll_walk_outcome()
    mood_gain = WALK_MOOD_GAIN
    bond_gain = WALK_BOND_GAIN
    extra_satiety_loss = 0
    reward: dict = {}

    if outcome == "material":
        mat_key, mat_name = _random_common_material()
        school_storage.add_item(uid, mat_key, 1)
        reward["material"] = mat_name
    elif outcome == "galleons":
        amount = random.randint(*WALK_GALLEONS_RANGE)
        core_storage.add_galleons(uid, amount)
        reward["galleons"] = amount
    elif outcome == "spooked":
        mood_gain = 0
        bond_gain = 1
        extra_satiety_loss = WALK_SPOOKED_SATIETY_PENALTY

    new_mood = min(MOOD_MAX, row["mood"] + mood_gain)
    new_satiety = max(0, row["satiety"] - extra_satiety_loss)
    new_bond = row["bond_exp"] + bond_gain
    storage.update_pet(row["id"], mood=new_mood, satiety=new_satiety, bond_exp=new_bond)

    return {
        "pet_name": row["pet_name"],
        "outcome": outcome,
        "line": catalog.WALK_LINES[outcome].format(n=row["pet_name"]),
        "mood": new_mood,
        "satiety": new_satiety,
        "level_up": _level_up(row["bond_exp"], new_bond),
        **reward,
    }


def train(uid: str) -> dict:
    row = _require_equipped(uid)
    player = core_storage.sync_stamina(uid)
    if player["stamina"] < TRAIN_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise PetError(
            f"你自己的体力不够训练宠物了（{player['stamina']}/{core_storage.STAMINA_MAX}），"
            f"约{wait_min}分钟后再来。"
        )
    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(uid, day)
    if daily["trains"] >= TRAIN_DAILY_LIMIT:
        raise PetError(f"今天已经训练过{TRAIN_DAILY_LIMIT}次了，让{row['pet_name']}歇一歇。")

    core_storage.spend_stamina(uid, TRAIN_STAMINA_COST)
    storage.increment_daily(uid, day, "trains")

    new_mood = max(0, row["mood"] - TRAIN_MOOD_COST)
    new_satiety = max(0, row["satiety"] - TRAIN_SATIETY_COST)
    new_bond = row["bond_exp"] + TRAIN_BOND_GAIN
    storage.update_pet(row["id"], mood=new_mood, satiety=new_satiety, bond_exp=new_bond)

    return {
        "pet_name": row["pet_name"],
        "line": catalog.train_line(row["personality"], row["pet_name"]),
        "mood": new_mood,
        "satiety": new_satiety,
        "bond_exp": new_bond,
        "level_up": _level_up(row["bond_exp"], new_bond),
    }


def _level_up(old_bond_exp: int, new_bond_exp: int) -> int | None:
    old_level = bond_level(old_bond_exp)
    new_level = bond_level(new_bond_exp)
    return new_level if new_level > old_level else None


# ======================== 跨系统联动加成（只读当前装备的宠物） ========================


def _perk_text(family: str, level: int) -> str:
    if family == "owl":
        unlocked = level >= GOSSIP_LIMIT_UNLOCK_LEVEL
        return (
            f"《女巫周刊》每日投稿上限 +{GOSSIP_LIMIT_BONUS}"
            if unlocked
            else f"羁绊等级到{GOSSIP_LIMIT_UNLOCK_LEVEL}解锁：《女巫周刊》每日投稿上限+{GOSSIP_LIMIT_BONUS}"
        )
    if family == "cat":
        discount = max(0, level - 1)
        return f"厨房探索消耗体力 -{discount}" if discount else "羁绊等级到2解锁：厨房探索省体力"
    if family in catalog.FOREST_ASSIST_FAMILIES:
        mult = max(0.5, 1 - 0.1 * (level - 1))
        return f"禁林遇袭概率 ×{mult:.1f}" if mult < 1 else "羁绊等级到2解锁：降低禁林遇袭概率"
    return ""


def gossip_daily_limit_bonus(uid: str) -> int:
    row = storage.get_equipped_pet(uid)
    if not row or row["family"] != "owl":
        return 0
    return GOSSIP_LIMIT_BONUS if bond_level(row["bond_exp"]) >= GOSSIP_LIMIT_UNLOCK_LEVEL else 0


def forage_stamina_discount(uid: str) -> int:
    row = storage.get_equipped_pet(uid)
    if not row or row["family"] != "cat":
        return 0
    return max(0, bond_level(row["bond_exp"]) - 1)


def forest_ambush_multiplier(uid: str) -> float:
    row = storage.get_equipped_pet(uid)
    if not row or row["family"] not in catalog.FOREST_ASSIST_FAMILIES:
        return 1.0
    return max(0.5, 1 - 0.1 * (bond_level(row["bond_exp"]) - 1))
