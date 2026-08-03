import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    read_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_letters_recipient ON letters (platform, to_uid, read_at);

CREATE TABLE IF NOT EXISTS letter_effects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    target_uid TEXT NOT NULL,
    item_type TEXT NOT NULL,
    applier_uid TEXT NOT NULL,
    applied_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_letter_effects_target ON letter_effects (platform, target_uid);

CREATE TABLE IF NOT EXISTS pending_quill_letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    applier_uid TEXT NOT NULL,
    original_from_uid TEXT NOT NULL,
    original_to_uid TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS letter_day_counts (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    day TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    last_send_time INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, uid, day)
);

CREATE TABLE IF NOT EXISTS sms_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    signature TEXT,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    read_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sms_recipient ON sms_messages (platform, to_uid, read_at);

CREATE TABLE IF NOT EXISTS pending_sms (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL,
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
        conn.commit()
    finally:
        conn.close()
