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

CREATE TABLE IF NOT EXISTS site_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tenants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    username            TEXT UNIQUE NOT NULL,
    view_password_hash  TEXT NOT NULL,
    admin_password_hash TEXT NOT NULL,
    api_token           TEXT UNIQUE NOT NULL,
    display_name        TEXT DEFAULT '',
    created_at          INTEGER DEFAULT 0
);

-- 弧/档期表：租户内可有多个弧，机器人数据写入 is_current=1 的弧
CREATE TABLE IF NOT EXISTS shows (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           INTEGER NOT NULL,
    name                TEXT NOT NULL DEFAULT '第一弧',
    description         TEXT DEFAULT '',
    is_current          INTEGER DEFAULT 0,
    public_view_enabled INTEGER DEFAULT 0,
    public_token        TEXT UNIQUE,
    created_at          INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_shows_tenant ON shows(tenant_id);

-- tenant_id / show_id 列通过 _migrate() 在运行时添加到现有表
