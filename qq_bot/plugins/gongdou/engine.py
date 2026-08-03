"""核心玩法逻辑：体力恢复、位分晋升、请安/侍寝/宫务、结盟、告状/使绊子、冷宫。"""

import random
import sqlite3
from datetime import date

from . import storage, titles

storage.init_db()

# ======================== 位分 ========================

RANKS = [
    ("答应", 0),
    ("常在", 80),
    ("贵人", 220),
    ("嫔", 500),
    ("妃", 1000),
    ("贵妃", 2000),
    ("皇贵妃", 4000),
    ("皇后", 8000),
]
MAX_RANK_INDEX = len(RANKS) - 1

# ======================== 体力 ========================

STAMINA_MAX = 30
STAMINA_REGEN_SECONDS = 8 * 60  # 每8分钟恢复1点体力

GREET_COST = 5
BED_COST = 8
CHORE_COST = 5
REPORT_COST = 6
SCHEME_COST = 12
ESCAPE_COST = 10

REPORT_MONEY_COST = 50
SCHEME_MONEY_COST = 150

REPORT_DAILY_LIMIT = 3
SCHEME_DAILY_LIMIT = 2

COLD_PALACE_SECONDS = 90 * 60  # 冷宫基础时长90分钟
ESCAPE_FAIL_PENALTY_SECONDS = 10 * 60

# ======================== 心机等级 ========================

SCHEME_LEVEL_THRESHOLDS = [0, 50, 120, 220, 350, 500, 700, 950, 1250, 1600]
MAX_SCHEME_LEVEL = len(SCHEME_LEVEL_THRESHOLDS)


class GameError(Exception):
    pass


def today_str() -> str:
    return date.today().isoformat()


# ======================== 位分换算 ========================


def rank_index_from_favor(favor: int) -> int:
    idx = 0
    for i, (_, threshold) in enumerate(RANKS):
        if favor >= threshold:
            idx = i
    return idx


def rank_name(index: int) -> str:
    return RANKS[index][0]


def rank_progress(favor: int) -> tuple[int, str, int, int | None]:
    """返回 (位分序号, 位分名, 当前位分门槛, 下一位分门槛或None)。"""
    idx = rank_index_from_favor(favor)
    next_threshold = RANKS[idx + 1][1] if idx < MAX_RANK_INDEX else None
    return idx, rank_name(idx), RANKS[idx][1], next_threshold


# ======================== 心机等级换算 ========================


def scheme_level_from_exp(total_exp: int) -> int:
    level = 1
    for i, threshold in enumerate(SCHEME_LEVEL_THRESHOLDS):
        if total_exp >= threshold:
            level = i + 1
    return min(level, MAX_SCHEME_LEVEL)


def grant_scheme_exp(uid: str, amount: int) -> tuple[int, bool]:
    storage.add_scheme_exp(uid, amount)
    player = storage.get_or_create_player(uid)
    old_level = player["scheme_level"]
    new_level = scheme_level_from_exp(player["scheme_exp"])
    leveled_up = new_level != old_level
    if leveled_up:
        storage.set_scheme_level(uid, new_level)
    return new_level, leveled_up


# ======================== 体力与每日重置 ========================


def sync_player(uid: str) -> sqlite3.Row:
    player = storage.get_or_create_player(uid)

    today = today_str()
    if player["counter_date"] != today:
        storage.update_player(
            uid, counter_date=today, report_count_today=0, scheme_count_today=0
        )
        player = storage.get_or_create_player(uid)

    if player["stamina"] < STAMINA_MAX:
        elapsed = storage.now() - player["stamina_updated_at"]
        regen = elapsed // STAMINA_REGEN_SECONDS
        if regen > 0:
            new_stamina = min(STAMINA_MAX, player["stamina"] + regen)
            consumed = regen * STAMINA_REGEN_SECONDS
            storage.update_player(
                uid, stamina=new_stamina, stamina_updated_at=player["stamina_updated_at"] + consumed
            )
            player = storage.get_or_create_player(uid)
    return player


def seconds_to_next_stamina(player: sqlite3.Row) -> int:
    if player["stamina"] >= STAMINA_MAX:
        return 0
    elapsed_into_tick = (storage.now() - player["stamina_updated_at"]) % STAMINA_REGEN_SECONDS
    return STAMINA_REGEN_SECONDS - elapsed_into_tick


def _require_stamina(player: sqlite3.Row, cost: int, action: str) -> None:
    if player["stamina"] < cost:
        raise GameError(
            f"体力不够。当前 {player['stamina']}/{STAMINA_MAX}，{action}需要 {cost}。"
            f"还差 {seconds_to_next_stamina(player) // 60 + 1} 分钟恢复下一点。"
        )


def _require_not_cold_palace(player: sqlite3.Row) -> None:
    remaining = player["cold_palace_until"] - storage.now()
    if remaining > 0:
        raise GameError(f"你正被打入冷宫，无颜面圣。还有 {remaining // 60 + 1} 分钟，或用 /冷宫脱身 碰碰运气。")


# ======================== 请安 ========================


def greet(uid: str) -> dict:
    player = sync_player(uid)
    _require_not_cold_palace(player)
    if player["last_greet_date"] == today_str():
        raise GameError("今日已经请过安了，明日再来。")
    _require_stamina(player, GREET_COST, "请安")

    favored = random.random() < 0.1
    favor_gain = random.randint(8, 15)
    money_gain = random.randint(5, 15)
    if favored:
        favor_gain *= 2
        money_gain *= 2

    old_idx = rank_index_from_favor(player["favor"])
    storage.update_player(
        uid,
        stamina=player["stamina"] - GREET_COST,
        last_greet_date=today_str(),
    )
    storage.add_favor(uid, favor_gain)
    storage.add_money(uid, money_gain)
    new_player = storage.get_or_create_player(uid)
    new_idx = rank_index_from_favor(new_player["favor"])

    return {
        "favored": favored,
        "favor_gain": favor_gain,
        "money_gain": money_gain,
        "rank_up": new_idx > old_idx,
        "old_rank": rank_name(old_idx),
        "new_rank": rank_name(new_idx),
        "new_titles": check_titles(uid),
    }


# ======================== 侍寝 ========================


def bed_service(uid: str) -> dict:
    player = sync_player(uid)
    _require_not_cold_palace(player)
    if player["last_bed_date"] == today_str():
        raise GameError("今日已经侍过寝了，明日再候召。")
    _require_stamina(player, BED_COST, "侍寝")

    chance = min(0.45 + player["scheme_level"] * 0.03, 0.75)
    success = random.random() < chance

    old_idx = rank_index_from_favor(player["favor"])
    storage.update_player(uid, stamina=player["stamina"] - BED_COST, last_bed_date=today_str())

    if success:
        favor_gain = random.randint(40, 80)
        money_gain = random.randint(20, 40)
        storage.add_favor(uid, favor_gain)
        storage.add_money(uid, money_gain)
        grant_scheme_exp(uid, 2)
        storage.increment_counter(uid, "bed_success_count")
    else:
        favor_gain = random.randint(2, 5)
        money_gain = 0
        storage.add_favor(uid, favor_gain)

    new_player = storage.get_or_create_player(uid)
    new_idx = rank_index_from_favor(new_player["favor"])

    return {
        "success": success,
        "chance": round(chance * 100),
        "favor_gain": favor_gain,
        "money_gain": money_gain,
        "rank_up": new_idx > old_idx,
        "old_rank": rank_name(old_idx),
        "new_rank": rank_name(new_idx),
        "new_titles": check_titles(uid),
    }


# ======================== 宫务 ========================


def chores(uid: str) -> dict:
    player = sync_player(uid)
    _require_not_cold_palace(player)
    _require_stamina(player, CHORE_COST, "宫务")

    money_gain = random.randint(15, 30)
    favor_gain = random.randint(2, 5)

    old_idx = rank_index_from_favor(player["favor"])
    storage.update_player(uid, stamina=player["stamina"] - CHORE_COST)
    storage.add_money(uid, money_gain)
    storage.add_favor(uid, favor_gain)
    grant_scheme_exp(uid, 1)

    new_player = storage.get_or_create_player(uid)
    new_idx = rank_index_from_favor(new_player["favor"])

    return {
        "money_gain": money_gain,
        "favor_gain": favor_gain,
        "rank_up": new_idx > old_idx,
        "old_rank": rank_name(old_idx),
        "new_rank": rank_name(new_idx),
        "new_titles": check_titles(uid),
    }


# ======================== 结盟 ========================


def propose_alliance(uid: str, target: str) -> dict:
    if uid == target:
        raise GameError("不能拉拢自己。")
    existing = storage.get_alliance(uid, target)
    if existing and existing["status"] == "active":
        raise GameError("已经是盟友了。")
    if existing and existing["status"] == "pending":
        if existing["requested_by"] == uid:
            raise GameError("邀约已经发出去了，等对方回应。")
        storage.activate_alliance(uid, target)
        return {"activated": True}
    storage.create_pending_alliance(uid, target)
    return {"activated": False}


def accept_alliance(uid: str, target: str) -> None:
    existing = storage.get_alliance(uid, target)
    if not existing or existing["status"] != "pending":
        raise GameError("没有来自这个人的结盟邀约。")
    if existing["requested_by"] == uid:
        raise GameError("这是你自己发出的邀约，等对方接受。")
    storage.activate_alliance(uid, target)


def break_alliance(uid: str, target: str) -> None:
    existing = storage.get_alliance(uid, target)
    if not existing:
        raise GameError("你们之间没有盟约。")
    storage.delete_alliance(uid, target)


# ======================== 告状 / 使绊子 ========================


def _rank_of(uid: str) -> int:
    p = storage.get_or_create_player(uid)
    return rank_index_from_favor(p["favor"])


def report(uid: str, target: str) -> dict:
    if uid == target:
        raise GameError("不能告自己的状。")
    attacker = sync_player(uid)
    _require_not_cold_palace(attacker)
    defender = storage.get_or_create_player(target)

    if storage.is_allied(uid, target):
        raise GameError("对方是你的盟友，先 /绝交 才能对付。")
    if attacker["report_count_today"] >= REPORT_DAILY_LIMIT:
        raise GameError(f"今日告状次数已用完（{REPORT_DAILY_LIMIT}次），明日再来。")
    _require_stamina(attacker, REPORT_COST, "告状")
    if attacker["money"] < REPORT_MONEY_COST:
        raise GameError(f"银两不够，告状打点需要 {REPORT_MONEY_COST} 两。")

    chance = min(max(0.55 + (attacker["scheme_level"] - defender["scheme_level"]) * 0.03, 0.15), 0.85)
    success = random.random() < chance

    storage.update_player(
        uid,
        stamina=attacker["stamina"] - REPORT_COST,
        report_count_today=attacker["report_count_today"] + 1,
    )
    storage.add_money(uid, -REPORT_MONEY_COST)

    old_target_idx = _rank_of(target)
    if success:
        favor_loss = random.randint(30, 60)
        money_loss = random.randint(10, 30)
        storage.add_favor(target, -favor_loss)
        storage.add_money(target, -money_loss)
        grant_scheme_exp(uid, 3)
        storage.increment_counter(uid, "report_success_count")
    else:
        favor_loss = random.randint(10, 20)
        money_loss = 0
        storage.add_favor(uid, -favor_loss)
        storage.increment_counter(uid, "report_fail_count")
    new_target_idx = _rank_of(target)

    return {
        "success": success,
        "chance": round(chance * 100),
        "favor_loss": favor_loss,
        "money_loss": money_loss,
        "target_rank_down": new_target_idx < old_target_idx,
        "target_old_rank": rank_name(old_target_idx),
        "target_new_rank": rank_name(new_target_idx),
        "new_titles": check_titles(uid),
    }


def scheme(uid: str, target: str) -> dict:
    if uid == target:
        raise GameError("不能对自己使绊子。")
    attacker = sync_player(uid)
    _require_not_cold_palace(attacker)
    defender = storage.get_or_create_player(target)

    if storage.is_allied(uid, target):
        raise GameError("对方是你的盟友，先 /绝交 才能对付。")
    if attacker["scheme_count_today"] >= SCHEME_DAILY_LIMIT:
        raise GameError(f"今日使绊子次数已用完（{SCHEME_DAILY_LIMIT}次），明日再来。")
    _require_stamina(attacker, SCHEME_COST, "使绊子")
    if attacker["money"] < SCHEME_MONEY_COST:
        raise GameError(f"银两不够，使绊子需要打点 {SCHEME_MONEY_COST} 两。")

    chance = min(max(0.40 + (attacker["scheme_level"] - defender["scheme_level"]) * 0.03, 0.10), 0.75)
    success = random.random() < chance

    storage.update_player(
        uid,
        stamina=attacker["stamina"] - SCHEME_COST,
        scheme_count_today=attacker["scheme_count_today"] + 1,
    )
    storage.add_money(uid, -SCHEME_MONEY_COST)

    old_target_idx = _rank_of(target)
    result = {"self_cold_palace": False, "target_cold_palace": False}

    if success:
        favor_loss = random.randint(100, 200)
        storage.add_favor(target, -favor_loss)
        grant_scheme_exp(uid, 8)
        storage.increment_counter(uid, "scheme_success_count")
        storage.increment_counter(target, "been_sabotaged_count")
        if random.random() < 0.3:
            storage.update_player(target, cold_palace_until=storage.now() + COLD_PALACE_SECONDS)
            storage.increment_counter(target, "cold_palace_count")
            result["target_cold_palace"] = True
        result["favor_loss"] = favor_loss
        result["money_loss"] = 0
    else:
        favor_loss = random.randint(50, 100)
        storage.add_favor(uid, -favor_loss)
        storage.increment_counter(uid, "scheme_fail_count")
        if random.random() < 0.3:
            storage.update_player(uid, cold_palace_until=storage.now() + COLD_PALACE_SECONDS)
            storage.increment_counter(uid, "cold_palace_count")
            result["self_cold_palace"] = True
        result["favor_loss"] = favor_loss
        result["money_loss"] = 0

    new_target_idx = _rank_of(target)
    result.update(
        {
            "success": success,
            "chance": round(chance * 100),
            "target_rank_down": new_target_idx < old_target_idx,
            "target_old_rank": rank_name(old_target_idx),
            "target_new_rank": rank_name(new_target_idx),
            "new_titles": check_titles(uid),
        }
    )
    return result


# ======================== 冷宫脱身 ========================


def escape_cold_palace(uid: str) -> dict:
    player = sync_player(uid)
    remaining = player["cold_palace_until"] - storage.now()
    if remaining <= 0:
        raise GameError("你不在冷宫里，用不上这招。")
    if player["stamina"] < ESCAPE_COST:
        raise GameError(
            f"体力不够。当前 {player['stamina']}/{STAMINA_MAX}，冷宫脱身需要 {ESCAPE_COST}。"
        )

    chance = min(0.35 + player["scheme_level"] * 0.03, 0.7)
    success = random.random() < chance
    storage.update_player(uid, stamina=player["stamina"] - ESCAPE_COST)

    if success:
        storage.update_player(uid, cold_palace_until=0)
        storage.increment_counter(uid, "escape_success_count")
    else:
        new_player = storage.get_or_create_player(uid)
        storage.update_player(
            uid, cold_palace_until=new_player["cold_palace_until"] + ESCAPE_FAIL_PENALTY_SECONDS
        )

    return {"success": success, "chance": round(chance * 100), "new_titles": check_titles(uid)}


# ======================== 称号 ========================


def build_title_context(uid: str) -> dict:
    player = storage.get_or_create_player(uid)
    return {
        "player": player,
        "rank_index": rank_index_from_favor(player["favor"]),
        "max_scheme_level": MAX_SCHEME_LEVEL,
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
