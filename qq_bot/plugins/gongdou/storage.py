import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gongdou.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    uid TEXT PRIMARY KEY,
    favor INTEGER NOT NULL DEFAULT 0,
    money INTEGER NOT NULL DEFAULT 200,
    stamina INTEGER NOT NULL DEFAULT 30,
    stamina_updated_at INTEGER NOT NULL,
    scheme_level INTEGER NOT NULL DEFAULT 1,
    scheme_exp INTEGER NOT NULL DEFAULT 0,
    last_greet_date TEXT NOT NULL DEFAULT '',
    last_bed_date TEXT NOT NULL DEFAULT '',
    counter_date TEXT NOT NULL DEFAULT '',
    report_count_today INTEGER NOT NULL DEFAULT 0,
    scheme_count_today INTEGER NOT NULL DEFAULT 0,
    cold_palace_until INTEGER NOT NULL DEFAULT 0,
    report_success_count INTEGER NOT NULL DEFAULT 0,
    report_fail_count INTEGER NOT NULL DEFAULT 0,
    scheme_success_count INTEGER NOT NULL DEFAULT 0,
    scheme_fail_count INTEGER NOT NULL DEFAULT 0,
    been_sabotaged_count INTEGER NOT NULL DEFAULT 0,
    cold_palace_count INTEGER NOT NULL DEFAULT 0,
    escape_success_count INTEGER NOT NULL DEFAULT 0,
    bed_success_count INTEGER NOT NULL DEFAULT 0,
    active_title TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS alliances (
    uid_a TEXT NOT NULL,
    uid_b TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (uid_a, uid_b)
);

CREATE TABLE IF NOT EXISTS player_titles (
    uid TEXT NOT NULL,
    title_key TEXT NOT NULL,
    unlocked_at INTEGER NOT NULL,
    PRIMARY KEY (uid, title_key)
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


# ======================== 玩家 ========================


def get_or_create_player(uid: str) -> sqlite3.Row:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
        if row:
            return row
        ts = now()
        conn.execute(
            "INSERT INTO players (uid, stamina, stamina_updated_at, created_at, updated_at) "
            "VALUES (?, 30, ?, ?, ?)",
            (uid, ts, ts, ts),
        )
        conn.commit()
        return conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def update_player(uid: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE players SET {cols} WHERE uid = ?", (*fields.values(), uid))
        conn.commit()
    finally:
        conn.close()


def add_money(uid: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET money = MAX(money + ?, 0), updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def add_favor(uid: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET favor = MAX(favor + ?, 0), updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def add_scheme_exp(uid: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET scheme_exp = scheme_exp + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def set_scheme_level(uid: str, level: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET scheme_level = ?, updated_at = ? WHERE uid = ?",
            (level, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def increment_counter(uid: str, field: str, amount: int = 1) -> None:
    assert field in (
        "report_success_count",
        "report_fail_count",
        "scheme_success_count",
        "scheme_fail_count",
        "been_sabotaged_count",
        "cold_palace_count",
        "escape_success_count",
        "bed_success_count",
    )
    conn = get_conn()
    try:
        conn.execute(
            f"UPDATE players SET {field} = {field} + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def leaderboard_favor(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT uid, favor, active_title FROM players ORDER BY favor DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()


def leaderboard_money(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT uid, money, active_title FROM players ORDER BY money DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()


def leaderboard_scheme(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT uid, scheme_level, scheme_exp, scheme_success_count, active_title FROM players "
            "ORDER BY scheme_level DESC, scheme_exp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


# ======================== 结盟 ========================


def _norm(uid_a: str, uid_b: str) -> tuple[str, str]:
    return (uid_a, uid_b) if uid_a <= uid_b else (uid_b, uid_a)


def get_alliance(uid_a: str, uid_b: str) -> sqlite3.Row | None:
    a, b = _norm(uid_a, uid_b)
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM alliances WHERE uid_a = ? AND uid_b = ?", (a, b)
        ).fetchone()
    finally:
        conn.close()


def create_pending_alliance(requester: str, target: str) -> None:
    a, b = _norm(requester, target)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO alliances (uid_a, uid_b, status, requested_by, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (a, b, requester, now()),
        )
        conn.commit()
    finally:
        conn.close()


def activate_alliance(uid_a: str, uid_b: str) -> None:
    a, b = _norm(uid_a, uid_b)
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE alliances SET status = 'active' WHERE uid_a = ? AND uid_b = ?", (a, b)
        )
        conn.commit()
    finally:
        conn.close()


def delete_alliance(uid_a: str, uid_b: str) -> None:
    a, b = _norm(uid_a, uid_b)
    conn = get_conn()
    try:
        conn.execute("DELETE FROM alliances WHERE uid_a = ? AND uid_b = ?", (a, b))
        conn.commit()
    finally:
        conn.close()


def is_allied(uid_a: str, uid_b: str) -> bool:
    row = get_alliance(uid_a, uid_b)
    return row is not None and row["status"] == "active"


def list_allies(uid: str) -> list[str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT uid_a, uid_b FROM alliances WHERE status = 'active' AND (uid_a = ? OR uid_b = ?)",
            (uid, uid),
        ).fetchall()
        return [r["uid_b"] if r["uid_a"] == uid else r["uid_a"] for r in rows]
    finally:
        conn.close()


# ======================== 称号 ========================


def has_title(uid: str, title_key: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM player_titles WHERE uid = ? AND title_key = ?", (uid, title_key)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def unlock_title(uid: str, title_key: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO player_titles (uid, title_key, unlocked_at) VALUES (?, ?, ?)",
            (uid, title_key, now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_titles(uid: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT title_key, unlocked_at FROM player_titles WHERE uid = ? ORDER BY unlocked_at",
            (uid,),
        ).fetchall()
    finally:
        conn.close()
