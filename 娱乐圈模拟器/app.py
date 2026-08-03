import os, json, random, time, math, colorsys, re
from datetime import timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session as S, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "yulequan_sim_secret_2026")
app.permanent_session_lifetime = timedelta(days=30)

DB_PATH    = os.path.join(os.path.dirname(__file__), "yulequan.db")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "yulequan_admin_888")
now_ts     = lambda: int(time.time())

# ── 数据库 ─────────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    return db

@app.teardown_appcontext
def close_db(e=None):
    db = getattr(g, '_db', None)
    if db: db.close()

def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    return cur.fetchone() if one else cur.fetchall()

def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur

def init_db():
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()
    existing_cols = {row[1] for row in db.execute("PRAGMA table_info(posts)")}
    if 'editable_until_ts' not in existing_cols:
        db.execute("ALTER TABLE posts ADD COLUMN editable_until_ts INTEGER")
        db.commit()
    letter_cols = {row[1] for row in db.execute("PRAGMA table_info(fan_letters)")}
    if 'sentiment' not in letter_cols:
        db.execute("ALTER TABLE fan_letters ADD COLUMN sentiment TEXT DEFAULT 'fan'")
        db.commit()
    player_cols = {row[1] for row in db.execute("PRAGMA table_info(players)")}
    if 'fan_club_name' not in player_cols:
        db.execute("ALTER TABLE players ADD COLUMN fan_club_name TEXT DEFAULT ''")
        db.commit()
    if 'fan_club_color' not in player_cols:
        db.execute("ALTER TABLE players ADD COLUMN fan_club_color TEXT DEFAULT ''")
        db.commit()
    drama_cols = {row[1] for row in db.execute("PRAGMA table_info(dramas)")}
    if 'format' not in drama_cols:
        db.execute("ALTER TABLE dramas ADD COLUMN format TEXT DEFAULT 'tv'")
        db.commit()
    if 'notifications_seen_ts' not in player_cols:
        db.execute("ALTER TABLE players ADD COLUMN notifications_seen_ts INTEGER DEFAULT 0")
        db.commit()
    dm_cols = {row[1] for row in db.execute("PRAGMA table_info(private_messages)")}
    if 'read' not in dm_cols:
        db.execute("ALTER TABLE private_messages ADD COLUMN read INTEGER DEFAULT 0")
        db.commit()
    season_cols = {row[1] for row in db.execute("PRAGMA table_info(award_seasons)")}
    if 'show_key' not in season_cols:
        db.execute("ALTER TABLE award_seasons ADD COLUMN show_key TEXT DEFAULT 'star'")
        db.commit()
    if 'tier' not in season_cols:
        db.execute("ALTER TABLE award_seasons ADD COLUMN tier TEXT DEFAULT 'minor'")
        db.commit()
    app_cols = {row[1] for row in db.execute("PRAGMA table_info(role_applications)")}
    if 'rival_name' not in app_cols:
        db.execute("ALTER TABLE role_applications ADD COLUMN rival_name TEXT DEFAULT ''")
        db.commit()
    db.execute("""CREATE TABLE IF NOT EXISTS audition_challenges (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        round_no       INTEGER NOT NULL,
        prompt         TEXT NOT NULL,
        chosen         TEXT DEFAULT '',
        created_ts     INTEGER DEFAULT 0
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_audition_app ON audition_challenges(application_id)")
    db.commit()
    role_cols = {row[1] for row in db.execute("PRAGMA table_info(drama_roles)")}
    if 'rating_score' not in role_cols:
        db.execute("ALTER TABLE drama_roles ADD COLUMN rating_score INTEGER DEFAULT 0")
        db.commit()
    if 'health' not in player_cols:
        db.execute("ALTER TABLE players ADD COLUMN health INTEGER DEFAULT 100")
        db.commit()
    if 'last_rest_ts' not in player_cols:
        db.execute("ALTER TABLE players ADD COLUMN last_rest_ts INTEGER DEFAULT 0")
        db.commit()
    if 'last_travel_ts' not in player_cols:
        db.execute("ALTER TABLE players ADD COLUMN last_travel_ts INTEGER DEFAULT 0")
        db.commit()
    rel_cols = {row[1] for row in db.execute("PRAGMA table_info(relationships)")}
    if 'married' not in rel_cols:
        db.execute("ALTER TABLE relationships ADD COLUMN married INTEGER DEFAULT 0")
        db.commit()
    if 'marriage_announced' not in rel_cols:
        db.execute("ALTER TABLE relationships ADD COLUMN marriage_announced INTEGER DEFAULT 0")
        db.commit()
    if 'pregnancy_status' not in rel_cols:
        db.execute("ALTER TABLE relationships ADD COLUMN pregnancy_status TEXT DEFAULT 'none'")
        db.commit()
    if 'pregnant_player_id' not in rel_cols:
        db.execute("ALTER TABLE relationships ADD COLUMN pregnant_player_id INTEGER")
        db.commit()
    if 'pregnancy_started_ts' not in rel_cols:
        db.execute("ALTER TABLE relationships ADD COLUMN pregnancy_started_ts INTEGER DEFAULT 0")
        db.commit()
    invite_cols = {row[1] for row in db.execute("PRAGMA table_info(social_invites)")}
    if 'topic' not in invite_cols:
        db.execute("ALTER TABLE social_invites ADD COLUMN topic TEXT")
        db.commit()
    db.execute("""CREATE TABLE IF NOT EXISTS children (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        relationship_id INTEGER NOT NULL,
        parent_a_id   INTEGER NOT NULL,
        parent_b_id   INTEGER NOT NULL,
        name          TEXT DEFAULT '',
        gender        TEXT DEFAULT 'female',
        born_ts       INTEGER DEFAULT 0,
        revealed      INTEGER DEFAULT 0
    )""")
    db.commit()
    _ensure_admin(db)
    _ensure_agencies(db)
    _ensure_ambassadors(db)
    _ensure_world_pool(db)
    _ensure_npcs(db)
    db.close()

def _ensure_admin(db):
    row = db.execute("SELECT id FROM users WHERE username=?", (ADMIN_USER,)).fetchone()
    if not row:
        db.execute(
            "INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (ADMIN_USER, generate_password_hash(ADMIN_PASS, method='pbkdf2:sha256'),
             '00000000', 'admin', 'approved', now_ts()))
        db.commit()

def _ensure_agencies(db):
    row = db.execute("SELECT id FROM agencies LIMIT 1").fetchone()
    if row:
        return
    seed = [
        ("星耀国际", "major", 0.45, 80),
        ("云溪文化", "major", 0.40, 65),
        ("拾光娱乐", "mid",   0.30, 40),
        ("野生工作室", "indie", 0.15, 15),
    ]
    db.executemany(
        "INSERT INTO agencies (agency_name,tier,cut_rate,reputation) VALUES (?,?,?,?)", seed)
    db.commit()

def _ensure_ambassadors(db):
    row = db.execute("SELECT id FROM brand_ambassadors LIMIT 1").fetchone()
    if row:
        return
    seed = ["临境", "格雷腕表", "柏澜高定", "沃森珠宝"]
    now = int(time.time())
    db.executemany(
        "INSERT INTO brand_ambassadors (brand_name,min_tier,max_scandal,min_reputation,created_ts) "
        "VALUES (?,'A',20,40,?)", [(name, now) for name in seed])
    db.commit()

# ── 天赋与人设常量 ──────────────────────────────────────────────────────────────

TALENT_KEYS = ["颜值", "唱功", "舞蹈", "演技", "镜头感", "创作力", "抗压力"]

HIDDEN_TRAITS = {
    "哭戏本命":   {"boost": "演技",   "desc": "催泪戏自带加成"},
    "高音本子":   {"boost": "唱功",   "desc": "高音段位额外加成"},
    "上镜感爆棚": {"boost": "镜头感", "desc": "镜头感独立于颜值给"},
    "钝感力max":  {"boost": "抗压力", "desc": "黑值涨得慢,适合走争议咖路线"},
}

PERSONA_TAGS = [
    "元气少年/少女", "高冷禁欲", "励志正能量", "耿直接地气", "纯欲天菜",
    "温柔知性", "邻家清新", "暗黑颓废", "学霸精英", "反差萌",
    "文艺清冷", "甜妹", "痞帅浪子", "大女主", "治愈系",
    "摇滚朋克", "古典雅致", "街头潮酷", "沙雕憨憨", "忠犬系",
    "姐系撑腰", "弟系宠溺", "高智商偶像", "幽默毒舌", "佛系随缘",
    "少年感", "御姐范", "纯情校草", "独立女性", "神秘感",
]

MAX_TALENT_ROLLS = 5

# ── 出身背景(家庭 × 出生地,组合数覆盖 100+ 种) ────────────────────────────────────

FAMILY_BACKGROUNDS = {
    "书香门第":         {"talent": "演技",   "amount": 4, "desc": "家里满墙的书,从小被逼着背台词式地念诗"},
    "商界世家":         {"cash": 300,                     "desc": "家里做点小生意,不算大富大贵但从不缺钱"},
    "文艺世家":         {"talent": "创作力", "amount": 4, "desc": "父母都是搞文艺的,家里乐器比玩具还多"},
    "小城个体户家庭":   {"cash": 100,                     "desc": "家里开着一间小店,从小在柜台后面写作业"},
    "体制内工薪家庭":   {"talent": "抗压力", "amount": 3, "desc": "父母都是按部就班的上班族,规矩从小刻进骨子里"},
    "普通双职工家庭":   {"fans": 20,                       "desc": "普普通通的双职工家庭,没什么特别的故事可讲"},
    "单亲家庭长大":     {"talent": "抗压力", "amount": 5, "desc": "一个人的肩膀早早扛起了两个人的活"},
    "隔代抚养长大":     {"talent": "抗压力", "amount": 3, "desc": "爷爷奶奶带大的孩子,独立得让人心疼"},
    "北漂打拼家庭":     {"cash": 50, "talent": "抗压力", "amount": 2, "desc": "举家北漂,搬过的家比读过的学校还多"},
    "梨园世家":         {"talent": "舞蹈",   "amount": 4, "desc": "祖上唱戏的,身段是打小练出来的"},
    "体育世家":         {"talent": "舞蹈",   "amount": 3, "desc": "从小被按在体操垫上,身体协调性是练出来的"},
    "军人家庭":         {"talent": "抗压力", "amount": 6, "desc": "作息精确到分钟,吃苦对这个家来说是家常便饭"},
    "教师家庭":         {"talent": "演技",   "amount": 3, "desc": "父母站惯了讲台,表达欲和感染力是耳濡目染的"},
    "自媒体/网红家庭":  {"fans": 50,                       "desc": "父母就在镜头前讨生活,直播设备比餐桌还熟悉"},
    "华侨家庭":         {"cash": 200,                     "desc": "常年跨国往返,见的世面比同龄人多一些"},
    "模特世家":         {"talent": "颜值",   "amount": 4, "desc": "家里长辈走过秀,气质和身形是天生带的"},
    "主持人家庭":       {"talent": "镜头感", "amount": 4, "desc": "从小跟着录影棚长大,面对镜头没有陌生感"},
    "农村留守经历":     {"talent": "抗压力", "amount": 5, "desc": "父母常年在外打工,一个人扛过很多个冬天"},
    "富二代家庭":       {"cash": 500,                     "desc": "从小不缺钱,唯一缺的是没人告诉过他什么是拒绝"},
    "白手起家创业家庭": {"cash": 150,                     "desc": "家里生意是这些年一点点做起来的,知道什么是熬"},
    "追星族父母家庭":   {"fans": 30,                       "desc": "打小被爸妈拉着追星,现在轮到自己被追了"},
    "艺考集训家庭":     {"talent": "唱功",   "amount": 3, "desc": "为了考学砸了不少钱在声乐集训班上"},
    "留学归国家庭":     {"cash": 150,                     "desc": "在国外待过几年,回来带了点见过世面的松弛感"},
    "跑江湖卖艺家庭":   {"talent": "舞蹈",   "amount": 3, "desc": "祖辈走南闯北卖艺为生,台上的胆子是祖传的"},
    "互联网新贵家庭":   {"cash": 250,                     "desc": "父母赶上了行业风口,家底攒得比同龄人快"},
    "独生女/独生子家庭":{"talent": "颜值",   "amount": 3, "desc": "被精心打理长大,从小到大都是家里的焦点"},
    "摄影/传媒世家":    {"talent": "镜头感", "amount": 3, "desc": "家里镜头比人还多,面对相机是本能反应"},
    "戏曲票友家庭":     {"talent": "唱功",   "amount": 4, "desc": "耳朵从小被吊嗓子的调门喂饱,乐感是泡出来的"},
}

BIRTHPLACE_CATEGORIES = {
    "一线城市老城区":       ["北京胡同", "上海弄堂", "广州西关", "天津老城厢"],
    "一线城市新区":         ["深圳南山", "上海浦东", "北京望京", "广州珠江新城"],
    "沿海小渔村":           ["福建霞浦渔村", "浙江舟山渔村", "广东汕尾渔村", "山东荣成渔村"],
    "内陆省会城市":         ["成都", "武汉", "郑州", "长沙", "合肥"],
    "西部小县城":           ["甘肃临夏小城", "云南边陲小城", "贵州山区小城", "新疆绿洲小城"],
    "东北老工业城市":       ["沈阳", "哈尔滨", "长春", "鞍山"],
    "江南水乡古镇":         ["乌镇", "周庄", "同里", "西塘", "甪直"],
    "边境小城":             ["云南瑞丽", "广西东兴", "内蒙古满洲里", "新疆霍尔果斯"],
    "华北平原小镇":         ["河北衡水小镇", "山东聊城小镇", "河南周口小镇", "山西运城小镇"],
    "南方山区县城":         ["福建龙岩山区", "广西百色山区", "江西赣州山区", "湖南湘西山区"],
    "海边旅游城市":         ["三亚", "厦门", "青岛", "北海", "威海"],
    "中部农业大县":         ["河南周口农业县", "安徽阜阳农业县", "湖北荆州农业县", "江西上饶农业县"],
    "高原城市":             ["拉萨", "西宁", "香格里拉", "大理"],
    "港口城市":             ["宁波", "天津", "大连", "湛江", "烟台"],
    "历史古都":             ["西安", "洛阳", "南京", "开封"],
    "经济特区":             ["深圳", "珠海", "厦门", "海南自贸港小城"],
    "煤炭资源型城市":       ["山西大同", "内蒙古鄂尔多斯", "陕西榆林", "山西阳泉"],
    "南方大都市周边卫星城": ["东莞", "佛山", "苏州", "昆山"],
}

def roll_background():
    family = random.choice(list(FAMILY_BACKGROUNDS.keys()))
    category = random.choice(list(BIRTHPLACE_CATEGORIES.keys()))
    birthplace = random.choice(BIRTHPLACE_CATEGORIES[category])
    return family, birthplace

def apply_family_bonus(player_id, family, talents):
    bonus = FAMILY_BACKGROUNDS.get(family, {})
    if 'talent' in bonus:
        talents[bonus['talent']] = min(99, talents.get(bonus['talent'], 0) + bonus['amount'])
        run("UPDATE players SET talents=? WHERE id=?", (json.dumps(talents, ensure_ascii=False), player_id))
    if 'cash' in bonus:
        run("UPDATE players SET cash=cash+? WHERE id=?", (bonus['cash'], player_id))
    if 'fans' in bonus:
        run("UPDATE players SET fans_count=fans_count+? WHERE id=?", (bonus['fans'], player_id))

CAREER_LINE_LABELS = {"idol": "偶像", "singer": "歌手", "actor": "演员"}

# ── 职业线转型/兼职(单一主线可以叠加,不删除原来的线) ──────────────────────────────

CAREER_TRANSITION_COST = 800
CAREER_TRANSITION_SONG_REQUIREMENT = 3   # 转型歌手:需要跨界发过几首歌
CAREER_TRANSITION_DRAMA_REQUIREMENT = 3  # 转型演员:需要杀青过几部戏
CAREER_TRANSITION_IDOL_POPULARITY = 50   # 转型偶像:需要人气门槛

def get_career_transition_status(player):
    """返回每条职业线的状态:已经拥有 / 还差什么条件才能转型。"""
    lines = json.loads(player['career_lines'] or '[]')
    result = {}
    for line in CAREER_LINE_LABELS:
        if line in lines:
            result[line] = {'has': True, 'eligible': False, 'reason': ''}
            continue
        if line == 'singer':
            count = q("SELECT COUNT(*) c FROM songs WHERE player_id=? AND is_crossover=1",
                      (player['id'],), one=True)['c']
            ok = count >= CAREER_TRANSITION_SONG_REQUIREMENT
            reason = f"需要跨界发过 {CAREER_TRANSITION_SONG_REQUIREMENT} 首歌(目前 {count} 首)"
        elif line == 'actor':
            count = q("SELECT COUNT(*) c FROM posts WHERE player_id=? AND post_type='drama_wrap'",
                      (player['id'],), one=True)['c']
            ok = count >= CAREER_TRANSITION_DRAMA_REQUIREMENT
            reason = f"需要杀青过 {CAREER_TRANSITION_DRAMA_REQUIREMENT} 部戏(目前 {count} 部)"
        else:  # idol
            ok = player['popularity'] >= CAREER_TRANSITION_IDOL_POPULARITY
            reason = f"需要人气达到 {CAREER_TRANSITION_IDOL_POPULARITY}(目前 {player['popularity']})"
        if ok and player['cash'] < CAREER_TRANSITION_COST:
            ok = False
            reason = f"条件已经达到,但资金不够(需要 {CAREER_TRANSITION_COST})"
        result[line] = {'has': False, 'eligible': ok, 'reason': reason}
    return result

def do_career_transition(player_id, target_line):
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if not player or target_line not in CAREER_LINE_LABELS:
        return False, '职业线不存在'
    info = get_career_transition_status(player)[target_line]
    if info['has']:
        return False, '已经是这条线了'
    if not info['eligible']:
        return False, info['reason']
    lines = json.loads(player['career_lines'] or '[]')
    lines.append(target_line)
    run("UPDATE players SET career_lines=?, cash=cash-? WHERE id=?",
        (json.dumps(lines, ensure_ascii=False), CAREER_TRANSITION_COST, player_id))
    return True, f"正式转型成为{CAREER_LINE_LABELS[target_line]}了"

# ── 世界人口池 / NPC 竞争者(固定盘子,涨粉即是零和博弈) ────────────────────────────

WORLD_POOL_INITIAL = 1_000_000_000  # 世界总盘子里"还没成为任何人粉丝"的路人数量,10亿
POACH_RATIO = 0.25             # 每次涨粉,固定比例是从其他艺人那里抢来的,不全靠白嫖路人盘子

NPC_COUNT = 30
NPC_STAR_COUNT = 4   # 开局就有几个已经走红的大咖 NPC,不是所有人都从 0 开始

NPC_SURNAMES = ["林", "陈", "周", "苏", "顾", "沈", "谢", "叶", "江", "秦",
                "萧", "唐", "任", "傅", "裴", "南宫", "上官", "欧阳", "赵", "钱",
                "孙", "李", "吴", "郑", "冯", "卫", "蒋", "韩", "杨", "朱"]
NPC_GIVEN_NAMES = ["晚晴", "知遥", "星回", "予安", "子墨", "一诺", "诗涵", "逸辰",
                   "惊鸿", "如故", "念安", "清欢", "景行", "牧之", "初晴", "叙白",
                   "浅眠", "南枝", "云舟", "望舒", "长歌", "青黎", "疏影", "承霄",
                   "凝霜", "沉舟", "浮生", "听澜", "无言", "半夏", "如晦", "书遥",
                   "怀瑾", "染尘", "留白", "未鸣", "岁安", "见微", "长晏", "知微"]

def _gen_npc_name(existing_names, used_given_names):
    available_given = [g for g in NPC_GIVEN_NAMES if g not in used_given_names] or NPC_GIVEN_NAMES
    for _ in range(50):
        surname = random.choice(NPC_SURNAMES)
        given = random.choice(available_given)
        name = surname + given
        if name not in existing_names:
            return name, given
    given = random.choice(NPC_GIVEN_NAMES)
    return random.choice(NPC_SURNAMES) + given + str(random.randint(1, 99)), given

def _ensure_world_pool(db):
    row = db.execute("SELECT value FROM meta WHERE key='world_pool'").fetchone()
    if not row:
        db.execute("INSERT INTO meta (key,value) VALUES ('world_pool', ?)", (str(WORLD_POOL_INITIAL),))
        db.commit()

def _ensure_npcs(db):
    row = db.execute("SELECT COUNT(*) c FROM players WHERE is_npc=1").fetchone()
    if row[0] >= NPC_COUNT:
        return
    agency_ids = [r[0] for r in db.execute("SELECT id FROM agencies").fetchall()]
    existing_names = set(r[0] for r in db.execute("SELECT stage_name FROM players").fetchall())
    used_given_names = set()
    to_create = NPC_COUNT - row[0]
    for i in range(to_create):
        name, given = _gen_npc_name(existing_names, used_given_names)
        existing_names.add(name)
        used_given_names.add(given)
        talents = roll_talents()
        traits = roll_hidden_traits()
        talents = apply_hidden_trait_bonus(talents, traits)
        family, birthplace = roll_background()
        bonus = FAMILY_BACKGROUNDS.get(family, {})
        is_star = i < NPC_STAR_COUNT
        cash = random.randint(500, 2000) if is_star else random.randint(0, 300)
        fans = random.randint(3000, 15000) if is_star else random.randint(0, 200)
        popularity = random.randint(150, 350) if is_star else random.randint(0, 20)
        if 'talent' in bonus:
            talents[bonus['talent']] = min(99, talents.get(bonus['talent'], 0) + bonus['amount'])
        if 'cash' in bonus:
            cash += bonus['cash']
        if 'fans' in bonus:
            fans += bonus['fans']
        career_line = random.choice(list(CAREER_LINE_LABELS.keys()))
        persona_tag = random.choice(PERSONA_TAGS)
        true_personality = random.choice(PERSONA_TAGS)
        agency_id = random.choice(agency_ids) if agency_ids else None
        gender = random.choice(['male', 'female'])
        db.execute(
            "INSERT INTO players (is_npc,age,gender,stage_name,talents,hidden_traits,career_lines,agency_id,"
            "persona_tag,family_background,birthplace,true_personality,revealed,roll_count,popularity,"
            "fans_count,cash,energy,energy_updated,created_ts) "
            "VALUES (1,18,?,?,?,?,?,?,?,?,?,?,1,1,?,?,?,100,?,?)",
            (gender, name, json.dumps(talents, ensure_ascii=False), json.dumps(traits, ensure_ascii=False),
             json.dumps([career_line], ensure_ascii=False), agency_id, persona_tag, family, birthplace,
             true_personality, popularity, fans, cash, now_ts(), now_ts()))
    db.commit()

def roll_talents():
    talents = {}
    for k in TALENT_KEYS:
        r = random.random()
        if r < 0.05:
            v = random.randint(90, 99)      # 老天爷追着喂饭
        elif r < 0.12:
            v = random.randint(20, 39)      # 天生短板
        else:
            v = random.randint(55, 80)      # 大部分人中等
        talents[k] = v
    return talents

def roll_hidden_traits():
    n = random.choices([0, 1, 2], weights=[40, 45, 15])[0]
    picked = random.sample(list(HIDDEN_TRAITS.keys()), n) if n else []
    return picked

def apply_hidden_trait_bonus(talents, traits):
    for t in traits:
        boost_key = HIDDEN_TRAITS[t]["boost"]
        talents[boost_key] = min(99, talents[boost_key] + 5)
    return talents

# ── 登录态 ─────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in S:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if S.get('role') != 'admin':
            flash('无权访问', 'error')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

# ── 体力(日常活动消耗,随时间自动恢复) ────────────────────────────────────────────

MAX_ENERGY = 100
ENERGY_REGEN_SECONDS = 30  # 内测期间调快:每 30 秒回 1 点,回满约 50 分钟(正式上线前考虑调回更慢的节奏)
ENERGY_COSTS = {'daily': 10, 'persona': 15, 'clapback': 20, 'comment': 5, 'attack': 25,
                'gig': 10, 'drama_apply': 15, 'variety': 15, 'dating': 10, 'collab': 15,
                'boost_trend': 10, 'charity': 5, 'brand_apply': 12, 'release_song': 15, 'concert': 20,
                'awards_campaign': 15, 'message': 3, 'luxury_gacha': 10, 'crisis_statement': 15,
                'super_topic_checkin': 5, 'intel_basic': 8, 'intel_deep': 15,
                'commercial_shoot': 12, 'magazine': 12, 'ambassador_apply': 15, 'hate_campaign': 20,
                'cp_boost': 10, 'cp_smear': 10}

def get_effective_energy(player_id):
    row = q("SELECT energy, energy_updated FROM players WHERE id=?", (player_id,), one=True)
    if not row:
        return 0
    base_ts = row['energy_updated'] or now_ts()
    elapsed = now_ts() - base_ts
    regen = elapsed // ENERGY_REGEN_SECONDS
    if regen <= 0:
        return row['energy']
    new_energy = min(MAX_ENERGY, row['energy'] + regen)
    new_updated = base_ts + regen * ENERGY_REGEN_SECONDS
    run("UPDATE players SET energy=?, energy_updated=? WHERE id=?", (new_energy, new_updated, player_id))
    return new_energy

def try_spend_energy(player_id, action_key):
    cost = ENERGY_COSTS.get(action_key, 0)
    current = get_effective_energy(player_id)
    if current < cost:
        return False
    run("UPDATE players SET energy=energy-? WHERE id=?", (cost, player_id))
    if cost > 0:
        run("UPDATE players SET health=MAX(0,health-?) WHERE id=?", (HEALTH_DRAIN_PER_ACTION, player_id))
    return True

# ── 健康值(工作耗健康,休息/旅游回血,太低会生病没法工作) ───────────────────────────

MAX_HEALTH = 100
HEALTH_DRAIN_PER_ACTION = 1
HEALTH_SICK_THRESHOLD = 20
HEALTH_LOW_PERFORMANCE_THRESHOLD = 50
HEALTH_LOW_MALUS = -10
HEALTH_SICK_MALUS = -20
REST_COOLDOWN_SECONDS = 3600
REST_HEALTH_GAIN = 15
TRAVEL_COOLDOWN_SECONDS = 3 * 3600
TRAVEL_HEALTH_GAIN = 35
TRAVEL_COST = 300

def is_player_sick(player_id):
    row = q("SELECT career_state FROM players WHERE id=?", (player_id,), one=True)
    return row is not None and row['career_state'] == 'sick'

def health_performance_malus(health, career_state):
    if career_state == 'sick':
        return HEALTH_SICK_MALUS
    if health < HEALTH_LOW_PERFORMANCE_THRESHOLD:
        return HEALTH_LOW_MALUS
    return 0

def run_health_checks():
    run("UPDATE players SET career_state='sick' WHERE health<=? AND career_state='active'",
        (HEALTH_SICK_THRESHOLD,))
    run("UPDATE players SET career_state='active' WHERE health>? AND career_state='sick'",
        (HEALTH_SICK_THRESHOLD,))

def rest_action(player_id):
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if now_ts() - (player['last_rest_ts'] or 0) < REST_COOLDOWN_SECONDS:
        return False, '刚休息过,还没到能再休息的时间'
    run("UPDATE players SET health=MIN(?,health+?), last_rest_ts=? WHERE id=?",
        (MAX_HEALTH, REST_HEALTH_GAIN, now_ts(), player_id))
    return True, '好好休息了一下,精神好多了'

def travel_action(player_id):
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if now_ts() - (player['last_travel_ts'] or 0) < TRAVEL_COOLDOWN_SECONDS:
        return False, '刚旅游回来,还没到能再去的时间'
    if player['cash'] < TRAVEL_COST:
        return False, '资金不够去旅游'
    run("UPDATE players SET health=MIN(?,health+?), cash=cash-?, last_travel_ts=? WHERE id=?",
        (MAX_HEALTH, TRAVEL_HEALTH_GAIN, TRAVEL_COST, now_ts(), player_id))
    return True, '出去散心旅游了一趟,整个人都放松了'

def me():
    uid = S.get('uid')
    if not uid:
        return None
    row = q("SELECT * FROM players WHERE user_id=?", (uid,), one=True)
    if not row:
        return None
    player = dict(row)
    player['energy'] = get_effective_energy(player['id'])
    return player

# ── 动态通知中心(把散在各处的"待处理"事件汇总成一个红点) ───────────────────────────

def get_notification_count(player_id):
    unread_messages = q("SELECT COUNT(*) c FROM private_messages WHERE to_player_id=? AND read=0",
                        (player_id,), one=True)['c']
    unread_letters = q("SELECT COUNT(*) c FROM fan_letters WHERE player_id=? AND replied=0",
                       (player_id,), one=True)['c']
    pending_tips = q("SELECT COUNT(*) c FROM paparazzi_tips WHERE player_id=? AND status='pending'",
                     (player_id,), one=True)['c']
    seen_ts = q("SELECT notifications_seen_ts FROM players WHERE id=?", (player_id,), one=True)['notifications_seen_ts'] or 0
    new_milestones = q("SELECT COUNT(*) c FROM milestones_achieved WHERE player_id=? AND created_ts>?",
                       (player_id, seen_ts), one=True)['c']
    return {
        'messages': unread_messages, 'letters': unread_letters,
        'tips': pending_tips, 'milestones': new_milestones,
        'total': unread_messages + unread_letters + pending_tips + new_milestones,
    }

@app.context_processor
def inject_notification_count():
    player = me()
    if not player:
        return {'notification_count': 0}
    return {'notification_count': get_notification_count(player['id'])['total']}

def log_admin(action, target_type='', target_id=None, detail=''):
    run("INSERT INTO admin_logs (admin_id,target_type,target_id,action,detail,created_ts) VALUES (?,?,?,?,?,?)",
        (S.get('uid'), target_type, target_id, action, detail, now_ts()))

# ── 首页 ───────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'uid' in S:
        return redirect(url_for('weibo') if S.get('role') == 'player' else url_for('admin_home'))
    return redirect(url_for('login'))

# ── 注册(基础信息 → 天赋揭晓 → 提交审核) ───────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        qq       = request.form.get('qq', '').strip()
        stage_name = request.form.get('stage_name', '').strip()
        agency_id  = request.form.get('agency_id', '')
        career_line = request.form.get('career_line', '')
        persona_tag = request.form.get('persona_tag', '')
        gender = request.form.get('gender', '')

        err = None
        if not (2 <= len(username) <= 20):
            err = '用户名长度需在 2-20 位之间'
        elif not (6 <= len(password)):
            err = '密码至少 6 位'
        elif not qq:
            err = '请填写 QQ 号'
        elif not (1 <= len(stage_name) <= 12):
            err = '艺名长度需在 1-12 位之间'
        elif gender not in ('male', 'female'):
            err = '请选择性别'
        elif career_line not in CAREER_LINE_LABELS:
            err = '请选择一条主职业线'
        elif persona_tag not in PERSONA_TAGS:
            err = '请选择一个人设标签'
        elif not agency_id:
            err = '请选择经纪公司'
        elif q("SELECT id FROM users WHERE username=?", (username,), one=True):
            err = '用户名已被占用'

        agencies = q("SELECT * FROM agencies ORDER BY id")
        if err:
            flash(err, 'error')
            return render_template('register.html', agencies=agencies,
                                    persona_tags=PERSONA_TAGS, career_lines=CAREER_LINE_LABELS)

        db = get_db()
        cur = db.execute(
            "INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (username, generate_password_hash(password, method='pbkdf2:sha256'), qq,
             'player', 'pending', now_ts()))
        uid = cur.lastrowid
        db.execute(
            "INSERT INTO players (user_id,gender,stage_name,career_lines,agency_id,persona_tag,"
            "energy_updated,created_ts) VALUES (?,?,?,?,?,?,?,?)",
            (uid, gender, stage_name, json.dumps([career_line], ensure_ascii=False),
             int(agency_id), persona_tag, now_ts(), now_ts()))
        db.commit()
        return redirect(url_for('register_pending'))

    agencies = q("SELECT * FROM agencies ORDER BY id")
    return render_template('register.html', agencies=agencies,
                            persona_tags=PERSONA_TAGS, career_lines=CAREER_LINE_LABELS)

@app.route('/register/pending')
def register_pending():
    return render_template('register_pending.html')

# ── 审核通过后首次进入:天赋 + 出身揭晓 ────────────────────────────────────────────

@app.route('/reveal', methods=['GET', 'POST'])
@login_required
def reveal():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if player['revealed']:
        return redirect(url_for('weibo'))

    if not player['talents'] or player['talents'] == '{}':
        talents = roll_talents()
        traits = roll_hidden_traits()
        talents = apply_hidden_trait_bonus(talents, traits)
        family, birthplace = roll_background()
        true_personality = random.choice(PERSONA_TAGS)
        run("UPDATE players SET talents=?, hidden_traits=?, family_background=?, birthplace=?, "
            "true_personality=?, roll_count=1 WHERE id=?",
            (json.dumps(talents, ensure_ascii=False), json.dumps(traits, ensure_ascii=False),
             family, birthplace, true_personality, player['id']))
        player = me()

    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'reroll' and player['roll_count'] < MAX_TALENT_ROLLS:
            talents = roll_talents()
            traits = roll_hidden_traits()
            talents = apply_hidden_trait_bonus(talents, traits)
            family, birthplace = roll_background()
            true_personality = random.choice(PERSONA_TAGS)
            run("UPDATE players SET talents=?, hidden_traits=?, family_background=?, birthplace=?, "
                "true_personality=?, roll_count=roll_count+1 WHERE id=?",
                (json.dumps(talents, ensure_ascii=False), json.dumps(traits, ensure_ascii=False),
                 family, birthplace, true_personality, player['id']))
            return redirect(url_for('reveal'))
        elif action == 'confirm':
            talents = json.loads(player['talents'] or '{}')
            apply_family_bonus(player['id'], player['family_background'], talents)
            run("UPDATE players SET revealed=1 WHERE id=?", (player['id'],))
            return redirect(url_for('weibo'))
        return redirect(url_for('reveal'))

    player_view = dict(player)
    player_view['talents'] = json.loads(player_view['talents'] or '{}')
    player_view['traits'] = json.loads(player_view['hidden_traits'] or '[]')
    player_view['career_line'] = json.loads(player_view['career_lines'] or '[]')[0]
    agency = q("SELECT * FROM agencies WHERE id=?", (player_view['agency_id'],), one=True)
    return render_template('reveal.html', player=player_view, agency=agency,
                            career_line_label=CAREER_LINE_LABELS.get(player_view['career_line']),
                            trait_info=HIDDEN_TRAITS, family_info=FAMILY_BACKGROUNDS,
                            max_rolls=MAX_TALENT_ROLLS)

# ── 登录 / 登出 ─────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if not user or not check_password_hash(user['password_hash'], password):
            err = '账号或密码错误'
        elif user['status'] == 'pending':
            err = '账号审核中,请等待管理员审核'
        elif user['status'] == 'rejected':
            err = '账号审核未通过'
        else:
            S.permanent = True
            S['uid'] = user['id']; S['uname'] = user['username']; S['role'] = user['role']
            run("UPDATE users SET last_login=? WHERE id=?", (now_ts(), user['id']))
            if user['role'] == 'admin':
                return redirect(url_for('admin_home'))
            player = q("SELECT revealed FROM players WHERE user_id=?", (user['id'],), one=True)
            return redirect(url_for('weibo') if player and player['revealed'] else url_for('reveal'))
    return render_template('login.html', err=err)

@app.route('/logout')
def logout():
    S.clear()
    return redirect(url_for('login'))

# ── 管理员专用登录 ───────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if user and user['role'] == 'admin' and check_password_hash(user['password_hash'], password):
            S.permanent = True
            S['uid'] = user['id']; S['uname'] = user['username']; S['role'] = 'admin'
            run("UPDATE users SET last_login=? WHERE id=?", (now_ts(), user['id']))
            return redirect(url_for('admin_home'))
        err = '账号或密码错误(仅管理员可用此入口)'
    return render_template('admin_login.html', err=err)

# ── 管理后台:首页统计 ────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_home():
    stats = {
        'pending':  q("SELECT COUNT(*) c FROM users WHERE status='pending'", one=True)['c'],
        'approved': q("SELECT COUNT(*) c FROM users WHERE status='approved' AND role='player'", one=True)['c'],
        'rejected': q("SELECT COUNT(*) c FROM users WHERE status='rejected'", one=True)['c'],
        'posts':    q("SELECT COUNT(*) c FROM posts", one=True)['c'],
    }
    return render_template('admin/home.html', stats=stats)

# ── 管理后台:待审核账号队列 ───────────────────────────────────────────────────────

@app.route('/admin/pending_users')
@admin_required
def admin_pending_users():
    status_filter = request.args.get('status', 'pending')
    if status_filter == 'all':
        rows = q("SELECT * FROM users WHERE role='player' ORDER BY created_ts DESC")
    else:
        rows = q("SELECT * FROM users WHERE role='player' AND status=? ORDER BY created_ts DESC",
                  (status_filter,))
    entries = []
    for u in rows:
        p = q("SELECT * FROM players WHERE user_id=?", (u['id'],), one=True)
        p_dict = None
        if p:
            p_dict = dict(p)
            p_dict['career_lines_list'] = json.loads(p_dict['career_lines'] or '[]')
        entries.append({'user': dict(u), 'player': p_dict})
    counts = {
        'pending':  q("SELECT COUNT(*) c FROM users WHERE role='player' AND status='pending'", one=True)['c'],
        'approved': q("SELECT COUNT(*) c FROM users WHERE role='player' AND status='approved'", one=True)['c'],
        'rejected': q("SELECT COUNT(*) c FROM users WHERE role='player' AND status='rejected'", one=True)['c'],
    }
    return render_template('admin/pending_users.html', entries=entries, counts=counts,
                            status_filter=status_filter, career_line_labels=CAREER_LINE_LABELS)

@app.route('/admin/users/<int:uid>/approve', methods=['POST'])
@admin_required
def admin_user_approve(uid):
    run("UPDATE users SET status='approved' WHERE id=?", (uid,))
    log_admin('approve', 'user', uid)
    flash('已通过审核', 'ok')
    return redirect(url_for('admin_pending_users'))

@app.route('/admin/users/<int:uid>/reject', methods=['POST'])
@admin_required
def admin_user_reject(uid):
    run("UPDATE users SET status='rejected' WHERE id=?", (uid,))
    log_admin('reject', 'user', uid)
    flash('已拒绝', 'ok')
    return redirect(url_for('admin_pending_users'))

# ── 管理后台:艺人数据管控 ─────────────────────────────────────────────────────────

@app.route('/admin/players')
@admin_required
def admin_players():
    rows = q("""SELECT p.*, u.username, u.qq FROM players p
                JOIN users u ON u.id = p.user_id
                WHERE u.status='approved' ORDER BY p.popularity DESC""")
    return render_template('admin/players.html', players=rows)

EDITABLE_PLAYER_FIELDS = [
    'popularity', 'scandal_value', 'fans_count', 'core_fan_loyalty',
    'cash', 'persona_integrity', 'persona_tag', 'stage_name',
]

@app.route('/admin/player/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_player_detail(pid):
    player = q("SELECT p.*, u.username, u.qq FROM players p JOIN users u ON u.id=p.user_id WHERE p.id=?",
               (pid,), one=True)
    if not player:
        flash('找不到该艺人', 'error')
        return redirect(url_for('admin_players'))

    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'set_field':
            field = request.form.get('field', '')
            value = request.form.get('value', '')
            if field in EDITABLE_PLAYER_FIELDS:
                if field in ('persona_tag', 'stage_name'):
                    run(f"UPDATE players SET {field}=? WHERE id=?", (value, pid))
                else:
                    try:
                        value = int(value)
                    except ValueError:
                        value = 0
                    run(f"UPDATE players SET {field}=? WHERE id=?", (value, pid))
                log_admin('set_field', 'player', pid, f'{field}={value}')
        elif action == 'set_talent':
            key = request.form.get('talent_key', '')
            value = request.form.get('value', '0')
            if key in TALENT_KEYS:
                talents = json.loads(player['talents'] or '{}')
                try:
                    talents[key] = int(value)
                except ValueError:
                    pass
                run("UPDATE players SET talents=? WHERE id=?",
                    (json.dumps(talents, ensure_ascii=False), pid))
                log_admin('set_talent', 'player', pid, f'{key}={value}')
        flash('已更新', 'ok')
        return redirect(url_for('admin_player_detail', pid=pid))

    agencies = q("SELECT * FROM agencies ORDER BY id")
    return render_template('admin/player_detail.html', player=player,
                            talents=json.loads(player['talents'] or '{}'),
                            traits=json.loads(player['hidden_traits'] or '[]'),
                            talent_keys=TALENT_KEYS, agencies=agencies)

@app.route('/admin/npcs')
@admin_required
def admin_npcs():
    rows = q("""SELECT p.*, a.agency_name FROM players p LEFT JOIN agencies a ON a.id = p.agency_id
               WHERE p.is_npc=1 ORDER BY p.popularity DESC""")
    return render_template('admin/npcs.html', npcs=rows)

# ── 管理后台:剧组/品牌/颁奖 只读列表 + 强制结算 ──────────────────────────────────────

@app.route('/admin/dramas')
@admin_required
def admin_dramas():
    dramas = q("SELECT * FROM dramas ORDER BY open_ts DESC LIMIT 30")
    drama_views = []
    for d in dramas:
        roles = q("""SELECT r.*, p.stage_name as winner_name FROM drama_roles r
                     LEFT JOIN players p ON p.id = r.winner_player_id
                     WHERE r.drama_id=? ORDER BY r.id""", (d['id'],))
        drama_views.append({'drama': dict(d), 'roles': roles})
    return render_template('admin/dramas.html', drama_views=drama_views)

@app.route('/admin/dramas/<int:drama_id>/force_resolve', methods=['POST'])
@admin_required
def admin_force_resolve_drama(drama_id):
    run("UPDATE dramas SET apply_close_ts=1 WHERE id=?", (drama_id,))
    run("UPDATE drama_roles SET shoot_end_ts=1 WHERE drama_id=? AND status='shooting'", (drama_id,))
    resolve_casting()
    resolve_shooting()
    log_admin('force_resolve', 'drama', drama_id)
    flash('已强制结算', 'ok')
    return redirect(url_for('admin_dramas'))

@app.route('/admin/brands')
@admin_required
def admin_brands():
    rows = q("""SELECT b.*, p.stage_name as signed_name FROM brands b
               LEFT JOIN players p ON p.id = b.signed_player_id
               ORDER BY b.created_ts DESC LIMIT 30""")
    return render_template('admin/brands.html', brands=rows)

@app.route('/admin/brands/<int:brand_id>/force_resolve', methods=['POST'])
@admin_required
def admin_force_resolve_brand(brand_id):
    brand = q("SELECT * FROM brands WHERE id=?", (brand_id,), one=True)
    if brand:
        if brand['status'] == 'open':
            run("UPDATE brands SET apply_close_ts=1 WHERE id=?", (brand_id,))
        elif brand['status'] == 'signed':
            run("UPDATE brands SET contract_end_ts=1 WHERE id=?", (brand_id,))
        resolve_brand_casting()
        check_brand_contracts()
        log_admin('force_resolve', 'brand', brand_id)
    flash('已强制结算', 'ok')
    return redirect(url_for('admin_brands'))

@app.route('/admin/awards')
@admin_required
def admin_awards():
    seasons = q("SELECT * FROM award_seasons ORDER BY created_ts DESC LIMIT 10")
    season_views = []
    for s in seasons:
        categories = q("SELECT * FROM award_categories WHERE season_id=?", (s['id'],))
        cat_views = []
        for c in categories:
            nominees = q("""SELECT n.*, p.stage_name FROM award_nominees n JOIN players p ON p.id = n.player_id
                           WHERE n.category_id=? ORDER BY n.won DESC, n.vote_score DESC""", (c['id'],))
            cat_views.append({'category': dict(c), 'nominees': nominees})
        season_views.append({'season': dict(s), 'categories': cat_views})
    return render_template('admin/awards.html', season_views=season_views)

@app.route('/admin/awards/<int:season_id>/force_resolve', methods=['POST'])
@admin_required
def admin_force_resolve_awards(season_id):
    run("UPDATE award_seasons SET campaign_end_ts=1 WHERE id=?", (season_id,))
    resolve_award_season()
    log_admin('force_resolve', 'award_season', season_id)
    flash('已强制结算', 'ok')
    return redirect(url_for('admin_awards'))

# ── 发微博 ─────────────────────────────────────────────────────────────────────

POST_EDIT_WINDOW_SECONDS = 3600  # 杀青/颁奖这类系统自动发博,离线玩家事后还能改感言的窗口

COMPOSABLE_POST_TYPES = {'daily': '日常营业', 'persona': '人设向发言', 'clapback': '怼黑评'}
POST_TYPE_LABELS = {**COMPOSABLE_POST_TYPES, 'drama_wrap': '剧组杀青',
                    'variety': '综艺录制', 'collab': '联合营业', 'dating_exposed': '恋情曝光',
                    'boosted': '买热搜', 'collapse': '塌房', 'brand_terminated': '代言解约',
                    'brand_complete': '代言达成', 'song_release': '发新歌', 'concert': '演唱会',
                    'bribe_exposed': '评奖黑幕', 'award_won': '颁奖典礼', 'dm_leaked': '私聊泄露',
                    'luxury_flex': '奢侈品晒图', 'crisis_statement': '危机公关声明',
                    'commercial_shoot': '商业拍摄', 'magazine': '杂志专访',
                    'ambassador_won': '荣升代言人', 'ambassador_lost': '代言人卸任',
                    'milestone': '里程碑', 'lifestyle_flex': '生活方式晒图', 'hate_campaign': '黑粉攻势'}

FAN_COMMENTS = [
    "哥哥今天也太帅了吧", "疯狂打call,支持到底", "这个状态绝了,顶起来",
    "已经循环播放八百遍了", "宝子今天也在认真营业呢", "眼睛狠狠瞪大了",
    "醒醒,人间不值得,只有他值得", "已经存好图当壁纸了", "这个爱豆我磕定了",
    "谁懂啊家人们,这也太好哭了", "反复观看根本停不下来", "这才是真正的实力派",
    "跟着他一起加油,冲冲冲", "永远相信自己家哥哥/姐姐", "这条微博我留着当传家宝",
    "这波业务能力直接封神", "护崽护到底,谁都别想欺负他", "越努力越幸运,加油",
]
HATER_COMMENTS = [
    "又开始立人设了,呵呵", "没实力就别硬凹了", "这作态真是一言难尽",
    "路人观感直接归零", "该学学怎么好好说话了", "求求别再刷屏了",
    "这波营销痕迹有点重", "内味儿又出来了", "建议专心搞业务别老整这些",
    "看完只想说一句好家伙", "这波公关稿写得挺用心", "路人缘怕是要吃紧了",
    "水军痕迹这么明显真的绷不住", "这自我感觉是不是有点良好", "求别再上热搜刷屏了",
]
PASSERBY_COMMENTS = [
    "路过打个酱油", "所以这是谁啊", "看了眼热搜过来的", "感觉还行吧,没啥感觉",
    "不认识,但祝生活愉快", "刷到就看看,不做评价", "这年头出名真快",
    "路人看戏中,坐等后续", "第一次听说这个名字", "随便看看,没什么特别想法",
]

HOMETOWN_CHANCE = 0.05  # 出身背景/出生地彩蛋,纯文本,不影响任何数值结算
HOMETOWN_FAMILY_COMMENTS = [
    "没想到还是{tag}老乡,格外亲切", "同样是{tag}出身,一下就有共鸣了",
    "{tag}出来的都不容易,懂的都懂", "看到{tag}背景就想多聊两句",
]
HOMETOWN_BIRTHPLACE_COMMENTS = [
    "老家的孩子出息了,与有荣焉", "没想到还是半个老乡,亲切了不少",
    "一听就知道是自己人,支持一下", "老乡见老乡,必须来打个招呼",
]

def _find_hometown_match(poster_id, poster_family, poster_birthplace):
    poster_category = None
    for cat, places in BIRTHPLACE_CATEGORIES.items():
        if poster_birthplace in places:
            poster_category = cat
            break
    candidates = q("SELECT id, stage_name, family_background, birthplace FROM players WHERE id != ?", (poster_id,))
    matches = []
    for c in candidates:
        if poster_family and c['family_background'] == poster_family:
            matches.append((c, 'family'))
        elif poster_category and c['birthplace'] in BIRTHPLACE_CATEGORIES.get(poster_category, []):
            matches.append((c, 'birthplace'))
    return random.choice(matches) if matches else None

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

RIVAL_HATE_CHANCE = 0.35
RIVAL_POP_TRANSFER = (1, 3)

def distribute_fan_gain(player_id, gain):
    """涨粉是零和博弈:大部分来自世界路人盘子,一部分固定从其他艺人那里抢过来。"""
    if gain <= 0:
        return
    row = q("SELECT value FROM meta WHERE key='world_pool'", one=True)
    world_pool = int(row['value']) if row and row['value'] else 0

    target_poach = max(0, round(gain * POACH_RATIO))
    from_pool = min(gain - target_poach, world_pool)
    poach_amount = gain - from_pool  # 池子不够时,缺口也走抢别人这条路

    if from_pool > 0:
        run("UPDATE meta SET value=? WHERE key='world_pool'", (str(world_pool - from_pool),))

    gained = from_pool
    if poach_amount > 0:
        victims = list(q("SELECT id, fans_count FROM players WHERE id != ? AND fans_count > 0 "
                          "ORDER BY RANDOM() LIMIT 3", (player_id,)))
        if victims:
            remaining = poach_amount
            for v in victims:
                if remaining <= 0:
                    break
                take = min(max(1, remaining // len(victims)), v['fans_count'], remaining)
                if take <= 0:
                    continue
                run("UPDATE players SET fans_count=fans_count-? WHERE id=?", (take, v['id']))
                gained += take
                remaining -= take
        else:
            gained += poach_amount  # 世界上还没有别的粉丝可抢,缺口只能算白来的

    run("UPDATE players SET fans_count=fans_count+? WHERE id=?", (gained, player_id))

def generate_comments(post_id, poster_id, fan_w, hater_w, passerby_w):
    n = random.randint(2, 5)
    pool = (['fan'] * fan_w) + (['hater'] * hater_w) + (['passerby'] * passerby_w)
    rival_assigned = False
    for _ in range(n):
        stance = random.choice(pool)
        rival_id = None
        content = random.choice({'fan': FAN_COMMENTS, 'hater': HATER_COMMENTS,
                                  'passerby': PASSERBY_COMMENTS}[stance])
        if stance == 'hater' and not rival_assigned and random.random() < RIVAL_HATE_CHANCE:
            rival = q("SELECT id, stage_name FROM players WHERE id != ? ORDER BY RANDOM() LIMIT 1",
                      (poster_id,), one=True)
            if rival:
                rival_id = rival['id']
                content = f"还是{rival['stage_name']}那边比较有实力,不像有些人"
                rival_assigned = True
                transfer = random.randint(*RIVAL_POP_TRANSFER)
                run("UPDATE players SET popularity=MAX(0,popularity-?) WHERE id=?", (transfer, poster_id))
                run("UPDATE players SET popularity=popularity+? WHERE id=?", (transfer, rival_id))
        run("INSERT INTO post_comments (post_id,stance,content,rival_player_id,created_ts) VALUES (?,?,?,?,?)",
            (post_id, stance, content, rival_id, now_ts()))

    if random.random() < HOMETOWN_CHANCE:
        poster = q("SELECT family_background, birthplace FROM players WHERE id=?", (poster_id,), one=True)
        match = _find_hometown_match(poster_id, poster['family_background'], poster['birthplace']) if poster else None
        if match:
            commenter, kind = match
            if kind == 'family':
                content = random.choice(HOMETOWN_FAMILY_COMMENTS).format(tag=commenter['family_background'])
            else:
                content = random.choice(HOMETOWN_BIRTHPLACE_COMMENTS)
            run("INSERT INTO post_comments (post_id,stance,content,commenter_id,created_ts) VALUES (?,?,?,?,?)",
                (post_id, 'celebrity', content, commenter['id'], now_ts()))

CRISIS_STANCE_LABELS = {'deny': '强硬否认', 'apologize': '卖惨求原谅', 'aloof': '云淡风轻'}

def resolve_post_effects(player, post_type, content, stance=None):
    """player 可以是真人玩家也可以是 NPC,行走同一套判定,这样 NPC 和真人在同一个世界里公平竞争。"""
    if player['career_state'] == 'blackout' and post_type != 'crisis_statement':
        return 'blackout'
    if not try_spend_energy(player['id'], post_type):
        return 'no_energy'
    traits = json.loads(player['hidden_traits'] or '[]')
    talents = json.loads(player['talents'] or '{}')
    outcome = 'ok'
    heat = 8

    if post_type == 'crisis_statement':
        if stance == 'deny':
            if random.random() < 0.5:
                run("UPDATE players SET scandal_value=MAX(0,scandal_value-?), popularity=popularity+? WHERE id=?",
                    (random.randint(15, 25), random.randint(1, 5), player['id']))
                outcome = 'success'
            else:
                run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?",
                    (random.randint(5, 15), player['id']))
                outcome = 'fail'
        elif stance == 'apologize':
            run("UPDATE players SET scandal_value=MAX(0,scandal_value-?), fans_count=fans_count+? WHERE id=?",
                (random.randint(10, 20), random.randint(5, 20), player['id']))
            outcome = 'ok'
        else:  # aloof,最安全但收益最小
            run("UPDATE players SET scandal_value=MAX(0,scandal_value-?) WHERE id=?",
                (random.randint(5, 10), player['id']))
            outcome = 'ok'
        heat = 20

    elif post_type == 'daily':
        today_start = now_ts() - 24 * 3600
        today_count = q("SELECT COUNT(*) c FROM posts WHERE player_id=? AND post_type='daily' AND created_ts>?",
                         (player['id'], today_start), one=True)['c']
        pop_gain = max(1, 3 - today_count)
        fans_gain = max(2, random.randint(5, 20) - today_count * 3)
        run("UPDATE players SET popularity=popularity+? WHERE id=?", (pop_gain, player['id']))
        distribute_fan_gain(player['id'], fans_gain)
        heat = 8

    elif post_type == 'persona':
        success_chance = clamp(player['persona_integrity'], 20, 90)
        if random.randint(1, 100) <= success_chance:
            outcome = 'success'
            run("UPDATE players SET persona_integrity=MIN(100,persona_integrity+3), popularity=popularity+? WHERE id=?",
                (random.randint(4, 10), player['id']))
            heat = 15
        else:
            outcome = 'fail'
            run("UPDATE players SET persona_integrity=MAX(0,persona_integrity-5), scandal_value=scandal_value+? WHERE id=?",
                (random.randint(2, 6), player['id']))
            heat = 12

    elif post_type == 'clapback':
        blunt_bonus = 30 if '钝感力max' in traits else 0
        success_chance = clamp(
            50 + (talents.get('抗压力', 50) - 50) * 0.6 - player['scandal_value'] * 0.3, 10, 90)
        if random.randint(1, 100) <= success_chance:
            outcome = 'success'
            run("UPDATE players SET popularity=popularity+? WHERE id=?",
                (random.randint(5, 10), player['id']))
            distribute_fan_gain(player['id'], random.randint(10, 30))
            heat = 25
        else:
            outcome = 'fail'
            scandal_gain = random.randint(8, 15)
            if blunt_bonus:
                scandal_gain = max(1, int(scandal_gain * 0.7))
            run("UPDATE players SET scandal_value=scandal_value+?, popularity=MAX(0,popularity-?) WHERE id=?",
                (scandal_gain, random.randint(3, 8), player['id']))
            heat = 30

    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player['id'], post_type, content, outcome, heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid

    if outcome == 'success':
        generate_comments(post_id, player['id'], fan_w=5, hater_w=1, passerby_w=2)
    elif outcome == 'fail':
        generate_comments(post_id, player['id'], fan_w=1, hater_w=5, passerby_w=2)
    else:
        generate_comments(post_id, player['id'], fan_w=3, hater_w=1, passerby_w=2)

    return outcome

# ── 买黑料 / 买狗仔造谣(攻击其他艺人) ─────────────────────────────────────────────

ATTACK_COST = 150
ATTACK_SCANDAL_RANGE = (10, 25)
ATTACK_BACKFIRE_CHANCE = 25  # 百分比,爆料被拆穿的概率

def execute_attack(attacker_id, target_id):
    attacker = q("SELECT * FROM players WHERE id=?", (attacker_id,), one=True)
    if not attacker or attacker['cash'] < ATTACK_COST or attacker['career_state'] == 'blackout':
        return None
    if not try_spend_energy(attacker_id, 'attack'):
        return None
    run("UPDATE players SET cash=cash-? WHERE id=?", (ATTACK_COST, attacker_id))
    backfire = random.randint(1, 100) <= ATTACK_BACKFIRE_CHANCE
    amount = random.randint(*ATTACK_SCANDAL_RANGE)
    if backfire:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?",
            (int(amount * 1.5), attacker_id))
    else:
        target = q("SELECT anti_scandal_reserve FROM players WHERE id=?", (target_id,), one=True)
        absorbed = min(target['anti_scandal_reserve'], amount // 2) if target else 0
        if absorbed > 0:
            run("UPDATE players SET anti_scandal_reserve=anti_scandal_reserve-? WHERE id=?", (absorbed, target_id))
            amount -= absorbed
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (amount, target_id))
    run("INSERT INTO boosts (player_id,boost_type,target_player_id,amount,backfire,created_ts) "
        "VALUES (?,?,?,?,?,?)",
        (attacker_id, 'buy_scandal', target_id, amount, int(backfire), now_ts()))
    return backfire

# ── 黑料情报市场(攻击前的侦查环节,只提供信息,不改变攻击判定) ───────────────────────

INTEL_TIERS = {
    'basic': {'cost': 80, 'energy_key': 'intel_basic', 'label': '基础档', 'min_tier': None},
    'deep':  {'cost': 200, 'energy_key': 'intel_deep', 'label': '深度档', 'min_tier': 'C'},
}
INTEL_FRESH_SECONDS = 24 * 3600

def buy_intel(buyer_id, target_id, tier):
    if tier not in INTEL_TIERS:
        return False, '档位不存在'
    buyer = q("SELECT * FROM players WHERE id=?", (buyer_id,), one=True)
    target = q("SELECT * FROM players WHERE id=?", (target_id,), one=True)
    if not buyer or not target or buyer_id == target_id:
        return False, '目标无效'
    spec = INTEL_TIERS[tier]
    if spec['min_tier'] and not meets_tier(buyer['popularity'], spec['min_tier']):
        return False, f"咖位不够,深度档需要 {spec['min_tier']} 级以上"
    if buyer['cash'] < spec['cost']:
        return False, '资金不足'
    if not try_spend_energy(buyer_id, spec['energy_key']):
        return False, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (spec['cost'], buyer_id))

    talents = json.loads(target['talents'] or '{}')
    if tier == 'basic':
        weakest = sorted(talents.items(), key=lambda kv: kv[1])[:2]
        revealed = {'weak_talents': [k for k, _ in weakest]}
    else:
        revealed = {'talents': talents, 'hidden_traits': json.loads(target['hidden_traits'] or '[]')}

    run("INSERT INTO intel_reports (buyer_player_id,target_player_id,tier,revealed_json,created_ts) "
        "VALUES (?,?,?,?,?)",
        (buyer_id, target_id, tier, json.dumps(revealed, ensure_ascii=False), now_ts()))
    return True, f"已经拿到{target['stage_name']}的{spec['label']}情报"

# ── 狗仔私信爆料(线人主动推送线索,不是玩家自己挑目标) ────────────────────────────

PAPARAZZI_TIP_TEMPLATES = [
    "线人偷偷告诉我,{target}这几天行程有点反常,像是在遮掩什么。",
    "有狗仔蹲到消息,说{target}片场耍大牌,被工作人员偷拍了。",
    "内部消息:{target}最近好像在偷偷谈恋爱,要不要往下查?",
    "圈里传{target}这次的资源来路不太干净,值得挖一挖。",
    "刚收到爆料,{target}好像卷进了一件说不清楚的事。",
]
PAPARAZZI_TIP_COUNT = 3

def ensure_paparazzi_tips(player_id):
    pending = q("SELECT COUNT(*) c FROM paparazzi_tips WHERE player_id=? AND status='pending'",
                (player_id,), one=True)['c']
    need = PAPARAZZI_TIP_COUNT - pending
    if need <= 0:
        return
    existing_targets = {r['target_player_id'] for r in q(
        "SELECT target_player_id FROM paparazzi_tips WHERE player_id=? AND status='pending'", (player_id,))}
    candidates = [c for c in q("SELECT id, stage_name FROM players WHERE id != ?", (player_id,))
                  if c['id'] not in existing_targets]
    random.shuffle(candidates)
    for c in candidates[:need]:
        tip_text = random.choice(PAPARAZZI_TIP_TEMPLATES).format(target=c['stage_name'])
        run("INSERT INTO paparazzi_tips (player_id,target_player_id,tip_text,created_ts) VALUES (?,?,?,?)",
            (player_id, c['id'], tip_text, now_ts()))

# ── 雇职业黑粉(独立于私生饭,买一场持续几轮的组织化黑评攻势) ────────────────────────

HATE_CAMPAIGN_COST = 300
HATE_CAMPAIGN_TICKS = 3

def hire_hate_campaign(hirer_id, target_id):
    hirer = q("SELECT * FROM players WHERE id=?", (hirer_id,), one=True)
    target = q("SELECT * FROM players WHERE id=?", (target_id,), one=True)
    if not hirer or not target or hirer_id == target_id:
        return False, '目标无效'
    if hirer['cash'] < HATE_CAMPAIGN_COST:
        return False, '资金不足'
    if not try_spend_energy(hirer_id, 'hate_campaign'):
        return False, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (HATE_CAMPAIGN_COST, hirer_id))
    run("INSERT INTO hate_campaigns (hirer_player_id,target_player_id,ticks_remaining,created_ts) "
        "VALUES (?,?,?,?)", (hirer_id, target_id, HATE_CAMPAIGN_TICKS, now_ts()))
    content = "评论区突然被大量黑评攻陷,风评一夜之间变差"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (target_id, 'hate_campaign', content, 'attacked', 28, now_ts()))
    get_db().commit()
    generate_comments(cur.lastrowid, target_id, fan_w=1, hater_w=6, passerby_w=2)
    return True, f"已经安排人手长期黑{target['stage_name']}了"

def run_hate_campaigns():
    active = q("SELECT * FROM hate_campaigns WHERE ticks_remaining > 0")
    for row in active:
        run("UPDATE players SET fans_count=MAX(0,fans_count-?), scandal_value=scandal_value+? WHERE id=?",
            (random.randint(10, 30), random.randint(3, 8), row['target_player_id']))
        run("UPDATE hate_campaigns SET ticks_remaining=ticks_remaining-1 WHERE id=?", (row['id'],))

# ── 买热搜(正面花钱刷话题,和买黑料对应) ──────────────────────────────────────────

BOOST_TREND_COST = 100

def buy_trend(player_id):
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if not player or player['cash'] < BOOST_TREND_COST or player['career_state'] == 'blackout':
        return None
    if not try_spend_energy(player_id, 'boost_trend'):
        return None
    today_start = now_ts() - 24 * 3600
    today_count = q("SELECT COUNT(*) c FROM boosts WHERE player_id=? AND boost_type='buy_trend' AND created_ts>?",
                     (player_id, today_start), one=True)['c']
    heat = max(5, random.randint(20, 40) - today_count * 8)  # 边际递减,同一天反复砸钱效果打折
    run("UPDATE players SET cash=cash-?, popularity=popularity+? WHERE id=?",
        (BOOST_TREND_COST, heat // 4, player_id))
    run("INSERT INTO boosts (player_id,boost_type,amount,created_ts) VALUES (?,?,?,?)",
        (player_id, 'buy_trend', heat, now_ts()))
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player_id, 'boosted', f"{player['stage_name']}买了一波热搜,话题度蹭蹭涨", 'ok', heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    generate_comments(post_id, player_id, fan_w=3, hater_w=2, passerby_w=3)  # 买热搜容易被看出来,黑粉占比稍高
    return heat

# ── 反黑值资源(公关团队常驻能力,平时攒着,遇袭时自动抵消部分伤害,也能主动清黑值) ──────

ANTI_SCANDAL_PASSIVE_GAIN = 1
ANTI_SCANDAL_MAX = 100

def accrue_anti_scandal_reserve():
    run("UPDATE players SET anti_scandal_reserve=MIN(?,anti_scandal_reserve+?)", (ANTI_SCANDAL_MAX, ANTI_SCANDAL_PASSIVE_GAIN))

def use_anti_scandal_reserve(player_id):
    player = q("SELECT anti_scandal_reserve, scandal_value FROM players WHERE id=?", (player_id,), one=True)
    if not player:
        return 0
    use_amount = min(player['anti_scandal_reserve'], player['scandal_value'])
    if use_amount > 0:
        run("UPDATE players SET anti_scandal_reserve=anti_scandal_reserve-?, scandal_value=scandal_value-? WHERE id=?",
            (use_amount, use_amount, player_id))
    return use_amount

# ── 塌房状态机(翻红弧光):黑值会自然回落,冲过阈值直接雪藏,期间只能做公益 ──────────────

SCANDAL_COLLAPSE_THRESHOLD = 80
BLACKOUT_DURATION_SECONDS = 6 * 3600
CHARITY_SCANDAL_RANGE = (5, 12)

def is_blacked_out(player):
    return player['career_state'] == 'blackout'

def trigger_collapse(player_id):
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if not player or player['career_state'] == 'blackout':
        return
    fan_loss = int(player['fans_count'] * 0.3)
    pop_loss = int(player['popularity'] * 0.4)
    run("""UPDATE players SET career_state='blackout', blackout_until_ts=?, scandal_value=?,
           fans_count=MAX(0,fans_count-?), popularity=MAX(0,popularity-?) WHERE id=?""",
        (now_ts() + BLACKOUT_DURATION_SECONDS, SCANDAL_COLLAPSE_THRESHOLD // 2, fan_loss, pop_loss, player_id))
    content = f"{player['stage_name']}塌房了,官方通告全部取消,进入无限期雪藏"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player_id, 'collapse', content, 'collapse', 50, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    generate_comments(post_id, player_id, fan_w=1, hater_w=6, passerby_w=3)

def decay_scandal_and_check_collapse():
    rows = q("SELECT id, scandal_value, career_state FROM players")
    for p in rows:
        if p['career_state'] == 'blackout' or p['scandal_value'] <= 0:
            continue
        decay = max(1, p['scandal_value'] // 20)
        new_scandal = max(0, p['scandal_value'] - decay)
        if new_scandal >= SCANDAL_COLLAPSE_THRESHOLD:
            trigger_collapse(p['id'])
        else:
            run("UPDATE players SET scandal_value=? WHERE id=?", (new_scandal, p['id']))

def lift_blackout_if_due():
    due = q("SELECT id FROM players WHERE career_state='blackout' AND blackout_until_ts <= ?", (now_ts(),))
    for p in due:
        run("UPDATE players SET career_state='normal' WHERE id=?", (p['id'],))

def do_charity(player):
    if not try_spend_energy(player['id'], 'charity'):
        return None, '体力不够了'
    reduction = random.randint(*CHARITY_SCANDAL_RANGE)
    run("UPDATE players SET scandal_value=MAX(0,scandal_value-?), fans_count=fans_count+? WHERE id=?",
        (reduction, random.randint(1, 5), player['id']))
    return reduction, None

# ── 粉丝超话打卡(死忠粉忠诚度的主要出口,每天有边际递减) ────────────────────────────

def do_super_topic_checkin(player, content):
    if player['career_state'] == 'blackout':
        return None, '雪藏期不能打卡'
    if not try_spend_energy(player['id'], 'super_topic_checkin'):
        return None, '体力不够了'
    today_start = now_ts() - 24 * 3600
    today_count = q("SELECT COUNT(*) c FROM super_topic_posts WHERE player_id=? AND created_ts>?",
                     (player['id'], today_start), one=True)['c']
    gain = max(1, random.randint(2, 6) - today_count)
    run("UPDATE players SET core_fan_loyalty=core_fan_loyalty+? WHERE id=?", (gain, player['id']))
    run("INSERT INTO super_topic_posts (player_id,content,created_ts) VALUES (?,?,?)",
        (player['id'], content, now_ts()))
    return gain, None

# ── 商品销量模拟(杂志/代言发售后跑一套实时销量,和超话安利互相挂钩) ───────────────────

PRODUCT_SALES_GROWTH_TICKS = 5
PRODUCT_HYPE_TEMPLATES = [
    "还不快去买{name}这期的{product}!",
    "姐妹们冲!{name}的{product}上架了,冲销量",
    "{name}的{product}已经安排上了,大家多多支持",
]

def launch_product_sales(player, post_id, product_name):
    initial = player['popularity'] + player['core_fan_loyalty'] * 2 + random.randint(50, 200)
    run("INSERT INTO product_sales (player_id,post_id,product_name,sales_count,ticks_remaining,created_ts) "
        "VALUES (?,?,?,?,?,?)",
        (player['id'], post_id, product_name, initial, PRODUCT_SALES_GROWTH_TICKS, now_ts()))
    hype = random.choice(PRODUCT_HYPE_TEMPLATES).format(name=player['stage_name'], product=product_name)
    run("INSERT INTO super_topic_posts (player_id,content,created_ts) VALUES (?,?,?)",
        (player['id'], hype, now_ts()))

def grow_product_sales():
    active = q("SELECT * FROM product_sales WHERE ticks_remaining > 0")
    for row in active:
        player = q("SELECT core_fan_loyalty FROM players WHERE id=?", (row['player_id'],), one=True)
        loyalty = player['core_fan_loyalty'] if player else 0
        gain = random.randint(20, 80) + loyalty // 4
        run("UPDATE product_sales SET sales_count=sales_count+?, ticks_remaining=ticks_remaining-1 WHERE id=?",
            (gain, row['id']))

# ── 接通告(持续性小额收入,每天有边际递减) ─────────────────────────────────────────

def do_gig(player):
    if player['career_state'] == 'blackout':
        return None
    if not try_spend_energy(player['id'], 'gig'):
        return None
    today_start = now_ts() - 24 * 3600
    today_count = q("SELECT COUNT(*) c FROM boosts WHERE player_id=? AND boost_type='gig' AND created_ts>?",
                     (player['id'], today_start), one=True)['c']
    base = 20 + player['popularity'] // 3
    cash_gain = max(5, base - today_count * 5) + random.randint(0, 15)
    run("UPDATE players SET cash=cash+? WHERE id=?", (cash_gain, player['id']))
    run("INSERT INTO boosts (player_id,boost_type,amount,created_ts) VALUES (?,?,?,?)",
        (player['id'], 'gig', cash_gain, now_ts()))
    return cash_gain

# ── 咖位等级(由人气派生,决定能不能抢哪个角色) ────────────────────────────────────

TIER_LADDER = ['D', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+', 'S']
TIER_THRESHOLDS = [0, 5, 15, 30, 50, 75, 105, 140, 180, 225, 280]

def get_tier(popularity):
    tier = TIER_LADDER[0]
    for i, th in enumerate(TIER_THRESHOLDS):
        if popularity >= th:
            tier = TIER_LADDER[i]
    return tier

def tier_index(tier):
    return TIER_LADDER.index(tier) if tier in TIER_LADDER else 0

def meets_tier(popularity, required_tier):
    return tier_index(get_tier(popularity)) >= tier_index(required_tier)

# ── 抢角色(知名 IP 大剧,按性别+咖位分角色,报名 → 定角 → 拍摄 → 播出口碑) ─────────────

# 每个角色: 角色名 / 性别要求 / 最低咖位 / 看重的属性 / 资金奖励区间 / 人气奖励区间
DRAMA_TEMPLATES = [
    {"title": "《甄嬛传》", "budget": "S", "roles": [  # 全女班底,没有男主
        {"name": "女主角(甄嬛)", "gender": "female", "tier": "S",  "talent": "演技", "cash": (3000, 5000), "pop": (80, 120)},
        {"name": "女二号(华妃)", "gender": "female", "tier": "A",  "talent": "颜值", "cash": (1000, 1800), "pop": (30, 50)},
        {"name": "女三号(皇后)", "gender": "female", "tier": "A",  "talent": "演技", "cash": (1000, 1800), "pop": (30, 50)},
    ]},
    {"title": "《琅琊榜》", "budget": "S", "roles": [  # 全男班底,没有女主
        {"name": "男主角(梅长苏)", "gender": "male", "tier": "S",  "talent": "演技",   "cash": (3000, 5000), "pop": (80, 120)},
        {"name": "男二号(靖王)",   "gender": "male", "tier": "A",  "talent": "抗压力", "cash": (1000, 1800), "pop": (30, 50)},
        {"name": "男三号(言豫津)", "gender": "male", "tier": "B+", "talent": "镜头感", "cash": (400, 800),   "pop": (10, 20)},
    ]},
    {"title": "《陈情令》", "budget": "S", "roles": [  # 全男班底,没有女主
        {"name": "男主角(魏无羡)", "gender": "male", "tier": "S", "talent": "唱功", "cash": (2800, 4800), "pop": (70, 110)},
        {"name": "男二号(蓝忘机)", "gender": "male", "tier": "A", "talent": "颜值", "cash": (900, 1600),  "pop": (25, 45)},
    ]},
    {"title": "《花千骨》", "budget": "S", "roles": [
        {"name": "女主角(花千骨)", "gender": "female", "tier": "S", "talent": "演技", "cash": (3000, 5000), "pop": (80, 120)},
        {"name": "男主角(白子画)", "gender": "male",   "tier": "S", "talent": "演技", "cash": (3000, 5000), "pop": (80, 120)},
    ]},
    {"title": "《延禧攻略》", "budget": "S", "roles": [  # 全女班底,没有男主
        {"name": "女主角(魏璎珞)", "gender": "female", "tier": "S", "talent": "演技", "cash": (2800, 4800), "pop": (70, 110)},
        {"name": "女二号(高贵妃)", "gender": "female", "tier": "A", "talent": "颜值", "cash": (900, 1600),  "pop": (25, 45)},
    ]},
    {"title": "《三生三世十里桃花》", "budget": "S", "roles": [
        {"name": "女主角(白浅)", "gender": "female", "tier": "S", "talent": "颜值", "cash": (3000, 5000), "pop": (80, 120)},
        {"name": "男主角(夜华)", "gender": "male",   "tier": "S", "talent": "演技", "cash": (3000, 5000), "pop": (80, 120)},
    ]},
    {"title": "《长安十二时辰》", "budget": "S", "roles": [  # 没有女主
        {"name": "男主角(张小敬)", "gender": "male", "tier": "S", "talent": "抗压力", "cash": (3000, 5000), "pop": (80, 120)},
        {"name": "男二号(李必)",   "gender": "male", "tier": "A", "talent": "创作力", "cash": (1000, 1800), "pop": (30, 50)},
    ]},
    {"title": "《人民的名义》", "budget": "A", "roles": [  # 没有女主
        {"name": "男主角(侯亮平)", "gender": "male", "tier": "A",  "talent": "演技",   "cash": (800, 1500), "pop": (25, 45)},
        {"name": "男二号(达康书记)", "gender": "male", "tier": "B+", "talent": "抗压力", "cash": (400, 700), "pop": (10, 20)},
    ]},
    {"title": "《欢乐颂》", "budget": "A", "roles": [  # 全女班底,没有男主
        {"name": "女主角(安迪)",   "gender": "female", "tier": "A",  "talent": "演技", "cash": (800, 1500), "pop": (25, 45)},
        {"name": "女二号(樊胜美)", "gender": "female", "tier": "B+", "talent": "演技", "cash": (400, 700),  "pop": (10, 20)},
        {"name": "女三号(曲筱绡)", "gender": "female", "tier": "B",  "talent": "颜值", "cash": (300, 600),  "pop": (10, 20)},
    ]},
    {"title": "《都挺好》", "budget": "A", "roles": [
        {"name": "女主角(苏明玉)", "gender": "female", "tier": "A",  "talent": "演技", "cash": (800, 1500), "pop": (25, 45)},
        {"name": "男二号(苏大强)", "gender": "male",   "tier": "B+", "talent": "演技", "cash": (400, 700),  "pop": (10, 20)},
    ]},
    {"title": "《我的前半生》", "budget": "A", "roles": [
        {"name": "女主角(罗子君)", "gender": "female", "tier": "A",  "talent": "演技",   "cash": (800, 1500), "pop": (25, 45)},
        {"name": "男二号(贺涵)",   "gender": "male",   "tier": "B+", "talent": "镜头感", "cash": (400, 700),  "pop": (10, 20)},
    ]},
    {"title": "《知否知否应是绿肥红瘦》", "budget": "A", "roles": [
        {"name": "女主角(明兰)",   "gender": "female", "tier": "A", "talent": "演技", "cash": (800, 1500), "pop": (25, 45)},
        {"name": "男主角(顾廷烨)", "gender": "male",   "tier": "A", "talent": "演技", "cash": (800, 1500), "pop": (25, 45)},
    ]},
    {"title": "《庆余年》", "budget": "A", "roles": [  # 没有女主
        {"name": "男主角(范闲)", "gender": "male", "tier": "A",  "talent": "创作力", "cash": (800, 1500), "pop": (25, 45)},
        {"name": "男二号(五竹)", "gender": "male", "tier": "B+", "talent": "抗压力", "cash": (400, 700),  "pop": (10, 20)},
    ]},
    {"title": "《山河令》", "budget": "A", "roles": [  # 没有女主
        {"name": "男主角(周子舒)", "gender": "male", "tier": "A", "talent": "唱功", "cash": (800, 1500), "pop": (25, 45)},
        {"name": "男二号(温客行)", "gender": "male", "tier": "A", "talent": "演技", "cash": (800, 1500), "pop": (25, 45)},
    ]},
    {"title": "《扫黑风暴》", "budget": "A", "roles": [
        {"name": "男主角(李成阳)", "gender": "male",   "tier": "A",  "talent": "抗压力", "cash": (800, 1500), "pop": (25, 45)},
        {"name": "女二号(林浩)",   "gender": "female", "tier": "B+", "talent": "演技",   "cash": (400, 700),  "pop": (10, 20)},
    ]},
    {"title": "《觉醒年代》", "budget": "A", "roles": [  # 没有女主
        {"name": "男主角(陈独秀)", "gender": "male", "tier": "A",  "talent": "演技",   "cash": (800, 1500), "pop": (25, 45)},
        {"name": "男二号(李大钊)", "gender": "male", "tier": "B+", "talent": "抗压力", "cash": (400, 700),  "pop": (10, 20)},
    ]},
    {"title": "《爱情公寓》", "budget": "B", "roles": [
        {"name": "男主角(曾小贤)", "gender": "male",   "tier": "B", "talent": "演技", "cash": (200, 400), "pop": (8, 15)},
        {"name": "女主角(胡一菲)", "gender": "female", "tier": "B", "talent": "演技", "cash": (200, 400), "pop": (8, 15)},
        {"name": "男二号(吕子乔)", "gender": "male",   "tier": "C", "talent": "颜值", "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《武林外传》", "budget": "B", "roles": [
        {"name": "女主角(佟湘玉)", "gender": "female", "tier": "B", "talent": "演技", "cash": (200, 400), "pop": (8, 15)},
        {"name": "男二号(白展堂)", "gender": "male",   "tier": "C", "talent": "演技", "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《家有儿女》", "budget": "B", "roles": [
        {"name": "男主角(刘星)", "gender": "male",   "tier": "B", "talent": "演技", "cash": (200, 400), "pop": (8, 15)},
        {"name": "女二号(小雪)", "gender": "female", "tier": "C", "talent": "颜值", "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《乡村爱情》", "budget": "B", "roles": [
        {"name": "男主角(谢广坤)", "gender": "male",   "tier": "B", "talent": "演技", "cash": (200, 400), "pop": (8, 15)},
        {"name": "女二号(王小蒙)", "gender": "female", "tier": "C", "talent": "颜值", "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《我在他乡挺好的》", "budget": "B", "roles": [  # 全女班底,没有男主
        {"name": "女主角(乔夕辰)", "gender": "female", "tier": "B", "talent": "演技", "cash": (200, 400), "pop": (8, 15)},
        {"name": "女二号(纪南嘉)", "gender": "female", "tier": "C", "talent": "唱功", "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《小欢喜》", "budget": "B", "roles": [
        {"name": "女主角(童文洁)", "gender": "female", "tier": "B", "talent": "演技", "cash": (200, 400), "pop": (8, 15)},
        {"name": "男二号(方圆)",   "gender": "male",   "tier": "C", "talent": "演技", "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《隐秘的角落》", "budget": "B", "roles": [  # 没有女主
        {"name": "男主角(张东升)", "gender": "male", "tier": "B", "talent": "演技",   "cash": (200, 400), "pop": (8, 15)},
        {"name": "男二号(朱朝阳)", "gender": "male", "tier": "C", "talent": "创作力", "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《沉默的真相》", "budget": "B", "roles": [
        {"name": "男主角(江阳)", "gender": "male",   "tier": "B", "talent": "抗压力", "cash": (200, 400), "pop": (8, 15)},
        {"name": "女二号(严良)", "gender": "female", "tier": "C", "talent": "演技",   "cash": (50, 120),  "pop": (2, 6)},
    ]},
    {"title": "《破事精英》", "budget": "C", "roles": [
        {"name": "男配角", "gender": "male",   "tier": "D", "talent": "演技", "cash": (30, 80), "pop": (1, 3)},
        {"name": "女配角", "gender": "female", "tier": "D", "talent": "演技", "cash": (30, 80), "pop": (1, 3)},
    ]},
    {"title": "《我是余欢水》", "budget": "C", "roles": [  # 全剧只有一个男主名额,没有女主
        {"name": "男主角(余欢水)", "gender": "male", "tier": "D", "talent": "演技", "cash": (30, 80), "pop": (1, 3)},
    ]},
    {"title": "《棋魂》", "budget": "C", "roles": [  # 没有女主
        {"name": "男主角(时光)", "gender": "male", "tier": "D", "talent": "创作力", "cash": (30, 80), "pop": (1, 3)},
        {"name": "男二号(褚嬴)", "gender": "male", "tier": "D", "talent": "演技",   "cash": (30, 80), "pop": (1, 3)},
    ]},
    # 以下是质量一般的虚构小IP(网大/竖屏短剧),纯凑数刷经验用,回报比上面的真实大IP更低
    {"title": "竖屏短剧《霸道总裁的第一百次追妻》", "budget": "D", "roles": [
        {"name": "女主角(顾晚晚)",   "gender": "female", "tier": "D", "talent": "颜值", "cash": (15, 40), "pop": (1, 2)},
        {"name": "男二号(总裁替身)", "gender": "male",   "tier": "D", "talent": "演技", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "网络电影《我在废墟捡到亿万富翁》", "budget": "D", "roles": [  # 没有女主
        {"name": "男主角(阿贵)", "gender": "male", "tier": "D", "talent": "演技", "cash": (15, 40), "pop": (1, 2)},
    ]},
    {"title": "竖屏短剧《离婚后我成了京圈太子妃》", "budget": "D", "roles": [
        {"name": "女主角(苏晚)",     "gender": "female", "tier": "D", "talent": "演技", "cash": (15, 40), "pop": (1, 2)},
        {"name": "男二号(落魄少爷)", "gender": "male",   "tier": "D", "talent": "颜值", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "网络大电影《赘婿的逆袭》", "budget": "D", "roles": [  # 没有女主
        {"name": "男主角(陈平安)", "gender": "male", "tier": "D", "talent": "抗压力", "cash": (15, 40), "pop": (1, 2)},
    ]},
    {"title": "竖屏短剧《穿越成猎户家的傻丫头》", "budget": "D", "roles": [  # 没有男主
        {"name": "女主角(小丫)", "gender": "female", "tier": "D", "talent": "演技", "cash": (15, 40), "pop": (1, 2)},
    ]},
    {"title": "网络电影《保安队长的逆袭人生》", "budget": "D", "roles": [  # 没有女主
        {"name": "男主角(老李)", "gender": "male", "tier": "D", "talent": "抗压力", "cash": (15, 40), "pop": (1, 2)},
    ]},
    {"title": "竖屏短剧《退婚后前未婚夫跪地求原谅》", "budget": "D", "roles": [
        {"name": "女主角(林小姐)",   "gender": "female", "tier": "D", "talent": "颜值", "cash": (15, 40), "pop": (1, 2)},
        {"name": "男二号(悔婚少爷)", "gender": "male",   "tier": "D", "talent": "演技", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "网络大电影《山寨古装:皇后娘娘要下岗》", "budget": "D", "roles": [
        {"name": "女主角(假皇后)",     "gender": "female", "tier": "D", "talent": "创作力", "cash": (15, 40), "pop": (1, 2)},
        {"name": "男二号(伪太监总管)", "gender": "male",   "tier": "D", "talent": "镜头感", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "短剧《我在民国当赘婿》", "budget": "D", "roles": [
        {"name": "男主角(沈知行)", "gender": "male",   "tier": "D", "talent": "演技", "cash": (15, 40), "pop": (1, 2)},
        {"name": "女二号(白月光)", "gender": "female", "tier": "D", "talent": "颜值", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "网络剧《重生之我在小区当保安》", "budget": "D", "roles": [  # 没有女主
        {"name": "男主角(周大力)", "gender": "male", "tier": "D", "talent": "抗压力", "cash": (15, 40), "pop": (1, 2)},
    ]},
    {"title": "短剧《千金归来虐渣打脸》", "budget": "D", "roles": [
        {"name": "女主角(顾念念)",   "gender": "female", "tier": "D", "talent": "演技", "cash": (15, 40), "pop": (1, 2)},
        {"name": "男二号(渣男前任)", "gender": "male",   "tier": "D", "talent": "颜值", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "网络剧《古装糊涂县令断案记》", "budget": "D", "roles": [  # 没有女主
        {"name": "男主角(县令)", "gender": "male", "tier": "D", "talent": "创作力", "cash": (15, 40), "pop": (1, 2)},
    ]},
    {"title": "短剧《赛博朋克风:机械师的复仇》", "budget": "D", "roles": [
        {"name": "男主角(阿泽)",   "gender": "male",   "tier": "D", "talent": "镜头感", "cash": (15, 40), "pop": (1, 2)},
        {"name": "女二号(女黑客)", "gender": "female", "tier": "D", "talent": "创作力", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "网络剧《小镇姑娘的直播人生》", "budget": "D", "roles": [  # 没有男主
        {"name": "女主角(小美)", "gender": "female", "tier": "D", "talent": "唱功", "cash": (15, 40), "pop": (1, 2)},
    ]},
    {"title": "短剧《我的老公是个咸鱼富豪》", "budget": "D", "roles": [
        {"name": "女主角(江小满)",   "gender": "female", "tier": "D", "talent": "颜值", "cash": (15, 40), "pop": (1, 2)},
        {"name": "男二号(隐藏富豪)", "gender": "male",   "tier": "D", "talent": "演技", "cash": (10, 25), "pop": (1, 1)},
    ]},
    {"title": "网络剧《废土求生:末日直播间》", "budget": "D", "roles": [  # 没有女主
        {"name": "男主角(阿凯)", "gender": "male", "tier": "D", "talent": "抗压力", "cash": (15, 40), "pop": (1, 2)},
    ]},
]

MONTH_SECONDS = 7200  # 游戏内"1个月" = 现实2小时

DAILY_DRAMA_RELEASE_MIN = 3
DAILY_DRAMA_RELEASE_MAX = 4
MAX_CONCURRENT_DRAMAS = 24  # 兜底上限,防止长期没人接导致无限堆积,不是日常触发的门槛
DRAMA_APPLY_WINDOW_SECONDS = MONTH_SECONDS          # 面试期 1 个月
DRAMA_RELEASE_INTERVAL_SECONDS = MONTH_SECONDS * 2  # 每 4 小时(游戏内2个月)放一批新剧本

# 进组后占用的档期长短按剧组体量决定(单位:月),电影天然比电视剧耗时更长
TV_SHOOT_MONTHS   = {'S': 4, 'A': 3, 'B': 2, 'C': 1, 'D': 1}
FILM_SHOOT_MONTHS = {'S': 6, 'A': 5, 'B': 4}

def shoot_duration_seconds(fmt, budget_tier):
    table = FILM_SHOOT_MONTHS if fmt == 'film' else TV_SHOOT_MONTHS
    return table.get(budget_tier, 1) * MONTH_SECONDS

def is_actor_busy(player_id):
    """进组拍摄中算占用档期,不能同时轧另一部戏;报名/面试阶段不算。"""
    return q("SELECT 1 FROM drama_roles WHERE winner_player_id=? AND status='shooting'",
             (player_id,), one=True) is not None

# 收视率:人气30% + 剧本水平20% + 演员表现(safe/risky小游戏产出)20% + 运气30%
SCRIPT_QUALITY_BASE = {'S': 75, 'A': 65, 'B': 55, 'C': 45, 'D': 35}

def compute_rating_score(popularity, budget_tier, match_val):
    pop_component = clamp(popularity, 0, 200) / 2
    script_component = clamp(SCRIPT_QUALITY_BASE.get(budget_tier, 50) + random.randint(-8, 8), 0, 100)
    perf_component = clamp(match_val, 0, 100)
    luck_component = random.randint(0, 100)
    return round(pop_component * 0.3 + script_component * 0.2 + perf_component * 0.2 + luck_component * 0.3)

def get_meta(key, default=None):
    row = q("SELECT value FROM meta WHERE key=?", (key,), one=True)
    return row['value'] if row else default

def set_meta(key, value):
    run("INSERT INTO meta (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)))

def _create_drama(template, now, fmt='tv'):
    cur = get_db().execute(
        "INSERT INTO dramas (title,budget_tier,format,open_ts,apply_close_ts) VALUES (?,?,?,?,?)",
        (template['title'], template['budget'], fmt, now, now + DRAMA_APPLY_WINDOW_SECONDS))
    get_db().commit()
    drama_id = cur.lastrowid
    for role in template['roles']:
        run("INSERT INTO drama_roles (drama_id,role_name,gender_requirement,tier_requirement,"
            "requirement_talent,reward_cash,reward_popularity,status,created_ts) "
            "VALUES (?,?,?,?,?,?,?,'casting',?)",
            (drama_id, role['name'], role['gender'], role['tier'], role['talent'],
             random.randint(*role['cash']), random.randint(*role['pop']), now))

def maybe_open_drama():
    """每 4 小时(游戏内2个月)放一批新剧(3-4部),不是常态补位式的"少于N部就补一部"。"""
    last_ts = int(get_meta('last_drama_release_ts', 0))
    if now_ts() - last_ts < DRAMA_RELEASE_INTERVAL_SECONDS:
        return
    set_meta('last_drama_release_ts', now_ts())

    open_count = q("""SELECT COUNT(DISTINCT drama_id) c FROM drama_roles
                     WHERE status IN ('casting','shooting')""", one=True)['c']
    if open_count >= MAX_CONCURRENT_DRAMAS:
        return  # 兜底:堆积太多了,今天先不放,等消化

    active_titles = {r['title'] for r in q(
        """SELECT DISTINCT d.title FROM dramas d JOIN drama_roles r ON r.drama_id = d.id
           WHERE r.status IN ('casting','shooting')""")}
    candidates = [t for t in DRAMA_TEMPLATES if t['title'] not in active_titles]
    batch_size = random.randint(DAILY_DRAMA_RELEASE_MIN, DAILY_DRAMA_RELEASE_MAX)
    random.shuffle(candidates)
    chosen = candidates[:batch_size]
    if len(chosen) < batch_size:
        # 池子不够用了(同名剧不能同时在跑),从全量模板里补,允许和历史剧重名
        filler = [t for t in DRAMA_TEMPLATES if t not in chosen]
        random.shuffle(filler)
        chosen += filler[:batch_size - len(chosen)]

    now = now_ts()
    for template in chosen:
        _create_drama(template, now)

# ── 电影(比电视剧门槛更高:只开 S/A 级,还要求获过奖,放送频率也低很多) ────────────────

FILM_MIN_AWARDS = 1
FILM_RELEASE_INTERVAL_DAYS = 3

FILM_TEMPLATES = [
    {"title": "《流浪地球》", "budget": "S", "roles": [
        {"name": "男主角(刘培强)", "gender": "male", "tier": "S", "talent": "抗压力", "cash": (5000, 8000), "pop": (100, 150)},
    ]},
    {"title": "《你好,李焕英》", "budget": "S", "roles": [
        {"name": "女主角(贾晓玲)", "gender": "female", "tier": "S", "talent": "演技", "cash": (5000, 8000), "pop": (100, 150)},
    ]},
    {"title": "《我不是药神》", "budget": "A", "roles": [
        {"name": "男主角(程勇)", "gender": "male", "tier": "A", "talent": "演技", "cash": (3000, 5000), "pop": (60, 100)},
    ]},
    {"title": "《满江红》", "budget": "S", "roles": [
        {"name": "男主角", "gender": "male", "tier": "S", "talent": "演技",   "cash": (5000, 8000), "pop": (100, 150)},
        {"name": "男二号", "gender": "male", "tier": "A", "talent": "抗压力", "cash": (2000, 3500), "pop": (40, 70)},
    ]},
    {"title": "《长津湖》", "budget": "S", "roles": [
        {"name": "男主角", "gender": "male", "tier": "S", "talent": "抗压力", "cash": (5000, 8000), "pop": (100, 150)},
    ]},
    {"title": "《封神第一部》", "budget": "S", "roles": [
        {"name": "男主角(姬发)", "gender": "male",   "tier": "S", "talent": "颜值", "cash": (5000, 8000), "pop": (100, 150)},
        {"name": "女主角(妲己)", "gender": "female", "tier": "S", "talent": "颜值", "cash": (5000, 8000), "pop": (100, 150)},
    ]},
    # 以下是虚构小成本电影(网络电影/网大),门槛比上面几部真实大片低,给刚拿到第一个奖、还够不上S级真片的人一个过渡
    {"title": "网络电影《逆袭之路》", "budget": "B", "roles": [  # 没有女主
        {"name": "男主角(林浩)", "gender": "male", "tier": "B", "talent": "抗压力", "cash": (1500, 2500), "pop": (30, 50)},
    ]},
    {"title": "网络电影《平凡人的英雄时刻》", "budget": "B", "roles": [  # 没有男主
        {"name": "女主角(苏晴)", "gender": "female", "tier": "B", "talent": "演技", "cash": (1500, 2500), "pop": (30, 50)},
    ]},
    {"title": "网大《都市侠客》", "budget": "B", "roles": [
        {"name": "男主角(阿龙)", "gender": "male",   "tier": "B", "talent": "演技", "cash": (1500, 2500), "pop": (30, 50)},
        {"name": "女二号(搭档)", "gender": "female", "tier": "B", "talent": "颜值", "cash": (800, 1300),  "pop": (15, 25)},
    ]},
    {"title": "网络电影《小城故事多》", "budget": "B", "roles": [  # 没有男主
        {"name": "女主角(阿雅)", "gender": "female", "tier": "B", "talent": "唱功", "cash": (1500, 2500), "pop": (30, 50)},
    ]},
]

def maybe_open_film():
    """电影比电视剧稀有得多,每 3 天才放一部,门槛也全部锁在 S/A 级。"""
    if not get_meta('last_drama_release_ts'):
        return  # 世界还没放过第一批剧,电影也先不放

    today = now_ts() // 86400
    last_day = int(get_meta('last_film_release_day', -1))
    if today - last_day < FILM_RELEASE_INTERVAL_DAYS:
        return
    set_meta('last_film_release_day', today)

    active_titles = {r['title'] for r in q(
        """SELECT DISTINCT d.title FROM dramas d JOIN drama_roles r ON r.drama_id = d.id
           WHERE r.status IN ('casting','shooting') AND d.format='film'""")}
    candidates = [t for t in FILM_TEMPLATES if t['title'] not in active_titles] or FILM_TEMPLATES
    template = random.choice(candidates)
    _create_drama(template, now_ts(), fmt='film')

# ── 试镜PK小游戏(报名后和NPC对手对戏,选择会影响定角判定) ──────────────────────────

AUDITION_CHALLENGE_ROUNDS = 2
RIVAL_NAME_POOL = [
    "苏黎", "陆屿", "林知遥", "顾念", "夏晚枝", "沈微光", "季白",
    "程若曦", "谢云舒", "宋亦臻", "凌小满", "萧景琛",
]
AUDITION_PROMPT_TEMPLATES = [
    "对手{rival}这段即兴发挥很有记忆点,{role}这里你怎么接?",
    "导演让你和{rival}对一段即兴戏,{role}这段你打算怎么演?",
    "{rival}刚刚那条又快又准,轮到你的{role},稳一点还是搏一把?",
    "候场室里{rival}状态很好,进去对{role}这段你怎么处理?",
]

def generate_audition_challenges(application_id, role_name, rival_name):
    prompts = random.sample(AUDITION_PROMPT_TEMPLATES, AUDITION_CHALLENGE_ROUNDS)
    for i, prompt in enumerate(prompts, start=1):
        run("INSERT INTO audition_challenges (application_id,round_no,prompt,created_ts) VALUES (?,?,?,?)",
            (application_id, i, prompt.format(role=role_name, rival=rival_name), now_ts()))

def answer_audition_challenge(player_id, challenge_id, choice):
    if choice not in ('safe', 'risky'):
        return False, '无效的选择'
    challenge = q("SELECT * FROM audition_challenges WHERE id=?", (challenge_id,), one=True)
    if not challenge:
        return False, '这轮试戏不存在'
    application = q("SELECT * FROM role_applications WHERE id=?", (challenge['application_id'],), one=True)
    if not application or application['player_id'] != player_id:
        return False, '这个试镜现在不能操作'
    role = q("SELECT status FROM drama_roles WHERE id=?", (application['role_id'],), one=True)
    if not role or role['status'] != 'casting':
        return False, '这个角色已经定角了'
    if challenge['chosen']:
        return False, '这轮已经对过戏了'
    run("UPDATE audition_challenges SET chosen=? WHERE id=?", (choice, challenge_id))
    return True, '对完这段戏了'

def audition_bonus(application_id, talent_value):
    rows = q("SELECT chosen FROM audition_challenges WHERE application_id=?", (application_id,))
    return safe_risky_bonus([r['chosen'] for r in rows], talent_value)

def apply_for_role(player_id, role_id):
    if q("SELECT id FROM role_applications WHERE role_id=? AND player_id=?",
         (role_id, player_id), one=True):
        return False, '已经报过名了'
    role = q("SELECT * FROM drama_roles WHERE id=?", (role_id,), one=True)
    if not role or role['status'] != 'casting':
        return False, '角色已经不在报名阶段'
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if player['career_state'] == 'blackout':
        return False, '雪藏期不能接戏'
    if player['career_state'] == 'sick':
        return False, '生病了,先把身体养好'
    if is_actor_busy(player_id):
        return False, '档期被占满了,先把手头的戏拍完'
    if role['gender_requirement'] != 'any' and player['gender'] != role['gender_requirement']:
        return False, '性别不符合角色要求'
    if not meets_tier(player['popularity'], role['tier_requirement']):
        return False, '咖位不够,拿不下这个角色'
    drama = q("SELECT format FROM dramas WHERE id=?", (role['drama_id'],), one=True)
    if drama and drama['format'] == 'film' and player['awards_won'] < FILM_MIN_AWARDS:
        return False, f'还没拿过奖,接不到电影(至少需要获奖 {FILM_MIN_AWARDS} 次)'
    if not try_spend_energy(player_id, 'drama_apply'):
        return False, '体力不够了'
    talents = json.loads(player['talents'] or '{}')
    score = talents.get(role['requirement_talent'], 50) + random.randint(-10, 10) + player['awards_won'] * 3
    rival_name = random.choice(RIVAL_NAME_POOL)
    cur = get_db().execute(
        "INSERT INTO role_applications (role_id,player_id,match_score,rival_name,created_ts) VALUES (?,?,?,?,?)",
        (role_id, player_id, score, rival_name, now_ts()))
    get_db().commit()
    generate_audition_challenges(cur.lastrowid, role['role_name'], rival_name)
    return True, '报名成功'

# ── 演戏小游戏(中选后的表演选择,影响最终杀青判定) ──────────────────────────────────

ACTING_CHALLENGE_ROUNDS = 3
ACTING_SAFE_BONUS = 2
ACTING_RISKY_TALENT_THRESHOLD = 70
ACTING_RISKY_HIT_BONUS = 8
ACTING_RISKY_MISS_PENALTY = -6
ACTING_PROMPT_TEMPLATES = [
    "这场{role}的重头戏,你打算怎么处理?",
    "导演喊卡之前,{role}这段情绪你要怎么演?",
    "对手演员临场加了词,{role}这里你怎么接?",
    "这条{role}的长镜头,一次过还是稳一点来?",
    "剧本里{role}这段没写清楚,你想怎么补?",
]

def generate_acting_challenges(role_id, role_name):
    prompts = random.sample(ACTING_PROMPT_TEMPLATES, ACTING_CHALLENGE_ROUNDS)
    for i, prompt in enumerate(prompts, start=1):
        run("INSERT INTO acting_challenges (role_id,round_no,prompt,created_ts) VALUES (?,?,?,?)",
            (role_id, i, prompt.format(role=role_name), now_ts()))

def answer_acting_challenge(player_id, challenge_id, choice):
    if choice not in ('safe', 'risky'):
        return False, '无效的选择'
    challenge = q("SELECT * FROM acting_challenges WHERE id=?", (challenge_id,), one=True)
    if not challenge:
        return False, '这轮戏份不存在'
    role = q("SELECT * FROM drama_roles WHERE id=?", (challenge['role_id'],), one=True)
    if not role or role['winner_player_id'] != player_id or role['status'] != 'shooting':
        return False, '这个角色现在不能操作'
    if challenge['chosen']:
        return False, '这轮已经演过了'
    run("UPDATE acting_challenges SET chosen=? WHERE id=?", (choice, challenge_id))
    return True, '演完这段了'

def acting_challenge_bonus(role_id, talent_value):
    rows = q("SELECT chosen FROM acting_challenges WHERE role_id=?", (role_id,))
    return safe_risky_bonus([r['chosen'] for r in rows], talent_value)

def safe_risky_bonus(choices, talent_value):
    """演戏/演唱会共用的"稳扎稳打/放手一搏"计分,choices 是 'safe'/'risky' 的列表。"""
    bonus = 0
    for choice in choices:
        if choice == 'safe':
            bonus += ACTING_SAFE_BONUS
        elif choice == 'risky':
            bonus += ACTING_RISKY_HIT_BONUS if talent_value >= ACTING_RISKY_TALENT_THRESHOLD else ACTING_RISKY_MISS_PENALTY
    return bonus

NPC_AUDITION_PICKS_PER_ROLE = (1, 3)  # 每个开放角色随机抽1-3个NPC去试镜,不是全员海投

def npc_auto_audition():
    """NPC 主动抢戏/抢面试,和玩家走同一套 apply_for_role/resolve_casting 管线,玩家可能被挤掉。"""
    open_roles = q("SELECT * FROM drama_roles WHERE status='casting'")
    for role in open_roles:
        already = {a['player_id'] for a in q(
            "SELECT player_id FROM role_applications WHERE role_id=?", (role['id'],))}
        candidates = q("""SELECT id FROM players WHERE is_npc=1 AND career_state='active'
                          AND (gender=? OR ?='any')""",
                       (role['gender_requirement'], role['gender_requirement']))
        pool = [c['id'] for c in candidates if c['id'] not in already and not is_actor_busy(c['id'])]
        random.shuffle(pool)
        for pid in pool[:random.randint(*NPC_AUDITION_PICKS_PER_ROLE)]:
            apply_for_role(pid, role['id'])

def resolve_casting():
    due_roles = q("""SELECT r.* FROM drama_roles r JOIN dramas d ON d.id = r.drama_id
                     WHERE r.status='casting' AND d.apply_close_ts <= ?""", (now_ts(),))
    for role in due_roles:
        apps = list(q("SELECT * FROM role_applications WHERE role_id=?", (role['id'],)))
        scored = []
        for a in apps:
            if is_actor_busy(a['player_id']):
                continue  # 已经在别的剧组拍摄中(含本次批量结算里刚定下的),不能轧戏
            applicant = q("SELECT talents FROM players WHERE id=?", (a['player_id'],), one=True)
            talents = json.loads(applicant['talents'] or '{}') if applicant else {}
            talent_val = talents.get(role['requirement_talent'], 50)
            effective_score = a['match_score'] + audition_bonus(a['id'], talent_val)
            scored.append((effective_score, a))
        scored.sort(key=lambda x: -x[0])

        winner_id, is_npc_fill = None, 0
        if scored:
            winner_id = scored[0][1]['player_id']
        else:
            # 没人报名(或报了名的都在别的剧组拍摄中),NPC 自动补位,大公司签的 NPC 优先
            candidates = q("""SELECT p.id, a.tier as agency_tier, p.popularity FROM players p
                              LEFT JOIN agencies a ON a.id = p.agency_id
                              WHERE p.is_npc=1 AND (p.gender=? OR ?='any')""",
                           (role['gender_requirement'], role['gender_requirement']))
            eligible = [c for c in candidates
                        if meets_tier(c['popularity'], role['tier_requirement']) and not is_actor_busy(c['id'])]
            if eligible:
                weights = [3 if c['agency_tier'] == 'major' else 1 for c in eligible]
                winner_id = random.choices(eligible, weights=weights)[0]['id']
                is_npc_fill = 1
        if winner_id:
            drama = q("SELECT format, budget_tier FROM dramas WHERE id=?", (role['drama_id'],), one=True)
            shoot_seconds = shoot_duration_seconds(drama['format'], drama['budget_tier']) if drama else MONTH_SECONDS
            run("UPDATE drama_roles SET status='shooting', winner_player_id=?, winner_is_npc_fill=?, "
                "shoot_end_ts=? WHERE id=?",
                (winner_id, is_npc_fill, now_ts() + shoot_seconds, role['id']))
            winner_row = q("SELECT is_npc FROM players WHERE id=?", (winner_id,), one=True)
            if winner_row and not winner_row['is_npc']:
                generate_acting_challenges(role['id'], role['role_name'])
        else:
            run("UPDATE drama_roles SET status='aired' WHERE id=?", (role['id'],))  # 彻底流拍

def resolve_shooting():
    due = q("SELECT * FROM drama_roles WHERE status='shooting' AND shoot_end_ts <= ?", (now_ts(),))
    for role in due:
        winner = q("SELECT * FROM players WHERE id=?", (role['winner_player_id'],), one=True)
        drama = q("SELECT * FROM dramas WHERE id=?", (role['drama_id'],), one=True)
        if not winner or not drama:
            run("UPDATE drama_roles SET status='aired' WHERE id=?", (role['id'],))
            continue
        talents = json.loads(winner['talents'] or '{}')
        talent_val = talents.get(role['requirement_talent'], 50)
        match_val = talent_val + acting_challenge_bonus(role['id'], talent_val)
        match_val += health_performance_malus(winner['health'], winner['career_state'])
        success = random.randint(1, 100) <= clamp(match_val, 20, 90)
        rating_score = compute_rating_score(winner['popularity'], drama['budget_tier'], match_val)
        run("UPDATE drama_roles SET rating_score=? WHERE id=?", (rating_score, role['id']))
        cash, pop = role['reward_cash'], role['reward_popularity']
        if rating_score >= 80:
            rating_tag = "全网追更爆款,"
        elif rating_score < 40:
            rating_tag = "扑得悄无声息,"
        else:
            rating_tag = ""
        if success:
            run("UPDATE players SET cash=cash+?, popularity=popularity+? WHERE id=?", (cash, pop, winner['id']))
            content = f"{drama['title']}杀青了,{rating_tag}饰演{role['role_name']}这段经历很难忘,谢谢大家的期待"
            outcome, heat = 'success', 35
        else:
            scandal = random.randint(3, 10)
            run("UPDATE players SET cash=cash+?, popularity=popularity+?, scandal_value=scandal_value+? WHERE id=?",
                (cash // 2, pop // 3, scandal, winner['id']))
            content = f"{drama['title']}拍摄结束了,{rating_tag}这次的{role['role_name']}留了不少遗憾"
            outcome, heat = 'fail', 20
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,editable_until_ts,created_ts) "
            "VALUES (?,?,?,?,?,?,?)",
            (winner['id'], 'drama_wrap', content, outcome, heat, now_ts() + POST_EDIT_WINDOW_SECONDS, now_ts()))
        get_db().commit()
        post_id = cur.lastrowid
        if success:
            generate_comments(post_id, winner['id'], fan_w=5, hater_w=1, passerby_w=2)
        else:
            generate_comments(post_id, winner['id'], fan_w=2, hater_w=3, passerby_w=2)
        run("UPDATE drama_roles SET status='aired' WHERE id=?", (role['id'],))

# ── 代言/品牌合作(分层门槛,大牌需要代言信誉,塌房会被解约) ─────────────────────────

BRAND_TEMPLATES = [
    # 小众(奶茶/文具,D档门槛,人气0就能接)
    {"name": "蜜雪冰城",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "喜茶",       "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "奈雪的茶",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "CoCo都可",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "一点点",     "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "茶百道",     "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "古茗",       "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "沪上阿姨",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "晨光文具",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "真彩文具",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "农夫山泉",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "康师傅",     "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "统一",       "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "旺旺",       "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "良品铺子",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "三只松鼠",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "蒙牛",       "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "伊利",       "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "优衣库",     "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "ZARA",       "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "无印良品",   "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "GAP",        "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    {"name": "H&M",        "tier": "niche", "min_tier": "D", "max_scandal": 999, "min_reputation": 0,
     "cash": (50, 150), "reputation": (3, 6), "duration": 3 * 3600},
    # 二线/中奢(美妆/运动/数码/中端手表,B-/B档门槛)
    {"name": "花西子",     "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "完美日记",   "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "兰蔻",       "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "雅诗兰黛",   "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "耐克",       "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "阿迪达斯",   "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "安踏",       "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "李宁",       "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "华为",       "tier": "mid", "min_tier": "B",  "max_scandal": 40, "min_reputation": 15,
     "cash": (500, 900), "reputation": (10, 18), "duration": 8 * 3600},
    {"name": "小米",       "tier": "mid", "min_tier": "B",  "max_scandal": 40, "min_reputation": 15,
     "cash": (500, 900), "reputation": (10, 18), "duration": 8 * 3600},
    {"name": "玉兰油",     "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "欧莱雅",     "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "资生堂",     "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "珀莱雅",     "tier": "mid", "min_tier": "B-", "max_scandal": 50, "min_reputation": 10,
     "cash": (300, 600), "reputation": (8, 15), "duration": 6 * 3600},
    {"name": "天梭",       "tier": "mid", "min_tier": "B",  "max_scandal": 40, "min_reputation": 15,
     "cash": (500, 900), "reputation": (10, 18), "duration": 8 * 3600},
    {"name": "卡西欧",     "tier": "mid", "min_tier": "B",  "max_scandal": 40, "min_reputation": 15,
     "cash": (500, 900), "reputation": (10, 18), "duration": 8 * 3600},
    {"name": "斯沃琪",     "tier": "mid", "min_tier": "B",  "max_scandal": 40, "min_reputation": 15,
     "cash": (500, 900), "reputation": (10, 18), "duration": 8 * 3600},
    {"name": "精工",       "tier": "mid", "min_tier": "B",  "max_scandal": 40, "min_reputation": 15,
     "cash": (500, 900), "reputation": (10, 18), "duration": 8 * 3600},
    # 大牌/高奢(箱包时装/腕表珠宝,A档门槛)
    {"name": "路易威登",   "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "香奈儿",     "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "迪奥",       "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "爱马仕",     "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "古驰",       "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "普拉达",     "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "卡地亚",     "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "宝格丽",     "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "欧米茄",     "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "劳力士",     "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "百达翡丽",   "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "爱彼",       "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "江诗丹顿",   "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
    {"name": "积家",       "tier": "top", "min_tier": "A", "max_scandal": 20, "min_reputation": 40,
     "cash": (2000, 4000), "reputation": (20, 35), "duration": 12 * 3600},
]

MAX_CONCURRENT_BRANDS = 3
BRAND_APPLY_WINDOW = 3600

def maybe_open_brand():
    open_count = q("SELECT COUNT(*) c FROM brands WHERE status='open'", one=True)['c']
    if open_count >= MAX_CONCURRENT_BRANDS:
        return
    active_names = {r['brand_name'] for r in q("SELECT brand_name FROM brands WHERE status IN ('open','signed')")}
    candidates = [t for t in BRAND_TEMPLATES if t['name'] not in active_names] or BRAND_TEMPLATES
    t = random.choice(candidates)
    now = now_ts()
    run("""INSERT INTO brands (brand_name,tier,min_tier,max_scandal,min_reputation,reward_cash,
           reward_reputation,duration_seconds,apply_close_ts,status,created_ts)
           VALUES (?,?,?,?,?,?,?,?,?,'open',?)""",
        (t['name'], t['tier'], t['min_tier'], t['max_scandal'], t['min_reputation'],
         random.randint(*t['cash']), random.randint(*t['reputation']), t['duration'],
         now + BRAND_APPLY_WINDOW, now))

def eligible_for_brand(player, brand):
    if player['career_state'] == 'blackout':
        return False, '雪藏期接不了代言'
    if not meets_tier(player['popularity'], brand['min_tier']):
        return False, '咖位不够'
    if player['scandal_value'] > brand['max_scandal']:
        return False, '黑值太高,品牌方不敢用'
    if player['endorsement_reputation'] < brand['min_reputation']:
        return False, '代言信誉不够,接不到这个牌子'
    return True, ''

def apply_for_brand(player_id, brand_id):
    if q("SELECT id FROM brand_applications WHERE brand_id=? AND player_id=?",
         (brand_id, player_id), one=True):
        return False, '已经报过名了'
    brand = q("SELECT * FROM brands WHERE id=?", (brand_id,), one=True)
    if not brand or brand['status'] != 'open':
        return False, '这个品牌已经不在招募阶段'
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    ok, reason = eligible_for_brand(player, brand)
    if not ok:
        return False, reason
    if not try_spend_energy(player_id, 'brand_apply'):
        return False, '体力不够了'
    score = player['popularity'] + random.randint(-10, 10) + player['awards_won'] * 3
    run("INSERT INTO brand_applications (brand_id,player_id,match_score,created_ts) VALUES (?,?,?,?)",
        (brand_id, player_id, score, now_ts()))
    return True, '已提交合作意向'

def resolve_brand_casting():
    due = q("SELECT * FROM brands WHERE status='open' AND apply_close_ts <= ?", (now_ts(),))
    for brand in due:
        apps = list(q("SELECT * FROM brand_applications WHERE brand_id=? ORDER BY match_score DESC", (brand['id'],)))
        winner_id = apps[0]['player_id'] if apps else None
        if not winner_id:
            candidates = q("SELECT * FROM players WHERE is_npc=1")
            eligible_ids = [c['id'] for c in candidates if eligible_for_brand(c, brand)[0]]
            if eligible_ids:
                winner_id = random.choice(eligible_ids)
        if winner_id:
            run("UPDATE brands SET status='signed', signed_player_id=?, contract_end_ts=? WHERE id=?",
                (winner_id, now_ts() + brand['duration_seconds'], brand['id']))
        else:
            run("UPDATE brands SET status='completed' WHERE id=?", (brand['id'],))

def check_brand_contracts():
    signed = q("SELECT * FROM brands WHERE status='signed'")
    for brand in signed:
        player = q("SELECT * FROM players WHERE id=?", (brand['signed_player_id'],), one=True)
        if not player:
            run("UPDATE brands SET status='completed' WHERE id=?", (brand['id'],))
            continue
        if player['career_state'] == 'blackout':
            penalty = int(brand['reward_cash'] * 0.2)
            run("UPDATE players SET cash=MAX(0,cash-?), scandal_value=scandal_value+? WHERE id=?",
                (penalty, 5, player['id']))
            content = f"{player['stage_name']}塌房,{brand['brand_name']}官宣解约并发布违约声明"
            cur = get_db().execute(
                "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
                (player['id'], 'brand_terminated', content, 'terminated', 30, now_ts()))
            get_db().commit()
            post_id = cur.lastrowid
            generate_comments(post_id, player['id'], fan_w=1, hater_w=5, passerby_w=2)
            run("UPDATE brands SET status='completed' WHERE id=?", (brand['id'],))
        elif now_ts() >= brand['contract_end_ts']:
            run("UPDATE players SET cash=cash+?, popularity=popularity+? WHERE id=?",
                (brand['reward_cash'], max(1, brand['reward_cash'] // 100), player['id']))
            run("UPDATE players SET endorsement_reputation=MIN(100,endorsement_reputation+?) WHERE id=?",
                (brand['reward_reputation'], player['id']))
            if brand['tier'] == 'top':
                content = f"{player['stage_name']}拿下{brand['brand_name']}代言人,官宣海报好评如潮"
                heat, fan_w, hater_w = 45, 5, 1
            else:
                content = f"{player['stage_name']}和{brand['brand_name']}的代言合作圆满结束"
                heat, fan_w, hater_w = 15, 3, 1
            cur = get_db().execute(
                "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
                (player['id'], 'brand_complete', content, 'success', heat, now_ts()))
            get_db().commit()
            post_id = cur.lastrowid
            generate_comments(post_id, player['id'], fan_w=fan_w, hater_w=hater_w, passerby_w=2)
            launch_product_sales(player, post_id, f"{brand['brand_name']}联名款")
            run("UPDATE brands SET status='completed' WHERE id=?", (brand['id'],))

# ── 品牌代言人(全局限量,支持直接挑战顶替现任) ──────────────────────────────────

AMBASSADOR_COST = 500

def ambassador_match_score(player):
    shoot_count = q("SELECT COUNT(*) c FROM posts WHERE player_id=? AND post_type IN ('commercial_shoot','magazine')",
                     (player['id'],), one=True)['c']
    return player['endorsement_reputation'] * 2 + player['popularity'] + shoot_count * 3 + player['awards_won'] * 3

def eligible_for_ambassador(player, ambassador):
    if player['career_state'] == 'blackout':
        return False, '雪藏期接不了代言人'
    if player['career_state'] == 'sick':
        return False, '生病了,先把身体养好'
    if not meets_tier(player['popularity'], ambassador['min_tier']):
        return False, '咖位不够'
    if player['scandal_value'] > ambassador['max_scandal']:
        return False, '黑值太高,品牌方不敢用'
    if player['endorsement_reputation'] < ambassador['min_reputation']:
        return False, '代言信誉不够,接不到这个牌子'
    return True, ''

def apply_for_ambassador(player_id, ambassador_id):
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    ambassador = q("SELECT * FROM brand_ambassadors WHERE id=?", (ambassador_id,), one=True)
    if not player or not ambassador:
        return False, '目标无效'
    ok, reason = eligible_for_ambassador(player, ambassador)
    if not ok:
        return False, reason
    if player['cash'] < AMBASSADOR_COST:
        return False, '资金不足'
    if not try_spend_energy(player_id, 'ambassador_apply'):
        return False, '体力不够了'

    if not ambassador['current_player_id']:
        run("UPDATE players SET cash=cash-?, popularity=popularity+?, "
            "endorsement_reputation=MIN(100,endorsement_reputation+?) WHERE id=?",
            (AMBASSADOR_COST, random.randint(10, 20), random.randint(5, 10), player_id))
        run("UPDATE brand_ambassadors SET current_player_id=?, held_since_ts=? WHERE id=?",
            (player_id, now_ts(), ambassador['id']))
        content = f"{player['stage_name']}正式成为{ambassador['brand_name']}代言人"
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (player_id, 'ambassador_won', content, 'success', 45, now_ts()))
        get_db().commit()
        generate_comments(cur.lastrowid, player_id, fan_w=5, hater_w=1, passerby_w=2)
        return True, f"恭喜,正式拿下{ambassador['brand_name']}代言人"

    holder_id = ambassador['current_player_id']
    if holder_id == player_id:
        return False, '你已经是这个品牌的代言人了'
    holder = q("SELECT * FROM players WHERE id=?", (holder_id,), one=True)
    run("UPDATE players SET cash=cash-? WHERE id=?", (AMBASSADOR_COST, player_id))
    challenger_score = ambassador_match_score(player)
    holder_score = ambassador_match_score(holder) if holder else 0
    if challenger_score <= holder_score:
        return False, '守擂成功,这次没能顶替'

    if holder:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(3, 8), holder_id))
        lost_content = f"{holder['stage_name']}卸任{ambassador['brand_name']}代言人"
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (holder_id, 'ambassador_lost', lost_content, 'lost', 30, now_ts()))
        get_db().commit()
        generate_comments(cur.lastrowid, holder_id, fan_w=1, hater_w=4, passerby_w=2)

    run("UPDATE players SET popularity=popularity+?, endorsement_reputation=MIN(100,endorsement_reputation+?) WHERE id=?",
        (random.randint(10, 20), random.randint(5, 10), player_id))
    run("UPDATE brand_ambassadors SET current_player_id=?, held_since_ts=? WHERE id=?",
        (player_id, now_ts(), ambassador['id']))
    won_content = f"{player['stage_name']}挑战成功,拿下{ambassador['brand_name']}代言人"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player_id, 'ambassador_won', won_content, 'success', 45, now_ts()))
    get_db().commit()
    generate_comments(cur.lastrowid, player_id, fan_w=5, hater_w=1, passerby_w=2)
    return True, f"挑战成功,顶替拿下{ambassador['brand_name']}代言人"

def check_ambassador_status():
    holders = q("SELECT * FROM brand_ambassadors WHERE current_player_id IS NOT NULL")
    for a in holders:
        player = q("SELECT * FROM players WHERE id=?", (a['current_player_id'],), one=True)
        if not player or player['scandal_value'] > a['max_scandal']:
            run("UPDATE brand_ambassadors SET current_player_id=NULL WHERE id=?", (a['id'],))
            if player:
                content = f"{player['stage_name']}黑值超标,{a['brand_name']}宣布解约代言人身份"
                cur = get_db().execute(
                    "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
                    (player['id'], 'ambassador_lost', content, 'terminated', 30, now_ts()))
                get_db().commit()
                generate_comments(cur.lastrowid, player['id'], fan_w=1, hater_w=5, passerby_w=2)

# ── 歌手线:发新歌 / 演唱会(跨界发片伤路人缘但能固死忠粉) ───────────────────────────

SONG_COST = 200
SONG_TITLES = ["星河", "无人知晓", "孤勇者2.0", "夜曲", "如愿", "少年游", "浮光", "归途", "破晓", "余温"]

def release_song(player):
    if player['career_state'] == 'blackout':
        return None, '雪藏期不能发歌'
    if player['cash'] < SONG_COST:
        return None, '资金不足,发不起新歌'
    if not try_spend_energy(player['id'], 'release_song'):
        return None, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (SONG_COST, player['id']))
    talents = json.loads(player['talents'] or '{}')
    career_lines = json.loads(player['career_lines'] or '[]')
    is_crossover = 'singer' not in career_lines
    skill = (talents.get('唱功', 50) + talents.get('创作力', 50)) / 2
    if is_crossover:
        skill *= 0.6  # 业余唱功打折,这是"任何职业线都能发,但非歌手线容易被路人群嘲"的核心判定
    critic_score = clamp(int(skill + random.randint(-10, 10)), 0, 100)
    title = random.choice(SONG_TITLES)

    if critic_score >= 70:
        run("UPDATE players SET popularity=popularity+? WHERE id=?", (random.randint(8, 18), player['id']))
        distribute_fan_gain(player['id'], random.randint(20, 60))
        outcome, heat = 'hit', 30
    elif critic_score >= 45:
        run("UPDATE players SET popularity=popularity+? WHERE id=?", (random.randint(2, 6), player['id']))
        outcome, heat = 'ok', 15
    else:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(5, 15), player['id']))
        outcome, heat = 'flop', 22

    # 死忠粉忠诚度看投入/诚意,不看真实水平——业余发片也能固粉,这条和路人评价完全独立
    loyalty_gain = random.randint(3, 10) + (5 if is_crossover else 0)
    run("UPDATE players SET core_fan_loyalty=core_fan_loyalty+? WHERE id=?", (loyalty_gain, player['id']))

    content = f"发布新歌《{title}》" + ("(跨界挑战唱作)" if is_crossover else "")
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player['id'], 'song_release', content, outcome, heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    if outcome == 'hit':
        generate_comments(post_id, player['id'], fan_w=5, hater_w=1, passerby_w=2)
    elif outcome == 'flop':
        generate_comments(post_id, player['id'], fan_w=2, hater_w=4, passerby_w=2)
    else:
        generate_comments(post_id, player['id'], fan_w=3, hater_w=2, passerby_w=2)
    run("INSERT INTO songs (player_id,title,is_crossover,invested,created_ts) VALUES (?,?,?,?,?)",
        (player['id'], title, int(is_crossover), SONG_COST, now_ts()))
    return outcome, None

# ── 商业拍摄 / 杂志专访(轻量即时动作,次数计入品牌代言人匹配分) ──────────────────────

COMMERCIAL_SHOOT_COST = 100
MAGAZINE_COST = 100

def do_commercial_shoot(player):
    if player['career_state'] == 'blackout':
        return None, '雪藏期接不了商业拍摄'
    if player['career_state'] == 'sick':
        return None, '生病了,先把身体养好'
    if player['cash'] < COMMERCIAL_SHOOT_COST:
        return None, '资金不足'
    if not try_spend_energy(player['id'], 'commercial_shoot'):
        return None, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (COMMERCIAL_SHOOT_COST, player['id']))
    talents = json.loads(player['talents'] or '{}')
    skill = (talents.get('颜值', 50) + talents.get('镜头感', 50)) / 2
    score = clamp(int(skill + random.randint(-10, 10)), 0, 100)

    if score >= 70:
        run("UPDATE players SET cash=cash+?, popularity=popularity+? WHERE id=?",
            (random.randint(200, 400), random.randint(4, 10), player['id']))
        outcome, heat = 'hit', 20
    elif score >= 45:
        run("UPDATE players SET cash=cash+? WHERE id=?", (random.randint(80, 200), player['id']))
        outcome, heat = 'ok', 12
    else:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(2, 8), player['id']))
        outcome, heat = 'flop', 15

    content = "拍摄了一组商业硬照,片场氛围很不错"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player['id'], 'commercial_shoot', content, outcome, heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    if outcome == 'hit':
        generate_comments(post_id, player['id'], fan_w=5, hater_w=1, passerby_w=2)
    elif outcome == 'flop':
        generate_comments(post_id, player['id'], fan_w=2, hater_w=4, passerby_w=2)
    else:
        generate_comments(post_id, player['id'], fan_w=3, hater_w=2, passerby_w=2)
    return outcome, None

def do_magazine(player):
    if player['career_state'] == 'blackout':
        return None, '雪藏期上不了杂志'
    if player['career_state'] == 'sick':
        return None, '生病了,先把身体养好'
    if player['cash'] < MAGAZINE_COST:
        return None, '资金不足'
    if not try_spend_energy(player['id'], 'magazine'):
        return None, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (MAGAZINE_COST, player['id']))
    talents = json.loads(player['talents'] or '{}')
    skill = (talents.get('演技', 50) + talents.get('创作力', 50)) / 2
    score = clamp(int(skill + random.randint(-10, 10)), 0, 100)

    if score >= 70:
        run("UPDATE players SET cash=cash+?, popularity=popularity+? WHERE id=?",
            (random.randint(200, 400), random.randint(4, 10), player['id']))
        outcome, heat = 'hit', 20
    elif score >= 45:
        run("UPDATE players SET cash=cash+? WHERE id=?", (random.randint(80, 200), player['id']))
        outcome, heat = 'ok', 12
    else:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(2, 8), player['id']))
        outcome, heat = 'flop', 15

    content = "接受了一次杂志专访,聊了聊这段时间的心路历程"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player['id'], 'magazine', content, outcome, heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    if outcome == 'hit':
        generate_comments(post_id, player['id'], fan_w=5, hater_w=1, passerby_w=2)
    elif outcome == 'flop':
        generate_comments(post_id, player['id'], fan_w=2, hater_w=4, passerby_w=2)
    else:
        generate_comments(post_id, player['id'], fan_w=3, hater_w=2, passerby_w=2)
    if outcome != 'flop':
        launch_product_sales(player, post_id, "本期杂志")
    return outcome, None

CONCERT_POPULARITY_THRESHOLD = 80
CONCERT_COST = 500

def hold_concert(player, choices=None):
    if player['career_state'] == 'blackout':
        return None, '雪藏期办不了演唱会'
    if player['career_state'] == 'sick':
        return None, '生病了,先把身体养好'
    if player['popularity'] < CONCERT_POPULARITY_THRESHOLD:
        return None, '人气不够,办不了演唱会'
    if player['cash'] < CONCERT_COST:
        return None, '资金不足,办不起演唱会'
    if not try_spend_energy(player['id'], 'concert'):
        return None, '体力不够了'
    talents = json.loads(player['talents'] or '{}')
    run("UPDATE players SET cash=cash-? WHERE id=?", (CONCERT_COST, player['id']))
    stage_skill = (talents.get('唱功', 50) + talents.get('抗压力', 50)) / 2
    stage_skill += safe_risky_bonus(choices or [], stage_skill)
    incident = random.randint(1, 100) > clamp(stage_skill, 20, 90)
    if incident:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(5, 15), player['id']))
        content, outcome, heat, fan_w, hater_w = "演唱会现场出了舞台事故,气氛一度尴尬", 'incident', 35, 2, 4
    else:
        cash_gain, pop_gain = random.randint(800, 2000), random.randint(15, 35)
        run("UPDATE players SET cash=cash+?, popularity=popularity+? WHERE id=?",
            (cash_gain, pop_gain, player['id']))
        distribute_fan_gain(player['id'], random.randint(50, 150))
        content, outcome, heat, fan_w, hater_w = "个人演唱会圆满落幕,全场大合唱", 'success', 40, 6, 1
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player['id'], 'concert', content, outcome, heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    generate_comments(post_id, player['id'], fan_w=fan_w, hater_w=hater_w, passerby_w=2)
    run("INSERT INTO concerts (player_id,invested,incident,held_ts) VALUES (?,?,?,?)",
        (player['id'], CONCERT_COST, outcome if incident else '', now_ts()))
    return outcome, None

# ── 奢侈品抽卡(到一定咖位才能玩,抽到稀有款会自动晒图,晒过头容易被吐槽凡尔赛) ──────────

LUXURY_GACHA_TIER_REQUIREMENT = 'B'
LUXURY_GACHA_COST = 300
VERSAILLES_BACKFIRE_CHANCE = 30  # 抽到限量款还晒图,有概率被吐槽凡尔赛过头

LUXURY_ITEM_POOL = {
    'common': {
        'weight': 60, 'pop': (0, 1),
        'items': ['定制香薰蜡烛', '设计师联名丝巾', '限定色号口红', '小众品牌耳环', '定制款香水'],
    },
    'premium': {
        'weight': 25, 'pop': (2, 5),
        'items': ['Gucci 腰带', 'LV 钱包', 'Dior 口红礼盒', 'Burberry 风衣', 'Tiffany 项链'],
    },
    'luxury': {
        'weight': 12, 'pop': (8, 15),
        'items': ['爱马仕丝巾', '香奈儿经典手袋', '卡地亚手镯', '劳力士手表', '宝格丽项链'],
    },
    'limited': {
        'weight': 3, 'pop': (20, 35),
        'items': ['爱马仕喜马拉雅铂金包(全球限量)', '百达翡丽限量腕表', '梵克雅宝高定珠宝', '香奈儿高定礼服'],
    },
}
LUXURY_RARITY_LABELS = {'common': '普通', 'premium': '精品', 'luxury': '奢侈品', 'limited': '限量'}

def draw_luxury_item(player):
    if not meets_tier(player['popularity'], LUXURY_GACHA_TIER_REQUIREMENT):
        return None, f'咖位要到 {LUXURY_GACHA_TIER_REQUIREMENT} 级以上才能进这个圈子'
    if player['career_state'] == 'blackout':
        return None, '雪藏期不适合炫富'
    if player['cash'] < LUXURY_GACHA_COST:
        return None, '资金不足'
    if not try_spend_energy(player['id'], 'luxury_gacha'):
        return None, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (LUXURY_GACHA_COST, player['id']))

    rarities = list(LUXURY_ITEM_POOL.keys())
    weights = [LUXURY_ITEM_POOL[r]['weight'] for r in rarities]
    rarity = random.choices(rarities, weights=weights)[0]
    item_name = random.choice(LUXURY_ITEM_POOL[rarity]['items'])
    pop_gain = random.randint(*LUXURY_ITEM_POOL[rarity]['pop'])

    backfire = rarity == 'limited' and random.randint(1, 100) <= VERSAILLES_BACKFIRE_CHANCE
    if backfire:
        pop_gain = max(0, pop_gain // 3)
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?",
            (random.randint(5, 12), player['id']))
    run("UPDATE players SET popularity=popularity+? WHERE id=?", (pop_gain, player['id']))
    run("INSERT INTO luxury_items (player_id,item_name,rarity,created_ts) VALUES (?,?,?,?)",
        (player['id'], item_name, rarity, now_ts()))

    if rarity in ('luxury', 'limited'):
        if backfire:
            content = f"抽到了{item_name},晒图被吐槽凡尔赛过头了"
            outcome, heat, fan_w, hater_w = 'versailles', 26, 2, 4
        else:
            content = f"抽到了{item_name},开箱晒图"
            outcome, heat, fan_w, hater_w = 'flex', 24, 5, 1
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (player['id'], 'luxury_flex', content, outcome, heat, now_ts()))
        get_db().commit()
        post_id = cur.lastrowid
        generate_comments(post_id, player['id'], fan_w=fan_w, hater_w=hater_w, passerby_w=2)

    return {'item_name': item_name, 'rarity': rarity, 'backfire': backfire}, None

# ── 明星生活方式消费(买房/买车,固定目录选购,不是抽卡) ──────────────────────────────

LIFESTYLE_CATALOG = {
    'apartment':  {'name': '市区公寓',   'category': '房产', 'price': 3000,  'pop': (5, 10)},
    'riverview':  {'name': '江景大平层', 'category': '房产', 'price': 8000,  'pop': (15, 25)},
    'villa':      {'name': '独栋别墅',   'category': '房产', 'price': 20000, 'pop': (30, 50)},
    'commuter':   {'name': '代步车',     'category': '座驾', 'price': 2000,  'pop': (3, 8)},
    'sedan':      {'name': '豪华轿车',   'category': '座驾', 'price': 6000,  'pop': (10, 20)},
    'sportscar':  {'name': '跑车',       'category': '座驾', 'price': 15000, 'pop': (25, 40)},
}

def buy_lifestyle_asset(player_id, item_key):
    item = LIFESTYLE_CATALOG.get(item_key)
    if not item:
        return False, '这件商品不存在'
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if not player:
        return False, '找不到玩家'
    if player['cash'] < item['price']:
        return False, '资金不足'
    run("UPDATE players SET cash=cash-? WHERE id=?", (item['price'], player_id))
    pop_gain = random.randint(*item['pop'])
    run("UPDATE players SET popularity=popularity+? WHERE id=?", (pop_gain, player_id))
    run("INSERT INTO lifestyle_assets (player_id,item_name,category,price,created_ts) VALUES (?,?,?,?,?)",
        (player_id, item['name'], item['category'], item['price'], now_ts()))

    content = f"低调晒了一下新买的{item['name']}"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player_id, 'lifestyle_flex', content, 'flex', 22, now_ts()))
    get_db().commit()
    generate_comments(cur.lastrowid, player_id, fan_w=5, hater_w=1, passerby_w=2)
    return True, f"新入手了{item['name']}"

# ── 颁奖典礼(评委权重 vs 大众投票分开算,冲奖/黑幕贿赂/典礼事故) ────────────────────
# 一套有等级的颁奖日历:小奖攒资历,一路冲到国内权威奖、电影节,最后冲奥斯卡。

AWARD_SHOWS = {
    'star': {
        'name': '星光盛典', 'tier': 'minor', 'cadence_days': 1,
        'min_tier': None, 'min_awards': 0, 'require_film': False, 'min_rating': 0,
        'categories': [
            {"name": "最佳新人", "judge_type": "critic", "career_line": "", "gender": "any", "talent": "演技"},
            {"name": "潜力艺人", "judge_type": "popular", "career_line": "", "gender": "any", "talent": ""},
        ],
    },
    'fan_choice': {
        'name': '观众喜爱奖', 'tier': 'minor', 'cadence_days': 1,
        'min_tier': None, 'min_awards': 0, 'require_film': False, 'min_rating': 0,
        'categories': [
            {"name": "观众最喜爱男艺人", "judge_type": "popular", "career_line": "", "gender": "male", "talent": ""},
            {"name": "观众最喜爱女艺人", "judge_type": "popular", "career_line": "", "gender": "female", "talent": ""},
        ],
    },
    'weibo_night': {
        'name': '微博之夜', 'tier': 'popularity', 'cadence_days': 2,
        'min_tier': None, 'min_awards': 0, 'require_film': False, 'min_rating': None,
        'categories': [
            {"name": "微博年度影响力人物", "judge_type": "popular", "career_line": "", "gender": "any", "talent": ""},
            {"name": "微博人气偶像", "judge_type": "popular", "career_line": "idol", "gender": "any", "talent": ""},
        ],
    },
    'baihua': {
        'name': '百花奖', 'tier': 'major', 'cadence_days': 3,
        'min_tier': 'B+', 'min_awards': 0, 'require_film': False, 'min_rating': 55,
        'categories': [
            {"name": "最佳男主角", "judge_type": "critic", "career_line": "actor", "gender": "male", "talent": "演技"},
            {"name": "最佳女主角", "judge_type": "critic", "career_line": "actor", "gender": "female", "talent": "演技"},
        ],
    },
    'golden_rooster_festival': {
        'name': '金鸡国际电影节', 'tier': 'festival', 'cadence_days': 5,
        'min_tier': 'A', 'min_awards': 0, 'require_film': True, 'min_rating': 70,
        'categories': [
            {"name": "最佳电影男主角", "judge_type": "critic", "career_line": "actor", "gender": "male", "talent": "演技"},
            {"name": "最佳电影女主角", "judge_type": "critic", "career_line": "actor", "gender": "female", "talent": "演技"},
        ],
    },
    'oscar': {
        'name': '奥斯卡', 'tier': 'top', 'cadence_days': 7,
        'min_tier': 'S', 'min_awards': 3, 'require_film': True, 'min_rating': 85,
        'categories': [
            {"name": "奥斯卡最佳男主角", "judge_type": "critic", "career_line": "actor", "gender": "male", "talent": "演技"},
            {"name": "奥斯卡最佳女主角", "judge_type": "critic", "career_line": "actor", "gender": "female", "talent": "演技"},
        ],
    },
}
AWARD_SHOW_REWARDS = {
    'minor':      {'pop': (20, 40),   'cash': (300, 800)},
    'popularity': {'pop': (25, 50),   'cash': (400, 1000)},
    'major':      {'pop': (40, 80),   'cash': (1000, 2000)},
    'festival':   {'pop': (70, 120),  'cash': (2000, 4000)},
    'top':        {'pop': (100, 180), 'cash': (5000, 10000)},
}
AWARD_TIER_LABELS = {
    'minor': '小奖', 'popularity': '人气榜', 'major': '国内权威',
    'festival': '电影节', 'top': '顶级',
}

AWARDS_CAMPAIGN_DURATION = 4 * 3600  # 冲奖期 4 小时
AWARDS_NOMINEE_COUNT = 5
CAMPAIGN_BOOST_COST = 150
BRIBE_COST = 200
JUDGE_WEIGHTS = {'critic': (0.7, 0.3), 'popular': (0.2, 0.8)}  # (评委权重, 大众投票权重)
CEREMONY_INCIDENT_BASE_CHANCE = 20

def has_film_credit(player_id):
    row = q("""SELECT 1 c FROM drama_roles r JOIN dramas d ON d.id = r.drama_id
              WHERE r.winner_player_id=? AND r.status='aired' AND d.format='film' LIMIT 1""",
            (player_id,), one=True)
    return row is not None

def best_qualifying_work(player_id, require_film, min_rating, since_ts):
    """过去一年杀青的作品里,挑 rating_score 最高的一条(一人只算一份工作,不会因为多部作品重复占坑)。"""
    sql = """SELECT r.* FROM drama_roles r JOIN dramas d ON d.id = r.drama_id
            WHERE r.winner_player_id=? AND r.status='aired' AND r.rating_score>=? AND r.created_ts>=?"""
    args = [player_id, min_rating, since_ts]
    if require_film:
        sql += " AND d.format='film'"
    rows = q(sql, tuple(args))
    return max(rows, key=lambda r: r['rating_score']) if rows else None

def maybe_open_award_shows():
    today = now_ts() // 86400
    for show_key, show in AWARD_SHOWS.items():
        if q("SELECT id FROM award_seasons WHERE show_key=? AND status='campaigning'", (show_key,), one=True):
            continue
        last_day = int(get_meta(f'last_award_{show_key}_day', -999))
        if today - last_day < show['cadence_days']:
            continue
        set_meta(f'last_award_{show_key}_day', today)
        _open_award_show(show_key, show)

def _open_award_show(show_key, show):
    now = now_ts()
    season_num = q("SELECT COUNT(*) c FROM award_seasons WHERE show_key=?", (show_key,), one=True)['c'] + 1
    db = get_db()
    cur = db.execute(
        "INSERT INTO award_seasons (season_name,nomination_start,campaign_end_ts,status,show_key,tier,created_ts) "
        "VALUES (?,?,?,?,?,?,?)",
        (f"第{season_num}届{show['name']}", now, now + AWARDS_CAMPAIGN_DURATION, 'campaigning',
         show_key, show['tier'], now))
    db.commit()
    season_id = cur.lastrowid

    candidates = list(q("SELECT * FROM players WHERE career_state != 'blackout'"))
    since_ts = now - MONTH_SECONDS * 12  # 过去一年
    for tpl in show['categories']:
        cat_cur = db.execute(
            "INSERT INTO award_categories (season_id,category_name,judge_type,career_line) VALUES (?,?,?,?)",
            (season_id, tpl['name'], tpl['judge_type'], tpl['career_line']))
        db.commit()
        category_id = cat_cur.lastrowid

        pool = []
        for c in candidates:
            if tpl['career_line']:
                lines = json.loads(c['career_lines'] or '[]')
                if tpl['career_line'] not in lines:
                    continue
            if tpl['gender'] != 'any' and c['gender'] != tpl['gender']:
                continue
            if show['min_tier'] and not meets_tier(c['popularity'], show['min_tier']):
                continue
            if c['awards_won'] < show['min_awards']:
                continue
            if show['require_film'] and not has_film_credit(c['id']):
                continue
            work_score = None
            if show['min_rating'] is not None:
                work = best_qualifying_work(c['id'], show['require_film'], show['min_rating'], since_ts)
                if not work:
                    continue  # 这一年没有够格的作品,压根进不了候选池
                work_score = work['rating_score']
            pool.append((c, work_score))

        if any(ws is not None for _, ws in pool):
            pool.sort(key=lambda cw: cw[1], reverse=True)
        elif tpl['talent']:
            pool.sort(key=lambda cw: json.loads(cw[0]['talents'] or '{}').get(tpl['talent'], 0), reverse=True)
        else:
            pool.sort(key=lambda cw: cw[0]['popularity'], reverse=True)

        for n, work_score in pool[:AWARDS_NOMINEE_COUNT]:
            talents = json.loads(n['talents'] or '{}')
            critic_score = work_score if work_score is not None else (
                talents.get(tpl['talent'], 50) if tpl['talent'] else n['popularity'] // 3)
            run("INSERT INTO award_nominees (category_id,player_id,critic_score,vote_score) VALUES (?,?,?,?)",
                (category_id, n['id'], critic_score, n['popularity']))

def campaign_boost(player_id, category_id):
    nominee = q("SELECT * FROM award_nominees WHERE category_id=? AND player_id=?",
                (category_id, player_id), one=True)
    if not nominee:
        return False, '你没有入围这个奖项'
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if player['cash'] < CAMPAIGN_BOOST_COST:
        return False, '资金不足'
    if not try_spend_energy(player_id, 'awards_campaign'):
        return False, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (CAMPAIGN_BOOST_COST, player_id))
    boost = random.randint(20, 40)
    run("UPDATE award_nominees SET vote_score=vote_score+? WHERE category_id=? AND player_id=?",
        (boost, category_id, player_id))
    today_start = now_ts() - 24 * 3600
    boosts_today = q("""SELECT COUNT(*) c FROM boosts WHERE player_id=? AND boost_type='awards_campaign'
                        AND created_ts>?""", (player_id, today_start), one=True)['c']
    run("INSERT INTO boosts (player_id,boost_type,amount,created_ts) VALUES (?,?,?,?)",
        (player_id, 'awards_campaign', boost, now_ts()))
    if boosts_today >= 3 and random.randint(1, 100) <= 25:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(5, 12), player_id))
        return True, '冲奖成功,但刷得太猛被扣了"刷奖"的帽子,黑值涨了'
    return True, '冲奖成功'

def bribe_judge(player_id, category_id):
    category = q("SELECT * FROM award_categories WHERE id=?", (category_id,), one=True)
    if not category or category['judge_type'] != 'critic':
        return False, '这个奖项没有评审团,买通没用'
    nominee = q("SELECT * FROM award_nominees WHERE category_id=? AND player_id=?",
                (category_id, player_id), one=True)
    if not nominee:
        return False, '你没有入围这个奖项'
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if player['cash'] < BRIBE_COST:
        return False, '资金不足'
    if not try_spend_energy(player_id, 'awards_campaign'):
        return False, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (BRIBE_COST, player_id))
    prior_bribes = q("SELECT COUNT(*) c FROM judge_bribes WHERE player_id=? AND category_id=?",
                      (player_id, category_id), one=True)['c']
    expose_chance = 20 + prior_bribes * 15  # 次数越多越容易露馅
    exposed = random.randint(1, 100) <= expose_chance
    run("INSERT INTO judge_bribes (category_id,player_id,invested,exposed,created_ts) VALUES (?,?,?,?,?)",
        (category_id, player_id, BRIBE_COST, int(exposed), now_ts()))
    if exposed:
        run("UPDATE award_nominees SET bribe_exposed=1 WHERE category_id=? AND player_id=?",
            (category_id, player_id))
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(25, 40), player_id))
        content = f"{player['stage_name']}评奖黑幕实锤,买通评委被扒出,已丧失本届提名资格"
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (player_id, 'bribe_exposed', content, 'exposed', 55, now_ts()))
        get_db().commit()
        post_id = cur.lastrowid
        generate_comments(post_id, player_id, fan_w=1, hater_w=6, passerby_w=3)
        return False, '买通评委被曝光了,评奖黑幕实锤,这个奖项直接没戏了'
    run("UPDATE award_nominees SET critic_score=critic_score+? WHERE category_id=? AND player_id=?",
        (random.randint(15, 25), category_id, player_id))
    return True, '悄悄打点了一下评委'

def resolve_award_season():
    due_seasons = q("SELECT * FROM award_seasons WHERE status='campaigning' AND campaign_end_ts <= ?",
                    (now_ts(),))
    for season in due_seasons:
        reward = AWARD_SHOW_REWARDS.get(season['tier'], AWARD_SHOW_REWARDS['minor'])
        categories = q("SELECT * FROM award_categories WHERE season_id=?", (season['id'],))
        for cat in categories:
            cw, vw = JUDGE_WEIGHTS[cat['judge_type']]
            nominees = [dict(n) for n in q(
                "SELECT * FROM award_nominees WHERE category_id=? AND bribe_exposed=0", (cat['id'],))]
            if not nominees:
                continue
            for n in nominees:
                n['final_score'] = n['critic_score'] * cw + n['vote_score'] * vw
            nominees.sort(key=lambda n: n['final_score'], reverse=True)
            winner = nominees[0]
            run("UPDATE award_nominees SET won=1 WHERE category_id=? AND player_id=?",
                (cat['id'], winner['player_id']))
            player = q("SELECT * FROM players WHERE id=?", (winner['player_id'],), one=True)
            if not player:
                continue
            talents = json.loads(player['talents'] or '{}')
            incident_chance = max(5, CEREMONY_INCIDENT_BASE_CHANCE - talents.get('抗压力', 50) // 5)
            incident = random.randint(1, 100) <= incident_chance
            run("UPDATE players SET popularity=popularity+?, cash=cash+?, awards_won=awards_won+1 WHERE id=?",
                (random.randint(*reward['pop']), random.randint(*reward['cash']), player['id']))
            if incident:
                run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(5, 15), player['id']))
                content = f"{player['stage_name']}拿下{season['season_name']}{cat['category_name']},不过颁奖夜现场出了点小意外"
                outcome, fan_w, hater_w = 'incident', 3, 3
            else:
                content = f"{player['stage_name']}拿下{season['season_name']}{cat['category_name']},全场起立鼓掌"
                outcome, fan_w, hater_w = 'success', 6, 1
            cur = get_db().execute(
                "INSERT INTO posts (player_id,post_type,content,outcome,heat,editable_until_ts,created_ts) "
                "VALUES (?,?,?,?,?,?,?)",
                (player['id'], 'award_won', content, outcome, 50, now_ts() + POST_EDIT_WINDOW_SECONDS, now_ts()))
            get_db().commit()
            post_id = cur.lastrowid
            generate_comments(post_id, player['id'], fan_w=fan_w, hater_w=hater_w, passerby_w=3)
            if season['show_key'] == 'oscar':
                unlock_milestone(player['id'], 'oscar_winner')
        run("UPDATE award_seasons SET status='announced' WHERE id=?", (season['id'],))

# ── 综艺/真人秀(门槛只看人气,和"真实性格倾向"的差值决定人设是加固还是崩) ─────────────

VARIETY_POPULARITY_THRESHOLD = 10
VARIETY_CONTENT = [
    "参加了一档户外真人秀,连续录了两天两夜",
    "上了一档访谈节目,聊了很多没公开过的故事",
    "参加了一档竞技类综艺,拼到最后一刻",
    "录了一期美食探店节目,笑点密集",
]

VARIETY_CHARM_BASE_CHANCE = 15
VARIETY_NATURAL_CHARM_BONUS = 8
VARIETY_SCRIPT_INTEGRITY_BONUS = 2
VARIETY_SCRIPT_CONFLICT_DISCOUNT = 0.8

def do_variety(player, choices=None):
    if player['career_state'] == 'blackout':
        return None, '雪藏期上不了综艺'
    if player['career_state'] == 'sick':
        return None, '生病了,先把身体养好'
    if player['popularity'] < VARIETY_POPULARITY_THRESHOLD:
        return None, '人气不够,还接不到综艺通告'
    if not try_spend_energy(player['id'], 'variety'):
        return None, '体力不够了'
    choices = choices or []
    natural_count = choices.count('natural')
    script_count = choices.count('script')
    persona = player['persona_tag']
    true_p = player['true_personality'] or persona
    content = random.choice(VARIETY_CONTENT)
    if persona == true_p:
        outcome = 'consistent'
        run("UPDATE players SET persona_integrity=MIN(100,persona_integrity+?), popularity=popularity+? WHERE id=?",
            (random.randint(3, 8), random.randint(3, 8), player['id']))
        heat = 18
    elif random.randint(1, 100) <= VARIETY_CHARM_BASE_CHANCE + natural_count * VARIETY_NATURAL_CHARM_BONUS:
        outcome = 'unexpected_charm'
        run("UPDATE players SET popularity=popularity+? WHERE id=?", (random.randint(8, 15), player['id']))
        distribute_fan_gain(player['id'], random.randint(10, 30))
        heat = 28
    else:
        outcome = 'conflict'
        discount = VARIETY_SCRIPT_CONFLICT_DISCOUNT if script_count > 0 else 1.0
        integrity_loss = max(0, int(random.randint(5, 12) * discount) - script_count * VARIETY_SCRIPT_INTEGRITY_BONUS)
        scandal_gain = int(random.randint(2, 8) * discount)
        run("UPDATE players SET persona_integrity=MAX(0,persona_integrity-?), scandal_value=scandal_value+? WHERE id=?",
            (integrity_loss, scandal_gain, player['id']))
        heat = 22
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player['id'], 'variety', content, outcome, heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    if outcome in ('consistent', 'unexpected_charm'):
        generate_comments(post_id, player['id'], fan_w=5, hater_w=1, passerby_w=3)
    else:
        generate_comments(post_id, player['id'], fan_w=2, hater_w=3, passerby_w=3)
    return outcome, None

# ── 好友与私信(合作过才能加好友通讯,好感度够了才能约会) ────────────────────────────

FRIEND_AFFINITY_DATING_THRESHOLD = 50
DM_AFFINITY_GAIN = 2

def get_friendship(player_a_id, player_b_id):
    a, b = sorted([player_a_id, player_b_id])
    return q("SELECT * FROM friendships WHERE player_a_id=? AND player_b_id=?", (a, b), one=True)

def ensure_friendship(player_a_id, player_b_id, affinity_gain=0):
    a, b = sorted([player_a_id, player_b_id])
    existing = q("SELECT * FROM friendships WHERE player_a_id=? AND player_b_id=?", (a, b), one=True)
    if existing:
        run("UPDATE friendships SET affinity=MIN(100,affinity+?) WHERE id=?", (affinity_gain, existing['id']))
    else:
        run("INSERT INTO friendships (player_a_id,player_b_id,affinity,created_ts) VALUES (?,?,?,?)",
            (a, b, clamp(affinity_gain, 0, 100), now_ts()))

def send_message(from_id, to_id, content):
    friendship = get_friendship(from_id, to_id)
    if not friendship:
        return False, '还没有合作过,加不了好友,发不了私信'
    if not try_spend_energy(from_id, 'message'):
        return False, '体力不够了'
    run("INSERT INTO private_messages (from_player_id,to_player_id,content,created_ts) VALUES (?,?,?,?)",
        (from_id, to_id, content, now_ts()))
    ensure_friendship(from_id, to_id, DM_AFFINITY_GAIN)
    return True, '发送成功'

# ── 炒CP(必须有合作作品才能组CP,任何人都能买通稿/黑稿) ───────────────────────────

CP_BOOST_COST = 100
CP_SMEAR_COST = 100

def ensure_cp_pair(player_a_id, player_b_id, bump):
    a, b = sorted([player_a_id, player_b_id])
    existing = q("SELECT * FROM cp_pairs WHERE player_a_id=? AND player_b_id=?", (a, b), one=True)
    if existing:
        run("UPDATE cp_pairs SET heat=heat+? WHERE id=?", (bump, existing['id']))
    else:
        run("INSERT INTO cp_pairs (player_a_id,player_b_id,heat,created_ts) VALUES (?,?,?,?)",
            (a, b, bump, now_ts()))

def boost_cp(buyer_id, cp_id):
    buyer = q("SELECT * FROM players WHERE id=?", (buyer_id,), one=True)
    cp = q("SELECT * FROM cp_pairs WHERE id=?", (cp_id,), one=True)
    if not buyer or not cp:
        return False, '这对CP不存在'
    if buyer['cash'] < CP_BOOST_COST:
        return False, '资金不足'
    if not try_spend_energy(buyer_id, 'cp_boost'):
        return False, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (CP_BOOST_COST, buyer_id))
    run("UPDATE cp_pairs SET heat=heat+? WHERE id=?", (random.randint(15, 35), cp_id))
    return True, '通稿买好了,热度涨了'

def smear_cp(buyer_id, cp_id):
    buyer = q("SELECT * FROM players WHERE id=?", (buyer_id,), one=True)
    cp = q("SELECT * FROM cp_pairs WHERE id=?", (cp_id,), one=True)
    if not buyer or not cp:
        return False, '这对CP不存在'
    if buyer['cash'] < CP_SMEAR_COST:
        return False, '资金不足'
    if not try_spend_energy(buyer_id, 'cp_smear'):
        return False, '体力不够了'
    run("UPDATE players SET cash=cash-? WHERE id=?", (CP_SMEAR_COST, buyer_id))
    run("UPDATE cp_pairs SET heat=MAX(0,heat-?) WHERE id=?", (random.randint(15, 35), cp_id))
    return True, '黑稿买好了,热度降了'

def decay_cp_heat():
    for row in q("SELECT id, heat FROM cp_pairs WHERE heat > 0"):
        run("UPDATE cp_pairs SET heat=heat-? WHERE id=?", (math.ceil(row['heat'] * 0.05), row['id']))

# ── 联合营业(合唱/同台综艺,双方同意才触发,同公司协同更好) ──────────────────────────

COLLAB_TYPES = ['合唱', '同台综艺', '联合直播']
VLOG_TOPICS = ['探店vlog', '旅行vlog', '日常vlog', '游戏直播', '剧组花絮', '宠物日常']

def resolve_collab(player_a_id, player_b_id, topic=None):
    a = q("SELECT * FROM players WHERE id=?", (player_a_id,), one=True)
    b = q("SELECT * FROM players WHERE id=?", (player_b_id,), one=True)
    if not a or not b:
        return
    same_agency = 1 if (a['agency_id'] and a['agency_id'] == b['agency_id']) else 0
    collab_type = f"合拍vlog·{topic}" if topic else random.choice(COLLAB_TYPES)
    base_heat = (a['popularity'] + b['popularity']) // 4 + 10
    flop = a['scandal_value'] > 60 or b['scandal_value'] > 60  # 风险共担:一方黑值高拖累整体评价
    multiplier = 1.3 if same_agency else 1.0

    if flop:
        outcome, heat = 'flop', max(5, base_heat // 2)
        pop_a, pop_b = random.randint(1, 4), random.randint(1, 4)
    else:
        outcome = 'hit'
        heat = int(base_heat * multiplier)
        pop_a = int(random.randint(5, 15) * multiplier)
        pop_b = int(random.randint(5, 15) * multiplier)

    run("UPDATE players SET popularity=popularity+? WHERE id=?", (pop_a, a['id']))
    run("UPDATE players SET popularity=popularity+? WHERE id=?", (pop_b, b['id']))
    if not same_agency and outcome == 'hit':
        distribute_fan_gain(a['id'], random.randint(5, 15))  # 跨公司破圈,互相导一点粉
        distribute_fan_gain(b['id'], random.randint(5, 15))

    content = f"和{b['stage_name']}一起录了{collab_type},效果{'意外的好' if outcome == 'hit' else '有点翻车'}"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (a['id'], 'collab', content, outcome, heat, now_ts()))
    get_db().commit()
    post_id = cur.lastrowid
    generate_comments(post_id, a['id'], fan_w=4 if outcome == 'hit' else 2,
                       hater_w=1 if outcome == 'hit' else 3, passerby_w=2)
    run("INSERT INTO collaborations (player_a_id,player_b_id,collab_type,same_agency,heat,created_ts) "
        "VALUES (?,?,?,?,?,?)", (a['id'], b['id'], collab_type, same_agency, heat, now_ts()))
    ensure_friendship(a['id'], b['id'], 15 if outcome == 'hit' else 3)  # 合作过才能加好友通讯,这是唯一入口
    ensure_cp_pair(a['id'], b['id'], bump=max(10, heat // 2))  # 有合作作品才能组CP,这是唯一入口

# ── 邀请机制(联合营业/恋爱共用:NPC 自动同意,真人需要对方接受) ───────────────────────

def send_invite(from_id, to_id, invite_type, topic=None):
    target = q("SELECT is_npc FROM players WHERE id=?", (to_id,), one=True)
    if not target:
        return False, '对象不存在'
    if from_id == to_id:
        return False, '不能选自己'
    inviter = q("SELECT career_state FROM players WHERE id=?", (from_id,), one=True)
    if inviter and inviter['career_state'] == 'blackout':
        return False, '雪藏期不能主动发起这个'
    if invite_type == 'dating':
        friendship = get_friendship(from_id, to_id)
        if not friendship or friendship['affinity'] < FRIEND_AFFINITY_DATING_THRESHOLD:
            return False, '还没合作过或者好感度不够,先多合作/多聊聊攒好感度'
    if target['is_npc']:
        if not try_spend_energy(from_id, invite_type):
            return False, '体力不够了'
        if invite_type == 'collab':
            resolve_collab(from_id, to_id, topic)
            return True, '合作已经完成'
        else:
            start_relationship(from_id, to_id)
            return True, '已经偷偷开始了这段感情'
    if q("""SELECT id FROM social_invites WHERE invite_type=? AND from_player_id=? AND to_player_id=?
           AND status='pending'""", (invite_type, from_id, to_id), one=True):
        return False, '已经发过邀请了,等对方回应'
    run("INSERT INTO social_invites (invite_type,from_player_id,to_player_id,status,topic,created_ts) "
        "VALUES (?,?,?,'pending',?,?)", (invite_type, from_id, to_id, topic, now_ts()))
    return True, '邀请已发送,等待对方回应'

def respond_invite(player_id, invite_id, accept):
    invite = q("SELECT * FROM social_invites WHERE id=? AND to_player_id=?", (invite_id, player_id), one=True)
    if not invite or invite['status'] != 'pending':
        return False, '这个邀请已经不在了'
    if not accept:
        run("UPDATE social_invites SET status='declined' WHERE id=?", (invite['id'],))
        return True, '已经拒绝这个邀请'
    if not try_spend_energy(player_id, invite['invite_type']):
        return False, '体力不够了,先歇一会儿再来接受这个邀请'
    run("UPDATE social_invites SET status='accepted' WHERE id=?", (invite['id'],))
    if invite['invite_type'] == 'collab':
        resolve_collab(invite['from_player_id'], invite['to_player_id'], invite['topic'])
    else:
        start_relationship(invite['from_player_id'], invite['to_player_id'])
    return True, '已经接受,合作完成了'

# ── 恋爱曝光系统(隐蔽度随时间衰减,曝光后果依人设反差浮动) ───────────────────────────

DATING_SECRECY_DECAY_BASE = 3
DATING_RESPONSE_WINDOW = 3600
HIGH_RISK_PERSONAS = {'高冷禁欲', '纯欲天菜', '学霸精英', '神秘感', '纯情校草', '独立女性'}
LOW_RISK_PERSONAS = {'耿直接地气', '元气少年/少女', '沙雕憨憨', '佛系随缘'}
DATING_RESPONSE_LABELS = {'confess': '发文承认', 'deny': '否认传闻', 'silence': '一直没有回应'}

def start_relationship(player_a_id, player_b_id):
    run("INSERT INTO relationships (player_a_id,player_b_id,secrecy,status,started_ts) "
        "VALUES (?,?,100,'secret',?)", (player_a_id, player_b_id, now_ts()))

def decay_and_check_exposure():
    active = q("SELECT * FROM relationships WHERE status='secret'")
    for rel in active:
        a = q("SELECT popularity FROM players WHERE id=?", (rel['player_a_id'],), one=True)
        b = q("SELECT popularity FROM players WHERE id=?", (rel['player_b_id'],), one=True) if rel['player_b_id'] else None
        combined_pop = (a['popularity'] if a else 0) + (b['popularity'] if b else 0)
        decay = DATING_SECRECY_DECAY_BASE + combined_pop // 50
        new_secrecy = max(0, rel['secrecy'] - decay)
        exposure_chance = (100 - new_secrecy) / 300
        if random.random() < exposure_chance:
            run("UPDATE relationships SET status='exposed_pending', secrecy=?, exposed_ts=?, "
                "response_deadline_ts=? WHERE id=?",
                (new_secrecy, now_ts(), now_ts() + DATING_RESPONSE_WINDOW, rel['id']))
        else:
            run("UPDATE relationships SET secrecy=? WHERE id=?", (new_secrecy, rel['id']))

def auto_resolve_expired_exposures():
    due = q("SELECT id FROM relationships WHERE status='exposed_pending' AND response_deadline_ts <= ?", (now_ts(),))
    for rel in due:
        apply_exposure_consequence(rel['id'], 'silence')

def apply_exposure_consequence(relationship_id, choice, responder_id=None, custom_content=''):
    rel = q("SELECT * FROM relationships WHERE id=?", (relationship_id,), one=True)
    if not rel or rel['status'] != 'exposed_pending':
        return
    for pid in [p for p in [rel['player_a_id'], rel['player_b_id']] if p]:
        player = q("SELECT * FROM players WHERE id=?", (pid,), one=True)
        if not player:
            continue
        persona = player['persona_tag']
        if persona in HIGH_RISK_PERSONAS:
            base_fan_loss_pct, base_scandal = 0.08, 20
        elif persona in LOW_RISK_PERSONAS:
            base_fan_loss_pct, base_scandal = 0.01, 5
        else:
            base_fan_loss_pct, base_scandal = 0.04, 12

        if choice == 'confess':
            fan_loss_pct, scandal = base_fan_loss_pct * 0.7, int(base_scandal * 0.7)
        elif choice == 'deny':
            if random.random() < 0.5:
                fan_loss_pct, scandal = base_fan_loss_pct * 0.6, int(base_scandal * 0.6)
            else:
                fan_loss_pct, scandal = base_fan_loss_pct * 1.6, int(base_scandal * 1.6)
        else:
            fan_loss_pct, scandal = base_fan_loss_pct, base_scandal

        fan_loss = int(player['fans_count'] * fan_loss_pct)
        run("UPDATE players SET fans_count=MAX(0,fans_count-?), scandal_value=scandal_value+?, "
            "popularity=MAX(0,popularity-?) WHERE id=?",
            (fan_loss, scandal, scandal // 3, pid))

        if pid == responder_id and custom_content:
            content = custom_content
        else:
            content = f"{player['stage_name']}恋情曝光,本人{DATING_RESPONSE_LABELS.get(choice, '')}"
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (pid, 'dating_exposed', content, choice, 40, now_ts()))
        get_db().commit()
        post_id = cur.lastrowid
        generate_comments(post_id, pid, fan_w=2, hater_w=4, passerby_w=3)
    run("UPDATE relationships SET status='together' WHERE id=?", (relationship_id,))

# ── 怀孕/生子(双性别都能怀孕,藏不住会被狗仔发现,足月后随机生1-2个孩子) ─────────────

PREGNANCY_CHANCE_PER_TICK = 0.015
PREGNANCY_TERM_MONTHS = 8
PREGNANCY_ABORT_HEALTH_COST = 25
PREGNANCY_DISCOVERY_BASE_CHANCE = 0.03
TWIN_CHANCE = 0.15

def run_pregnancy_checks():
    for rel in q("SELECT * FROM relationships WHERE status='together' AND pregnancy_status='none'"):
        if not rel['player_b_id']:
            continue
        if random.random() < PREGNANCY_CHANCE_PER_TICK:
            carrier = random.choice([rel['player_a_id'], rel['player_b_id']])
            run("""UPDATE relationships SET pregnancy_status='deciding', pregnant_player_id=?,
                   pregnancy_started_ts=? WHERE id=?""", (carrier, now_ts(), rel['id']))

    concealing = q("SELECT * FROM relationships WHERE pregnancy_status='concealing'")
    for rel in concealing:
        months_along = (now_ts() - rel['pregnancy_started_ts']) / MONTH_SECONDS
        if months_along >= PREGNANCY_TERM_MONTHS:
            _deliver_children(rel)
            continue
        if not rel['marriage_announced']:
            discover_chance = PREGNANCY_DISCOVERY_BASE_CHANCE * (1 + months_along / PREGNANCY_TERM_MONTHS)
            if random.random() < discover_chance:
                _paparazzi_discover_pregnancy(rel)

    for child in q("SELECT * FROM children WHERE revealed=0"):
        rel = q("SELECT * FROM relationships WHERE id=?", (child['relationship_id'],), one=True)
        if rel and not rel['marriage_announced'] and random.random() < PREGNANCY_DISCOVERY_BASE_CHANCE:
            _paparazzi_discover_child(child)

def _paparazzi_discover_pregnancy(rel):
    for pid in [p for p in (rel['player_a_id'], rel['player_b_id']) if p]:
        player = q("SELECT * FROM players WHERE id=?", (pid,), one=True)
        if not player:
            continue
        fan_loss = int(player['fans_count'] * 0.05)
        run("UPDATE players SET fans_count=MAX(0,fans_count-?), scandal_value=scandal_value+? WHERE id=?",
            (fan_loss, random.randint(10, 20), pid))
        content = f"{player['stage_name']}被扒出偷偷怀孕在家,一直没有公开"
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (pid, 'pregnancy_exposed', content, 'exposed', 45, now_ts()))
        get_db().commit()
        generate_comments(cur.lastrowid, pid, fan_w=2, hater_w=4, passerby_w=3)

def _paparazzi_discover_child(child):
    for pid in [p for p in (child['parent_a_id'], child['parent_b_id']) if p]:
        player = q("SELECT * FROM players WHERE id=?", (pid,), one=True)
        if not player:
            continue
        fan_loss = int(player['fans_count'] * 0.05)
        run("UPDATE players SET fans_count=MAX(0,fans_count-?), scandal_value=scandal_value+? WHERE id=?",
            (fan_loss, random.randint(10, 20), pid))
        content = f"{player['stage_name']}被扒出早已经悄悄生子,一直瞒着没公开"
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (pid, 'child_exposed', content, 'exposed', 45, now_ts()))
        get_db().commit()
        generate_comments(cur.lastrowid, pid, fan_w=2, hater_w=4, passerby_w=3)

def _deliver_children(rel):
    twin = random.random() < TWIN_CHANCE
    count = 2 if twin else 1
    for _ in range(count):
        gender = random.choice(['male', 'female'])
        run("""INSERT INTO children (relationship_id,parent_a_id,parent_b_id,gender,born_ts)
               VALUES (?,?,?,?,?)""", (rel['id'], rel['player_a_id'], rel['player_b_id'], gender, now_ts()))
    run("UPDATE relationships SET pregnancy_status='born' WHERE id=?", (rel['id'],))

def decide_pregnancy(player_id, relationship_id, choice):
    rel = q("SELECT * FROM relationships WHERE id=?", (relationship_id,), one=True)
    if not rel or rel['pregnancy_status'] != 'deciding':
        return False, '现在没有需要决定的怀孕剧情'
    if player_id not in (rel['player_a_id'], rel['player_b_id']):
        return False, '这不是你的恋爱关系'
    if choice == 'abort':
        run("UPDATE relationships SET pregnancy_status='terminated' WHERE id=?", (relationship_id,))
        run("UPDATE players SET health=MAX(0,health-?) WHERE id=?",
            (PREGNANCY_ABORT_HEALTH_COST, rel['pregnant_player_id']))
        return True, '决定打掉了,身体受了些损伤'
    elif choice == 'conceal':
        run("UPDATE relationships SET pregnancy_status='concealing' WHERE id=?", (relationship_id,))
        return True, '决定藏着生下来,之后要小心别被狗仔盯上'
    return False, '无效的选择'

def name_child(player_id, child_id, name):
    child = q("SELECT * FROM children WHERE id=?", (child_id,), one=True)
    if not child or player_id not in (child['parent_a_id'], child['parent_b_id']):
        return False, '这不是你的孩子'
    if child['name']:
        return False, '已经起过名字了'
    name = (name or '').strip()[:10]
    if not name:
        return False, '名字不能是空的'
    run("UPDATE children SET name=? WHERE id=?", (name, child_id))
    return True, '起好名字了'

def announce_marriage(player_id, relationship_id):
    rel = q("SELECT * FROM relationships WHERE id=?", (relationship_id,), one=True)
    if not rel or rel['status'] != 'together':
        return False, '现在没有可以官宣的关系'
    if player_id not in (rel['player_a_id'], rel['player_b_id']):
        return False, '这不是你的恋爱关系'
    if rel['marriage_announced']:
        return False, '已经官宣过了'
    run("UPDATE relationships SET married=1, marriage_announced=1 WHERE id=?", (relationship_id,))
    for pid in [p for p in (rel['player_a_id'], rel['player_b_id']) if p]:
        player = q("SELECT stage_name FROM players WHERE id=?", (pid,), one=True)
        content = f"{player['stage_name']}官宣结婚了,想把最好的都给这个家"
        cur = get_db().execute(
            "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
            (pid, 'marriage_announced', content, 'announced', 50, now_ts()))
        get_db().commit()
        generate_comments(cur.lastrowid, pid, fan_w=6, hater_w=1, passerby_w=3)
    return True, '官宣结婚了'

def reveal_child(player_id, child_id):
    child = q("SELECT * FROM children WHERE id=?", (child_id,), one=True)
    if not child or player_id not in (child['parent_a_id'], child['parent_b_id']):
        return False, '这不是你的孩子'
    if child['revealed']:
        return False, '已经公开过了'
    run("UPDATE children SET revealed=1 WHERE id=?", (child_id,))
    player = q("SELECT stage_name FROM players WHERE id=?", (player_id,), one=True)
    name_part = child['name'] or '孩子'
    content = f"{player['stage_name']}公开了自己的孩子{name_part},今后要一起努力生活"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player_id, 'child_revealed', content, 'revealed', 50, now_ts()))
    get_db().commit()
    generate_comments(cur.lastrowid, player_id, fan_w=6, hater_w=1, passerby_w=3)
    return True, '公开了孩子'

# ── 粉丝来信(红了之后才会触发的被动正面事件,私信收件箱新增一类) ────────────────────

FAN_LETTER_POPULARITY_THRESHOLD = 20
FAN_LETTER_CHANCE_PER_TICK = 0.08
FAN_LETTER_TEMPLATES = [
    "一直都在关注你,今天看到你发的博突然就哭了,加油鸭",
    "从路人到粉丝就是一瞬间的事,谢谢你让我看到这么努力的样子",
    "偷偷写了这封信,希望你能看到——你真的一直在被喜欢着",
    "追星三年,第一次这么想跟偶像说声谢谢",
    "今天心情不好,刷到你的微博突然就好多了,谢谢你的存在",
    "身边人都不理解我为什么喜欢你,但我知道自己没选错",
    "希望有一天能当面告诉你,你真的改变了我很多",
    "不求回复,只是想让你知道,有人一直在支持你",
]
FAN_LETTER_REPLY_LOYALTY = (2, 6)
FAN_LETTER_REPLY_FANS = (1, 5)

HATER_LETTER_CHANCE = 0.3  # 命中来信触发时,这个比例是黑粉信而不是粉丝信
HATER_LETTER_TEMPLATES = [
    "劝你早点退网,没有实力硬撑真的很尴尬",
    "不知道哪来的自信天天发这些,建议清醒一下",
    "身边人都说你这次营业很刻意,你自己心里没数吗",
    "路人缘都被你作没了,还不知道收敛",
    "这么多年了业务能力一点没涨,靠脸还能撑多久",
    "劝你多花点时间练习,少花点时间凹人设",
    "早就看你不顺眼了,迟早塌房",
    "你的粉丝滤镜是不是太厚了,清醒点吧",
]
HATER_CLAPBACK_ENERGY_KEY = 'message'

def run_fan_letter_checks():
    famous = q("SELECT id FROM players WHERE popularity > ?", (FAN_LETTER_POPULARITY_THRESHOLD,))
    for p in famous:
        if random.random() >= FAN_LETTER_CHANCE_PER_TICK:
            continue
        if random.random() < HATER_LETTER_CHANCE:
            content = random.choice(HATER_LETTER_TEMPLATES)
            sentiment = 'hater'
        else:
            content = random.choice(FAN_LETTER_TEMPLATES)
            sentiment = 'fan'
        run("INSERT INTO fan_letters (player_id,content,sentiment,created_ts) VALUES (?,?,?,?)",
            (p['id'], content, sentiment, now_ts()))

def reply_fan_letter(player_id, letter_id):
    letter = q("SELECT * FROM fan_letters WHERE id=?", (letter_id,), one=True)
    if not letter or letter['player_id'] != player_id:
        return False, '找不到这封信'
    if letter['replied']:
        return False, '已经回复过了'
    if not try_spend_energy(player_id, 'message'):
        return False, '体力不够了'
    run("UPDATE players SET core_fan_loyalty=core_fan_loyalty+?, fans_count=fans_count+? WHERE id=?",
        (random.randint(*FAN_LETTER_REPLY_LOYALTY), random.randint(*FAN_LETTER_REPLY_FANS), player_id))
    run("UPDATE fan_letters SET replied=1 WHERE id=?", (letter_id,))
    return True, '回信发出去了'

def dismiss_fan_letter(player_id, letter_id):
    letter = q("SELECT * FROM fan_letters WHERE id=?", (letter_id,), one=True)
    if not letter or letter['player_id'] != player_id:
        return False, '找不到这封信'
    if letter['replied']:
        return False, '已经处理过了'
    run("UPDATE fan_letters SET replied=1 WHERE id=?", (letter_id,))
    return True, '不理它了'

def clapback_hater_letter(player_id, letter_id):
    letter = q("SELECT * FROM fan_letters WHERE id=?", (letter_id,), one=True)
    if not letter or letter['player_id'] != player_id:
        return False, '找不到这封信'
    if letter['replied']:
        return False, '已经处理过了'
    if not try_spend_energy(player_id, HATER_CLAPBACK_ENERGY_KEY):
        return False, '体力不够了'
    if random.random() < 0.5:
        run("UPDATE players SET popularity=popularity+? WHERE id=?", (random.randint(1, 3), player_id))
        msg = '怼回去了,还挺解气,涨了点人气'
    else:
        run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (random.randint(1, 3), player_id))
        msg = '怼回去了,不过被截图流传,涨了点黑值'
    run("UPDATE fan_letters SET replied=1 WHERE id=?", (letter_id,))
    return True, msg

# ── 粉丝送礼物(纯收藏向,进背包,不给数值加成) ──────────────────────────────────────

FAN_GIFT_POPULARITY_THRESHOLD = 20
FAN_GIFT_CHANCE_PER_TICK = 0.05
FAN_GIFT_POOL = {
    'common': {
        'weight': 60,
        'items': ['应援手幅', '粉丝自制贴纸', '打印的合影照片', '手写贺卡', '应援色徽章'],
    },
    'premium': {
        'weight': 30,
        'items': ['亲手织的围巾', '手绘同人插画', '定制钥匙扣', '应援灯牌'],
    },
    'rare': {
        'weight': 10,
        'items': ['限定周边礼盒', '粉丝集资定制手办', '生日应援企划纪念册'],
    },
}
FAN_GIFT_RARITY_LABELS = {'common': '普通', 'premium': '精品', 'rare': '珍贵'}
FAN_GIFT_FROM_LABELS = ['一位路过的粉丝', '匿名应援站', '一位死忠粉', '后援会', '一位老粉']

def run_fan_gift_checks():
    famous = q("SELECT id FROM players WHERE popularity > ?", (FAN_GIFT_POPULARITY_THRESHOLD,))
    for p in famous:
        if random.random() >= FAN_GIFT_CHANCE_PER_TICK:
            continue
        rarities = list(FAN_GIFT_POOL.keys())
        weights = [FAN_GIFT_POOL[r]['weight'] for r in rarities]
        rarity = random.choices(rarities, weights=weights)[0]
        item_name = random.choice(FAN_GIFT_POOL[rarity]['items'])
        from_label = random.choice(FAN_GIFT_FROM_LABELS)
        run("INSERT INTO fan_gifts (player_id,item_name,rarity,from_label,created_ts) VALUES (?,?,?,?,?)",
            (p['id'], item_name, rarity, from_label, now_ts()))

# ── 里程碑成就墙(数值型)────────────────────────────────────────────────────────

MILESTONE_DEFINITIONS = [
    ('fans_1000', '粉丝破1000', lambda p: p['fans_count'] >= 1000),
    ('fans_10000', '粉丝破10000', lambda p: p['fans_count'] >= 10000),
    ('fans_100000', '粉丝破100000', lambda p: p['fans_count'] >= 100000),
    ('tier_C', '晋升咖位C', lambda p: p['popularity'] >= 15),
    ('tier_B', '晋升咖位B', lambda p: p['popularity'] >= 75),
    ('tier_A', '晋升咖位A', lambda p: p['popularity'] >= 180),
    ('tier_S', '晋升咖位S', lambda p: p['popularity'] >= 280),
    ('awards_1', '首次获奖', lambda p: p['awards_won'] >= 1),
    ('awards_3', '获奖达到3次', lambda p: p['awards_won'] >= 3),
    ('awards_5', '获奖达到5次', lambda p: p['awards_won'] >= 5),
]
MILESTONE_LABELS = {key: label for key, label, _ in MILESTONE_DEFINITIONS}
MILESTONE_LABELS['ambassador_first'] = '首次拿下品牌代言人'
MILESTONE_LABELS['oscar_winner'] = '奥斯卡封帝/封后'

def unlock_milestone(player_id, key):
    if not q("SELECT 1 FROM players WHERE id=?", (player_id,), one=True):
        return
    already = q("SELECT 1 FROM milestones_achieved WHERE player_id=? AND milestone_key=?",
                (player_id, key), one=True)
    if already:
        return
    run("INSERT OR IGNORE INTO milestones_achieved (player_id,milestone_key,created_ts) VALUES (?,?,?)",
        (player_id, key, now_ts()))
    player = q("SELECT stage_name FROM players WHERE id=?", (player_id,), one=True)
    content = f"{player['stage_name']}达成里程碑:{MILESTONE_LABELS.get(key, key)}"
    cur = get_db().execute(
        "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
        (player_id, 'milestone', content, 'success', 25, now_ts()))
    get_db().commit()
    generate_comments(cur.lastrowid, player_id, fan_w=4, hater_w=1, passerby_w=2)

def check_milestones(player_id):
    player = q("SELECT * FROM players WHERE id=?", (player_id,), one=True)
    if not player:
        return
    achieved = {r['milestone_key'] for r in q(
        "SELECT milestone_key FROM milestones_achieved WHERE player_id=?", (player_id,))}
    for key, _, check in MILESTONE_DEFINITIONS:
        if key not in achieved and check(player):
            unlock_milestone(player_id, key)
    if 'ambassador_first' not in achieved:
        won_count = q("SELECT COUNT(*) c FROM posts WHERE player_id=? AND post_type='ambassador_won'",
                      (player_id,), one=True)['c']
        if won_count >= 1:
            unlock_milestone(player_id, 'ambassador_first')

def check_all_milestones():
    for row in q("SELECT id FROM players"):
        check_milestones(row['id'])

# ── 私生饭骚扰(红了之后才会触发的被动负面事件) ────────────────────────────────────

SASAENG_POPULARITY_THRESHOLD = 50
SASAENG_CHANCE_PER_TICK = 0.05
SASAENG_KINDS = ['stalk', 'leak']

DM_LEAK_CHANCE = 0.4  # 有私信记录的情况下,私生饭优先泄露私聊而不是走通用骚扰

def run_sasaeng_checks():
    famous = q("SELECT id, stage_name FROM players WHERE popularity > ?", (SASAENG_POPULARITY_THRESHOLD,))
    for p in famous:
        if random.random() >= SASAENG_CHANCE_PER_TICK:
            continue
        dm_row = q("""SELECT from_player_id, to_player_id FROM private_messages
                     WHERE from_player_id=? OR to_player_id=? ORDER BY RANDOM() LIMIT 1""",
                   (p['id'], p['id']), one=True)
        if dm_row and random.random() < DM_LEAK_CHANCE:
            partner_id = dm_row['to_player_id'] if dm_row['from_player_id'] == p['id'] else dm_row['from_player_id']
            partner = q("SELECT stage_name FROM players WHERE id=?", (partner_id,), one=True)
            scandal_gain = random.randint(8, 18)
            run("UPDATE players SET scandal_value=scandal_value+? WHERE id=?", (scandal_gain, p['id']))
            content = f"{p['stage_name']}和{partner['stage_name'] if partner else '神秘人士'}的私聊记录疑似曝光"
            cur = get_db().execute(
                "INSERT INTO posts (player_id,post_type,content,outcome,heat,created_ts) VALUES (?,?,?,?,?,?)",
                (p['id'], 'dm_leaked', content, 'leaked', 32, now_ts()))
            get_db().commit()
            post_id = cur.lastrowid
            generate_comments(post_id, p['id'], fan_w=2, hater_w=4, passerby_w=3)
            run("INSERT INTO sasaeng_events (target_player_id,hired_by_player_id,event_kind,created_ts) "
                "VALUES (?,NULL,'dm_leak',?)", (p['id'], now_ts()))
            continue
        kind = random.choice(SASAENG_KINDS)
        scandal_gain = random.randint(3, 10)
        fan_loss = random.randint(5, 20)
        run("UPDATE players SET scandal_value=scandal_value+?, fans_count=MAX(0,fans_count-?) WHERE id=?",
            (scandal_gain, fan_loss, p['id']))
        run("INSERT INTO sasaeng_events (target_player_id,hired_by_player_id,event_kind,created_ts) "
            "VALUES (?,NULL,?,?)", (p['id'], kind, now_ts()))

# ── NPC 竞争者自动行为(每个 tick 随机行动,和真人共用同一套判定) ───────────────────

NPC_ACTION_CHANCE = 0.4
NPC_ATTACK_CHANCE = 0.12
NPC_AUTO_CONTENT = {
    'daily':    ["今天状态不错,继续加油", "谢谢大家一直以来的支持", "又是元气满满的一天"],
    'persona':  ["做自己觉得对的事,足够了", "有些话不吐不快,今天想聊聊自己", "希望大家能看到真实的我"],
    'clapback': ["有些话我不会一直忍着不说", "谣言不攻自破,清者自清", "该澄清的事情必须澄清"],
}

NPC_GIG_CHANCE = 0.35
NPC_DRAMA_APPLY_CHANCE = 0.5

NPC_VARIETY_CHANCE = 0.15
NPC_COLLAB_CHANCE = 0.08
NPC_DATING_CHANCE = 0.04

NPC_BRAND_APPLY_CHANCE = 0.3
NPC_SONG_CHANCE = 0.1
NPC_CONCERT_CHANCE = 0.03
NPC_AWARDS_CAMPAIGN_CHANCE = 0.2
NPC_LUXURY_CHANCE = 0.1
NPC_SUPER_TOPIC_CHANCE = 0.2

def npc_settlement_tick():
    """高频结算循环(每20~30秒跑一次,由 run.py 里独立线程驱动):
    只处理"到点结算"类逻辑(判断条件是 xxx_ts <= now),让剧组定角/杀青、代言签约/到期这类结果尽快出来,
    不含衰减/概率类逻辑(那些是按"每小时一次"校准的数值平衡,放这里跑会被放大很多倍)。"""
    resolve_casting()
    resolve_shooting()
    resolve_brand_casting()
    check_brand_contracts()
    check_ambassador_status()
    resolve_award_season()
    auto_resolve_expired_exposures()
    lift_blackout_if_due()

def npc_auto_tick():
    maybe_open_drama()
    maybe_open_film()
    npc_auto_audition()
    maybe_open_brand()
    check_all_milestones()
    grow_product_sales()
    run_hate_campaigns()
    decay_cp_heat()
    maybe_open_award_shows()
    decay_and_check_exposure()
    decay_scandal_and_check_collapse()
    accrue_anti_scandal_reserve()
    run_health_checks()
    run_pregnancy_checks()

    npcs = q("SELECT * FROM players WHERE is_npc=1")
    open_roles = list(q("SELECT id FROM drama_roles WHERE status='casting'"))
    open_brands = list(q("SELECT id FROM brands WHERE status='open'"))
    for npc in npcs:
        if random.random() < NPC_ACTION_CHANCE:
            post_type = random.choices(['daily', 'persona', 'clapback'], weights=[60, 25, 15])[0]
            content = random.choice(NPC_AUTO_CONTENT[post_type])
            resolve_post_effects(dict(npc), post_type, content)
        if random.random() < NPC_GIG_CHANCE:
            do_gig(dict(npc))
        if open_roles and random.random() < NPC_DRAMA_APPLY_CHANCE:
            for r in open_roles:
                ok, _ = apply_for_role(npc['id'], r['id'])
                if ok:
                    break  # 一次 tick 最多报一个,不要疯狂海投
        if open_brands and random.random() < NPC_BRAND_APPLY_CHANCE:
            for b in open_brands:
                ok, _ = apply_for_brand(npc['id'], b['id'])
                if ok:
                    break
        if random.random() < NPC_SONG_CHANCE:
            release_song(dict(npc))
        if random.random() < NPC_CONCERT_CHANCE:
            hold_concert(dict(npc))
        if random.random() < NPC_LUXURY_CHANCE:
            draw_luxury_item(dict(npc))
        if random.random() < NPC_SUPER_TOPIC_CHANCE:
            do_super_topic_checkin(dict(npc), f"{npc['stage_name']}超话打卡")
        if random.random() < NPC_AWARDS_CAMPAIGN_CHANCE:
            my_nom = q("SELECT category_id FROM award_nominees WHERE player_id=? ORDER BY RANDOM() LIMIT 1",
                       (npc['id'],), one=True)
            if my_nom:
                campaign_boost(npc['id'], my_nom['category_id'])
        if random.random() < NPC_VARIETY_CHANCE:
            do_variety(dict(npc))
        if random.random() < NPC_COLLAB_CHANCE:
            target = q("SELECT id FROM players WHERE id != ? ORDER BY RANDOM() LIMIT 1", (npc['id'],), one=True)
            if target:
                send_invite(npc['id'], target['id'], 'collab')
        if random.random() < NPC_DATING_CHANCE:
            existing = q("""SELECT id FROM relationships WHERE (player_a_id=? OR player_b_id=?)
                            AND status IN ('secret','exposed_pending','together')""", (npc['id'], npc['id']), one=True)
            if not existing:
                target = q("SELECT id FROM players WHERE id != ? ORDER BY RANDOM() LIMIT 1", (npc['id'],), one=True)
                if target:
                    send_invite(npc['id'], target['id'], 'dating')
        if random.random() < NPC_ATTACK_CHANCE:
            npc_row = q("SELECT * FROM players WHERE id=?", (npc['id'],), one=True)
            if npc_row and npc_row['cash'] >= ATTACK_COST:
                # 优先盯着当前最火的那几个人打,枪打出头鸟
                candidates = q("""SELECT id FROM players WHERE id != ?
                                  ORDER BY popularity DESC LIMIT 8""", (npc['id'],))
                if candidates:
                    target = random.choice(list(candidates))
                    execute_attack(npc['id'], target['id'])

# ── 今日待办(打开主页就知道现在能做什么,不用自己满世界翻) ──────────────────────────

def get_todo_items(player):
    pid = player['id']
    items = []

    if player['career_state'] not in ('blackout', 'sick') and not is_actor_busy(pid):
        applied_role_ids = {r['role_id'] for r in q(
            "SELECT role_id FROM role_applications WHERE player_id=?", (pid,))}
        open_roles = q("""SELECT r.id, r.role_name, r.tier_requirement, r.gender_requirement,
                                  d.title, d.format
                           FROM drama_roles r JOIN dramas d ON d.id = r.drama_id
                           WHERE r.status='casting'""")
        eligible = []
        for r in open_roles:
            if r['id'] in applied_role_ids:
                continue
            if r['gender_requirement'] != 'any' and r['gender_requirement'] != player['gender']:
                continue
            if not meets_tier(player['popularity'], r['tier_requirement']):
                continue
            if r['format'] == 'film' and player['awards_won'] < FILM_MIN_AWARDS:
                continue
            eligible.append(r)
        if eligible:
            first = eligible[0]
            example = f"《{first['title']}》{first['role_name']}"
            text = f"有 {len(eligible)} 个能报的剧组角色在招募" + (f",比如{example}" if len(eligible) > 1 else f":{example}")
            items.append({'text': text, 'url': url_for('drama_list')})

    open_brands = q("SELECT * FROM brands WHERE status='open'")
    applied_brand_ids = {b['brand_id'] for b in q(
        "SELECT brand_id FROM brand_applications WHERE player_id=?", (pid,))}
    eligible_brands = [b for b in open_brands if b['id'] not in applied_brand_ids
                        and eligible_for_brand(player, b)[0]]
    if eligible_brands:
        first = eligible_brands[0]
        text = f"有 {len(eligible_brands)} 个能接的代言在招募" + \
               (f",比如{first['brand_name']}" if len(eligible_brands) > 1 else f":{first['brand_name']}")
        items.append({'text': text, 'url': url_for('brand_list')})

    pending_invites = q("""SELECT invite_type FROM social_invites
                           WHERE to_player_id=? AND status='pending'""", (pid,))
    collab_n = sum(1 for i in pending_invites if i['invite_type'] == 'collab')
    dating_n = sum(1 for i in pending_invites if i['invite_type'] == 'dating')
    if collab_n:
        items.append({'text': f"有 {collab_n} 个联合营业邀请等你回应", 'url': url_for('collab_page')})
    if dating_n:
        items.append({'text': f"有 {dating_n} 个约会邀请等你回应", 'url': url_for('dating_page')})

    if not items:
        energy = get_effective_energy(pid)
        if energy >= 50:
            items.append({'text': f"体力还剩 {energy} 点没用,去接个通告或发条博客吧", 'url': url_for('weibo')})

    return items

@app.route('/profile')
@login_required
def profile():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if not player['revealed']:
        return redirect(url_for('reveal'))
    run("UPDATE players SET notifications_seen_ts=? WHERE id=?", (now_ts(), player['id']))
    player_view = dict(player)
    player_view['talents'] = json.loads(player_view['talents'] or '{}')
    player_view['traits'] = json.loads(player_view['hidden_traits'] or '[]')
    career_lines_list = json.loads(player_view['career_lines'] or '[]')
    player_view['career_line'] = career_lines_list[0]
    player_view['tier'] = get_tier(player_view['popularity'])
    agency = q("SELECT * FROM agencies WHERE id=?", (player_view['agency_id'],), one=True)
    active_dramas = q("""SELECT d.title, r.role_name, r.status FROM drama_roles r
                         JOIN dramas d ON d.id = r.drama_id
                         WHERE r.winner_player_id=? AND r.status='shooting'""", (player['id'],))
    active_brands = q("SELECT brand_name, tier, contract_end_ts FROM brands WHERE status='signed' AND signed_player_id=?",
                       (player['id'],))
    transition_status = get_career_transition_status(player)
    milestones = q("SELECT milestone_key, created_ts FROM milestones_achieved WHERE player_id=? ORDER BY created_ts",
                   (player['id'],))
    return render_template('profile.html', player=player_view, agency=agency,
                            career_line_labels_all=[CAREER_LINE_LABELS[l] for l in career_lines_list],
                            trait_info=HIDDEN_TRAITS, family_info=FAMILY_BACKGROUNDS,
                            active_dramas=active_dramas, active_brands=active_brands,
                            transition_status=transition_status, career_line_labels=CAREER_LINE_LABELS,
                            transition_cost=CAREER_TRANSITION_COST,
                            milestones=milestones, milestone_labels=MILESTONE_LABELS)

@app.route('/rest', methods=['POST'])
@login_required
def rest_route():
    player = me()
    if not player:
        return redirect(url_for('login'))
    ok, msg = rest_action(player['id'])
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('profile'))

@app.route('/travel', methods=['POST'])
@login_required
def travel_route():
    player = me()
    if not player:
        return redirect(url_for('login'))
    ok, msg = travel_action(player['id'])
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('profile'))

# 应援色分类:HSV 的色相(H)决定色系,饱和度(S)/明度(V)甄别黑白灰和粉色这几个特例。
# 色相分区的边界是按常见色感画的经验值,不是严格的色彩学定义,允许后续微调。
FAN_COLOR_SUFFIXES = ['红', '橙', '黄', '绿', '青', '蓝', '紫', '粉', '黑', '白', '灰']

def classify_fan_color_suffix(hex_color):
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h_deg = h * 360
    if v < 0.2:
        return '黑'
    if s < 0.12:
        return '白' if v >= 0.7 else '灰'
    in_red_zone = h_deg >= 330 or h_deg < 20
    if in_red_zone and s < 0.5 and v > 0.65:
        return '粉'  # 红色系但饱和度不高、够亮,读起来是"粉"不是"红"
    if in_red_zone:
        return '红'
    if h_deg < 45:
        return '橙'
    if h_deg < 70:
        return '黄'
    if h_deg < 160:
        return '绿'
    if h_deg < 200:
        return '青'
    if h_deg < 260:
        return '蓝'
    return '紫'  # 260-330

@app.route('/notifications')
@login_required
def notifications_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    counts = get_notification_count(me_player['id'])
    return render_template('notifications.html', counts=counts)

@app.route('/profile/fan_club_name', methods=['POST'])
@login_required
def set_fan_club_name():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    if me_player['fan_club_name']:
        flash('粉丝团名字已经定下来了,不能再改', 'error')
        return redirect(url_for('profile'))
    prefix = request.form.get('fan_club_prefix', '').strip()
    color = request.form.get('fan_club_color', '').strip()
    if not (1 <= len(prefix) <= 10):
        flash('粉丝团名字前缀长度需在 1-10 位之间', 'error')
        return redirect(url_for('profile'))
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        flash('应援色格式不对', 'error')
        return redirect(url_for('profile'))
    suffix = classify_fan_color_suffix(color)
    name = f"{prefix}{suffix}"
    run("UPDATE players SET fan_club_name=?, fan_club_color=? WHERE id=?", (name, color, me_player['id']))
    flash(f"粉丝团正式定名为「{name}」,应援色也定下来了,以后都不能再改了", 'ok')
    return redirect(url_for('profile'))

@app.route('/career/transition', methods=['POST'])
@login_required
def career_transition():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    target_line = request.form.get('target_line', '')
    ok, msg = do_career_transition(me_player['id'], target_line)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('profile'))

@app.route('/weibo', methods=['GET'])
@login_required
def weibo():
    player = me()
    if player and not player['revealed']:
        return redirect(url_for('reveal'))
    if player:
        player['tier'] = get_tier(player['popularity'])
    posts = q("""SELECT po.*, p.stage_name FROM posts po
                 JOIN players p ON p.id = po.player_id
                 ORDER BY po.created_ts DESC LIMIT 30""")
    posts = [dict(p) for p in posts]
    for p in posts:
        comments = []
        for c in q("SELECT * FROM post_comments WHERE post_id=? ORDER BY created_ts", (p['id'],)):
            c = dict(c)
            if c['commenter_id']:
                commenter = q("SELECT stage_name FROM players WHERE id=?", (c['commenter_id'],), one=True)
                c['commenter_name'] = commenter['stage_name'] if commenter else '匿名艺人'
            comments.append(c)
        p['comments'] = comments
        p['can_edit'] = bool(player and p['player_id'] == player['id']
                              and p['editable_until_ts'] and p['editable_until_ts'] > now_ts())
        sales = q("SELECT product_name, sales_count FROM product_sales WHERE post_id=?", (p['id'],), one=True)
        p['sales'] = dict(sales) if sales else None
    todo_items = get_todo_items(player) if player else []
    return render_template('weibo.html', player=player, posts=posts,
                            post_type_labels=POST_TYPE_LABELS, composable_post_types=COMPOSABLE_POST_TYPES,
                            crisis_stance_labels=CRISIS_STANCE_LABELS,
                            commercial_shoot_cost=COMMERCIAL_SHOOT_COST, magazine_cost=MAGAZINE_COST,
                            ambassador_link_ready=True, todo_items=todo_items)

@app.route('/weibo/post/<int:post_id>/edit', methods=['POST'])
@login_required
def weibo_post_edit(post_id):
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    post = q("SELECT * FROM posts WHERE id=?", (post_id,), one=True)
    if not post or post['player_id'] != me_player['id']:
        flash('无法编辑这条微博', 'error')
        return redirect(url_for('weibo'))
    if not post['editable_until_ts'] or post['editable_until_ts'] < now_ts():
        flash('编辑窗口已经关闭', 'error')
        return redirect(url_for('weibo'))
    content = request.form.get('content', '').strip()
    if not content:
        flash('内容不能为空', 'error')
        return redirect(url_for('weibo'))
    run("UPDATE posts SET content=? WHERE id=?", (content, post_id))
    flash('感言已更新', 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/post', methods=['POST'])
@login_required
def weibo_post():
    player = me()
    if not player:
        return redirect(url_for('login'))
    post_type = request.form.get('post_type', 'daily')
    content = request.form.get('content', '').strip()
    stance = request.form.get('stance', '')
    if not content:
        flash('内容不能为空', 'error')
        return redirect(url_for('weibo'))
    outcome = resolve_post_effects(player, post_type, content, stance=stance)
    if outcome == 'no_energy':
        flash('体力不够了,先歇一会儿吧', 'error')
    elif outcome == 'blackout':
        flash('雪藏期间做不了这个', 'error')
    return redirect(url_for('weibo'))

# ── 明星互评(可能双赢,可能双输,可能只对一边有利) ─────────────────────────────────

INTERACTION_OUTCOMES = ['mutual_good', 'mutual_bad', 'favor_commenter', 'favor_poster']
INTERACTION_WEIGHTS = [35, 15, 25, 25]

@app.route('/weibo/comment', methods=['POST'])
@login_required
def weibo_comment():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    post_id = request.form.get('post_id', '')
    content = request.form.get('content', '').strip()
    if not content:
        flash('评论内容不能为空', 'error')
        return redirect(url_for('weibo'))
    post = q("SELECT * FROM posts WHERE id=?", (post_id,), one=True)
    if not post:
        return redirect(url_for('weibo'))
    if not try_spend_energy(me_player['id'], 'comment'):
        flash('体力不够了,先歇一会儿吧', 'error')
        return redirect(url_for('weibo'))

    poster_id = post['player_id']
    delta = random.randint(1, 5)
    if poster_id != me_player['id']:
        outcome = random.choices(INTERACTION_OUTCOMES, weights=INTERACTION_WEIGHTS)[0]
        if outcome == 'mutual_good':
            run("UPDATE players SET popularity=popularity+? WHERE id=?", (delta, poster_id))
            run("UPDATE players SET popularity=popularity+? WHERE id=?", (delta, me_player['id']))
        elif outcome == 'mutual_bad':
            run("UPDATE players SET popularity=MAX(0,popularity-?) WHERE id=?", (delta, poster_id))
            run("UPDATE players SET popularity=MAX(0,popularity-?) WHERE id=?", (delta, me_player['id']))
        elif outcome == 'favor_commenter':
            run("UPDATE players SET popularity=popularity+? WHERE id=?", (delta, me_player['id']))
        elif outcome == 'favor_poster':
            run("UPDATE players SET popularity=popularity+? WHERE id=?", (delta, poster_id))

    run("INSERT INTO post_comments (post_id,stance,content,commenter_id,created_ts) VALUES (?,?,?,?,?)",
        (post_id, 'celebrity', content, me_player['id'], now_ts()))
    return redirect(url_for('weibo'))

# ── 买黑料/买狗仔造谣(攻击其他艺人的操作页) ───────────────────────────────────────

@app.route('/weibo/attack', methods=['GET', 'POST'])
@login_required
def weibo_attack():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    if request.method == 'POST':
        target_id = request.form.get('target_id', '')
        target = q("SELECT * FROM players WHERE id=?", (target_id,), one=True)
        if not target or str(target['id']) == str(me_player['id']):
            flash('目标无效', 'error')
            return redirect(url_for('weibo_attack'))
        if me_player['cash'] < ATTACK_COST:
            flash('资金不足,雇不起狗仔', 'error')
            return redirect(url_for('weibo_attack'))
        if me_player['energy'] < ENERGY_COSTS['attack']:
            flash('体力不够了,先歇一会儿吧', 'error')
            return redirect(url_for('weibo_attack'))
        backfire = execute_attack(me_player['id'], target['id'])
        if backfire:
            flash('爆料被拆穿了,反噬到自己身上', 'error')
        else:
            flash(f"已经买通狗仔,对{target['stage_name']}的爆料已经放出", 'ok')
        return redirect(url_for('weibo_attack'))

    targets = q("""SELECT id, stage_name, popularity, scandal_value, is_npc FROM players
                   WHERE id != ? ORDER BY popularity DESC LIMIT 30""", (me_player['id'],))
    fresh_since = now_ts() - INTEL_FRESH_SECONDS
    intel_rows = q("""SELECT target_player_id, tier, revealed_json FROM intel_reports
                      WHERE buyer_player_id=? AND created_ts>? ORDER BY created_ts DESC""",
                   (me_player['id'], fresh_since))
    my_intel = {}
    for r in intel_rows:
        my_intel.setdefault(r['target_player_id'], json.loads(r['revealed_json']))
    return render_template('weibo_attack.html', targets=targets, cost=ATTACK_COST, cash=me_player['cash'],
                            my_intel=my_intel)

# ── 黑料情报市场 ────────────────────────────────────────────────────────────────

@app.route('/weibo/intel', methods=['GET'])
@login_required
def intel_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    targets = q("""SELECT id, stage_name, popularity, is_npc FROM players
                   WHERE id != ? ORDER BY popularity DESC LIMIT 30""", (me_player['id'],))
    my_reports = q("""SELECT ir.*, p.stage_name as target_name FROM intel_reports ir
                      JOIN players p ON p.id = ir.target_player_id
                      WHERE ir.buyer_player_id=? ORDER BY ir.created_ts DESC LIMIT 30""", (me_player['id'],))
    reports_view = []
    for r in my_reports:
        r = dict(r)
        r['revealed'] = json.loads(r['revealed_json'])
        reports_view.append(r)
    return render_template('intel.html', targets=targets, my_reports=reports_view,
                            my_tier=get_tier(me_player['popularity']), tiers=INTEL_TIERS)

@app.route('/weibo/intel/buy', methods=['POST'])
@login_required
def intel_buy():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    target_id = request.form.get('target_id', '')
    tier = request.form.get('tier', 'basic')
    ok, msg = buy_intel(me_player['id'], int(target_id), tier)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('intel_page'))

# ── 狗仔私信爆料收件箱 ──────────────────────────────────────────────────────────

@app.route('/weibo/paparazzi', methods=['GET'])
@login_required
def paparazzi_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    ensure_paparazzi_tips(me_player['id'])
    tips = q("""SELECT pt.*, p.stage_name as target_name FROM paparazzi_tips pt
               JOIN players p ON p.id = pt.target_player_id
               WHERE pt.player_id=? AND pt.status='pending' ORDER BY pt.created_ts DESC""",
             (me_player['id'],))
    return render_template('paparazzi.html', tips=tips, tiers=INTEL_TIERS, attack_cost=ATTACK_COST,
                            cash=me_player['cash'], hate_campaign_cost=HATE_CAMPAIGN_COST,
                            hate_campaign_ticks=HATE_CAMPAIGN_TICKS)

@app.route('/weibo/paparazzi/act', methods=['POST'])
@login_required
def paparazzi_act():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    tip_id = request.form.get('tip_id', '')
    action = request.form.get('action', '')
    tip = q("SELECT * FROM paparazzi_tips WHERE id=?", (tip_id,), one=True)
    if not tip or tip['player_id'] != me_player['id'] or tip['status'] != 'pending':
        flash('这条线索已经处理过了', 'error')
        return redirect(url_for('paparazzi_page'))
    if action in ('basic', 'deep'):
        ok, msg = buy_intel(me_player['id'], tip['target_player_id'], action)
        flash(msg, 'ok' if ok else 'error')
    elif action == 'attack':
        if me_player['cash'] < ATTACK_COST:
            flash('资金不足,雇不起狗仔', 'error')
            return redirect(url_for('paparazzi_page'))
        target = q("SELECT stage_name FROM players WHERE id=?", (tip['target_player_id'],), one=True)
        backfire = execute_attack(me_player['id'], tip['target_player_id'])
        if backfire is None:
            flash('体力不够了,先歇一会儿吧', 'error')
            return redirect(url_for('paparazzi_page'))
        elif backfire:
            flash('爆料被拆穿了,反噬到自己身上', 'error')
        else:
            flash(f"已经把{target['stage_name'] if target else '对方'}的料捅出去了", 'ok')
    elif action == 'hate_campaign':
        ok, msg = hire_hate_campaign(me_player['id'], tip['target_player_id'])
        flash(msg, 'ok' if ok else 'error')
    else:
        flash('无效的操作', 'error')
        return redirect(url_for('paparazzi_page'))
    run("UPDATE paparazzi_tips SET status='resolved' WHERE id=?", (tip_id,))
    return redirect(url_for('paparazzi_page'))

# ── 买热搜 / 反黑值 / 做公益(塌房自救) ──────────────────────────────────────────

@app.route('/weibo/boost_trend', methods=['POST'])
@login_required
def weibo_boost_trend():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if player['career_state'] == 'blackout':
        flash('雪藏期买热搜也没人理你了', 'error')
        return redirect(url_for('weibo'))
    if player['cash'] < BOOST_TREND_COST:
        flash('资金不足,买不起这波热搜', 'error')
        return redirect(url_for('weibo'))
    heat = buy_trend(player['id'])
    if heat is None:
        flash('体力不够了,先歇一会儿吧', 'error')
    else:
        flash(f'买热搜成功,注入了 {heat} 点热度', 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/use_reserve', methods=['POST'])
@login_required
def weibo_use_reserve():
    player = me()
    if not player:
        return redirect(url_for('login'))
    used = use_anti_scandal_reserve(player['id'])
    if used <= 0:
        flash('没有可用的反黑值,或者现在没有黑值需要清', 'error')
    else:
        flash(f'公关团队帮你压下去了 {used} 点黑值', 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/refresh_energy', methods=['POST'])
@login_required
def weibo_refresh_energy():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if ENERGY_REGEN_SECONDS >= 60:
        regen_desc = f'{ENERGY_REGEN_SECONDS // 60} 分钟'
    else:
        regen_desc = f'{ENERGY_REGEN_SECONDS} 秒'
    flash(f'当前体力 {player["energy"]}/100(体力是自动恢复的,每 {regen_desc} +1 点,不用一直点这个按钮)', 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/charity', methods=['POST'])
@login_required
def weibo_charity():
    player = me()
    if not player:
        return redirect(url_for('login'))
    reduction, err = do_charity(player)
    if err:
        flash(err, 'error')
    else:
        flash(f'低调做了公益,黑值降了 {reduction} 点', 'ok')
    return redirect(url_for('weibo'))

# ── 接通告(赚钱) ────────────────────────────────────────────────────────────────

@app.route('/weibo/gig', methods=['POST'])
@login_required
def weibo_gig():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if player['career_state'] == 'blackout':
        flash('雪藏期接不到通告,先做做公益吧', 'error')
        return redirect(url_for('weibo'))
    gain = do_gig(player)
    if gain is None:
        flash('体力不够了,先歇一会儿吧', 'error')
    else:
        flash(f'接了个通告,到手 {gain} 资金', 'ok')
    return redirect(url_for('weibo'))

# ── 抢角色 ─────────────────────────────────────────────────────────────────────

GENDER_LABELS = {'male': '男', 'female': '女', 'any': '不限'}

@app.route('/weibo/drama')
@login_required
def drama_list():
    me_player = me()
    active_dramas = q("""SELECT DISTINCT d.* FROM dramas d JOIN drama_roles r ON r.drama_id = d.id
                         WHERE r.status IN ('casting','shooting') ORDER BY d.open_ts DESC""")
    my_applications = {}
    busy = False
    if me_player:
        rows = q("SELECT id, role_id FROM role_applications WHERE player_id=?", (me_player['id'],))
        my_applications = {r['role_id']: r['id'] for r in rows}
        busy = is_actor_busy(me_player['id'])

    drama_views = []
    for d in active_dramas:
        roles = q("SELECT * FROM drama_roles WHERE drama_id=? ORDER BY id", (d['id'],))
        role_views = []
        for r in roles:
            eligible, reason = True, ''
            if me_player:
                if busy:
                    eligible, reason = False, '档期被占满了'
                elif r['gender_requirement'] != 'any' and me_player['gender'] != r['gender_requirement']:
                    eligible, reason = False, '性别不符'
                elif not meets_tier(me_player['popularity'], r['tier_requirement']):
                    eligible, reason = False, '咖位不够'
                elif d['format'] == 'film' and me_player['awards_won'] < FILM_MIN_AWARDS:
                    eligible, reason = False, f'还没拿过奖,接不到电影(至少需要获奖 {FILM_MIN_AWARDS} 次)'
            winner_name = None
            if r['winner_player_id']:
                w = q("SELECT stage_name FROM players WHERE id=?", (r['winner_player_id'],), one=True)
                winner_name = w['stage_name'] if w else None
            role_views.append({'role': dict(r), 'eligible': eligible, 'reason': reason,
                                'applied': r['id'] in my_applications,
                                'application_id': my_applications.get(r['id']),
                                'winner_name': winner_name})
        drama_views.append({'drama': dict(d), 'roles': role_views})

    recent_results = q("""SELECT d.title, r.role_name, r.winner_player_id, a.match_score, r.rating_score
                          FROM role_applications a
                          JOIN drama_roles r ON r.id = a.role_id
                          JOIN dramas d ON d.id = r.drama_id
                          WHERE a.player_id=? AND r.status='aired'
                          ORDER BY a.created_ts DESC LIMIT 10""", (me_player['id'],)) if me_player else []
    my_tier = get_tier(me_player['popularity']) if me_player else None
    return render_template('drama.html', drama_views=drama_views, my_tier=my_tier,
                            recent_results=recent_results, me_id=me_player['id'] if me_player else None,
                            gender_labels=GENDER_LABELS)

@app.route('/weibo/drama/apply', methods=['POST'])
@login_required
def drama_apply():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    role_id = request.form.get('role_id', '')
    ok, msg = apply_for_role(me_player['id'], role_id)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('drama_list'))

@app.route('/weibo/drama/act/<int:role_id>')
@login_required
def drama_act(role_id):
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    role = q("""SELECT r.*, d.title FROM drama_roles r JOIN dramas d ON d.id = r.drama_id
               WHERE r.id=?""", (role_id,), one=True)
    if not role or role['winner_player_id'] != me_player['id'] or role['status'] != 'shooting':
        flash('这个角色现在不能操作', 'error')
        return redirect(url_for('drama_list'))
    challenges = q("SELECT * FROM acting_challenges WHERE role_id=? ORDER BY round_no", (role_id,))
    return render_template('drama_act.html', role=role, challenges=challenges)

@app.route('/weibo/drama/act/<int:challenge_id>/answer', methods=['POST'])
@login_required
def drama_act_answer(challenge_id):
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    choice = request.form.get('choice', '')
    challenge = q("SELECT role_id FROM acting_challenges WHERE id=?", (challenge_id,), one=True)
    ok, msg = answer_acting_challenge(me_player['id'], challenge_id, choice)
    flash(msg, 'ok' if ok else 'error')
    if challenge:
        return redirect(url_for('drama_act', role_id=challenge['role_id']))
    return redirect(url_for('drama_list'))

@app.route('/weibo/drama/audition/<int:application_id>')
@login_required
def drama_audition(application_id):
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    application = q("""SELECT a.*, r.role_name, r.status as role_status, d.title FROM role_applications a
                       JOIN drama_roles r ON r.id = a.role_id JOIN dramas d ON d.id = r.drama_id
                       WHERE a.id=?""", (application_id,), one=True)
    if not application or application['player_id'] != me_player['id']:
        flash('这个试镜现在不能操作', 'error')
        return redirect(url_for('drama_list'))
    challenges = q("SELECT * FROM audition_challenges WHERE application_id=? ORDER BY round_no", (application_id,))
    return render_template('drama_audition.html', application=application, challenges=challenges)

@app.route('/weibo/drama/audition/<int:challenge_id>/answer', methods=['POST'])
@login_required
def drama_audition_answer(challenge_id):
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    choice = request.form.get('choice', '')
    challenge = q("SELECT application_id FROM audition_challenges WHERE id=?", (challenge_id,), one=True)
    ok, msg = answer_audition_challenge(me_player['id'], challenge_id, choice)
    flash(msg, 'ok' if ok else 'error')
    if challenge:
        return redirect(url_for('drama_audition', application_id=challenge['application_id']))
    return redirect(url_for('drama_list'))

# ── 代言/品牌合作 ───────────────────────────────────────────────────────────────

@app.route('/weibo/brand')
@login_required
def brand_list():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    open_brands = q("SELECT * FROM brands WHERE status='open' ORDER BY created_ts DESC")
    my_applications = {r['brand_id'] for r in q(
        "SELECT brand_id FROM brand_applications WHERE player_id=?", (me_player['id'],))}
    brand_views = []
    for b in open_brands:
        ok, reason = eligible_for_brand(me_player, b)
        brand_views.append({'brand': dict(b), 'eligible': ok, 'reason': reason,
                             'applied': b['id'] in my_applications})
    signed = q("""SELECT * FROM brands WHERE status='signed' AND signed_player_id=?""", (me_player['id'],))
    return render_template('brand.html', brand_views=brand_views, signed=signed,
                            reputation=me_player['endorsement_reputation'])

@app.route('/weibo/brand/apply', methods=['POST'])
@login_required
def brand_apply():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    brand_id = request.form.get('brand_id', '')
    ok, msg = apply_for_brand(me_player['id'], brand_id)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('brand_list'))

# ── 品牌代言人(全局限量,支持挑战顶替) ──────────────────────────────────────────

@app.route('/weibo/ambassador')
@login_required
def ambassador_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    ambassadors = q("SELECT * FROM brand_ambassadors ORDER BY id")
    my_score = ambassador_match_score(me_player)
    views = []
    for a in ambassadors:
        holder = None
        holder_score = None
        if a['current_player_id']:
            holder = q("SELECT id, stage_name FROM players WHERE id=?", (a['current_player_id'],), one=True)
            holder_row = q("SELECT * FROM players WHERE id=?", (a['current_player_id'],), one=True)
            holder_score = ambassador_match_score(holder_row) if holder_row else 0
        eligible, reason = eligible_for_ambassador(me_player, a)
        views.append({'ambassador': dict(a), 'holder': holder, 'holder_score': holder_score,
                      'is_me': a['current_player_id'] == me_player['id'],
                      'eligible': eligible, 'reason': reason})
    return render_template('ambassador.html', views=views, my_score=my_score, cost=AMBASSADOR_COST)

@app.route('/weibo/ambassador/apply', methods=['POST'])
@login_required
def ambassador_apply():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    ambassador_id = request.form.get('ambassador_id', '')
    ok, msg = apply_for_ambassador(me_player['id'], int(ambassador_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('ambassador_page'))

# ── 颁奖典礼 ────────────────────────────────────────────────────────────────────

@app.route('/weibo/awards')
@login_required
def awards_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    tier_order = ['minor', 'popularity', 'major', 'festival', 'top']
    seasons = q("SELECT * FROM award_seasons WHERE status='campaigning'")
    seasons = sorted(seasons, key=lambda s: tier_order.index(s['tier']) if s['tier'] in tier_order else 0)
    season_views = []
    for season in seasons:
        show = AWARD_SHOWS.get(season['show_key'], {})
        eligible, reason = True, ''
        if show.get('min_tier') and not meets_tier(me_player['popularity'], show['min_tier']):
            eligible, reason = False, f"咖位要到 {show['min_tier']} 以上"
        elif me_player['awards_won'] < show.get('min_awards', 0):
            eligible, reason = False, f"还差 {show['min_awards'] - me_player['awards_won']} 个奖才够格"
        elif show.get('require_film') and not has_film_credit(me_player['id']):
            eligible, reason = False, '还没有电影作品,进不去这场'
        elif show.get('min_rating') is not None and not best_qualifying_work(
                me_player['id'], show.get('require_film', False), show['min_rating'], now_ts() - MONTH_SECONDS * 12):
            eligible, reason = False, '这一年还没有够格的作品,进不去这场'
        categories = q("SELECT * FROM award_categories WHERE season_id=?", (season['id'],))
        category_views = []
        for cat in categories:
            nominees = q("""SELECT n.*, p.stage_name FROM award_nominees n JOIN players p ON p.id = n.player_id
                            WHERE n.category_id=? ORDER BY n.vote_score DESC""", (cat['id'],))
            is_nominated = any(n['player_id'] == me_player['id'] for n in nominees)
            category_views.append({'category': dict(cat), 'nominees': nominees, 'is_nominated': is_nominated})
        season_views.append({'season': dict(season), 'tier_label': AWARD_TIER_LABELS.get(season['tier'], season['tier']),
                              'eligible': eligible, 'reason': reason, 'category_views': category_views})
    recent_wins = q("""SELECT c.category_name, s.season_name FROM award_nominees n
                       JOIN award_categories c ON c.id = n.category_id
                       JOIN award_seasons s ON s.id = c.season_id
                       WHERE n.player_id=? AND n.won=1 ORDER BY s.id DESC LIMIT 10""", (me_player['id'],))
    return render_template('awards.html', season_views=season_views,
                            recent_wins=recent_wins, campaign_cost=CAMPAIGN_BOOST_COST, bribe_cost=BRIBE_COST,
                            me_id=me_player['id'])

@app.route('/weibo/awards/campaign', methods=['POST'])
@login_required
def awards_campaign():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    category_id = request.form.get('category_id', '')
    ok, msg = campaign_boost(me_player['id'], category_id)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('awards_page'))

@app.route('/weibo/awards/bribe', methods=['POST'])
@login_required
def awards_bribe():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    category_id = request.form.get('category_id', '')
    ok, msg = bribe_judge(me_player['id'], category_id)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('awards_page'))

# ── 歌手线:发新歌 / 演唱会 ────────────────────────────────────────────────────────

SONG_OUTCOME_LABELS = {'hit': '新歌大爆,路人缘和粉丝都涨了', 'ok': '新歌反响平平',
                       'flop': '新歌翻车了,被群嘲上了热搜'}
CONCERT_OUTCOME_LABELS = {'success': '演唱会圆满落幕', 'incident': '演唱会出了舞台事故'}

@app.route('/weibo/release_song', methods=['POST'])
@login_required
def weibo_release_song():
    player = me()
    if not player:
        return redirect(url_for('login'))
    outcome, err = release_song(player)
    if err:
        flash(err, 'error')
    else:
        flash(SONG_OUTCOME_LABELS.get(outcome, '新歌发布了'), 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/concert', methods=['POST'])
@login_required
def weibo_concert():
    player = me()
    if not player:
        return redirect(url_for('login'))
    outcome, err = hold_concert(player)
    if err:
        flash(err, 'error')
    else:
        flash(CONCERT_OUTCOME_LABELS.get(outcome, '演唱会办完了'), 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/concert/prepare', methods=['GET', 'POST'])
@login_required
def weibo_concert_prepare():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if request.method == 'POST':
        choices = [request.form.get(f'choice_{i}', '') for i in (1, 2, 3)]
        outcome, err = hold_concert(player, choices)
        if err:
            flash(err, 'error')
        else:
            flash(CONCERT_OUTCOME_LABELS.get(outcome, '演唱会办完了'), 'ok')
        return redirect(url_for('weibo'))
    return render_template('concert_prepare.html')

SHOOT_OUTCOME_LABELS = {'hit': '这组硬照拍得很出彩', 'ok': '拍摄顺利完成', 'flop': '拍摄现场出了点小状况'}

@app.route('/weibo/commercial_shoot', methods=['POST'])
@login_required
def weibo_commercial_shoot():
    player = me()
    if not player:
        return redirect(url_for('login'))
    outcome, err = do_commercial_shoot(player)
    if err:
        flash(err, 'error')
    else:
        flash(SHOOT_OUTCOME_LABELS.get(outcome, '拍摄完成了'), 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/magazine', methods=['POST'])
@login_required
def weibo_magazine():
    player = me()
    if not player:
        return redirect(url_for('login'))
    outcome, err = do_magazine(player)
    if err:
        flash(err, 'error')
    else:
        flash(SHOOT_OUTCOME_LABELS.get(outcome, '专访完成了'), 'ok')
    return redirect(url_for('weibo'))

# ── 奢侈品抽卡 ───────────────────────────────────────────────────────────────────

@app.route('/weibo/luxury', methods=['GET', 'POST'])
@login_required
def luxury_page():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if request.method == 'POST':
        result, err = draw_luxury_item(player)
        if err:
            flash(err, 'error')
        else:
            label = LUXURY_RARITY_LABELS.get(result['rarity'], result['rarity'])
            msg = f"抽到了【{label}】{result['item_name']}"
            if result['backfire']:
                msg += ",不过晒图被吐槽凡尔赛过头了"
            flash(msg, 'ok')
        return redirect(url_for('luxury_page'))
    collection = q("SELECT * FROM luxury_items WHERE player_id=? ORDER BY created_ts DESC LIMIT 30",
                   (player['id'],))
    return render_template('luxury.html', collection=collection, cost=LUXURY_GACHA_COST,
                            tier_requirement=LUXURY_GACHA_TIER_REQUIREMENT, my_tier=get_tier(player['popularity']),
                            rarity_labels=LUXURY_RARITY_LABELS)

@app.route('/backpack')
@login_required
def backpack_page():
    player = me()
    if not player:
        return redirect(url_for('login'))
    gifts = q("SELECT * FROM fan_gifts WHERE player_id=? ORDER BY created_ts DESC LIMIT 50", (player['id'],))
    return render_template('backpack.html', gifts=gifts, rarity_labels=FAN_GIFT_RARITY_LABELS)

@app.route('/lifestyle', methods=['GET', 'POST'])
@login_required
def lifestyle_page():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if request.method == 'POST':
        item_key = request.form.get('item_key', '')
        ok, msg = buy_lifestyle_asset(player['id'], item_key)
        flash(msg, 'ok' if ok else 'error')
        return redirect(url_for('lifestyle_page'))
    assets = q("SELECT * FROM lifestyle_assets WHERE player_id=? ORDER BY created_ts DESC", (player['id'],))
    return render_template('lifestyle.html', catalog=LIFESTYLE_CATALOG, assets=assets, cash=player['cash'])

# ── 综艺 ───────────────────────────────────────────────────────────────────────

VARIETY_OUTCOME_LABELS = {'consistent': '表现和人设很契合,人设更稳了', 'unexpected_charm': '意外的反差萌圈了一波粉',
                          'conflict': '真实性格露出来了一点,人设有点崩'}

@app.route('/weibo/variety', methods=['POST'])
@login_required
def weibo_variety():
    player = me()
    if not player:
        return redirect(url_for('login'))
    outcome, err = do_variety(player)
    if err:
        flash(err, 'error')
    else:
        flash(VARIETY_OUTCOME_LABELS.get(outcome, '综艺录完了'), 'ok')
    return redirect(url_for('weibo'))

@app.route('/weibo/variety/prepare', methods=['GET', 'POST'])
@login_required
def weibo_variety_prepare():
    player = me()
    if not player:
        return redirect(url_for('login'))
    if request.method == 'POST':
        choices = [request.form.get(f'choice_{i}', '') for i in (1, 2)]
        outcome, err = do_variety(player, choices)
        if err:
            flash(err, 'error')
        else:
            flash(VARIETY_OUTCOME_LABELS.get(outcome, '综艺录完了'), 'ok')
        return redirect(url_for('weibo'))
    return render_template('variety_prepare.html')

# ── 联合营业 ────────────────────────────────────────────────────────────────────

@app.route('/weibo/collab', methods=['GET', 'POST'])
@login_required
def collab_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    if request.method == 'POST':
        target_id = request.form.get('target_id', '')
        topic = request.form.get('topic', '') or None
        ok, msg = send_invite(me_player['id'], int(target_id), 'collab', topic=topic)
        flash(msg, 'ok' if ok else 'error')
        return redirect(url_for('collab_page'))
    candidates = q("""SELECT id, stage_name, is_npc, agency_id FROM players
                      WHERE id != ? ORDER BY RANDOM() LIMIT 20""", (me_player['id'],))
    pending_invites = q("""SELECT si.*, p.stage_name as from_name FROM social_invites si
                           JOIN players p ON p.id = si.from_player_id
                           WHERE si.to_player_id=? AND si.invite_type='collab' AND si.status='pending'""",
                        (me_player['id'],))
    recent = q("""SELECT c.*, pa.stage_name as a_name, pb.stage_name as b_name FROM collaborations c
                 JOIN players pa ON pa.id = c.player_a_id JOIN players pb ON pb.id = c.player_b_id
                 WHERE c.player_a_id=? OR c.player_b_id=? ORDER BY c.created_ts DESC LIMIT 10""",
              (me_player['id'], me_player['id']))
    return render_template('collab.html', candidates=candidates, pending_invites=pending_invites, recent=recent,
                            vlog_topics=VLOG_TOPICS)

# ── 好友/私信(必须合作过才能加好友,好感度够了才能约会) ──────────────────────────────

@app.route('/messages')
@login_required
def messages_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    friend_rows = q("""SELECT * FROM friendships WHERE player_a_id=? OR player_b_id=?
                       ORDER BY affinity DESC""", (me_player['id'], me_player['id']))
    friends = []
    for f in friend_rows:
        friend_id = f['player_b_id'] if f['player_a_id'] == me_player['id'] else f['player_a_id']
        friend = q("SELECT id, stage_name, is_npc FROM players WHERE id=?", (friend_id,), one=True)
        if not friend:
            continue
        thread = q("""SELECT * FROM private_messages WHERE (from_player_id=? AND to_player_id=?)
                     OR (from_player_id=? AND to_player_id=?) ORDER BY created_ts DESC LIMIT 10""",
                   (me_player['id'], friend_id, friend_id, me_player['id']))
        friends.append({'friend': friend, 'affinity': f['affinity'],
                         'can_date': f['affinity'] >= FRIEND_AFFINITY_DATING_THRESHOLD,
                         'thread': list(reversed(thread))})
    fan_letters = q("SELECT * FROM fan_letters WHERE player_id=? AND replied=0 ORDER BY created_ts DESC",
                    (me_player['id'],))
    run("UPDATE private_messages SET read=1 WHERE to_player_id=? AND read=0", (me_player['id'],))
    return render_template('messages.html', friends=friends, me_id=me_player['id'],
                            dating_threshold=FRIEND_AFFINITY_DATING_THRESHOLD, fan_letters=fan_letters)

@app.route('/messages/send', methods=['POST'])
@login_required
def messages_send():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    friend_id = request.form.get('friend_id', '')
    content = request.form.get('content', '').strip()
    if not content:
        flash('内容不能为空', 'error')
        return redirect(url_for('messages_page'))
    ok, msg = send_message(me_player['id'], int(friend_id), content)
    if not ok:
        flash(msg, 'error')
    return redirect(url_for('messages_page'))

@app.route('/messages/fan_letter/reply', methods=['POST'])
@login_required
def fan_letter_reply():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    letter_id = request.form.get('letter_id', '')
    ok, msg = reply_fan_letter(me_player['id'], int(letter_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('messages_page'))

@app.route('/messages/fan_letter/dismiss', methods=['POST'])
@login_required
def fan_letter_dismiss():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    letter_id = request.form.get('letter_id', '')
    ok, msg = dismiss_fan_letter(me_player['id'], int(letter_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('messages_page'))

@app.route('/messages/fan_letter/clapback', methods=['POST'])
@login_required
def fan_letter_clapback():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    letter_id = request.form.get('letter_id', '')
    ok, msg = clapback_hater_letter(me_player['id'], int(letter_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('messages_page'))

# ── 恋爱曝光 ────────────────────────────────────────────────────────────────────

@app.route('/weibo/dating', methods=['GET'])
@login_required
def dating_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    rows = q("""SELECT * FROM relationships WHERE (player_a_id=? OR player_b_id=?)
               AND status IN ('secret','exposed_pending','together') ORDER BY started_ts DESC LIMIT 1""",
             (me_player['id'], me_player['id']))
    my_rel = dict(rows[0]) if rows else None
    partner = None
    children = []
    if my_rel:
        partner_id = my_rel['player_b_id'] if my_rel['player_a_id'] == me_player['id'] else my_rel['player_a_id']
        partner = q("SELECT stage_name, is_npc FROM players WHERE id=?", (partner_id,), one=True)
        children = q("SELECT * FROM children WHERE relationship_id=? ORDER BY born_ts", (my_rel['id'],))
    friend_rows = q("""SELECT * FROM friendships WHERE player_a_id=? OR player_b_id=?
                      ORDER BY affinity DESC""", (me_player['id'], me_player['id']))
    candidates = []
    for f in friend_rows:
        friend_id = f['player_b_id'] if f['player_a_id'] == me_player['id'] else f['player_a_id']
        friend = q("SELECT id, stage_name, is_npc FROM players WHERE id=?", (friend_id,), one=True)
        if friend:
            candidates.append({'id': friend['id'], 'stage_name': friend['stage_name'],
                                'is_npc': friend['is_npc'], 'affinity': f['affinity']})
    pending_invites = q("""SELECT si.*, p.stage_name as from_name FROM social_invites si
                           JOIN players p ON p.id = si.from_player_id
                           WHERE si.to_player_id=? AND si.invite_type='dating' AND si.status='pending'""",
                        (me_player['id'],))
    return render_template('dating.html', my_rel=my_rel, partner=partner, candidates=candidates, children=children,
                            pending_invites=pending_invites, dating_threshold=FRIEND_AFFINITY_DATING_THRESHOLD,
                            pregnancy_months=PREGNANCY_TERM_MONTHS)

@app.route('/weibo/dating/start', methods=['POST'])
@login_required
def dating_start():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    target_id = request.form.get('target_id', '')
    ok, msg = send_invite(me_player['id'], int(target_id), 'dating')
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('dating_page'))

@app.route('/weibo/dating/respond', methods=['POST'])
@login_required
def dating_respond():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    choice = request.form.get('choice', '')
    rel_id = request.form.get('relationship_id', '')
    content = request.form.get('content', '').strip()
    apply_exposure_consequence(rel_id, choice, responder_id=me_player['id'], custom_content=content)
    flash('已经回应了', 'ok')
    return redirect(url_for('dating_page'))

@app.route('/weibo/dating/pregnancy', methods=['POST'])
@login_required
def dating_pregnancy():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    rel_id = request.form.get('relationship_id', '')
    choice = request.form.get('choice', '')
    ok, msg = decide_pregnancy(me_player['id'], int(rel_id), choice)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('dating_page'))

@app.route('/weibo/dating/announce_marriage', methods=['POST'])
@login_required
def dating_announce_marriage():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    rel_id = request.form.get('relationship_id', '')
    ok, msg = announce_marriage(me_player['id'], int(rel_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('dating_page'))

@app.route('/weibo/dating/name_child', methods=['POST'])
@login_required
def dating_name_child():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    child_id = request.form.get('child_id', '')
    name = request.form.get('name', '')
    ok, msg = name_child(me_player['id'], int(child_id), name)
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('dating_page'))

@app.route('/weibo/dating/reveal_child', methods=['POST'])
@login_required
def dating_reveal_child():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    child_id = request.form.get('child_id', '')
    ok, msg = reveal_child(me_player['id'], int(child_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('dating_page'))

@app.route('/weibo/invites/respond', methods=['POST'])
@login_required
def invite_respond():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    invite_id = request.form.get('invite_id', '')
    accept = request.form.get('accept', '') == '1'
    ok, msg = respond_invite(me_player['id'], int(invite_id), accept)
    flash(msg, 'ok' if ok else 'error')
    return redirect(request.referrer or url_for('weibo'))

# ── 粉丝超话 ────────────────────────────────────────────────────────────────────

@app.route('/super_topic', methods=['GET'])
@login_required
def super_topic_page():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    view_id = request.args.get('player_id', me_player['id'], type=int)
    host = q("SELECT id, stage_name, fan_club_name, fan_club_color FROM players WHERE id=?", (view_id,), one=True)
    if not host:
        host = me_player
        view_id = me_player['id']
    posts = q("SELECT * FROM super_topic_posts WHERE player_id=? ORDER BY created_ts DESC LIMIT 30", (view_id,))
    return render_template('super_topic.html', host=host, posts=posts,
                            is_own=(view_id == me_player['id']), me_player=me_player)

@app.route('/super_topic/checkin', methods=['POST'])
@login_required
def super_topic_checkin():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    content = request.form.get('content', '').strip() or f"{me_player['stage_name']}超话打卡"
    gain, err = do_super_topic_checkin(me_player, content)
    if err:
        flash(err, 'error')
    return redirect(url_for('super_topic_page'))

# ── 排行榜 ─────────────────────────────────────────────────────────────────────

@app.route('/leaderboard')
@login_required
def leaderboard():
    rows = q("""SELECT id, stage_name, popularity, fans_count, scandal_value, is_npc
                FROM players ORDER BY popularity DESC LIMIT 50""")
    loyalty_rows = q("""SELECT id, stage_name, core_fan_loyalty, is_npc
                        FROM players ORDER BY core_fan_loyalty DESC LIMIT 50""")
    me_player = me()
    return render_template('leaderboard.html', rows=rows, loyalty_rows=loyalty_rows,
                            me_id=me_player['id'] if me_player else None)

# ── 炒CP排行榜 ──────────────────────────────────────────────────────────────────

@app.route('/cp')
@login_required
def cp_page():
    rows = q("""SELECT cp.id, cp.heat, pa.stage_name as a_name, pb.stage_name as b_name
               FROM cp_pairs cp
               JOIN players pa ON pa.id = cp.player_a_id
               JOIN players pb ON pb.id = cp.player_b_id
               ORDER BY cp.heat DESC LIMIT 30""")
    return render_template('cp.html', rows=rows, boost_cost=CP_BOOST_COST, smear_cost=CP_SMEAR_COST)

@app.route('/cp/boost', methods=['POST'])
@login_required
def cp_boost():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    cp_id = request.form.get('cp_id', '')
    ok, msg = boost_cp(me_player['id'], int(cp_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('cp_page'))

@app.route('/cp/smear', methods=['POST'])
@login_required
def cp_smear():
    me_player = me()
    if not me_player:
        return redirect(url_for('login'))
    cp_id = request.form.get('cp_id', '')
    ok, msg = smear_cp(me_player['id'], int(cp_id))
    flash(msg, 'ok' if ok else 'error')
    return redirect(url_for('cp_page'))

# ── 热搜榜 ─────────────────────────────────────────────────────────────────────

@app.route('/trending')
@login_required
def trending():
    latest_tick = q("SELECT MAX(tick_id) t FROM trending_topics", one=True)['t']
    if latest_tick is None:
        topics = []
    else:
        topics = q("SELECT * FROM trending_topics WHERE tick_id=? ORDER BY rank LIMIT 20", (latest_tick,))
    return render_template('trending.html', topics=topics)

if __name__ == '__main__':
    init_db()
