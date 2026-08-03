CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT DEFAULT 'player',
    created_ts    INTEGER DEFAULT 0,
    last_login    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS survivors (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER UNIQUE,
    name               TEXT NOT NULL DEFAULT '',
    specialization     TEXT DEFAULT '',
    health             INTEGER DEFAULT 100,
    energy             INTEGER DEFAULT 100,
    energy_updated     INTEGER DEFAULT 0,
    status             TEXT DEFAULT 'normal',
    contribution       INTEGER DEFAULT 0,
    wallet             INTEGER DEFAULT 0,
    weapon_level       INTEGER DEFAULT 0,
    gear_level         INTEGER DEFAULT 0,
    weapon_type        TEXT DEFAULT '',
    weapon_durability     INTEGER DEFAULT 0,
    weapon_max_durability INTEGER DEFAULT 0,
    stat_intelligence  INTEGER DEFAULT 3,
    stat_strength      INTEGER DEFAULT 3,
    stat_agility       INTEGER DEFAULT 3,
    stat_education     INTEGER DEFAULT 3,
    stat_willpower     INTEGER DEFAULT 3,
    stat_appearance    INTEGER DEFAULT 3,
    stat_luck          INTEGER DEFAULT 3,
    respawn_count      INTEGER DEFAULT 0,
    illness            TEXT DEFAULT '',
    illness_started_ts INTEGER DEFAULT 0,
    room_tier          INTEGER DEFAULT 0,
    age_years          INTEGER DEFAULT 20,
    age_updated_ts     INTEGER DEFAULT 0,
    birth_rights       INTEGER DEFAULT 0,
    happiness          INTEGER DEFAULT 70,
    is_depressed       INTEGER DEFAULT 0,
    infected           INTEGER DEFAULT 0,
    infected_since_day INTEGER DEFAULT 0,
    created_ts         INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS alert_claims (
    alert_key   TEXT PRIMARY KEY,
    claimed_by  TEXT,
    claimed_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS base_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    day_count     INTEGER DEFAULT 1,
    season        TEXT DEFAULT '初春',
    morale        INTEGER DEFAULT 60,
    last_tick_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS resources (
    key     TEXT PRIMARY KEY,
    amount  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS buildings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_index  INTEGER UNIQUE NOT NULL,
    type        TEXT NOT NULL DEFAULT 'empty',
    level       INTEGER DEFAULT 0,
    hp          INTEGER DEFAULT 0,
    max_hp      INTEGER DEFAULT 0,
    crop_type   TEXT DEFAULT '',
    ready_ts    INTEGER DEFAULT 0,
    built_by    INTEGER DEFAULT 0,
    updated_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day_count   INTEGER,
    kind        TEXT,
    detail      TEXT,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS action_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    survivor_id   INTEGER,
    survivor_name TEXT,
    action        TEXT,
    detail        TEXT,
    created_ts    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS daily_counters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    survivor_id INTEGER NOT NULL,
    key         TEXT NOT NULL,
    day         TEXT NOT NULL,
    count       INTEGER DEFAULT 0,
    UNIQUE(survivor_id, key, day)
);

CREATE TABLE IF NOT EXISTS relationships (
    a_id        INTEGER NOT NULL,
    b_id        INTEGER NOT NULL,
    affinity    INTEGER DEFAULT 0,
    is_couple   INTEGER DEFAULT 0,
    proposed_by INTEGER DEFAULT 0,
    shared_room INTEGER DEFAULT 0,
    updated_ts  INTEGER DEFAULT 0,
    PRIMARY KEY (a_id, b_id)
);

CREATE TABLE IF NOT EXISTS birth_invites (
    code             TEXT PRIMARY KEY,
    parent_a_id      INTEGER NOT NULL,
    parent_b_id      INTEGER NOT NULL,
    created_ts       INTEGER DEFAULT 0,
    used             INTEGER DEFAULT 0,
    child_survivor_id INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS survivor_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id   INTEGER NOT NULL,
    item_type  TEXT NOT NULL,
    item_key   TEXT NOT NULL,
    status     TEXT DEFAULT 'inventory',
    created_ts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS market_listings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    price     INTEGER NOT NULL,
    listed_ts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mail (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id               INTEGER NOT NULL,
    to_id                 INTEGER NOT NULL,
    note                  TEXT DEFAULT '',
    wallet_amount         INTEGER DEFAULT 0,
    weapon_level          INTEGER DEFAULT 0,
    weapon_type           TEXT DEFAULT '',
    weapon_durability     INTEGER DEFAULT 0,
    weapon_max_durability INTEGER DEFAULT 0,
    gear_level            INTEGER DEFAULT 0,
    is_read               INTEGER DEFAULT 0,
    claimed               INTEGER DEFAULT 0,
    created_ts            INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mail_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_id          INTEGER NOT NULL,
    survivor_item_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS expeditions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    member_a_id    INTEGER NOT NULL,
    member_b_id    INTEGER NOT NULL,
    map_key        TEXT NOT NULL DEFAULT '',
    monster_key    TEXT NOT NULL DEFAULT '',
    monster_hp     INTEGER DEFAULT 0,
    monster_max_hp INTEGER DEFAULT 0,
    status         TEXT DEFAULT 'inviting',
    round_number   INTEGER DEFAULT 0,
    action_a       TEXT DEFAULT '',
    action_b       TEXT DEFAULT '',
    created_ts     INTEGER DEFAULT 0,
    updated_ts     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS expedition_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    expedition_id INTEGER NOT NULL,
    round_number  INTEGER,
    text          TEXT,
    created_ts    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS map_progress (
    map_key  TEXT PRIMARY KEY,
    progress INTEGER DEFAULT 0,
    unlocked INTEGER DEFAULT 0
);
