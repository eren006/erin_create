import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    group_openid TEXT NOT NULL,
    trigger_at INTEGER NOT NULL,
    content TEXT NOT NULL,
    repeat TEXT NOT NULL DEFAULT 'none',
    created_at INTEGER NOT NULL,
    fail_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reminders_trigger_at ON reminders (trigger_at);

CREATE TABLE IF NOT EXISTS last_fired (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    group_openid TEXT NOT NULL,
    content TEXT NOT NULL,
    fired_at INTEGER NOT NULL,
    PRIMARY KEY (platform, uid)
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
        try:
            conn.execute("ALTER TABLE reminders ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 列已存在（旧库升级用，新库建表时已经带了这一列）
        conn.commit()
    finally:
        conn.close()
