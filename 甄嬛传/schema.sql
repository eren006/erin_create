-- 甄嬛传·紫禁城 数据库结构（SQLite）
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    lethal_ready_day INTEGER NOT NULL DEFAULT 0,
    created_ts    INTEGER NOT NULL
);

-- 玩家和 NPC 妃嫔共用一张表：user_id 为空、npc_key 非空的是 NPC
CREATE TABLE IF NOT EXISTS consorts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER UNIQUE,
    npc_key          TEXT UNIQUE,
    surname          TEXT NOT NULL,
    given            TEXT NOT NULL,
    title            TEXT NOT NULL DEFAULT '',      -- 封号，单字
    rank             INTEGER NOT NULL DEFAULT 0,    -- 0=秀女 1=官女子 ... 8=皇贵妃 9=皇后
    rank_since_day   INTEGER NOT NULL DEFAULT 0,
    palace           TEXT NOT NULL DEFAULT '',
    family           TEXT NOT NULL DEFAULT '',
    personality      TEXT NOT NULL DEFAULT '',

    appearance       INTEGER NOT NULL DEFAULT 40,   -- 容貌
    talent           INTEGER NOT NULL DEFAULT 30,   -- 才艺
    scheme           INTEGER NOT NULL DEFAULT 30,   -- 心计
    virtue           INTEGER NOT NULL DEFAULT 40,   -- 德行
    health           INTEGER NOT NULL DEFAULT 70,   -- 体质

    favor            INTEGER NOT NULL DEFAULT 0,    -- 圣宠
    silver           INTEGER NOT NULL DEFAULT 0,
    energy           INTEGER NOT NULL DEFAULT 5,

    status           TEXT NOT NULL DEFAULT 'xiunv', -- xiunv / normal / confined(禁足) / cold(冷宫) / dead(已故)
    status_until_day INTEGER NOT NULL DEFAULT 0,
    rank_before_cold INTEGER NOT NULL DEFAULT 0,
    pregnant_since   INTEGER NOT NULL DEFAULT 0,    -- 0=未有孕，否则为有孕那天

    arts             TEXT NOT NULL DEFAULT '{}',    -- {"琴": 3, ...} 各才艺修习次数
    secret           TEXT NOT NULL DEFAULT 'none',
    secret_revealed  INTEGER NOT NULL DEFAULT 0,
    eyes_until_day   INTEGER NOT NULL DEFAULT 0,    -- 眼线有效到哪天（含）
    seek_bonus       INTEGER NOT NULL DEFAULT 0,    -- 今晚翻牌加成，结算后清零
    greet_day        INTEGER NOT NULL DEFAULT 0,
    missed_greet     INTEGER NOT NULL DEFAULT 0,
    entered_day      INTEGER NOT NULL DEFAULT 0,    -- 殿选中选那天
    bedded_count     INTEGER NOT NULL DEFAULT 0,
    dianxuan_score   INTEGER NOT NULL DEFAULT 0,

    age_months       INTEGER NOT NULL DEFAULT 240,
    poisoned_day     INTEGER NOT NULL DEFAULT 0,
    poison_treatment INTEGER NOT NULL DEFAULT 0,      -- 0=没请太医 1=请了
    protected_until_day INTEGER NOT NULL DEFAULT 0,
    death_day        INTEGER NOT NULL DEFAULT 0,
    death_reason     TEXT NOT NULL DEFAULT '',
    archived_user_id INTEGER,

    aggression       REAL NOT NULL DEFAULT 0,       -- 仅 NPC：每晚出手概率
    intro            TEXT NOT NULL DEFAULT '',
    created_ts       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS game_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    day              INTEGER NOT NULL DEFAULT 1,
    last_settle_date TEXT NOT NULL DEFAULT '',
    emperor_mood     TEXT NOT NULL DEFAULT '平和',
    emperor_pref     TEXT NOT NULL DEFAULT '琴',
    last_bed_id      INTEGER NOT NULL DEFAULT 0,
    last_bed_day     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS intrigues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day          INTEGER NOT NULL,
    attacker_id  INTEGER NOT NULL,
    target_id    INTEGER NOT NULL,
    method       TEXT NOT NULL,
    silver_paid  INTEGER NOT NULL DEFAULT 0,
    item_used    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending / done / cancelled
    result       TEXT NOT NULL DEFAULT '',          -- success / caught / fizzle / void
    created_ts   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    consort_id  INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'info',       -- info / good / bad / decree
    text        TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    created_ts  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gazette (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         INTEGER NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'news',       -- news / bed / decree / scandal / birth
    text        TEXT NOT NULL,
    created_ts  INTEGER NOT NULL
);

-- 两人关系，a_id < b_id
CREATE TABLE IF NOT EXISTS relations (
    a_id        INTEGER NOT NULL,
    b_id        INTEGER NOT NULL,
    affinity    INTEGER NOT NULL DEFAULT 0,
    sister      INTEGER NOT NULL DEFAULT 0,
    invite_from INTEGER NOT NULL DEFAULT 0,         -- 谁发起了结拜邀请，0=无
    PRIMARY KEY (a_id, b_id)
);

CREATE TABLE IF NOT EXISTS known_secrets (
    knower_id   INTEGER NOT NULL,
    target_id   INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    PRIMARY KEY (knower_id, target_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    consort_id  INTEGER NOT NULL,
    item_key    TEXT NOT NULL,
    qty         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (consort_id, item_key)
);

CREATE TABLE IF NOT EXISTS heirs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mother_id   INTEGER NOT NULL,
    gender      TEXT NOT NULL,                      -- 皇子 / 公主
    ordinal     INTEGER NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    born_day    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_counters (
    consort_id  INTEGER NOT NULL,
    key         TEXT NOT NULL,
    day         INTEGER NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (consort_id, key, day)
);

CREATE INDEX IF NOT EXISTS idx_consorts_rank    ON consorts(rank DESC, favor DESC);
CREATE INDEX IF NOT EXISTS idx_intrigues_status ON intrigues(status, day);
CREATE INDEX IF NOT EXISTS idx_messages_owner   ON messages(consort_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_gazette_day      ON gazette(day DESC, id DESC);
