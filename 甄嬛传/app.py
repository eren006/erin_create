"""甄嬛传·紫禁城 —— 多人宫斗网页游戏

玩家以秀女身份入宫，经殿选后在后宫里争宠、结盟、使计。
皇帝是系统 NPC，每晚固定时刻（SETTLE_HOUR）统一结算：阴谋 → 翻牌子 → 生产 → 晋封 → 月例。
"""
import os, json, random, math, time, threading
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session as S, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "zhenhuan_dev_secret")
app.permanent_session_lifetime = timedelta(days=30)

DB_PATH       = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "zhenhuan.db"))
ADMIN_USER    = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS    = os.environ.get("ADMIN_PASSWORD", "zhenhuan_admin_888")
SETTLE_HOUR   = int(os.environ.get("SETTLE_HOUR", 21))
SETTLE_MINUTE = int(os.environ.get("SETTLE_MINUTE", 0))
TZ            = timezone(timedelta(hours=8))
now_ts        = lambda: int(time.time())

# ── 数据库 ─────────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH, timeout=15)
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
    if not getattr(g, "atomic", False): db.commit()
    return cur

def atomic(fn):
    """资源扣除和结算要么全部完成，要么全部回滚；多进程由 SQLite 写锁保护。"""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if getattr(g, 'atomic', False):
            return fn(*args, **kwargs)
        with settle_lock:
            db = get_db()
            db.execute('BEGIN IMMEDIATE')
            g.atomic = True
            try:
                result = fn(*args, **kwargs)
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise
            finally:
                g.atomic = False
    return wrapped

# ── 位分 ───────────────────────────────────────────────────────────────────────

RANK_NAMES = ['秀女', '官女子', '答应', '常在', '贵人', '嫔', '妃', '贵妃', '皇贵妃', '皇后']
PROMOTE_FAVOR  = {2: 40, 3: 90, 4: 170, 5: 300, 6: 480, 7: 720, 8: 1000}   # 晋到该位分所需圣宠
PROMOTE_VIRTUE = {2: 0, 3: 10, 4: 20, 5: 35, 6: 50, 7: 60, 8: 70}          # 晋到该位分所需德行
RANK_SLOTS     = {5: 6, 6: 4, 7: 2, 8: 1, 9: 1}                           # 嫔以上有名额，含 NPC
MIN_DAYS_AT_RANK = 2
STIPEND = {1: 5, 2: 10, 3: 15, 4: 25, 5: 40, 6: 60, 7: 90, 8: 130, 9: 200}  # 每日月例银
PLAYER_MAX_RANK = 8   # 玩家最高到皇贵妃，皇后位由 NPC 占着

FAVOR_DECAY = 0.04    # 每晚圣宠自然流失比例
ENERGY_MAX = 5
PREGNANCY_DAYS = 2      # 诊出喜脉后，再经过两次结算分娩
FERTILE_BEFORE_AGE = 45 # 四十五岁起不再新怀孕
LETHAL_COOLDOWN = 7     # 同一账号两次毒害至少隔 7 天，死后重建也不重置
NEWCOMER_LETHAL_SHIELD = 3   # 入宫前 3 天不能被毒害
RESCUE_PROTECT_DAYS = 3      # 中毒获救后 3 天不能再被毒害
TREAT_COST = 50
POISON_SURVIVE = {0: 0.35, 1: 0.90}   # 没请太医 / 请了太医
CONFINE_DAYS = 2
COLD_DAYS = 5

TITLE_POOL = list('莞惠安祺瑾婉容贞淳柔懿宁怡颖璟瑶玥韵馨娴淑嘉恬澜宸昭徽祥和敏')

PLAYER_PALACES = ['碎玉轩', '延禧宫', '咸福宫', '永寿宫', '钟粹宫', '储秀宫',
                  '永和宫', '景阳宫', '长春宫', '启祥宫']

ARTS = ['琴', '棋', '书', '画', '诗', '舞', '女红']
ART_MASTERY = 8       # 修习满这么多次算精通

FAVOR_WORDS = [(600, '圣眷正浓'), (250, '颇得圣心'), (80, '偶承恩泽'), (1, '圣恩尚浅'), (-1, '未曾承宠')]

def favor_word(f):
    for th, w in FAVOR_WORDS:
        if f >= th: return w
    return '未曾承宠'

def display_name(c):
    if c is None: return '（无）'
    if c['status'] == 'dead':
        return f"故·{c['title'] or c['surname']}{RANK_NAMES[c['rank']]}"
    if c['status'] == 'cold':
        return f"{c['surname']}氏"
    r = c['rank']
    if r == 0: return f"秀女{c['surname']}{c['given']}"
    if r == 9: return '皇后'
    return f"{c['title'] or c['surname']}{RANK_NAMES[r]}"

def full_name(c):
    return f"{c['surname']}{c['given']}"

# ── 出身 / 性格 ────────────────────────────────────────────────────────────────

FAMILIES = {
    'dali':    dict(name='大理寺少卿之女', desc='父亲断案清正，你自小读书明理，也学会了看人。',
                    mods=dict(talent=8, virtue=4), silver=150, dx=5),
    'jizhou':  dict(name='济州协领之女', desc='满军旗出身，端方持重，是太后会喜欢的那种姑娘。',
                    mods=dict(virtue=10, appearance=2), silver=200, dx=8),
    'songyang':dict(name='松阳县丞之女', desc='家世寒微，入宫的衣裳都是借的。你比谁都清楚，自己只能靠自己。',
                    mods=dict(talent=5, scheme=10), silver=40, dx=-5),
    'merchant':dict(name='江南富商之女', desc='银子从来不缺，缺的是一个体面出身。',
                    mods=dict(virtue=-5, appearance=3), silver=420, dx=0),
    'general': dict(name='镇边将门之女', desc='父兄在西北打仗，你入宫时身后是整个家族的指望。',
                    mods=dict(health=15, scheme=3), silver=250, dx=6),
    'hanlin':  dict(name='翰林学士之女', desc='家中藏书三千卷，才情是真的，身子骨弱也是真的。',
                    mods=dict(talent=12, health=-8), silver=120, dx=4),
    'physician':dict(name='太医院御医之女', desc='父亲见惯了宫里的生死，教你的第一件事是：入口的东西要当心。',
                    mods=dict(health=10, scheme=5), silver=150, dx=2),
    'manchu':  dict(name='满洲大姓旁支', desc='姓氏够响亮，族里却不止你一个指望。',
                    mods=dict(virtue=3, appearance=4, scheme=-3), silver=260, dx=10),
}

PERSONALITIES = {
    'gentle':  dict(name='温婉', mods=dict(virtue=6), desc='皇上与你相处舒心，圣宠获得 +10%'),
    'clever':  dict(name='聪慧', mods=dict(talent=4, scheme=4), desc='修习才艺每次多长 1 点'),
    'charming':dict(name='娇媚', mods=dict(appearance=8, virtue=-4), desc='翻牌子时更容易被选中 +15%'),
    'deep':    dict(name='城府', mods=dict(scheme=8, virtue=-2), desc='使计成功率 +5%'),
    'dignified':dict(name='端庄', mods=dict(virtue=4, appearance=2), desc='请安多得德行，被人算计时成功率 -5%'),
    'naive':   dict(name='天真', mods=dict(virtue=8, scheme=-6), desc='被人害了，皇上反倒怜惜：圣宠损失减半'),
}

STAT_KEYS = ['appearance', 'talent', 'scheme', 'virtue']
STAT_NAMES = dict(appearance='容貌', talent='才艺', scheme='心计', virtue='德行', health='体质')
STAT_BASE = dict(appearance=40, talent=30, scheme=30, virtue=40, health=70)
FREE_POINTS = 12
POINT_CAP_PER_STAT = 10

def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(round(v))))

# ── 秘密 ───────────────────────────────────────────────────────────────────────

SECRETS = {
    'none':      dict(name='身家清白', weight=45, penalty='', confess=''),
    'lover':     dict(name='入宫前曾有意中人', weight=15,
                      penalty='圣宠折半，德行 -15', confess='圣宠 -20%'),
    'fake':      dict(name='冒认了出身', weight=12,
                      penalty='降一级位分', confess='圣宠 -30%'),
    'book':      dict(name='私藏禁书', weight=10,
                      penalty='禁足 3 天', confess='禁足 1 天'),
    'scar':      dict(name='脸上旧伤一直用脂粉遮着', weight=13,
                      penalty='容貌 -10，圣宠 -20%', confess='容貌 -5'),
    'physician': dict(name='与太医过从甚密', weight=5,
                      penalty='打入冷宫', confess='禁足 3 天'),
}

def roll_secret():
    keys = list(SECRETS)
    return random.choices(keys, weights=[SECRETS[k]['weight'] for k in keys])[0]

# ── 物品 ───────────────────────────────────────────────────────────────────────

ITEMS = {
    'renshen':  dict(name='老山参', price=60, usable=True, desc='体质 +15'),
    'shuhen':   dict(name='舒痕胶', price=150, usable=True, desc='容貌 +3（每天限用一次）'),
    'shujin':   dict(name='蜀锦新衣', price=80, usable=True, desc='今晚翻牌子的机会大增'),
    'qinpu':    dict(name='前朝琴谱', price=50, usable=True, desc='才艺 +3'),
    'antai':    dict(name='安胎药', price=100, usable=False, desc='放在身边：有孕时若遭人下药，可保住胎儿一次'),
    'ruyi':     dict(name='玉如意', price=120, usable=False, desc='赠给别人，对方好感 +15'),
    'shexiang': dict(name='麝香', price=200, usable=False, black=True, desc='使计「暗下麝香」必需。私藏被查到可不好说'),
}

# ── 行动 ───────────────────────────────────────────────────────────────────────

ACTIONS = {
    'greet':   dict(name='景仁宫请安', energy=1, silver=0, daily=1, when={'normal'}, sick_block=True,
                    desc='给皇后请安，德行 +1。偶尔会碰上华妃发难'),
    'study':   dict(name='修习才艺', energy=1, silver=0, daily=3, when={'normal', 'confined'},
                    desc='才艺提升；某门修满 8 次即精通'),
    'groom':   dict(name='梳妆保养', energy=1, silver=15, daily=2, when={'normal', 'confined'},
                    desc='容貌 +1~2，体质 +3'),
    'garden':  dict(name='去御花园走走', energy=1, silver=0, daily=2, when={'normal'}, sick_block=True,
                    desc='说不定能遇见皇上，也说不定撞见不该看的'),
    'seek':    dict(name='送汤羹去养心殿', energy=1, silver=20, daily=2, when={'normal'}, sick_block=True,
                    desc='看皇上心情，圣宠上涨，今晚翻牌机会增加'),
    'rest':    dict(name='静养', energy=1, silver=0, daily=3, when={'normal', 'confined', 'cold'},
                    desc='体质 +8'),
    'reflect': dict(name='闭门自省', energy=1, silver=0, daily=2, when={'confined', 'cold'},
                    desc='德行 +2；在冷宫里还有一线机会让皇上想起你'),
    'eyes':    dict(name='安插眼线', energy=0, silver=100, daily=1, when={'normal', 'confined'},
                    desc='五天内更难被算计，被害时能知道是谁'),
    'visit':   dict(name='串门', energy=1, silver=0, daily=3, when={'normal'}, sick_block=True, target=True,
                    desc='双方好感 +6~10'),
    'spy':     dict(name='打探底细', energy=1, silver=30, daily=1, when={'normal'}, target=True,
                    desc='有机会探到对方的秘密'),
    'plead':   dict(name='向皇上求情', energy=1, silver=50, daily=1, when={'normal'}, target=True,
                    desc='为禁足或冷宫中的姐妹求情，缩短日子'),
}

# ── 阴谋 ───────────────────────────────────────────────────────────────────────

INTRIGUES = {
    'lethal': dict(name='毒害', silver=500, energy=3, min_rank=5, base=0.35, npc_ok=False,
                   desc='成：对方中毒，下一次结算前请了太医九成能活，没请只有三成五。败露：自己打入冷宫。每个账号 7 天一次'),
    'rumor':  dict(name='散布流言', silver=30, energy=2, min_rank=1, base=0.55, npc_ok=True,
                   desc='成：对方圣宠 -15%，德行 -3。败露：自己德行 -5，圣宠 -10%'),
    'steal':  dict(name='截宠', silver=60, energy=2, min_rank=1, base=0.50, npc_ok=True,
                   desc='若今晚翻的是对方的牌子，由你顶上。败露：圣宠 -15%，禁足 1 天'),
    'frame':  dict(name='栽赃陷害', silver=100, energy=2, min_rank=2, base=0.45, npc_ok=True,
                   desc='成：对方禁足 2 天，圣宠 -20%。败露：自己禁足 2 天'),
    'poison': dict(name='暗下麝香', silver=0, item='shexiang', energy=2, min_rank=3, base=0.45, npc_ok=False,
                   desc='成：对方体质 -30，有孕则小产。败露：自己降一级并禁足 3 天'),
    'expose': dict(name='告发秘密', silver=50, energy=2, min_rank=1, base=0.70, npc_ok=False,
                   desc='需先探到对方的秘密。成：按秘密处罚对方。皇上不信：自己德行 -8，圣宠 -15%'),
    'witch':  dict(name='构陷巫蛊', silver=300, energy=3, min_rank=4, base=0.35, npc_ok=True,
                   desc='成：对方打入冷宫。败露：打入冷宫的是你'),
}
INTRIGUE_TARGET_DAILY_MAX = 2

# ── NPC ────────────────────────────────────────────────────────────────────────

NPCS = [
    dict(npc_key='huanghou', surname='乌拉那拉', given='宜修', title='', rank=9, palace='景仁宫',
         appearance=62, talent=70, scheme=92, virtue=80, health=75, favor=250, aggression=0.35,
         intro='中宫皇后，待人宽和，六宫都说她贤德。'),
    dict(npc_key='huafei', surname='年', given='世兰', title='华', rank=6, palace='翊坤宫',
         appearance=90, talent=55, scheme=70, virtue=30, health=85, favor=420, aggression=0.4,
         intro='宠冠六宫，兄长年羹尧手握重兵。最见不得别人得宠。'),
    dict(npc_key='duanfei', surname='齐', given='月宾', title='端', rank=6, palace='延庆殿',
         appearance=55, talent=60, scheme=65, virtue=75, health=20, favor=40, aggression=0,
         intro='常年卧病，深居简出，却什么都看在眼里。'),
    dict(npc_key='qifei', surname='李', given='静言', title='齐', rank=6, palace='长春宫',
         appearance=58, talent=35, scheme=30, virtue=50, health=70, favor=90, aggression=0.05,
         intro='三阿哥生母，心直口快，常被人当枪使。'),
    dict(npc_key='jingpin', surname='冯', given='若昭', title='敬', rank=5, palace='咸福宫',
         appearance=60, talent=58, scheme=50, virtue=70, health=72, favor=110, aggression=0,
         intro='性子温吞，与人为善，在宫里熬了许多年。'),
    dict(npc_key='lipin', surname='费', given='云烟', title='丽', rank=5, palace='启祥宫',
         appearance=75, talent=40, scheme=40, virtue=35, health=75, favor=170, aggression=0.12,
         intro='华妃跟前的人，嘴快心浅。'),
    dict(npc_key='caoguiren', surname='曹', given='琴默', title='', rank=4, palace='启祥宫',
         appearance=62, talent=55, scheme=80, virtue=45, health=65, favor=150, aggression=0.2,
         intro='温宜公主生母，华妃的智囊，笑里藏刀。'),
    dict(npc_key='xinchangzai', surname='吕', given='盈风', title='欣', rank=3, palace='储秀宫',
         appearance=55, talent=45, scheme=40, virtue=55, health=70, favor=70, aggression=0,
         intro='资历老，位分低，说话爽利。'),
]

# ── 殿选 ───────────────────────────────────────────────────────────────────────

DIANXUAN_QUESTIONS = [
    dict(key='name', who='皇上', ask='「你叫什么名字？这名字可有什么出处？」', opts=[
        dict(text='引一句诗作答，说名字取自其中', stat='talent', bonus=8,
             react='皇上微微一笑：「倒是个好名字，也念得好。」'),
        dict(text='规规矩矩报上家门与名字', stat='virtue', bonus=4,
             react='太后点点头：「是个懂规矩的。」'),
        dict(text='抬头看了皇上一眼，才轻声作答', stat='appearance', bonus=6,
             react='皇上多看了你两眼。'),
        dict(text='「名字是父母所取，臣女不敢妄言出处。」', stat='scheme', bonus=3,
             react='殿上安静了一瞬，没人挑得出错。'),
    ]),
    dict(key='book', who='太后', ask='「平日在家都读些什么书？」', opts=[
        dict(text='《女则》《女训》', stat='virtue', bonus=8,
             react='太后面露满意：「女子德行为先。」'),
        dict(text='诗词歌赋，也读些史书', stat='talent', bonus=2,
             react='太后淡淡道：「读得多了，心也就野了。」皇上倒是有些兴趣。'),
        dict(text='「臣女愚钝，只识得几个字。」', stat='scheme', bonus=5,
             react='华妃掩口一笑，你却因此没被任何人记住——这正是你想要的。'),
        dict(text='「偶尔翻看父兄的兵书。」', stat='appearance', bonus=-2, risky=True,
             react='满殿一静。皇上却笑了：「有意思。」'),
    ]),
    dict(key='flower', who='殿前', ask='候选时，一只蝴蝶忽然落在你衣襟上，众人都看了过来。', opts=[
        dict(text='静立不动，任它停着', stat='virtue', bonus=5,
             react='太后说了句：「沉得住气。」'),
        dict(text='借着蝴蝶随口吟了两句诗', stat='talent', bonus=6,
             react='皇上抬眼看你：「这倒巧。」'),
        dict(text='低头嫣然一笑，任由众人去看', stat='appearance', bonus=8,
             react='皇上的目光在你身上停了片刻。'),
        dict(text='惊慌地抬手把蝴蝶拂开', stat='virtue', bonus=-15,
             react='引得几位秀女低笑，太后皱了皱眉。'),
    ]),
    dict(key='huafei', who='华妃', ask='华妃冷冷打量你：「这身衣裳倒是素净得很，是家里穷得置办不起吗？」', opts=[
        dict(text='「家母常说，素净是女子本分。」', stat='virtue', bonus=6,
             react='太后看了华妃一眼，华妃只好收了声。'),
        dict(text='低头不语，由她说去', stat='scheme', bonus=4,
             react='华妃自觉无趣，转头去看下一个了。'),
        dict(text='「娘娘这身才叫华贵，臣女望尘莫及。」', stat='scheme', bonus=6,
             react='华妃哼了一声，脸上倒是好看了些。'),
        dict(text='不卑不亢地抬起头，直视华妃', stat='appearance', bonus=5, risky=True,
             react='皇上似乎起了兴致，华妃的脸色却沉了下来。'),
    ]),
    dict(key='art', who='皇上', ask='「可会些什么才艺？」', opts=[
        dict(text='当场吟一首新作的诗', stat='talent', bonus=8,
             react='皇上抚掌：「好一个才女。」'),
        dict(text='「只会些女红针黹。」', stat='virtue', bonus=5,
             react='太后颔首：「会过日子的。」'),
        dict(text='「愿为皇上献舞一支。」', stat='appearance', bonus=7,
             react='皇上笑道：「来日再看吧。」语气却是满意的。'),
        dict(text='「臣女愚钝，不敢在御前献丑。」', stat='scheme', bonus=2,
             react='平平淡淡地过去了。'),
    ]),
]
# 总分阈值 → 初封位分。模拟过分布：随手答中位数约 99，扬长避短地答中位数约 120，
# 这组阈值下随手答约 5% 贵人，用心答约 25% 贵人
DIANXUAN_TIERS = [(135, 4), (110, 3), (85, 2), (-999, 1)]

def dianxuan_questions_for(consort_id):
    rnd = random.Random(consort_id * 7919)
    return rnd.sample(DIANXUAN_QUESTIONS, 3)

# ── 游戏状态 / 工具 ────────────────────────────────────────────────────────────

settle_lock = threading.RLock()

def init_db():
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    # 幂等迁移：旧角色从更新时开始计龄，不按旧存档天数追溯增长。
    migrations = {
        'consorts': {'age_months': 'INTEGER NOT NULL DEFAULT 240',
                     'poisoned_day': 'INTEGER NOT NULL DEFAULT 0',
                     'poison_treatment': 'INTEGER NOT NULL DEFAULT 0',
                     'protected_until_day': 'INTEGER NOT NULL DEFAULT 0',
                     'death_day': 'INTEGER NOT NULL DEFAULT 0',
                     'death_reason': "TEXT NOT NULL DEFAULT ''",
                     'archived_user_id': 'INTEGER'},
        'users': {'lethal_ready_day': 'INTEGER NOT NULL DEFAULT 0'}
    }
    for table, fields in migrations.items():
        existing = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
        for field, definition in fields.items():
            if field not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
    if not db.execute("SELECT 1 FROM game_state WHERE id=1").fetchone():
        now = datetime.now(TZ)
        # 开服时若已过今天的结算时刻，视为今天已结算，免得一开服就空结算一次
        last = now.date().isoformat() if past_settle_time(now) else ''
        db.execute("INSERT INTO game_state (id, day, last_settle_date, emperor_mood, emperor_pref) VALUES (1,1,?,?,?)",
                   (last, '平和', random.choice(ARTS)))
    for n in NPCS:
        if not db.execute("SELECT 1 FROM consorts WHERE npc_key=?", (n['npc_key'],)).fetchone():
            db.execute("""INSERT INTO consorts (npc_key, surname, given, title, rank, palace,
                          appearance, talent, scheme, virtue, health, favor, aggression, intro,
                          status, entered_day, created_ts)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'normal', 0, ?)""",
                       (n['npc_key'], n['surname'], n['given'], n['title'], n['rank'], n['palace'],
                        n['appearance'], n['talent'], n['scheme'], n['virtue'], n['health'],
                        n['favor'], n['aggression'], n['intro'], now_ts()))
    db.commit()
    db.close()

def past_settle_time(now):
    return (now.hour, now.minute) >= (SETTLE_HOUR, SETTLE_MINUTE)

def state():
    return q("SELECT * FROM game_state WHERE id=1", one=True)

def cur_day():
    return state()['day']

def next_settle_text():
    now = datetime.now(TZ)
    st = state()
    target = now.replace(hour=SETTLE_HOUR, minute=SETTLE_MINUTE, second=0, microsecond=0)
    if st['last_settle_date'] == now.date().isoformat():
        target += timedelta(days=1)
    return ('今晚 ' if target.date() == now.date() else '明晚 ') + target.strftime('%H:%M')

def get_consort(cid):
    return q("SELECT * FROM consorts WHERE id=?", (cid,), one=True)

def my_consort():
    uid = S.get('uid')
    if not uid: return None
    return q("SELECT * FROM consorts WHERE user_id=?", (uid,), one=True)

def is_sick(c):
    return c['health'] < 25 or bool(c['poisoned_day'])

def arts_of(c):
    try: return json.loads(c['arts'] or '{}')
    except Exception: return {}

def notify(cid, text, kind='info'):
    run("INSERT INTO messages (consort_id, day, kind, text, created_ts) VALUES (?,?,?,?,?)",
        (cid, cur_day(), kind, text, now_ts()))

def gazette(text, kind='news', day=None):
    run("INSERT INTO gazette (day, kind, text, created_ts) VALUES (?,?,?,?)",
        (day or cur_day(), kind, text, now_ts()))

def daily_count(cid, key):
    row = q("SELECT count FROM daily_counters WHERE consort_id=? AND key=? AND day=?",
            (cid, key, cur_day()), one=True)
    return row['count'] if row else 0

def daily_inc(cid, key, n=1):
    run("""INSERT INTO daily_counters (consort_id, key, day, count) VALUES (?,?,?,?)
           ON CONFLICT(consort_id, key, day) DO UPDATE SET count=count+?""",
        (cid, key, cur_day(), n, n))

def set_stat(cid, field, value):
    assert field in ('appearance', 'talent', 'scheme', 'virtue', 'health')
    run(f"UPDATE consorts SET {field}=? WHERE id=?", (clamp(value, 1, 100), cid))

def add_stat(cid, field, delta):
    c = get_consort(cid)
    set_stat(cid, field, c[field] + delta)

def add_favor(cid, delta, gain_mult=True):
    c = get_consort(cid)
    if delta > 0 and gain_mult and c['personality'] == 'gentle':
        delta = int(round(delta * 1.1))
    run("UPDATE consorts SET favor=MAX(0, favor+?) WHERE id=?", (int(delta), cid))
    return int(delta)

def cut_favor(cid, ratio, minimum=0):
    """按比例扣圣宠，天真性格减半。返回实际扣掉的数"""
    c = get_consort(cid)
    if c['personality'] == 'naive': ratio /= 2
    loss = max(minimum, int(c['favor'] * ratio))
    loss = min(loss, c['favor'])
    run("UPDATE consorts SET favor=favor-? WHERE id=?", (loss, cid))
    return loss

def add_silver(cid, delta):
    run("UPDATE consorts SET silver=MAX(0, silver+?) WHERE id=?", (int(delta), cid))

def inv_qty(cid, key):
    row = q("SELECT qty FROM inventory WHERE consort_id=? AND item_key=?", (cid, key), one=True)
    return row['qty'] if row else 0

def inv_add(cid, key, n=1):
    run("""INSERT INTO inventory (consort_id, item_key, qty) VALUES (?,?,?)
           ON CONFLICT(consort_id, item_key) DO UPDATE SET qty=qty+?""", (cid, key, n, n))
    run("DELETE FROM inventory WHERE qty<=0")

def pair(a, b):
    return (a, b) if a < b else (b, a)

def relation(a, b):
    x, y = pair(a, b)
    return q("SELECT * FROM relations WHERE a_id=? AND b_id=?", (x, y), one=True)

def add_affinity(a, b, delta):
    x, y = pair(a, b)
    run("""INSERT INTO relations (a_id, b_id, affinity) VALUES (?,?,?)
           ON CONFLICT(a_id, b_id) DO UPDATE SET affinity=MAX(-100, MIN(100, affinity+?))""",
        (x, y, max(-100, min(100, delta)), delta))

def sisters_of(cid):
    rows = q("""SELECT c.id FROM relations r JOIN consorts c
                ON c.id=CASE WHEN r.a_id=? THEN r.b_id ELSE r.a_id END
                WHERE r.sister=1 AND (r.a_id=? OR r.b_id=?) AND c.status!='dead'""", (cid, cid, cid))
    return [r['id'] for r in rows]

def active_sister_count(cid):
    n = 0
    for sid in sisters_of(cid):
        s = get_consort(sid)
        if s and s['status'] in ('normal', 'confined'): n += 1
    return n

def eyes_active(c):
    return c['eyes_until_day'] >= cur_day()

def slot_free(rank, exclude_id=None):
    cap = RANK_SLOTS.get(rank)
    if cap is None: return True
    used = q("SELECT COUNT(*) n FROM consorts WHERE rank=? AND status NOT IN ('cold','xiunv','dead') AND id!=?",
             (rank, exclude_id or 0), one=True)['n']
    return used < cap

def assign_title(cid):
    used = {r['title'] for r in q("SELECT title FROM consorts WHERE title!='' AND status NOT IN ('cold','dead')")}
    pool = [t for t in TITLE_POOL if t not in used]
    if not pool: return ''
    t = random.choice(pool)
    run("UPDATE consorts SET title=? WHERE id=?", (t, cid))
    return t

def set_rank(cid, new_rank, reason_day=None):
    new_rank = max(1, min(9, new_rank))
    run("UPDATE consorts SET rank=?, rank_since_day=? WHERE id=?", (new_rank, reason_day or cur_day(), cid))
    c = get_consort(cid)
    if new_rank >= 5 and not c['title']:
        assign_title(cid)

def confine(cid, days):
    c = get_consort(cid)
    if c['status'] in ('cold', 'dead'): return
    until = max(c['status_until_day'] if c['status'] == 'confined' else 0, cur_day() + days)
    run("UPDATE consorts SET status='confined', status_until_day=? WHERE id=?", (until, cid))

def send_to_cold(cid):
    c = get_consort(cid)
    if c['status'] == 'dead': return
    # 废为庶人：封号一并褫夺，出冷宫后要重新挣
    run("""UPDATE consorts SET status='cold', status_until_day=?, rank_before_cold=?,
           favor=0, pregnant_since=0, seek_bonus=0, title=? WHERE id=?""",
        (cur_day() + COLD_DAYS, c['rank'], c['title'] if c['npc_key'] else '', cid))

def release_from_cold(cid, reason):
    c = get_consort(cid)
    if c['npc_key'] or c['status'] == 'dead': return   # NPC 进了冷宫就不再出来
    new_rank = min(2, max(1, c['rank_before_cold']))
    run("""UPDATE consorts SET status='normal', status_until_day=0, rank=?, rank_since_day=?,
           favor=20 WHERE id=?""", (new_rank, cur_day(), cid))
    c = get_consort(cid)
    notify(cid, f"{reason}你被放出冷宫，复为{RANK_NAMES[new_rank]}。", 'decree')
    gazette(f"{reason}{full_name(c)}出冷宫，复为{display_name(c)}。", 'decree')

def emperor_art_bonus(c):
    arts = arts_of(c)
    return arts.get(state()['emperor_pref'], 0) >= ART_MASTERY

# ── 登录 ───────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    @atomic
    def wrapper(*a, **kw):
        if not S.get('uid'):
            return redirect(url_for('login'))
        c = my_consort()
        if c is None:
            if request.endpoint not in ('create', 'logout'):
                return redirect(url_for('create'))
        elif c['status'] == 'xiunv' and request.endpoint not in ('dianxuan', 'logout'):
            return redirect(url_for('dianxuan'))
        elif c['status'] == 'dead' and request.endpoint not in ('memorial', 'rebirth', 'logout'):
            return redirect(url_for('memorial'))
        g.me = c
        return f(*a, **kw)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not S.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*a, **kw)
    return wrapper

@app.context_processor
def inject_globals():
    ctx = dict(dn=display_name, full_name=full_name, RANK_NAMES=RANK_NAMES, STAT_NAMES=STAT_NAMES,
               favor_word=favor_word, ITEMS=ITEMS, FAMILIES=FAMILIES, PERSONALITIES=PERSONALITIES, age_text=age_text, palace_date=palace_date,
               poison_deadline=lambda ts: datetime.fromtimestamp(ts, TZ).strftime('%m月%d日 %H:%M'))
    try:
        ctx['gs'] = state()
        ctx['next_settle'] = next_settle_text()
    except Exception:
        pass
    return ctx

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        u = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if u and check_password_hash(u['password_hash'], password):
            S.permanent = True
            S['uid'] = u['id']
            return redirect(url_for('index'))
        flash('账号或密码不对。', 'bad')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not (2 <= len(username) <= 20):
            flash('账号要 2 到 20 个字。', 'bad')
        elif len(password) < 4:
            flash('密码至少 4 位。', 'bad')
        elif q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            flash('这个账号已经有人用了。', 'bad')
        else:
            cur = run("INSERT INTO users (username, password_hash, created_ts) VALUES (?,?,?)",
                      (username, generate_password_hash(password, method='pbkdf2:sha256'), now_ts()))
            S.permanent = True
            S['uid'] = cur.lastrowid
            return redirect(url_for('create'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    S.clear()
    return redirect(url_for('login'))

# ── 创建秀女 ───────────────────────────────────────────────────────────────────

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if g.me is not None:
        return redirect(url_for('index'))
    if request.method == 'POST':
        f = request.form
        surname, given = f.get('surname', '').strip(), f.get('given', '').strip()
        fam, per = f.get('family'), f.get('personality')
        try:
            age = int(f.get('age', 20))
            pts = {k: int(f.get(k, 0) or 0) for k in STAT_KEYS}
        except ValueError:
            pts = None
        err = None
        if not (1 <= len(surname) <= 4) or not (1 <= len(given) <= 3):
            err = '姓 1~4 个字，名 1~3 个字。'
        elif pts is not None and not 18 <= age <= 22:
            err = '入宫年龄为十八至二十二岁。'
        elif fam not in FAMILIES or per not in PERSONALITIES:
            err = '请选择出身和性格。'
        elif pts is None or any(v < 0 or v > POINT_CAP_PER_STAT for v in pts.values()) \
                or sum(pts.values()) > FREE_POINTS:
            err = f'加点有误：总共 {FREE_POINTS} 点，每项最多 {POINT_CAP_PER_STAT} 点。'
        elif q("SELECT 1 FROM consorts WHERE surname=? AND given=?", (surname, given), one=True):
            err = '宫里已经有同名的人了，换个名字吧。'
        if err:
            flash(err, 'bad')
            return render_template('create.html', form=f)
        stats = dict(STAT_BASE)
        for k in STAT_KEYS: stats[k] += pts[k]
        for src in (FAMILIES[fam]['mods'], PERSONALITIES[per]['mods']):
            for k, v in src.items(): stats[k] += v
        stats = {k: clamp(v, 5, 100) for k, v in stats.items()}
        run("""INSERT INTO consorts (user_id, surname, given, family, personality,
               appearance, talent, scheme, virtue, health, silver, secret, status, created_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'xiunv', ?)""",
            (S['uid'], surname, given, fam, per, stats['appearance'], stats['talent'],
             stats['scheme'], stats['virtue'], stats['health'], FAMILIES[fam]['silver'],
             roll_secret(), now_ts()))
        run('UPDATE consorts SET age_months=? WHERE user_id=?', (age * 12, S['uid']))
        return redirect(url_for('dianxuan'))
    return render_template('create.html', form={})

@app.route('/dianxuan', methods=['GET', 'POST'])
@login_required
def dianxuan():
    c = g.me
    if c['status'] != 'xiunv':
        return redirect(url_for('index'))
    qs = dianxuan_questions_for(c['id'])
    if request.method == 'POST':
        total, reactions, risky_huafei = 0, [], False
        for qu in qs:
            try:
                opt = qu['opts'][int(request.form.get(qu['key'], ''))]
            except (ValueError, IndexError):
                flash('每一问都要作答。', 'bad')
                return render_template('dianxuan.html', qs=qs, c=c)
            val = c[opt['stat']] * 0.6 + opt['bonus'] + random.randint(-5, 10)
            if opt.get('risky'):
                val += random.choice([-12, 15])
                if qu['key'] == 'huafei': risky_huafei = True
            total += val
            reactions.append(dict(ask=qu['ask'], who=qu['who'], answer=opt['text'], react=opt['react']))
        total += FAMILIES[c['family']]['dx']
        total = int(round(total))
        rank = next(r for th, r in DIANXUAN_TIERS if total >= th)
        day = cur_day()
        taken = [r['palace'] for r in q("SELECT palace FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('cold','dead')")]
        palace = min(PLAYER_PALACES, key=lambda p: (taken.count(p), random.random()))
        favor = {4: 40, 3: 20, 2: 10, 1: 0}[rank]
        run("""UPDATE consorts SET status='normal', rank=?, rank_since_day=?, palace=?, favor=?,
               entered_day=?, dianxuan_score=?, energy=? WHERE id=?""",
            (rank, day, palace, favor, day, total, ENERGY_MAX, c['id']))
        title = ''
        if rank >= 4 or (rank == 3 and random.random() < 0.3):
            title = assign_title(c['id'])
        c = get_consort(c['id'])
        decree = f"{FAMILIES[c['family']]['name']}{full_name(c)}，留牌子，" \
                 f"{'赐封号「' + title + '」，' if title else ''}封为{display_name(c)}，赐居{palace}。"
        gazette(f"殿选：{decree}", 'decree')
        notify(c['id'], f"殿选中选。{decree}", 'decree')
        if risky_huafei:
            add_affinity(c['id'], q("SELECT id FROM consorts WHERE npc_key='huafei'", one=True)['id'], -30)
        return render_template('dianxuan_result.html', c=c, reactions=reactions, total=total, title=title)
    return render_template('dianxuan.html', qs=qs, c=c)

# ── 我的宫苑 ───────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    c = g.me
    day = cur_day()
    msgs = q("SELECT * FROM messages WHERE consort_id=? ORDER BY id DESC LIMIT 20", (c['id'],))
    run("UPDATE messages SET is_read=1 WHERE consort_id=? AND is_read=0", (c['id'],))
    nxt = c['rank'] + 1
    promo = None
    if c['status'] != 'cold' and nxt <= PLAYER_MAX_RANK:
        promo = dict(rank=RANK_NAMES[nxt], favor=PROMOTE_FAVOR[nxt], virtue=PROMOTE_VIRTUE[nxt],
                     slot=slot_free(nxt, c['id']), days_ok=(day - c['rank_since_day']) >= MIN_DAYS_AT_RANK)
    counts = {k: daily_count(c['id'], k) for k in ACTIONS}
    heirs = q("SELECT * FROM heirs WHERE mother_id=? ORDER BY id", (c['id'],))
    players = q("""SELECT * FROM consorts WHERE id!=? AND user_id IS NOT NULL AND status NOT IN ('xiunv','dead')
                   ORDER BY rank DESC, favor DESC""", (c['id'],))
    return render_template('index.html', c=c, msgs=msgs, promo=promo, counts=counts, ACTIONS=ACTIONS,
                           arts=arts_of(c), ARTS=ARTS, ART_MASTERY=ART_MASTERY, heirs=heirs,
                           sick=is_sick(c), eyes=eyes_active(c), secret=SECRETS[c['secret']],
                           players=players, day=day, PREGNANCY_DAYS=PREGNANCY_DAYS)

class Reject(Exception):
    pass

def charge(c, cfg):
    run("UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?",
        (cfg['energy'], cfg['silver'], c['id']))

def pick_target(c, allow_npc=False):
    try:
        tid = int(request.form.get('target_id', 0))
    except ValueError:
        raise Reject('没选对象。')
    t = get_consort(tid)
    if not t or t['id'] == c['id'] or t['status'] in ('xiunv', 'dead'):
        raise Reject('没有这个人。')
    if t['npc_key'] and not allow_npc:
        raise Reject('这件事只能对玩家做。')
    return t

@app.route('/act/<key>', methods=['POST'])
@login_required
def act(key):
    c = g.me
    cfg = ACTIONS.get(key)
    if not cfg:
        return redirect(url_for('index'))
    try:
        if c['status'] not in cfg['when']:
            raise Reject({'confined': '禁足中，出不了宫门。', 'cold': '冷宫里做不了这件事。'}
                         .get(c['status'], '现在做不了这件事。'))
        if cfg.get('sick_block') and is_sick(c):
            raise Reject('你病得起不来身，先静养吧。')
        if c['energy'] < cfg['energy']:
            raise Reject('今天精力用完了，等夜里结算后恢复。')
        if c['silver'] < cfg['silver']:
            raise Reject(f"银子不够，需要 {cfg['silver']} 两。")
        if daily_count(c['id'], key) >= cfg['daily']:
            raise Reject(f"「{cfg['name']}」今天已经做过 {cfg['daily']} 次了。")
        msg, kind = ACTION_HANDLERS[key](c, cfg)
        daily_inc(c['id'], key)
        flash(msg, kind)
    except Reject as e:
        flash(str(e), 'bad')
    back = request.form.get('back')
    return redirect(url_for(back) if back in ('social', 'index') else url_for('index'))

def do_greet(c, cfg):
    charge(c, cfg)
    gain = 2 if c['personality'] == 'dignified' else 1
    add_stat(c['id'], 'virtue', gain)
    run("UPDATE consorts SET greet_day=?, missed_greet=0 WHERE id=?", (cur_day(), c['id']))
    msg = f"你到景仁宫给皇后请了安。德行 +{gain}。"
    r = random.random()
    huafei = q("SELECT * FROM consorts WHERE npc_key='huafei'", one=True)
    if r < 0.3 and huafei['status'] == 'normal':
        if c['virtue'] + c['scheme'] + random.randint(0, 60) >= 110:
            add_favor(c['id'], 3)
            msg += "华妃当众发难，你应对得体，皇后夸你识大体。圣宠 +3。"
            return msg, 'good'
        add_stat(c['id'], 'health', -5)
        return msg + "华妃当众发难，你没接住，被罚在廊下跪了半个时辰。体质 -5。", 'bad'
    if r < 0.5:
        add_silver(c['id'], 20)
        return msg + "皇后赏了你一对珠花。银子 +20。", 'good'
    return msg, 'info'

def do_study(c, cfg):
    art = request.form.get('art')
    if art not in ARTS:
        raise Reject('选一门要修习的才艺。')
    charge(c, cfg)
    gain = 2 if c['talent'] < 60 else 1
    if c['personality'] == 'clever': gain += 1
    add_stat(c['id'], 'talent', gain)
    arts = arts_of(c)
    before = arts.get(art, 0)
    arts[art] = before + 1
    run("UPDATE consorts SET arts=? WHERE id=?", (json.dumps(arts, ensure_ascii=False), c['id']))
    msg = f"你练了一日{art}。才艺 +{gain}。"
    if before < ART_MASTERY <= arts[art]:
        msg += f"你的{art}已臻精通。"
        gazette(f"听说{display_name(c)}的{art}已臻化境。")
    if art == state()['emperor_pref'] and c['status'] == 'normal':
        add_favor(c['id'], 2)
        msg += "皇上近来正喜欢这个，有人把你练习的事传到了养心殿。圣宠 +2。"
    return msg, 'good'

def do_groom(c, cfg):
    charge(c, cfg)
    gain = 2 if c['appearance'] < 70 else 1
    add_stat(c['id'], 'appearance', gain)
    add_stat(c['id'], 'health', 3)
    return f"你细细梳妆，敷了珍珠粉。容貌 +{gain}，体质 +3。", 'good'

def do_rest(c, cfg):
    charge(c, cfg)
    add_stat(c['id'], 'health', 8)
    return "你歇了一日，喝了几盏参汤。体质 +8。", 'good'

def do_reflect(c, cfg):
    charge(c, cfg)
    add_stat(c['id'], 'virtue', 2)
    msg = "你闭门抄了一日经书。德行 +2。"
    if c['status'] == 'cold' and random.random() < 0.05 + c['talent'] / 2000:
        release_from_cold(c['id'], '皇上夜里听见冷宫方向传来琴声，心生怜惜。')
        return msg + "……皇上竟想起了你。", 'good'
    return msg, 'info'

def do_eyes(c, cfg):
    charge(c, cfg)
    run("UPDATE consorts SET eyes_until_day=? WHERE id=?", (cur_day() + 4, c['id']))
    return "你打点了几个宫人做眼线，接下来五天宫里的风吹草动都瞒不过你。", 'good'

def do_seek(c, cfg):
    charge(c, cfg)
    mood = state()['emperor_mood']
    run("UPDATE consorts SET seek_bonus=seek_bonus+15 WHERE id=?", (c['id'],))
    if mood == '大悦':
        g_ = add_favor(c['id'], random.randint(10, 15))
        return f"皇上心情正好，留你说了会儿话。圣宠 +{g_}。", 'good'
    if mood == '平和':
        g_ = add_favor(c['id'], random.randint(5, 10))
        return f"苏培盛接了汤羹，说皇上喝着很合口。圣宠 +{g_}。", 'good'
    if mood == '烦闷':
        if random.random() < 0.5:
            return "苏培盛说皇上在批折子，汤羹放下就走吧。", 'info'
        g_ = add_favor(c['id'], random.randint(4, 8))
        return f"皇上心里烦，喝了你的汤倒舒坦了些。圣宠 +{g_}。", 'good'
    add_favor(c['id'], -5)
    return "皇上正为前朝的事动怒，你撞在了气头上。圣宠 -5。", 'bad'

def do_garden(c, cfg):
    charge(c, cfg)
    events = [('emperor', 18 + c['appearance'] / 6 + c['talent'] / 10), ('flower', 22), ('secret', 12),
              ('huafei', 14), ('quiet', 22), ('meet', 12)]
    ev = random.choices([e for e, _ in events], weights=[w for _, w in events])[0]
    if ev == 'emperor':
        g_ = add_favor(c['id'], random.randint(8, 18))
        run("UPDATE consorts SET seek_bonus=seek_bonus+10 WHERE id=?", (c['id'],))
        return f"你在杏花树下遇见了皇上，说了好一会儿话。圣宠 +{g_}。", 'good'
    if ev == 'flower':
        amt = random.randint(10, 30)
        add_silver(c['id'], amt)
        return f"你在假山石缝里拾到一支金簪，托人换了银子。银子 +{amt}。", 'good'
    if ev == 'secret':
        cands = q("""SELECT id FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status NOT IN ('xiunv','cold','dead')
                     AND secret_revealed=0 AND id NOT IN (SELECT target_id FROM known_secrets WHERE knower_id=?)""",
                  (c['id'], c['id']))
        if cands:
            t = get_consort(random.choice(cands)['id'])
            run("INSERT OR IGNORE INTO known_secrets (knower_id, target_id, day) VALUES (?,?,?)",
                (c['id'], t['id'], cur_day()))
            if t['secret'] == 'none':
                return f"你在假山后听见{display_name(t)}的宫女在嚼舌根，说的都是些无关紧要的事——看来她确实清白。", 'info'
            return f"你在假山后听见{display_name(t)}的宫女在嚼舌根：原来她{SECRETS[t['secret']]['name']}。", 'good'
        return "你在假山后听见有人在说话，走近却没了人影。", 'info'
    if ev == 'huafei':
        if c['virtue'] + random.randint(0, 50) >= 70:
            add_favor(c['id'], 2)
            return "华妃的轿辇经过，你行礼一丝不苟，她挑不出错来。圣宠 +2。", 'info'
        add_stat(c['id'], 'health', -8)
        return "华妃嫌你挡了路，罚你在日头底下跪着。体质 -8。", 'bad'
    if ev == 'meet':
        others = q("""SELECT id FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status='normal'""", (c['id'],))
        if others:
            t = get_consort(random.choice(others)['id'])
            add_affinity(c['id'], t['id'], 5)
            notify(t['id'], f"{display_name(c)}在御花园与你闲话了几句。好感 +5。")
            return f"你在千鲤池边遇见{display_name(t)}，聊得投缘。好感 +5。", 'good'
    add_stat(c['id'], 'health', 2)
    return "你在亭子里坐了坐，看了会儿锦鲤。体质 +2。", 'info'

def do_visit(c, cfg):
    t = pick_target(c)
    if t['status'] == 'cold':
        raise Reject('冷宫不许探视。')
    if daily_count(c['id'], f'visit:{t["id"]}') >= 1:
        raise Reject('今天已经去过她那儿了。')
    charge(c, cfg)
    daily_inc(c['id'], f'visit:{t["id"]}')
    gain = random.randint(6, 10)
    add_affinity(c['id'], t['id'], gain)
    notify(t['id'], f"{display_name(c)}来{t['palace']}坐了坐。好感 +{gain}。")
    return f"你去{t['palace']}看了{display_name(t)}，一起喝茶说话。好感 +{gain}。", 'good'

def do_spy(c, cfg):
    t = pick_target(c)
    if t['secret_revealed']:
        raise Reject('她的底细六宫早都知道了。')
    if q("SELECT 1 FROM known_secrets WHERE knower_id=? AND target_id=?", (c['id'], t['id']), one=True):
        raise Reject('她的底细你已经摸清了。')
    charge(c, cfg)
    p = clamp((0.35 + (c['scheme'] - t['scheme']) * 0.01 - (0.15 if eyes_active(t) else 0)) * 100, 10, 85) / 100
    if random.random() < p:
        run("INSERT OR IGNORE INTO known_secrets (knower_id, target_id, day) VALUES (?,?,?)",
            (c['id'], t['id'], cur_day()))
        if t['secret'] == 'none':
            return f"你使银子打听了一圈：{display_name(t)}身家清白，没什么把柄。", 'info'
        return f"打听到了：{display_name(t)}{SECRETS[t['secret']]['name']}。", 'good'
    if random.random() < (0.6 if eyes_active(t) else 0.25):
        who = display_name(c) if eyes_active(t) else '有人'
        notify(t['id'], f"眼线来报：{who}在打听你的底细。", 'bad')
        return "银子花了，什么也没打听到，还惊动了对方。", 'bad'
    return "银子花了，什么也没打听到。", 'info'

def do_plead(c, cfg):
    t = pick_target(c)
    if t['status'] not in ('confined', 'cold'):
        raise Reject('她好好的，不必求情。')
    rel = relation(c['id'], t['id'])
    if not rel or (not rel['sister'] and rel['affinity'] < 30):
        raise Reject('你与她交情不够，贸然求情反惹皇上疑心。需结为姐妹或好感 30 以上。')
    charge(c, cfg)
    p = min(0.85, 0.4 + c['favor'] / 1000 + c['virtue'] / 200)
    if random.random() < p:
        cut = 1 if t['status'] == 'confined' else 2
        run("UPDATE consorts SET status_until_day=status_until_day-? WHERE id=?", (cut, t['id']))
        notify(t['id'], f"{display_name(c)}在皇上跟前替你求了情，日子缩短了 {cut} 天。", 'good')
        add_affinity(c['id'], t['id'], 5)
        t2 = get_consort(t['id'])
        if t2['status_until_day'] <= cur_day():
            if t2['status'] == 'cold':
                release_from_cold(t['id'], f"{display_name(c)}苦苦求情，")
            else:
                run("UPDATE consorts SET status='normal', status_until_day=0 WHERE id=?", (t['id'],))
                notify(t['id'], '禁足解了。', 'good')
        return f"皇上听了你的话，松了口。{full_name(t)}的日子缩短了 {cut} 天。", 'good'
    add_favor(c['id'], -5)
    return "皇上脸色一沉：「后宫的事，轮得到你来说？」圣宠 -5。", 'bad'

ACTION_HANDLERS = dict(greet=do_greet, study=do_study, groom=do_groom, rest=do_rest, reflect=do_reflect,
                       eyes=do_eyes, seek=do_seek, garden=do_garden, visit=do_visit, spy=do_spy, plead=do_plead)

# ── 秘密坦白 ───────────────────────────────────────────────────────────────────

def apply_secret_penalty(cid, confessed):
    c = get_consort(cid)
    s = c['secret']
    if s == 'lover':
        if confessed: cut_favor(cid, 0.2)
        else:
            cut_favor(cid, 0.5); add_stat(cid, 'virtue', -15)
    elif s == 'fake':
        if confessed: cut_favor(cid, 0.3)
        elif c['rank'] > 1: set_rank(cid, c['rank'] - 1)
    elif s == 'book':
        confine(cid, 1 if confessed else 3)
    elif s == 'scar':
        add_stat(cid, 'appearance', -5 if confessed else -10)
        if not confessed: cut_favor(cid, 0.2)
    elif s == 'physician':
        if confessed: confine(cid, 3)
        else: send_to_cold(cid)
    run("UPDATE consorts SET secret_revealed=1 WHERE id=?", (cid,))

@app.route('/confess', methods=['POST'])
@login_required
def confess():
    c = g.me
    if c['secret'] == 'none' or c['secret_revealed']:
        flash('你没有需要坦白的事。', 'bad')
        return redirect(url_for('index'))
    if c['status'] == 'cold':
        flash('冷宫里的话，传不到皇上耳朵里。', 'bad')
        return redirect(url_for('index'))
    apply_secret_penalty(c['id'], confessed=True)
    sec = SECRETS[c['secret']]
    flash(f"你向皇上坦白了：{sec['name']}。皇上念你诚实，从轻发落：{sec['confess']}。", 'info')
    gazette(f"{display_name(c)}主动向皇上陈情，皇上从轻发落。")
    return redirect(url_for('index'))

# ── 六宫（社交）────────────────────────────────────────────────────────────────

@app.route('/social')
@login_required
def social():
    c = g.me
    others = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status NOT IN ('xiunv','dead')
                  ORDER BY rank DESC, favor DESC""", (c['id'],))
    rels = {}
    for o in others:
        rels[o['id']] = relation(c['id'], o['id'])
    known = {r['target_id'] for r in q("SELECT target_id FROM known_secrets WHERE knower_id=?", (c['id'],))}
    inv = q("SELECT * FROM inventory WHERE consort_id=? AND qty>0", (c['id'],))
    return render_template('social.html', c=c, others=others, rels=rels, known=known, SECRETS=SECRETS,
                           inv=inv, sister_count=len(sisters_of(c['id'])), ACTIONS=ACTIONS)

@app.route('/sister/<action>/<int:tid>', methods=['POST'])
@login_required
def sister(action, tid):
    c = g.me
    t = get_consort(tid)
    if not t or t['npc_key'] or t['id'] == c['id'] or t['status'] in ('xiunv', 'dead'):
        flash('没有这个人。', 'bad')
        return redirect(url_for('social'))
    rel = relation(c['id'], tid)
    x, y = pair(c['id'], tid)
    if action == 'invite':
        if not rel or rel['affinity'] < 40:
            flash('交情还不到，好感 40 以上才能结为姐妹。', 'bad')
        elif rel['sister']:
            flash('你们已经是姐妹了。', 'bad')
        elif len(sisters_of(c['id'])) >= 3:
            flash('你已有三位姐妹，人多口杂。', 'bad')
        else:
            run("UPDATE relations SET invite_from=? WHERE a_id=? AND b_id=?", (c['id'], x, y))
            notify(tid, f"{display_name(c)}想与你义结金兰，去「六宫」回应她。", 'good')
            flash('已递了话过去，等她回应。', 'info')
    elif action == 'accept':
        if not rel or rel['invite_from'] != tid:
            flash('她并没有向你提过这事。', 'bad')
        elif len(sisters_of(c['id'])) >= 3 or len(sisters_of(tid)) >= 3:
            flash('有一方已经有三位姐妹了。', 'bad')
        else:
            run("UPDATE relations SET sister=1, invite_from=0 WHERE a_id=? AND b_id=?", (x, y))
            notify(tid, f"{display_name(c)}答应了，你们从此以姐妹相称。", 'good')
            gazette(f"{display_name(c)}与{display_name(t)}义结金兰。")
            flash(f"你与{display_name(t)}结为姐妹。", 'good')
    elif action == 'decline':
        if rel and rel['invite_from'] == tid:
            run("UPDATE relations SET invite_from=0 WHERE a_id=? AND b_id=?", (x, y))
            notify(tid, f"{display_name(c)}婉拒了结拜的提议。")
            flash('你婉拒了。', 'info')
    elif action == 'break':
        if rel and rel['sister']:
            run("UPDATE relations SET sister=0, invite_from=0, affinity=MAX(-100, affinity-30) WHERE a_id=? AND b_id=?",
                (x, y))
            notify(tid, f"{display_name(c)}与你割袍断义了。", 'bad')
            gazette(f"{display_name(c)}与{display_name(t)}反目，从此形同陌路。")
            flash('你们从此不再是姐妹。好感 -30。', 'bad')
    return redirect(url_for('social'))

@app.route('/gift/<int:tid>', methods=['POST'])
@login_required
def gift(tid):
    c = g.me
    t = get_consort(tid)
    if not t or t['npc_key'] or t['id'] == c['id'] or t['status'] in ('xiunv', 'dead'):
        flash('没有这个人。', 'bad')
        return redirect(url_for('social'))
    if c['status'] == 'cold':
        flash('冷宫里送不出东西。', 'bad')
        return redirect(url_for('social'))
    if daily_count(c['id'], 'gift') >= 3:
        flash('今天已经送过三回礼了。', 'bad')
        return redirect(url_for('social'))
    kind = request.form.get('kind')
    if kind == 'silver':
        try: amt = int(request.form.get('amount', 0))
        except ValueError: amt = 0
        if amt <= 0 or amt > c['silver']:
            flash('银子数目不对。', 'bad')
            return redirect(url_for('social'))
        add_silver(c['id'], -amt); add_silver(tid, amt)
        what, aff = f'{amt} 两银子', 3
    else:
        item = request.form.get('item')
        if item not in ITEMS or inv_qty(c['id'], item) < 1:
            flash('你没有这件东西。', 'bad')
            return redirect(url_for('social'))
        inv_add(c['id'], item, -1)
        if item == 'ruyi':
            what, aff = ITEMS[item]['name'], 15   # 玉如意赠出即消耗，不进对方背包，不能来回刷
        else:
            inv_add(tid, item, 1)
            what, aff = ITEMS[item]['name'], 3
    # 非消耗性的赠礼每天每个方向只加一次好感，防止两人来回倒腾刷好感
    if aff == 3:
        if daily_count(c['id'], f'gift_aff:{tid}') >= 1: aff = 0
        else: daily_inc(c['id'], f'gift_aff:{tid}')
    if aff: add_affinity(c['id'], tid, aff)
    daily_inc(c['id'], 'gift')
    notify(tid, f"{display_name(c)}差人送来{what}。" + (f"好感 +{aff}。" if aff else ''), 'good')
    flash(f"已把{what}送到{t['palace']}。" + (f"好感 +{aff}。" if aff else ''), 'good')
    return redirect(url_for('social'))

# ── 内务府 ─────────────────────────────────────────────────────────────────────

@app.route('/shop')
@login_required
def shop():
    c = g.me
    inv = {r['item_key']: r['qty'] for r in q("SELECT * FROM inventory WHERE consort_id=?", (c['id'],))}
    return render_template('shop.html', c=c, inv=inv)

@app.route('/shop/buy/<key>', methods=['POST'])
@login_required
def shop_buy(key):
    c = g.me
    it = ITEMS.get(key)
    if not it:
        return redirect(url_for('shop'))
    if c['status'] == 'cold':
        flash('冷宫的人，内务府不理会。', 'bad')
    elif c['silver'] < it['price']:
        flash(f"银子不够，{it['name']}要 {it['price']} 两。", 'bad')
    else:
        add_silver(c['id'], -it['price'])
        inv_add(c['id'], key, 1)
        flash(f"买下了{it['name']}。", 'good')
    return redirect(url_for('shop'))

@app.route('/shop/use/<key>', methods=['POST'])
@login_required
def shop_use(key):
    c = g.me
    it = ITEMS.get(key)
    if not it or not it['usable'] or inv_qty(c['id'], key) < 1:
        flash('用不了。', 'bad')
        return redirect(url_for('shop'))
    if key == 'shuhen':
        if daily_count(c['id'], 'use_shuhen') >= 1:
            flash('舒痕胶一天抹一次就够了。', 'bad')
            return redirect(url_for('shop'))
        daily_inc(c['id'], 'use_shuhen')
        add_stat(c['id'], 'appearance', 3); msg = '容貌 +3。'
    elif key == 'renshen':
        add_stat(c['id'], 'health', 15); msg = '体质 +15。'
    elif key == 'qinpu':
        add_stat(c['id'], 'talent', 3); msg = '才艺 +3。'
    elif key == 'shujin':
        if c['status'] != 'normal':
            flash('现在穿给谁看呢。', 'bad')
            return redirect(url_for('shop'))
        run("UPDATE consorts SET seek_bonus=seek_bonus+25 WHERE id=?", (c['id'],)); msg = '今晚翻牌子的机会大增。'
    else:
        msg = ''
    inv_add(c['id'], key, -1)
    flash(f"用了{it['name']}。{msg}", 'good')
    return redirect(url_for('shop'))

# ── 使计 ───────────────────────────────────────────────────────────────────────

def intrigue_targets(c):
    return q("""SELECT * FROM consorts WHERE id!=? AND status NOT IN ('xiunv','cold','dead')
                ORDER BY user_id IS NULL, rank DESC, favor DESC""", (c['id'],))

@app.route('/intrigue')
@login_required
def intrigue():
    c = g.me
    day = cur_day()
    mine = q("SELECT * FROM intrigues WHERE attacker_id=? ORDER BY id DESC LIMIT 15", (c['id'],))
    known = q("""SELECT k.target_id, c.secret, c.secret_revealed FROM known_secrets k
                 JOIN consorts c ON c.id=k.target_id WHERE k.knower_id=?""", (c['id'],))
    return render_template('intrigue.html', c=c, targets=intrigue_targets(c), INTRIGUES=INTRIGUES, mine=mine,
                           known=known, SECRETS=SECRETS, day=day, get_consort=get_consort,
                           used_today=daily_count(c['id'], 'intrigue'), inventory={k: inv_qty(c['id'], k) for k in ITEMS})

@app.route('/intrigue/submit', methods=['POST'])
@login_required
def intrigue_submit():
    c = g.me
    method = request.form.get('method')
    cfg = INTRIGUES.get(method)
    try:
        tid = int(request.form.get('target_id', 0))
    except ValueError:
        tid = 0
    t = get_consort(tid)
    err = None
    day = cur_day()
    if not cfg: err = '选一个计策。'
    elif c['status'] != 'normal': err = '你自身难保，先顾好自己吧。'
    elif is_sick(c): err = '你病着，没力气算计别人。'
    elif not t or t['id'] == c['id'] or t['status'] in ('xiunv', 'cold', 'dead'): err = '这个人不能当目标。'
    elif t['npc_key'] and not cfg['npc_ok']: err = f"「{cfg['name']}」不能用在她身上。"
    elif c['rank'] < cfg['min_rank']: err = f"位分到{RANK_NAMES[cfg['min_rank']]}才使得动「{cfg['name']}」。"
    elif daily_count(c['id'], 'intrigue') >= 1: err = '一天只能谋划一件事，多了容易露马脚。'
    elif c['energy'] < cfg['energy']: err = f"精力不够，需要 {cfg['energy']} 点。"
    elif c['silver'] < cfg['silver']: err = f"银子不够，需要 {cfg['silver']} 两。"
    elif cfg.get('item') and inv_qty(c['id'], cfg['item']) < 1: err = f"手里没有{ITEMS[cfg['item']]['name']}。"
    elif t['user_id'] and t['entered_day'] >= day: err = '她今天才入宫，皇上正新鲜着，这会儿动手太扎眼。'
    elif q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status='pending'",
           (tid, day), one=True)['n'] >= INTRIGUE_TARGET_DAILY_MAX:
        err = '今天盯着她的人已经够多了，换个日子吧。'
    elif method == 'lethal':
        err = lethal_block(c, t, day)
    elif method == 'expose':
        if t['secret_revealed']: err = '她的事早就人尽皆知了。'
        elif not q("SELECT 1 FROM known_secrets WHERE knower_id=? AND target_id=?", (c['id'], tid), one=True):
            err = '你手里没有她的把柄，先去打探。'
        elif t['secret'] == 'none': err = '她身家清白，没什么可告发的。'
    elif method == 'steal' and (t['pregnant_since'] or is_sick(t)):
        err = '她今晚本就侍不了寝。'
    if err:
        flash(err, 'bad')
        return redirect(url_for('intrigue'))
    run("UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?", (cfg['energy'], cfg['silver'], c['id']))
    if cfg.get('item'): inv_add(c['id'], cfg['item'], -1)
    run("""INSERT INTO intrigues (day, attacker_id, target_id, method, silver_paid, item_used, created_ts)
           VALUES (?,?,?,?,?,?,?)""", (day, c['id'], tid, method, cfg['silver'], cfg.get('item', ''), now_ts()))
    if method == 'lethal':
        run('UPDATE users SET lethal_ready_day=? WHERE id=?', (day + LETHAL_COOLDOWN, c['user_id']))
    daily_inc(c['id'], 'intrigue')
    flash(f"已安排下去。{next_settle_text()} 见分晓。", 'info')
    return redirect(url_for('intrigue'))

@app.route('/intrigue/cancel/<int:iid>', methods=['POST'])
@login_required
def intrigue_cancel(iid):
    c = g.me
    it = q("SELECT * FROM intrigues WHERE id=? AND attacker_id=? AND status='pending'", (iid, c['id']), one=True)
    if it:
        run("UPDATE intrigues SET status='cancelled' WHERE id=?", (iid,))
        add_silver(c['id'], it['silver_paid'])
        if it['item_used']: inv_add(c['id'], it['item_used'], 1)
        flash('你把人叫了回来，银子和东西收回了，花掉的精力回不来。', 'info')
    return redirect(url_for('intrigue'))

# ── 位分榜 / 邸报 / 子嗣 ───────────────────────────────────────────────────────

@app.route('/ranks')
@login_required
def ranks():
    rows = q("SELECT * FROM consorts WHERE status NOT IN ('xiunv','dead') ORDER BY rank DESC, favor DESC")
    groups = []
    for r in range(9, 0, -1):
        members = [x for x in rows if x['rank'] == r and x['status'] != 'cold']
        if members or r in RANK_SLOTS:
            groups.append(dict(rank=r, name=RANK_NAMES[r], members=members, cap=RANK_SLOTS.get(r)))
    cold = [x for x in rows if x['status'] == 'cold']
    st = state()
    last_bed = get_consort(st['last_bed_id']) if st['last_bed_id'] else None
    return render_template('ranks.html', groups=groups, cold=cold, me=g.me, last_bed=last_bed)

@app.route('/gazette')
@login_required
def gazette_page():
    day = cur_day()
    rows = q("SELECT * FROM gazette WHERE day>=? ORDER BY day DESC, id DESC", (max(1, day - 7),))
    days = {}
    for r in rows:
        days.setdefault(r['day'], []).append(r)
    return render_template('gazette.html', days=sorted(days.items(), reverse=True), day=day)

CN_NUM = '零一二三四五六七八九十'

def cn_ordinal(n):
    if n <= 10: return CN_NUM[n]
    if n < 20: return '十' + CN_NUM[n - 10]
    return CN_NUM[n // 10] + '十' + (CN_NUM[n % 10] if n % 10 else '')

def heir_label(h):
    if h['name']: return h['name']
    return f"{cn_ordinal(h['ordinal'])}阿哥" if h['gender'] == '皇子' else f"{cn_ordinal(h['ordinal'])}公主"

app.jinja_env.globals['heir_label'] = heir_label

@app.route('/heirs', methods=['GET', 'POST'])
@login_required
def heirs():
    c = g.me
    if request.method == 'POST':
        try: hid = int(request.form.get('heir_id', 0))
        except ValueError: hid = 0
        name = request.form.get('name', '').strip()
        h = q("SELECT * FROM heirs WHERE id=? AND mother_id=?", (hid, c['id']), one=True)
        if not h or h['name']:
            flash('名字已经定了，改不了。', 'bad')
        elif not (2 <= len(name) <= 4):
            flash('名字 2~4 个字。', 'bad')
        else:
            run("UPDATE heirs SET name=? WHERE id=?", (name, hid))
            flash(f"皇上允了，赐名「{name}」。", 'good')
        return redirect(url_for('heirs'))
    rows = q("SELECT h.*, c.surname FROM heirs h JOIN consorts c ON c.id=h.mother_id ORDER BY h.id")
    return render_template('heirs.html', c=c, rows=rows, get_consort=get_consort)

# ── 每晚结算 ───────────────────────────────────────────────────────────────────

def intrigue_success_p(atk, tgt, cfg):
    p = cfg['base'] + (atk['scheme'] - tgt['scheme']) * 0.008
    if atk['personality'] == 'deep': p += 0.05
    if eyes_active(tgt): p -= 0.12
    p -= min(0.15, 0.05 * active_sister_count(tgt['id']))
    if tgt['personality'] == 'dignified': p -= 0.05
    if tgt['virtue'] >= 70: p -= 0.05
    if tgt['rank'] == 9: p -= 0.15
    return max(0.08, min(0.85, p))

def intrigue_caught_p(atk, tgt):
    p = 0.35 + (tgt['scheme'] - atk['scheme']) * 0.005 + (0.25 if eyes_active(tgt) else 0)
    if state()['emperor_mood'] == '震怒': p += 0.1
    return max(0.15, min(0.8, p))

def resolve_intrigue(it, bed_id=None):
    """结算一条阴谋。steal 需要传入今晚被翻牌的人。返回 (result, 被截宠后的新侍寝人或 None)"""
    cfg = INTRIGUES[it['method']]
    atk, tgt = get_consort(it['attacker_id']), get_consort(it['target_id'])
    an, tn = display_name(atk), display_name(tgt)
    new_bed = None

    def done(result):
        run("UPDATE intrigues SET status='done', result=? WHERE id=?", (result, it['id']))
        return result, new_bed

    # 双方有一方已进冷宫、或者出手的人被禁足，事情就办不成了
    if atk['status'] in ('cold', 'dead') or tgt['status'] in ('cold', 'xiunv', 'dead'):
        if atk['user_id']: notify(atk['id'], f"你对{tn}的「{cfg['name']}」没来得及办：局面已经变了。")
        return done('void')
    if it['method'] == 'steal' and (atk['status'] != 'normal' or atk['pregnant_since'] or is_sick(atk)):
        if atk['user_id']: notify(atk['id'], f"你今晚自身难保，对{tn}的截宠只好作罢。")
        return done('void')
    if it['method'] == 'steal' and tgt['id'] != bed_id:
        if atk['user_id']: notify(atk['id'], f"今晚翻的不是{tn}的牌子，你的截宠落了空。银子白花了。")
        return done('void')

    if it['method'] == 'lethal' and (atk['status'] != 'normal' or is_sick(atk) or
            tgt['poisoned_day'] or tgt['protected_until_day'] >= cur_day()):
        if atk['user_id']: notify(atk['id'], f"你对{tn}的毒害落空了：局面已经变了，银子白花了。")
        return done('void')
    tell_name = eyes_active(tgt)
    if it['method'] == 'expose':
        success, caught = random.random() < intrigue_success_p(atk, tgt, cfg), True
    else:
        success = random.random() < intrigue_success_p(atk, tgt, cfg)
        caught = (not success) and random.random() < intrigue_caught_p(atk, tgt)

    if success:
        who = an if tell_name else '有人'
        m = it['method']
        if m == 'lethal':
            run('UPDATE consorts SET poisoned_day=?, poison_treatment=0, health=MAX(1,health-20) WHERE id=?',
                (cur_day(), tgt['id']))
            victim = f"你中毒了，体质 -20。下一次结算前一定要请太医（{TREAT_COST} 两，姐妹也能替你请）：请了九成能活，不请只有三成五。" + \
                     (f"眼线查到是{an}下的手。" if tell_name else '')
            gz = f'{tn}突然中毒，性命垂危。'
        elif m == 'rumor':
            loss = cut_favor(tgt['id'], 0.15, 10)
            add_stat(tgt['id'], 'virtue', -3)
            victim = f"宫里起了关于你的流言，是{who}在背后散播。圣宠 -{loss}，德行 -3。"
            gz = f"宫中有流言说{tn}品行不端，传得有鼻子有眼。"
        elif m == 'frame':
            loss = cut_favor(tgt['id'], 0.2)
            confine(tgt['id'], CONFINE_DAYS)
            victim = f"你宫里搜出了不该有的东西，{who}栽赃陷害了你。禁足 {CONFINE_DAYS} 天，圣宠 -{loss}。"
            gz = f"{tn}宫中搜出违禁之物，皇上下旨禁足。"
        elif m == 'poison':
            if tgt['pregnant_since'] and inv_qty(tgt['id'], 'antai') > 0:
                inv_add(tgt['id'], 'antai', -1)
                add_stat(tgt['id'], 'health', -10)
                victim = f"你的饮食里被人下了麝香，幸好一直在服安胎药，胎儿保住了。体质 -10。" + \
                         (f"眼线查到是{an}。" if tell_name else '')
                gz = None
            elif tgt['pregnant_since']:
                run("UPDATE consorts SET pregnant_since=0 WHERE id=?", (tgt['id'],))
                add_stat(tgt['id'], 'health', -30)
                add_favor(tgt['id'], 10, gain_mult=False)
                victim = f"你小产了。太医说是日常饮食里混了麝香，{who}好狠的心。体质 -30。皇上怜惜你，圣宠 +10。"
                gz = f"{tn}不幸小产，皇上痛惜不已。"
            else:
                add_stat(tgt['id'], 'health', -30)
                victim = f"你近来总觉得身子不适，太医说是熏香里掺了东西。{who}在害你。体质 -30。"
                gz = None
        elif m == 'steal':
            new_bed = atk['id']
            victim = f"原本今晚翻的是你的牌子，却被{who}半路截了去。"
            gz = None
        elif m == 'expose':
            sec = SECRETS[tgt['secret']]
            apply_secret_penalty(tgt['id'], confessed=False)
            victim = f"{an}在皇上面前告发你{sec['name']}。皇上震怒：{sec['penalty']}。"
            gz = f"{an}告发{tn}{sec['name']}，皇上震怒，{sec['penalty']}。"
        elif m == 'witch':
            send_to_cold(tgt['id'])
            victim = f"你宫中搜出了写着皇上生辰八字的巫蛊人偶。百口莫辩，你被打入冷宫。" + \
                     (f"眼线说，是{an}的人动的手。" if tell_name else '')
            gz = f"{tn}宫中搜出巫蛊之物，皇上大怒，废为庶人，打入冷宫。"
        if tgt['user_id']: notify(tgt['id'], victim, 'bad')
        if atk['user_id']: notify(atk['id'], f"你对{tn}的「{cfg['name']}」成了。", 'good')
        if gz: gazette(gz, 'scandal')
        return done('success')

    if caught:
        mood_extra = state()['emperor_mood'] == '震怒'
        m = it['method']
        if m == 'lethal':
            send_to_cold(atk['id'])
            pen = '毒害败露，废位并打入冷宫'
        elif m == 'rumor':
            add_stat(atk['id'], 'virtue', -5); cut_favor(atk['id'], 0.1)
            pen = '德行 -5，圣宠 -10%'
        elif m == 'frame':
            confine(atk['id'], CONFINE_DAYS); cut_favor(atk['id'], 0.15)
            pen = f'禁足 {CONFINE_DAYS} 天，圣宠 -15%'
        elif m == 'poison':
            if atk['rank'] > 1: set_rank(atk['id'], atk['rank'] - 1)
            confine(atk['id'], 3)
            pen = '降一级位分，禁足 3 天'
        elif m == 'steal':
            cut_favor(atk['id'], 0.15); confine(atk['id'], 1)
            pen = '圣宠 -15%，禁足 1 天'
        elif m == 'expose':
            add_stat(atk['id'], 'virtue', -8); cut_favor(atk['id'], 0.15)
            pen = '德行 -8，圣宠 -15%'
        else:  # witch
            send_to_cold(atk['id'])
            pen = '打入冷宫'
        if mood_extra and m != 'witch':
            cut_favor(atk['id'], 0.1); pen += '（皇上正在气头上，圣宠再 -10%）'
        if atk['user_id']: notify(atk['id'], f"你对{tn}的「{cfg['name']}」败露了。{pen}。", 'bad')
        if tgt['user_id']: notify(tgt['id'], f"{an}想对你「{cfg['name']}」，被当场拿住。", 'good')
        if m == 'expose':
            gazette(f"{an}在御前告发{tn}，查无实据，皇上斥其搬弄是非。", 'scandal')
        else:
            gazette(f"{an}意图{cfg['name']}{tn}，事情败露。{pen}。", 'scandal')
        return done('caught')

    if atk['user_id']: notify(atk['id'], f"你对{tn}的「{cfg['name']}」没成，好在没人察觉。")
    return done('fizzle')

def npc_schemes(day):
    """NPC 按性子出手，写进今晚的阴谋队列"""
    for npc in q("SELECT * FROM consorts WHERE npc_key IS NOT NULL AND status='normal' AND aggression>0"):
        if random.random() >= npc['aggression']: continue
        players = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND entered_day<?""", (day,))
        if not players: return
        key = npc['npc_key']
        if key == 'huanghou':
            preg = [p for p in players if p['pregnant_since']]
            if preg: target, method = random.choice(preg), 'poison'
            elif random.random() < 0.4:
                target, method = max(players, key=lambda p: p['favor']), 'rumor'
            else: continue
        elif key == 'huafei':
            grudge = {p['id'] for p in players if (relation(npc['id'], p['id']) or {'affinity': 0})['affinity'] <= -20}
            pool = [p for p in players if p['favor'] >= 60 or p['id'] in grudge]
            if not pool: continue
            target = max(pool, key=lambda p: p['favor'] + (100 if p['id'] in grudge else 0))
            method = 'frame' if target['rank'] >= 3 else 'rumor'
        else:
            pool = [p for p in players if p['favor'] >= 30]
            if not pool: continue
            target, method = random.choice(pool), 'rumor'
        if q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status='pending'",
             (target['id'], day), one=True)['n'] >= INTRIGUE_TARGET_DAILY_MAX:
            continue
        run("INSERT INTO intrigues (day, attacker_id, target_id, method, created_ts) VALUES (?,?,?,?,?)",
            (day, npc['id'], target['id'], method, now_ts()))

def bed_weight(c, day):
    w = 10 + c['favor'] * 0.15 + c['appearance'] * 0.3 + c['talent'] * 0.15 + c['seek_bonus']
    if emperor_art_bonus(c): w += 20
    if c['user_id'] and day - c['entered_day'] <= 3: w += 15   # 皇上喜新
    if c['personality'] == 'charming': w *= 1.15
    return max(1, w)

@atomic
def settle_day():
    with settle_lock:
        st = state()
        day = st['day']
        report = []

        # 先处理之前几天中的毒；当晚新中毒的人不会当晚就死。
        resolve_poison_crises(day)

        # 1. NPC 出手 + 结算阴谋（截宠除外，要等翻牌子）
        npc_schemes(day)
        pend = q("SELECT * FROM intrigues WHERE status='pending' AND day<=? AND method!='steal'", (day,))
        pend = list(pend); random.shuffle(pend)
        for it in pend:
            resolve_intrigue(it)

        # 2. 翻牌子
        cands = [c for c in q("""SELECT * FROM consorts WHERE status='normal' AND rank BETWEEN 1 AND 8
                                 AND pregnant_since=0""") if not is_sick(c)]
        bed = None
        if cands:
            bed = random.choices(cands, weights=[bed_weight(c, day) for c in cands])[0]
            steals = list(q("SELECT * FROM intrigues WHERE status='pending' AND method='steal' AND day<=?", (day,)))
            random.shuffle(steals)
            for it in steals:
                _, new_bed = resolve_intrigue(it, bed['id'] if bed else None)
                if new_bed and bed and new_bed != bed['id']:
                    nb = get_consort(new_bed)
                    if nb['status'] == 'normal' and not nb['pregnant_since']:
                        bed = nb
        if bed:
            bed = get_consort(bed['id'])
            gain = add_favor(bed['id'], 30 + bed['appearance'] * 0.2 + bed['talent'] * 0.1)
            run("UPDATE consorts SET bedded_count=bedded_count+1 WHERE id=?", (bed['id'],))
            run("UPDATE game_state SET last_bed_id=?, last_bed_day=? WHERE id=1", (bed['id'], day))
            gazette(f"敬事房：今夜皇上翻了{display_name(bed)}的牌子。", 'bed')
            if bed['user_id']:
                msg = f"敬事房来传话：今夜皇上翻了你的牌子。圣宠 +{gain}。"
                if bed['age_months'] < FERTILE_BEFORE_AGE * 12 and random.random() < 0.12 + bed['health'] / 1000:
                    run("UPDATE consorts SET pregnant_since=? WHERE id=?", (day, bed['id']))
                    msg += f"……太医诊出了喜脉，{PREGNANCY_DAYS} 天后临盆。"
                    gazette(f"{display_name(bed)}有喜了。", 'birth')
                notify(bed['id'], msg, 'good')
            report.append(f"侍寝：{display_name(bed)}")
            # 另有两位得赏
            others = [c for c in cands if c['id'] != bed['id']]
            for _ in range(min(2, len(others))):
                r = random.choices(others, weights=[bed_weight(c, day) for c in others])[0]
                others.remove(r)
                add_favor(r['id'], 8); add_silver(r['id'], 20)
                if r['user_id']:
                    notify(r['id'], "皇上想起了你，赏了一对玉镯。圣宠 +8，银子 +20。", 'good')

        # 3. 生产
        for c in q("SELECT * FROM consorts WHERE status!='dead' AND pregnant_since>0 AND ?-pregnant_since>=?", (day, PREGNANCY_DAYS)):
            gender = random.choice(['皇子', '公主'])
            n = q("SELECT COUNT(*) n FROM heirs WHERE gender=?", (gender,), one=True)['n']
            ordinal = n + (6 if gender == '皇子' else 3)
            run("INSERT INTO heirs (mother_id, gender, ordinal, born_day) VALUES (?,?,?,?)",
                (c['id'], gender, ordinal, day))
            run("UPDATE consorts SET pregnant_since=0 WHERE id=?", (c['id'],))
            extra = ''
            if c['health'] < 50 and random.random() < 0.3:
                add_stat(c['id'], 'health', -20); extra = '难产了一整夜，元气大伤，体质 -20。'
            label = f"{cn_ordinal(ordinal)}{'阿哥' if gender == '皇子' else '公主'}"
            if gender == '皇子':
                add_favor(c['id'], 100, gain_mult=False)
                if c['rank'] < PLAYER_MAX_RANK and slot_free(c['rank'] + 1, c['id']):
                    set_rank(c['id'], c['rank'] + 1)
                    extra += f"母凭子贵，晋为{display_name(get_consort(c['id']))}。"
            else:
                add_favor(c['id'], 60, gain_mult=False)
            gazette(f"{display_name(c)}诞下{label}。{extra}", 'birth')
            notify(c['id'], f"你诞下了{label}。{extra}", 'good')

        # 4. 晋封（按圣宠高低排队抢名额，每晚每人最多晋一级）
        for c in q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND status IN ('normal','confined')
                      AND rank BETWEEN 1 AND ? ORDER BY favor DESC""", (PLAYER_MAX_RANK - 1,)):
            c = get_consort(c['id'])
            nxt = c['rank'] + 1
            if c['status'] != 'normal': continue
            if c['favor'] < PROMOTE_FAVOR[nxt] or c['virtue'] < PROMOTE_VIRTUE[nxt]: continue
            need_days = 1 if c['rank'] == 1 else MIN_DAYS_AT_RANK
            if day - c['rank_since_day'] < need_days: continue
            if not slot_free(nxt, c['id']):
                if daily_count(c['id'], 'slot_full_notice') == 0:
                    notify(c['id'], f"论圣宠你已够得上{RANK_NAMES[nxt]}，可{RANK_NAMES[nxt]}的位子都满了。")
                    daily_inc(c['id'], 'slot_full_notice')
                continue
            set_rank(c['id'], nxt)
            c2 = get_consort(c['id'])
            gazette(f"圣旨：{full_name(c2)}晋为{display_name(c2)}。", 'decree')
            notify(c['id'], f"圣旨到：晋你为{display_name(c2)}。", 'decree')
            report.append(f"晋封：{display_name(c2)}")

        # 5. 日常：月例、圣宠流失、精力、禁足/冷宫期满、请安
        for c in q("SELECT * FROM consorts WHERE status NOT IN ('xiunv','dead')"):
            c = get_consort(c['id'])
            run('UPDATE consorts SET age_months=age_months+6 WHERE id=?', (c['id'],))   # 一天 = 宫中半年
            if c['status'] != 'cold':
                add_silver(c['id'], STIPEND.get(c['rank'], 0))
            if not c['pregnant_since']:
                decay = math.ceil(c['favor'] * FAVOR_DECAY)
                run("UPDATE consorts SET favor=MAX(0, favor-?) WHERE id=?", (decay, c['id']))
            if c['npc_key'] and c['status'] == 'normal':
                add_favor(c['id'], random.randint(0, 8), gain_mult=False)
            run("UPDATE consorts SET energy=?, seek_bonus=0 WHERE id=?", (ENERGY_MAX, c['id']))
            if c['status'] == 'confined' and c['status_until_day'] <= day:
                run("UPDATE consorts SET status='normal', status_until_day=0 WHERE id=?", (c['id'],))
                if c['user_id']: notify(c['id'], '禁足期满，你又能出门了。', 'good')
            elif c['status'] == 'cold' and c['user_id'] and c['status_until_day'] <= day:
                release_from_cold(c['id'], '皇上念及旧情，')
            if c['user_id'] and c['status'] == 'normal' and c['entered_day'] < day and c['greet_day'] < day:
                missed = c['missed_greet'] + 1
                run("UPDATE consorts SET missed_greet=? WHERE id=?", (missed, c['id']))
                if missed >= 2:
                    add_stat(c['id'], 'virtue', -3)
                    notify(c['id'], f"你已经 {missed} 天没去给皇后请安了，宫里说你恃宠而骄。德行 -3。", 'bad')

        # 6. 进入新的一天
        new_day = day + 1
        mood = random.choices(['大悦', '平和', '烦闷', '震怒'], weights=[15, 55, 22, 8])[0]
        pref = random.choice(ARTS) if new_day % 7 == 1 else st['emperor_pref']
        run("UPDATE game_state SET day=?, last_settle_date=?, emperor_mood=?, emperor_pref=? WHERE id=1",
            (new_day, datetime.now(TZ).date().isoformat(), mood, pref))
        if pref != st['emperor_pref']:
            gazette(f"听养心殿的人说，皇上这几日格外喜欢{pref}。", 'news', day=new_day)
        return report

@atomic
def maybe_settle():
    """后台线程每分钟调用：过了今天的结算时刻且今天还没结算过，就结算一次"""
    now = datetime.now(TZ)
    if past_settle_time(now) and state()['last_settle_date'] != now.date().isoformat():
        settle_day()

# ── 后台 ───────────────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USER and request.form.get('password') == ADMIN_PASS:
            S['admin'] = True
            return redirect(url_for('admin'))
        flash('账号或密码不对。', 'bad')
    return render_template('admin_login.html')

@app.route('/admin')
@admin_required
def admin():
    rows = q("SELECT c.*, u.username FROM consorts c LEFT JOIN users u ON u.id=c.user_id ORDER BY c.user_id IS NULL, c.rank DESC, c.favor DESC")
    pend = q("SELECT * FROM intrigues WHERE status='pending' ORDER BY id")
    return render_template('admin.html', rows=rows, pend=pend, get_consort=get_consort, INTRIGUES=INTRIGUES,
                           SECRETS=SECRETS)

@app.route('/admin/settle', methods=['POST'])
@admin_required
def admin_settle():
    report = settle_day()
    flash('已手动结算一天。' + ('；'.join(report) if report else ''), 'good')
    return redirect(url_for('admin'))

@app.route('/admin/edit/<int:cid>', methods=['POST'])
@admin_required
def admin_edit(cid):
    c = get_consort(cid)
    if not c or c['status'] == 'dead':
        flash('已故角色的宫史不能直接改为存活。', 'bad')
        return redirect(url_for('admin'))
    f = request.form
    try:
        favor, silver, rank = int(f['favor']), int(f['silver']), int(f['rank'])
    except (KeyError, ValueError):
        flash('数值有误。', 'bad')
        return redirect(url_for('admin'))
    status = f.get('status', c['status'])
    if status not in ('normal', 'confined', 'cold', 'xiunv'): status = c['status']
    run("UPDATE consorts SET favor=?, silver=?, rank=?, status=? WHERE id=?",
        (max(0, favor), max(0, silver), max(0, min(9, rank)), status, cid))
    if status in ('confined', 'cold') and c['status'] != status:
        run("UPDATE consorts SET status_until_day=? WHERE id=?",
            (cur_day() + (CONFINE_DAYS if status == 'confined' else COLD_DAYS), cid))
    if rank >= 5 and not c['title']: assign_title(cid)
    flash(f"已修改 {full_name(c)}。", 'good')
    return redirect(url_for('admin'))

@app.route('/admin/decree', methods=['POST'])
@admin_required
def admin_decree():
    text = request.form.get('text', '').strip()
    if text:
        gazette(text, 'decree')
        flash('已发布到邸报。', 'good')
    return redirect(url_for('admin'))

@app.route('/admin/reset', methods=['POST'])
@admin_required
def admin_reset():
    if request.form.get('confirm') != '重开':
        flash('要在框里输入「重开」才会重置。', 'bad')
        return redirect(url_for('admin'))
    for t in ('intrigues', 'messages', 'gazette', 'relations', 'known_secrets', 'inventory', 'heirs',
              'daily_counters', 'consorts', 'game_state'):
        run(f"DELETE FROM {t}")
    if request.form.get('keep_users') != '1':
        run("DELETE FROM users")
    run('UPDATE users SET lethal_ready_day=0')
    init_db()
    flash('已重开一届选秀。', 'good')
    return redirect(url_for('admin'))

@app.route('/admin/logout')
def admin_logout():
    S.pop('admin', None)
    return redirect(url_for('admin_login'))

# ── 年龄、毒害救治与宫史 ─────────────────────────────────────────────────────

def age_text(months):
    return f"{months // 12}岁" + ('半' if months % 12 >= 6 else '')


def palace_date(day):
    return f"宫历{(day - 1) // 2 + 1}年{'上半年' if day % 2 else '下半年'}"


def lethal_block(c, t, day):
    account = q('SELECT lethal_ready_day FROM users WHERE id=?', (c['user_id'],), one=True)
    if account['lethal_ready_day'] > day:
        return f"你上次毒害还没过 {LETHAL_COOLDOWN} 天，第 {account['lethal_ready_day']} 天才能再动手（撤回也不重置）。"
    if day - t['entered_day'] < NEWCOMER_LETHAL_SHIELD:
        return f'她入宫还不满 {NEWCOMER_LETHAL_SHIELD} 天，不能毒害。'
    if t['poisoned_day'] or t['protected_until_day'] >= day:
        return '她正中着毒，或者刚被救回来，这几天动不得。'
    return None


def die(cid, reason):
    c = get_consort(cid)
    if c['status'] == 'dead':
        return
    name = display_name(c)
    run("""UPDATE consorts SET status='dead', death_day=?, death_reason=?, archived_user_id=user_id,
           pregnant_since=0, poisoned_day=0, poison_treatment=0,
           energy=0, seek_bonus=0, status_until_day=0 WHERE id=?""", (cur_day(), reason, cid))
    run("UPDATE intrigues SET status='done', result='void' WHERE status='pending' AND (attacker_id=? OR target_id=?)", (cid, cid))
    notify(cid, f'你因{reason}离世，终年{age_text(c["age_months"])}。可以另建一位秀女重新入宫。', 'bad')
    gazette(f'{name}因{reason}薨逝，终年{age_text(c["age_months"])}。', 'death')


def resolve_poison_crises(day):
    # 只处理之前几天中的毒：当晚刚中毒的人至少有一整天可以请太医
    for c in q("SELECT * FROM consorts WHERE status!='dead' AND poisoned_day>0 AND poisoned_day<?", (day,)):
        if random.random() >= POISON_SURVIVE[min(1, c['poison_treatment'])]:
            die(c['id'], '中毒救治无效')
        else:
            run('''UPDATE consorts SET poisoned_day=0, poison_treatment=0,
                   protected_until_day=?, health=MAX(health,35) WHERE id=?''', (day + RESCUE_PROTECT_DAYS, c['id']))
            notify(c['id'], f'你挺过来了。接下来 {RESCUE_PROTECT_DAYS} 天不会再被毒害，好好静养。', 'good')
            gazette(f'{display_name(c)}脱离险境，留宫静养。', 'news')


@app.route('/treat/<int:tid>', methods=['POST'])
@login_required
def treat(tid):
    """请太医：本人（禁足、冷宫也行）或姐妹/好感 30 以上的人都能请，谁请谁出银子"""
    c, t = g.me, get_consort(tid)
    err = None
    if not t or not t['poisoned_day'] or t['status'] == 'dead':
        err = '她现在不需要请太医。'
    elif c['id'] != tid and not (tid in sisters_of(c['id']) or
                                 (relation(c['id'], tid) or {'affinity': 0})['affinity'] >= 30):
        err = '你与她交情不够，要结为姐妹或好感 30 以上才能替她请太医。'
    elif t['poison_treatment']:
        err = '太医已经在了。'
    elif c['silver'] < TREAT_COST:
        err = f'请太医要 {TREAT_COST} 两银子。'
    if err:
        flash(err, 'bad')
    else:
        add_silver(c['id'], -TREAT_COST)
        run('UPDATE consorts SET poison_treatment=1 WHERE id=?', (tid,))
        text = '太医来了，九成能救回来，下一次结算见分晓。'
        if c['id'] != tid:
            notify(tid, f'{display_name(c)}替你请了太医。{text}', 'good')
            add_affinity(c['id'], tid, 5)
        flash(text, 'good')
    return redirect(url_for('index' if c['id'] == tid else 'social'))


@app.route('/memorial')
@login_required
def memorial():
    c = g.me
    history = q("SELECT * FROM consorts WHERE archived_user_id=? AND status='dead' ORDER BY death_day DESC, id DESC", (S['uid'],))
    return render_template('memorial.html', c=c, history=history)


@app.route('/rebirth', methods=['POST'])
@login_required
def rebirth():
    if g.me['status'] != 'dead':
        return redirect(url_for('index'))
    # 保留旧角色、皇嗣和事件引用；仅释放账号的一人一角约束。
    run("UPDATE consorts SET user_id=NULL WHERE id=? AND status='dead'", (g.me['id'],))
    return redirect(url_for('create'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=int(os.environ.get('PORT', 5024)))
