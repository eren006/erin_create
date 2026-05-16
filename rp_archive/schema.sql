CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    group_id    TEXT,
    platform    TEXT,
    game_day    TEXT,
    game_time   TEXT,
    place       TEXT,
    subtype     TEXT,
    participants TEXT DEFAULT '[]',
    start_ts    INTEGER DEFAULT 0,
    end_ts      INTEGER DEFAULT 0,
    forced      INTEGER DEFAULT 0,
    total_replies INTEGER DEFAULT 0,
    total_words   INTEGER DEFAULT 0,
    stats       TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS rp_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    role_name   TEXT,
    content     TEXT,
    seq         INTEGER DEFAULT 0,
    timestamp   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS extra_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    type        TEXT,
    from_role   TEXT,
    to_role     TEXT,
    content     TEXT,
    extra_info  TEXT DEFAULT '{}',
    timestamp   INTEGER DEFAULT 0,
    game_day    TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_game_day ON sessions(game_day);
CREATE INDEX IF NOT EXISTS idx_rp_session ON rp_entries(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_session ON extra_events(session_id);

CREATE TABLE IF NOT EXISTS players (
    qq          TEXT PRIMARY KEY,
    role_name   TEXT NOT NULL DEFAULT '',
    show_name   TEXT DEFAULT '',
    sessions_count INTEGER DEFAULT 0,
    total_replies  INTEGER DEFAULT 0,
    total_words    INTEGER DEFAULT 0,
    last_updated   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_players_role ON players(role_name);
