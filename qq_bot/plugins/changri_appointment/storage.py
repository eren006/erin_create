import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS group_pool (
    platform TEXT NOT NULL,
    group_openid TEXT NOT NULL,
    label TEXT NOT NULL,
    occupied INTEGER NOT NULL DEFAULT 0,
    occupied_by INTEGER,
    PRIMARY KEY (platform, group_openid)
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    initiator_uid TEXT NOT NULL,
    day TEXT NOT NULL,
    time_range TEXT NOT NULL,
    subtype TEXT NOT NULL,
    place TEXT,
    group_openid TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    last_reply_at INTEGER,
    last_reminded_at INTEGER
);

CREATE TABLE IF NOT EXISTS appointment_participants (
    appointment_id INTEGER NOT NULL,
    uid TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (appointment_id, uid)
);

CREATE TABLE IF NOT EXISTS session_stats (
    appointment_id INTEGER NOT NULL,
    uid TEXT NOT NULL,
    role_name TEXT NOT NULL,
    replies INTEGER NOT NULL DEFAULT 0,
    words INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (appointment_id, uid)
);

CREATE TABLE IF NOT EXISTS join_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER NOT NULL,
    applicant_uid TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL
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
        for stmt in (
            "ALTER TABLE appointments ADD COLUMN last_reply_at INTEGER",
            "ALTER TABLE appointments ADD COLUMN last_reminded_at INTEGER",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # 列已存在（旧库升级用）
        conn.commit()
    finally:
        conn.close()
