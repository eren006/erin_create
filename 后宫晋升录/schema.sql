-- 后宫晋升录 · 数据库结构
-- SQLite

PRAGMA foreign_keys = ON;

-- ============================================================
-- 玩家妃嫔主表
-- ============================================================
CREATE TABLE IF NOT EXISTS concubines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    qq              TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    rank            TEXT NOT NULL DEFAULT '秀女',
    rank_order      INTEGER NOT NULL DEFAULT 0,     -- 0=秀女 1=答应 ... 8=皇后

    family_tier     INTEGER NOT NULL DEFAULT 1,
    family_type     TEXT NOT NULL DEFAULT '',
    personality     TEXT NOT NULL DEFAULT '',

    age             INTEGER NOT NULL DEFAULT 14,

    appearance      REAL NOT NULL DEFAULT 50,
    talent          REAL NOT NULL DEFAULT 20,
    scheme          REAL NOT NULL DEFAULT 20,
    health          REAL NOT NULL DEFAULT 70,
    virtue          REAL NOT NULL DEFAULT 30,

    sacred_favor    INTEGER NOT NULL DEFAULT 0,
    love            REAL NOT NULL DEFAULT 0,
    prestige        REAL NOT NULL DEFAULT 0,
    silver          INTEGER NOT NULL DEFAULT 0,

    stamina         INTEGER NOT NULL DEFAULT 100,
    stamina_max     INTEGER NOT NULL DEFAULT 100,

    status          TEXT NOT NULL DEFAULT 'normal',
    -- normal / pregnant / bedridden / eliminated / dead

    pregnant_day    INTEGER NOT NULL DEFAULT 0,

    last_attend_day INTEGER NOT NULL DEFAULT 0,
    greet_day       INTEGER NOT NULL DEFAULT 0,
    greet_count     INTEGER NOT NULL DEFAULT 0,
    last_study_day  INTEGER NOT NULL DEFAULT 0,
    study_type      TEXT NOT NULL DEFAULT '',
    last_stroll_day INTEGER NOT NULL DEFAULT 0,
    last_spy_day    INTEGER NOT NULL DEFAULT 0,

    love_stage      TEXT NOT NULL DEFAULT '陌路',
    -- 陌路/有印象/垂青/心悦/专宠/执念

    low_love_days   INTEGER NOT NULL DEFAULT 0,
    bedridden_days  INTEGER NOT NULL DEFAULT 0,
    prestige_warning INTEGER NOT NULL DEFAULT 0,

    last_apply_day  INTEGER NOT NULL DEFAULT 0,
    mastered_arts   TEXT NOT NULL DEFAULT '',
    items_held      TEXT NOT NULL DEFAULT '',
    servants        TEXT NOT NULL DEFAULT '',
    secret_revealed INTEGER NOT NULL DEFAULT 0,

    attended_today  INTEGER NOT NULL DEFAULT 0,
    festival_score  REAL NOT NULL DEFAULT 0,

    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ============================================================
-- NPC 妃嫔表
-- ============================================================
CREATE TABLE IF NOT EXISTS npc_concubines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL DEFAULT '',
    rank            TEXT NOT NULL,
    rank_order      INTEGER NOT NULL DEFAULT 0,

    age             INTEGER NOT NULL DEFAULT 20,
    appearance      REAL NOT NULL DEFAULT 60,
    talent          REAL NOT NULL DEFAULT 50,
    scheme          REAL NOT NULL DEFAULT 50,
    health          REAL NOT NULL DEFAULT 70,
    virtue          REAL NOT NULL DEFAULT 40,

    love            REAL NOT NULL DEFAULT 50,
    prestige        REAL NOT NULL DEFAULT 100,
    sacred_favor    INTEGER NOT NULL DEFAULT 0,

    behavior        TEXT NOT NULL DEFAULT 'defensive',
    -- defensive / love_type / aggressive / heir_type / talent_type / schemer / follower

    attend_priority INTEGER NOT NULL DEFAULT 5,
    intrigue_chance INTEGER NOT NULL DEFAULT 0,

    is_alive        INTEGER NOT NULL DEFAULT 1,
    pregnant_day    INTEGER NOT NULL DEFAULT 0,
    sons_count      INTEGER NOT NULL DEFAULT 0,

    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ============================================================
-- 子嗣表
-- ============================================================
CREATE TABLE IF NOT EXISTS heirs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    mother_qq       TEXT,
    mother_npc_id   INTEGER,
    mother_name     TEXT NOT NULL,

    name            TEXT NOT NULL DEFAULT '',
    gender          TEXT NOT NULL,              -- 皇子 / 公主
    age             INTEGER NOT NULL DEFAULT 0,

    talent          REAL NOT NULL DEFAULT 20,
    prestige_score  REAL NOT NULL DEFAULT 0,
    support_silver  INTEGER NOT NULL DEFAULT 0,

    health          REAL NOT NULL DEFAULT 80,
    is_alive        INTEGER NOT NULL DEFAULT 1,

    stage           TEXT NOT NULL DEFAULT '幼年',
    -- 幼年(0-3) / 童年(4-10) / 少年(11-15) / 成年(16+)

    succession_rank INTEGER DEFAULT NULL,

    born_day        INTEGER NOT NULL DEFAULT 1,
    born_at         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ============================================================
-- 陷害队列表
-- ============================================================
CREATE TABLE IF NOT EXISTS intrigue_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    attacker_qq     TEXT NOT NULL,
    attacker_name   TEXT NOT NULL,

    target_qq       TEXT,
    target_npc_id   INTEGER,
    target_name     TEXT NOT NULL,

    method          TEXT NOT NULL,
    -- 吹枕边风/诬告/买通太监/下毒/构陷失宠/截财/落胎

    weapon_bonus    INTEGER NOT NULL DEFAULT 0,
    cost_scheme     INTEGER NOT NULL DEFAULT 0,
    cost_silver     INTEGER NOT NULL DEFAULT 0,
    cost_favor      INTEGER NOT NULL DEFAULT 0,

    status          TEXT NOT NULL DEFAULT 'pending',
    -- pending / executed / cancelled

    result          TEXT DEFAULT NULL,          -- success / found / fail
    result_detail   TEXT DEFAULT NULL,

    submitted_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    executed_at     TEXT DEFAULT NULL,
    execute_day     INTEGER NOT NULL DEFAULT 0
);


-- ============================================================
-- 每日日志表
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    day_num         INTEGER NOT NULL,
    log_type        TEXT NOT NULL,
    -- settlement / event / rumor / festival / promotion / death / birth / intrigue_result

    title           TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL,
    affected        TEXT NOT NULL DEFAULT '',
    is_major        INTEGER NOT NULL DEFAULT 0,

    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ============================================================
-- 节日记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS festivals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    day_num         INTEGER NOT NULL,
    festival_name   TEXT NOT NULL,
    -- 花朝节 / 皇帝寿辰 / 中秋宴 / 冬至祭典 / 太后寿宴

    status          TEXT NOT NULL DEFAULT 'upcoming',
    -- upcoming / active / settled

    -- JSON: [{"qq":"...","name":"...","score":0,"silver_offered":0,"result":"..."}]
    participants    TEXT NOT NULL DEFAULT '[]',
    result_text     TEXT DEFAULT NULL,

    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ============================================================
-- 秘密表
-- ============================================================
CREATE TABLE IF NOT EXISTS secrets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    qq              TEXT NOT NULL UNIQUE,
    secret_type     TEXT NOT NULL,
    -- 出身造假 / 入宫前有婚约 / 暗中信奉邪教 / 家族曾谋反 / 身有隐疾 / 无秘密

    penalty_desc    TEXT NOT NULL DEFAULT '',
    is_revealed     INTEGER NOT NULL DEFAULT 0,
    revealed_day    INTEGER DEFAULT NULL,
    revealed_by     TEXT DEFAULT NULL,

    confessed       INTEGER NOT NULL DEFAULT 0,
    confessed_day   INTEGER DEFAULT NULL
);

-- ============================================================
-- 信物持有表
-- ============================================================
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    owner_qq        TEXT,
    owner_npc_id    INTEGER,
    owner_name      TEXT NOT NULL,

    item_name       TEXT NOT NULL,
    -- 玉佩 / 亲笔手书 / 凤钗 / 宫灯 / 血玉扳指

    effect_desc     TEXT NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    expires_day     INTEGER NOT NULL DEFAULT -1,   -- -1=永久

    obtained_day    INTEGER NOT NULL DEFAULT 1,
    obtained_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ============================================================
-- 游戏全局状态（永远只有一行）
-- ============================================================
CREATE TABLE IF NOT EXISTS game_state (
    id              INTEGER PRIMARY KEY DEFAULT 1,

    day_num         INTEGER NOT NULL DEFAULT 0,
    emperor_health  REAL NOT NULL DEFAULT 100,
    emperor_stage   TEXT NOT NULL DEFAULT '龙体康健',
    emperor_mood    TEXT NOT NULL DEFAULT '平和',
    emperor_pref    TEXT NOT NULL DEFAULT '',   -- 本周喜好

    favored_qq      TEXT DEFAULT NULL,          -- 专宠者QQ
    favored_name    TEXT DEFAULT NULL,

    game_phase      TEXT NOT NULL DEFAULT 'active',
    -- active / dying / ended

    attend_slots    INTEGER NOT NULL DEFAULT 5,
    attend_slots_max INTEGER NOT NULL DEFAULT 5,

    season          TEXT NOT NULL DEFAULT '春',

    last_settlement TEXT DEFAULT NULL,

    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

INSERT OR IGNORE INTO game_state (id) VALUES (1);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_concubines_rank     ON concubines(rank_order DESC);
CREATE INDEX IF NOT EXISTS idx_concubines_sacred   ON concubines(sacred_favor DESC);
CREATE INDEX IF NOT EXISTS idx_concubines_love     ON concubines(love DESC);
CREATE INDEX IF NOT EXISTS idx_heirs_mother        ON heirs(mother_qq);
CREATE INDEX IF NOT EXISTS idx_heirs_alive         ON heirs(is_alive, gender);
CREATE INDEX IF NOT EXISTS idx_intrigue_pending    ON intrigue_queue(status, execute_day);
CREATE INDEX IF NOT EXISTS idx_daily_log_day       ON daily_log(day_num DESC);
