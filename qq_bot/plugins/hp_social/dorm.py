"""寝室系统：新政策——不同学院可以合住，但必须同性别，一间两人。

邀请/接受/拒绝/撤回的流程完全照搬决斗邀请（hp_events/duel.py）的写法：
一个人同一时间只能有一条发出的邀请，用 PRIMARY KEY(from_uid) 的表天然保证。
"dorms" 表用两个 UNIQUE INDEX 保证一个人不会同时挂在两间寝室下。
"""

from __future__ import annotations

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS dorms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    member_a TEXT NOT NULL,
    member_b TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dorms_member_a ON dorms(member_a);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dorms_member_b ON dorms(member_b);

CREATE TABLE IF NOT EXISTS dorm_invites (
    from_uid TEXT PRIMARY KEY,
    to_uid TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""

NAME_MAX_LEN = 20


class DormError(Exception):
    pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


init_db()


def _require_enrolled(uid: str, who: str = "你") -> None:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise DormError(f"{who}还没有分院，先发「/入学」完成入学测试。")


def _get_dorm_row(uid: str):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM dorms WHERE member_a = ? OR member_b = ?", (uid, uid)
        ).fetchone()
    finally:
        conn.close()


def _roommate_of(row, uid: str) -> str:
    return row["member_b"] if row["member_a"] == uid else row["member_a"]


# ======================== 邀请 ========================


def invite(uid: str, target_uid: str) -> dict:
    _require_enrolled(uid)
    if target_uid == uid:
        raise DormError("不能邀请自己同住一间寝室。")
    _require_enrolled(target_uid, "对方")

    me = core_storage.get_player(uid)
    them = core_storage.get_player(target_uid)
    if me["gender"] != them["gender"]:
        raise DormError("新政策规定寝室必须是同性别的两个人，你和对方性别不一样。")

    if _get_dorm_row(uid):
        raise DormError("你已经有寝室了，先退出现在的寝室才能邀请别人。")
    if _get_dorm_row(target_uid):
        raise DormError("对方已经有寝室了。")

    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM dorm_invites WHERE from_uid = ?", (uid,)
        ).fetchone()
        if existing:
            raise DormError("你已经发出过一份邀请了，等对方回应，或者先撤回。")
        conn.execute(
            "INSERT INTO dorm_invites (from_uid, to_uid, created_at) VALUES (?, ?, ?)",
            (uid, target_uid, core_storage.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"target": target_uid}


def withdraw(uid: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM dorm_invites WHERE from_uid = ?", (uid,)
        ).fetchone()
        if not row:
            raise DormError("你没有待回应的寝室邀请。")
        conn.execute("DELETE FROM dorm_invites WHERE from_uid = ?", (uid,))
        conn.commit()
        return {"target": row["to_uid"]}
    finally:
        conn.close()


def decline(uid: str, from_uid: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM dorm_invites WHERE from_uid = ? AND to_uid = ?", (from_uid, uid)
        ).fetchone()
        if not row:
            raise DormError("没有这个人发给你的寝室邀请。")
        conn.execute("DELETE FROM dorm_invites WHERE from_uid = ?", (from_uid,))
        conn.commit()
        return {"from_uid": from_uid}
    finally:
        conn.close()


def accept(uid: str, from_uid: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM dorm_invites WHERE from_uid = ? AND to_uid = ?", (from_uid, uid)
        ).fetchone()
        if not row:
            raise DormError("没有这个人发给你的寝室邀请。")

        if _get_dorm_row(uid) or _get_dorm_row(from_uid):
            conn.execute("DELETE FROM dorm_invites WHERE from_uid = ?", (from_uid,))
            conn.commit()
            raise DormError("这份邀请已经失效了（有一方已经加入了别的寝室）。")

        me = core_storage.get_player(uid)
        them = core_storage.get_player(from_uid)
        if not them or not them["house"] or me["gender"] != them["gender"]:
            conn.execute("DELETE FROM dorm_invites WHERE from_uid = ?", (from_uid,))
            conn.commit()
            raise DormError("这份邀请已经失效了。")

        conn.execute("DELETE FROM dorm_invites WHERE from_uid = ?", (from_uid,))
        default_name = f"{core_storage.get_name(from_uid)}和{core_storage.get_name(uid)}的寝室"
        conn.execute(
            "INSERT INTO dorms (name, member_a, member_b, created_at) VALUES (?, ?, ?, ?)",
            (default_name[:NAME_MAX_LEN], from_uid, uid, core_storage.now()),
        )
        conn.commit()
        return {"roommate": from_uid, "name": default_name[:NAME_MAX_LEN]}
    finally:
        conn.close()


# ======================== 寝室管理 ========================


def get_my_dorm(uid: str) -> dict | None:
    row = _get_dorm_row(uid)
    if not row:
        return None
    roommate = _roommate_of(row, uid)
    return {
        "id": row["id"],
        "name": row["name"],
        "roommate": roommate,
        "roommate_name": core_storage.get_full_name(roommate),
        "created_at": row["created_at"],
        "score": _dorm_score(row["member_a"]) + _dorm_score(row["member_b"]),
    }


def leave(uid: str) -> dict:
    row = _get_dorm_row(uid)
    if not row:
        raise DormError("你现在没有寝室。")
    roommate = _roommate_of(row, uid)
    conn = get_conn()
    try:
        conn.execute("DELETE FROM dorms WHERE id = ?", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    return {"roommate": roommate}


def rename(uid: str, name: str) -> dict:
    row = _get_dorm_row(uid)
    if not row:
        raise DormError("你现在没有寝室，没法改名。")
    name = name.strip()
    if not name:
        raise DormError("寝室名不能是空的。")
    if len(name) > NAME_MAX_LEN:
        raise DormError(f"寝室名最多{NAME_MAX_LEN}个字。")
    conn = get_conn()
    try:
        conn.execute("UPDATE dorms SET name = ? WHERE id = ?", (name, row["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"name": name}


# ======================== 战力 / 排行榜 ========================


def _dorm_score(uid: str) -> int:
    """学业分（总学科经验）+ 课外活动分（决斗胜场/禁林战绩/已学咒语/魁地奇赛季得分）。"""
    from plugins.hp_events import storage as events_storage

    conn = get_conn()
    try:
        academic = conn.execute(
            "SELECT COALESCE(SUM(exp), 0) FROM subject_exp WHERE uid = ?", (uid,)
        ).fetchone()[0]
        duel_wins = conn.execute(
            "SELECT COUNT(*) FROM duel_sessions WHERE status = 'finished' AND winner = ?", (uid,)
        ).fetchone()[0]
        forest_kills = conn.execute(
            "SELECT COUNT(*) FROM forest_defeated WHERE uid = ?", (uid,)
        ).fetchone()[0]
    finally:
        conn.close()

    spells_learned = len(core_storage.list_learned_spells(uid))
    quidditch_player = events_storage.get_quidditch_player(uid)
    quidditch_score = quidditch_player["season_score"] if quidditch_player else 0

    extracurricular = duel_wins * 10 + forest_kills * 5 + spells_learned * 3 + quidditch_score
    return academic + extracurricular


def leaderboard(limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM dorms").fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        score = _dorm_score(row["member_a"]) + _dorm_score(row["member_b"])
        result.append(
            {
                "name": row["name"],
                "member_a_name": core_storage.get_full_name(row["member_a"]),
                "member_b_name": core_storage.get_full_name(row["member_b"]),
                "score": score,
            }
        )
    result.sort(key=lambda d: d["score"], reverse=True)
    return result[:limit]
