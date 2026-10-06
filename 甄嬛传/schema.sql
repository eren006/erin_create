-- 甄嬛传·紫禁城 数据库结构（SQLite）
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    stat_roll_reign INTEGER NOT NULL DEFAULT 0,
    stat_roll TEXT NOT NULL DEFAULT '',
    east_palace_reign INTEGER NOT NULL DEFAULT 0,
    east_palace_old INTEGER NOT NULL DEFAULT 0,
    password_hash TEXT NOT NULL,
    qq_number TEXT NOT NULL DEFAULT '',
    drug_ready_day INTEGER NOT NULL DEFAULT 0,
    lethal_ready_day INTEGER NOT NULL DEFAULT 0,
    nameless_ready_day INTEGER NOT NULL DEFAULT 0,  -- 「无名」冷却，死后重建也不重置
    created_ts    INTEGER NOT NULL
);

-- 玩家和 NPC 妃嫔共用一张表：user_id 为空、npc_key 非空的是 NPC
CREATE TABLE IF NOT EXISTS consorts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER UNIQUE,
    npc_key          TEXT UNIQUE,
    entry_origin     TEXT NOT NULL DEFAULT 'new',
    bed_daily_day INTEGER NOT NULL DEFAULT 0,
    bed_daily_count INTEGER NOT NULL DEFAULT 0,
    influence        INTEGER NOT NULL DEFAULT 0,
    unfavored_days   INTEGER NOT NULL DEFAULT 0,
    ill_care         TEXT NOT NULL DEFAULT 'normal',
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
    energy           INTEGER NOT NULL DEFAULT 8,

    status           TEXT NOT NULL DEFAULT 'xiunv', -- xiunv / normal / confined(禁足) / cold(冷宫) / dead(已故)
    status_until_day INTEGER NOT NULL DEFAULT 0,
    rank_before_cold INTEGER NOT NULL DEFAULT 0,
    pregnancy_started_ts REAL NOT NULL DEFAULT 0,
    pregnant_since   INTEGER NOT NULL DEFAULT 0,    -- 0=未有孕，否则为有孕那天

    arts             TEXT NOT NULL DEFAULT '{}',    -- {"琴": 3, ...} 各才艺修习次数
    secret           TEXT NOT NULL DEFAULT 'lover',
    secret_revealed  INTEGER NOT NULL DEFAULT 0,
    eyes_until_day   INTEGER NOT NULL DEFAULT 0,    -- 眼线有效到哪天（含）
    seek_bonus       INTEGER NOT NULL DEFAULT 0,    -- 今晚翻牌加成，结算后清零
    greet_day        INTEGER NOT NULL DEFAULT 0,
    missed_greet     INTEGER NOT NULL DEFAULT 0,
    entered_day      INTEGER NOT NULL DEFAULT 0,    -- 殿选中选那天
    bedded_count     INTEGER NOT NULL DEFAULT 0,
    pregnancy_misses INTEGER NOT NULL DEFAULT 0,
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
    drugged_until_day INTEGER NOT NULL DEFAULT 0,
    drugged_day      INTEGER NOT NULL DEFAULT 0,    -- 上次被下药得手是哪天（之后 2 天不能再被下药）
    drug_ledger      INTEGER NOT NULL DEFAULT 0,    -- 在暗柜买药时被内务府记了几笔（查案搜宫时用）
    hall             TEXT NOT NULL DEFAULT '',      -- 住在 palace 的哪一间：main 正殿 / east 东配殿 / west 西配殿 / back 后殿；空=没有住处（冷宫、已故）
    housing_waiting   TEXT NOT NULL DEFAULT '',      -- main/side：已通知等候安置，腾房后清空
    discipline_ready_day INTEGER NOT NULL DEFAULT 0, -- 主位管教配殿的冷却：到这天才能再罚/赏

    guide_step       INTEGER NOT NULL DEFAULT 0,    -- 教引嬷嬷引导线走到第几步；-1=跳过，等于步数上限=走完了
    guide_progress   TEXT NOT NULL DEFAULT '[]',    -- 当前这一步已经做到的子项
    guide_tips       TEXT NOT NULL DEFAULT '[]',    -- 已经出现过的「遇事提点」，同一件事只说一次

    ill_day          INTEGER NOT NULL DEFAULT 0,    -- 病重：哪天病倒的，0=没病；走和中毒一样的生死判定
    ill_treatment    INTEGER NOT NULL DEFAULT 0,    -- 0=没请太医 1=请了
    weak_days        INTEGER NOT NULL DEFAULT 0,    -- 连续体质<25 的天数，够 3 天染病
    postpartum_until INTEGER NOT NULL DEFAULT 0,    -- 小产/难产后这几天内，每晚有概率染病

    aggression       REAL NOT NULL DEFAULT 0,       -- 仅 NPC：每晚出手概率
    intro            TEXT NOT NULL DEFAULT '',
    created_ts       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS game_state (
    drug_balance_version INTEGER NOT NULL DEFAULT 0,
    drug_rules_version INTEGER NOT NULL DEFAULT 0,
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    day              INTEGER NOT NULL DEFAULT 1,
    last_bed_round_key TEXT NOT NULL DEFAULT '',
    last_settle_date TEXT NOT NULL DEFAULT '',
    last_midday_promotion_date TEXT NOT NULL DEFAULT '',
    emperor_mood     TEXT NOT NULL DEFAULT '平和',
    emperor_pref     TEXT NOT NULL DEFAULT '琴',
    last_bed_id      INTEGER NOT NULL DEFAULT 0,
    last_bed_day     INTEGER NOT NULL DEFAULT 0,
    last_energy_key  TEXT NOT NULL DEFAULT '',            -- 最近一次按时回精力的时点
    last_bed_ids     TEXT NOT NULL DEFAULT '[]',     -- 最近一轮被翻牌的全部人（可能不止一位）
    last_bed_pool    TEXT NOT NULL DEFAULT '[]',    -- 当晚递上去的绿头牌，「昨夜宫中」回放用
    reign_no         INTEGER NOT NULL DEFAULT 1,     -- 第几届（一位皇上一届）
    reign_start_day  INTEGER NOT NULL DEFAULT 1,
    emperor_start_age INTEGER NOT NULL DEFAULT 20,   -- 这一届开始时皇上几岁，之后每晚长两岁
    emperor_death_day INTEGER NOT NULL DEFAULT 0,    -- 已定下的驾崩日（病重从它前两天算起，共 3 天）；0 = 还没病
    mourning         INTEGER NOT NULL DEFAULT 0,     -- 国丧：驾崩后停一天，下一次结算时开下一届选秀
    era_name         TEXT NOT NULL DEFAULT '',       -- 年号（第一届为空）
    emperor_name     TEXT NOT NULL DEFAULT '',       -- 今上的名字（第一届为空）
    emperor_traits   TEXT NOT NULL DEFAULT '{}',     -- 今上的性格与学问/骑射/品行（第一届为空）
    dowager          TEXT NOT NULL DEFAULT '',       -- 今上的太后（第一届为空）
    dowager_uid      INTEGER NOT NULL DEFAULT 0,     -- 太后是哪个玩家家族的人（0 = NPC 或没有）
    event_started    INTEGER NOT NULL DEFAULT 1,     -- 活动是否已经开始计时；0 时每晚不自动结算，天数、皇上寿数都停着
    maintenance      INTEGER NOT NULL DEFAULT 0      -- 管理员正在调整（改数据库、部署等）；0/1，跟 event_started 分开管
);

-- 历代：每一届驾崩那晚定格一条
CREATE TABLE IF NOT EXISTS reigns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reign_no      INTEGER NOT NULL,
    era_name      TEXT NOT NULL DEFAULT '',
    emperor_name  TEXT NOT NULL DEFAULT '',
    start_age     INTEGER NOT NULL,
    end_age_text  TEXT NOT NULL DEFAULT '',
    start_day     INTEGER NOT NULL,
    end_day       INTEGER NOT NULL,
    successor     TEXT NOT NULL DEFAULT '',          -- 新帝
    dowager       TEXT NOT NULL DEFAULT '',          -- 新帝的太后
    edict         TEXT NOT NULL DEFAULT '[]',        -- 遗诏：一句话开头 + 这一届的大事，JSON 数组
    fates         TEXT NOT NULL DEFAULT '[]',        -- 每位玩家的最终位分和结局，JSON 数组
    records       TEXT NOT NULL DEFAULT '[]',        -- 几项纪录，JSON 数组
    created_ts    INTEGER NOT NULL
);

-- 每届结束时，玩家自己的信原样存进来，只有本人能翻、不能再回
CREATE TABLE IF NOT EXISTS reign_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reign_no    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    from_name   TEXT NOT NULL,
    to_name     TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reign_letters_user ON reign_letters(user_id, reign_no);

CREATE TABLE IF NOT EXISTS intrigues (
    resolved_ts REAL NOT NULL DEFAULT 0,
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day          INTEGER NOT NULL,
    attacker_id  INTEGER NOT NULL,
    target_id    INTEGER NOT NULL,
    method       TEXT NOT NULL,
    silver_paid  INTEGER NOT NULL DEFAULT 0,
    item_used    TEXT NOT NULL DEFAULT '',
    drug         TEXT NOT NULL DEFAULT '',          -- 下药：实际下的是哪种药（用「无名」时是出手时选的那种）
    agent_maid_id INTEGER NOT NULL DEFAULT 0,       -- 下药：经手的内应宫人，0=自己动手
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

-- 日常消息：谁在什么时候做了什么（只记明面上的日常，使计、买药、打探这类暗事不记）
CREATE TABLE IF NOT EXISTS daily_feed (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         INTEGER NOT NULL,
    consort_id  INTEGER NOT NULL,
    text        TEXT NOT NULL,
    created_ts  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_feed_day ON daily_feed(day, id);

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
    caretaker_id INTEGER NOT NULL DEFAULT 0,         -- 现在跟谁：抓周前恒等于生母；贵人以下的生母，抓周那天可能改指给别人
    gender      TEXT NOT NULL,                      -- 皇子 / 公主
    ordinal     INTEGER NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    born_day    INTEGER NOT NULL,
    personality TEXT NOT NULL DEFAULT '',            -- 聪敏/憨厚/顽皮/怯懦/倔强，出生时随机
    study       INTEGER NOT NULL DEFAULT 20,         -- 学问
    riding      INTEGER NOT NULL DEFAULT 20,         -- 骑射
    virtue      INTEGER NOT NULL DEFAULT 20,         -- 品行
    health      INTEGER NOT NULL DEFAULT 60,         -- 体质
    gift_study  INTEGER NOT NULL DEFAULT 100,        -- 资质（百分数，100=中人）：教养时学问涨幅按它缩放
    gift_riding INTEGER NOT NULL DEFAULT 100,
    gift_virtue INTEGER NOT NULL DEFAULT 100,
    favor       INTEGER NOT NULL DEFAULT 0,          -- 圣眷，教养/小事件/考校累加，夺嫡阶段另按公式重算
    mother_affinity    INTEGER NOT NULL DEFAULT 50,  -- 跟生母的情分
    caretaker_affinity INTEGER NOT NULL DEFAULT 50,  -- 跟现在抚养人的情分；自己养时两个数一起动
    zhuazhou    TEXT NOT NULL DEFAULT '',            -- 抓周抓到的东西，走过一次之后不再是空
    seen_events TEXT NOT NULL DEFAULT '[]',          -- 遇到过的小事件，同一件不重复
    foster_request_to INTEGER NOT NULL DEFAULT 0,    -- 周岁前生母托付给了谁、还在等对方点头（consorts.id）
    visit_banned INTEGER NOT NULL DEFAULT 0,         -- 玩家养母设了「不许探视」
    concealed   INTEGER NOT NULL DEFAULT 0,          -- 养母瞒着孩子身世；生母下次探视会说破
    reclaim_after_day INTEGER NOT NULL DEFAULT 0,    -- 求皇上讨回失败后，这天之前不能再求
    adult_day   INTEGER NOT NULL DEFAULT 0,          -- 满 16 岁成年的那天，0 = 还没成年
    title       TEXT NOT NULL DEFAULT '',            -- 皇子的爵位（亲王/郡王/贝勒/贝子）或公主的封号（和硕/固伦公主）
    marriage    TEXT NOT NULL DEFAULT '',            -- 公主：choice 等母亲拿主意 / capital 留京下嫁 / mongol 抚蒙古
    marry_day   INTEGER NOT NULL DEFAULT 0,
    errand      TEXT NOT NULL DEFAULT '',            -- 皇子手上的差事 JSON：{key, day, approach}
    plead_ready_day INTEGER NOT NULL DEFAULT 0,      -- 皇子：替母亲求情，这天之前不能再求；公主：进言，这天之前不能再进言
    npc_key     TEXT NOT NULL DEFAULT '',            -- 系统皇子：third 三阿哥 / fourth 四阿哥，玩家生的恒为空
    ambition    INTEGER NOT NULL DEFAULT 30,         -- 野心，成年那晚按性格定
    faction     INTEGER NOT NULL DEFAULT 0,          -- 自己结交的朝臣数
    status      TEXT NOT NULL DEFAULT '',            -- '' / crown 太子 / deposed 废太子圈禁
    exam_bonus  INTEGER NOT NULL DEFAULT 0,          -- 下一次考校判定加成（站队者递消息、收买上书房），考校后清零
    feud_until_day INTEGER NOT NULL DEFAULT 0,       -- 被人挑拨兄弟，这天之前每晚圣眷 -3
    gift        TEXT NOT NULL DEFAULT '',            -- 万寿节备下的寿礼：calligraphy / fur / antique
    orphan_deadline_day INTEGER NOT NULL DEFAULT 0,  -- 没人要的皇子：这天还无人抚养，皇后就抱走
    reprimand_ready_day INTEGER NOT NULL DEFAULT 0,  -- 结党过多被当众训斥，这天之前不再训斥
    forged      INTEGER NOT NULL DEFAULT 0           -- 矫诏成功：驾崩那晚匾后改成他
);

-- 站队：每人最多一个明站、一个暗站，7 天内不能改
CREATE TABLE IF NOT EXISTS stances (
    consort_id  INTEGER NOT NULL,
    kind        TEXT NOT NULL,                       -- open / secret
    heir_id     INTEGER NOT NULL,
    since_day   INTEGER NOT NULL,
    PRIMARY KEY (consort_id, kind)
);

-- 求皇上把没人要的皇子抱来抚养；每晚在求过的人里按信任、位分加权抽一位
CREATE TABLE IF NOT EXISTS heir_claims (
    consort_id  INTEGER NOT NULL,
    heir_id     INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    PRIMARY KEY (consort_id, heir_id)
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

-- 收买宫人：倾心(progress) ≥ 宫人忠心时 turned=1，成了收买者的内应
CREATE TABLE IF NOT EXISTS bribes (
    briber_id   INTEGER NOT NULL,
    maid_id     INTEGER NOT NULL,
    progress    INTEGER NOT NULL DEFAULT 0,
    turned      INTEGER NOT NULL DEFAULT 0,
    counter     INTEGER NOT NULL DEFAULT 0,          -- 主子已知情、将计就计
    exposed     INTEGER NOT NULL DEFAULT 0,          -- 清查时被查出，等主子定夺
    reported    INTEGER NOT NULL DEFAULT 0,          -- 忠心的宫人把收银子的事告诉了主子，等主子定夺
    last_day    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (briber_id, maid_id)
);

-- 药效：发作有先后（惊梦香等被翻牌才发作、青丝引每晚扣体质、春信丹临盆才露馅）
CREATE TABLE IF NOT EXISTS afflictions (
    expires_ts REAL NOT NULL DEFAULT 0,
    restore_stat TEXT NOT NULL DEFAULT '',
    restore_delta INTEGER NOT NULL DEFAULT 0,
    ticks INTEGER NOT NULL DEFAULT 0,
    last_tick_day INTEGER NOT NULL DEFAULT -1,
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    consort_id    INTEGER NOT NULL,
    drug          TEXT NOT NULL,
    attacker_id   INTEGER NOT NULL DEFAULT 0,
    intrigue_id   INTEGER NOT NULL DEFAULT 0,
    start_day     INTEGER NOT NULL,
    until_day     INTEGER NOT NULL DEFAULT 0,        -- 到这天（含）为止；0=直到被诊出
    status        TEXT NOT NULL DEFAULT 'active'     -- active / done
);
CREATE INDEX IF NOT EXISTS idx_afflictions ON afflictions(consort_id, status);

-- 案子：药性发作被发现时开案，下一次结算定案。v1.4 的慎刑司查案会在这张表上加嫌疑人
CREATE TABLE IF NOT EXISTS cases (
    victim_trust_loss INTEGER NOT NULL DEFAULT 15,
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    day           INTEGER NOT NULL,                  -- 开案那天
    victim_id     INTEGER NOT NULL,
    culprit_id    INTEGER NOT NULL,
    intrigue_id   INTEGER NOT NULL DEFAULT 0,
    drug          TEXT NOT NULL DEFAULT '',
    agent_maid_id INTEGER NOT NULL DEFAULT 0,
    victim_punished INTEGER NOT NULL DEFAULT 0,      -- 春信丹：受害人先被当成欺君罚了
    status        TEXT NOT NULL DEFAULT 'open',      -- open / convicted / unsolved
    closed_day    INTEGER NOT NULL DEFAULT 0,
    created_ts    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status, day);

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
    hobby_item_id INTEGER NOT NULL DEFAULT 0,       -- 附的是雅趣作品而不是内务府的东西时用这个
    is_read     INTEGER NOT NULL DEFAULT 0,
    is_broadcast INTEGER NOT NULL DEFAULT 0,        -- 管理员群发的补偿信，from_id=0 显示为「内务府」
    broadcast_id INTEGER NOT NULL DEFAULT 0,        -- 同一次群发共享一个 id（取这批第一封信自己的 id），方便后台统计领取人数
    claimed     INTEGER NOT NULL DEFAULT 1,         -- 普通信送出即到账，恒为 1；群发信有附件时送出先是 0，点了「领取」才到账
    deleted_by_from INTEGER NOT NULL DEFAULT 0,     -- 删信只对自己的信箱生效，对方那份不受影响
    deleted_by_to   INTEGER NOT NULL DEFAULT 0,
    sender_label TEXT NOT NULL DEFAULT '',          -- 系统代写的信（公主家书）显示的寄信人；空则 from_id=0 显示为「内务府」
    created_ts  INTEGER NOT NULL
);

-- 标星：谁把哪封信标了星，标星的信放最前面、不参与翻页
CREATE TABLE IF NOT EXISTS letter_stars (
    letter_id   INTEGER NOT NULL,
    consort_id  INTEGER NOT NULL,
    PRIMARY KEY (letter_id, consort_id)
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

CREATE TABLE IF NOT EXISTS case_suspects (
 case_id INTEGER NOT NULL, consort_id INTEGER NOT NULL,
 suspicion INTEGER NOT NULL DEFAULT 0, pleaded INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(case_id,consort_id)
);
CREATE TABLE IF NOT EXISTS case_actions (
 case_id INTEGER NOT NULL, consort_id INTEGER NOT NULL, day INTEGER NOT NULL,
 action TEXT NOT NULL, target_id INTEGER NOT NULL,
 PRIMARY KEY(case_id,consort_id,day,action)
);

-- 雅趣：每件作品起意→打磨→成了，三步；成了之后进 hobby_items，可摆可送
CREATE TABLE IF NOT EXISTS hobby_projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER NOT NULL,
    kind        TEXT NOT NULL,                     -- flower / incense / painting / tea
    style       TEXT NOT NULL,                      -- 选的花种/香方/题目/茶款
    stage       INTEGER NOT NULL DEFAULT 0,          -- 0 起意，做完一次 act 才 +1，到 2 完成
    last_day    INTEGER NOT NULL DEFAULT 0,          -- 上次推进是哪天，同一天不能再推进
    started_day INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'       -- active / done
);
CREATE INDEX IF NOT EXISTS idx_hobby_projects_owner ON hobby_projects(owner_id, status);

-- 雅趣作品：独一份，不是内务府买来的东西，holder_id 记着现在摆在谁那儿
CREATE TABLE IF NOT EXISTS hobby_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    style       TEXT NOT NULL,
    quality     TEXT NOT NULL DEFAULT '普通',        -- 普通 / 精巧 / 上品
    maker_id    INTEGER NOT NULL,
    holder_id   INTEGER NOT NULL,
    created_day INTEGER NOT NULL,
    history     TEXT NOT NULL DEFAULT '[]'           -- [{"from":id,"to":id,"day":n}, ...] 送过谁的记录
);
CREATE INDEX IF NOT EXISTS idx_hobby_items_holder ON hobby_items(holder_id);

-- 寝宫陈设：固定 4 个位置，放自己或别人送的作品
CREATE TABLE IF NOT EXISTS displays (
    consort_id  INTEGER NOT NULL,
    slot        TEXT NOT NULL,                       -- window / desk / wall / tea
    item_id     INTEGER NOT NULL,
    PRIMARY KEY (consort_id, slot)
);


-- ── 家族（九点九节）：一个账号就是一个家族，跨届一直在 ─────────────────────────────
CREATE TABLE IF NOT EXISTS families (
    career_path TEXT NOT NULL DEFAULT '',
    background TEXT NOT NULL DEFAULT '',
    user_id      INTEGER PRIMARY KEY,
    surname      TEXT NOT NULL,                      -- 全家族共用，注册时定下，不能改
    tier         TEXT NOT NULL,                      -- 门第（FAMILIES 的 key），不能改
    prestige     INTEGER NOT NULL DEFAULT 0,         -- 名望，跨届累积
    estate       INTEGER NOT NULL DEFAULT 0,         -- 家底：送回家的银子，家里的存款，谁都能支取
    head_name    TEXT NOT NULL DEFAULT '',           -- 家主（代表人）：先是父亲，父亲没了是兄长，再是侄子、族叔
    head_role    TEXT NOT NULL DEFAULT '父亲',
    head_gen     INTEGER NOT NULL DEFAULT 0,
    head_age_months INTEGER NOT NULL DEFAULT 0,
    head_office  INTEGER NOT NULL DEFAULT 0,         -- 官职品级，0 白身 ~ 9 一品
    head_ill_day INTEGER NOT NULL DEFAULT 0,         -- 家主病了：从哪天起，0 = 没病
    backing_heir_id INTEGER NOT NULL DEFAULT 0,      -- 家里这一届支持哪位阿哥，0 = 默认跟着自家的孩子走
    backing_day  INTEGER NOT NULL DEFAULT 0,
    withdraw_day INTEGER NOT NULL DEFAULT 0,         -- 上次支取家底的日子
    petition_day INTEGER NOT NULL DEFAULT 0,         -- 上次荐官的日子
    request_day  INTEGER NOT NULL DEFAULT 0,         -- 上次家里来求助的日子
    created_ts   INTEGER NOT NULL
);

-- 家里的大事记（也是族谱页最上面的荣耀：太后、太妃、亲王、公主）
CREATE TABLE IF NOT EXISTS family_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    reign_no  INTEGER NOT NULL,
    day       INTEGER NOT NULL,
    text      TEXT NOT NULL,
    honor     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_family_log_user ON family_log(user_id, id);

-- 家里的生意：本金投出去，几天后有盈有亏，还可能被御史参一本
CREATE TABLE IF NOT EXISTS family_ventures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    consort_id  INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    principal   INTEGER NOT NULL,
    start_day   INTEGER NOT NULL,
    mature_day  INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',        -- open / done
    result      TEXT NOT NULL DEFAULT ''
);

-- 家里来求你帮忙：升迁要打点、闯了祸要说情、欠了债、家主病了、该站哪位阿哥
CREATE TABLE IF NOT EXISTS family_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    consort_id  INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    day         INTEGER NOT NULL,
    expires_day INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',        -- open / done / declined / lapsed
    data        TEXT NOT NULL DEFAULT '{}'
);


-- 告警：结算出错、结算拖延、页面 500、备份失败。同一件事没处理前只累加次数，1 小时内不重复推送
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    key         TEXT NOT NULL,
    message     TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    count       INTEGER NOT NULL DEFAULT 1,
    first_ts    INTEGER NOT NULL,
    last_ts     INTEGER NOT NULL,
    notified_ts INTEGER NOT NULL DEFAULT 0,
    resolved    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(resolved, key);


-- 人情：几件够分量的事，不新开一条数值，只记"发生过"
CREATE TABLE IF NOT EXISTS memories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    a_id    INTEGER NOT NULL,
    b_id    INTEGER NOT NULL,
    kind    TEXT NOT NULL,
    day     INTEGER NOT NULL,
    note    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_memories_ab ON memories(a_id, b_id);

-- 小聚：主人邀约挂在客人账号上，客人当天上线随时能看到、回应
CREATE TABLE IF NOT EXISTS gatherings (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id  INTEGER NOT NULL,
    guest_id INTEGER NOT NULL,
    theme    TEXT NOT NULL,
    day      INTEGER NOT NULL,
    status   TEXT NOT NULL DEFAULT 'pending'   -- pending / done / lapsed
);
CREATE INDEX IF NOT EXISTS idx_gatherings_guest ON gatherings(guest_id, day, status);

-- 借华妃的刀（设计文档九点二十二节）：一次借刀一行，从「等今晚出手」走到「欠人情」再到还清/赖账
CREATE TABLE IF NOT EXISTS knife_debts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    consort_id  INTEGER NOT NULL,                    -- 求华妃出手的人
    intrigue_id INTEGER NOT NULL DEFAULT 0,          -- 华妃替她发起的那条阴谋
    victim_id   INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'hit',         -- hit 等今晚出手 / owed 欠着人情 / paid / broken 赖账 / void 没得手 / covered 败露但华妃护着 / exposed 被供出
    debt        TEXT NOT NULL DEFAULT '',            -- KNIFE_DEBTS 的 key
    x_id        INTEGER NOT NULL DEFAULT 0,          -- 人情是散流言时的对象
    maid_id     INTEGER NOT NULL DEFAULT 0,          -- 人情是送宫人时的那名宫人
    start_day   INTEGER NOT NULL DEFAULT 0,
    due_day     INTEGER NOT NULL DEFAULT 0,
    created_ts  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_knife_debts_owner ON knife_debts(consort_id, status);

-- 玩家双方争夺皇嗣抚养权；养育所领回不触发争夺。
CREATE TABLE IF NOT EXISTS custody_battles (
    heir_id INTEGER PRIMARY KEY,
    challenger_id INTEGER NOT NULL,
    defender_id INTEGER NOT NULL,
    challenger_progress INTEGER NOT NULL DEFAULT 0,
    defender_progress INTEGER NOT NULL DEFAULT 0,
    started_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    winner_id INTEGER NOT NULL DEFAULT 0
);


-- 菜园：每人最多 6 块地，种下去按真实时间长成（ready_ts 是成熟的时间戳），浇水一次缩短 25%
CREATE TABLE IF NOT EXISTS garden_plots (
    consort_id  INTEGER NOT NULL,
    slot        INTEGER NOT NULL,
    crop        TEXT NOT NULL,
    planted_ts  INTEGER NOT NULL,
    ready_ts    INTEGER NOT NULL,
    watered     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (consort_id, slot)
);
-- 收下来还没卖、没送的菜
CREATE TABLE IF NOT EXISTS garden_stock (
    consort_id  INTEGER NOT NULL,
    crop        TEXT NOT NULL,
    qty         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (consort_id, crop)
);
-- 新年宴会：每晚 22 点开，banquet_date 是哪一晚的宴会（报名截止 22 点，之后算下一晚）
CREATE TABLE IF NOT EXISTS banquet_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    banquet_date  TEXT NOT NULL,
    consort_id    INTEGER NOT NULL,
    art           TEXT NOT NULL,
    piece         TEXT NOT NULL DEFAULT '',     -- 节目名
    rehearsed     INTEGER NOT NULL DEFAULT 0,   -- 排练了几次，最多 2
    partner_id    INTEGER NOT NULL DEFAULT 0,   -- 合奏搭档的 consort_id，互相指着对方才算数
    tier          INTEGER NOT NULL DEFAULT 1,   -- 节目档次 1~3
    buff          INTEGER NOT NULL DEFAULT 0,   -- 吃了宴前小食的加分
    note          TEXT NOT NULL DEFAULT '',     -- 台上表现的一句评语
    score         REAL,
    place         INTEGER,                      -- 名次，开席后才有
    UNIQUE (banquet_date, consort_id)
);

-- 合奏邀请：发起人必须已报节目，对方点头才结成一队
CREATE TABLE IF NOT EXISTS banquet_invites (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    banquet_date  TEXT NOT NULL,
    from_id       INTEGER NOT NULL,
    to_id         INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'   -- pending / accepted / declined / void
);
-- 戏装铺买下的行头
CREATE TABLE IF NOT EXISTS banquet_gear (
    consort_id    INTEGER NOT NULL,
    gear_key      TEXT NOT NULL,
    PRIMARY KEY (consort_id, gear_key)
);

-- 成就：达成过的记一笔（成就内容在 app.py 的 ACHIEVEMENTS，现算进度）
CREATE TABLE IF NOT EXISTS achievements (
    consort_id  INTEGER NOT NULL,
    key         TEXT NOT NULL,
    ts          INTEGER NOT NULL,
    PRIMARY KEY (consort_id, key)
);
