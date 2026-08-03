import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    platform TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    desc TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL,
    max_uses INTEGER,
    can_resell INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (platform, code)
);

CREATE TABLE IF NOT EXISTS inventory_stacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    uid TEXT NOT NULL,
    code TEXT NOT NULL,
    count INTEGER NOT NULL,
    remaining_uses INTEGER,
    current_durability INTEGER
);
CREATE INDEX IF NOT EXISTS idx_inventory_owner ON inventory_stacks (platform, uid, code);

CREATE TABLE IF NOT EXISTS shop_listings (
    platform TEXT NOT NULL,
    code TEXT NOT NULL,
    price INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    currency_name TEXT NOT NULL,
    PRIMARY KEY (platform, code)
);

CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    seller_uid TEXT NOT NULL,
    code TEXT NOT NULL,
    count INTEGER NOT NULL,
    remaining_uses INTEGER,
    current_durability INTEGER,
    price INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    currency_name TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


MIGRATIONS = [
    "ALTER TABLE inventory_stacks ADD COLUMN expires_at INTEGER",
]


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        for migration in MIGRATIONS:
            try:
                conn.execute(migration)
                conn.commit()
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
    finally:
        conn.close()
