"""级长选举：四年级结束时自动提名，五年级开学前投票选出各院级长。

时间线（贴合原著——级长在五年级前确定）：
  Day 16  四年级结业，系统按学业表现自动提名各院前3名，投票开放
  Day 17  投票进行中
  Day 18  唱票，各院得票前2名当选

候选人不开放自由报名——一窝蜂报名会把票稀释掉，而且"平时认真上课的人才有资格"
本身就是个正向反馈。只能投本院，一人一票，可以改投。
"""

from __future__ import annotations

from plugins.hp_core import storage as core_storage

from . import storage

storage.init_prefect()

NOMINATE_DAY = 16
CLOSE_DAY = 18
CANDIDATES_PER_HOUSE = 3
WINNERS_PER_HOUSE = 2
PREFECT_TITLE = "级长"
DUTY_HOUSE_POINTS = 3
DUTY_GALLEONS = 15


class PrefectError(Exception):
    pass


def phase(day: int) -> str:
    if day < NOMINATE_DAY:
        return "before"
    if day < CLOSE_DAY:
        return "voting"
    return "closed"


def nominate() -> dict[str, list[str]]:
    """按学业表现自动提名各院前3名。幂等——重复调用不会改变已有名单。"""
    if storage.list_prefect_candidates():
        return _candidates_by_house()

    board = core_storage.student_leaderboard(limit=500)
    by_house: dict[str, list[str]] = {}
    for row in board:
        bucket = by_house.setdefault(row["house"], [])
        if len(bucket) < CANDIDATES_PER_HOUSE:
            bucket.append(row["uid"])
    for house, uids in by_house.items():
        for uid in uids:
            storage.add_prefect_candidate(uid, house)
    return by_house


def _candidates_by_house() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in storage.list_prefect_candidates():
        result.setdefault(row["house"], []).append(row["uid"])
    return result


def candidates(house: str | None = None) -> list[dict]:
    rows = storage.list_prefect_candidates(house)
    tally = storage.vote_tally()
    return [
        {
            "uid": row["uid"],
            "house": row["house"],
            "name": core_storage.get_full_name(row["uid"]),
            "votes": tally.get(row["uid"], 0),
        }
        for row in rows
    ]


def vote(uid: str, target_uid: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise PrefectError("你还没有完成入学手续。")

    day = core_storage.get_current_day() or 1
    state = phase(day)
    if state == "before":
        raise PrefectError(f"级长选举还没开始，第{NOMINATE_DAY}天开放投票。")
    if state == "closed":
        raise PrefectError("投票已经截止了。")

    target = core_storage.get_player(target_uid)
    if not target or not target["house"]:
        raise PrefectError("找不到这个候选人。")
    if target["house"] != player["house"]:
        raise PrefectError(f"只能投本院的候选人——你是{player['house']}的。")
    if not storage.is_prefect_candidate(target_uid):
        raise PrefectError("这个人不在候选名单里。")
    if target_uid == uid:
        raise PrefectError("不能投给自己。")

    previous = storage.get_prefect_vote(uid)
    storage.cast_prefect_vote(uid, target_uid, player["house"])
    return {
        "target": target_uid,
        "changed": bool(previous and previous != target_uid),
        "previous": previous,
    }


def my_vote(uid: str) -> str | None:
    return storage.get_prefect_vote(uid)


def close_election() -> dict[str, list[dict]]:
    """唱票并授予称号。幂等——已经产生过级长就直接返回结果。"""
    existing = storage.list_prefects()
    if existing:
        return _winners_by_house(existing)

    tally = storage.vote_tally()
    results: dict[str, list[dict]] = {}
    for house in core_storage.HOUSES:
        pool = [
            {"uid": row["uid"], "votes": tally.get(row["uid"], 0)}
            for row in storage.list_prefect_candidates(house)
        ]
        if not pool:
            results[house] = []
            continue
        # 票数相同时，按学业排名兜底，避免随机决出的级长看起来莫名其妙
        order = {row["uid"]: i for i, row in enumerate(core_storage.student_leaderboard(limit=500))}
        pool.sort(key=lambda x: (-x["votes"], order.get(x["uid"], 9999)))
        winners = pool[:WINNERS_PER_HOUSE]
        for w in winners:
            storage.add_prefect(w["uid"], house, w["votes"])
            core_storage.unlock_title(w["uid"], "prefect")
        results[house] = [
            {"uid": w["uid"], "name": core_storage.get_full_name(w["uid"]), "votes": w["votes"]}
            for w in winners
        ]
    return results


def _winners_by_house(rows) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {house: [] for house in core_storage.HOUSES}
    for row in rows:
        result.setdefault(row["house"], []).append(
            {"uid": row["uid"], "name": core_storage.get_full_name(row["uid"]), "votes": row["votes"]}
        )
    return result


def is_prefect(uid: str) -> bool:
    return storage.is_prefect(uid)


def prefects() -> dict[str, list[dict]]:
    return _winners_by_house(storage.list_prefects())


# ======================== 级长任务 ========================


def run_duty(uid: str) -> dict:
    """级长每天可以带一次巡查，给本院加分，自己也拿点跑腿费。"""
    if not is_prefect(uid):
        raise PrefectError("只有级长能带队巡查。")
    player = core_storage.get_player(uid)
    day = core_storage.get_current_day() or 1
    if storage.has_done_duty(uid, day):
        raise PrefectError("今天已经巡查过了，明天再来。")

    storage.mark_duty_done(uid, day)
    core_storage.add_house_points(player["house"], DUTY_HOUSE_POINTS)
    core_storage.add_galleons(uid, DUTY_GALLEONS)
    return {
        "house": player["house"],
        "house_points": DUTY_HOUSE_POINTS,
        "galleons": DUTY_GALLEONS,
    }


def duty_state(uid: str) -> dict:
    day = core_storage.get_current_day() or 1
    return {
        "is_prefect": is_prefect(uid),
        "done_today": storage.has_done_duty(uid, day) if is_prefect(uid) else False,
    }
