"""核心玩法逻辑：运气恢复、探宝、开石、观察、鉴定、变现、眼力成长。"""

import random
import sqlite3

from . import catalog, storage, titles

storage.init_db()

LUCK_MAX = 20
LUCK_REGEN_SECONDS = 10 * 60  # 每10分钟自然恢复1点运气
EXPLORE_COST = 5
MINE_COST = 5
MAX_CLUES_PER_ITEM = 3

EXPLORE_OUTCOME_WEIGHTS = [
    ("empty", 45),
    ("stone", 30),
    ("antique", 15),
    ("calligraphy", 10),
]

MINE_OUTCOME_WEIGHTS = [
    ("dirt", 55),
    ("gem", 45),
]

QUALITY_NAMES = [t[0] for t in catalog.QUALITY_TIERS]
QUALITY_WEIGHTS_NORMAL = [50, 25, 13, 8, 4]
QUALITY_WEIGHTS_LUCKY = [35, 25, 18, 14, 8]  # 满运气出手时，档次分布更favor高档

EYE_LEVEL_THRESHOLDS = [0, 80, 200, 400, 700, 1100, 1600, 2200, 3000, 4000]  # 总经验达到即为对应等级
MAX_EYE_LEVEL = len(EYE_LEVEL_THRESHOLDS)


class GameError(Exception):
    pass


# ======================== 运气 ========================


def sync_player(uid: str) -> sqlite3.Row:
    player = storage.get_or_create_player(uid)
    if player["luck"] >= LUCK_MAX:
        if storage.now() - player["luck_updated_at"] > 5:
            storage.update_player(uid, luck_updated_at=storage.now())
            player = storage.get_or_create_player(uid)
        return player

    elapsed = storage.now() - player["luck_updated_at"]
    regen = elapsed // LUCK_REGEN_SECONDS
    if regen > 0:
        new_luck = min(LUCK_MAX, player["luck"] + regen)
        consumed = regen * LUCK_REGEN_SECONDS
        storage.update_player(uid, luck=new_luck, luck_updated_at=player["luck_updated_at"] + consumed)
        player = storage.get_or_create_player(uid)
    return player


def seconds_to_next_luck(player: sqlite3.Row) -> int:
    if player["luck"] >= LUCK_MAX:
        return 0
    elapsed_into_tick = (storage.now() - player["luck_updated_at"]) % LUCK_REGEN_SECONDS
    return LUCK_REGEN_SECONDS - elapsed_into_tick


def seconds_to_full(player: sqlite3.Row) -> int:
    if player["luck"] >= LUCK_MAX:
        return 0
    needed = LUCK_MAX - player["luck"]
    return seconds_to_next_luck(player) + (needed - 1) * LUCK_REGEN_SECONDS


# ======================== 眼力等级 ========================


def level_from_exp(total_exp: int) -> int:
    level = 1
    for i, threshold in enumerate(EYE_LEVEL_THRESHOLDS):
        if total_exp >= threshold:
            level = i + 1
    return min(level, MAX_EYE_LEVEL)


def grant_eye_exp(uid: str, amount: int) -> tuple[int, bool]:
    """返回 (新等级, 是否升级)。"""
    storage.add_eye_exp(uid, amount)
    player = storage.get_or_create_player(uid)
    old_level = player["eye_level"]
    new_level = level_from_exp(player["eye_exp"])
    leveled_up = new_level != old_level
    if leveled_up:
        storage.set_eye_level(uid, new_level, player["eye_exp"])
    return new_level, leveled_up


# ======================== 生成藏品 ========================


def _pick_quality(lucky: bool) -> tuple[str, float, int]:
    weights = QUALITY_WEIGHTS_LUCKY if lucky else QUALITY_WEIGHTS_NORMAL
    return random.choices(catalog.QUALITY_TIERS, weights=weights, k=1)[0]


def _compute_rarity(item_type: catalog.ItemType, quality_bonus: int, dynasty: str) -> int:
    score = item_type.base_rarity + quality_bonus
    if dynasty:
        score += round((catalog.DYNASTY_MULTIPLIER.get(dynasty, 1.0) - 1) * 100)
    return score


def _compute_value(item_type: catalog.ItemType, quality_mult: float, dynasty: str) -> int:
    value = item_type.base_value * quality_mult
    if dynasty:
        value *= catalog.DYNASTY_MULTIPLIER.get(dynasty, 1.0)
    return max(int(value), 1)


def _spawn_item(uid: str, category: str, kind: str, lucky: bool, revealed: bool = False) -> sqlite3.Row:
    candidates = catalog.ITEM_TYPES_BY_CATEGORY[category]
    weights = [1.0 / t.base_rarity for t in candidates]
    item_type = random.choices(candidates, weights=weights, k=1)[0]
    quality_name, quality_mult, quality_bonus = _pick_quality(lucky)
    dynasty = random.choice(item_type.dynasty_pool) if item_type.dynasty_pool else ""
    rarity_score = _compute_rarity(item_type, quality_bonus, dynasty)
    base_value = _compute_value(item_type, quality_mult, dynasty)
    item_id = storage.create_item(
        uid=uid,
        category=category,
        type_name=item_type.name,
        dynasty=dynasty,
        quality=quality_name,
        base_value=base_value,
        rarity_score=rarity_score,
        kind=kind,
        is_opened=1 if revealed else 0,
    )
    return storage.get_item(item_id)


# ======================== 探宝 ========================


def explore(uid: str) -> dict:
    player = sync_player(uid)
    if player["luck"] < EXPLORE_COST:
        raise GameError(
            f"运气不够。当前 {player['luck']}/{LUCK_MAX}，探宝需要 {EXPLORE_COST}。"
            f"还差 {seconds_to_next_luck(player) // 60 + 1} 分钟恢复下一点。"
        )
    lucky_run = player["luck"] >= LUCK_MAX
    storage.update_player(uid, luck=player["luck"] - EXPLORE_COST)

    outcome_names = [o[0] for o in EXPLORE_OUTCOME_WEIGHTS]
    outcome_weights = [o[1] for o in EXPLORE_OUTCOME_WEIGHTS]
    outcome = random.choices(outcome_names, weights=outcome_weights, k=1)[0]

    if outcome == "empty":
        return {"outcome": "empty", "item": None, "new_titles": []}
    if outcome == "stone":
        item = _spawn_item(uid, catalog.STONE_CATEGORY, "stone", lucky_run)
        return {"outcome": "stone", "item": item, "new_titles": []}
    if outcome == "antique":
        category = random.choice(["瓷器", "青铜器", "古玉器", "文房", "钱币"])
        item = _spawn_item(uid, category, "antique", lucky_run)
        return {"outcome": "antique", "item": item, "new_titles": []}
    item = _spawn_item(uid, "字画", "antique", lucky_run)
    return {"outcome": "calligraphy", "item": item, "new_titles": []}


# ======================== 挖矿 ========================


def mine(uid: str) -> dict:
    player = sync_player(uid)
    if player["luck"] < MINE_COST:
        raise GameError(
            f"运气不够。当前 {player['luck']}/{LUCK_MAX}，挖矿需要 {MINE_COST}。"
            f"还差 {seconds_to_next_luck(player) // 60 + 1} 分钟恢复下一点。"
        )
    lucky_run = player["luck"] >= LUCK_MAX
    storage.update_player(uid, luck=player["luck"] - MINE_COST)
    storage.increment_counter(uid, "mine_count")

    outcome_names = [o[0] for o in MINE_OUTCOME_WEIGHTS]
    outcome_weights = [o[1] for o in MINE_OUTCOME_WEIGHTS]
    outcome = random.choices(outcome_names, weights=outcome_weights, k=1)[0]

    if outcome == "dirt":
        return {"outcome": "dirt", "item": None, "new_titles": check_titles(uid)}
    item = _spawn_item(uid, catalog.GEM_CATEGORY, "gem", lucky_run, revealed=True)
    return {"outcome": "gem", "item": item, "new_titles": check_titles(uid)}


# ======================== 开石 ========================


def open_stone(uid: str, item_id: int) -> dict:
    item = storage.get_item(item_id)
    if not item or item["uid"] != uid:
        raise GameError("找不到这件东西，检查一下编号。")
    if item["kind"] != "stone":
        raise GameError("这不是原石，用不上开石。")
    if item["is_opened"]:
        raise GameError("已经开过了。")
    storage.update_item(item_id, is_opened=1, status="背包")
    grant_eye_exp(uid, 3)
    item = storage.get_item(item_id)
    return {"item": item, "new_titles": check_titles(uid)}


# ======================== 观察 ========================


def observe(uid: str, item_id: int) -> dict:
    item = storage.get_item(item_id)
    if not item or item["uid"] != uid:
        raise GameError("找不到这件东西，检查一下编号。")
    if item["kind"] != "antique":
        raise GameError("这类东西用不上细节观察，直接开石就行。")
    if item["is_identified"]:
        raise GameError("已经鉴定过了。")

    clues = storage.get_clues(item)
    if len(clues) >= MAX_CLUES_PER_ITEM:
        raise GameError("能看的细节都看过了，该出手鉴定了。")
    dims = catalog.CLUE_DIMENSIONS.get(item["category"], [])
    available = [d for d in dims if d not in clues]
    if not available:
        raise GameError("能看的细节都看过了，该出手鉴定了。")

    player = sync_player(uid)
    dim = random.choice(available)
    accurate_chance = min(0.35 + player["eye_level"] * 0.06, 0.85)
    vague_chance = 0.25
    roll = random.random()
    if roll < accurate_chance:
        text = random.choice(catalog.CLUE_TEMPLATES_ACCURATE).format(
            dim=dim, dynasty=item["dynasty"] or "本朝", quality=item["quality"]
        )
    elif roll < accurate_chance + vague_chance:
        text = random.choice(catalog.CLUE_TEMPLATES_VAGUE).format(dim=dim)
    else:
        other_dynasties = [d for d in catalog.DYNASTY_MULTIPLIER if d != item["dynasty"]]
        fake_dynasty = random.choice(other_dynasties) if other_dynasties else "不明"
        text = random.choice(catalog.CLUE_TEMPLATES_MISLEADING).format(dim=dim, dynasty=fake_dynasty)

    storage.add_clue(item_id, dim)
    return {"dimension": dim, "text": text, "clue_count": len(clues) + 1}


# ======================== 鉴定 ========================


def identify(uid: str, item_id: int) -> dict:
    item = storage.get_item(item_id)
    if not item or item["uid"] != uid:
        raise GameError("找不到这件东西，检查一下编号。")
    if item["kind"] != "antique":
        raise GameError("这类东西用不上鉴定，直接开石就行。")
    if item["is_identified"]:
        raise GameError("已经鉴定过了。")

    player = sync_player(uid)
    clue_count = len(storage.get_clues(item))
    base = 30 + player["eye_level"] * 8
    clue_bonus = min(clue_count * 10, 30)
    final_chance = min(base + clue_bonus, 90)
    roll = random.randint(1, 100)
    success = roll <= final_chance

    if success:
        perceived_type = item["type_name"]
        perceived_dynasty = item["dynasty"]
        exp_gain = 15
        storage.increment_counter(uid, "identify_success_count")
    else:
        candidates = [t for t in catalog.ITEM_TYPES_BY_CATEGORY[item["category"]] if t.name != item["type_name"]]
        wrong_type = random.choice(candidates)
        perceived_type = wrong_type.name
        pool = wrong_type.dynasty_pool or tuple(catalog.DYNASTY_MULTIPLIER)
        perceived_dynasty = random.choice(pool)
        exp_gain = 5
        storage.increment_counter(uid, "identify_fail_count")

    storage.update_item(
        item_id,
        is_identified=1,
        identify_correct=1 if success else 0,
        perceived_type=perceived_type,
        perceived_dynasty=perceived_dynasty,
    )
    new_level, leveled_up = grant_eye_exp(uid, exp_gain)

    return {
        "success": success,
        "chance": final_chance,
        "roll": roll,
        "perceived_type": perceived_type,
        "perceived_dynasty": perceived_dynasty,
        "true_type": item["type_name"],
        "true_dynasty": item["dynasty"],
        "eye_level": new_level,
        "leveled_up": leveled_up,
        "new_titles": check_titles(uid),
    }


# ======================== 变现 ========================


def price_item(item: sqlite3.Row) -> tuple[int, str]:
    quality_mult = next(m for n, m, _ in catalog.QUALITY_TIERS if n == item["quality"])
    dynasty_mult = catalog.DYNASTY_MULTIPLIER.get(item["dynasty"], 1.0) if item["dynasty"] else 1.0

    if item["kind"] in ("stone", "gem"):
        if not item["is_opened"]:
            price = item["base_value"] * random.uniform(0.3, 1.3)
            return max(int(price), 1), "未开原石，行情按赌石价估，波动大"
        label = "玉质" if item["kind"] == "stone" else "成色"
        price = item["base_value"] * random.uniform(0.85, 1.15)
        return max(int(price), 1), f"按{label}定价"

    if not item["is_identified"]:
        price = item["base_value"] * random.uniform(0.25, 0.9)
        return max(int(price), 1), "未鉴定，按保守估值收购"
    if item["identify_correct"]:
        price = item["base_value"] * random.uniform(0.9, 1.25)
        return max(int(price), 1), "鉴定无误，按行情足额定价"

    wrong_type = catalog.ITEM_TYPES_BY_NAME.get(item["perceived_type"])
    base = wrong_type.base_value if wrong_type else item["base_value"]
    price = base * quality_mult * dynasty_mult * random.uniform(0.85, 1.15)
    return max(int(price), 1), f"按你认定的「{item['perceived_type']}」定价，可能与真实价值不符"


def sell_item(uid: str, item_id: int) -> dict:
    item = storage.get_item(item_id)
    if not item or item["uid"] != uid:
        raise GameError("找不到这件东西，检查一下编号。")
    if item["status"] != "背包":
        raise GameError("这件东西不在背包里，卖不了。")
    if item["kind"] == "stone" and not item["is_opened"]:
        pass  # 未开原石允许直接送拍，赌一把
    price, note = price_item(item)
    storage.update_item(item_id, status="已卖出", sold_price=price)
    storage.add_money(uid, price)
    return {"price": price, "note": note, "item": item, "new_titles": check_titles(uid)}


# ======================== 图鉴 ========================


def codex_progress(uid: str) -> dict[str, tuple[int, int]]:
    discovered_names = storage.codex_discovered(uid)
    progress = {}
    for cat, types in catalog.ITEM_TYPES_BY_CATEGORY.items():
        total = len(types)
        discovered = sum(1 for t in types if t.name in discovered_names)
        progress[cat] = (discovered, total)
    return progress


def codex_detail(uid: str, category: str) -> list[tuple[str, bool]]:
    discovered_names = storage.codex_discovered(uid)
    types = catalog.ITEM_TYPES_BY_CATEGORY.get(category, [])
    return [(t.name, t.name in discovered_names) for t in types]


# ======================== 称号 ========================


def build_title_context(uid: str) -> dict:
    player = storage.get_or_create_player(uid)
    return {
        "player": player,
        "codex_names": storage.codex_discovered(uid),
        "category_progress": codex_progress(uid),
        "has_传世": storage.has_quality(uid, "传世"),
        "has_fine_gem": any(
            storage.has_quality(uid, q, category=catalog.GEM_CATEGORY) for q in ("精品", "极品", "传世")
        ),
        "max_eye_level": MAX_EYE_LEVEL,
    }


def check_titles(uid: str) -> list[titles.TitleDef]:
    ctx = build_title_context(uid)
    unlocked = []
    for title in titles.TITLE_DEFS:
        if storage.has_title(uid, title.key):
            continue
        if title.check(ctx):
            storage.unlock_title(uid, title.key)
            unlocked.append(title)
    return unlocked
