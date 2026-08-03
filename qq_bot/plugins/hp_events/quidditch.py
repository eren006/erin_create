"""魁地奇：位置占位/PK、训练、比赛模拟、MVP统计。

位置实力不设独立的"养成数值"——四维属性(速度/碰撞/体力/准头)在成为选手时
一次性随机分配10点，之后只能靠/魁地奇训练慢慢加，装备(扫帚)加成字段已经留好，
等对角巷商店系统做出来之后往broom_*_bonus里写值就行，现在都是0。

注意命名：这里的"体力"(stamina字段)是魁地奇四维属性之一，跟hp_core.storage里
全局的体力值资源池(players.stamina)是两回事，两张表互不相关，只是恰好同名。
"""

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_school import shop_catalog
from plugins.hp_school import storage as school_storage

from . import storage

storage.init_db()


class QuidditchError(Exception):
    pass


POSITIONS = ("追球手", "击球手", "守门员", "找球手")
# 每个位置看两项属性，主属性权重0.7、副属性0.3；四项属性在四个位置里各出现两次，不偏科。
POSITION_STATS = {
    "追球手": {"accuracy": 0.7, "speed": 0.3},  # 准头为主（能不能进），速度为辅（能不能到位）
    "击球手": {"collision": 0.7, "stamina": 0.3},  # 碰撞为主（打得狠），体力为辅（打一整场）
    "守门员": {"stamina": 0.7, "collision": 0.3},  # 体力为主（撑住一整场），碰撞为辅（扑得住）
    "找球手": {"speed": 0.7, "accuracy": 0.3},  # 速度为主（追得上），准头为辅（抓得住）
}
STAT_LABELS = {"speed": "速度", "collision": "碰撞", "stamina": "体力", "accuracy": "准头"}
STAT_KEYS = ("speed", "collision", "stamina", "accuracy")

FLYING_SUBJECT_KEY = "flying"
FLYING_THRESHOLD = 40
STAT_TOTAL_POINTS = 10
MIN_GRADE = 2

TRAINING_STAMINA_COST = 6
TRAINING_DAILY_LIMIT = 3
TRAINING_GAIN = 2

MATCH_DAILY_LIMIT = 2
CHASER_ROUNDS = 5
CHASER_GOAL_SCORE = 10
SEEKER_CATCH_SCORE = 150
MATCH_WIN_HOUSE_POINTS = 15

NPC_STATS = {"speed": 3, "collision": 2, "stamina": 3, "accuracy": 2}


def _check_eligible(player) -> None:
    if not player or not player["house"]:
        raise QuidditchError("你还没有分院，先发「/入学」完成入学测试。")
    if player["grade"] < MIN_GRADE:
        raise QuidditchError(f"要到{MIN_GRADE}年级才能参加魁地奇，你现在是{player['grade']}年级。")
    flying_exp = core_storage.get_subject_exp(player["uid"], FLYING_SUBJECT_KEY)
    if flying_exp < FLYING_THRESHOLD:
        raise QuidditchError(f"飞行课经验不够（{flying_exp}/{FLYING_THRESHOLD}），先多上几次「/上课 飞行课」。")


def _random_stats() -> dict[str, int]:
    cuts = sorted(random.randint(0, STAT_TOTAL_POINTS) for _ in range(len(STAT_KEYS) - 1))
    values = []
    prev = 0
    for c in cuts:
        values.append(c - prev)
        prev = c
    values.append(STAT_TOTAL_POINTS - prev)
    random.shuffle(values)
    return dict(zip(STAT_KEYS, values))


def _effective_stat(row, key: str) -> int:
    """扫帚耐久归零后加成失效，得用「/施咒 修复如初」修好才能重新生效。"""
    if row["broom_durability"] <= 0:
        return row[key]
    return row[key] + row[f"broom_{key}_bonus"]


def _position_power_row(row, position: str) -> float:
    """用于PK：双方都是真实玩家的DB行，直接按位置权重加权。"""
    return sum(_effective_stat(row, stat) * weight for stat, weight in POSITION_STATS[position].items())


def _position_power_entry(entry: dict, position: str) -> float:
    """用于比赛模拟：entry可能是真人也可能是NPC替补，走_stat_of统一取值。"""
    return sum(_stat_of(entry, stat) * weight for stat, weight in POSITION_STATS[position].items())


def _position_desc(position: str) -> str:
    return "+".join(f"{STAT_LABELS[k]}{int(w * 100)}%" for k, w in POSITION_STATS[position].items())


def _win_chance(my_value: float, their_value: float) -> float:
    total = my_value + their_value
    base = 0.5 if total <= 0 else my_value / total
    luck = random.random()
    return min(1.0, max(0.0, 0.8 * base + 0.2 * luck))


def _get_or_create(uid: str, house: str):
    qp = storage.get_quidditch_player(uid)
    if not qp:
        storage.create_quidditch_player(uid, house, _random_stats())
        qp = storage.get_quidditch_player(uid)
    return qp


# ======================== 占位 / PK ========================


def become_player(uid: str, position_input: str) -> dict:
    player = core_storage.get_player(uid)
    _check_eligible(player)
    if position_input not in POSITIONS:
        raise QuidditchError(f"没有这个位置。可选：{'、'.join(POSITIONS)}")

    holder = storage.get_position_holder(player["house"], position_input)
    if holder:
        raise QuidditchError(
            f"「{position_input}」已经有人了（{holder['uid']}），用「/取代魁地奇 {position_input}」来PK。"
        )

    qp = storage.get_quidditch_player(uid)
    if qp and qp["position"]:
        raise QuidditchError(f"你已经是本院「{qp['position']}」了，不能同时占两个位置。")
    if not qp:
        qp = _get_or_create(uid, player["house"])

    storage.set_position(uid, position_input)
    qp = storage.get_quidditch_player(uid)
    return {
        "position": position_input,
        "stats": {STAT_LABELS[k]: qp[k] for k in STAT_KEYS},
    }


def challenge_position(uid: str, position_input: str) -> dict:
    player = core_storage.get_player(uid)
    _check_eligible(player)
    if position_input not in POSITIONS:
        raise QuidditchError(f"没有这个位置。可选：{'、'.join(POSITIONS)}")

    holder = storage.get_position_holder(player["house"], position_input)
    if not holder:
        raise QuidditchError(f"「{position_input}」现在是空的，直接「/成为魁地奇选手 {position_input}」就行。")
    if holder["uid"] == uid:
        raise QuidditchError("这就是你自己的位置。")

    qp = storage.get_quidditch_player(uid)
    if qp and qp["position"]:
        raise QuidditchError(f"你已经是本院「{qp['position']}」了，不能再挑战别的位置。")
    if not qp:
        qp = _get_or_create(uid, player["house"])

    chance = _win_chance(_position_power_row(qp, position_input), _position_power_row(holder, position_input))
    win = chance > 0.5
    if win:
        storage.set_position(holder["uid"], "")
        storage.set_position(uid, position_input)
    return {
        "win": win,
        "chance": chance,
        "position": position_input,
        "stat_desc": _position_desc(position_input),
        "opponent": holder["uid"],
    }


def equip_broom(uid: str, item_input: str) -> dict:
    qp = storage.get_quidditch_player(uid)
    if not qp:
        raise QuidditchError("你还不是魁地奇选手，先「/成为魁地奇选手 <位置>」。")

    item = shop_catalog.find(item_input.strip())
    if not item or item[2] != "扫帚":
        raise QuidditchError("这不是扫帚。")
    key, name, _, _, _, effect = item

    if school_storage.get_item_quantity(uid, key) <= 0:
        raise QuidditchError(f"你还没有「{name}」，先去「/对角巷购买 {name}」。")

    durability = effect["durability"]
    storage.set_broom_bonus(uid, key, effect, durability)
    return {"name": name, "effect": effect, "durability": durability}


def repair_broom(uid: str) -> dict:
    """修复如初的效果入口。归 hp_school 的施咒指令调用。"""
    qp = storage.get_quidditch_player(uid)
    if not qp or not qp["broom_key"]:
        raise QuidditchError("你没有装备扫帚，没什么可修的。")
    item = shop_catalog.find(qp["broom_key"])
    if not item:
        raise QuidditchError("你装备的扫帚型号有点问题，联系管理员。")
    full = item[5]["durability"]
    if qp["broom_durability"] >= full:
        raise QuidditchError(f"「{item[1]}」还是好好的（耐久{qp['broom_durability']}/{full}），不用修。")
    storage.repair_broom(uid, full)
    return {"name": item[1], "before": qp["broom_durability"], "after": full}


def get_roster(house: str) -> dict[str, object]:
    rows = storage.get_house_roster(house)
    roster: dict[str, object] = {p: None for p in POSITIONS}
    for row in rows:
        roster[row["position"]] = row
    return roster


# ======================== 训练 ========================


def train(uid: str) -> dict:
    qp = storage.get_quidditch_player(uid)
    if not qp:
        raise QuidditchError("你还不是魁地奇选手，先「/成为魁地奇选手 <位置>」。")

    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(uid, day)
    if daily["trainings"] >= TRAINING_DAILY_LIMIT:
        raise QuidditchError(f"今天已经训练{TRAINING_DAILY_LIMIT}次了，明天再来。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < TRAINING_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise QuidditchError(
            f"你刚跨上扫帚就觉得双腿发软，当前体力{player['stamina']}/{core_storage.STAMINA_MAX}；"
            f"完成训练需要{TRAINING_STAMINA_COST}点。先在看台歇一会儿，约{wait_min}分钟后恢复一轮。"
        )

    core_storage.spend_stamina(uid, TRAINING_STAMINA_COST)
    storage.increment_daily(uid, day, "trainings")
    stat_key = random.choice(STAT_KEYS)
    storage.add_stat(uid, stat_key, TRAINING_GAIN)

    return {
        "stat": STAT_LABELS[stat_key],
        "gain": TRAINING_GAIN,
        "today_count": daily["trainings"] + 1,
        "daily_limit": TRAINING_DAILY_LIMIT,
    }


# ======================== 比赛 ========================


def _lineup(house: str, day: int) -> dict[str, dict]:
    """返回该院四个位置这场比赛的实际出场者：真人(次数没用完)或NPC替补。"""
    lineup = {}
    for position in POSITIONS:
        holder = storage.get_position_holder(house, position)
        if holder is None:
            lineup[position] = {"uid": None, "row": None, "is_npc": True}
            continue
        daily = storage.get_daily(holder["uid"], day)
        is_npc = daily["matches"] >= MATCH_DAILY_LIMIT
        lineup[position] = {"uid": holder["uid"], "row": holder, "is_npc": is_npc}
    return lineup


def _stat_of(entry: dict, key: str) -> int:
    if entry["is_npc"] or entry["row"] is None:
        return NPC_STATS[key]
    return _effective_stat(entry["row"], key)


def simulate_match(initiator_uid: str, house_a: str, house_b: str) -> dict:
    if house_a == house_b:
        raise QuidditchError("不能挑战自己的学院。")

    initiator = storage.get_quidditch_player(initiator_uid)
    if not initiator or not initiator["position"]:
        raise QuidditchError("你还不是魁地奇选手（或者没有位置），不能发起比赛。")
    if initiator["house"] not in (house_a, house_b):
        raise QuidditchError("你只能代表自己的学院发起比赛。")

    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(initiator_uid, day)
    if daily["matches"] >= MATCH_DAILY_LIMIT:
        raise QuidditchError(f"你今天已经打过{MATCH_DAILY_LIMIT}场比赛了，明天再来。")

    lineup_a = _lineup(house_a, day)
    lineup_b = _lineup(house_b, day)

    score_a, score_b = 0, 0
    scorers: list[tuple[str, int]] = []

    for _ in range(CHASER_ROUNDS):
        for atk_house, atk_lineup, def_lineup in (
            (house_a, lineup_a, lineup_b),
            (house_b, lineup_b, lineup_a),
        ):
            chaser = atk_lineup["追球手"]
            keeper = def_lineup["守门员"]
            beater = def_lineup["击球手"]
            attack = _position_power_entry(chaser, "追球手")
            defense = _position_power_entry(keeper, "守门员") + _position_power_entry(beater, "击球手") * 0.5
            if _win_chance(attack, defense) > 0.5:
                if atk_house == house_a:
                    score_a += CHASER_GOAL_SCORE
                else:
                    score_b += CHASER_GOAL_SCORE
                if not chaser["is_npc"] and chaser["uid"]:
                    scorers.append((chaser["uid"], CHASER_GOAL_SCORE))

    seeker_a, seeker_b = lineup_a["找球手"], lineup_b["找球手"]
    chance_a = _win_chance(_position_power_entry(seeker_a, "找球手"), _position_power_entry(seeker_b, "找球手"))
    if chance_a > 0.5:
        score_a += SEEKER_CATCH_SCORE
        seeker_winner_house = house_a
        if not seeker_a["is_npc"] and seeker_a["uid"]:
            scorers.append((seeker_a["uid"], SEEKER_CATCH_SCORE))
    else:
        score_b += SEEKER_CATCH_SCORE
        seeker_winner_house = house_b
        if not seeker_b["is_npc"] and seeker_b["uid"]:
            scorers.append((seeker_b["uid"], SEEKER_CATCH_SCORE))

    winner_house = None
    if score_a > score_b:
        winner_house = house_a
    elif score_b > score_a:
        winner_house = house_b
    if winner_house:
        core_storage.add_house_points(winner_house, MATCH_WIN_HOUSE_POINTS)

    for uid, amount in scorers:
        storage.add_season_score(uid, amount)

    worn_out = []
    for lineup in (lineup_a, lineup_b):
        for entry in lineup.values():
            if entry["is_npc"] or not entry["uid"]:
                continue
            storage.increment_daily(entry["uid"], day, "matches")
            row = entry["row"]
            if row["broom_key"] and row["broom_durability"] > 0:
                storage.wear_broom(entry["uid"])  # 打一场磨损1点耐久
                if row["broom_durability"] - 1 <= 0:
                    worn_out.append(entry["uid"])

    return {
        "house_a": house_a,
        "house_b": house_b,
        "score_a": score_a,
        "score_b": score_b,
        "winner": winner_house,
        "seeker_winner_house": seeker_winner_house,
        "scorers": scorers,
        "worn_out": worn_out,
    }


# ======================== MVP ========================


def get_mvp(house: str):
    rows = storage.mvp_by_house(house, limit=1)
    if rows and rows[0]["season_score"] > 0:
        return rows[0]
    return None


def reset_season_scores() -> None:
    """学年结算颁完MVP之后清零，下学年重新计分。"""
    storage.reset_all_season_scores()
    return None
