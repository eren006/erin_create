"""魁地奇：位置占位/PK、训练、比赛模拟、MVP统计。

位置实力不设独立的"养成数值"——四维属性(速度/碰撞/体力/准头)在成为选手时
一次性随机分配10点，之后只能靠训练（train()）慢慢加，装备(扫帚)加成字段已经留好，
等对角巷商店系统做出来之后往broom_*_bonus里写值就行，现在都是0。

注意命名：这里的"体力"(stamina字段)是魁地奇四维属性之一，跟hp_core.storage里
全局的体力值资源池(players.stamina)是两回事，两张表互不相关，只是恰好同名。
"""

import math
import random
from itertools import combinations

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
MATCH_HOUSE_DAILY_LIMIT = 8  # 全院当天最多参与这么多场，人多的学院不能靠人海堆场次刷院分
CHASER_ROUNDS = 5
CHASER_GOAL_SCORE = 10
KEEPER_STOP_SCORE = 4  # 守门员/击球手挡下一次进攻的赛季得分——此前只有进球和抓飞贼能拿分，防守位置永远陪衬
BEATER_STOP_SCORE = 2
# 原著里150分相对10分/球是合理的，因为正赛能打几十上百个进球再抓飞贼；
# 这里一场比赛封顶就5轮追球手对攻（单队最多50分），150分一抓等于锁定胜负，追球手/守门员/击球手全打白工。
# 降到50——正好是单队五轮全中的封顶分，追球手拼命灌球仍有翻盘机会，抓飞贼不再是绝对话语权。
SEEKER_CATCH_SCORE = 50
MATCH_WIN_HOUSE_POINTS = 15
MATCH_WIN_CONTRIBUTION_PER_PLAYER = 5  # 赢球时上场的每个真人队员各记一笔个人贡献，不是只记发起人

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


def position_desc(position: str) -> str:
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
            f"「{position_input}」已经有人了（{core_storage.get_full_name(holder['uid'])}），"
            "去挑战那个位置来PK。"
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
        raise QuidditchError(f"「{position_input}」现在是空的，直接占位就行，不用挑战。")
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
        "stat_desc": position_desc(position_input),
        "opponent": holder["uid"],
    }


def switch_position(uid: str, new_position: str) -> dict:
    """已经有位置的选手换到本院另一个位置——空位直接换；对方也是本院队员（已占位）的话，
    直接跟对方对调位置，不判定属性胜负，不限次数。真要抢的是"自己还没位置、想凭实力抢一个"，
    那走挑战PK（见challenge_position），不走这个函数。"""
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise QuidditchError("你还没有分院，先发「/入学」完成入学测试。")
    if new_position not in POSITIONS:
        raise QuidditchError(f"没有这个位置。可选：{'、'.join(POSITIONS)}")

    qp = storage.get_quidditch_player(uid)
    if not qp or not qp["position"]:
        raise QuidditchError("你还不是魁地奇选手，没有位置可换。")
    if qp["position"] == new_position:
        raise QuidditchError("你已经在这个位置了。")

    old_position = qp["position"]
    holder = storage.get_position_holder(player["house"], new_position)
    if holder:
        storage.set_position(holder["uid"], old_position)
        storage.set_position(uid, new_position)
        return {"old_position": old_position, "position": new_position, "swapped_with": holder["uid"]}

    storage.set_position(uid, new_position)
    return {"old_position": old_position, "position": new_position, "swapped_with": None}


def equip_broom(uid: str, item_input: str) -> dict:
    qp = storage.get_quidditch_player(uid)
    if not qp:
        raise QuidditchError("你还不是魁地奇选手，先去网页魁地奇页面占一个位置。")

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
        raise QuidditchError("你还不是魁地奇选手，先去网页魁地奇页面占一个位置。")

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


def _lineup(house: str) -> dict[str, dict]:
    """返回该院四个位置这场比赛的实际出场者：占着位置就是真人上场，位置空缺才用NPC替补。
    出场次数不再限制能不能被摆上阵——谁发起比赛才受MATCH_DAILY_LIMIT管，见simulate_match。"""
    lineup = {}
    for position in POSITIONS:
        holder = storage.get_position_holder(house, position)
        if holder is None:
            lineup[position] = {"uid": None, "row": None, "is_npc": True}
            continue
        lineup[position] = {"uid": holder["uid"], "row": holder, "is_npc": False}
    return lineup


def _stat_of(entry: dict, key: str) -> int:
    if entry["is_npc"] or entry["row"] is None:
        return NPC_STATS[key]
    return _effective_stat(entry["row"], key)


def _entry_label(entry: dict) -> str:
    if entry["is_npc"] or not entry["uid"]:
        return "NPC替补"
    return core_storage.get_full_name(entry["uid"])


def _has_any_player(house: str) -> bool:
    return any(storage.get_position_holder(house, position) for position in POSITIONS)


def _simulate_score(house_a: str, lineup_a: dict, house_b: str, lineup_b: dict) -> dict:
    """跑一次比赛的得分结算：5轮追球手对攻+1次找球手对决。纯计算，不touch数据库、
    没有任何副作用——simulate_match（真实对局）和matchup_analysis（后台胜率分析）
    共用这份逻辑，保证分析出来的胜率跟真实对局用的是同一套规则，不会两边分头维护、
    以后改了引擎却忘了同步。"""
    score_a, score_b = 0, 0
    scorers: list[tuple[str, int]] = []
    log: list[str] = []

    for round_no in range(1, CHASER_ROUNDS + 1):
        for atk_house, atk_lineup, def_lineup in (
            (house_a, lineup_a, lineup_b),
            (house_b, lineup_b, lineup_a),
        ):
            chaser = atk_lineup["追球手"]
            keeper = def_lineup["守门员"]
            beater = def_lineup["击球手"]
            attack = _position_power_entry(chaser, "追球手")
            defense = _position_power_entry(keeper, "守门员") + _position_power_entry(beater, "击球手") * 0.5
            chaser_label = _entry_label(chaser)
            if _win_chance(attack, defense) > 0.5:
                if atk_house == house_a:
                    score_a += CHASER_GOAL_SCORE
                else:
                    score_b += CHASER_GOAL_SCORE
                if not chaser["is_npc"] and chaser["uid"]:
                    scorers.append((chaser["uid"], CHASER_GOAL_SCORE))
                log.append(
                    f"第{round_no}轮：{atk_house}追球手{chaser_label}进球！（{score_a}:{score_b}）"
                )
            else:
                keeper_label = _entry_label(keeper)
                if not keeper["is_npc"] and keeper["uid"]:
                    scorers.append((keeper["uid"], KEEPER_STOP_SCORE))
                if not beater["is_npc"] and beater["uid"]:
                    scorers.append((beater["uid"], BEATER_STOP_SCORE))
                log.append(
                    f"第{round_no}轮：{atk_house}追球手{chaser_label}的进攻被"
                    f"守门员{keeper_label}挡了下来。（{score_a}:{score_b}）"
                )

    seeker_a, seeker_b = lineup_a["找球手"], lineup_b["找球手"]
    chance_a = _win_chance(_position_power_entry(seeker_a, "找球手"), _position_power_entry(seeker_b, "找球手"))
    if chance_a > 0.5:
        score_a += SEEKER_CATCH_SCORE
        seeker_winner_house = house_a
        winner_label = _entry_label(seeker_a)
        if not seeker_a["is_npc"] and seeker_a["uid"]:
            scorers.append((seeker_a["uid"], SEEKER_CATCH_SCORE))
    else:
        score_b += SEEKER_CATCH_SCORE
        seeker_winner_house = house_b
        winner_label = _entry_label(seeker_b)
        if not seeker_b["is_npc"] and seeker_b["uid"]:
            scorers.append((seeker_b["uid"], SEEKER_CATCH_SCORE))
    log.append(
        f"找球手对决：{seeker_winner_house}的{winner_label}率先抓住了金色飞贼！"
        f"+{SEEKER_CATCH_SCORE}分（{score_a}:{score_b}）"
    )

    return {
        "score_a": score_a,
        "score_b": score_b,
        "scorers": scorers,
        "seeker_winner_house": seeker_winner_house,
        "log": log,
    }


def simulate_match(initiator_uid: str, house_a: str) -> dict:
    initiator = storage.get_quidditch_player(initiator_uid)
    if not initiator or not initiator["position"]:
        raise QuidditchError("你还不是魁地奇选手（或者没有位置），不能发起比赛。")
    if initiator["house"] != house_a:
        raise QuidditchError("你只能代表自己的学院发起比赛。")

    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(initiator_uid, day)
    if daily["initiated"] >= MATCH_DAILY_LIMIT:
        raise QuidditchError(f"你今天已经发起过{MATCH_DAILY_LIMIT}场比赛了，明天再来。")
    if storage.get_house_daily_matches(house_a, day) >= MATCH_HOUSE_DAILY_LIMIT:
        raise QuidditchError(f"{house_a}今天已经打了{MATCH_HOUSE_DAILY_LIMIT}场比赛，明天再来。")

    candidates = [
        h for h in core_storage.HOUSES
        if h != house_a and _has_any_player(h)
        and storage.get_house_daily_matches(h, day) < MATCH_HOUSE_DAILY_LIMIT
    ]
    if not candidates:
        raise QuidditchError("其他学院今天都凑不齐对手了（没人加入或者场次用完），明天再来。")
    house_b = random.choice(candidates)

    lineup_a = _lineup(house_a)
    lineup_b = _lineup(house_b)

    result = _simulate_score(house_a, lineup_a, house_b, lineup_b)
    score_a, score_b = result["score_a"], result["score_b"]
    scorers, log = result["scorers"], result["log"]
    seeker_winner_house = result["seeker_winner_house"]

    winner_house = None
    if score_a > score_b:
        winner_house = house_a
    elif score_b > score_a:
        winner_house = house_b
    if winner_house:
        core_storage.add_house_points(winner_house, MATCH_WIN_HOUSE_POINTS)
        winning_lineup = lineup_a if winner_house == house_a else lineup_b
        for entry in winning_lineup.values():
            if not entry["is_npc"] and entry["uid"]:
                core_storage.add_house_contribution(
                    entry["uid"], winner_house, MATCH_WIN_CONTRIBUTION_PER_PLAYER
                )

    for uid, amount in scorers:
        storage.add_season_score(uid, amount)

    worn_out = []
    for lineup in (lineup_a, lineup_b):
        for entry in lineup.values():
            if entry["is_npc"] or not entry["uid"]:
                continue
            storage.increment_daily(entry["uid"], day, "matches")  # 仅统计出场场次，不再限制上场资格
            row = entry["row"]
            if row["broom_key"] and row["broom_durability"] > 0:
                storage.wear_broom(entry["uid"])  # 打一场磨损1点耐久
                if row["broom_durability"] - 1 <= 0:
                    worn_out.append(entry["uid"])

    storage.increment_daily(initiator_uid, day, "initiated")
    storage.increment_house_daily_matches(house_a, day)
    storage.increment_house_daily_matches(house_b, day)

    return {
        "house_a": house_a,
        "house_b": house_b,
        "score_a": score_a,
        "score_b": score_b,
        "winner": winner_house,
        "seeker_winner_house": seeker_winner_house,
        "scorers": scorers,
        "worn_out": worn_out,
        "log": log,
    }


# ======================== MVP ========================


def get_mvp(house: str):
    rows = storage.mvp_by_house(house, limit=1)
    if rows and rows[0]["season_score"] > 0:
        return rows[0]
    return None


def get_leaderboard(limit: int = 10) -> list[dict]:
    return storage.quidditch_leaderboard(limit)


def reset_season_scores() -> None:
    """学年结算颁完MVP之后清零，下学年重新计分。"""
    storage.reset_all_season_scores()
    return None


# ======================== 后台：对战胜率分析 ========================


def _wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """二项比例的95%置信区间（默认z=1.96），威尔逊区间在小样本或胜率贴近0/1时
    比正态近似更稳，不会算出负数或超过1的区间。"""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (max(0.0, (center - margin) / denom), min(1.0, (center + margin) / denom))


def _matchup_stats(house_a: str, lineup_a: dict, house_b: str, lineup_b: dict, trials: int) -> dict:
    """拿两边当前阵容跑trials次纯计算模拟（不落库、没有任何副作用），
    统计出A方胜率和95%置信区间，外加双方各位置的当前战力值供对比。"""
    wins_a = wins_b = draws = 0
    for _ in range(trials):
        result = _simulate_score(house_a, lineup_a, house_b, lineup_b)
        if result["score_a"] > result["score_b"]:
            wins_a += 1
        elif result["score_b"] > result["score_a"]:
            wins_b += 1
        else:
            draws += 1

    ci_low, ci_high = _wilson_interval(wins_a, trials)
    return {
        "house_a": house_a,
        "house_b": house_b,
        "trials": trials,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "draws": draws,
        "win_rate_a": wins_a / trials,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "power_a": {pos: round(_position_power_entry(lineup_a[pos], pos), 1) for pos in POSITIONS},
        "power_b": {pos: round(_position_power_entry(lineup_b[pos], pos), 1) for pos in POSITIONS},
    }


def matchup_analysis(house_a: str, house_b: str, trials: int = 1000) -> dict:
    """单独两个学院之间的对战胜率分析，用双方当前实际阵容（含扫帚加成）。"""
    return _matchup_stats(house_a, _lineup(house_a), house_b, _lineup(house_b), trials)


def all_matchups(trials: int = 1000) -> list[dict]:
    """全部两两对阵组合（4个学院=6组），供后台一次性看完整对战分析表。"""
    lineups = {house: _lineup(house) for house in core_storage.HOUSES}
    return [
        _matchup_stats(a, lineups[a], b, lineups[b], trials)
        for a, b in combinations(core_storage.HOUSES, 2)
    ]
