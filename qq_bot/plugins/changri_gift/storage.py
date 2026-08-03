import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS preset_gifts (
    platform TEXT NOT NULL,
    name TEXT NOT NULL,
    desc TEXT NOT NULL DEFAULT '',
    usage_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, name)
);

CREATE TABLE IF NOT EXISTS gift_sightings (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    gift_name TEXT NOT NULL,
    first_seen_at INTEGER NOT NULL,
    PRIMARY KEY (platform, uid, gift_name)
);

CREATE TABLE IF NOT EXISTS gift_day_counts (
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    day TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    last_send_time INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, uid, day)
);

CREATE TABLE IF NOT EXISTS pending_gift (
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
