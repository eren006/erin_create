import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "yuca_calendar.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    name TEXT NOT NULL,
    start_year INTEGER NOT NULL,
    start_month INTEGER NOT NULL,
    start_day INTEGER NOT NULL,
    end_year INTEGER NOT NULL,
    end_month INTEGER NOT NULL,
    end_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT '未知',
    character TEXT NOT NULL DEFAULT '未知',
    orientation TEXT NOT NULL DEFAULT '未知',
    theme TEXT NOT NULL DEFAULT '未知',
    role_name TEXT NOT NULL DEFAULT '未知',
    role_type TEXT NOT NULL DEFAULT '未知',
    gender TEXT NOT NULL DEFAULT '未知',
    outcome TEXT NOT NULL DEFAULT '未知',
    reminded_start INTEGER NOT NULL DEFAULT 0,
    reminded_end INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (uid, name)
);
CREATE INDEX IF NOT EXISTS idx_schedules_uid ON schedules (uid);
CREATE INDEX IF NOT EXISTS idx_schedules_reminder ON schedules (end_year, end_month, end_day, reminded_end);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    name TEXT NOT NULL,
    start_year INTEGER NOT NULL,
    start_month INTEGER NOT NULL,
    start_day INTEGER NOT NULL,
    end_year INTEGER NOT NULL,
    end_month INTEGER NOT NULL,
    end_day INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE (uid, name)
);
CREATE INDEX IF NOT EXISTS idx_submissions_uid ON submissions (uid);
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
        try:
            conn.execute("ALTER TABLE schedules ADD COLUMN he_partner_qq TEXT")
        except sqlite3.OperationalError:
            pass  # 列已存在（旧库升级用）
        conn.commit()
    finally:
        conn.close()
