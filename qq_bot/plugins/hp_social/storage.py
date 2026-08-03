import sqlite3
import time

from plugins.hp_core.storage import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS affection (
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (from_uid, to_uid)
);

CREATE TABLE IF NOT EXISTS relationships (
    uid_a TEXT NOT NULL,
    uid_b TEXT NOT NULL,
    established_at INTEGER NOT NULL,
    PRIMARY KEY (uid_a, uid_b)
);

CREATE TABLE IF NOT EXISTS flirt_log (
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    PRIMARY KEY (from_uid, to_uid, day)
);

CREATE TABLE IF NOT EXISTS social_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    dates INTEGER NOT NULL DEFAULT 0,
    interferes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


# ======================== 好感度（单向） ========================


def get_affection(from_uid: str, to_uid: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM affection WHERE from_uid = ? AND to_uid = ?", (from_uid, to_uid)
        ).fetchone()
        return row["value"] if row else 0
    finally:
        conn.close()


def add_affection(from_uid: str, to_uid: str, amount: int, max_value: int) -> int:
    """封顶max_value、保底0，返回变化后的值。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO affection (from_uid, to_uid, value, updated_at) "
            "VALUES (?, ?, MAX(0, MIN(?, ?)), ?) "
            "ON CONFLICT(from_uid, to_uid) DO UPDATE SET "
            "value = MAX(0, MIN(?, affection.value + ?)), updated_at = excluded.updated_at",
            (from_uid, to_uid, max_value, amount, now(), max_value, amount),
        )
        conn.commit()
        row = conn.execute(
            "SELECT value FROM affection WHERE from_uid = ? AND to_uid = ?", (from_uid, to_uid)
        ).fetchone()
        return row["value"]
    finally:
        conn.close()


def list_affection_from(from_uid: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM affection WHERE from_uid = ? AND value > 0 ORDER BY value DESC", (from_uid,)
        ).fetchall()
    finally:
        conn.close()


def list_affection_to(to_uid: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM affection WHERE to_uid = ? AND value > 0 ORDER BY value DESC", (to_uid,)
        ).fetchall()
    finally:
        conn.close()


# ======================== 恋爱关系 ========================


def _pair(uid_a: str, uid_b: str) -> tuple[str, str]:
    """统一按字典序存，保证同一对人只有一条记录，查询不用考虑方向。"""
    return (uid_a, uid_b) if uid_a < uid_b else (uid_b, uid_a)


def get_partner(uid: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT uid_a, uid_b FROM relationships WHERE uid_a = ? OR uid_b = ?", (uid, uid)
        ).fetchone()
        if not row:
            return None
        return row["uid_b"] if row["uid_a"] == uid else row["uid_a"]
    finally:
        conn.close()


def create_relationship(uid_a: str, uid_b: str) -> None:
    a, b = _pair(uid_a, uid_b)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO relationships (uid_a, uid_b, established_at) VALUES (?, ?, ?)",
            (a, b, now()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_relationship(uid_a: str, uid_b: str) -> bool:
    a, b = _pair(uid_a, uid_b)
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM relationships WHERE uid_a = ? AND uid_b = ?", (a, b))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_all_couples() -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM relationships ORDER BY established_at").fetchall()
    finally:
        conn.close()


# ======================== 调情记录 ========================


def try_log_flirt(from_uid: str, to_uid: str, day: int) -> bool:
    """今天还没对这个人调过情就记一笔返回True，已经调过了返回False。
    是"对每个人每天各一次"，不是"每天总共一次"。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO flirt_log (from_uid, to_uid, day) VALUES (?, ?, ?)",
            (from_uid, to_uid, day),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ======================== 每日次数 ========================


def get_daily(uid: str, day: int) -> sqlite3.Row:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM social_daily WHERE uid = ? AND day = ?", (uid, day)).fetchone()
        if row:
            return row
        conn.execute("INSERT OR IGNORE INTO social_daily (uid, day) VALUES (?, ?)", (uid, day))
        conn.commit()
        return conn.execute("SELECT * FROM social_daily WHERE uid = ? AND day = ?", (uid, day)).fetchone()
    finally:
        conn.close()


def increment_daily(uid: str, day: int, field: str) -> None:
    assert field in ("dates", "interferes")
    conn = get_conn()
    try:
        conn.execute(
            f"INSERT INTO social_daily (uid, day, {field}) VALUES (?, ?, 1) "
            f"ON CONFLICT(uid, day) DO UPDATE SET {field} = {field} + 1",
            (uid, day),
        )
        conn.commit()
    finally:
        conn.close()
