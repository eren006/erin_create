"""决斗系统：邀请/接受/撤回，回合制对局，咒语冷却，5回合定胜负。

流程：A发起 → 机器人@B → B接受(或拒绝，A也可以撤回) → 进入对局
对局是持久化的（存在duel_sessions表里），中途被打断可以用「/返回决斗」随时回来。
出手顺序固定 A→B→A→B…，一个回合双方各出一次，共5回合。
每次轮到你可以：出咒语 / 逃跑 / 什么都不做（咒语全在冷却时的保底选项）。

克制是"你这一发 vs 对手上一发"：攻击→控制→强击→防御→攻击。顺序出招意味着
后手能看到先手出了什么，所以读对手、算冷却都是有意义的。
"""

from plugins.hp_core import spells as spell_catalog
from plugins.hp_core import storage as core_storage

from . import storage

storage.init_db()


class DuelError(Exception):
    pass


def _require_duelist(uid: str, who: str = "你"):
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise DuelError(f"{who}还没有分院，先发「/入学」完成入学测试。")
    if player["grade"] < spell_catalog.DUEL_MIN_GRADE:
        raise DuelError(
            f"决斗俱乐部要{spell_catalog.DUEL_MIN_GRADE}年级才能参加，"
            f"{'你' if who == '你' else '对方'}现在是{player['grade']}年级。"
        )
    return player


def _usable_spells(uid: str) -> list[tuple]:
    return spell_catalog.combat_spells_of(core_storage.list_learned_spells(uid))


# ======================== 邀请 ========================


def challenge(uid: str, target_uid: str) -> dict:
    player = _require_duelist(uid)
    if target_uid == uid:
        raise DuelError("不能跟自己决斗。")
    _require_duelist(target_uid, "对方")

    if not _usable_spells(uid):
        raise DuelError("你还没学会任何能用于决斗的咒语，先去上课（「/我的魔咒」看进度）。")

    if storage.get_active_session(uid):
        raise DuelError("你正在决斗中，打完再说（「/返回决斗」看战况）。")
    if storage.get_active_session(target_uid):
        raise DuelError("对方正在跟别人决斗，等TA打完。")
    if storage.get_challenge_by_challenger(uid):
        raise DuelError("你已经发起过一次决斗邀请了，等对方回应，或者用「/撤回决斗」取消。")

    day = core_storage.get_current_day() or 1
    my_daily = storage.get_duel_daily(uid, day)
    if my_daily["initiated"] >= spell_catalog.DUEL_DAILY_INITIATE_LIMIT:
        raise DuelError(f"你今天已经发起{spell_catalog.DUEL_DAILY_INITIATE_LIMIT}次决斗了，明天再来。")
    their_daily = storage.get_duel_daily(target_uid, day)
    if their_daily["received"] >= spell_catalog.DUEL_DAILY_RECEIVE_LIMIT:
        raise DuelError(f"对方今天已经被挑战{spell_catalog.DUEL_DAILY_RECEIVE_LIMIT}次了，放过TA吧。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < spell_catalog.DUEL_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise DuelError(
            f"你现在连魔杖都握不太稳，体力只有{player['stamina']}/{core_storage.STAMINA_MAX}；"
            f"发起一场决斗需要{spell_catalog.DUEL_STAMINA_COST}点。先喘口气，约{wait_min}分钟后恢复一轮。"
        )

    core_storage.spend_stamina(uid, spell_catalog.DUEL_STAMINA_COST)
    storage.create_challenge(uid, target_uid)
    return {"target": target_uid}


def withdraw(uid: str) -> dict:
    row = storage.get_challenge_by_challenger(uid)
    if not row:
        raise DuelError("你没有待回应的决斗邀请。")
    storage.delete_challenge(uid)
    core_storage.spend_stamina(uid, -spell_catalog.DUEL_STAMINA_COST)  # 撤回退还体力
    return {"target": row["target_uid"]}


def decline(uid: str, challenger_uid: str) -> dict:
    row = storage.get_challenge_to(uid, challenger_uid)
    if not row:
        raise DuelError("没有这个人发给你的决斗邀请。")
    storage.delete_challenge(challenger_uid)
    core_storage.spend_stamina(challenger_uid, -spell_catalog.DUEL_STAMINA_COST)  # 被拒也退还
    return {"challenger": challenger_uid}


def accept(uid: str, challenger_uid: str) -> dict:
    row = storage.get_challenge_to(uid, challenger_uid)
    if not row:
        raise DuelError("没有这个人发给你的决斗邀请。")
    _require_duelist(uid)

    if not _usable_spells(uid):
        raise DuelError("你还没学会任何能用于决斗的咒语，打不了，先去上课。")
    if storage.get_active_session(uid) or storage.get_active_session(challenger_uid):
        storage.delete_challenge(challenger_uid)
        raise DuelError("这场邀请已经失效了（有人已经在别的决斗里）。")

    day = core_storage.get_current_day() or 1
    storage.delete_challenge(challenger_uid)
    storage.increment_duel_daily(challenger_uid, day, "initiated")
    storage.increment_duel_daily(uid, day, "received")

    session_id = storage.create_session(challenger_uid, uid, spell_catalog.DUEL_HP)
    return {"session_id": session_id, "challenger": challenger_uid, "first": challenger_uid}


# ======================== 对局 ========================


def _side_of(session, uid: str) -> str:
    return "a" if session["uid_a"] == uid else "b"


def _opponent_of(session, uid: str) -> str:
    return session["uid_b"] if session["uid_a"] == uid else session["uid_a"]


def get_state(uid: str) -> dict:
    session = storage.get_active_session(uid)
    if not session:
        raise DuelError("你现在没有进行中的决斗。")
    side = _side_of(session, uid)
    opp_side = "b" if side == "a" else "a"
    cooldowns = storage.get_cooldowns(session["id"], uid)
    learned = _usable_spells(uid)
    locked = session[f"locked_{side}"]

    available, unavailable = [], []
    for spell in learned:
        key, name, latin, subject, min_grade, category, desc = spell
        stats = spell_catalog.COMBAT[key]
        reason = None
        if stats.get("once") and session[f"ace_used_{side}"]:
            reason = "本场已用过"
        elif cooldowns.get(key, 0) > session["round"]:
            reason = f"冷却至第{cooldowns[key]}回合"
        elif locked and (locked == "any" or locked == category):
            reason = "被对方封锁"
        entry = {"name": name, "category": category, "damage": stats.get("damage", 0), "reason": reason}
        (unavailable if reason else available).append(entry)

    return {
        "session_id": session["id"],
        "round": session["round"],
        "total_rounds": spell_catalog.DUEL_ROUNDS,
        "my_hp": session[f"hp_{side}"],
        "opp_hp": session[f"hp_{opp_side}"],
        "opponent": _opponent_of(session, uid),
        "my_turn": session["turn"] == side,
        "my_shield": session[f"shield_{side}"],
        "opp_last_spell": session[f"last_spell_{opp_side}"],
        "locked": locked,
        "available": available,
        "unavailable": unavailable,
    }


def _finish(session, winner_uid: str | None, reason: str) -> dict:
    storage.update_session(session["id"], status="finished", winner=winner_uid or "")
    result = {"finished": True, "winner": winner_uid, "reason": reason}
    if winner_uid:
        loser_uid = _opponent_of(session, winner_uid)
        winner = core_storage.get_player(winner_uid)
        if winner and winner["house"]:
            core_storage.add_house_points(winner["house"], spell_catalog.DUEL_WIN_HOUSE_POINTS)
        core_storage.add_subject_exp(winner_uid, "defence", spell_catalog.DUEL_WIN_SUBJECT_EXP)
        core_storage.add_subject_exp(loser_uid, "defence", spell_catalog.DUEL_LOSE_SUBJECT_EXP)
        result["house_points"] = spell_catalog.DUEL_WIN_HOUSE_POINTS
        result["winner_house"] = winner["house"] if winner else ""
        result["loser"] = loser_uid
    else:
        for u in (session["uid_a"], session["uid_b"]):
            core_storage.add_subject_exp(u, "defence", spell_catalog.DUEL_LOSE_SUBJECT_EXP)
    return result


def _advance_turn(session) -> dict:
    """换手；如果一个回合两边都出完了，回合数+1。返回要写回session的字段。"""
    if session["turn"] == "a":
        return {"turn": "b"}
    return {"turn": "a", "round": session["round"] + 1}


def cast(uid: str, spell_input: str) -> dict:
    session = storage.get_active_session(uid)
    if not session:
        raise DuelError("你现在没有进行中的决斗。")
    side = _side_of(session, uid)
    if session["turn"] != side:
        raise DuelError("还没轮到你，等对方出手。")

    spell = spell_catalog.find(spell_input.strip())
    if not spell:
        raise DuelError("没有这个咒语。")
    key, name, latin, subject, min_grade, category, desc = spell

    if not core_storage.has_spell(uid, key):
        raise DuelError(f"你还没学会「{name}」。")
    if category not in spell_catalog.COMBAT_CATEGORIES:
        raise DuelError(f"「{name}」不是战斗咒语，决斗里用不上。")

    stats = spell_catalog.COMBAT[key]
    opp_side = "b" if side == "a" else "a"

    if stats.get("once") and session[f"ace_used_{side}"]:
        raise DuelError(f"「{name}」每场决斗只能用一次，你已经用过了。")
    cooldowns = storage.get_cooldowns(session["id"], uid)
    if cooldowns.get(key, 0) > session["round"]:
        raise DuelError(f"「{name}」还在冷却，第{cooldowns[key]}回合才能再用。")
    locked = session[f"locked_{side}"]
    if locked and (locked == "any" or locked == category):
        raise DuelError(f"你被对方封锁了，这一回合用不了{'任何咒语' if locked == 'any' else name}。")

    # ── 结算 ──
    opp_last = session[f"last_spell_{opp_side}"]
    opp_last_category = ""
    if opp_last:
        opp_spell = spell_catalog.SPELLS_BY_KEY.get(opp_last)
        opp_last_category = opp_spell[5] if opp_spell else ""
    countered = (
        category != "ace"
        and opp_last_category
        and spell_catalog.COUNTERS.get(category) == opp_last_category
    )
    multiplier = spell_catalog.COUNTER_DAMAGE_BONUS if countered else 1.0

    damage = int(stats.get("damage", 0) * multiplier)
    shield_gain = int(stats.get("shield", 0) * multiplier)

    updates: dict = {f"last_spell_{side}": key}
    blocked = 0
    if damage:
        opp_shield = session[f"shield_{opp_side}"]
        if opp_shield and not stats.get("pierce"):
            blocked = min(opp_shield, damage)
            damage -= blocked
            updates[f"shield_{opp_side}"] = opp_shield - blocked
        elif opp_shield and stats.get("pierce"):
            updates[f"shield_{opp_side}"] = 0  # 强击/王牌直接打穿护盾
    new_opp_hp = max(0, session[f"hp_{opp_side}"] - damage)
    updates[f"hp_{opp_side}"] = new_opp_hp

    if shield_gain:
        updates[f"shield_{side}"] = session[f"shield_{side}"] + shield_gain
    if stats.get("lock"):
        updates[f"locked_{opp_side}"] = stats["lock"]
    else:
        updates[f"locked_{opp_side}"] = ""  # 没上锁就把对方身上的锁解除
    updates[f"locked_{side}"] = ""  # 自己身上的锁这回合已经生效过了，清掉
    if stats.get("once"):
        updates[f"ace_used_{side}"] = 1

    storage.set_cooldown(session["id"], uid, key, session["round"] + stats.get("cooldown", 1))

    action = {
        "spell": name,
        "latin": latin,
        "category": category,
        "damage": damage,
        "blocked": blocked,
        "shield_gain": shield_gain,
        "countered": countered,
        "countered_what": opp_last_category,
        "lock": stats.get("lock", ""),
        "opp_hp": new_opp_hp,
        "opponent": _opponent_of(session, uid),
    }

    # ── 判定是否结束 ──
    if new_opp_hp <= 0:
        storage.update_session(session["id"], **updates)
        session = storage.get_session(session["id"])
        return {**action, **_finish(session, uid, "对手倒下了")}

    updates.update(_advance_turn(session))
    storage.update_session(session["id"], **updates)
    session = storage.get_session(session["id"])

    if session["round"] > spell_catalog.DUEL_ROUNDS:
        if session["hp_a"] > session["hp_b"]:
            winner = session["uid_a"]
        elif session["hp_b"] > session["hp_a"]:
            winner = session["uid_b"]
        else:
            winner = None
        return {**action, **_finish(session, winner, f"{spell_catalog.DUEL_ROUNDS}个回合打完，按剩余血量判定")}

    return {
        **action,
        "finished": False,
        "round": session["round"],
        "next_turn": session["uid_a"] if session["turn"] == "a" else session["uid_b"],
    }


def skip(uid: str) -> dict:
    """什么都不做。咒语全在冷却时的保底选项，但任何时候都能用。"""
    session = storage.get_active_session(uid)
    if not session:
        raise DuelError("你现在没有进行中的决斗。")
    side = _side_of(session, uid)
    if session["turn"] != side:
        raise DuelError("还没轮到你，等对方出手。")

    updates = {f"last_spell_{side}": "", f"locked_{side}": ""}
    updates.update(_advance_turn(session))
    storage.update_session(session["id"], **updates)
    session = storage.get_session(session["id"])

    if session["round"] > spell_catalog.DUEL_ROUNDS:
        if session["hp_a"] > session["hp_b"]:
            winner = session["uid_a"]
        elif session["hp_b"] > session["hp_a"]:
            winner = session["uid_b"]
        else:
            winner = None
        return {"skipped": True, **_finish(session, winner, f"{spell_catalog.DUEL_ROUNDS}个回合打完，按剩余血量判定")}

    return {
        "skipped": True,
        "finished": False,
        "round": session["round"],
        "opponent": _opponent_of(session, uid),
    }


def flee(uid: str) -> dict:
    session = storage.get_active_session(uid)
    if not session:
        raise DuelError("你现在没有进行中的决斗。")
    opponent = _opponent_of(session, uid)
    result = _finish(session, opponent, "对手逃跑了")
    return {"fled": True, "opponent": opponent, **result}
