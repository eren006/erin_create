CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT DEFAULT 'player',
    created_at    INTEGER DEFAULT 0,
    last_login    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS characters (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    spirit_root         TEXT NOT NULL,
    elements            TEXT DEFAULT '[]',
    realm_idx           INTEGER DEFAULT 0,
    exp                 INTEGER DEFAULT 0,
    energy              INTEGER DEFAULT 100,
    energy_updated      INTEGER DEFAULT 0,
    hp                  INTEGER DEFAULT 100,
    spirit_stones       INTEGER DEFAULT 100,
    breakthrough_bonus  INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS techniques (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    type           TEXT DEFAULT 'cultivation',
    realm_required INTEGER DEFAULT 0,
    power          INTEGER DEFAULT 0,
    exp_bonus      REAL DEFAULT 0.0,
    rarity         TEXT DEFAULT 'common'
);

CREATE TABLE IF NOT EXISTS char_techniques (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id     INTEGER NOT NULL,
    tech_id     INTEGER NOT NULL,
    learned_at  INTEGER DEFAULT 0,
    UNIQUE(char_id, tech_id)
);

CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    description  TEXT DEFAULT '',
    type         TEXT DEFAULT 'misc',
    effect_json  TEXT DEFAULT '{}',
    rarity       TEXT DEFAULT 'common',
    market_price INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS inventory (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id  INTEGER NOT NULL,
    item_id  INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1,
    UNIQUE(char_id, item_id)
);

CREATE TABLE IF NOT EXISTS forge_recipes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    result_type    TEXT DEFAULT 'weapon',
    base_effect    TEXT DEFAULT '{}',
    description     TEXT DEFAULT '',
    ingredients    TEXT DEFAULT '[]',
    success_rate   REAL DEFAULT 0.60,
    realm_required INTEGER DEFAULT 0,
    stone_cost     INTEGER DEFAULT 0,
    rarity         TEXT DEFAULT 'uncommon',
    is_active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS auctions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL,
    price       INTEGER DEFAULT 0,
    is_active   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pet_types (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    description  TEXT DEFAULT '',
    effect_json  TEXT DEFAULT '{}',
    rarity       TEXT DEFAULT 'common',
    market_price INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS char_pets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id     INTEGER NOT NULL,
    pet_type_id INTEGER NOT NULL,
    nickname    TEXT DEFAULT '',
    level       INTEGER DEFAULT 1,
    obtained_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_char_pets ON char_pets(char_id);

CREATE TABLE IF NOT EXISTS dungeons (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    realm_required INTEGER DEFAULT 0,
    energy_cost    INTEGER DEFAULT 20,
    reward_mult    REAL DEFAULT 1.0,
    tier           INTEGER DEFAULT 0,
    is_active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS alchemy_recipes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    result_item_id INTEGER NOT NULL,
    result_qty     INTEGER DEFAULT 1,
    ingredients    TEXT NOT NULL DEFAULT '[]',
    success_rate   REAL DEFAULT 0.80,
    realm_required INTEGER DEFAULT 0,
    is_active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS monsters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    description  TEXT DEFAULT '',
    realm_min    INTEGER DEFAULT 0,
    realm_max    INTEGER DEFAULT 99,
    hp           INTEGER DEFAULT 100,
    attack       INTEGER DEFAULT 15,
    defense      INTEGER DEFAULT 5,
    exp_reward   INTEGER DEFAULT 50,
    stone_reward INTEGER DEFAULT 20,
    drop_json    TEXT DEFAULT '[]',
    is_active    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS explore_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    type         TEXT DEFAULT 'nothing',
    realm_min    INTEGER DEFAULT 0,
    realm_max    INTEGER DEFAULT 99,
    rewards_json TEXT DEFAULT '{}',
    weight       INTEGER DEFAULT 10,
    is_active    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS char_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id    INTEGER NOT NULL,
    type       TEXT DEFAULT 'info',
    content    TEXT NOT NULL,
    created_at INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS encounters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id      INTEGER NOT NULL,
    age          INTEGER DEFAULT 0,
    kind         TEXT DEFAULT 'instant',
    title        TEXT NOT NULL,
    narrative    TEXT DEFAULT '',
    status       TEXT DEFAULT 'pending',
    options_json TEXT DEFAULT '[]',
    result_text  TEXT DEFAULT '',
    created_at   INTEGER DEFAULT 0,
    resolved_at  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_enc_char ON encounters(char_id, status);

CREATE TABLE IF NOT EXISTS relationships (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    char_a      INTEGER NOT NULL,
    char_b      INTEGER NOT NULL,
    affinity    INTEGER DEFAULT 0,
    is_partner  INTEGER DEFAULT 0,
    is_daolv    INTEGER DEFAULT 0,
    last_shuangxiu INTEGER DEFAULT 0,
    updated_at  INTEGER DEFAULT 0,
    UNIQUE(char_a, char_b)
);
CREATE INDEX IF NOT EXISTS idx_rel_a ON relationships(char_a);
CREATE INDEX IF NOT EXISTS idx_rel_b ON relationships(char_b);

CREATE TABLE IF NOT EXISTS interactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_char   INTEGER NOT NULL,
    to_char     INTEGER NOT NULL,
    type        TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    payload     TEXT DEFAULT '{}',
    created_at  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_inter_to ON interactions(to_char, status);

CREATE TABLE IF NOT EXISTS daily_counters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id     INTEGER NOT NULL,
    key         TEXT NOT NULL,
    day         TEXT NOT NULL,
    count       INTEGER DEFAULT 0,
    UNIQUE(char_id, key, day)
);

CREATE TABLE IF NOT EXISTS world_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    description       TEXT DEFAULT '',
    icon              TEXT DEFAULT '👹',
    boss_hp_total     INTEGER DEFAULT 100000,
    boss_hp_remaining INTEGER DEFAULT 100000,
    is_active         INTEGER DEFAULT 1,
    ends_at           INTEGER DEFAULT 0,
    created_at        INTEGER DEFAULT 0,
    hit_drops_json    TEXT DEFAULT '[]',
    clear_drops_json  TEXT DEFAULT '[]',
    clear_bonus_stones INTEGER DEFAULT 500,
    clear_bonus_lingfu INTEGER DEFAULT 20
);

CREATE TABLE IF NOT EXISTS event_hits (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id  INTEGER NOT NULL,
    char_id   INTEGER NOT NULL,
    damage    INTEGER DEFAULT 0,
    hits      INTEGER DEFAULT 0,
    UNIQUE(event_id, char_id)
);

CREATE TABLE IF NOT EXISTS gacha_pools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    icon        TEXT DEFAULT '🎴',
    cost        INTEGER DEFAULT 10,
    pity_max    INTEGER DEFAULT 90,
    is_active   INTEGER DEFAULT 1,
    created_at  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gacha_pool_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id   INTEGER NOT NULL,
    item_type TEXT DEFAULT 'item',
    item_id   INTEGER DEFAULT 0,
    item_name TEXT DEFAULT '',
    rarity    TEXT DEFAULT 'common',
    weight    INTEGER DEFAULT 100,
    is_active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_gpi ON gacha_pool_items(pool_id, is_active);

CREATE TABLE IF NOT EXISTS gacha_records (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id    INTEGER NOT NULL,
    pool_id    INTEGER NOT NULL,
    item_type  TEXT DEFAULT '',
    item_id    INTEGER DEFAULT 0,
    item_name  TEXT DEFAULT '',
    rarity     TEXT DEFAULT 'common',
    created_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_gr ON gacha_records(char_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    emblem      TEXT DEFAULT '🏯',
    leader_id   INTEGER NOT NULL,
    created_at  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sect_members (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sect_id      INTEGER NOT NULL,
    char_id      INTEGER UNIQUE NOT NULL,
    rank         TEXT DEFAULT 'member',
    joined_at    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sect_mbr ON sect_members(sect_id);
CREATE INDEX IF NOT EXISTS idx_sect_char ON sect_members(char_id);

CREATE TABLE IF NOT EXISTS sect_invites (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sect_id   INTEGER NOT NULL,
    from_char INTEGER NOT NULL,
    to_char   INTEGER NOT NULL,
    status    TEXT DEFAULT 'pending',
    created_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sect_inv ON sect_invites(to_char, status);

CREATE TABLE IF NOT EXISTS sect_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sect_id    INTEGER NOT NULL,
    char_id    INTEGER NOT NULL,
    content    TEXT NOT NULL,
    created_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sect_post ON sect_posts(sect_id, created_at DESC);

CREATE TABLE IF NOT EXISTS discipleships (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    shifu_id     INTEGER NOT NULL,
    tudi_id      INTEGER UNIQUE NOT NULL,
    status       TEXT DEFAULT 'active',
    formed_at    INTEGER DEFAULT 0,
    graduated_at INTEGER DEFAULT 0,
    last_teach   INTEGER DEFAULT 0,
    last_invite  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ds_shifu ON discipleships(shifu_id);

CREATE TABLE IF NOT EXISTS achievement_defs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    key            TEXT UNIQUE NOT NULL,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    category       TEXT DEFAULT '修炼',
    icon           TEXT DEFAULT '🏆',
    condition_json TEXT DEFAULT '{}',
    reward_stones  INTEGER DEFAULT 0,
    reward_exp     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS char_achievements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id      INTEGER NOT NULL,
    ach_key      TEXT NOT NULL,
    progress     INTEGER DEFAULT 0,
    completed    INTEGER DEFAULT 0,
    completed_at INTEGER DEFAULT 0,
    UNIQUE(char_id, ach_key)
);
CREATE INDEX IF NOT EXISTS idx_char_ach ON char_achievements(char_id);

CREATE TABLE IF NOT EXISTS world_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT DEFAULT 'info',
    content    TEXT NOT NULL,
    created_at INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS char_perks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id      INTEGER NOT NULL,
    perk_key     TEXT NOT NULL,
    value        REAL DEFAULT 0,
    realm_earned TEXT DEFAULT '',
    earned_at    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_perks_char ON char_perks(char_id);

CREATE TABLE IF NOT EXISTS offspring (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_a    INTEGER NOT NULL,
    parent_b    INTEGER NOT NULL,
    name        TEXT DEFAULT '无名',
    spirit_root TEXT DEFAULT '五灵根',
    elements    TEXT DEFAULT '[]',
    conceived_at INTEGER DEFAULT 0,
    matures_at   INTEGER DEFAULT 0,
    is_matured   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_offspring ON offspring(parent_a, parent_b);

CREATE TABLE IF NOT EXISTS invite_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    created_at  INTEGER DEFAULT 0,
    used_by     INTEGER DEFAULT NULL,
    used_at     INTEGER DEFAULT 0,
    note        TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_invite_code ON invite_codes(code);

CREATE TABLE IF NOT EXISTS site_config (
    key   TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_chars_rank   ON characters(realm_idx DESC, exp DESC);
CREATE INDEX IF NOT EXISTS idx_char_logs    ON char_logs(char_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inventory    ON inventory(char_id);
CREATE INDEX IF NOT EXISTS idx_char_tech    ON char_techniques(char_id);
