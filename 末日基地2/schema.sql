-- 末日基地2.0 v0.1 骨架 schema
-- 只落地设计文档 A 档确认的核心范围,B/C 档留到以后再加表,不预留字段。

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    respawn_count INTEGER DEFAULT 0,   -- 一节:每账号最多重开3次
    permadead     INTEGER DEFAULT 0,   -- 第3次重开后再死 = 永久锁定
    approved      INTEGER DEFAULT 0,   -- 试玩阶段:新注册需要管理员批准才能进游戏
    created_ts    INTEGER DEFAULT 0
);

-- 一个用户一辈子会有多条 character 记录(死了重开=全新身份,不继承任何东西)
CREATE TABLE IF NOT EXISTS characters (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    name              TEXT NOT NULL,
    status            TEXT DEFAULT 'alive',   -- alive / dead
    -- 二节:四维属性,全部从0起步,各自封顶20
    stat_str          INTEGER DEFAULT 0,
    stat_spd          INTEGER DEFAULT 0,
    stat_int          INTEGER DEFAULT 0,
    stat_luck         INTEGER DEFAULT 0,
    hp                INTEGER DEFAULT 100,
    infection         INTEGER DEFAULT 0,      -- 到100=死亡,只升不降(解药以后再做)
    hunger            INTEGER DEFAULT 100,
    thirst            INTEGER DEFAULT 100,
    stamina           INTEGER DEFAULT 100,    -- 软体力：归零仍可行动，但效率和风险恶化
    stamina_updated_ts INTEGER DEFAULT 0,      -- 按真实时间恢复体力
    level             INTEGER DEFAULT 1,      -- 封顶30
    xp                INTEGER DEFAULT 0,
    blueprint_points  INTEGER DEFAULT 0,
    wallet            INTEGER DEFAULT 0,      -- 十四.1 钱包货币
    storage_capacity  INTEGER DEFAULT 150,    -- 九.3 个人随身储物上限(背包可加)
    tile_x            INTEGER DEFAULT 0,      -- 当前所在地块坐标(出生点=0,0)
    tile_y            INTEGER DEFAULT 0,
    shelter_id        INTEGER,                -- 同一时间只能属于1个庇护所
    protected_until_ts INTEGER DEFAULT 0,     -- 三节:2天新手保护期
    poison_until_ts    INTEGER DEFAULT 0,     -- 生水中毒(六节),期间持续掉血
    pending_zombie_type TEXT,                 -- 十六.6:回合制战斗进行中的对手(为空=没有遭遇)
    pending_zombie_hp   INTEGER DEFAULT 0,
    combat_max_hp       INTEGER DEFAULT 0,    -- 战斗开始时敌人生命，用于风险与进度展示
    combat_round_no     INTEGER DEFAULT 0,
    combat_intent       TEXT DEFAULT '',      -- 敌人下一步意图（先预告，再结算）
    combat_terrain      TEXT DEFAULT '',
    combat_aim          INTEGER DEFAULT 0,     -- 玩家是否已经完成瞄准/蓄力
    combat_reload       INTEGER DEFAULT 0,     -- 弩是否需要装填
    combat_enemy_buff   INTEGER DEFAULT 0,     -- 尖叫等行为造成的临时强化
    combat_status       TEXT DEFAULT '',       -- grabbed 等单场状态
    combat_tactic_used  INTEGER DEFAULT 0,
    combat_pet_used     INTEGER DEFAULT 0,
    combat_signal_used  INTEGER DEFAULT 0,
    combat_advantage    INTEGER DEFAULT 0,     -- 地形/伙伴创造的下一击优势
    pending_combat_reward TEXT DEFAULT '',     -- 击杀后的现场处置，选择前不能跳过
    equipped_weapon    TEXT DEFAULT 'fist',   -- 八.3:武器进阶路线,fist不需要解锁
    weapon_durability  INTEGER DEFAULT 100,
    equipped_armor     TEXT,                  -- 护甲图纸key,NULL=没穿甲
    armor_durability   INTEGER DEFAULT 0,
    armor_tier         INTEGER DEFAULT 0,     -- 0=无 1/2/3=八.3+十六.1的简化三档
    equipped_vehicle   TEXT,                  -- 二十九节:交通工具,NULL=没有,省体力/无冷却/一次挪多格
    backpack_count     INTEGER DEFAULT 0,     -- 九.3:背包数量,每件+100容量,封顶3件
    has_fishing_rod    INTEGER DEFAULT 0,     -- 钓鱼:造过鱼竿才能在水域地块钓鱼
    pending_fish_key    TEXT,                 -- 钓鱼小游戏进行中分配到的鱼种(为空=没在钓)
    pending_fish_started_ts INTEGER DEFAULT 0,
    pending_tame_key    TEXT,                 -- 驯养:正在驯服的野生动物(为空=没在驯)
    pending_tame_affinity INTEGER DEFAULT 0,  -- 好感度,攒到100驯服成功
    tamed_animal_key    TEXT,                 -- 已驯服并带回兽栏的动物(一次只能养一只)
    animal_collect_ready_ts INTEGER DEFAULT 0, -- 生产型/所有动物的被动产出(零件/粪便),tick里自动结算
    move_cooldown_until_ts INTEGER DEFAULT 0, -- 十六.2:移动冷却(负重会拉长这个)
    pending_tree_started_ts INTEGER DEFAULT 0,   -- 二十四节:种树计时,不依赖地图资源点也能稳定拿木材
    pending_quarry_started_ts INTEGER DEFAULT 0, -- 同上,挖石头
    auto_eat_enabled INTEGER DEFAULT 0,          -- 二十五节:随身物资够的话自动吃喝,玩家自己开关
    infection_relief_started_ts INTEGER DEFAULT 0, -- 感染度被动缓解改成确定性计时后不再靠概率
    created_ts        INTEGER DEFAULT 0,
    last_action_ts     INTEGER DEFAULT 0,
    death_ts          INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 二节:个人等级解锁图纸(点数1:1),这里记录"已解锁"状态
CREATE TABLE IF NOT EXISTS character_blueprints (
    character_id  INTEGER NOT NULL,
    blueprint_key TEXT NOT NULL,
    unlocked_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, blueprint_key)
);

CREATE INDEX IF NOT EXISTS idx_characters_user ON characters(user_id);
CREATE INDEX IF NOT EXISTS idx_characters_tile ON characters(tile_x, tile_y);

-- 九.3:随身携带的个人储物(和房子/庇护所仓库是三个分开的容器)
CREATE TABLE IF NOT EXISTS character_inventory (
    character_id INTEGER NOT NULL,
    resource_key TEXT NOT NULL,
    amount       INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, resource_key)
);

-- 四节:地图无限延伸,地块按需生成(第一次有人到达时写入)
CREATE TABLE IF NOT EXISTS world_tiles (
    x             INTEGER NOT NULL,
    y             INTEGER NOT NULL,
    discovered_ts INTEGER DEFAULT 0,
    has_building  INTEGER DEFAULT 0,   -- 十四.3:建筑对全服可见,占了这块地就不能再建
    is_water      INTEGER DEFAULT 0,   -- 钓鱼:水域地块,不能建造/没有普通资源点
    PRIMARY KEY (x, y)
);

-- 八.1:资源刷新按单个槽位,不是整块地图重置
CREATE TABLE IF NOT EXISTS resource_nodes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tile_x           INTEGER NOT NULL,
    tile_y           INTEGER NOT NULL,
    resource_key     TEXT NOT NULL,
    rarity           TEXT NOT NULL,     -- normal / rare / landmark
    max_amount       INTEGER NOT NULL,
    current_amount   INTEGER NOT NULL,
    depleted_ts       INTEGER DEFAULT 0, -- 采光时打的时间戳,配合稀有度算刷新
    gone_forever      INTEGER DEFAULT 0  -- 地标级拿完永久消失
);

CREATE INDEX IF NOT EXISTS idx_resource_nodes_tile ON resource_nodes(tile_x, tile_y);

-- 三节:个人房子,一个人可以建多座,各自储物独立(十一.2)
CREATE TABLE IF NOT EXISTS houses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    tile_x       INTEGER NOT NULL,
    tile_y       INTEGER NOT NULL,
    has_workbench INTEGER DEFAULT 0,   -- 八.3:个人房子可建基础工作台
    level        INTEGER DEFAULT 1,
    hp           INTEGER DEFAULT 80,
    max_hp       INTEGER DEFAULT 80,
    auto_defense INTEGER DEFAULT 0,    -- Lv4起，夜袭消耗房屋仓库弹药削弱尸群
    auto_defense_damaged INTEGER DEFAULT 0,
    raid_stance  TEXT DEFAULT 'balanced',     -- balanced/storage/facility/conserve/lure
    last_raid_ts INTEGER DEFAULT 0,
    built_ts     INTEGER DEFAULT 0,
    abandoned    INTEGER DEFAULT 0,     -- 三节:户主死亡即废弃
    abandoned_ts INTEGER DEFAULT 0,
    storage_crates INTEGER DEFAULT 0,   -- 二十六节:不需要工作台就能造的储物箱，每个给房子仓库扩容
    has_metal_driller INTEGER DEFAULT 0,     -- 二十八节:打矿机，被动产出金属
    metal_driller_ready_ts INTEGER DEFAULT 0,
    custom_name  TEXT DEFAULT '',       -- 二十九节:多套房子时玩家自定义名字,用于地图上区分"家1/家2"
    FOREIGN KEY (owner_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS house_inventory (
    house_id     INTEGER NOT NULL,
    resource_key TEXT NOT NULL,
    amount       INTEGER DEFAULT 0,
    PRIMARY KEY (house_id, resource_key)
);

CREATE TABLE IF NOT EXISTS house_raid_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    house_id          INTEGER NOT NULL,
    character_id      INTEGER NOT NULL,
    day_count         INTEGER NOT NULL,
    attack_strength   INTEGER DEFAULT 0,
    counter_damage    INTEGER DEFAULT 0,
    structure_damage  INTEGER DEFAULT 0,
    character_damage  INTEGER DEFAULT 0,
    summary           TEXT NOT NULL,
    created_ts        INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_house_raid_logs_house
ON house_raid_logs(house_id, id DESC);

-- 五节:庇护所,公开报名制,3人起步顶级20人(十.1:成员数降到0才废弃)
CREATE TABLE IF NOT EXISTS shelters (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    banner           TEXT DEFAULT '',
    tile_x           INTEGER NOT NULL,
    tile_y           INTEGER NOT NULL,
    tier             INTEGER DEFAULT 1,     -- 1-6级,人数/仓库随之扩大
    research_points  INTEGER DEFAULT 0,
    defense_walls    INTEGER DEFAULT 0,     -- 十六.3:防御建筑,各自给固定防御值
    defense_traps    INTEGER DEFAULT 0,
    defense_tower    INTEGER DEFAULT 0,
    has_furnace      INTEGER DEFAULT 0,
    furnace_ready_ts INTEGER DEFAULT 0,     -- 六节:炉子煮水批次,0=空闲,>0=还在煮/已煮好待收
    has_advanced_workbench INTEGER DEFAULT 0,
    farmland_plots   INTEGER DEFAULT 1,     -- 五节:自带一块初始田地,升级增加
    farm_ready_ts    INTEGER DEFAULT 0,     -- 五节:田地下一次可收获的时间戳
    has_greenhouse   INTEGER DEFAULT 0,     -- B档62条:温室,解锁稀有作物种植位
    has_vaccine      INTEGER DEFAULT 0,     -- 11.3:解药研发,每个庇护所各自独立点出来
    has_endgame_device INTEGER DEFAULT 0,   -- 十二节:归途装置,建好后靠 resonance_material 攒进度
    has_hunting_trap INTEGER DEFAULT 0,     -- B档60条:狩猎陷阱(和防御用的陷阱是两回事)
    hunting_trap_ready_ts INTEGER DEFAULT 0,
    has_animal_pen   INTEGER DEFAULT 0,     -- 驯养:兽栏,驯服的动物必须带回来养
    storage_crates   INTEGER DEFAULT 0,     -- 二十六节:储物箱扩容,房子改建成庇护所时会带过来
    has_workbench    INTEGER DEFAULT 0,     -- 二十九节:基础工作台,房子有的话改建成庇护所时会带过来,和高级工作台是两回事
    repeller_level   INTEGER DEFAULT 0,     -- 二十九节:驱赶器等级,0=没建,1-3级压低所在及周边区域的噪声/威胁上限
    has_mega_warehouse INTEGER DEFAULT 0,   -- 二十九节:超大仓库,一次性+500容量,不能叠加,和储物箱是两条路
    abandoned        INTEGER DEFAULT 0,
    abandoned_ts     INTEGER DEFAULT 0,     -- 十.1:成员数降到0的时间,配合清理逻辑算废弃期满
    completed_ending INTEGER DEFAULT 0,     -- 十二.2:终局完结标记
    created_ts       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS shelter_inventory (
    shelter_id   INTEGER NOT NULL,
    resource_key TEXT NOT NULL,
    amount       INTEGER DEFAULT 0,
    PRIMARY KEY (shelter_id, resource_key)
);

-- 十.2:死亡遗物点,24小时后清理(和普通资源同一刷新周期复用逻辑)
CREATE TABLE IF NOT EXISTS death_loot (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tile_x       INTEGER NOT NULL,
    tile_y       INTEGER NOT NULL,
    resource_key TEXT NOT NULL,
    amount       INTEGER NOT NULL,
    dropped_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS action_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id  INTEGER,
    action        TEXT,
    detail        TEXT,
    created_ts    INTEGER DEFAULT 0
);

-- 五节:庇护所成员死亡通知(死者身份+死亡地点+死亡时间)
CREATE TABLE IF NOT EXISTS shelter_notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shelter_id  INTEGER NOT NULL,
    message     TEXT NOT NULL,
    created_ts  INTEGER DEFAULT 0
);

-- 钓鱼图鉴:每个角色抓到过哪些鱼种、抓到过几次
CREATE TABLE IF NOT EXISTS character_fish_log (
    character_id   INTEGER NOT NULL,
    fish_key       TEXT NOT NULL,
    catch_count    INTEGER DEFAULT 0,
    first_caught_ts INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, fish_key)
);

-- 全局世界状态,单行(昼夜/天数,八.2全局统一时钟)
CREATE TABLE IF NOT EXISTS world_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    day_count     INTEGER DEFAULT 1,
    day_started_ts INTEGER DEFAULT 0,
    last_tick_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- B档59条:流动商人,钱包货币目前唯一的消耗出口,定期刷新库存
CREATE TABLE IF NOT EXISTS merchant_stock (
    resource_key TEXT PRIMARY KEY,
    price        INTEGER NOT NULL,
    stock_amount INTEGER NOT NULL
);

-- v0.3:每日个人目标。无连续签到，漏一天不会损失任何东西。
CREATE TABLE IF NOT EXISTS daily_goal_progress (
    character_id INTEGER NOT NULL,
    day_count    INTEGER NOT NULL,
    goal_key     TEXT NOT NULL,
    progress     INTEGER DEFAULT 0,
    claimed      INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, day_count, goal_key)
);

-- v0.3:庇护所成员留言与系统编年史共用一张时间线。
CREATE TABLE IF NOT EXISTS shelter_feed (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    shelter_id   INTEGER NOT NULL,
    character_id INTEGER,
    entry_type   TEXT NOT NULL DEFAULT 'message', -- message / chronicle
    author_name  TEXT DEFAULT '',
    content      TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_shelter_feed ON shelter_feed(shelter_id, id DESC);

-- v0.3:每天每个庇护所一顿共同晚餐，成员共同捐生鲜。
CREATE TABLE IF NOT EXISTS shelter_feasts (
    shelter_id   INTEGER NOT NULL,
    day_count    INTEGER NOT NULL,
    target       INTEGER NOT NULL,
    contributed  INTEGER DEFAULT 0,
    completed    INTEGER DEFAULT 0,
    completed_ts INTEGER DEFAULT 0,
    PRIMARY KEY (shelter_id, day_count)
);

-- v0.4:移动途中一次只挂一个探索抉择，处理完才继续。
CREATE TABLE IF NOT EXISTS pending_world_events (
    character_id INTEGER PRIMARY KEY,
    event_key    TEXT NOT NULL,
    tile_x       INTEGER NOT NULL,
    tile_y       INTEGER NOT NULL,
    created_ts   INTEGER DEFAULT 0
);

-- v0.4:共享地图情报，同一角色在同一格只保留最新一条。
CREATE TABLE IF NOT EXISTS map_notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    author_name  TEXT NOT NULL,
    tile_x       INTEGER NOT NULL,
    tile_y       INTEGER NOT NULL,
    content      TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    UNIQUE(character_id, tile_x, tile_y)
);
CREATE INDEX IF NOT EXISTS idx_map_notes_tile ON map_notes(tile_x, tile_y);

-- 三十节:邮箱——纯文字消息，不带任何物品/货币附件，物资交换只能面对面走既有的存取/藏点系统。
CREATE TABLE IF NOT EXISTS player_mail (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    from_character_id  INTEGER NOT NULL,
    from_name          TEXT NOT NULL,
    to_character_id    INTEGER NOT NULL,
    subject            TEXT DEFAULT '',
    body               TEXT NOT NULL,
    is_read            INTEGER DEFAULT 0,
    action_type        TEXT DEFAULT '',     -- 二十九节:邮件内嵌操作按钮,目前只有claim_dynamic_quest一种
    action_ref         INTEGER DEFAULT 0,   -- 配合action_type用,比如对应的dynamic_personal_quests.id
    created_ts         INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_player_mail_to ON player_mail(to_character_id, is_read);

-- v1.9:全地图按5x5地块划分区域。噪声是短期信号，威胁是长期尸群压力。
CREATE TABLE IF NOT EXISTS map_regions (
    region_x       INTEGER NOT NULL,
    region_y       INTEGER NOT NULL,
    noise          INTEGER DEFAULT 0,
    threat         INTEGER DEFAULT 0,
    last_decay_day INTEGER DEFAULT 1,
    updated_ts     INTEGER DEFAULT 0,
    PRIMARY KEY (region_x, region_y)
);
CREATE TABLE IF NOT EXISTS region_threat_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    region_x     INTEGER NOT NULL,
    region_y     INTEGER NOT NULL,
    character_id INTEGER,
    event_key    TEXT NOT NULL,
    noise_added  INTEGER DEFAULT 0,
    threat_added INTEGER DEFAULT 0,
    detail       TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_region_threat_events_region
ON region_threat_events(region_x,region_y,id DESC);

-- v2.0:房屋与庇护所共用的独立电网。owner_type只允许house/shelter。
CREATE TABLE IF NOT EXISTS power_grids (
    owner_type          TEXT NOT NULL,
    owner_id            INTEGER NOT NULL,
    generator_level     INTEGER DEFAULT 0,
    charge              INTEGER DEFAULT 0,
    mode                TEXT DEFAULT 'balanced',
    damaged             INTEGER DEFAULT 0,
    last_generation_day INTEGER DEFAULT 0,
    updated_ts          INTEGER DEFAULT 0,
    PRIMARY KEY (owner_type, owner_id)
);
CREATE TABLE IF NOT EXISTS power_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type   TEXT NOT NULL,
    owner_id     INTEGER NOT NULL,
    character_id INTEGER,
    event_key    TEXT NOT NULL,
    power_change INTEGER DEFAULT 0,
    detail       TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_power_logs_owner
ON power_logs(owner_type,owner_id,id DESC);

-- 二十九节:被动资源采集机(打矿机/自动伐木机/自动采石机)，房子或庇护所都能装，
-- 房子改建成庇护所时owner_type/owner_id会跟着迁移，不会随房子被删除而消失。
CREATE TABLE IF NOT EXISTS resource_extractors (
    owner_type   TEXT NOT NULL,
    owner_id     INTEGER NOT NULL,
    kind         TEXT NOT NULL,       -- metal_driller / auto_lumberjack / auto_quarry
    level        INTEGER DEFAULT 1,
    ready_ts     INTEGER DEFAULT 0,
    PRIMARY KEY (owner_type, owner_id, kind)
);

-- v0.4:每3个游戏日一期的全服共同目标。
CREATE TABLE IF NOT EXISTS world_goals (
    cycle_id     INTEGER PRIMARY KEY,
    goal_key     TEXT NOT NULL,
    resource_key TEXT,
    target       INTEGER NOT NULL,
    progress     INTEGER DEFAULT 0,
    completed    INTEGER DEFAULT 0,
    completed_ts INTEGER DEFAULT 0
);

-- v0.4:系统自动写入的世界日报/重大新闻。
CREATE TABLE IF NOT EXISTS world_news (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_count    INTEGER NOT NULL,
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_world_news_day_title ON world_news(day_count, title);

-- v0.4:求购物资委托。发布时钱包报酬先托管，完成后自动支付。
CREATE TABLE IF NOT EXISTS commissions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_character_id INTEGER NOT NULL,
    creator_name         TEXT NOT NULL,
    resource_key         TEXT NOT NULL,
    amount               INTEGER NOT NULL,
    reward               INTEGER NOT NULL,
    status               TEXT DEFAULT 'open', -- open / completed / cancelled
    completed_by         INTEGER,
    completed_by_name    TEXT,
    created_ts           INTEGER DEFAULT 0,
    completed_ts         INTEGER DEFAULT 0
);

-- v0.5:动物名字、陪伴起点与共同战绩。
CREATE TABLE IF NOT EXISTS tamed_animal_profiles (
    character_id INTEGER PRIMARY KEY,
    animal_key   TEXT NOT NULL,
    custom_name  TEXT NOT NULL,
    tamed_ts     INTEGER DEFAULT 0,
    battles_won  INTEGER DEFAULT 0,
    resources_produced INTEGER DEFAULT 0
);

-- v0.5:附近玩家可见的救援信号，完成或撤销后保留记录。
CREATE TABLE IF NOT EXISTS rescue_signals (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_character_id INTEGER NOT NULL,
    requester_name       TEXT NOT NULL,
    tile_x               INTEGER NOT NULL,
    tile_y               INTEGER NOT NULL,
    message              TEXT NOT NULL,
    status               TEXT DEFAULT 'open', -- open / completed / cancelled
    responder_character_id INTEGER,
    responder_name       TEXT,
    created_ts           INTEGER DEFAULT 0,
    completed_ts         INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rescue_open ON rescue_signals(status, tile_x, tile_y);

-- v0.6:庇护所贡献与兑换记录。
CREATE TABLE IF NOT EXISTS shelter_contributions (
    character_id INTEGER NOT NULL,
    shelter_id   INTEGER NOT NULL,
    points       INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, shelter_id)
);
CREATE TABLE IF NOT EXISTS shelter_reward_unlocks (
    character_id INTEGER NOT NULL,
    reward_key   TEXT NOT NULL,
    unlocked_ts  INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, reward_key)
);

-- v0.6:公开串门记录，每人每天对同一庇护所计一次。
CREATE TABLE IF NOT EXISTS shelter_visits (
    visitor_character_id INTEGER NOT NULL,
    shelter_id           INTEGER NOT NULL,
    day_count            INTEGER NOT NULL,
    visitor_name         TEXT NOT NULL,
    message              TEXT DEFAULT '',
    visited_ts           INTEGER DEFAULT 0,
    PRIMARY KEY (visitor_character_id, shelter_id, day_count)
);

-- v0.6:三日无线电寻宝活动与个人棋盘进度。
CREATE TABLE IF NOT EXISTS radio_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    status      TEXT DEFAULT 'active',
    starts_ts   INTEGER DEFAULT 0,
    ends_ts     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS radio_event_progress (
    event_id     INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    position     INTEGER DEFAULT 0,
    rolls_day    INTEGER DEFAULT 0,
    rolls_used   INTEGER DEFAULT 0,
    finished     INTEGER DEFAULT 0,
    PRIMARY KEY (event_id, character_id)
);

-- v0.6:全服持续性灾害；每天不同岗位都可贡献有限次数。
CREATE TABLE IF NOT EXISTS world_disasters (
    cycle_id    INTEGER PRIMARY KEY,
    disaster_key TEXT NOT NULL,
    name        TEXT NOT NULL,
    hp          INTEGER NOT NULL,
    max_hp      INTEGER NOT NULL,
    status      TEXT DEFAULT 'active',
    starts_ts   INTEGER DEFAULT 0,
    ends_ts     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS disaster_contributions (
    cycle_id     INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    day_count    INTEGER NOT NULL,
    actions_used INTEGER DEFAULT 0,
    total_points INTEGER DEFAULT 0,
    PRIMARY KEY (cycle_id, character_id, day_count)
);

-- v0.6:首页滚动公告。
CREATE TABLE IF NOT EXISTS server_announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,
    created_ts  INTEGER DEFAULT 0
);

-- v0.7:每日一次免费废土手气，随机结果只给惊喜、不制造惩罚。
CREATE TABLE IF NOT EXISTS daily_fortune_draws (
    character_id INTEGER NOT NULL,
    day_count    INTEGER NOT NULL,
    style        TEXT NOT NULL,
    result_key   TEXT NOT NULL,
    result_text  TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, day_count)
);

-- v0.8:个人长期主线“北辰信号”与不设期限的支线任务。
CREATE TABLE IF NOT EXISTS story_states (
    character_id INTEGER PRIMARY KEY,
    chapter      INTEGER DEFAULT 1,
    completed    INTEGER DEFAULT 0,
    updated_ts   INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS story_counters (
    character_id INTEGER NOT NULL,
    counter_key  TEXT NOT NULL,
    value        INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, counter_key)
);
CREATE TABLE IF NOT EXISTS side_quests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    quest_key    TEXT NOT NULL,
    progress     INTEGER DEFAULT 0,
    target       INTEGER NOT NULL,
    status       TEXT DEFAULT 'active',
    created_ts   INTEGER DEFAULT 0,
    completed_ts INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_side_quests_active ON side_quests(character_id, status);

-- v1.0/v1.7:每个角色每天一次的北辰个人行动。最快第8日取得终局设计图；
-- 真正组装北辰归航信标后才完成主线，错过不惩罚。
CREATE TABLE IF NOT EXISTS story_daily_actions (
    character_id INTEGER NOT NULL,
    survivor_day INTEGER NOT NULL,
    action_key    TEXT NOT NULL,
    outcome_text TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, survivor_day)
);

-- v1.1:沉浸生活层。
CREATE TABLE IF NOT EXISTS npc_relationships (
    character_id INTEGER NOT NULL,
    npc_key      TEXT NOT NULL,
    trust        INTEGER DEFAULT 0,
    contact_count INTEGER DEFAULT 0,
    last_line    TEXT DEFAULT '',
    updated_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, npc_key)
);
CREATE TABLE IF NOT EXISTS npc_contact_logs (
    character_id INTEGER NOT NULL,
    survivor_day INTEGER NOT NULL,
    npc_key      TEXT NOT NULL,
    line         TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, survivor_day)
);
CREATE TABLE IF NOT EXISTS character_tags (
    character_id INTEGER NOT NULL,
    tag_key      TEXT NOT NULL,
    detail       TEXT DEFAULT '',
    earned_ts    INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, tag_key)
);
CREATE TABLE IF NOT EXISTS character_location_memories (
    character_id INTEGER NOT NULL,
    tile_x       INTEGER NOT NULL,
    tile_y       INTEGER NOT NULL,
    first_visited_ts INTEGER DEFAULT 0,
    last_visited_ts  INTEGER DEFAULT 0,
    visit_count  INTEGER DEFAULT 1,
    last_memory  TEXT DEFAULT '',
    PRIMARY KEY (character_id, tile_x, tile_y)
);
CREATE TABLE IF NOT EXISTS character_room_corners (
    character_id INTEGER PRIMARY KEY,
    corner_key   TEXT NOT NULL,
    custom_note  TEXT DEFAULT '',
    updated_ts   INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bedtime_broadcasts (
    character_id INTEGER NOT NULL,
    survivor_day INTEGER NOT NULL,
    broadcast_text TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, survivor_day)
);
CREATE TABLE IF NOT EXISTS story_choices (
    character_id INTEGER NOT NULL,
    chapter      INTEGER NOT NULL,
    choice_key   TEXT NOT NULL,
    choice_label TEXT NOT NULL,
    trace_text   TEXT NOT NULL,
    chosen_ts    INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, chapter)
);

-- v0.9:语言cosplay角色身份层。背景/特质选定后锁定，外号/皮相/头像/自述可修改。
CREATE TABLE IF NOT EXISTS character_profiles (
    character_id  INTEGER PRIMARY KEY,
    nickname      TEXT DEFAULT '',
    face_claim    TEXT DEFAULT '',
    background_key TEXT NOT NULL,
    trait_a       TEXT NOT NULL,
    trait_b       TEXT NOT NULL,
    avatar_key    TEXT DEFAULT 'avatar-01',
    bio           TEXT DEFAULT '',
    created_ts    INTEGER DEFAULT 0,
    updated_ts    INTEGER DEFAULT 0
);

-- v1.2:玩家关系、婚姻与家族传承。关系对使用小ID/大ID规范化，避免重复夫妻记录。
CREATE TABLE IF NOT EXISTS player_bonds (
    char_a       INTEGER NOT NULL,
    char_b       INTEGER NOT NULL,
    affinity     INTEGER DEFAULT 0,
    married      INTEGER DEFAULT 0,
    married_ts   INTEGER DEFAULT 0,
    separated_ts INTEGER DEFAULT 0,
    PRIMARY KEY (char_a, char_b)
);

-- 十九节:结伴同行——不需要庇护所、不需要羁绊值的轻量临时组队，随时可结束，无惩罚。
CREATE TABLE IF NOT EXISTS companion_bonds (
    char_a       INTEGER NOT NULL,
    char_b       INTEGER NOT NULL,
    status       TEXT DEFAULT 'pending', -- pending / active / ended
    requested_by INTEGER NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    resolved_ts  INTEGER DEFAULT 0,
    PRIMARY KEY (char_a, char_b)
);

CREATE TABLE IF NOT EXISTS bond_interactions (
    from_char    INTEGER NOT NULL,
    to_char      INTEGER NOT NULL,
    survivor_day INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (from_char, to_char, survivor_day)
);

CREATE TABLE IF NOT EXISTS family_proposals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_type TEXT NOT NULL, -- marriage / child
    from_char     INTEGER NOT NULL,
    to_char       INTEGER NOT NULL,
    ring_key      TEXT DEFAULT '',
    child_name    TEXT DEFAULT '',
    status        TEXT DEFAULT 'pending',
    created_ts    INTEGER DEFAULT 0,
    resolved_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_family_proposals_to ON family_proposals(to_char, status);

CREATE TABLE IF NOT EXISTS children (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_a               INTEGER NOT NULL,
    parent_b               INTEGER NOT NULL,
    name                   TEXT NOT NULL,
    born_ts                INTEGER DEFAULT 0,
    status                 TEXT DEFAULT 'alive', -- alive / dead / heir
    hp                     INTEGER DEFAULT 100,
    care_points            INTEGER DEFAULT 0,
    stat_str               INTEGER DEFAULT 0,
    stat_spd               INTEGER DEFAULT 0,
    stat_int               INTEGER DEFAULT 0,
    stat_luck              INTEGER DEFAULT 0,
    trait_a                TEXT DEFAULT '',
    trait_b                TEXT DEFAULT '',
    tile_x                 INTEGER DEFAULT 0,
    tile_y                 INTEGER DEFAULT 0,
    last_explore_age       INTEGER DEFAULT -1,
    last_needs_age         INTEGER DEFAULT -1,
    death_reason           TEXT DEFAULT '',
    successor_character_id INTEGER,
    created_ts             INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_children_parents ON children(parent_a, parent_b, status);

CREATE TABLE IF NOT EXISTS child_inventory (
    child_id     INTEGER NOT NULL,
    resource_key TEXT NOT NULL,
    amount       INTEGER DEFAULT 0,
    PRIMARY KEY (child_id, resource_key)
);

CREATE TABLE IF NOT EXISTS child_care_logs (
    child_id            INTEGER NOT NULL,
    parent_character_id INTEGER NOT NULL,
    survivor_day        INTEGER NOT NULL,
    care_kind           TEXT NOT NULL,
    created_ts          INTEGER DEFAULT 0,
    PRIMARY KEY (child_id, parent_character_id, survivor_day)
);

CREATE TABLE IF NOT EXISTS child_exploration_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id     INTEGER NOT NULL,
    age_day      INTEGER NOT NULL,
    outcome      TEXT NOT NULL,
    detail       TEXT NOT NULL,
    hp_change    INTEGER DEFAULT 0,
    resource_key TEXT DEFAULT '',
    amount       INTEGER DEFAULT 0,
    created_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_child_explore_logs ON child_exploration_logs(child_id, id DESC);

CREATE TABLE IF NOT EXISTS child_help_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id     INTEGER NOT NULL,
    age_day      INTEGER NOT NULL,
    need_key     TEXT NOT NULL, -- care / food / water / medicine
    message      TEXT NOT NULL,
    status       TEXT DEFAULT 'open',
    created_ts   INTEGER DEFAULT 0,
    resolved_ts  INTEGER DEFAULT 0,
    UNIQUE (child_id, age_day, need_key)
);

-- v1.3:家族社会关系、相册、成长节点与传承遗物。
CREATE TABLE IF NOT EXISTS close_relationships (
    char_a      INTEGER NOT NULL,
    char_b      INTEGER NOT NULL,
    role        TEXT NOT NULL, -- best_friend / sworn_family
    status      TEXT DEFAULT 'pending',
    requested_by INTEGER NOT NULL,
    created_ts  INTEGER DEFAULT 0,
    resolved_ts INTEGER DEFAULT 0,
    PRIMARY KEY (char_a, char_b, role)
);

CREATE TABLE IF NOT EXISTS child_guardians (
    child_id          INTEGER NOT NULL,
    guardian_character_id INTEGER NOT NULL,
    status            TEXT DEFAULT 'pending',
    requested_by      INTEGER NOT NULL,
    created_ts        INTEGER DEFAULT 0,
    resolved_ts       INTEGER DEFAULT 0,
    PRIMARY KEY (child_id, guardian_character_id)
);

CREATE TABLE IF NOT EXISTS child_growth_choices (
    child_id     INTEGER NOT NULL,
    milestone    INTEGER NOT NULL,
    choice_key   TEXT NOT NULL,
    choice_label TEXT NOT NULL,
    story_text   TEXT NOT NULL,
    chosen_by    INTEGER NOT NULL,
    chosen_ts    INTEGER DEFAULT 0,
    PRIMARY KEY (child_id, milestone)
);

CREATE TABLE IF NOT EXISTS family_album (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER,
    related_character_id INTEGER,
    child_id     INTEGER,
    event_key    TEXT NOT NULL,
    title        TEXT NOT NULL,
    story_text   TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_family_album_character ON family_album(character_id, id DESC);

CREATE TABLE IF NOT EXISTS family_heirlooms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_character_id INTEGER NOT NULL,
    founder_character_id INTEGER NOT NULL,
    custom_name   TEXT NOT NULL,
    item_key      TEXT NOT NULL,
    generation    INTEGER DEFAULT 1,
    rescue_count  INTEGER DEFAULT 0,
    battle_count  INTEGER DEFAULT 0,
    story_text    TEXT DEFAULT '',
    created_ts    INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS heirloom_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    heirloom_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    event_text  TEXT NOT NULL,
    created_ts  INTEGER DEFAULT 0
);

-- v1.3:离线远征与经历驱动支线。
CREATE TABLE IF NOT EXISTS expeditions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    route_key    TEXT NOT NULL,
    strategy     TEXT NOT NULL,
    companion_character_id INTEGER,
    child_id     INTEGER,
    status       TEXT DEFAULT 'active',
    depart_ts    INTEGER DEFAULT 0,
    return_ts    INTEGER DEFAULT 0,
    result_key   TEXT DEFAULT '',
    result_text  TEXT DEFAULT '',
    hp_change    INTEGER DEFAULT 0,
    reward_key   TEXT DEFAULT '',
    reward_amount INTEGER DEFAULT 0,
    resolved_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dynamic_personal_quests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    source_key   TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL,
    objective_key TEXT NOT NULL,
    target       INTEGER DEFAULT 1,
    progress     INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'active',
    reward_key   TEXT DEFAULT 'wallet',
    reward_amount INTEGER DEFAULT 10,
    notified     INTEGER DEFAULT 0,        -- 二十九节:达标提醒邮件是否已经发过,避免重复发信
    created_ts   INTEGER DEFAULT 0,
    completed_ts INTEGER DEFAULT 0
);

-- v1.3:每天一个可共同回应的庇护所生活事件。
CREATE TABLE IF NOT EXISTS shelter_life_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    shelter_id   INTEGER NOT NULL,
    day_count    INTEGER NOT NULL,
    event_key    TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL,
    status       TEXT DEFAULT 'open',
    winning_option TEXT DEFAULT '',
    resolved_ts  INTEGER DEFAULT 0,
    UNIQUE (shelter_id, day_count)
);
CREATE TABLE IF NOT EXISTS shelter_life_votes (
    event_id     INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    option_key   TEXT NOT NULL,
    voted_ts     INTEGER DEFAULT 0,
    PRIMARY KEY (event_id, character_id)
);

-- v1.4:个人生活工坊——烹饪、酿造、缝纫与小型畜牧。
CREATE TABLE IF NOT EXISTS personal_homesteads (
    character_id INTEGER PRIMARY KEY,
    has_kitchen  INTEGER DEFAULT 0,
    has_brewery  INTEGER DEFAULT 0,
    has_sewing   INTEGER DEFAULT 0,
    has_livestock INTEGER DEFAULT 0,
    cooking_skill INTEGER DEFAULT 0,
    brewing_skill INTEGER DEFAULT 0,
    sewing_skill INTEGER DEFAULT 0,
    created_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS life_crafting_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    craft_type   TEXT NOT NULL,
    recipe_key   TEXT NOT NULL,
    detail       TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS drink_batches (
    character_id INTEGER PRIMARY KEY,
    recipe_key   TEXT NOT NULL,
    ready_ts     INTEGER DEFAULT 0,
    started_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS personal_outfits (
    character_id INTEGER NOT NULL,
    outfit_key   TEXT NOT NULL,
    amount       INTEGER DEFAULT 0,
    equipped     INTEGER DEFAULT 0,
    crafted_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, outfit_key)
);
CREATE TABLE IF NOT EXISTS child_outfits (
    child_id    INTEGER PRIMARY KEY,
    outfit_key  TEXT NOT NULL,
    gifted_by   INTEGER NOT NULL,
    gifted_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS personal_livestock (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    species_key  TEXT NOT NULL,
    custom_name  TEXT NOT NULL,
    born_ts      INTEGER DEFAULT 0,
    health       INTEGER DEFAULT 100,
    fed_age_day  INTEGER DEFAULT -1,
    last_settled_age INTEGER DEFAULT -1,
    last_produce_age INTEGER DEFAULT -1,
    status       TEXT DEFAULT 'alive',
    parent_a     INTEGER,
    parent_b     INTEGER,
    created_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_personal_livestock_owner ON personal_livestock(character_id, status);

CREATE TABLE IF NOT EXISTS livestock_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id    INTEGER NOT NULL,
    event_key    TEXT NOT NULL,
    detail       TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS livestock_breeding_logs (
    character_id INTEGER NOT NULL,
    species_key  TEXT NOT NULL,
    age_day      INTEGER NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, species_key, age_day)
);

-- v1.5:个人生存技术——污染检测、弹药复装、补给藏点与废墟拆解。
CREATE TABLE IF NOT EXISTS personal_survival_workshops (
    character_id INTEGER PRIMARY KEY,
    has_water_tester INTEGER DEFAULT 0,
    has_ammo_press INTEGER DEFAULT 0,
    reload_skill INTEGER DEFAULT 0,
    water_skill  INTEGER DEFAULT 0,
    created_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tested_water_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id  INTEGER NOT NULL,
    contamination_key TEXT NOT NULL,
    source_x      INTEGER DEFAULT 0,
    source_y      INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'tested',
    tested_ts     INTEGER DEFAULT 0,
    treated_ts    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS weapon_maintenance (
    character_id INTEGER PRIMARY KEY,
    maintained_battles INTEGER DEFAULT 0,
    clean_count  INTEGER DEFAULT 0,
    last_cleaned_ts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS supply_caches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_character_id INTEGER NOT NULL,
    owner_user_id INTEGER NOT NULL,
    custom_name   TEXT NOT NULL,
    tile_x        INTEGER NOT NULL,
    tile_y        INTEGER NOT NULL,
    access_mode   TEXT DEFAULT 'private', -- private / family
    capacity      INTEGER DEFAULT 50,
    condition     INTEGER DEFAULT 100,
    created_ts    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_supply_caches_tile ON supply_caches(tile_x,tile_y);
CREATE TABLE IF NOT EXISTS supply_cache_inventory (
    cache_id      INTEGER NOT NULL,
    resource_key  TEXT NOT NULL,
    amount        INTEGER DEFAULT 0,
    PRIMARY KEY (cache_id, resource_key)
);
CREATE TABLE IF NOT EXISTS supply_cache_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_id      INTEGER NOT NULL,
    character_id  INTEGER NOT NULL,
    action_key    TEXT NOT NULL,
    detail        TEXT NOT NULL,
    created_ts    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ruin_sites (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tile_x        INTEGER NOT NULL,
    tile_y        INTEGER NOT NULL,
    site_type     TEXT NOT NULL,
    integrity     INTEGER DEFAULT 100,
    total_noise   INTEGER DEFAULT 0,
    discovered_by INTEGER NOT NULL,
    discovered_ts INTEGER DEFAULT 0,
    UNIQUE (tile_x, tile_y)
);
CREATE TABLE IF NOT EXISTS ruin_compartments (
    site_id       INTEGER NOT NULL,
    part_key      TEXT NOT NULL,
    dismantled    INTEGER DEFAULT 0,
    dismantled_by INTEGER,
    dismantled_ts INTEGER DEFAULT 0,
    PRIMARY KEY (site_id, part_key)
);
CREATE TABLE IF NOT EXISTS ruin_dismantle_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id       INTEGER NOT NULL,
    character_id  INTEGER NOT NULL,
    part_key      TEXT NOT NULL,
    noise         INTEGER DEFAULT 0,
    result_text   TEXT NOT NULL,
    created_ts    INTEGER DEFAULT 0
);

-- v1.6:娱乐与精神状态。娱乐按角色幸存日温和下降；崩溃一天最多结算一次。
CREATE TABLE IF NOT EXISTS character_wellbeing (
    character_id        INTEGER PRIMARY KEY,
    recreation          INTEGER DEFAULT 70,
    last_settled_day    INTEGER DEFAULT 1,
    mental_state        TEXT DEFAULT 'stable',
    breakdown_count     INTEGER DEFAULT 0,
    last_breakdown_day  INTEGER DEFAULT 0,
    last_breakdown_text TEXT DEFAULT '',
    updated_ts          INTEGER DEFAULT 0
);

-- v2.1:生活玩法为当天下一场战斗提供温和加成；伤势只影响选择，不会离线致死。
CREATE TABLE IF NOT EXISTS character_combat_preparations (
    character_id INTEGER PRIMARY KEY,
    survivor_day INTEGER NOT NULL,
    food_key     TEXT DEFAULT '',
    drink_key    TEXT DEFAULT '',
    updated_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS character_injuries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    injury_key   TEXT NOT NULL,
    source_text  TEXT NOT NULL,
    status       TEXT DEFAULT 'active',
    created_ts   INTEGER DEFAULT 0,
    treated_ts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_character_injuries_active
ON character_injuries(character_id,status);
CREATE TABLE IF NOT EXISTS recreation_activities (
    character_id INTEGER NOT NULL,
    survivor_day INTEGER NOT NULL,
    activity_key TEXT NOT NULL,
    gain         INTEGER DEFAULT 0,
    detail       TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, survivor_day)
);

-- 支线可每天无奖励换掉一条，避免多人/后期目标永久堵住任务栏。
CREATE TABLE IF NOT EXISTS side_quest_rerolls (
    character_id  INTEGER NOT NULL,
    survivor_day  INTEGER NOT NULL,
    old_quest_key TEXT NOT NULL,
    created_ts    INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, survivor_day)
);

-- v1.7:每天选择一种生活方向。它只提供温和加成，不选择也没有惩罚。
CREATE TABLE IF NOT EXISTS daily_plans (
    character_id INTEGER NOT NULL,
    survivor_day INTEGER NOT NULL,
    plan_key     TEXT NOT NULL,
    created_ts   INTEGER DEFAULT 0,
    PRIMARY KEY (character_id, survivor_day)
);
