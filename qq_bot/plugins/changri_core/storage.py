import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    role_name TEXT NOT NULL,
    gid TEXT,
    PRIMARY KEY (platform, uid)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_role_name
    ON accounts (platform, role_name);

CREATE TABLE IF NOT EXISTS extra_accounts (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    main_uid TEXT NOT NULL,
    PRIMARY KEY (platform, uid)
);

CREATE TABLE IF NOT EXISTS admins (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    PRIMARY KEY (platform, uid)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS char_profiles (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    gender TEXT NOT NULL DEFAULT '女',
    age INTEGER NOT NULL DEFAULT 18,
    look TEXT NOT NULL DEFAULT '',
    bio TEXT NOT NULL DEFAULT '',
    look_updated_at INTEGER NOT NULL DEFAULT 0,
    bio_updated_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, uid)
);

CREATE TABLE IF NOT EXISTS places (
    platform TEXT NOT NULL,
    name TEXT NOT NULL,
    desc TEXT NOT NULL DEFAULT '',
    locked INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, name)
);

CREATE TABLE IF NOT EXISTS place_keys (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    place_name TEXT NOT NULL,
    PRIMARY KEY (platform, uid, place_name)
);

CREATE TABLE IF NOT EXISTS feature_user_blocklist (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    feature_key TEXT NOT NULL,
    PRIMARY KEY (platform, uid, feature_key)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    read_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications (platform, uid, read_at);

CREATE TABLE IF NOT EXISTS activated_groups (
    platform TEXT NOT NULL,
    group_openid TEXT NOT NULL,
    activated_at INTEGER NOT NULL,
    activated_by TEXT NOT NULL,
    PRIMARY KEY (platform, group_openid)
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
