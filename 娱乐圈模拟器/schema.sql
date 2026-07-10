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

CREATE TABLE IF NOT EXISTS agencies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agency_name TEXT NOT NULL,
    tier        TEXT DEFAULT '',
    cut_rate    REAL DEFAULT 0.3,
    reputation  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS players (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER UNIQUE,
    is_npc              INTEGER DEFAULT 0,
    age                 INTEGER DEFAULT 18,
    gender              TEXT DEFAULT '',
    stage_name          TEXT NOT NULL DEFAULT '',
    talents             TEXT DEFAULT '{}',
    hidden_traits       TEXT DEFAULT '[]',
    career_lines        TEXT DEFAULT '[]',
    agency_id           INTEGER,
    fans_count          INTEGER DEFAULT 0,
    core_fan_loyalty    INTEGER DEFAULT 0,
    popularity          INTEGER DEFAULT 0,
    scandal_value       INTEGER DEFAULT 0,
    persona_tag         TEXT DEFAULT '',
    persona_integrity   INTEGER DEFAULT 100,
    cash                INTEGER DEFAULT 0,
    roll_count          INTEGER DEFAULT 0,
    revealed            INTEGER DEFAULT 0,
    energy              INTEGER DEFAULT 100,
    energy_updated      INTEGER DEFAULT 0,
    family_background   TEXT DEFAULT '',
    birthplace          TEXT DEFAULT '',
    true_personality    TEXT DEFAULT '',
    career_state        TEXT DEFAULT 'normal',  -- normal/blackout
    blackout_until_ts    INTEGER DEFAULT 0,
    anti_scandal_reserve INTEGER DEFAULT 0,
    endorsement_reputation INTEGER DEFAULT 0,
    awards_won          INTEGER DEFAULT 0,
    fan_club_name       TEXT DEFAULT '',
    fan_club_color      TEXT DEFAULT '',
    notifications_seen_ts INTEGER DEFAULT 0,
    health              INTEGER DEFAULT 100,
    last_rest_ts        INTEGER DEFAULT 0,
    last_travel_ts      INTEGER DEFAULT 0,
    created_ts          INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS posts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id          INTEGER NOT NULL,
    post_type          TEXT NOT NULL,
    content            TEXT DEFAULT '',
    outcome            TEXT DEFAULT '',
    likes              INTEGER DEFAULT 0,
    reposts            INTEGER DEFAULT 0,
    comments_count     INTEGER DEFAULT 0,
    heat               INTEGER DEFAULT 0,
    editable_until_ts  INTEGER,
    created_ts         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS post_comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER NOT NULL,
    stance          TEXT DEFAULT '',
    content         TEXT DEFAULT '',
    commenter_id    INTEGER,
    rival_player_id INTEGER,
    created_ts      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS boosts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id        INTEGER NOT NULL,
    boost_type       TEXT NOT NULL,
    target_player_id INTEGER,
    amount           INTEGER DEFAULT 0,
    backfire         INTEGER DEFAULT 0,
    created_ts       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sasaeng_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    target_player_id INTEGER NOT NULL,
    hired_by_player_id INTEGER,
    event_kind       TEXT DEFAULT '',
    created_ts       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trending_topics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_text        TEXT NOT NULL,
    related_player_id INTEGER,
    topic_kind        TEXT DEFAULT '',
    heat              INTEGER DEFAULT 0,
    rank              INTEGER DEFAULT 0,
    tick_id           INTEGER DEFAULT 0,
    created_ts        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER NOT NULL,
    target_type TEXT DEFAULT '',
    target_id   INTEGER,
    action      TEXT DEFAULT '',
    detail      TEXT DEFAULT '',
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS dramas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    budget_tier     TEXT DEFAULT '',
    format          TEXT DEFAULT 'tv',
    open_ts         INTEGER DEFAULT 0,
    apply_close_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS drama_roles (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    drama_id           INTEGER NOT NULL,
    role_name          TEXT NOT NULL,
    gender_requirement TEXT DEFAULT 'any',
    tier_requirement   TEXT DEFAULT 'D',
    requirement_talent TEXT DEFAULT '',
    reward_cash        INTEGER DEFAULT 0,
    reward_popularity  INTEGER DEFAULT 0,
    status             TEXT DEFAULT 'casting',  -- casting/shooting/aired
    winner_player_id   INTEGER,
    winner_is_npc_fill INTEGER DEFAULT 0,
    shoot_end_ts       INTEGER DEFAULT 0,
    rating_score       INTEGER DEFAULT 0,
    created_ts         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS role_applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id     INTEGER NOT NULL,
    player_id   INTEGER NOT NULL,
    match_score INTEGER DEFAULT 0,
    rival_name  TEXT DEFAULT '',
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS relationships (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    player_a_id          INTEGER NOT NULL,
    player_b_id          INTEGER,
    secrecy              INTEGER DEFAULT 100,
    status               TEXT DEFAULT 'secret',  -- secret/exposed_pending/together/ended
    started_ts           INTEGER DEFAULT 0,
    exposed_ts           INTEGER DEFAULT 0,
    response_deadline_ts INTEGER DEFAULT 0,
    married              INTEGER DEFAULT 0,
    marriage_announced   INTEGER DEFAULT 0,
    pregnancy_status     TEXT DEFAULT 'none',  -- none/deciding/concealing/terminated/born
    pregnant_player_id   INTEGER,
    pregnancy_started_ts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS children (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_id  INTEGER NOT NULL,
    parent_a_id      INTEGER NOT NULL,
    parent_b_id      INTEGER NOT NULL,
    name             TEXT DEFAULT '',
    gender           TEXT DEFAULT 'female',
    born_ts          INTEGER DEFAULT 0,
    revealed         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS collaborations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_a_id INTEGER NOT NULL,
    player_b_id INTEGER NOT NULL,
    collab_type TEXT DEFAULT '',
    same_agency INTEGER DEFAULT 0,
    heat        INTEGER DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS social_invites (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invite_type    TEXT NOT NULL,  -- dating/collab
    from_player_id INTEGER NOT NULL,
    to_player_id   INTEGER NOT NULL,
    status         TEXT DEFAULT 'pending',  -- pending/accepted/declined
    created_ts     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS friendships (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_a_id INTEGER NOT NULL,  -- 总是较小的 id,配对唯一
    player_b_id INTEGER NOT NULL,
    affinity    INTEGER DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS private_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_player_id INTEGER NOT NULL,
    to_player_id   INTEGER NOT NULL,
    content        TEXT DEFAULT '',
    read           INTEGER DEFAULT 0,
    created_ts     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS brands (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_name       TEXT NOT NULL,
    tier             TEXT DEFAULT '',   -- niche/mid/top
    min_tier         TEXT DEFAULT 'D',  -- 咖位门槛,复用抢角色的等级体系
    max_scandal      INTEGER DEFAULT 999,
    min_reputation   INTEGER DEFAULT 0,
    reward_cash      INTEGER DEFAULT 0,
    reward_reputation INTEGER DEFAULT 0,
    duration_seconds INTEGER DEFAULT 0,
    apply_close_ts   INTEGER DEFAULT 0,
    status           TEXT DEFAULT 'open',  -- open/signed/completed
    signed_player_id INTEGER,
    contract_end_ts  INTEGER DEFAULT 0,
    created_ts       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS brand_applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id    INTEGER NOT NULL,
    player_id   INTEGER NOT NULL,
    match_score INTEGER DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS songs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    INTEGER NOT NULL,
    title        TEXT NOT NULL,
    is_crossover INTEGER DEFAULT 0,
    invested     INTEGER DEFAULT 0,
    created_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS luxury_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id  INTEGER NOT NULL,
    item_name  TEXT NOT NULL,
    rarity     TEXT DEFAULT '',
    created_ts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS concerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    invested    INTEGER DEFAULT 0,
    incident    TEXT DEFAULT '',
    held_ts     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS award_seasons (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    season_name      TEXT NOT NULL,
    nomination_start INTEGER DEFAULT 0,
    campaign_end_ts  INTEGER DEFAULT 0,
    status           TEXT DEFAULT 'campaigning',  -- campaigning/announced
    show_key         TEXT DEFAULT 'star',
    tier             TEXT DEFAULT 'minor',
    created_ts       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS award_categories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id     INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    judge_type    TEXT DEFAULT 'popular',  -- critic/popular
    career_line   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS award_nominees (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id   INTEGER NOT NULL,
    player_id     INTEGER NOT NULL,
    critic_score  INTEGER DEFAULT 0,
    vote_score    INTEGER DEFAULT 0,
    won           INTEGER DEFAULT 0,
    bribe_exposed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS judge_bribes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    player_id   INTEGER NOT NULL,
    invested    INTEGER DEFAULT 0,
    exposed     INTEGER DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS super_topic_posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    content     TEXT DEFAULT '',
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS intel_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_player_id   INTEGER NOT NULL,
    target_player_id  INTEGER NOT NULL,
    tier              TEXT DEFAULT 'basic',
    revealed_json     TEXT DEFAULT '{}',
    created_ts        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paparazzi_tips (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id         INTEGER NOT NULL,
    target_player_id  INTEGER NOT NULL,
    tip_text          TEXT DEFAULT '',
    status            TEXT DEFAULT 'pending',
    created_ts        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS brand_ambassadors (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_name        TEXT NOT NULL,
    min_tier          TEXT DEFAULT 'A',
    max_scandal       INTEGER DEFAULT 20,
    min_reputation    INTEGER DEFAULT 40,
    current_player_id INTEGER,
    held_since_ts     INTEGER DEFAULT 0,
    created_ts        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fan_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    content     TEXT DEFAULT '',
    sentiment   TEXT DEFAULT 'fan',
    replied     INTEGER DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS milestones_achieved (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id      INTEGER NOT NULL,
    milestone_key  TEXT NOT NULL,
    created_ts     INTEGER DEFAULT 0,
    UNIQUE(player_id, milestone_key)
);

CREATE TABLE IF NOT EXISTS fan_gifts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    item_name   TEXT NOT NULL,
    rarity      TEXT DEFAULT '',
    from_label  TEXT DEFAULT '',
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS product_sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER NOT NULL,
    post_id         INTEGER NOT NULL,
    product_name    TEXT NOT NULL,
    sales_count     INTEGER DEFAULT 0,
    ticks_remaining INTEGER DEFAULT 5,
    created_ts      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lifestyle_assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    item_name   TEXT NOT NULL,
    category    TEXT DEFAULT '',
    price       INTEGER DEFAULT 0,
    created_ts  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS hate_campaigns (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    hirer_player_id   INTEGER NOT NULL,
    target_player_id  INTEGER NOT NULL,
    ticks_remaining   INTEGER DEFAULT 3,
    created_ts        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cp_pairs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_a_id  INTEGER NOT NULL,
    player_b_id  INTEGER NOT NULL,
    heat         INTEGER DEFAULT 0,
    created_ts   INTEGER DEFAULT 0,
    UNIQUE(player_a_id, player_b_id)
);

CREATE TABLE IF NOT EXISTS acting_challenges (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id      INTEGER NOT NULL,
    round_no     INTEGER NOT NULL,
    prompt       TEXT NOT NULL,
    chosen       TEXT DEFAULT '',
    created_ts   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audition_challenges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    round_no       INTEGER NOT NULL,
    prompt         TEXT NOT NULL,
    chosen         TEXT DEFAULT '',
    created_ts     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audition_app ON audition_challenges(application_id);

CREATE INDEX IF NOT EXISTS idx_posts_player ON posts(player_id, created_ts);
CREATE INDEX IF NOT EXISTS idx_topics_tick ON trending_topics(tick_id, rank);
CREATE INDEX IF NOT EXISTS idx_players_user ON players(user_id);
CREATE INDEX IF NOT EXISTS idx_comments_post ON post_comments(post_id);
CREATE INDEX IF NOT EXISTS idx_boosts_target ON boosts(target_player_id);
CREATE INDEX IF NOT EXISTS idx_sasaeng_target ON sasaeng_events(target_player_id);
CREATE INDEX IF NOT EXISTS idx_players_npc ON players(is_npc);
CREATE INDEX IF NOT EXISTS idx_drama_roles_status ON drama_roles(status);
CREATE INDEX IF NOT EXISTS idx_drama_roles_drama ON drama_roles(drama_id);
CREATE INDEX IF NOT EXISTS idx_role_apps_role ON role_applications(role_id, player_id);
CREATE INDEX IF NOT EXISTS idx_relationships_a ON relationships(player_a_id, status);
CREATE INDEX IF NOT EXISTS idx_relationships_b ON relationships(player_b_id, status);
CREATE INDEX IF NOT EXISTS idx_invites_to ON social_invites(to_player_id, status);
CREATE INDEX IF NOT EXISTS idx_brands_status ON brands(status);
CREATE INDEX IF NOT EXISTS idx_brand_apps_brand ON brand_applications(brand_id, player_id);
CREATE INDEX IF NOT EXISTS idx_songs_player ON songs(player_id);
CREATE INDEX IF NOT EXISTS idx_luxury_player ON luxury_items(player_id);
CREATE INDEX IF NOT EXISTS idx_award_seasons_status ON award_seasons(status);
CREATE INDEX IF NOT EXISTS idx_award_categories_season ON award_categories(season_id);
CREATE INDEX IF NOT EXISTS idx_award_nominees_category ON award_nominees(category_id, player_id);
CREATE INDEX IF NOT EXISTS idx_friendships_pair ON friendships(player_a_id, player_b_id);
CREATE INDEX IF NOT EXISTS idx_messages_pair ON private_messages(from_player_id, to_player_id, created_ts);
