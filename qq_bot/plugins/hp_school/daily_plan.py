"""聚合今日可行动信息，供 /今日安排 一次展示。"""

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

from . import homework, lessons, mainline, storage, subjects, work

GRADE_END_DAY = {1: 4, 2: 8, 3: 12, 4: 16, 5: 21, 6: 25, 7: 30}


class DailyPlanError(Exception):
    pass


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _one(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchone()


def build(uid: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise DailyPlanError("你还没有分院，先发「/入学 你的名字」完成入学测试。")
    player = core_storage.sync_stamina(uid)
    day = core_storage.get_current_day() or 1
    homework_state = homework.list_today(uid)

    unlocked = [row for row in subjects.SUBJECTS if player["grade"] >= row[2]]
    lesson_rows = []
    scored_lessons = core_storage.get_total_scored_lesson_count(uid, day)
    for key, name, _, _ in unlocked:
        count = core_storage.get_lesson_count(uid, key, day)
        if count:
            lesson_rows.append(f"{name}{count}次")

    session = storage.get_lesson_session(uid)
    unfinished = subjects.SUBJECTS_BY_KEY[session["subject_key"]][0] if session else ""
    activities = []
    conn = get_conn()
    try:
        if player["grade"] >= 2:
            qp = None
            if _table_exists(conn, "quidditch_players"):
                qp = _one(conn, "SELECT position FROM quidditch_players WHERE uid=?", (uid,))
            if qp and qp["position"]:
                daily = _one(conn, "SELECT trainings, matches FROM quidditch_daily WHERE uid=? AND day=?", (uid, day))
                trainings = daily["trainings"] if daily else 0
                matches = daily["matches"] if daily else 0
                activities.append(f"魁地奇：训练{trainings}/3，比赛{matches}/2")
            else:
                activities.append("魁地奇：已解锁，可争取球队位置")
        if player["grade"] >= 3:
            daily = None
            if _table_exists(conn, "duel_daily"):
                daily = _one(conn, "SELECT initiated FROM duel_daily WHERE uid=? AND day=?", (uid, day))
            activities.append(f"决斗俱乐部：主动发起{daily['initiated'] if daily else 0}/3")
        if player["grade"] >= 2 and _table_exists(conn, "forest_runs"):
            runs = _one(conn, "SELECT runs FROM forest_daily WHERE uid=? AND day=?", (uid, day))
            in_forest = _one(conn, "SELECT depth FROM forest_runs WHERE uid=? AND status='active'", (uid,))
            if in_forest:
                activities.append(f"禁林：正在第{in_forest['depth']}层（「/禁林状态」查看）")
            else:
                activities.append(f"禁林探险：{runs['runs'] if runs else 0}/2")
        if _table_exists(conn, "relationships"):
            partner = _one(conn, "SELECT 1 FROM relationships WHERE uid_a=? OR uid_b=?", (uid, uid))
            if partner:
                social = _one(conn, "SELECT dates FROM social_daily WHERE uid=? AND day=?", (uid, day))
                activities.append(f"约会：{social['dates'] if social else 0}/2")
    finally:
        conn.close()

    claimable = mainline.claimable_rewards(uid)
    work_count = storage.get_work_count(uid, day)
    return {
        "day": day,
        "grade": player["grade"],
        "stamina": player["stamina"],
        "stamina_max": core_storage.STAMINA_MAX,
        "homework": homework_state,
        "scored_lessons": scored_lessons,
        "scored_lesson_cap": lessons.DAILY_GLOBAL_LIMIT,
        "lesson_rows": lesson_rows,
        "unfinished_lesson": unfinished,
        "activities": activities,
        "claimable": claimable,
        "work_count": work_count,
        "days_to_exam": max(0, GRADE_END_DAY[player["grade"]] - day),
    }
