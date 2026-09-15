-- reincarnated: 账号是否已用掉唯一一次转世机会(旧角色寿终/飞升后可重新建角一次,之后不可再建)
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    qq            TEXT NOT NULL,
    role          TEXT DEFAULT 'player',
    status        TEXT DEFAULT 'pending',
    reincarnated  INTEGER DEFAULT 0,
    created_ts    INTEGER DEFAULT 0,
    last_login    INTEGER DEFAULT 0,
    spirit_test_attempts INTEGER NOT NULL DEFAULT 0,
    spirit_test_last_ts  INTEGER NOT NULL DEFAULT 0,
    spirit_test_passed   INTEGER NOT NULL DEFAULT 0
);

-- rank_tier: 0=外门 1=普通 2=内门 3=亲传(拜师入峰) 4=执事 5=长老 6=掌门(含已飞升的历代掌门)
-- join_seq: 全服入门先后顺序,创建时分配,永久不变,用于生成"大师兄/二师姐"这类称号
-- user_id 不再唯一:账号用掉转世机会后可拥有第二个角色行,查活跃角色一律加 ascended=0 AND deceased=0
-- ascended: 因担任掌门被后台操作"飞升"、或寿元耗尽时境界达到合体以上判定为"渡劫飞升"
-- deceased: 寿元耗尽且境界不足合体,判定为"寿终正寝",与 ascended 二选一,终局后都不再行动
-- stamina/stamina_ts: 体力懒惰结算,每次读取前按经过时间补齐,上限见 game_data.STAMINA_CAP
-- physique/mind_state/reputation: 体魄(累加)/心境(0-100)/宗门声望(累加,不可消费,晋升新增门槛)
CREATE TABLE IF NOT EXISTS characters (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL,
    name               TEXT NOT NULL,
    gender             TEXT NOT NULL DEFAULT 'm',
    bio                TEXT DEFAULT '',
    realm_idx          INTEGER DEFAULT 0,
    exp                INTEGER DEFAULT 0,
    rank_tier          INTEGER DEFAULT 0,
    join_seq           INTEGER NOT NULL,
    peak_id            INTEGER DEFAULT NULL,
    contribution       INTEGER DEFAULT 0,
    total_contribution INTEGER DEFAULT 0,
    spirit_root        TEXT DEFAULT NULL,
    talent_key         TEXT DEFAULT NULL,
    immortal_bone_key  TEXT DEFAULT NULL,
    bonus_lifespan_years INTEGER DEFAULT 0,
    pet_key            TEXT DEFAULT NULL,
    pet_name           TEXT DEFAULT NULL,
    pet_appearance     TEXT DEFAULT NULL,
    pet_personality    TEXT DEFAULT NULL,
    pet_habit          TEXT DEFAULT NULL,
    pet_breeder_name   TEXT DEFAULT NULL,
    pet_history        TEXT DEFAULT NULL,
    pet_bound_ts       INTEGER DEFAULT 0,
    pet_level          INTEGER DEFAULT 1,
    pet_exp            INTEGER DEFAULT 0,
    alchemist_level    INTEGER DEFAULT 1,
    alchemist_exp      INTEGER DEFAULT 0,
    element_mutation   TEXT DEFAULT NULL,
    forger_level       INTEGER DEFAULT 1,
    forger_exp         INTEGER DEFAULT 0,
    stamina            INTEGER DEFAULT 100,
    stamina_ts         INTEGER DEFAULT 0,
    physique           INTEGER DEFAULT 0,
    mind_state         INTEGER DEFAULT 50,
    reputation         INTEGER DEFAULT 0,
    breakthrough_fail_streak INTEGER DEFAULT 0,
    retreat_started_ts INTEGER DEFAULT 0,
    retreat_until_ts   INTEGER DEFAULT 0,
    lingshi            INTEGER DEFAULT 0,
    cave_tier          INTEGER DEFAULT 0,
    cave_array_level   INTEGER DEFAULT 0,
    cave_array_ts      INTEGER DEFAULT 0,
    cave_garden_seed   TEXT DEFAULT NULL,
    cave_garden_ready_ts INTEGER DEFAULT 0,
    cave_scenery       TEXT DEFAULT NULL,
    cave_traits        TEXT DEFAULT '[]',
    cave_location      TEXT DEFAULT NULL,
    cave_name          TEXT DEFAULT NULL,
    technique_deviation INTEGER DEFAULT 0,
    injury_until_ts    INTEGER DEFAULT 0,
    equipped_weapon_key    TEXT DEFAULT NULL,
    equipped_armor_key     TEXT DEFAULT NULL,
    equipped_accessory_key TEXT DEFAULT NULL,
    artifact_core_bound       INTEGER DEFAULT 0,
    artifact_core_orientation TEXT DEFAULT NULL,
    artifact_core_level       INTEGER DEFAULT 0,
    artifact_core_exp         INTEGER DEFAULT 0,
    artifact_core_quality     TEXT DEFAULT NULL,
    artifact_core_name        TEXT DEFAULT NULL,
    artifact_core_spirit      TEXT DEFAULT NULL,
    dan_quality         TEXT DEFAULT NULL,
    dan_name            TEXT DEFAULT NULL,
    dan_quality_pending TEXT DEFAULT NULL,
    dan_stage           INTEGER DEFAULT 0,
    dan_fail_streak     INTEGER DEFAULT 0,
    infant_stage         INTEGER DEFAULT 0,
    infant_name          TEXT DEFAULT NULL,
    infant_fail_streak   INTEGER DEFAULT 0,
    infant_trial_buff    INTEGER DEFAULT 0,
    infant_weak_until_ts INTEGER DEFAULT 0,
    shen_quality         TEXT DEFAULT NULL,
    shen_quality_pending TEXT DEFAULT NULL,
    shen_stage           INTEGER DEFAULT 0,
    shen_fail_streak     INTEGER DEFAULT 0,
    heti_stage           INTEGER DEFAULT 0,
    heti_fail_streak     INTEGER DEFAULT 0,
    heti_trial_buff      INTEGER DEFAULT 0,
    heti_weak_until_ts   INTEGER DEFAULT 0,
    ascended           INTEGER DEFAULT 0,
    dao_hao            TEXT DEFAULT NULL,
    dao_path_key       TEXT DEFAULT NULL,
    dao_path_chosen_ts INTEGER DEFAULT NULL,
    deceased           INTEGER DEFAULT 0,
    is_npc             INTEGER NOT NULL DEFAULT 0,
    travel_points      INTEGER NOT NULL DEFAULT 2,
    travel_points_ts   INTEGER DEFAULT 0,
    severe_injury_until_ts INTEGER DEFAULT 0,
    lifespan_warned_realm_idx INTEGER DEFAULT -1,
    created_ts         INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (peak_id) REFERENCES peaks(id)
);

CREATE TABLE IF NOT EXISTS character_weapon_masteries (
    char_id      INTEGER NOT NULL,
    weapon_style TEXT NOT NULL,
    mastery      INTEGER NOT NULL DEFAULT 0,
    updated_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (char_id, weapon_style),
    FOREIGN KEY (char_id) REFERENCES characters(id)
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

-- ── 峰:固定8峰(7长老峰+1掌门峰),精英弟子拜师入峰 / 师徒 ─────────────────────────
-- is_leader: 1=掌门峰(唯一,长老之位只能由继任产生,不可通过考核获得)
-- elder_id 允许为空:峰主(长老/掌门)飞升或出缺后,峰保留、弟子留任,等待本峰弟子考核补位

CREATE TABLE IF NOT EXISTS peaks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    is_leader   INTEGER NOT NULL DEFAULT 0,
    elder_id    INTEGER DEFAULT NULL,
    created_ts  INTEGER DEFAULT 0,
    FOREIGN KEY (elder_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS discipleships (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    master_id     INTEGER NOT NULL,
    disciple_id   INTEGER NOT NULL UNIQUE,
    status        TEXT DEFAULT 'active',
    created_ts    INTEGER DEFAULT 0,
    FOREIGN KEY (master_id) REFERENCES characters(id),
    FOREIGN KEY (disciple_id) REFERENCES characters(id)
);

-- ── 宗门单例配置:掌门NPC占位 + 飞升继承定时事件 ─────────────────────────────────

CREATE TABLE IF NOT EXISTS sect_config (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    sect_name             TEXT NOT NULL DEFAULT '九霄仙门',
    npc_leader_name       TEXT NOT NULL DEFAULT '沈天铭',
    founded_ts            INTEGER DEFAULT 0,
    succession_target_ts  INTEGER DEFAULT 0,
    succession_done       INTEGER DEFAULT 0
);

-- ── 通用基建:邀请码 / 礼包码 / 站内信 / 成就 / 每日计数器 ────────────────────────

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

-- ── 天魔入侵:后台手动开启的限时全宗活动,全体角色共享同一头目血量,不是各打各的副本 ──────
-- status: active(进行中) / defeated(已剿灭) / expired(超时未剿灭,天魔遁走)
-- phase: 0=天魔降临 1=魔将结阵 2=魔念暴走 3=众生破魔,按 boss_hp/boss_hp_max 比例推进
-- adds_json: phase=1 时生成的三只魔将{key:{label,hp,hp_max}},魔将存活期间对天魔本体的伤害打折
CREATE TABLE IF NOT EXISTS invasions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    status         TEXT NOT NULL DEFAULT 'active',
    boss_label     TEXT NOT NULL,
    boss_hp        INTEGER NOT NULL,
    boss_hp_max    INTEGER NOT NULL,
    phase          INTEGER NOT NULL DEFAULT 0,
    adds_json      TEXT DEFAULT NULL,
    killer_char_id INTEGER DEFAULT NULL,
    opened_ts      INTEGER NOT NULL,
    ends_ts        INTEGER NOT NULL,
    resolved_ts    INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS invasion_participants (
    invasion_id   INTEGER NOT NULL,
    char_id       INTEGER NOT NULL,
    damage_dealt  INTEGER NOT NULL DEFAULT 0,
    attack_count  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (invasion_id, char_id),
    FOREIGN KEY (invasion_id) REFERENCES invasions(id),
    FOREIGN KEY (char_id) REFERENCES characters(id)
);

-- ── 宗门节日:后台选类型开启的轻量全宗活动,持续数日,到期自动收尾公布结果 ─────────────
-- 结果一次性算完存进 results_json 快照,不是实时查询——节日落幕后即便宠物数据变了,
-- 当届的名录也不会跟着变,这样"某届品鉴会谁得了什么"才是一句钉死的历史,不是活的排行榜。
CREATE TABLE IF NOT EXISTS festivals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type_key     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    opened_ts    INTEGER NOT NULL,
    ends_ts      INTEGER NOT NULL,
    resolved_ts  INTEGER DEFAULT NULL,
    results_json TEXT DEFAULT NULL
);

-- 开山大典:每名弟子在本届典礼里限选一次职责,line_text 是结算时生成宗门史用的那一句,
-- 存下来避免结算时角色改名/换武器导致史书文本跟当时对不上。
-- 开山大典·抽奖:典礼期间(72小时)人人可参与,每小时限抽一次,跟是否领了职责无关——
-- 给"进度条已经点满"之后剩下的时间找点互动,不是一次性的。
CREATE TABLE IF NOT EXISTS kaishan_draws (
    festival_id   INTEGER NOT NULL,
    char_id       INTEGER NOT NULL,
    last_draw_ts  INTEGER NOT NULL,
    PRIMARY KEY (festival_id, char_id)
);

CREATE TABLE IF NOT EXISTS kaishan_participation (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    festival_id        INTEGER NOT NULL,
    char_id            INTEGER NOT NULL,
    duty_key           TEXT NOT NULL,
    line_text          TEXT NOT NULL,
    bonus_material_key TEXT DEFAULT NULL,
    bonus_material_qty INTEGER DEFAULT NULL,
    created_ts         INTEGER NOT NULL,
    UNIQUE(festival_id, char_id)
);

-- 中秋观月:一人可发起一次邀约(或独自赏月,to_char_id留空即成),对方需回应才生成共同回忆;
-- 双人一旦accepted/declined即定型,不可再改;独自赏月创建时直接是accepted。
CREATE TABLE IF NOT EXISTS zhongqiu_moments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    festival_id   INTEGER NOT NULL,
    from_char_id  INTEGER NOT NULL,
    to_char_id    INTEGER,
    location_key  TEXT NOT NULL,
    activity_key  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    memory_text   TEXT,
    gift_desc     TEXT,
    created_ts    INTEGER NOT NULL,
    responded_ts  INTEGER
);

-- 本届只许"定下"一次赏月(邀约/独自赏月),declined 的不算数,可以重新再约——
-- 与 _zhongqiu_active_row() 里 from_char_id 一侧的判定条件对齐,堵住并发重复提交刷奖励的口子。
CREATE UNIQUE INDEX IF NOT EXISTS idx_zhongqiu_moments_from_active
    ON zhongqiu_moments(festival_id, from_char_id) WHERE status != 'declined';

-- 中秋月饼试炼：每次开工消耗当小时一次机会，进度走错即清空；成品可食用、赠送和收藏。
CREATE TABLE IF NOT EXISTS zhongqiu_bake_usage (
    festival_id INTEGER NOT NULL, char_id INTEGER NOT NULL, hour_bucket INTEGER NOT NULL,
    attempts_used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (festival_id, char_id, hour_bucket)
);
CREATE TABLE IF NOT EXISTS zhongqiu_bake_sessions (
    festival_id INTEGER NOT NULL, char_id INTEGER NOT NULL, cake_key TEXT NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0, started_ts INTEGER NOT NULL,
    PRIMARY KEY (festival_id, char_id)
);
CREATE TABLE IF NOT EXISTS zhongqiu_bake_collection (
    festival_id INTEGER NOT NULL, char_id INTEGER NOT NULL, cake_key TEXT NOT NULL,
    first_baked_ts INTEGER NOT NULL, bake_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (festival_id, char_id, cake_key)
);
CREATE TABLE IF NOT EXISTS zhongqiu_mooncake_inventory (
    festival_id INTEGER NOT NULL, char_id INTEGER NOT NULL, cake_key TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (festival_id, char_id, cake_key)
);
CREATE TABLE IF NOT EXISTS zhongqiu_bake_rankings (
    festival_id INTEGER NOT NULL, char_id INTEGER NOT NULL, rank INTEGER NOT NULL,
    completed_ts INTEGER NOT NULL, reward_lingshi INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (festival_id, char_id), UNIQUE (festival_id, rank)
);
-- 记住做对的工序:每种月饼独立记录已确认正确的前几步(不会因某次试炼失败而清空已确认部分),
-- 下次开工直接从已知的下一步开始,省得每次失败都要从头猜起。
CREATE TABLE IF NOT EXISTS zhongqiu_bake_known (
    festival_id INTEGER NOT NULL, char_id INTEGER NOT NULL, cake_key TEXT NOT NULL,
    known_steps INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (festival_id, char_id, cake_key)
);

-- 新岁赐福:许愿(snapshot_json 存下当时的相关数值,供下一届许愿时回顾是否应验)+
-- 除岁活动(全宗共享进度,跟开山大典同一个思路)+ 福签/红包(单向赠送,可选立即拆或留存)。
CREATE TABLE IF NOT EXISTS xinsui_wishes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    festival_id   INTEGER NOT NULL,
    char_id       INTEGER NOT NULL,
    wish_key      TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_ts    INTEGER NOT NULL,
    UNIQUE(festival_id, char_id)
);
CREATE TABLE IF NOT EXISTS xinsui_activity (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    festival_id   INTEGER NOT NULL,
    char_id       INTEGER NOT NULL,
    activity_key  TEXT NOT NULL,
    line_text     TEXT NOT NULL,
    created_ts    INTEGER NOT NULL,
    UNIQUE(festival_id, char_id)
);
CREATE TABLE IF NOT EXISTS xinsui_blessings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    festival_id   INTEGER NOT NULL,
    from_char_id  INTEGER NOT NULL,
    to_char_id    INTEGER NOT NULL,
    gift_name     TEXT NOT NULL,
    rarity_key    TEXT NOT NULL,
    message       TEXT NOT NULL,
    opened        INTEGER NOT NULL DEFAULT 0,
    created_ts    INTEGER NOT NULL,
    opened_ts     INTEGER
);

-- from_char_id: 有值代表这是玩家互发的私信,可回信;为空代表系统/宗门公告类通知
CREATE TABLE IF NOT EXISTS mail (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id          INTEGER NOT NULL,
    from_char_id     INTEGER DEFAULT NULL,
    from_label       TEXT DEFAULT '系统',
    subject          TEXT NOT NULL,
    body             TEXT DEFAULT '',
    attachment_json  TEXT DEFAULT NULL,
    claimed          INTEGER DEFAULT 0,
    read             INTEGER DEFAULT 0,
    created_ts       INTEGER DEFAULT 0,
    FOREIGN KEY (char_id) REFERENCES characters(id),
    FOREIGN KEY (from_char_id) REFERENCES characters(id)
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

-- 行侠奇遇:行侠令任务结算后小概率额外触发的一次性剧情事件,每个角色每条只会遇到一次
CREATE TABLE IF NOT EXISTS character_story_encounters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id       INTEGER NOT NULL,
    encounter_key TEXT NOT NULL,
    choice_key    TEXT NOT NULL,
    tag_label     TEXT,
    resolved_ts   INTEGER DEFAULT 0,
    UNIQUE(char_id, encounter_key)
);

CREATE TABLE IF NOT EXISTS character_dao_paths (
    char_id      INTEGER NOT NULL,
    path_key     TEXT NOT NULL,
    progress     INTEGER NOT NULL DEFAULT 0,
    unlocked_ts  INTEGER,
    PRIMARY KEY (char_id, path_key)
);

CREATE TABLE IF NOT EXISTS daily_counters (
    char_id      INTEGER NOT NULL,
    counter_key  TEXT NOT NULL,
    day          TEXT NOT NULL,
    count        INTEGER DEFAULT 0,
    PRIMARY KEY (char_id, counter_key, day)
);

-- ── 宗门大事记:按宗门纪年记录重大事件(继任/飞升/寿终/仙骨出世等),只读时间线 ────────

-- is_major: 全宗级大事(掌门更替/仙骨天灵根/旷世奇珍/天魔入侵/节日开启落幕)才置1,
-- 供 /api/chronicle/major 给QQ机器人轮询播报用;日常小事(NPC长老让贤、游历遇险等)不置1,避免刷屏
CREATE TABLE IF NOT EXISTS chronicle (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL DEFAULT 0,
    text        TEXT NOT NULL,
    is_major    INTEGER NOT NULL DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

-- ── 每日基础任务:每天随机抽3项(仿 daily_counters 按天分区),完成2项/3项分别发奖 ──────

CREATE TABLE IF NOT EXISTS daily_state (
    char_id       INTEGER NOT NULL,
    day           TEXT NOT NULL,
    task_keys     TEXT NOT NULL,
    done_keys     TEXT NOT NULL DEFAULT '[]',
    bonus_claimed INTEGER DEFAULT 0,
    full_claimed  INTEGER DEFAULT 0,
    PRIMARY KEY (char_id, day)
);

-- ── 羁绊:义结金兰(可多个)/ 道侣(唯一),双方都需同意方可缔结,缔结后打坐修为互相加成 ──

-- ── 炼丹:已学会的丹方 / 已炼出待服用或出售的丹药库存 ──────────────────────────────

CREATE TABLE IF NOT EXISTS character_recipes (
    char_id      INTEGER NOT NULL,
    recipe_key   TEXT NOT NULL,
    learned_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (char_id, recipe_key)
);

CREATE TABLE IF NOT EXISTS character_pills (
    char_id      INTEGER NOT NULL,
    recipe_key   TEXT NOT NULL,
    qty          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (char_id, recipe_key)
);

-- ── 炼器:法宝库存,形态×属性(或变异属性)×稀有度三元组,组合生成不需要预定义配方表 ────

CREATE TABLE IF NOT EXISTS character_artifacts (
    char_id      INTEGER NOT NULL,
    form         TEXT NOT NULL,
    element_key  TEXT NOT NULL,
    rarity_key   TEXT NOT NULL,
    qty          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (char_id, form, element_key, rarity_key)
);

-- ── 洞府:灵材仓库(建造/升级消耗) / 已建成的纯展示装饰(需先解锁对应特征) ─────────────

CREATE TABLE IF NOT EXISTS character_materials (
    char_id      INTEGER NOT NULL,
    material_key TEXT NOT NULL,
    qty          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (char_id, material_key)
);

CREATE TABLE IF NOT EXISTS character_decorations (
    char_id         INTEGER NOT NULL,
    decoration_key  TEXT NOT NULL,
    built_ts        INTEGER DEFAULT 0,
    PRIMARY KEY (char_id, decoration_key)
);

-- ── 功法:峰专属功法的持有记录(自己峰的+机缘习得的旁门功法),各自独立记熟练度 ──────────

CREATE TABLE IF NOT EXISTS character_techniques (
    char_id       INTEGER NOT NULL,
    technique_key TEXT NOT NULL,
    learned_ts    INTEGER DEFAULT 0,
    mastery       INTEGER NOT NULL DEFAULT 0,
    insight       TEXT,
    PRIMARY KEY (char_id, technique_key)
);

CREATE TABLE IF NOT EXISTS bonds (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    char_a_id             INTEGER NOT NULL,
    char_b_id             INTEGER NOT NULL,
    bond_type             TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'pending',
    created_ts            INTEGER DEFAULT 0,
    accepted_ts           INTEGER DEFAULT 0,
    affinity              INTEGER NOT NULL DEFAULT 0,
    conceive_fail_streak  INTEGER NOT NULL DEFAULT 0,
    conceive_last_ts      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (char_a_id) REFERENCES characters(id),
    FOREIGN KEY (char_b_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS bond_interactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    bond_id       INTEGER NOT NULL,
    actor_id      INTEGER NOT NULL,
    action_key    TEXT NOT NULL,
    day           TEXT NOT NULL,
    memory_text   TEXT NOT NULL,
    affinity_gain INTEGER NOT NULL DEFAULT 0,
    created_ts    INTEGER DEFAULT 0,
    UNIQUE (bond_id, actor_id, day),
    FOREIGN KEY (bond_id) REFERENCES bonds(id),
    FOREIGN KEY (actor_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS bond_gifts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    maker_id       INTEGER,
    owner_id       INTEGER NOT NULL,
    recipient_id   INTEGER,
    bond_id        INTEGER,
    gift_type      TEXT NOT NULL,
    gift_name      TEXT NOT NULL,
    rarity_key     TEXT NOT NULL,
    trait_key      TEXT NOT NULL,
    source_key     TEXT NOT NULL,
    origin_text    TEXT NOT NULL,
    message        TEXT DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'inventory',
    created_ts     INTEGER DEFAULT 0,
    gifted_ts      INTEGER DEFAULT 0,
    responded_ts   INTEGER DEFAULT 0,
    FOREIGN KEY (maker_id) REFERENCES characters(id),
    FOREIGN KEY (owner_id) REFERENCES characters(id),
    FOREIGN KEY (recipient_id) REFERENCES characters(id),
    FOREIGN KEY (bond_id) REFERENCES bonds(id)
);

-- ── 子嗣:父母字段多态(角色或子嗣自身),支持代代相传;求子/成长/结亲三段仪式 ────────────
-- parent_a 恒为"真实一方"(角色或子嗣),parent_b 可以是角色/子嗣/散修NPC(此时 npc_name 非空)

CREATE TABLE IF NOT EXISTS offspring (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    gender              TEXT NOT NULL,
    generation          INTEGER NOT NULL DEFAULT 1,
    parent_a_kind       TEXT NOT NULL,
    parent_a_id         INTEGER NOT NULL,
    parent_b_kind       TEXT NOT NULL,
    parent_b_id         INTEGER,
    parent_b_npc_name   TEXT,
    realm_idx           INTEGER NOT NULL DEFAULT 0,
    exp                 INTEGER NOT NULL DEFAULT 0,
    spirit_root         TEXT,
    talent_key          TEXT,
    personality_key     TEXT,
    hobby_key           TEXT,
    archetype           TEXT,
    life_event          TEXT,
    alive               INTEGER NOT NULL DEFAULT 1,
    frail_warned_ts     INTEGER,
    spouse_offspring_id INTEGER,
    spouse_npc_name     TEXT,
    married_ts          INTEGER,
    npc_proposal_name   TEXT,
    conceive_fail_streak INTEGER NOT NULL DEFAULT 0,
    conceive_last_ts    INTEGER NOT NULL DEFAULT 0,
    born_ts             INTEGER NOT NULL,
    last_growth_ts      INTEGER NOT NULL,
    deceased_ts         INTEGER,
    created_ts          INTEGER NOT NULL
);

-- ── 结亲提议:两个子嗣之间的联姻邀约,由任一方家长发起、对方任一家长回应 ─────────────────

CREATE TABLE IF NOT EXISTS offspring_proposals (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    from_offspring_id  INTEGER NOT NULL,
    to_offspring_id    INTEGER NOT NULL,
    from_char_id       INTEGER NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending',
    created_ts         INTEGER DEFAULT 0,
    accepted_ts        INTEGER
);

-- ── 交易行:寄售制,挂单即托管(灵材/丹药/法宝库存立刻扣除),买家一口价买断 ──────────────

CREATE TABLE IF NOT EXISTS market_listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_char_id  INTEGER NOT NULL,
    item_kind       TEXT NOT NULL,
    item_key        TEXT NOT NULL,
    item_key2       TEXT,
    item_key3       TEXT,
    qty_total       INTEGER NOT NULL,
    qty_remaining   INTEGER NOT NULL,
    price_per_unit  INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_ts      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS market_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER NOT NULL,
    seller_char_id  INTEGER NOT NULL,
    buyer_char_id   INTEGER NOT NULL,
    item_kind       TEXT NOT NULL,
    item_key        TEXT NOT NULL,
    item_key2       TEXT,
    item_key3       TEXT,
    qty             INTEGER NOT NULL,
    price_per_unit  INTEGER NOT NULL,
    created_ts      INTEGER NOT NULL
);

-- ── 秘境装备:武器/防具/饰品是可替换的库存(固定模板,按数量堆叠);本命法宝状态存在角色表上 ──

CREATE TABLE IF NOT EXISTS character_equipment (
    char_id      INTEGER NOT NULL,
    item_key     TEXT NOT NULL,
    qty          INTEGER NOT NULL DEFAULT 0,
    lore         TEXT,
    PRIMARY KEY (char_id, item_key)
);

-- 灵宠:每只独立一行(同物种可以养多只,各自有名字/等级),不是按key堆qty的库存表
CREATE TABLE IF NOT EXISTS character_pets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    pet_key         TEXT NOT NULL,
    pet_name        TEXT,
    appearance      TEXT,
    personality     TEXT,
    habit           TEXT,
    breeder_name    TEXT,
    history         TEXT,
    level           INTEGER NOT NULL DEFAULT 1,
    exp             INTEGER NOT NULL DEFAULT 0,
    bound_ts        INTEGER DEFAULT 0,
    location        TEXT NOT NULL DEFAULT 'roster',
    holding_expires_ts INTEGER DEFAULT 0
);

-- 配装预设:固定3个槽位(p1/p2/p3),存武器/防具/饰品三个item_key,标签自定义;
-- 应用时按已有的equip/unequip逻辑逐件换装,某件不再持有就跳过那一件,不报错中断
CREATE TABLE IF NOT EXISTS character_equipment_presets (
    char_id       INTEGER NOT NULL,
    preset_key    TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    weapon_key    TEXT,
    armor_key     TEXT,
    accessory_key TEXT,
    updated_ts    INTEGER NOT NULL,
    PRIMARY KEY (char_id, preset_key)
);

-- ── 秘境:每天限入一次的运行状态,按(char_id, day)唯一;深度/气血/体力/封存收获都记在这一行上 ──

-- 秘境每次"探索"点击的逐条日志,便于追查是否有人绕过体力上限反复刷探索(仅追加,不参与游戏逻辑)
CREATE TABLE IF NOT EXISTS mystic_explore_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id             INTEGER NOT NULL,
    day                 TEXT NOT NULL,
    session_id          INTEGER NOT NULL,
    depth               INTEGER NOT NULL,
    stamina_before       INTEGER NOT NULL,
    event_type          TEXT NOT NULL,
    created_ts          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mystic_explore_log_char_day ON mystic_explore_log(char_id, day);

CREATE TABLE IF NOT EXISTS mystic_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id             INTEGER NOT NULL,
    day                 TEXT NOT NULL,
    zone_key            TEXT NOT NULL,
    depth               INTEGER NOT NULL DEFAULT 1,
    stamina             INTEGER NOT NULL,
    hp                  INTEGER NOT NULL,
    hp_max              INTEGER NOT NULL,
    escape_charms       INTEGER NOT NULL DEFAULT 0,
    heal_uses           INTEGER NOT NULL DEFAULT 0,
    hidden_unlocked     INTEGER NOT NULL DEFAULT 0,
    sealed_loot_json    TEXT NOT NULL DEFAULT '{}',
    pending_loot_json   TEXT NOT NULL DEFAULT '{}',
    pending_event_json  TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    entered_ts          INTEGER NOT NULL,
    ended_ts            INTEGER,
    UNIQUE(char_id, day)
);

-- ── 游历人间:长周期、轻操作、剧情驱动的支线,不像秘境那样禁止其他操作,纯后台计时+惰性结算 ──
-- 一人同一时间最多一趟游历,claim后删行,可以开下一趟;events_total按时长档位算,事件均匀分布在行程里

CREATE TABLE IF NOT EXISTS travel_sessions (
    char_id            INTEGER PRIMARY KEY,
    region_key         TEXT NOT NULL,
    duration_key       TEXT NOT NULL,
    started_ts         INTEGER NOT NULL,
    ends_ts            INTEGER NOT NULL,
    next_event_ts      INTEGER NOT NULL,
    events_done        INTEGER NOT NULL DEFAULT 0,
    events_total       INTEGER NOT NULL,
    had_special_event  INTEGER NOT NULL DEFAULT 0,
    pending_event_json TEXT,
    log_json           TEXT NOT NULL DEFAULT '[]'
);

-- 连锁奇遇进度:clue(线索持有)/waiting(等待发展)/ready(可以继续)/completed/failed/branched
CREATE TABLE IF NOT EXISTS travel_threads (
    char_id     INTEGER NOT NULL,
    thread_key  TEXT NOT NULL,
    node_key    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'clue',
    ready_ts    INTEGER DEFAULT 0,
    updated_ts  INTEGER NOT NULL,
    PRIMARY KEY (char_id, thread_key)
);

-- 地区熟悉度:纯累加,不锁定,用于解锁传说奇遇/深层事件;legendary_miss_streak 撑起传说奇遇的递增概率保底
CREATE TABLE IF NOT EXISTS character_region_familiarity (
    char_id     INTEGER NOT NULL,
    region_key  TEXT NOT NULL,
    familiarity INTEGER NOT NULL DEFAULT 0,
    legendary_miss_streak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (char_id, region_key)
);

-- 游历遇险求援:全宗可见,认领后锁定一段时间需完成救援判定,超时自动释放给其他人;
-- 过期无人认领完成则由后备力量兜底,caller一方惰性结算为较轻的"轻伤"(不是无人问津的孤立无援)
CREATE TABLE IF NOT EXISTS travel_rescue_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    claimed_by   INTEGER,
    claim_expires_ts INTEGER DEFAULT 0,
    char_id      INTEGER NOT NULL,
    region_key   TEXT NOT NULL,
    danger_key   TEXT NOT NULL,
    danger_text  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open',
    rescuer_id   INTEGER,
    expires_ts   INTEGER NOT NULL,
    created_ts   INTEGER NOT NULL,
    resolved_ts  INTEGER
);
