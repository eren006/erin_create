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

    trust            INTEGER NOT NULL DEFAULT 20,   -- 皇上的信任 0~100，与圣宠分开
    pending_scene    TEXT NOT NULL DEFAULT '',      -- 待定夺的场景 JSON，结算时清空
    recap_seen_day   INTEGER NOT NULL DEFAULT 0,    -- 看过「昨夜宫中」到第几夜
    last_audience_day INTEGER NOT NULL DEFAULT 0,   -- 上次侍寝或被召见是哪天
    last_promote_day INTEGER NOT NULL DEFAULT 0,
    dianxuan_quote   TEXT NOT NULL DEFAULT '',      -- 殿选时说过的第一句话，入宫周年时皇上会提起

    maid_offer       TEXT NOT NULL DEFAULT '',      -- 内务府摆出来的宫人候选 JSON
    maid_event       TEXT NOT NULL DEFAULT '',      -- 今天宫人来找的小事 JSON，结算时清空
    punish_ready_day INTEGER NOT NULL DEFAULT 0,    -- 发落宫人冷却：到这天才能再发落
    maid_punished_day INTEGER NOT NULL DEFAULT 0,   -- 自己宫里上次有宫人被发落是哪天

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
    last_bed_day     INTEGER NOT NULL DEFAULT 0,
    last_bed_pool    TEXT NOT NULL DEFAULT '[]'     -- 当晚递上去的绿头牌，「昨夜宫中」回放用
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
    kind        TEXT NOT NULL DEFAULT 'info',       -- info / good / bad / decree / edict(口谕)
    text        TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    is_night    INTEGER NOT NULL DEFAULT 0,         -- 夜间结算时产生的
    created_ts  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gazette (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         INTEGER NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'news',       -- news / bed / audience / decree / scandal / birth / death
    text        TEXT NOT NULL,
    is_night    INTEGER NOT NULL DEFAULT 0,
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

-- 宫人：玩家亲手挑、亲手赐名；名字全宫不重复（已故的也算）
CREATE TABLE IF NOT EXISTS maids (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id       INTEGER NOT NULL,                 -- 伺候的主子（consorts.id）
    name           TEXT NOT NULL UNIQUE,
    trait          TEXT NOT NULL,
    loyalty        INTEGER NOT NULL DEFAULT 60,
    backstory      TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'active',   -- active / dead / gone
    sick_until_day INTEGER NOT NULL DEFAULT 0,
    joined_day     INTEGER NOT NULL,
    left_day       INTEGER NOT NULL DEFAULT 0,
    left_reason    TEXT NOT NULL DEFAULT '',
    buried         INTEGER NOT NULL DEFAULT 0,
    seen_events    TEXT NOT NULL DEFAULT '[]',       -- 遇到过的小事，同一件不重复
    hid_burning    INTEGER NOT NULL DEFAULT 0,       -- 主子替她瞒下了烧纸的事（以后查案搜宫会用到）
    created_ts     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_maids_owner ON maids(owner_id, status);

CREATE TABLE IF NOT EXISTS daily_counters (
    consort_id  INTEGER NOT NULL,
    key         TEXT NOT NULL,
    day         INTEGER NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (consort_id, key, day)
);

CREATE TABLE IF NOT EXISTS letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id     INTEGER NOT NULL,
    to_id       INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    body        TEXT NOT NULL,
    silver      INTEGER NOT NULL DEFAULT 0,
    item_key    TEXT NOT NULL DEFAULT '',
    is_read     INTEGER NOT NULL DEFAULT 0,
    created_ts  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_letters_to      ON letters(to_id, id DESC);

-- 投诉举报：snapshot 存被举报内容的快照，管理员删信后仍留有记录
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL,
    target_id   INTEGER NOT NULL DEFAULT 0,
    letter_id   INTEGER NOT NULL DEFAULT 0,
    category    TEXT NOT NULL,
    reason      TEXT NOT NULL,
    snapshot    TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open',
    result      TEXT NOT NULL DEFAULT '',
    created_ts  INTEGER NOT NULL,
    handled_ts  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reports_status  ON reports(status, id DESC);
CREATE INDEX IF NOT EXISTS idx_consorts_rank    ON consorts(rank DESC, favor DESC);
CREATE INDEX IF NOT EXISTS idx_intrigues_status ON intrigues(status, day);
CREATE INDEX IF NOT EXISTS idx_messages_owner   ON messages(consort_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_gazette_day      ON gazette(day DESC, id DESC);
