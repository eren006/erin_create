CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    qq            TEXT NOT NULL,
    role          TEXT DEFAULT 'player',
    status        TEXT DEFAULT 'pending',
    created_ts    INTEGER DEFAULT 0,
    last_login    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS characters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    species         TEXT NOT NULL,
    bio             TEXT DEFAULT '',
    stage_index     INTEGER DEFAULT 0,
    yao_power       INTEGER DEFAULT 0,
    humanoid_value  INTEGER DEFAULT 100,
    humanity        INTEGER DEFAULT 50,
    final_form      TEXT DEFAULT NULL,
    created_ts      INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER,
    target_type TEXT DEFAULT '',
    target_id   INTEGER,
    action      TEXT NOT NULL,
    detail      TEXT DEFAULT '',
    created_ts  INTEGER DEFAULT 0
);

-- ── 宗门/师徒 ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    leader_id   INTEGER NOT NULL,
    description TEXT DEFAULT '',
    created_ts  INTEGER DEFAULT 0,
    FOREIGN KEY (leader_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS clan_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id     INTEGER NOT NULL,
    char_id     INTEGER NOT NULL UNIQUE,
    rank        TEXT DEFAULT 'member',
    joined_ts   INTEGER DEFAULT 0,
    FOREIGN KEY (clan_id) REFERENCES clans(id),
    FOREIGN KEY (char_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS mentorships (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    master_id     INTEGER NOT NULL,
    disciple_id   INTEGER NOT NULL UNIQUE,
    created_ts    INTEGER DEFAULT 0,
    FOREIGN KEY (master_id) REFERENCES characters(id),
    FOREIGN KEY (disciple_id) REFERENCES characters(id)
);

-- ── 通用基建:邀请码 / 礼包码 / 站内信 / 快照 / 成就 / 每日计数器 ──────────────────

CREATE TABLE IF NOT EXISTS invite_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    max_uses    INTEGER DEFAULT 1,
    used_count  INTEGER DEFAULT 0,
    expires_ts  INTEGER DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gift_codes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT UNIQUE NOT NULL,
    reward_json  TEXT DEFAULT '{}',
    max_uses     INTEGER DEFAULT 1,
    used_count   INTEGER DEFAULT 0,
    expires_ts   INTEGER DEFAULT 0,
    created_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gift_code_uses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gift_code_id  INTEGER NOT NULL,
    char_id       INTEGER NOT NULL,
    used_ts       INTEGER DEFAULT 0,
    UNIQUE(gift_code_id, char_id),
    FOREIGN KEY (gift_code_id) REFERENCES gift_codes(id),
    FOREIGN KEY (char_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS mail (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id          INTEGER NOT NULL,
    from_label       TEXT DEFAULT '系统',
    subject          TEXT NOT NULL,
    body             TEXT DEFAULT '',
    attachment_json  TEXT DEFAULT NULL,
    claimed          INTEGER DEFAULT 0,
    read             INTEGER DEFAULT 0,
    created_ts       INTEGER DEFAULT 0,
    FOREIGN KEY (char_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS char_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    stage_index     INTEGER DEFAULT 0,
    yao_power       INTEGER DEFAULT 0,
    humanoid_value  INTEGER DEFAULT 0,
    humanity        INTEGER DEFAULT 0,
    created_ts      INTEGER DEFAULT 0,
    FOREIGN KEY (char_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS achievement_defs (
    key            TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    condition_json TEXT DEFAULT '{}',
    reward_json    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS char_achievements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    achieved_ts     INTEGER DEFAULT 0,
    UNIQUE(char_id, achievement_key),
    FOREIGN KEY (char_id) REFERENCES characters(id),
    FOREIGN KEY (achievement_key) REFERENCES achievement_defs(key)
);

CREATE TABLE IF NOT EXISTS daily_counters (
    char_id      INTEGER NOT NULL,
    counter_key  TEXT NOT NULL,
    day          TEXT NOT NULL,
    count        INTEGER DEFAULT 0,
    PRIMARY KEY (char_id, counter_key, day)
);
