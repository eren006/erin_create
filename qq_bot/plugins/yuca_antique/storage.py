import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "yuca_antique.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    uid TEXT PRIMARY KEY,
    luck INTEGER NOT NULL DEFAULT 20,
    luck_updated_at INTEGER NOT NULL,
    eye_level INTEGER NOT NULL DEFAULT 1,
    eye_exp INTEGER NOT NULL DEFAULT 0,
    money INTEGER NOT NULL DEFAULT 0,
    identify_success_count INTEGER NOT NULL DEFAULT 0,
    identify_fail_count INTEGER NOT NULL DEFAULT 0,
    mine_count INTEGER NOT NULL DEFAULT 0,
    active_title TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS player_titles (
    uid TEXT NOT NULL,
    title_key TEXT NOT NULL,
    unlocked_at INTEGER NOT NULL,
    PRIMARY KEY (uid, title_key)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    category TEXT NOT NULL,
    type_name TEXT NOT NULL,
    dynasty TEXT NOT NULL DEFAULT '',
    quality TEXT NOT NULL,
    base_value INTEGER NOT NULL,
    rarity_score INTEGER NOT NULL,
    kind TEXT NOT NULL,
    is_opened INTEGER NOT NULL DEFAULT 0,
    is_identified INTEGER NOT NULL DEFAULT 0,
    identify_correct INTEGER NOT NULL DEFAULT 0,
    perceived_type TEXT NOT NULL DEFAULT '',
    perceived_dynasty TEXT NOT NULL DEFAULT '',
    clues_revealed TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT '背包',
    sold_price INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_uid ON items (uid);
CREATE INDEX IF NOT EXISTS idx_items_uid_status ON items (uid, status);
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
        for stmt in (
            "ALTER TABLE players ADD COLUMN identify_success_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE players ADD COLUMN identify_fail_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE players ADD COLUMN mine_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE players ADD COLUMN active_title TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # 列已存在（旧库升级用）
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
            "INSERT INTO players (uid, luck, luck_updated_at, eye_level, eye_exp, money, created_at, updated_at) "
            "VALUES (?, 20, ?, 1, 0, 0, ?, ?)",
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
            "UPDATE players SET money = money + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def add_eye_exp(uid: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET eye_exp = eye_exp + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def set_eye_level(uid: str, level: int, exp: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET eye_level = ?, eye_exp = ?, updated_at = ? WHERE uid = ?",
            (level, exp, now(), uid),
        )
        conn.commit()
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


def leaderboard_eye(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT uid, eye_level, eye_exp, active_title FROM players "
            "ORDER BY eye_level DESC, eye_exp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def increment_counter(uid: str, field: str, amount: int = 1) -> None:
    assert field in ("identify_success_count", "identify_fail_count", "mine_count")
    conn = get_conn()
    try:
        conn.execute(
            f"UPDATE players SET {field} = {field} + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


# ======================== 藏品 ========================


def create_item(
    uid: str,
    category: str,
    type_name: str,
    dynasty: str,
    quality: str,
    base_value: int,
    rarity_score: int,
    kind: str,
    is_opened: int = 0,
) -> int:
    conn = get_conn()
    try:
        ts = now()
        cur = conn.execute(
            "INSERT INTO items (uid, category, type_name, dynasty, quality, base_value, rarity_score, "
            "kind, is_opened, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, category, type_name, dynasty, quality, base_value, rarity_score, kind, is_opened, ts, ts),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_item(item_id: int) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()


def list_items(uid: str, status: str | None = None) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        if status:
            return conn.execute(
                "SELECT * FROM items WHERE uid = ? AND status = ? ORDER BY id DESC", (uid, status)
            ).fetchall()
        return conn.execute(
            "SELECT * FROM items WHERE uid = ? ORDER BY id DESC", (uid,)
        ).fetchall()
    finally:
        conn.close()


def update_item(item_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE items SET {cols} WHERE id = ?", (*fields.values(), item_id))
        conn.commit()
    finally:
        conn.close()


def get_clues(item: sqlite3.Row) -> list[str]:
    try:
        return json.loads(item["clues_revealed"])
    except (TypeError, ValueError):
        return []


def add_clue(item_id: int, clue: str) -> None:
    item = get_item(item_id)
    if not item:
        return
    clues = get_clues(item)
    clues.append(clue)
    update_item(item_id, clues_revealed=json.dumps(clues, ensure_ascii=False))


def top_showcase_rarity(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM items WHERE uid = ? AND status = '展示柜' ORDER BY rarity_score DESC LIMIT 1",
            (uid,),
        ).fetchone()
    finally:
        conn.close()


def leaderboard_showcase(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT top.uid, top.type_name, top.dynasty, top.quality, top.rarity_score, "
            "       players.active_title FROM ("
            "  SELECT *, ROW_NUMBER() OVER (PARTITION BY uid ORDER BY rarity_score DESC) AS rn "
            "  FROM items WHERE status = '展示柜'"
            ") AS top JOIN players ON players.uid = top.uid "
            "WHERE top.rn = 1 ORDER BY top.rarity_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


# ======================== 图鉴 ========================


def codex_discovered(uid: str) -> set[str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT type_name FROM items WHERE uid = ? AND ("
            "  (kind IN ('stone', 'gem') AND is_opened = 1) OR"
            "  (kind = 'antique' AND is_identified = 1 AND identify_correct = 1)"
            ")",
            (uid,),
        ).fetchall()
        return {r["type_name"] for r in rows}
    finally:
        conn.close()


def has_quality(uid: str, quality: str, category: str | None = None) -> bool:
    conn = get_conn()
    try:
        sql = (
            "SELECT 1 FROM items WHERE uid = ? AND quality = ? AND ("
            "  (kind IN ('stone', 'gem') AND is_opened = 1) OR"
            "  (kind = 'antique' AND is_identified = 1 AND identify_correct = 1)"
            ")"
        )
        params: tuple = (uid, quality)
        if category:
            sql += " AND category = ?"
            params = (uid, quality, category)
        row = conn.execute(sql + " LIMIT 1", params).fetchone()
        return row is not None
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
