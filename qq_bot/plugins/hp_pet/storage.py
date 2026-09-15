"""宠物系统存表：一人可以养多只，但同一时间只能"装备"一只——只有装备中的那只
会衰减心情/饱食度、能互动、也只有它的羁绊等级对其他系统生效。

心情/饱食度不额外开定时任务刷新——跟 hp_core 的体力值一个思路，
每次读之前先按 synced_at 到现在经过的时间结算衰减（见 pet.py 的 _sync）。
"""

from __future__ import annotations

import sqlite3

from plugins.hp_core.storage import get_conn, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS pets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    item_key TEXT NOT NULL,
    family TEXT NOT NULL,
    breed_name TEXT NOT NULL,
    pet_name TEXT NOT NULL,
    personality TEXT NOT NULL,
    mood INTEGER NOT NULL DEFAULT 70,
    satiety INTEGER NOT NULL DEFAULT 70,
    synced_at INTEGER NOT NULL,
    bond_exp INTEGER NOT NULL DEFAULT 0,
    last_play_at INTEGER NOT NULL DEFAULT 0,
    equipped INTEGER NOT NULL DEFAULT 0,
    adopted_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pets_uid ON pets(uid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pets_uid_equipped ON pets(uid) WHERE equipped = 1;

CREATE TABLE IF NOT EXISTS pet_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    feeds INTEGER NOT NULL DEFAULT 0,
    walks INTEGER NOT NULL DEFAULT 0,
    trains INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);
"""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        is not None
    )


def _migrate_from_single_pet_table(conn: sqlite3.Connection) -> None:
    """功能刚上线时 pets 是"uid当主键、一人一只"的旧结构。这里升级成"id自增+
    equipped标记、一人可多养"，旧数据原样搬过来，各自标记成已装备（反正之前
    本来就只有一只，装备状态天然就是它）。"""
    if not _table_exists(conn, "pets"):
        return
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(pets)").fetchall()}
    if "id" in cols:
        return  # 已经是新结构
    conn.execute("ALTER TABLE pets RENAME TO pets_old_single")


def _copy_from_old_single_pet_table(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "pets_old_single"):
        return
    conn.execute(
        "INSERT INTO pets (uid, item_key, family, breed_name, pet_name, personality, "
        "mood, satiety, synced_at, bond_exp, last_play_at, equipped, adopted_at) "
        "SELECT uid, item_key, family, breed_name, pet_name, personality, "
        "mood, satiety, synced_at, bond_exp, last_play_at, 1, adopted_at FROM pets_old_single"
    )
    conn.execute("DROP TABLE pets_old_single")


def init_db() -> None:
    conn = get_conn()
    try:
        _migrate_from_single_pet_table(conn)
        conn.executescript(SCHEMA)
        _copy_from_old_single_pet_table(conn)
        conn.commit()
    finally:
        conn.close()


init_db()


# ======================== 宠物本体 ========================


def get_equipped_pet(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM pets WHERE uid = ? AND equipped = 1", (uid,)).fetchone()
    finally:
        conn.close()


def list_pets(uid: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM pets WHERE uid = ? ORDER BY adopted_at", (uid,)
        ).fetchall()
    finally:
        conn.close()


def get_pet_by_name(uid: str, pet_name: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM pets WHERE uid = ? AND pet_name = ?", (uid, pet_name)
        ).fetchone()
    finally:
        conn.close()


def create_pet(
    uid: str, item_key: str, family: str, breed_name: str, pet_name: str, personality: str,
    mood: int, satiety: int, equipped: bool,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO pets (uid, item_key, family, breed_name, pet_name, personality, "
            "mood, satiety, synced_at, bond_exp, last_play_at, equipped, adopted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
            (uid, item_key, family, breed_name, pet_name, personality, mood, satiety,
             now(), int(equipped), now()),
        )
        conn.commit()
    finally:
        conn.close()


def equip_pet(uid: str, pet_id: int) -> None:
    """切换装备：先卸下当前那只，再装备目标——装备时把synced_at拨到现在，
    避免它在"箱子里"放了多久，一装备就被结算一大笔心情/饱食度衰减。"""
    conn = get_conn()
    try:
        conn.execute("UPDATE pets SET equipped = 0 WHERE uid = ? AND equipped = 1", (uid,))
        conn.execute(
            "UPDATE pets SET equipped = 1, synced_at = ? WHERE id = ? AND uid = ?",
            (now(), pet_id, uid),
        )
        conn.commit()
    finally:
        conn.close()


def update_pet(pet_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE pets SET {cols} WHERE id = ?", (*fields.values(), pet_id))
        conn.commit()
    finally:
        conn.close()


def delete_pet(pet_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM pets WHERE id = ?", (pet_id,))
        conn.commit()
    finally:
        conn.close()


# ======================== 每日次数 ========================


def get_daily(uid: str, day: int) -> sqlite3.Row:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM pet_daily WHERE uid = ? AND day = ?", (uid, day)).fetchone()
        if row:
            return row
        conn.execute("INSERT OR IGNORE INTO pet_daily (uid, day) VALUES (?, ?)", (uid, day))
        conn.commit()
        return conn.execute("SELECT * FROM pet_daily WHERE uid = ? AND day = ?", (uid, day)).fetchone()
    finally:
        conn.close()


def increment_daily(uid: str, day: int, field: str) -> None:
    assert field in ("feeds", "walks", "trains")
    conn = get_conn()
    try:
        conn.execute(
            f"INSERT INTO pet_daily (uid, day, {field}) VALUES (?, ?, 1) "
            f"ON CONFLICT(uid, day) DO UPDATE SET {field} = {field} + 1",
            (uid, day),
        )
        conn.commit()
    finally:
        conn.close()
