import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changri.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS forum_posts (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    author_uid TEXT NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS forum_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    author_uid TEXT NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    quote_floor INTEGER,
    quote_content TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forum_replies_post ON forum_replies (post_id);

CREATE TABLE IF NOT EXISTS forum_post_votes (
    post_id TEXT NOT NULL,
    voter_name TEXT NOT NULL,
    vote_type TEXT NOT NULL,
    PRIMARY KEY (post_id, voter_name)
);

CREATE TABLE IF NOT EXISTS forum_reply_votes (
    reply_id INTEGER NOT NULL,
    voter_name TEXT NOT NULL,
    vote_type TEXT NOT NULL,
    PRIMARY KEY (reply_id, voter_name)
);

CREATE TABLE IF NOT EXISTS relationship_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    uid_lo TEXT NOT NULL,
    uid_hi TEXT NOT NULL,
    initiator_uid TEXT NOT NULL,
    initiator_name TEXT NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    is_mandatory INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    UNIQUE (platform, uid_lo, uid_hi)
);

CREATE TABLE IF NOT EXISTS relationship_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id INTEGER NOT NULL,
    from_uid TEXT NOT NULL,
    from_name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_relationship_details_line ON relationship_details (line_id);
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
