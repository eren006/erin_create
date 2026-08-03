import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS auctions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    code TEXT NOT NULL,
    start_price INTEGER NOT NULL,
    min_increment INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    currency_name TEXT NOT NULL,
    start_time INTEGER NOT NULL,
    end_time INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    winner_uid TEXT,
    expire_hours REAL
);

CREATE TABLE IF NOT EXISTS auction_bids (
    auction_id INTEGER NOT NULL,
    uid TEXT NOT NULL,
    amount INTEGER NOT NULL,
    is_anon INTEGER NOT NULL DEFAULT 0,
    bid_time INTEGER NOT NULL,
    PRIMARY KEY (auction_id, uid)
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


MIGRATIONS = [
    "ALTER TABLE auctions ADD COLUMN expire_hours REAL",
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
