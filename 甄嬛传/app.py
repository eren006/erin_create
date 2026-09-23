"""甄嬛传·紫禁城 —— 多人宫斗网页游戏

玩家以秀女身份入宫，经殿选后在后宫里争宠、结盟、使计。
皇帝是系统 NPC，每晚固定时刻（SETTLE_HOUR）统一结算：阴谋 → 翻牌子 → 生产 → 晋封 → 月例。
"""
import os, re, json, random, math, time, threading
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session as S, flash, g, has_request_context)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

# ── 访问日志（留存 200 天，按天轮转） ────────────────────────────────────────────
import logging.handlers
_access_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_access_dir, exist_ok=True)
_access_h = logging.handlers.TimedRotatingFileHandler(os.path.join(_access_dir, "access.log"),
                                                     when="midnight", backupCount=200, encoding="utf-8")
_access_h.setFormatter(logging.Formatter("%(message)s"))
_access_log = logging.getLogger("access_log")
_access_log.setLevel(logging.INFO)
_access_log.propagate = False
_access_log.addHandler(_access_h)

@app.after_request
def _write_access_log(resp):
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "-").split(",")[0].strip()
        _access_log.info("%s\t%s\t%s\t%s %s\t%s\t%s" % (
            datetime.now().isoformat(timespec="seconds"), ip, request.environ.get("SERVER_PORT", "-"),
            request.method, request.full_path.rstrip("?"), resp.status_code, S.get('uid') or '-'))
    except Exception:
        pass
    return resp
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
RANK_SLOTS     = {4: 8, 5: 6, 6: 4, 7: 2, 8: 1, 9: 1}                     # 贵人以上有名额，含 NPC
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
POISON_SURVIVE = {0: 0.35, 1: 0.90}   # 没请太医 / 请了太医（病重沿用同一套概率）
CONFINE_DAYS = 2
COLD_DAYS = 5

# ── 老死与病死 ─────────────────────────────────────────────────────────────────
OLD_AGE_START = 600          # 50 岁（600 个月）起，每晚有寿终的可能
OLD_AGE_BASE = 0.003          # 概率 = (年龄 - 50) × 0.3%，体质 ≥60 减半、<30 翻倍
OLD_AGE_REMINDER_START = 660  # 55 岁起，每满 5 岁提醒一句
OLD_AGE_REMINDER_STEP = 60
WEAK_SICK_DAYS = 3            # 连续体质 <25 这么多天，染病
COLD_SICK_CHANCE = 0.05       # 冷宫阴寒，每晚染病概率
EPIDEMIC_INTERVAL = 10        # 全宫时疫，每隔这么多天可能来一次
EPIDEMIC_CHANCE = 0.3         # 到了日子，真发生时疫的概率
POSTPARTUM_SICK_DAYS = 3      # 小产、难产后这么多天内
POSTPARTUM_SICK_CHANCE = 0.10 # ……每晚染病概率
SHI_WORDS = ['孝', '敬', '贞', '惠', '顺', '安', '静', '和']  # 老死时嫔以上追封的谥字

TRUST_START = 20
TRUST_WORDS = [(70, '倚重'), (40, '信得过'), (20, '尚可'), (-1, '存疑')]
TRUSTED_LINE = 50           # 信任到这条线，被散流言/栽赃时圣宠损失减半
NPC_BED_MULT = 0.5          # NPC 翻牌权重打五折，免得宫里原有的妃嫔占掉大半夜晚
AUDIENCE_PER_NIGHT = 2      # 每晚除侍寝外再单独召见几位玩家
LONG_UNSEEN_DAYS = 6        # 这么多天没见过皇上，算"久未见驾"（宫中三年）

TITLE_POOL = list('莞惠安祺瑾婉容贞淳柔懿宁怡颖璟瑶玥韵馨娴淑嘉恬澜宸昭徽祥和敏')

# 承乾宫暂不开放；十三处宫院各四间，初始七间正殿留待晋封。
PALACES = {
    '景仁宫': dict(group='东六宫', desc='东边甬道到此一折，宫门便藏在两株古柏后。庭中砖缝修得齐整，雨后也少见积水。', main='正殿檐下悬着素色宫灯，长窗相对，晨间一眼能望到庭心。'),
    '钟粹宫': dict(group='东六宫', desc='宫墙近处有一道旧钟楼的影子，晴日总要缓缓挪过院落。廊柱漆色稍旧，石阶却被洒扫得发亮。', main='正殿临着宽阶，窗格细密，日光落在地上如一张浅金的网。'),
    '景阳宫': dict(group='东六宫', desc='沿东边长巷走到深处才见宫门，平日少有人经过。院角一架藤萝，入夏便遮住半面白墙。', main='正殿地势略高，推窗可见藤梢，风来时纸页也跟着轻响。'),
    '永和宫': dict(group='东六宫', desc='两重小院以短廊相接，走动时不必绕过露天庭心。旧人爱在廊下晒书，木架至今还留着。', main='正殿梁架素净，靠北有一面旧书格，灯下闻得到淡淡木香。'),
    '延禧宫': dict(group='东六宫', desc='东侧宫墙外有一道排水渠，夏雨一来，隔墙便听得水声。院中几块石板颜色不同，是旧年修补留下的。', main='正殿窗前留着低矮花台，雨丝斜入时，先打湿青砖边沿。'),
    '永寿宫': dict(group='西六宫', desc='宫门内外两道影壁挡住穿堂风，冬天比邻院安稳些。庭里一棵老槐，树荫年年落在同一口石缸上。', main='正殿南窗宽敞，冬日暖光铺到榻前，槐影停在帘外。'),
    '翊坤宫': dict(group='西六宫', desc='西路甬道在宫前放宽，仪仗经过也转得开。台阶两侧的石兽常年有人擦拭，雨里仍泛着润光。', main='正殿进深阔大，重帘垂到近地处，香炉的烟缓缓绕过绣屏。'),
    '储秀宫': dict(group='西六宫', desc='庭院不大，花木却修剪得格外细致。相传从前掌事宫人每季换一种花，后来便成了此处的习惯。', main='正殿门窗漆色鲜亮，檐角投下的阴影正好遮住阶前花盆。'),
    '启祥宫': dict(group='西六宫', desc='出宫门便是往养心殿去的长巷，清晨常听见远处靴声。院里东西两条廊道相通，下雨也能走个来回。', main='正殿前廊深长，窗内铺着旧毡，外头的脚步声到此便轻了。'),
    '长春宫': dict(group='西六宫', desc='宫前两丛丁香开得早，花谢以后仍有绿叶遮着窗。后院石桌一角微缺，宫人说是搬树时不慎磕的。', main='正殿临着花庭，帘钩样式古朴，春风来时满屋都是丁香气。'),
    '咸福宫': dict(group='西六宫', desc='院落方整，廊檐低缓，住在这里的人说话也像放轻了些。西墙根留着一小片苔痕，洒扫时总绕开它。', main='正殿陈设疏朗，一张长案靠着明窗，午后适合静坐理线。'),
    '延庆殿': dict(group='独院', desc='这处院子离热闹的宫巷稍远，门前青石常覆着薄薄落叶。没有穿行的近路，来人多是专程探望。', main='正殿帘色清淡，药柜藏在屏后，窗外竹叶替屋里滤去强光。'),
    '碎玉轩': dict(group='独院', desc='小院缩在一段曲墙后，转过月洞门才见屋舍。墙边一株老梅枝干倾斜，宫人年年替它添一根支木。', main='正殿不甚宽大，窗边恰容一榻，冬日坐着便能看见梅枝。'),
}
HALL_NAMES = dict(main='正殿', east='东配殿', west='西配殿', back='后殿')
HALL_DESCS = dict(
    main='庭院在阶前展开，廊下有人候着，开门便看得到各处灯火。',
    east='早上先见着日头，窗纸渐渐透亮，檐下的露水还没干。',
    west='午后西晒，日影缓缓越过窗棂，热时要把竹帘放低些。',
    back='屋子窄些，挨着宫墙，夜里能听见巡更人在墙外走过。',
)
DISCIPLINE_COOLDOWN = 3


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
    'yinzhen':  dict(name='银针', price=60, usable=False, desc='放在身边：被人下药时成算 -15%，挡下一次就断一根'),
}

# ── 药材（内务府暗柜）──────────────────────────────────────────────────────────
# 药名全部原创。case：什么时候开案——now 当晚 / bed 被翻牌那夜 / diag 被诊出时 / due 临盆那夜 / none 不开案
# eat：是吃进去的（试毒宫人尝得出来）；days：药效持续几晚（含当晚）

DRUGS = {
    'yanzhi':   dict(name='胭脂霰', rank=2, price=80,  case='now', eat=False, days=3,
                     desc='掺在胭脂里，脸上起红疹：容貌 -10，3 天内不被翻牌'),
    'jingmeng': dict(name='惊梦香', rank=2, price=100, case='bed', eat=False, days=3,
                     desc='夜里惊悸：3 天内若被翻牌，侍寝不涨圣宠反扣 30%、信任 -5'),
    'yachan':   dict(name='哑蝉汤', rank=3, price=120, case='now', eat=True, days=3,
                     desc='嗓子坏了：才艺 -8，3 天内被召见、侍寝时只答得出「体谅」'),
    'hanshui':  dict(name='寒水散', rank=3, price=200, case='now', eat=True, days=10,
                     desc='伤胞宫：体质 -25，有孕则小产（安胎药可挡一次），没孕则 10 天内不会有孕'),
    'qingsi':   dict(name='青丝引', rank=4, price=250, case='diag', eat=True, days=0,
                     desc='慢毒：每晚体质 -6，直到被太医诊出；体质掉到 1 就转成中毒'),
    'chunxin':  dict(name='春信丹', rank=4, price=300, case='due', eat=True, days=0,
                     desc='假孕：诊出「喜脉」，到临盆那夜真相大白。皇上若不信她，她要背欺君的罪名'),
    'lihun':    dict(name='离魂草', rank=5, price=500, case='now', eat=True, days=0,
                     desc='致死毒：对方中毒，下一次结算前请了太医九成能活，没请只有三成五。每个账号 7 天一次'),
    'wuming':   dict(name='无名', rank=6, price=800, case='none', eat=False, days=0,
                     desc='出手时再选一种药（离魂草除外），事后不开案，成悬案。每个账号 15 天一次'),
}
DRUG_ENERGY = 2
DRUG_BASE = 0.35
CABINET_SLOTS = 3             # 暗柜每人每天刷几种
LEDGER_CHANCE = 0.10          # 暗柜买药被内务府记一笔的概率
NAMELESS_COOLDOWN = 15
DRUG_NEWCOMER_SHIELD = 5      # 入宫不满 5 天不能被下药、宫人不能被收买
DRUGGED_SHIELD = 2            # 被下药得手后 2 天内不能再被下药
SELF_HAND_PENALTY = 0.15      # 没有内应、自己动手
NEEDLE_BLOCK = 0.15
TASTER_LOYALTY = 80           # 忠心到这里的宫人会替主子试毒
TASTER_CHANCE = 0.20
GIFT_DRUG_CHANCE = 0.05       # 手巧、忠心 ≥80 的宫人每晚献药
DIAGNOSE_CHANCE = 0.70
SLOW_POISON_TICK = 6

# ── 雅趣 ───────────────────────────────────────────────────────────────────────
# 每件作品三步：0 起意（选定就有的那句）→ act 一次 1 打磨 → act 两次 2 成了，进 hobby_items。
# 不给属性、不给圣宠，只给故事和人情——这是底线，见设计文档九点十三节。

HOBBIES = {
    'flower': dict(name='莳花', verb='选一个花种', item_word='花',
        styles=['白山茶', '绿萼梅', '素心兰', '西府海棠', '月季', '丁香'],
        texts=[
            '你在殿角辟出一小块地，种下了{style}的苗。',
            '这几日得空就去看它，浇水、除虫、挪盆晒太阳，眼看着日渐抽枝。',
            '你养了些日子的{style}终于开了，满殿都是若有若无的香气。',
        ]),
    'incense': dict(name='调香', verb='选一个香方打底', item_word='香',
        styles=['沉水', '梨花白', '冷香', '琥珀', '素馨', '龙涎'],
        texts=[
            '你翻出旧年的香谱，挑了{style}这个方子，先配了个底子。',
            '这几天你总在试配比例，多一分则腻，少一分则淡，反反复复地改。',
            '你终于调出了满意的{style}，往后这便是你自己的常用香了。',
        ]),
    'painting': dict(name='书画', verb='挑一个题目', item_word='字画',
        styles=['寒梅傲雪', '秋山行旅', '临兰亭序', '一枝墨竹', '春江水暖', '小楷心经'],
        texts=[
            '你铺开一张素纸，定下了「{style}」这个题目，先打了几遍草稿。',
            '这几日闲下来就练笔，废了的纸攒了一叠，但落笔渐渐稳了。',
            '你终于落定最后一笔，一幅「{style}」就此成了，墨迹犹新。',
        ]),
    'tea': dict(name='茶事', verb='选一款茶试水', item_word='茶',
        styles=['明前龙井', '武夷岩茶', '六安瓜片', '云雾茶', '滇红', '白毫银针'],
        texts=[
            '你收了一份{style}，先净手温杯，试了第一道水。',
            '这几日你换着水温、换着茶具，慢慢琢磨出合口的路数。',
            '你把{style}的冲泡诀窍摸熟了，往后待客也有了自己的一套。',
        ]),
}
HOBBY_ENERGY = 1
HOBBY_FREE_FAVOR = 80          # 圣宠到「偶承恩泽」以下（不含）时，雅趣免精力——失宠时更该有地方可去
HOBBY_UNLOCK_ITEMS = 3         # 做出几件作品后，开放兼修第二样
HOBBY_QUALITIES = ['普通', '精巧', '上品']
HOBBY_GIFT_AFFINITY = 10       # 送自己做的作品，好感 +10（比玉如意 15 克制一点，比普通东西更值钱）
DISPLAY_SLOTS = dict(window='窗边', desk='案头', wall='墙上', tea='茶席')

def roll_hobby_quality(cid, kind):
    """品级只看做过几件同类作品加一点运气，跟属性无关——雅趣拼的是用心，不是天赋"""
    made = q('SELECT COUNT(*) n FROM hobby_items WHERE maker_id=? AND kind=?', (cid, kind), one=True)['n']
    r = random.random() + made * 0.05
    if r >= 0.92: return '上品'
    if r >= 0.60: return '精巧'
    return '普通'

def hobby_item_desc(item):
    return f"{HOBBIES[item['kind']]['name']}·{item['style']}（{item['quality']}）"

def hobby_unlocked_kinds(c):
    return [k for k in c['hobby_kinds'].split(',') if k]

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
    'spy':     dict(name='打探底细', energy=0, silver=30, daily=1, when={'normal'}, target=True, errand=True,
                    desc='派一个宫人去打听对方的秘密（用一次差使，不花精力）'),
    'plead':   dict(name='向皇上求情', energy=1, silver=50, daily=1, when={'normal'}, target=True,
                    desc='为禁足或冷宫中的姐妹求情，缩短日子。成败看皇上对你的信任'),
}

# ── 阴谋 ───────────────────────────────────────────────────────────────────────

INTRIGUES = {
    'rumor':  dict(name='散布流言', silver=30, energy=2, min_rank=1, base=0.55, npc_ok=True,
                   desc='成：对方圣宠 -15%，德行 -3。败露：自己德行 -5，圣宠 -10%'),
    'steal':  dict(name='截宠', silver=60, energy=2, min_rank=1, base=0.50, npc_ok=True,
                   desc='若今晚翻的是对方的牌子，由你顶上。败露：圣宠 -15%，禁足 1 天'),
    'frame':  dict(name='栽赃陷害', silver=100, energy=2, min_rank=2, base=0.45, npc_ok=True,
                   desc='成：对方禁足 2 天，圣宠 -20%。败露：自己禁足 2 天'),
    'drug':   dict(name='下药', silver=0, energy=DRUG_ENERGY, min_rank=2, base=DRUG_BASE, npc_ok=False,
                   desc='用手里的药，交给对方宫里的内应去下，或者自己动手'),
    'expose': dict(name='告发秘密', silver=50, energy=2, min_rank=1, base=0.70, npc_ok=False,
                   desc='需先探到对方的秘密。皇上信不信看你的信任。成：按秘密处罚对方，你信任 +5。不信：自己德行 -8，圣宠 -15%，信任 -10'),
    'witch':  dict(name='构陷巫蛊', silver=300, energy=3, min_rank=4, base=0.35, npc_ok=True,
                   desc='成：对方打入冷宫。败露：打入冷宫的是你'),
    'punish': dict(name='发落宫人', silver=50, energy=2, min_rank=5, base=0.50, npc_ok=False,
                   desc='找个由头，把对方宫里一个宫人拖去慎刑司。要比对方高两级以上，每 7 天一次；'
                        '对方会知道是你。成：那个宫人没了，对方全宫宫人忠心 -5。败露：德行 -8，信任 -10'),
}
INTRIGUE_TARGET_DAILY_MAX = 2
LEGACY_INTRIGUE_NAMES = dict(lethal='毒害', poison='暗下麝香')

def intrigue_label(it):
    if it['method'] == 'drug' and it['drug'] in DRUGS:
        used = it['item_used']
        return '下药·' + (f"{DRUGS[used]['name']}（{DRUGS[it['drug']]['name']}）" if used == 'wuming' else DRUGS[it['drug']]['name'])
    return INTRIGUES[it['method']]['name'] if it['method'] in INTRIGUES else LEGACY_INTRIGUE_NAMES.get(it['method'], it['method'])

# ── 教引嬷嬷 ───────────────────────────────────────────────────────────────────
# 新人引导线：guide_step 走到第几步（-1=跳过，len(GUIDE_STEPS)=走完了），
# guide_progress 记当前这一步已经做到的子项，全做到才算这一步过关、发银子、进下一步。
# reqs 是「子项组」的列表，每组只要占到其中一个 key 就算过；guide_tips 是遇事提点的去重记录。

GUIDE_REWARD = 10
REQ_LABELS = dict(maid='挑一个宫人、赐名', greet='去景仁宫请安', study='修习一次才艺', garden='去御花园走走',
                  visit='串一次门', letter='写一封信', gazette='看一次邸报', eyes='安插眼线', inspect='清查一次宫人')

GUIDE_STEPS = [
    dict(title='入宫当天', reqs=[frozenset({'maid'})],
         teach='内务府会按你的位分给宫人份例，往后不少事都要靠宫人跑腿；精力每天 5 点，例银按位分每晚发。',
         open_line='「小主头一日进宫，先别急着往养心殿跑。规矩没学会，见了皇上也是白见。去内务府挑个贴身的人，往后有些跑腿的事，还得靠她。」',
         close_line='「像个样子了。」'),
    dict(title='第一天', reqs=[frozenset({'greet'}), frozenset({'study'}), frozenset({'garden'})],
         teach='请安断了两天，德行会掉；场景里的选择看的是属性加一点运气，不是瞎选。',
         open_line='「今日去景仁宫请个安，皇后娘娘瞧着和气，规矩却不能少。得空再练一门才艺，御花园也去走走，散散心。」',
         close_line='「老奴多嘴一句：宫里送来的吃食，入口前多看一眼。」'),
    dict(title='第二天', reqs=[frozenset({'visit'}), frozenset({'letter'}), frozenset({'gazette'})],
         teach='好感够了能结拜姐妹，姐妹会让算计你的人更难得手；邸报上的事，六宫都看得到。',
         open_line='「串串门，跟人处熟络些；写封信，宫里书信往来都是有规矩的。邸报也该看看，宫里出了什么事，一目了然。」',
         close_line='「多个照应，总比孤零零一个人强。」'),
    dict(title='第三天', reqs=[frozenset({'eyes', 'inspect'})],
         teach='宫里不是人人都安分，你身上还有几天新人保护，趁这几天把眼线安插好。',
         open_line='「老奴在这宫里三十年，见过比小主聪明的，也见过比小主得宠的。活到最后的，都是沉得住气的。去安插个眼线，或是清查一下宫人，学着防备些。」',
         close_line='「往后的路，小主自己走吧。有事只管来找老奴。」'),
]

def guide_start(cid):
    run("UPDATE consorts SET guide_step=0, guide_progress='[]', guide_tips='[]' WHERE id=?", (cid,))
    notify(cid, f"许嬷嬷凑上前来：{GUIDE_STEPS[0]['open_line']}", 'info')

def guide_mark(cid, key):
    c = get_consort(cid)
    if not c or not c['user_id'] or not (0 <= c['guide_step'] < len(GUIDE_STEPS)): return
    try: progress = set(json.loads(c['guide_progress'] or '[]'))
    except ValueError: progress = set()
    if key in progress: return
    progress.add(key)
    step = GUIDE_STEPS[c['guide_step']]
    if not all(progress & req for req in step['reqs']):
        run("UPDATE consorts SET guide_progress=? WHERE id=?", (json.dumps(sorted(progress)), cid))
        return
    add_silver(cid, GUIDE_REWARD)
    new_step = c['guide_step'] + 1
    run("UPDATE consorts SET guide_step=?, guide_progress='[]' WHERE id=?", (new_step, cid))
    line = GUIDE_STEPS[new_step]['open_line'] if new_step < len(GUIDE_STEPS) else '「往后的路，小主自己走吧。有事只管来找老奴。」'
    notify(cid, f"许嬷嬷{step['close_line']}银子 +{GUIDE_REWARD} 两。{line}", 'good')

def guide_view(c):
    if not (0 <= c['guide_step'] < len(GUIDE_STEPS)): return None
    step = GUIDE_STEPS[c['guide_step']]
    try: progress = set(json.loads(c['guide_progress'] or '[]'))
    except ValueError: progress = set()
    checklist = [(' / '.join(REQ_LABELS[k] for k in sorted(req)), bool(progress & req)) for req in step['reqs']]
    return dict(title=step['title'], teach=step['teach'], open_line=step['open_line'], checklist=checklist)

def guide_tip(cid, key, line):
    c = get_consort(cid)
    if not c or not c['user_id']: return
    try: seen = json.loads(c['guide_tips'] or '[]')
    except ValueError: seen = []
    if key in seen: return
    run("UPDATE consorts SET guide_tips=? WHERE id=?", (json.dumps(seen + [key], ensure_ascii=False), cid))
    notify(cid, f"许嬷嬷：{line}", 'info')

# ── 场景（带选择的小剧情）─────────────────────────────────────────────────────
# 每个选项：stat 为空=必成；否则 属性值 + 随机 0~40 ≥ dc 算成（dc 70 时属性 50 约五成）。
# win/lose 里的键：favor 圣宠 / trust 信任 / virtue 德行 / health 体质 / appearance 容貌 /
# talent 才艺 / silver 银子 / seek 今晚翻牌加成 / huafei 华妃对你的好感

SCENE_ROLL = 40

SCENES = {
    'garden_emperor': dict(place='御花园', text='杏花树下，你一抬头，正撞见皇上负手而立，身边只跟着苏培盛。皇上也看见了你。', opts=[
        dict(text='借眼前的景致吟两句诗', stat='talent', dc=70,
             win=dict(favor=18, seek=15), win_text='皇上接了下半句，笑说你是个妙人。',
             lose=dict(favor=3), lose_text='诗吟到一半卡了壳，皇上倒也没说什么，只点了点头。'),
        dict(text='规规矩矩行礼问安', stat=None,
             win=dict(favor=8), win_text='皇上问了几句起居，便往前走了。'),
        dict(text='折一枝杏花奉上', stat='appearance', dc=72,
             win=dict(favor=15, seek=20), win_text='皇上接过花，多看了你两眼。',
             lose=dict(favor=-3, virtue=-1), lose_text='苏培盛轻咳一声：「小主，御花园的花可折不得。」'),
    ]),
    'garden_huafei': dict(place='御花园', text='华妃的轿辇迎面而来。她抬手让轿子停下，居高临下地看着你：「见了本宫，怎么不跪？」', opts=[
        dict(text='立刻跪下请罪', stat=None,
             win=dict(health=-4), win_text='你跪在石子路上，直到华妃的轿辇走远。'),
        dict(text='「方才正要去给皇后娘娘请安，没瞧见娘娘。」', stat='scheme', dc=70,
             win=dict(virtue=2), win_text='华妃听到「皇后」二字，冷哼一声走了。',
             lose=dict(health=-10, huafei=-10), lose_text='「拿皇后压本宫？」华妃罚你跪了一个时辰。'),
        dict(text='不卑不亢地行礼，不跪', stat='virtue', dc=80,
             win=dict(favor=6, trust=4, huafei=-15), win_text='宫人把这事传开了，皇上听说后反倒说你有骨气。',
             lose=dict(health=-12, huafei=-20), lose_text='华妃大怒，罚你在日头底下跪到晌午。'),
    ]),
    'greet_huafei': dict(place='景仁宫', text='请安时，华妃把茶盏往桌上一放：「妹妹这身衣裳，倒比皇后娘娘还鲜亮。」满殿都安静了。', opts=[
        dict(text='起身谢罪，说回去就换', stat=None,
             win=dict(virtue=1), win_text='皇后打了个圆场，这事就过去了。'),
        dict(text='「是皇后娘娘前日赏的料子。」', stat='scheme', dc=72,
             win=dict(favor=4, virtue=1), win_text='皇后微微一笑。华妃脸色难看，却说不出话来。',
             lose=dict(virtue=-2, huafei=-10), lose_text='皇后并没有接你的话，场面更尴尬了。'),
        dict(text='「娘娘说笑了，嫔妾哪敢与娘娘相比。」', stat='virtue', dc=65,
             win=dict(virtue=3), win_text='皇后夸你识大体。',
             lose=dict(health=-5), lose_text='华妃不依不饶，你被罚在廊下站了半个时辰。'),
    ]),
    'seek_angry': dict(place='养心殿', text='养心殿里一地碎瓷。皇上头也不抬：「谁让你来的？」', opts=[
        dict(text='放下汤羹，悄悄退下', stat=None,
             win=dict(), win_text='苏培盛朝你感激地点了点头。'),
        dict(text='软语宽慰，替皇上揉一揉额角', stat='appearance', dc=75,
             win=dict(favor=15, seek=10), win_text='皇上的脸色慢慢缓和下来，留你坐了一会儿。',
             lose=dict(favor=-8), lose_text='「朕说了不见人！」你被赶了出来。'),
        dict(text='劝皇上以龙体为重', stat='virtue', dc=75,
             win=dict(favor=6, trust=8), win_text='皇上叹了口气：「满宫里，也就你还敢说这话。」',
             lose=dict(favor=-8), lose_text='皇上冷冷看你一眼：「后宫不得干政。」'),
    ]),
}

# 侍寝和召见共用的问题池。三个选项分三路：体谅（稳）、讨巧（多涨圣宠）、直言（多涨信任、也可能碰钉子）
AUDIENCE_PROMPTS = [
    dict(ask='「人人都说朕偏心，你也这样想？」', opts=[
        dict(text='体谅：「皇上心里装着天下，偏一点也是常情。」', stat='virtue', dc=65,
             win=dict(favor=8, trust=4), win_text='皇上笑了笑，没再说什么。', lose=dict(favor=2), lose_text='皇上「嗯」了一声，似乎没听进去。'),
        dict(text='讨巧：「皇上若偏心，就偏着嫔妾吧。」', stat='appearance', dc=70,
             win=dict(favor=18), win_text='皇上捏了捏你的脸：「就你嘴甜。」', lose=dict(favor=-4, trust=-2), lose_text='皇上淡淡道：「油嘴滑舌。」'),
        dict(text='直言：「是有些。翊坤宫那边，旁人确有怨言。」', stat='scheme', dc=72,
             win=dict(favor=2, trust=10), win_text='皇上沉默片刻：「难得有人跟朕说实话。」', lose=dict(favor=-10, trust=3), lose_text='皇上沉下脸来。可这话，他记住了。'),
    ]),
    dict(ask='「前朝为西北军饷吵了一整天，朕头疼。」', opts=[
        dict(text='体谅：替皇上揉额角，一句不提政事', stat='virtue', dc=60,
             win=dict(favor=10, trust=3), win_text='皇上闭着眼，眉头慢慢松开了。', lose=dict(favor=3), lose_text='皇上还是心事重重。'),
        dict(text='讨巧：讲几件宫里的趣事逗皇上笑', stat='talent', dc=70,
             win=dict(favor=15), win_text='皇上笑出了声：「你这张嘴。」', lose=dict(favor=2), lose_text='皇上勉强笑了笑。'),
        dict(text='直言：「后宫不得干政，可嫔妾听说……」', stat='scheme', dc=78,
             win=dict(trust=12), win_text='皇上坐直了身子，听你说完，若有所思。', lose=dict(favor=-12, trust=-3), lose_text='「后宫不得干政，你忘了？」'),
    ]),
    dict(ask='「你入宫这些日子，过得可好？」', opts=[
        dict(text='体谅：「有皇上惦记，一切都好。」', stat='virtue', dc=60,
             win=dict(favor=8, trust=3), win_text='皇上点点头，握了握你的手。', lose=dict(favor=2), lose_text='皇上似乎有些心不在焉。'),
        dict(text='讨巧：「就是皇上来得太少了。」', stat='appearance', dc=70,
             win=dict(favor=16), win_text='皇上笑道：「那朕往后常来。」', lose=dict(favor=-3), lose_text='皇上皱了皱眉：「朕还要顾着六宫。」'),
        dict(text='直言：说出宫里受过的委屈', stat='virtue', dc=72,
             win=dict(favor=4, trust=10), win_text='皇上听完，沉声道：「朕知道了。」', lose=dict(trust=-4), lose_text='「朕不爱听这些抱怨。」'),
    ]),
    dict(ask='「朕新得了一幅字，你来看看好不好。」', opts=[
        dict(text='体谅：「皇上的眼光，自然是好的。」', stat=None,
             win=dict(favor=5), win_text='皇上满意地把字收了起来。'),
        dict(text='讨巧：「嫔妾斗胆，为皇上题两句。」', stat='talent', dc=72,
             win=dict(favor=14, trust=3), win_text='皇上抚掌：「好！」', lose=dict(favor=-2), lose_text='题得平平，皇上没说什么。'),
        dict(text='直言：「这字……怕是赝品。」', stat='talent', dc=80,
             win=dict(favor=5, trust=15), win_text='皇上愣了愣，大笑：「果然瞒不过你。朕是故意试你的。」', lose=dict(favor=-10), lose_text='皇上不悦：「你懂什么。」'),
    ]),
]

# 侍寝时额外多一个选项：替身在禁足或冷宫的姐妹求情，成败只看信任（信任 + 随机 0~40 ≥ 50）
PLEAD_IN_BED = dict(text='替身陷困境的姐妹求情', stat='trust', dc=50, plead=True,
                    win=dict(), win_text='皇上沉吟片刻：「罢了，看在你的面上。」',
                    lose=dict(trust=-3), lose_text='皇上翻了个身：「这事你别管。」')

EFFECT_NAMES = dict(favor='圣宠', trust='信任', virtue='德行', health='体质',
                    appearance='容貌', talent='才艺', silver='银子')

# ── NPC ────────────────────────────────────────────────────────────────────────

NPCS = [
    dict(npc_key='huanghou', hall='main', surname='乌拉那拉', given='宜修', title='', rank=9, palace='景仁宫',
         appearance=62, talent=70, scheme=92, virtue=80, health=75, favor=250, aggression=0.35,
         intro='中宫皇后，待人宽和，六宫都说她贤德。'),
    dict(npc_key='huafei', hall='main', surname='年', given='世兰', title='华', rank=6, palace='翊坤宫',
         appearance=90, talent=55, scheme=70, virtue=30, health=85, favor=420, aggression=0.4,
         intro='宠冠六宫，兄长年羹尧手握重兵。最见不得别人得宠。'),
    dict(npc_key='duanfei', hall='main', surname='齐', given='月宾', title='端', rank=6, palace='延庆殿',
         appearance=55, talent=60, scheme=65, virtue=75, health=20, favor=40, aggression=0,
         intro='常年卧病，深居简出，却什么都看在眼里。'),
    dict(npc_key='qifei', hall='main', surname='李', given='静言', title='齐', rank=6, palace='长春宫',
         appearance=58, talent=35, scheme=30, virtue=50, health=70, favor=90, aggression=0.05,
         intro='三阿哥生母，心直口快，常被人当枪使。'),
    dict(npc_key='jingpin', hall='main', surname='冯', given='若昭', title='敬', rank=5, palace='咸福宫',
         appearance=60, talent=58, scheme=50, virtue=70, health=72, favor=110, aggression=0,
         intro='性子温吞，与人为善，在宫里熬了许多年。'),
    dict(npc_key='lipin', hall='main', surname='费', given='云烟', title='丽', rank=5, palace='启祥宫',
         appearance=75, talent=40, scheme=40, virtue=35, health=75, favor=170, aggression=0.12,
         intro='华妃跟前的人，嘴快心浅。'),
    dict(npc_key='caoguiren', hall='east', surname='曹', given='琴默', title='', rank=4, palace='启祥宫',
         appearance=62, talent=55, scheme=80, virtue=45, health=65, favor=150, aggression=0.2,
         intro='温宜公主生母，华妃的智囊，笑里藏刀。'),
    dict(npc_key='xinchangzai', hall='east', surname='吕', given='盈风', title='欣', rank=3, palace='储秀宫',
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
        dict(text='静立不动，任蝴蝶停着', stat='virtue', bonus=5,
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
                     'archived_user_id': 'INTEGER',
                     'trust': 'INTEGER NOT NULL DEFAULT 20',
                     'pending_scene': "TEXT NOT NULL DEFAULT ''",
                     'recap_seen_day': 'INTEGER NOT NULL DEFAULT 0',
                     'last_audience_day': 'INTEGER NOT NULL DEFAULT 0',
                     'last_promote_day': 'INTEGER NOT NULL DEFAULT 0',
                     'dianxuan_quote': "TEXT NOT NULL DEFAULT ''",
                     'maid_offer': "TEXT NOT NULL DEFAULT ''",
                     'maid_event': "TEXT NOT NULL DEFAULT ''",
                     'punish_ready_day': 'INTEGER NOT NULL DEFAULT 0',
                     'maid_punished_day': 'INTEGER NOT NULL DEFAULT 0',
                     'drugged_day': 'INTEGER NOT NULL DEFAULT 0',
                     'drug_ledger': 'INTEGER NOT NULL DEFAULT 0',
                     'hall': "TEXT NOT NULL DEFAULT ''",
                     'discipline_ready_day': 'INTEGER NOT NULL DEFAULT 0',
                     'housing_waiting': "TEXT NOT NULL DEFAULT ''",
                     'hobby_kinds': "TEXT NOT NULL DEFAULT ''",
                     'guide_step': 'INTEGER NOT NULL DEFAULT 0',
                     'guide_progress': "TEXT NOT NULL DEFAULT '[]'",
                     'guide_tips': "TEXT NOT NULL DEFAULT '[]'",
                     'ill_day': 'INTEGER NOT NULL DEFAULT 0',
                     'ill_treatment': 'INTEGER NOT NULL DEFAULT 0',
                     'weak_days': 'INTEGER NOT NULL DEFAULT 0',
                     'postpartum_until': 'INTEGER NOT NULL DEFAULT 0',
                     'heir_event': "TEXT NOT NULL DEFAULT ''"},
        'heirs': {'caretaker_id': 'INTEGER NOT NULL DEFAULT 0',
                  'personality': "TEXT NOT NULL DEFAULT ''",
                  'study': 'INTEGER NOT NULL DEFAULT 20',
                  'riding': 'INTEGER NOT NULL DEFAULT 20',
                  'virtue': 'INTEGER NOT NULL DEFAULT 20',
                  'health': 'INTEGER NOT NULL DEFAULT 60',
                  'favor': 'INTEGER NOT NULL DEFAULT 0',
                  'mother_affinity': 'INTEGER NOT NULL DEFAULT 50',
                  'caretaker_affinity': 'INTEGER NOT NULL DEFAULT 50',
                  'zhuazhou': "TEXT NOT NULL DEFAULT ''",
                  'seen_events': "TEXT NOT NULL DEFAULT '[]'",
                  'foster_request_to': 'INTEGER NOT NULL DEFAULT 0',
                  'visit_banned': 'INTEGER NOT NULL DEFAULT 0',
                  'concealed': 'INTEGER NOT NULL DEFAULT 0',
                  'reclaim_after_day': 'INTEGER NOT NULL DEFAULT 0'},
        'cases': {'convicted_id': 'INTEGER NOT NULL DEFAULT 0', 'wrongful': 'INTEGER NOT NULL DEFAULT 0'},
        'intrigues': {'drug': "TEXT NOT NULL DEFAULT ''",
                      'agent_maid_id': 'INTEGER NOT NULL DEFAULT 0'},
        'letters': {'hobby_item_id': 'INTEGER NOT NULL DEFAULT 0',
                    'is_broadcast': 'INTEGER NOT NULL DEFAULT 0',
                    'broadcast_id': 'INTEGER NOT NULL DEFAULT 0',
                    'claimed': 'INTEGER NOT NULL DEFAULT 1',
                    'deleted_by_from': 'INTEGER NOT NULL DEFAULT 0',
                    'deleted_by_to': 'INTEGER NOT NULL DEFAULT 0'},
        'messages': {'is_night': 'INTEGER NOT NULL DEFAULT 0'},
        'gazette': {'is_night': 'INTEGER NOT NULL DEFAULT 0'},
        'game_state': {'last_bed_pool': "TEXT NOT NULL DEFAULT '[]'"},
        'users': {'lethal_ready_day': 'INTEGER NOT NULL DEFAULT 0',
                  'nameless_ready_day': 'INTEGER NOT NULL DEFAULT 0',
                  'banned': 'INTEGER NOT NULL DEFAULT 0'}
    }
    for table, fields in migrations.items():
        existing = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
        for field, definition in fields.items():
            if field not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
                if table == 'consorts' and field == 'guide_step':
                    # 教引嬷嬷是新功能，老档里已经存在的角色（不管在不在冷宫、死没死）都已经过了新人这一段，
                    # 直接跳过；只有这次迁移之后新入宫、新重生的角色才会在 dianxuan()/rebirth() 里显式置 0
                    db.execute("UPDATE consorts SET guide_step=-1")
                if table == 'heirs' and field == 'caretaker_id':
                    # 老档里的皇嗣一律先算生母在带，之后 heir_growth_tick 该抓周的会照常判
                    db.execute("UPDATE heirs SET caretaker_id=mother_id WHERE caretaker_id=0")
    retire_musk(db)
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
    for n in NPCS:
        db.execute("UPDATE consorts SET hall=? WHERE npc_key=? AND hall='' AND status NOT IN ('cold','dead')",
                   (n['hall'], n['npc_key']))
    db.commit()
    db.close()
    with app.app_context():
        housing_sync()      # 老存档里的玩家第一次启动时分好住处；之后每次都是空操作

def retire_musk(db):
    """v1.4：「暗下麝香」「毒害」并入「下药」。手里的麝香按 200 两退钱，还没结算的旧计策撤回退款（幂等）"""
    row = db.execute("SELECT day FROM game_state WHERE id=1").fetchone()
    day, ts = (row[0] if row else 1), now_ts()
    refunds = {}
    for cid, qty in db.execute("SELECT consort_id, qty FROM inventory WHERE item_key='shexiang' AND qty>0").fetchall():
        refunds[cid] = refunds.get(cid, 0) + 200 * qty
    for iid, cid, paid, item in db.execute("""SELECT id, attacker_id, silver_paid, item_used FROM intrigues
                                             WHERE status='pending' AND method IN ('poison','lethal')""").fetchall():
        refunds[cid] = refunds.get(cid, 0) + paid + (200 if item == 'shexiang' else 0)
        db.execute("UPDATE intrigues SET status='cancelled' WHERE id=?", (iid,))
    db.execute("DELETE FROM inventory WHERE item_key='shexiang'")
    for cid, amt in refunds.items():
        if not amt: continue
        db.execute("UPDATE consorts SET silver=silver+? WHERE id=?", (amt, cid))
        db.execute("INSERT INTO messages (consort_id, day, kind, text, created_ts) VALUES (?,?,?,?,?)",
                   (cid, day, 'info', f'内务府不再私下卖麝香，「暗下麝香」「毒害」改成了「下药」。你手里的麝香和还没办的事折成 {amt} 两银子退给你了。', ts))

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
    return c['health'] < 25 or bool(c['poisoned_day']) or bool(c['ill_day'])

def arts_of(c):
    try: return json.loads(c['arts'] or '{}')
    except Exception: return {}

def settling():
    return getattr(g, 'settling', False)

def notify(cid, text, kind='info'):
    run("INSERT INTO messages (consort_id, day, kind, text, is_night, created_ts) VALUES (?,?,?,?,?,?)",
        (cid, cur_day(), kind, text, int(settling()), now_ts()))

def gazette(text, kind='news', day=None):
    run("INSERT INTO gazette (day, kind, text, is_night, created_ts) VALUES (?,?,?,?,?)",
        (day or cur_day(), kind, text, int(settling()), now_ts()))

def night_mark(cid, key, **data):
    """夜间结算里记下某人经历了什么，结算末尾据此挑一句口谕；白天调用无效"""
    if settling() and cid:
        g.night_events.setdefault(cid, {})[key] = data

def add_trust(cid, delta):
    run("UPDATE consorts SET trust=MAX(0, MIN(100, trust+?)) WHERE id=?", (int(delta), cid))

def trust_word(t):
    for th, w in TRUST_WORDS:
        if t >= th: return w
    return TRUST_WORDS[-1][1]

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
    old = get_consort(cid)['rank']
    run("UPDATE consorts SET rank=?, rank_since_day=? WHERE id=?", (new_rank, reason_day or cur_day(), cid))
    if new_rank > old:
        run("UPDATE consorts SET last_promote_day=? WHERE id=?", (cur_day(), cid))
    c = get_consort(cid)
    if new_rank >= 5 and not c['title']:
        assign_title(cid)
    housing_sync(fill_main=not settling())

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
           favor=0, pregnant_since=0, seek_bonus=0, hall='', housing_waiting='', title=? WHERE id=?""",
        (cur_day() + COLD_DAYS, c['rank'], c['title'] if c['npc_key'] else '', cid))
    housing_sync(fill_main=not settling())
    guide_tip(cid, 'cold', '「冷宫的日子不好熬，但没到头呢。多闭门自省，未必没有转机。」')

def release_from_cold(cid, reason):
    c = get_consort(cid)
    if c['npc_key'] or c['status'] == 'dead': return   # NPC 进了冷宫就不再出来
    new_rank = min(2, max(1, c['rank_before_cold']))
    run("""UPDATE consorts SET status='normal', status_until_day=0, rank=?, rank_since_day=?,
           favor=20, palace='', hall='', housing_waiting='' WHERE id=?""", (new_rank, cur_day(), cid))
    housing_sync(fill_main=not settling())
    c = get_consort(cid)
    night_mark(cid, 'cold_release')
    notify(cid, f"{reason}你被放出冷宫，复为{RANK_NAMES[new_rank]}。", 'decree')
    gazette(f"{reason}{full_name(c)}出冷宫，复为{display_name(c)}。", 'decree')

def emperor_art_bonus(c):
    arts = arts_of(c)
    return arts.get(state()['emperor_pref'], 0) >= ART_MASTERY

# ── 违禁词过滤 ─────────────────────────────────────────────────────────────────

BLOCKLIST_PATH = os.path.join(BASE_DIR, "blocklist.txt")
MODERATION_LOG = os.path.join(BASE_DIR, "logs", "moderation.log")
_blocklist_cache = {'mtime': None, 'words': []}
_NOISE = re.compile(r'[\s\W_]+')

def _blocked_words():
    try:
        mtime = os.path.getmtime(BLOCKLIST_PATH)
    except OSError:
        return []
    if _blocklist_cache['mtime'] != mtime:
        with open(BLOCKLIST_PATH, encoding='utf-8') as f:
            words = [_NOISE.sub('', ln.strip().lower()) for ln in f if ln.strip() and not ln.lstrip().startswith('#')]
        _blocklist_cache.update(mtime=mtime, words=[w for w in words if w])
    return _blocklist_cache['words']

def blocked_hit(field, text):
    """文本命中违禁词返回该词，并写入 moderation.log；干净返回 None。去掉空格标点后再比，防止拆字规避。"""
    flat = _NOISE.sub('', (text or '').lower())
    for w in _blocked_words():
        if w in flat:
            try:
                os.makedirs(os.path.dirname(MODERATION_LOG), exist_ok=True)
                with open(MODERATION_LOG, 'a', encoding='utf-8') as f:
                    f.write(f"{datetime.now(TZ).isoformat(timespec='seconds')}\tuid={S.get('uid') if has_request_context() else '-'}\t{field}\t命中「{w}」\t{text}\n")
            except OSError:
                pass
            return w
    return None

BLOCKED_MSG = '内容含有不允许的字词，请修改后再试。'

# ── 登录 ───────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    @atomic
    def wrapper(*a, **kw):
        if not S.get('uid'):
            return redirect(url_for('login'))
        u = q("SELECT banned FROM users WHERE id=?", (S['uid'],), one=True)
        if u is None or u['banned']:
            S.pop('uid', None)
            flash('该账号已被停用，如有异议请联系管理员。', 'bad')
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
               favor_word=favor_word, trust_word=trust_word, residence_name=residence_name, HALL_NAMES=HALL_NAMES, ITEMS=ITEMS, DRUGS=DRUGS, HOBBIES=HOBBIES, DISPLAY_SLOTS=DISPLAY_SLOTS,
               HOBBY_ENERGY=HOBBY_ENERGY, HOBBY_UNLOCK_ITEMS=HOBBY_UNLOCK_ITEMS, daily_count=daily_count, intrigue_label=intrigue_label, FAMILIES=FAMILIES, PERSONALITIES=PERSONALITIES, age_text=age_text, palace_date=palace_date,
               HEIR_STATS=HEIR_STATS, HEIR_PERSONALITIES=HEIR_PERSONALITIES, heir_age_days=heir_age_days,
               poison_deadline=lambda ts: datetime.fromtimestamp(ts, TZ).strftime('%m月%d日 %H:%M'))
    try:
        ctx['gs'] = state()
        ctx['next_settle'] = next_settle_text()
        me = getattr(g, 'me', None)
        ctx['open_cases_count'] = q("SELECT COUNT(DISTINCT c.id) FROM cases c LEFT JOIN case_suspects s ON s.case_id=c.id WHERE c.status='open' AND (c.victim_id=? OR s.consort_id=?)", (me['id'], me['id']), one=True)[0] if me else 0
        ctx['unread_letters'] = q("SELECT COUNT(*) n FROM letters WHERE to_id=? AND is_read=0 AND deleted_by_to=0",
                                  (me['id'],), one=True)['n'] if me else 0
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
            if u['banned']:
                flash('该账号因违规已被停用，如有异议请联系管理员。', 'bad')
                return render_template('login.html')
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
        elif blocked_hit('账号', username):
            flash(BLOCKED_MSG, 'bad')
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
        elif blocked_hit('姓名', surname + given):
            err = BLOCKED_MSG
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
        total, reactions, risky_huafei, quote = 0, [], False, ''

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
            quote = quote or opt['text']      # 记下第一问的回答，入宫周年时皇上会提起
            reactions.append(dict(ask=qu['ask'], who=qu['who'], answer=opt['text'], react=opt['react']))
        total += FAMILIES[c['family']]['dx']
        total = int(round(total))
        rank = next(r for th, r in DIANXUAN_TIERS if total >= th)
        if not slot_free(rank):     # 贵人满员时，殿选再出色也只能先封常在
            rank -= 1
        day = cur_day()
        room = empty_residence((('east', 'west'), ('back',)))
        if room is None:
            flash('宫中屋舍暂满，且候内务府另行传唤。', 'info')
            return redirect(url_for('dianxuan'))
        palace, hall = room
        favor = {4: 40, 3: 20, 2: 10, 1: 0}[rank]
        run("""UPDATE consorts SET status='normal', rank=?, rank_since_day=?, palace=?, hall=?, favor=?,
               entered_day=?, dianxuan_score=?, energy=?, trust=?, last_audience_day=?, recap_seen_day=?,
               dianxuan_quote=? WHERE id=?""",
            (rank, day, palace, hall, favor, day, total, ENERGY_MAX, TRUST_START, day, day - 1, quote, c['id']))
        title = ''
        if rank >= 4 or (rank == 3 and random.random() < 0.3):
            title = assign_title(c['id'])
        c = get_consort(c['id'])
        decree = f"{FAMILIES[c['family']]['name']}{full_name(c)}，留牌子，" \
                 f"{'赐封号「' + title + '」，' if title else ''}封为{display_name(c)}，赐居{palace}{HALL_NAMES[hall]}。"
        gazette(f"殿选：{decree}", 'decree')
        notify(c['id'], f"殿选中选。{decree}", 'decree')
        guide_start(c['id'])
        if risky_huafei:
            add_affinity(c['id'], q("SELECT id FROM consorts WHERE npc_key='huafei'", one=True)['id'], -30)
        return render_template('dianxuan_result.html', c=c, reactions=reactions, total=total, title=title)
    return render_template('dianxuan.html', qs=qs, c=c)

# ── 我的宫苑 ───────────────────────────────────────────────────────────────────

def pending_redirect(c):
    """早上第一次进来先看「昨夜宫中」，再处理待定夺的场景"""
    last_night = cur_day() - 1
    if last_night >= 1 and c['entered_day'] <= last_night and c['recap_seen_day'] < last_night:
        return redirect(url_for('recap'))
    if get_scene(c):
        return redirect(url_for('scene'))
    return None

@app.route('/')
@login_required
def index():
    c = g.me
    r = pending_redirect(c)
    if r: return r
    day = cur_day()
    msgs = q("SELECT * FROM messages WHERE consort_id=? AND kind!='edict' ORDER BY id DESC LIMIT 20", (c['id'],))
    run("UPDATE messages SET is_read=1 WHERE consort_id=? AND is_read=0", (c['id'],))
    edict = q("SELECT * FROM messages WHERE consort_id=? AND kind='edict' AND day>=? ORDER BY id DESC LIMIT 1",
              (c['id'], day - 1), one=True)
    nxt = c['rank'] + 1
    promo = None
    if c['status'] not in ('cold',) and nxt <= PLAYER_MAX_RANK:
        promo = dict(rank=RANK_NAMES[nxt], favor=PROMOTE_FAVOR[nxt], virtue=PROMOTE_VIRTUE[nxt],
                     slot=slot_free(nxt, c['id']), days_ok=(day - c['rank_since_day']) >= MIN_DAYS_AT_RANK)
    heirs = q("SELECT * FROM heirs WHERE mother_id=? ORDER BY id", (c['id'],))
    maid_gap = 0 if c['status'] == 'cold' else maid_quota(c['rank']) - len(active_maids(c['id']))
    return render_template('index.html', c=c, msgs=msgs, promo=promo, heirs=heirs, edict=edict, maid_gap=maid_gap,
                           sick=is_sick(c), eyes=eyes_active(c), secret=SECRETS[c['secret']], guide=guide_view(c),
                           day=day, PREGNANCY_DAYS=PREGNANCY_DAYS, tiles=map_tiles(c))

@app.route('/guide/skip', methods=['POST'])
@login_required
def guide_skip():
    run("UPDATE consorts SET guide_step=-1 WHERE id=?", (g.me['id'],))
    flash('许嬷嬷福了福身：「小主既有主意，老奴便不多嘴了，有事只管来找老奴。」', 'info')
    return redirect(url_for('index'))

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
    if get_scene(c):
        return redirect(url_for('scene'))
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
        if cfg.get('errand') and not free_errand_maids(c):
            raise Reject('宫人今天都派出去了。' if active_maids(c['id']) else '你宫里还没有宫人，先去内务府挑一个。')
        msg, kind = ACTION_HANDLERS[key](c, cfg)
        daily_inc(c['id'], key)
        if key in REQ_LABELS: guide_mark(c['id'], key)
        if getattr(g, 'scene_started', False):
            return redirect(url_for('scene'))
        flash(msg, kind)
    except Reject as e:
        flash(str(e), 'bad')
    back = request.form.get('back', '')
    if back in PLACES:
        return redirect(url_for('place', key=back))
    return redirect(url_for('social') if back == 'social' else url_for('index'))

def do_greet(c, cfg):
    charge(c, cfg)
    gain = 2 if c['personality'] == 'dignified' else 1
    add_stat(c['id'], 'virtue', gain)
    run("UPDATE consorts SET greet_day=?, missed_greet=0 WHERE id=?", (cur_day(), c['id']))
    msg = f"你到景仁宫给皇后请了安。德行 +{gain}。"
    r = random.random()
    huafei = q("SELECT * FROM consorts WHERE npc_key='huafei'", one=True)
    if r < 0.3 and huafei['status'] == 'normal':
        start_scene(c['id'], 'greet_huafei')
        return msg, 'info'
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
    start_scene(c['id'], 'seek_angry')
    return '', 'info'

def do_garden(c, cfg):
    charge(c, cfg)
    events = [('emperor', 18 + c['appearance'] / 6 + c['talent'] / 10), ('flower', 22), ('secret', 12),
              ('huafei', 14), ('quiet', 22), ('meet', 12)]
    ev = random.choices([e for e, _ in events], weights=[w for _, w in events])[0]
    if ev == 'emperor':
        start_scene(c['id'], 'garden_emperor')
        return '', 'info'
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
        start_scene(c['id'], 'garden_huafei')
        return '', 'info'
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
    m = take_errand(c, prefer='jiling')
    p = 0.35 + (c['scheme'] - t['scheme']) * 0.01 - (0.15 if eyes_active(t) else 0)
    if m['trait'] == 'jiling': p += 0.10
    p = clamp(p * 100, 10, 85) / 100
    if random.random() < p:
        run("INSERT OR IGNORE INTO known_secrets (knower_id, target_id, day) VALUES (?,?,?)",
            (c['id'], t['id'], cur_day()))
        if t['secret'] == 'none':
            return f"{m['name']}使银子打听了一圈：{display_name(t)}身家清白，没什么把柄。", 'info'
        return f"{m['name']}打听到了：{display_name(t)}{SECRETS[t['secret']]['name']}。", 'good'
    if random.random() < (0.6 if eyes_active(t) else 0.25):
        who = display_name(c) if eyes_active(t) else '有人'
        notify(t['id'], f"眼线来报：{who}在打听你的底细。", 'bad')
        return f"{m['name']}银子花了，什么也没打听到，还惊动了对方。", 'bad'
    return f"{m['name']}银子花了，什么也没打听到。", 'info'

def do_plead(c, cfg):
    t = pick_target(c)
    if t['status'] not in ('confined', 'cold'):
        raise Reject('她好好的，不必求情。')
    rel = relation(c['id'], t['id'])
    if not rel or (not rel['sister'] and rel['affinity'] < 30):
        raise Reject('你与她交情不够，贸然求情反惹皇上疑心。需结为姐妹或好感 30 以上。')
    charge(c, cfg)
    if random.random() < plead_chance(c):
        cut = shorten_punishment(c, t)
        return f"皇上听了你的话，松了口。{full_name(t)}的日子缩短了 {cut} 天。", 'good'
    add_trust(c['id'], -3)
    return "皇上脸色一沉：「后宫的事，轮得到你来说？」信任 -3。", 'bad'

def plead_chance(c):
    """求情看信任：30% + 信任 × 0.6%，最高 90%（信任 20 约四成，信任 60 约三分之二）"""
    return min(0.9, 0.3 + c['trust'] * 0.006)

def shorten_punishment(helper, t):
    cut = 1 if t['status'] == 'confined' else 2
    run("UPDATE consorts SET status_until_day=status_until_day-? WHERE id=?", (cut, t['id']))
    notify(t['id'], f"{display_name(helper)}在皇上跟前替你求了情，日子缩短了 {cut} 天。", 'good')
    add_affinity(helper['id'], t['id'], 5)
    t2 = get_consort(t['id'])
    if t2['status_until_day'] <= cur_day():
        if t2['status'] == 'cold':
            release_from_cold(t['id'], f"{display_name(helper)}苦苦求情，")
        else:
            run("UPDATE consorts SET status='normal', status_until_day=0 WHERE id=?", (t['id'],))
            notify(t['id'], '禁足解了。', 'good')
    return cut

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
    add_trust(c['id'], 5)
    sec = SECRETS[c['secret']]
    flash(f"你向皇上坦白了：{sec['name']}。皇上念你诚实，从轻发落：{sec['confess']}。信任 +5。", 'info')
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

# ── 内务府 ─────────────────────────────────────────────────────────────────────

@app.route('/shop')
@login_required
def shop():
    c = g.me
    inv = {r['item_key']: r['qty'] for r in q("SELECT * FROM inventory WHERE consort_id=?", (c['id'],))}
    return render_template('shop.html', c=c, inv=inv, stock=cabinet_stock(c['id'], cur_day()))

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
                           used_today=daily_count(c['id'], 'intrigue'), inventory={k: inv_qty(c['id'], k) for k in (*ITEMS, *DRUGS)}, agents=drug_agents(c['id']))

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
    used = request.form.get('drug', '')
    drug = request.form.get('effect', '') if used == 'wuming' else used
    try: mid = int(request.form.get('agent_maid_id', 0))
    except ValueError: mid = -1
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
    elif method == 'drug':
        err = drug_block(c, t, drug, used, mid, day)
    elif method == 'expose':
        if t['secret_revealed']: err = '她的事早就人尽皆知了。'
        elif not q("SELECT 1 FROM known_secrets WHERE knower_id=? AND target_id=?", (c['id'], tid), one=True):
            err = '你手里没有她的把柄，先去打探。'
        elif t['secret'] == 'none': err = '她身家清白，没什么可告发的。'
    elif method == 'steal' and (t['pregnant_since'] or is_sick(t)):
        err = '她今晚本就侍不了寝。'
    elif method == 'punish':
        err = punish_block(c, t, day)
    if err:
        flash(err, 'bad')
        return redirect(url_for('intrigue'))
    run("UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?", (cfg['energy'], cfg['silver'], c['id']))
    if cfg.get('item'): inv_add(c['id'], cfg['item'], -1)
    run("""INSERT INTO intrigues (day, attacker_id, target_id, method, silver_paid, item_used, created_ts)
           VALUES (?,?,?,?,?,?,?)""", (day, c['id'], tid, method, cfg['silver'], cfg.get('item', ''), now_ts()))
    if method == 'drug':
        iid = q('SELECT last_insert_rowid()', one=True)[0]
        inv_add(c['id'], used, -1)
        run('UPDATE intrigues SET drug=?, item_used=?, agent_maid_id=? WHERE id=?', (drug, used, mid, iid))
        if drug == 'lihun':
            run('UPDATE users SET lethal_ready_day=? WHERE id=?', (day + LETHAL_COOLDOWN, c['user_id']))
        if used == 'wuming':
            run('UPDATE users SET nameless_ready_day=? WHERE id=?', (day + NAMELESS_COOLDOWN, c['user_id']))
    if method == 'punish':   # 和毒害一样，撤回也不重置冷却
        run('UPDATE consorts SET punish_ready_day=? WHERE id=?', (day + PUNISH_COOLDOWN, c['id']))
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

# ── 宫人 ───────────────────────────────────────────────────────────────────────
# 玩家在内务府亲手挑、亲手赐名。名字两个字、全宫不重复（已故、已离开的也算）。
# 每个宫人每天能跑一次差使；每晚领 1 两月钱，忠心随主子的处境涨落。

MAID_QUOTA = {1: 1, 2: 2, 3: 2, 4: 3}   # 官女子 1、答应/常在 2、贵人 3，嫔以上 4
MAID_TRAITS = {
    'shouqiao': dict(name='手巧', desc='手脚利落，心细如发。'),
    'zuijin':   dict(name='嘴紧', desc='什么话到她这儿都烂在肚子里。'),
    'suizui':   dict(name='碎嘴', desc='消息灵通，主子散布流言时成算 +10%。可她自己的嘴也管不住。'),
    'tancai':   dict(name='贪财', desc='见钱眼开，忠心最高只到 70。', cap=70),
    'zhonghou': dict(name='忠厚', desc='老实本分，忠心不会低于 40。', floor=40),
    'jiling':   dict(name='机灵', desc='眼疾手快，派她去打探，成算 +10%。'),
}
MAID_BACKSTORIES = [
    '浣衣局调来的，手上还有冻疮。',
    '原先伺候过一位答应，那位小主没了。',
    '内务府管事的远房侄女，说话带着京腔。',
    '江南织造送进来的，会绣双面绣。',
    '家里兄弟多，十二岁就进宫了。',
    '在御膳房烧过三年火，闻得出菜里的味道。',
    '以前在太后宫里当过差，不知为何被调了出来。',
    '识得几个字，说是爹从前是个账房先生。',
    '满脸稚气，说话还有些怯。',
    '在花房伺候过，认得宫里所有的花草。',
    '一手好梳头的手艺，原先是给嬷嬷们梳头的。',
    '性子闷，一整天说不了三句话。',
    '笑起来眼睛弯弯的，谁见了都喜欢。',
    '从辛者库出来的，没人知道她犯过什么事。',
    '父亲是宫里的侍卫，常托人捎东西进来。',
    '左眉有颗痣，嬷嬷说那是有福的相。',
]
MAID_WAGE = 1              # 每个宫人每晚的月钱
MAID_REROLL_COST = 10      # 每天第二次起换一批候选
MAID_REWARD_COST = 20
MAID_BURY_COST = 20
MAID_EVENT_CHANCE = 0.3    # 每天第一次进本宫时，宫人来找你的概率
MAID_NEW_SHIELD = 3        # 刚挑的宫人 3 天内不会被发落
PUNISH_COOLDOWN = 7        # 发落宫人：出手的人 7 天一次；每个人的宫人 7 天内最多被发落一个
HUAFEI_PUNISH_CHANCE = 0.05
_HAN2 = re.compile(r'^[一-鿿]{2}$')

def maid_quota(rank):
    return 0 if rank < 1 else MAID_QUOTA.get(rank, 4)

def active_maids(cid):
    return q("SELECT * FROM maids WHERE owner_id=? AND status='active' ORDER BY id", (cid,))

def get_maid(mid):
    return q("SELECT * FROM maids WHERE id=?", (mid,), one=True)

def add_loyalty(mid, delta):
    m = get_maid(mid)
    t = MAID_TRAITS.get(m['trait'], {})
    run("UPDATE maids SET loyalty=? WHERE id=?",
        (max(t.get('floor', 0), min(t.get('cap', 100), m['loyalty'] + int(delta))), mid))

def loyalty_word(v):
    return '死心塌地' if v >= 80 else '忠心' if v >= 60 else '尚可' if v >= 40 else '离心'

def maid_leave(mid, status, reason):
    run("UPDATE maids SET status=?, left_day=?, left_reason=? WHERE id=?", (status, cur_day(), reason, mid))
    if status == 'dead':
        owner = get_consort(get_maid(mid)['owner_id'])
        guide_tip(owner['id'], 'maid_death', '「宫里的人来来去去，是常事。厚葬一下，也算全了这份情分。」')

def has_maid_trait(cid, trait):
    return any(m['trait'] == trait and m['sick_until_day'] < cur_day() for m in active_maids(cid))

def free_errand_maids(c):
    """今天还没跑过差使、没卧病的宫人。冷宫里宫人不在身边"""
    if c['status'] == 'cold': return []
    day = cur_day()
    return [m for m in active_maids(c['id'])
            if m['sick_until_day'] < day and daily_count(c['id'], f"errand:{m['id']}") == 0]

def take_errand(c, prefer=None):
    free = free_errand_maids(c)
    if not free:
        raise Reject('宫人今天都派出去了。')
    m = next((x for x in free if x['trait'] == prefer), free[0])
    daily_inc(c['id'], f"errand:{m['id']}")
    return m

def roll_maid_offer():
    out = []
    for story in random.sample(MAID_BACKSTORIES, 4):
        trait = random.choice(list(MAID_TRAITS))
        out.append(dict(trait=trait, loyalty=random.randint(50, 70), backstory=story))
    return out

def maid_offer(c):
    try:
        offer = json.loads(c['maid_offer']) if c['maid_offer'] else None
    except ValueError:
        offer = None
    if not offer:
        offer = roll_maid_offer()
        run("UPDATE consorts SET maid_offer=? WHERE id=?", (json.dumps(offer, ensure_ascii=False), c['id']))
    return offer

def maid_name_error(name):
    if not _HAN2.match(name or ''):
        return '宫人的名字要是两个汉字。'
    if blocked_hit('宫人名', name):
        return BLOCKED_MSG
    if q("SELECT 1 FROM maids WHERE name=?", (name,), one=True):
        return f'宫里已经有过叫「{name}」的宫人了，换一个吧。'
    if q("SELECT 1 FROM consorts WHERE given=?", (name,), one=True):
        return f'「{name}」和一位小主的名字撞了，宫人不能用。'
    return None

def punishable_maids(cid):
    day = cur_day()
    return [m for m in active_maids(cid) if day - m['joined_day'] >= MAID_NEW_SHIELD]

def punish_block(c, t, day):
    if c['rank'] < t['rank'] + 2:
        return '要比她高两级以上，才发落得了她宫里的人。'
    if c['punish_ready_day'] > day:
        return f"你上次发落宫人还没过 {PUNISH_COOLDOWN} 天，第 {c['punish_ready_day']} 天才能再动手。"
    if t['maid_punished_day'] and day - t['maid_punished_day'] < PUNISH_COOLDOWN:
        return '她宫里前几天才没了人，这会儿再动太扎眼。'
    if not punishable_maids(t['id']):
        return '她宫里眼下没有能拿来做文章的宫人（刚挑的宫人 3 天内动不得）。'
    return None

def huafei_punish(day):
    """华妃记恨谁，每晚有 5% 找由头发落那人宫里的宫人"""
    hf = q("SELECT * FROM consorts WHERE npc_key='huafei' AND status='normal'", one=True)
    if not hf or hf['punish_ready_day'] > day: return
    for p in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND entered_day<?", (day,)):
        rel = relation(hf['id'], p['id'])
        if not rel or rel['affinity'] > -20 or random.random() >= HUAFEI_PUNISH_CHANCE: continue
        if punish_block(hf, p, day): continue
        if q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status='pending'",
             (p['id'], day), one=True)['n'] >= INTRIGUE_TARGET_DAILY_MAX: continue
        run("INSERT INTO intrigues (day, attacker_id, target_id, method, created_ts) VALUES (?,?,?,?,?)",
            (day, hf['id'], p['id'], 'punish', now_ts()))
        run("UPDATE consorts SET punish_ready_day=? WHERE id=?", (day + PUNISH_COOLDOWN, hf['id']))
        return

def maid_upkeep(day):
    for c in q("SELECT * FROM consorts WHERE status NOT IN ('xiunv','dead')"):
        maids = active_maids(c['id'])
        if not maids: continue
        for m in maids:
            if m['sick_until_day'] and m['sick_until_day'] <= day:
                run("UPDATE maids SET sick_until_day=0 WHERE id=?", (m['id'],))
        if c['status'] == 'cold':          # 冷宫里宫人不在跟前，不发月钱，心也散了
            for m in maids: add_loyalty(m['id'], -5)
            continue
        wage = MAID_WAGE * len(maids)
        if c['silver'] < wage:
            for m in maids: add_loyalty(m['id'], -5)
            if c['user_id']:
                notify(c['id'], f"宫人的月钱发不出来（{len(maids)} 人要 {wage} 两），全宫宫人忠心 -5。", 'bad')
            continue
        add_silver(c['id'], -wage)
        for m in maids:
            add_loyalty(m['id'], -2 if c['status'] == 'confined' else 1)
    run("UPDATE consorts SET maid_event='' WHERE maid_event!=''")

# ── 宫人的小事 ─────────────────────────────────────────────────────────────────
# 每条选项的效果：loyalty 当事宫人忠心 / loyalty2 另一个宫人 / silver / virtue / appearance / seek 今晚翻牌加成
# affinity 和被牵扯的那位小主的好感 / gossip 听闲话 / hide 替她瞒下烧纸

MAID_EVENTS = {
    'mother_ill': dict(text='{m}红着眼圈来回话：家里捎信说老娘病了，想跟小主讨 10 两银子抓药。', opts=[
        dict(text='给她 10 两', silver=-10, loyalty=10, say='{m}磕了个头，眼泪都掉下来了。'),
        dict(text='宫里有宫里的规矩，不给', loyalty=-5, say='{m}低着头退下了，一句话也没说。')]),
    'vase': dict(text='{m}收拾博古架时失了手，打碎了你最心爱的那只瓶子，跪在地上直发抖。', opts=[
        dict(text='罚她去院里跪着', loyalty=-8, say='{m}在院里跪到天黑。'),
        dict(text='碎碎平安，算了', loyalty=6, say='{m}愣了半晌，才敢起身谢恩。')]),
    'gossip': dict(text='{m}从御花园回来，神神秘秘地说听到了别宫的闲话。', opts=[
        dict(text='让她说', gossip=True, say=''),
        dict(text='叫她别乱传', virtue=1, loyalty=2, say='{m}吐了吐舌头：「奴婢记下了。」')]),
    'quarrel': dict(text='{m}和{m2}不知为什么拌起嘴来，一前一后来找你评理。', two=True, opts=[
        dict(text='向着{m}', loyalty=8, loyalty2=-8, say='{m}得意地瞥了{m2}一眼。'),
        dict(text='向着{m2}', loyalty=-8, loyalty2=8, say='{m}咬着嘴唇，眼圈红了。'),
        dict(text='各打五十大板', loyalty=-2, loyalty2=-2, say='两个人都不吭声了。')]),
    'birthday': dict(text='今天是{m}的生辰，她自己没提，是别人悄悄告诉你的。', opts=[
        dict(text='赏她一支簪子（15 两）', silver=-15, loyalty=10, say='{m}把簪子捧在手里看了又看。'),
        dict(text='说句吉祥话', loyalty=3, say='{m}笑着福了福身。')]),
    'bullied': dict(text='{m}哭着回来，说在甬道上被{t}宫里的人推搡了，还挨了两句骂。', needs_target=True, opts=[
        dict(text='替她出头', loyalty=12, affinity=-5, say='你亲自去{t}那儿讨了个说法，{m}感激得不得了。'),
        dict(text='让她忍着', loyalty=-4, say='{m}抹着眼泪下去了。')]),
    'burning': dict(text='夜里你闻见烟味，原来是{m}躲在后院偷偷给过世的爹娘烧纸——这在宫里是犯忌讳的。', opts=[
        dict(text='替她瞒着', loyalty=15, hide=True, say='{m}跪下给你磕了三个头。这事要是哪天被人翻出来，你也脱不了干系。'),
        dict(text='按规矩上报', loyalty=-20, virtue=2, say='{m}被内务府罚了月钱。她再看你的眼神，不一样了。')]),
    'sachet': dict(text='{m}熬了几个晚上，绣了个香囊孝敬你，针脚细密。', opts=[
        dict(text='自己戴着', appearance=1, loyalty=2, say='你把香囊系在腰间，{m}高兴得什么似的。'),
        dict(text='托人转送养心殿', seek=5, say='香囊送去了养心殿。今晚翻牌子的机会大了些。')]),
}

def roll_maid_event(c):
    """每天第一次进本宫时掷一次。同一件事同一个宫人不会遇到两次"""
    if c['status'] == 'cold' or c['maid_event'] or daily_count(c['id'], 'maid_event_roll'): return
    daily_inc(c['id'], 'maid_event_roll')
    if random.random() >= MAID_EVENT_CHANCE: return
    maids = list(active_maids(c['id']))
    if not maids: return
    random.shuffle(maids)
    others = q("""SELECT id FROM consorts WHERE id!=? AND status='normal' AND rank>=1""", (c['id'],))
    for key in random.sample(list(MAID_EVENTS), len(MAID_EVENTS)):
        ev = MAID_EVENTS[key]
        if ev.get('needs_target') and not others: continue
        for m in maids:
            if key in json.loads(m['seen_events'] or '[]'): continue
            data = dict(key=key, maid=m['id'], day=cur_day())
            if ev.get('two'):
                m2 = next((x for x in maids if x['id'] != m['id']), None)
                if not m2: break
                data['maid2'] = m2['id']
            if ev.get('needs_target'):
                data['target'] = random.choice(others)['id']
            run("UPDATE consorts SET maid_event=? WHERE id=?", (json.dumps(data), c['id']))
            return

def maid_event_view(c):
    """返回 (正文, 选项文字列表, 数据, 名字表)；事情已经过期或当事人不在了就返回 None"""
    try:
        data = json.loads(c['maid_event']) if c['maid_event'] else None
    except ValueError:
        return None
    if not data or data.get('day') != cur_day(): return None
    m = get_maid(data['maid'])
    m2 = get_maid(data['maid2']) if data.get('maid2') else None
    t = get_consort(data['target']) if data.get('target') else None
    if not m or m['status'] != 'active' or m['owner_id'] != c['id']: return None
    if data.get('maid2') and (not m2 or m2['status'] != 'active' or m2['owner_id'] != c['id']): return None
    names = dict(m=m['name'], m2=m2['name'] if m2 else '', t=display_name(t) if t else '')
    ev = MAID_EVENTS[data['key']]
    return ev['text'].format(**names), [o['text'].format(**names) for o in ev['opts']], data, names

@app.route('/maids/event', methods=['POST'])
@login_required
def maid_event_choose():
    c = g.me
    view = maid_event_view(c)
    if not view:
        run("UPDATE consorts SET maid_event='' WHERE id=?", (c['id'],))
        return redirect(url_for('place', key='home'))
    _, _, data, names = view
    ev = MAID_EVENTS[data['key']]
    try:
        opt = ev['opts'][int(request.form.get('opt', ''))]
    except (ValueError, IndexError):
        return redirect(url_for('place', key='home'))
    if opt.get('silver') and c['silver'] < -opt['silver']:
        flash(f"手头只有 {c['silver']} 两，拿不出来。", 'bad')
        return redirect(url_for('place', key='home'))
    run("UPDATE consorts SET maid_event='' WHERE id=?", (c['id'],))
    m = get_maid(data['maid'])
    seen = json.loads(m['seen_events'] or '[]') + [data['key']]
    run("UPDATE maids SET seen_events=? WHERE id=?", (json.dumps(seen), m['id']))
    parts = []
    if opt.get('silver'):
        add_silver(c['id'], opt['silver']); parts.append(f"银子 {opt['silver']:+d}")
    if opt.get('loyalty'):
        add_loyalty(m['id'], opt['loyalty']); parts.append(f"{m['name']}忠心 {opt['loyalty']:+d}")
    if opt.get('loyalty2') and data.get('maid2'):
        add_loyalty(data['maid2'], opt['loyalty2']); parts.append(f"{names['m2']}忠心 {opt['loyalty2']:+d}")
    for k in ('virtue', 'appearance'):
        if opt.get(k):
            add_stat(c['id'], k, opt[k]); parts.append(f"{STAT_NAMES[k]} {opt[k]:+d}")
    if opt.get('seek'):
        if c['status'] == 'normal':
            run("UPDATE consorts SET seek_bonus=seek_bonus+? WHERE id=?", (opt['seek'], c['id']))
        else:
            parts.append('可你眼下见不着皇上，香囊白送了')
    if opt.get('affinity') and data.get('target'):
        add_affinity(c['id'], data['target'], opt['affinity']); parts.append(f"和{names['t']}好感 {opt['affinity']:+d}")
    if opt.get('hide'):
        run("UPDATE maids SET hid_burning=1 WHERE id=?", (m['id'],))
    say = opt['say'].format(**names)
    if opt.get('gossip'):
        say = maid_gossip(c, m)
    flash('　'.join(x for x in (say, '，'.join(parts) + ('。' if parts else '')) if x), 'good')
    return redirect(url_for('place', key='home'))

GOSSIP_WORDS = dict(greet='去景仁宫请了安', study='练了才艺', groom='梳妆打扮', garden='逛了御花园',
                    seek='往养心殿送了汤羹', rest='在宫里静养', reflect='闭门抄经', visit='四处串门',
                    spy='派人打听别人的事', plead='去养心殿替人求情', letter='写了信', intrigue='私下里安排了什么事')

def maid_gossip(c, m):
    others = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status NOT IN ('xiunv','dead')""", (c['id'],))
    if not others:
        return f"{m['name']}说了半天，都是些没影的事。"
    t = random.choice(others)
    return f"{m['name']}说：「{display_name(t)}今儿个{daily_activity(t['id'], cur_day())}。」"


def daily_activity(cid, day):
    did = [GOSSIP_WORDS[r['key']] + (f" {r['count']} 回" if r['count'] > 1 else '')
           for r in q("SELECT key,count FROM daily_counters WHERE consort_id=? AND day=? ORDER BY key", (cid, day))
           if r['key'] in GOSSIP_WORDS and r['count'] > 0]
    return '、'.join(did) if did else '一步都没出宫门'


# ── 宫人页面 ───────────────────────────────────────────────────────────────────

@app.route('/maids')
@login_required
def maids_page():
    c = g.me
    mine = active_maids(c['id'])
    quota = maid_quota(c['rank'])
    can_pick = c['status'] != 'cold' and len(mine) < quota
    past = q("SELECT * FROM maids WHERE owner_id=? AND status!='active' ORDER BY left_day DESC, id DESC", (c['id'],))
    return render_template('maids.html', c=c, mine=mine, quota=quota, can_pick=can_pick,
                           offer=maid_offer(c) if can_pick else [], past=past, TRAITS=MAID_TRAITS,
                           loyalty_word=loyalty_word, free_reroll=daily_count(c['id'], 'maid_reroll') == 0,
                           rewarded=daily_count(c['id'], 'maid_reward') > 0,
                           errands=len(free_errand_maids(c)), costs=dict(reroll=MAID_REROLL_COST,
                           reward=MAID_REWARD_COST, bury=MAID_BURY_COST, wage=MAID_WAGE))

@app.route('/maids/pick', methods=['POST'])
@login_required
def maid_pick():
    c = g.me
    name = request.form.get('name', '').strip()
    try: idx = int(request.form.get('idx', ''))
    except ValueError: idx = -1
    offer = maid_offer(c)
    err = None
    if c['status'] == 'cold': err = '冷宫里，内务府不会派人来。'
    elif len(active_maids(c['id'])) >= maid_quota(c['rank']):
        err = f"按{RANK_NAMES[c['rank']]}的份例，你宫里的宫人已经满了。"
    elif not 0 <= idx < len(offer): err = '选一个人。'
    else: err = maid_name_error(name)
    if err:
        flash(err, 'bad')
        return redirect(url_for('maids_page'))
    pick = offer[idx]
    run("""INSERT INTO maids (owner_id, name, trait, loyalty, backstory, joined_day, created_ts)
           VALUES (?,?,?,?,?,?,?)""", (c['id'], name, pick['trait'], pick['loyalty'], pick['backstory'], cur_day(), now_ts()))
    run("UPDATE consorts SET maid_offer='' WHERE id=?", (c['id'],))
    guide_mark(c['id'], 'maid')
    flash(f"你给她赐名「{name}」。{name}跪下谢恩，从今往后就是{c['palace'] or '你宫里'}的人了。", 'good')
    return redirect(url_for('maids_page'))

@app.route('/maids/reroll', methods=['POST'])
@login_required
def maid_reroll():
    c = g.me
    cost = 0 if daily_count(c['id'], 'maid_reroll') == 0 else MAID_REROLL_COST
    if c['status'] == 'cold' or len(active_maids(c['id'])) >= maid_quota(c['rank']):
        return redirect(url_for('maids_page'))
    if c['silver'] < cost:
        flash(f'换一批要打点 {cost} 两。', 'bad')
        return redirect(url_for('maids_page'))
    add_silver(c['id'], -cost)
    daily_inc(c['id'], 'maid_reroll')
    run("UPDATE consorts SET maid_offer=? WHERE id=?", (json.dumps(roll_maid_offer(), ensure_ascii=False), c['id']))
    flash('内务府又领来了几个人。' + (f'打点 {cost} 两。' if cost else ''), 'info')
    return redirect(url_for('maids_page'))

@app.route('/maids/reward', methods=['POST'])
@login_required
def maid_reward():
    c = g.me
    mine = active_maids(c['id'])
    err = None
    if c['status'] == 'cold': err = '冷宫里连自己都顾不上。'
    elif not mine: err = '你宫里还没有宫人。'
    elif daily_count(c['id'], 'maid_reward'): err = '今天已经赏过了。'
    elif c['silver'] < MAID_REWARD_COST: err = f'要 {MAID_REWARD_COST} 两银子。'
    if err:
        flash(err, 'bad')
        return redirect(url_for('maids_page'))
    add_silver(c['id'], -MAID_REWARD_COST)
    daily_inc(c['id'], 'maid_reward')
    for m in mine: add_loyalty(m['id'], 5)
    flash(f'你赏了宫人们些果子和银钱。全宫宫人忠心 +5。', 'good')
    return redirect(url_for('maids_page'))

@app.route('/maids/bury/<int:mid>', methods=['POST'])
@login_required
def maid_bury(mid):
    c = g.me
    m = get_maid(mid)
    err = None
    if not m or m['owner_id'] != c['id'] or m['status'] != 'dead': err = '没有这个人。'
    elif m['buried']: err = '已经厚葬过了。'
    elif c['silver'] < MAID_BURY_COST: err = f'要 {MAID_BURY_COST} 两银子。'
    if err:
        flash(err, 'bad')
        return redirect(url_for('maids_page'))
    add_silver(c['id'], -MAID_BURY_COST)
    run("UPDATE maids SET buried=1 WHERE id=?", (mid,))
    for other in active_maids(c['id']): add_loyalty(other['id'], 10)
    flash(f"你出银子给{m['name']}置了口薄棺，托人送回她家乡。宫里的人都看在眼里，全宫宫人忠心 +10。", 'good')
    return redirect(url_for('maids_page'))

@app.route('/admin/maid_rename', methods=['POST'])
@admin_required
def admin_maid_rename():
    old, new = request.form.get('old', '').strip(), request.form.get('new', '').strip()
    m = q("SELECT * FROM maids WHERE name=?", (old,), one=True)
    err = '没有叫这个名字的宫人。' if not m else maid_name_error(new)
    if err:
        flash(err, 'bad')
    else:
        run("UPDATE maids SET name=? WHERE id=?", (new, m['id']))
        flash(f'已把宫人「{old}」改名为「{new}」。', 'good')
    return redirect(url_for('admin'))

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
    if g.me: guide_mark(g.me['id'], 'gazette')
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
        elif blocked_hit('赐名', name):
            flash(BLOCKED_MSG, 'bad')
        else:
            run("UPDATE heirs SET name=? WHERE id=?", (name, hid))
            flash(f"皇上允了，赐名「{name}」。", 'good')
        return redirect(url_for('heirs'))
    rows = q("SELECT h.*, c.surname FROM heirs h JOIN consorts c ON c.id=h.mother_id ORDER BY h.id")
    day = cur_day()
    acts = {}
    for h in rows:
        a = {}
        if h['mother_id'] == c['id'] and h['caretaker_id'] == c['id'] and c['rank'] < 5 and c['status'] == 'normal' \
                and not h['zhuazhou'] and heir_age_days(h, day) < ZHUAZHOU_AGE_DAYS:
            a['entrust'] = True
            if h['foster_request_to']: a['waiting_on'] = get_consort(h['foster_request_to'])
        if h['foster_request_to'] == c['id']: a['reply'] = True
        if h['mother_id'] == c['id'] and h['caretaker_id'] not in (0, c['id']) and c['status'] != 'dead':
            a['visit'] = True
            if c['rank'] >= 5: a['reclaim'] = True
            a['reclaim_wait'] = max(0, h['reclaim_after_day'] - day)
        if h['caretaker_id'] == c['id'] and h['mother_id'] != c['id']: a['can_ban'] = True
        if a: acts[h['id']] = a
    targets = entrust_candidates(c) if any(a.get('entrust') for a in acts.values()) else []
    return render_template('heirs.html', c=c, rows=rows, get_consort=get_consort, acts=acts, targets=targets)

# ── 皇嗣成长（九点六节 A~D：还没做成年、抚养关系博弈、夺嫡） ─────────────────────

HEIR_STATS = dict(study='学问', riding='骑射', virtue='品行', health='体质')

HEIR_PERSONALITIES = {
    'clever':   dict(name='聪敏', desc='读书涨得更快'),
    'honest':   dict(name='憨厚', desc='立规矩效果加倍，读书慢一些'),
    'naughty':  dict(name='顽皮', desc='陪他玩情分涨得多，读书慢一些'),
    'timid':    dict(name='怯懦', desc='将来考校吃亏，但情分涨得快'),
    'stubborn': dict(name='倔强', desc='被罚时情分掉得多，骑射涨得更快'),
}

ZHUAZHOU_ITEMS = [
    dict(key='book', name='书卷', stat='study', line='一把抓住了那卷书，攥得紧紧的'),
    dict(key='bow', name='弓箭', stat='riding', line='径直扑向那张小弓，谁都拉不开他的手'),
    dict(key='seal', name='印章', stat='virtue', line='摸到那方印章，端端正正地捧在手里'),
    dict(key='abacus', name='算盘', stat='virtue', line='拨弄起了算盘珠子，拨得叮当响'),
    dict(key='rouge', name='胭脂', stat='health', line='伸手碰了碰那盒胭脂，咯咯笑了起来'),
]
ZHUAZHOU_GAIN = 10
ZHUAZHOU_AGE_DAYS = 2      # 出生第 2 天=周岁，一定触发抓周

HEIR_RAISE_ENERGY = 1
HEIR_RAISE = {
    'study':      dict(name='读书', gain=dict(study=3)),
    'ride':       dict(name='骑射', gain=dict(riding=3)),
    'ride_girl':  dict(name='琴棋', gain=dict(study=2, virtue=1)),   # 公主版的「骑射」
    'discipline': dict(name='立规矩', gain=dict(virtue=3), affinity=-1),
    'play':       dict(name='陪他玩', affinity=5),
}

HEIR_EVENT_CHANCE = 0.25
HEIR_FOSTER_TALK_AGE_DAYS = 16   # 抱养的孩子 8 岁（出生第 16 天）起才会问「我的亲额娘是谁」

HEIR_EVENTS = {
    'father_visit': dict(text='「额娘，皇阿玛好久没来了。」', opts=[
        dict(text='如实说', virtue=2, affinity=2, say='他似懂非懂地点点头。'),
        dict(text='哄他说皇阿玛忙', affinity=4, say='他信以为真，笑了。')]),
    'fight': dict(text='他在上书房和{t}宫里的孩子打了一架，师傅来告状。', needs_target=True, opts=[
        dict(text='罚他', virtue=3, affinity=-3, say='他跪了半个时辰，一声没吭。'),
        dict(text='护着他', affinity=5, target_affinity=-5, say='你替他挡了下来，只是从此和{t}的关系僵了。')]),
    'puppy': dict(text='他缠着要养一只小狗。', opts=[
        dict(text='准了（10 两）', silver=-10, affinity=5, say='他抱着那只小狗，乐得合不拢嘴。'),
        dict(text='不准', affinity=-2, say='他闷闷不乐地走开了。')]),
    'praise': dict(text='师傅来回话，夸他这几日文章写得好。', opts=[
        dict(text='让他去给皇阿玛请安', favor=3, say='皇上听了几句，点头称许。'),
        dict(text='私下赏他', affinity=4, say='他把那点赏赐宝贝似的收了起来。')]),
    'fever': dict(text='夜里他发起热来，烧得脸通红。', opts=[
        dict(text='守一夜', mother_health=-5, affinity=10, say='你守到天明，他终于退了烧。'),
        dict(text='交给太医', say='太医说不打紧，你这才松了口气。')]),
    'treat': dict(text='{t}着人送来一碟点心，说是给孩子的。', needs_target=True, opts=[
        dict(text='收下', target_affinity=3, say='他吃得满嘴都是渣，你和{t}的交情也厚实了些。'),
        dict(text='原样退回', affinity=-1, say='退是退了，只是不知这份心思该往哪儿搁。')]),
    'true_mother': dict(text='他忽然问：「我的亲额娘，到底是谁？」', foster_only=True, opts=[
        dict(text='说实话', to_mother_affinity=10, say='他沉默了许久，没再说话。'),
        dict(text='瞒着', affinity=5, conceal=True, say='他似乎不太信，但没再追问——只是往后，这事早晚要被人说破。')]),
    'sneak_visit': dict(text='宫人来报，他偷偷跑去看了生母，被拦在了半路上。', foster_only=True, opts=[
        dict(text='由他去', to_mother_affinity=6, say='你叹了口气，没有阻拦。'),
        dict(text='拦下', affinity=-3, say='他被拦回来，一路上都没说话。')]),
}


def heir_age_days(h, day=None):
    return (day or cur_day()) - h['born_day']


def heir_age_years(h, day=None):
    return heir_age_days(h, day) // 2


# ── 皇上考校 / 随驾秋狝 ──────────────────────────────────────────────────────

HEIR_EXAM_INTERVAL = 7
HEIR_EXAM_MIN_AGE, HEIR_EXAM_MAX_AGE = 6, 15
HEIR_HUNT_INTERVAL = 14
HEIR_HUNT_MIN_AGE = 12
HEIR_HUNT_ROLL = 20
HEIR_HUNT_REWARD = 15

# 每 7 天随机抽一位 6~15 岁的皇嗣，给抚养人一段场景替他应对。题目判定用孩子的属性，不是抚养人自己的——
# 跟别的场景不一样，scene() 里专门判了 sc['key']=='exam' 这一支
EXAM_PROMPTS = [
    dict(topic='学问', ask='「听闻{h}近来读书用心，都读了些什么？」', opts=[
        dict(text='让他自己从容应答', stat='study', dc=60, win=dict(heir_favor=8), win_text='他答得条理分明，皇上频频点头。',
             lose=dict(), lose_text='他答得磕磕绊绊，皇上没说什么，只是叹了口气。'),
        dict(text='在一旁替他圆场', stat='study', dc=45, win=dict(heir_favor=5), win_text='你帮着搭了两句话，皇上倒也满意。',
             lose=dict(), lose_text='圆得不太漂亮，皇上不置可否。')]),
    dict(topic='骑射', ask='「{h}这几日骑射练得怎么样了，可敢当场演武？」', opts=[
        dict(text='让他上场演武', stat='riding', dc=60, win=dict(heir_favor=8), win_text='一箭中的，皇上抚掌称好。',
             lose=dict(), lose_text='箭偏了准头，皇上没说什么。'),
        dict(text='说他还年幼，容后再练', stat='riding', dc=45, win=dict(heir_favor=5), win_text='皇上倒也没多说什么，点了点头。',
             lose=dict(), lose_text='皇上似乎不太满意，只是没当场说破。')]),
    dict(topic='孝道', ask='「{h}平日待人接物，学得怎么样了？」', opts=[
        dict(text='如实讲他这些日子的长进', stat='virtue', dc=60, win=dict(heir_favor=10), win_text='皇上听得高兴，连声说好。',
             lose=dict(), lose_text='皇上听着，没说什么。'),
        dict(text='谦虚几句，说还要多教导', stat='virtue', dc=45, win=dict(heir_favor=6), win_text='皇上说你教子有方。',
             lose=dict(), lose_text='皇上「嗯」了一声，不甚在意。')]),
]


def heir_exam_tick(day):
    if day % HEIR_EXAM_INTERVAL: return
    eligible = [h for h in q("SELECT * FROM heirs WHERE caretaker_id!=0")
                if HEIR_EXAM_MIN_AGE <= heir_age_years(h, day) <= HEIR_EXAM_MAX_AGE]
    if not eligible: return
    h = random.choice(eligible)
    caretaker = get_consort(h['caretaker_id'])
    if not caretaker['user_id'] or caretaker['status'] != 'normal' or get_scene(caretaker):
        return   # 抚养人是 NPC、不在能应对的状态、或今晚已经有别的场景在排队，这次考校就错过了
    prompt_idx = random.randrange(len(EXAM_PROMPTS))
    start_scene(caretaker['id'], 'exam', heir=h['id'], prompt=prompt_idx)
    gazette(f"皇上考校{heir_label(h)}的功课。", 'news')


def heir_hunt_tick(day):
    if day % HEIR_HUNT_INTERVAL: return
    eligible = [h for h in q("SELECT * FROM heirs WHERE gender='皇子'") if heir_age_years(h, day) >= HEIR_HUNT_MIN_AGE]
    if not eligible: return
    winner = max(eligible, key=lambda h: h['riding'] + random.randint(0, HEIR_HUNT_ROLL))
    run('UPDATE heirs SET favor=favor+? WHERE id=?', (HEIR_HUNT_REWARD, winner['id']))
    label = heir_label(winner)
    gazette(f"随驾秋狝，{label}猎获最多，圣眷 +{HEIR_HUNT_REWARD}。", 'news')
    caretaker = get_consort(winner['caretaker_id'])
    if caretaker['user_id']:
        notify(caretaker['id'], f"{label}随驾秋狝，猎获最多，圣眷 +{HEIR_HUNT_REWARD}。", 'good')


def add_heir_affinity(hid, which, delta):
    col = 'mother_affinity' if which == 'mother' else 'caretaker_affinity'
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    run(f'UPDATE heirs SET {col}=? WHERE id=?', (clamp(h[col] + delta), hid))
    if h['caretaker_id'] == h['mother_id']:
        other = 'caretaker_affinity' if which == 'mother' else 'mother_affinity'
        run(f'UPDATE heirs SET {other}=? WHERE id=?', (clamp(h[other] + delta), hid))


def pick_foster(exclude=()):
    """挑一位嫔以上、正在当差的妃嫔当养母：带孩子最少的优先，同样多时 NPC 在前"""
    marks = ','.join('?' * len(exclude)) or '-1'
    rows = q(f"""SELECT c.id, COUNT(h2.id) n FROM consorts c LEFT JOIN heirs h2 ON h2.caretaker_id=c.id
                 WHERE c.rank>=5 AND c.status='normal' AND c.id NOT IN ({marks})
                 GROUP BY c.id ORDER BY n, c.npc_key IS NULL, c.id""", tuple(exclude))
    return get_consort(rows[0]['id']) if rows else None


def heir_growth_tick(day):
    """抓周（出生满周岁那天，一定触发）：贵人以下的生母，抓周时孩子按祖制改由嫔以上抚养。
    周岁前已经托付成了的不用再指；没托付的，皇上指给一位无子的嫔以上"""
    for h in q("SELECT * FROM heirs WHERE zhuazhou='' AND ?-born_day=?", (day, ZHUAZHOU_AGE_DAYS)):
        item = random.choice(ZHUAZHOU_ITEMS)
        run(f"UPDATE heirs SET zhuazhou=?, foster_request_to=0, {item['stat']}={item['stat']}+? WHERE id=?",
            (item['key'], ZHUAZHOU_GAIN, h['id']))
        mother = get_consort(h['mother_id'])
        label = heir_label(h)
        gazette(f"{label}周岁抓周，{item['line']}。", 'news')
        if mother['user_id']:
            notify(mother['id'], f"{label}今日抓周，{item['line']}。{HEIR_STATS[item['stat']]} +{ZHUAZHOU_GAIN}。", 'good')
        if mother['rank'] < 5 and h['caretaker_id'] == h['mother_id']:
            foster = pick_foster()
            if foster:
                run('UPDATE heirs SET caretaker_id=?, caretaker_affinity=50 WHERE id=?', (foster['id'], h['id']))
                gazette(f"祖制：{label}生母位分不及，皇上指{display_name(foster)}抚养{label}。", 'decree')
                if mother['user_id']:
                    notify(mother['id'], f"按祖制，{label}被抱去{display_name(foster)}宫里抚养了。晋到嫔位后可以去养心殿求皇上把孩子讨回来。", 'bad')
                if foster['user_id']:
                    notify(foster['id'], f"皇上把{label}指给你抚养了。去本宫就能教养。", 'good')


def heir_rehome_tick(day):
    """抚养人进了冷宫或没了，孩子一律换人带：生母已是嫔以上又正当差，还给生母；否则皇上另指一位"""
    for h in q("SELECT * FROM heirs WHERE caretaker_id!=0"):
        cur = get_consort(h['caretaker_id'])
        if cur['status'] not in ('cold', 'dead'): continue
        mother = get_consort(h['mother_id'])
        label = heir_label(h)
        cur_gone = '进了冷宫' if cur['status'] == 'cold' else '薨逝了'
        if h['caretaker_id'] != h['mother_id'] and mother['status'] == 'normal' and mother['rank'] >= 5:
            run('UPDATE heirs SET caretaker_id=?, caretaker_affinity=mother_affinity WHERE id=?', (mother['id'], h['id']))
            gazette(f"{display_name(cur)}{cur_gone}，{label}由生母{display_name(mother)}领回抚养。", 'decree')
            if mother['user_id']:
                notify(mother['id'], f"{display_name(cur)}{cur_gone}，皇上让你把{label}领回去了。", 'good')
            continue
        foster = pick_foster(exclude=(cur['id'], mother['id']))
        if not foster: continue   # 一位合适的都没有，明晚再看
        run('UPDATE heirs SET caretaker_id=?, caretaker_affinity=50 WHERE id=?', (foster['id'], h['id']))
        gazette(f"{display_name(cur)}{cur_gone}，皇上指{display_name(foster)}抚养{label}。", 'decree')
        if cur['user_id']:
            notify(cur['id'], f"你{cur_gone}，{label}被皇上指给{display_name(foster)}抚养了。", 'bad')
        if mother['id'] != cur['id'] and mother['user_id'] and mother['status'] != 'dead':
            notify(mother['id'], f"{label}的抚养人{cur_gone}，皇上指{display_name(foster)}接着抚养。", 'info')
        if foster['user_id']:
            notify(foster['id'], f"皇上把{label}指给你抚养了。去本宫就能教养。", 'good')


# ── 抚养博弈：托付、探视、讨回（九点六节 C） ──────────────────────────────────────

HEIR_VISIT_ENERGY = 1
HEIR_VISIT_GAIN = 4
HEIR_RECLAIM_ENERGY = 1
HEIR_RECLAIM_COOLDOWN = 7
HEIR_ENTRUST_MIN_AFFINITY = 40
HEIR_EXPOSED_PENALTY = 20    # 养母瞒着身世，被生母探视时说破，孩子对养母的情分

def entrust_candidates(c):
    """能托付孩子的人：在线的、嫔以上、正当差、好感够"""
    out = []
    for t in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND rank>=5 AND id!=?", (c['id'],)):
        rel = relation(c['id'], t['id'])
        if rel and rel['affinity'] >= HEIR_ENTRUST_MIN_AFFINITY: out.append(t)
    return out


@app.route('/heirs/entrust/<int:hid>', methods=['POST'])
@login_required
def heir_entrust(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    try: tid = int(request.form.get('target_id', 0))
    except ValueError: tid = 0
    t = get_consort(tid) if tid else None
    err = None
    if not h or h['mother_id'] != c['id'] or h['caretaker_id'] != c['id']: err = '这不是你亲自带着的孩子。'
    elif h['zhuazhou'] or heir_age_days(h) >= ZHUAZHOU_AGE_DAYS: err = '孩子已经周岁，祖制已定，托付不及了。'
    elif c['rank'] >= 5: err = '你已是嫔位，本就可以亲自抚养，不必托付。'
    elif c['status'] != 'normal': err = '眼下这个境况，托付不了人。'
    elif not t or t['id'] not in {x['id'] for x in entrust_candidates(c)}:
        err = f'要托付给嫔位以上、且与你好感不低于 {HEIR_ENTRUST_MIN_AFFINITY} 的姐妹。'
    if err:
        flash(err, 'bad'); return redirect(url_for('heirs'))
    label = heir_label(h)
    run('UPDATE heirs SET foster_request_to=? WHERE id=?', (t['id'], hid))
    notify(t['id'], f"{display_name(c)}想把{label}托付给你抚养。去「子嗣」页点头或回绝。周岁抓周前不答复，祖制就另指别人了。", 'info')
    flash(f"已请{display_name(t)}过目。对方点头之前，孩子还在你身边。", 'good')
    return redirect(url_for('heirs'))


@app.route('/heirs/entrust_reply/<int:hid>', methods=['POST'])
@login_required
def heir_entrust_reply(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    if not h or h['foster_request_to'] != c['id']:
        flash('没有这桩托付。', 'bad'); return redirect(url_for('heirs'))
    mother = get_consort(h['mother_id'])
    label = heir_label(h)
    run('UPDATE heirs SET foster_request_to=0 WHERE id=?', (hid,))
    if request.form.get('reply') != 'yes':
        if mother['user_id']: notify(mother['id'], f"{display_name(c)}婉拒了你托付{label}的请求。", 'bad')
        flash('已回绝。', 'good'); return redirect(url_for('heirs'))
    if c['rank'] < 5 or c['status'] != 'normal' or h['zhuazhou'] or h['caretaker_id'] != h['mother_id'] or mother['status'] == 'dead':
        flash('这桩托付已经办不成了。', 'bad'); return redirect(url_for('heirs'))
    run('UPDATE heirs SET caretaker_id=?, caretaker_affinity=50 WHERE id=?', (c['id'], hid))
    add_affinity(c['id'], mother['id'], 5)
    gazette(f"{display_name(mother)}将{label}托付给{display_name(c)}抚养。", 'news')
    if mother['user_id']: notify(mother['id'], f"{display_name(c)}应下了，{label}往后由她抚养。晋到嫔位后可以去求皇上讨回。", 'good')
    flash(f"{label}往后由你抚养，去本宫就能教养。", 'good')
    return redirect(url_for('heirs'))


@app.route('/heirs/visit/<int:hid>', methods=['POST'])
@login_required
def heir_visit(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    err = None
    if not h or h['mother_id'] != c['id'] or h['caretaker_id'] in (0, c['id']): err = '孩子不在别人宫里，用不着探视。'
    elif c['status'] != 'normal': err = '你现在出不了门。'
    elif c['energy'] < HEIR_VISIT_ENERGY: err = '精力不够了。'
    elif daily_count(c['id'], f'hvisit:{hid}'): err = '今天已经去看过了。'
    else:
        fo = get_consort(h['caretaker_id'])
        if fo['status'] != 'normal': err = '抚养人眼下不在宫里，见不着。'
        elif h['visit_banned'] and fo['user_id']: err = f"{display_name(fo)}不许你探视。"
    if err:
        flash(err, 'bad'); return redirect(url_for('heirs'))
    label = heir_label(h)
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (HEIR_VISIT_ENERGY, c['id']))
    daily_inc(c['id'], f'hvisit:{hid}')
    add_heir_affinity(hid, 'mother', HEIR_VISIT_GAIN)
    msg = f"你去{display_name(fo)}宫里看了{label}，跟生母的情分 +{HEIR_VISIT_GAIN}。"
    if h['concealed']:
        run('UPDATE heirs SET concealed=0 WHERE id=?', (hid,))
        add_heir_affinity(hid, 'caretaker', -HEIR_EXPOSED_PENALTY)
        msg += f"你忍不住说破了身世，{label}才知道被瞒了这么久。"
        if fo['user_id']:
            notify(fo['id'], f"生母来探视{label}，把当年瞒着的身世说破了。{label}对你的情分 -{HEIR_EXPOSED_PENALTY}。", 'bad')
    flash(msg, 'good')
    return redirect(url_for('heirs'))


@app.route('/heirs/ban/<int:hid>', methods=['POST'])
@login_required
def heir_ban(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    if not h or h['caretaker_id'] != c['id'] or h['mother_id'] == c['id']:
        flash('这不是你抱养的孩子。', 'bad'); return redirect(url_for('heirs'))
    run('UPDATE heirs SET visit_banned=? WHERE id=?', (0 if h['visit_banned'] else 1, hid))
    flash('已不许生母探视。' if not h['visit_banned'] else '又许生母来探视了。', 'good')
    return redirect(url_for('heirs'))


@app.route('/heirs/reclaim/<int:hid>', methods=['POST'])
@login_required
def heir_reclaim(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    err = None
    if not h or h['mother_id'] != c['id'] or h['caretaker_id'] in (0, c['id']): err = '孩子本就在你身边。'
    elif c['rank'] < 5: err = '嫔位以上才能求皇上把孩子还回来。'
    elif c['status'] != 'normal': err = '你现在去不了养心殿。'
    elif cur_day() < h['reclaim_after_day']: err = f"皇上刚驳回过，{h['reclaim_after_day'] - cur_day()} 天后才能再求。"
    elif c['energy'] < HEIR_RECLAIM_ENERGY: err = '精力不够了。'
    if err:
        flash(err, 'bad'); return redirect(url_for('heirs'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (HEIR_RECLAIM_ENERGY, c['id']))
    label = heir_label(h)
    old = get_consort(h['caretaker_id'])
    if random.random() < plead_chance(c):
        run('UPDATE heirs SET caretaker_id=?, caretaker_affinity=mother_affinity, visit_banned=0, concealed=0 WHERE id=?', (c['id'], hid))
        gazette(f"{display_name(c)}向皇上求得恩典，将{label}领回亲自抚养。", 'decree')
        if old['user_id']:
            notify(old['id'], f"皇上准了{display_name(c)}的请求，{label}被领回生母身边。", 'bad')
            add_affinity(c['id'], old['id'], -10)
        flash(f"皇上准了。{label}回到你身边，往后由你亲自教养。", 'good')
    else:
        run('UPDATE heirs SET reclaim_after_day=? WHERE id=?', (cur_day() + HEIR_RECLAIM_COOLDOWN, hid))
        flash(f"皇上说：「孩子在{display_name(old)}那里养得好好的。」{HEIR_RECLAIM_COOLDOWN} 天内不能再求。", 'bad')
    return redirect(url_for('heirs'))


@app.route('/heirs/raise/<int:hid>', methods=['POST'])
@login_required
def heir_raise(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    key = request.form.get('opt', '')
    if key == 'ride' and h and h['gender'] == '公主': key = 'ride_girl'
    cfg = HEIR_RAISE.get(key)
    err = None
    if not h or h['caretaker_id'] != c['id']: err = '这不是你在抚养的孩子。'
    elif not cfg: err = '选一样教养的法子。'
    elif c['energy'] < HEIR_RAISE_ENERGY: err = '精力不够了。'
    elif daily_count(c['id'], f'raise:{hid}'): err = '今天已经教养过他了。'
    if err:
        flash(err, 'bad')
        return redirect(url_for('place', key='home'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (HEIR_RAISE_ENERGY, c['id']))
    daily_inc(c['id'], f'raise:{hid}')
    parts = []
    for stat, amt in cfg.get('gain', {}).items():
        if h['personality'] == 'clever' and stat == 'study': amt = round(amt * 1.5)
        elif h['personality'] == 'honest' and stat == 'study': amt = round(amt * 0.7)
        elif h['personality'] == 'naughty' and stat == 'study': amt = round(amt * 0.5)
        elif h['personality'] == 'stubborn' and stat == 'riding': amt = round(amt * 1.3)
        run(f'UPDATE heirs SET {stat}=? WHERE id=?', (clamp(h[stat] + amt), hid))
        parts.append(f"{HEIR_STATS[stat]} +{amt}")
    aff = cfg.get('affinity', 0)
    if h['personality'] == 'honest' and key == 'discipline': aff = round(aff * 1.5)
    if h['personality'] == 'naughty' and key == 'play': aff = round(aff * 2)
    if h['personality'] == 'stubborn' and aff < 0: aff = round(aff * 1.5)
    if h['personality'] == 'timid' and aff > 0: aff = round(aff * 1.5)
    if aff:
        add_heir_affinity(hid, 'caretaker', aff)
        parts.append(f"情分 {aff:+d}")
    flash(f"{cfg['name']}：" + '，'.join(parts) + '。', 'good')
    return redirect(url_for('place', key='home'))


def roll_heir_event(c):
    """每天第一次进本宫时掷一次。同一件事同一个孩子不会遇到两次"""
    if c['status'] == 'cold' or c['heir_event'] or daily_count(c['id'], 'heir_event_roll'): return
    daily_inc(c['id'], 'heir_event_roll')
    if random.random() >= HEIR_EVENT_CHANCE: return
    mine = list(q("SELECT * FROM heirs WHERE caretaker_id=?", (c['id'],)))
    if not mine: return
    random.shuffle(mine)
    day = cur_day()
    others = q("SELECT id FROM consorts WHERE id!=? AND user_id IS NOT NULL AND status='normal'", (c['id'],))
    for key in random.sample(list(HEIR_EVENTS), len(HEIR_EVENTS)):
        ev = HEIR_EVENTS[key]
        if ev.get('needs_target') and not others: continue
        for h in mine:
            if ev.get('foster_only') and (h['caretaker_id'] == h['mother_id'] or heir_age_days(h, day) < HEIR_FOSTER_TALK_AGE_DAYS):
                continue
            if key in json.loads(h['seen_events'] or '[]'): continue
            data = dict(key=key, heir=h['id'], day=day)
            if ev.get('needs_target'): data['target'] = random.choice(others)['id']
            run("UPDATE consorts SET heir_event=? WHERE id=?", (json.dumps(data), c['id']))
            return


def heir_event_view(c):
    try:
        data = json.loads(c['heir_event']) if c['heir_event'] else None
    except ValueError:
        return None
    if not data or data.get('day') != cur_day(): return None
    h = q('SELECT * FROM heirs WHERE id=?', (data['heir'],), one=True)
    if not h or h['caretaker_id'] != c['id']: return None
    t = get_consort(data['target']) if data.get('target') else None
    if data.get('target') and (not t or t['status'] != 'normal'): return None
    ev = HEIR_EVENTS[data['key']]
    names = dict(h=heir_label(h), t=display_name(t) if t else '')
    return ev['text'].format(**names), [o['text'].format(**names) for o in ev['opts']], data, names


@app.route('/heirs/event', methods=['POST'])
@login_required
def heir_event_choose():
    c = g.me
    view = heir_event_view(c)
    if not view:
        run("UPDATE consorts SET heir_event='' WHERE id=?", (c['id'],))
        return redirect(url_for('place', key='home'))
    _, _, data, names = view
    ev = HEIR_EVENTS[data['key']]
    try:
        opt = ev['opts'][int(request.form.get('opt', ''))]
    except (ValueError, IndexError):
        return redirect(url_for('place', key='home'))
    if opt.get('silver') and c['silver'] < -opt['silver']:
        flash(f"手头只有 {c['silver']} 两，拿不出来。", 'bad')
        return redirect(url_for('place', key='home'))
    run("UPDATE consorts SET heir_event='' WHERE id=?", (c['id'],))
    h = q('SELECT * FROM heirs WHERE id=?', (data['heir'],), one=True)
    seen = json.loads(h['seen_events'] or '[]') + [data['key']]
    run("UPDATE heirs SET seen_events=? WHERE id=?", (json.dumps(seen), h['id']))
    parts = []
    if opt.get('silver'):
        add_silver(c['id'], opt['silver']); parts.append(f"银子 {opt['silver']:+d}")
    if opt.get('mother_health'):
        add_stat(c['id'], 'health', opt['mother_health']); parts.append(f"体质 {opt['mother_health']:+d}")
    for stat in ('virtue',):
        if opt.get(stat):
            run(f'UPDATE heirs SET {stat}=? WHERE id=?', (clamp(h[stat] + opt[stat]), h['id']))
            parts.append(f"{HEIR_STATS[stat]} {opt[stat]:+d}")
    if opt.get('favor'):
        run('UPDATE heirs SET favor=favor+? WHERE id=?', (opt['favor'], h['id']))
        parts.append(f"圣眷 {opt['favor']:+d}")
    if opt.get('affinity'):
        add_heir_affinity(h['id'], 'caretaker', opt['affinity']); parts.append(f"情分 {opt['affinity']:+d}")
    if opt.get('conceal'):
        run('UPDATE heirs SET concealed=1 WHERE id=?', (h['id'],))
    if opt.get('to_mother_affinity'):
        add_heir_affinity(h['id'], 'mother', opt['to_mother_affinity']); parts.append(f"跟生母的情分 {opt['to_mother_affinity']:+d}")
    if opt.get('target_affinity') and data.get('target'):
        add_affinity(c['id'], data['target'], opt['target_affinity']); parts.append(f"和{names['t']}好感 {opt['target_affinity']:+d}")
    say = opt['say'].format(**names)
    flash('　'.join(x for x in (say, '，'.join(parts) + ('。' if parts else '')) if x), 'good')
    return redirect(url_for('place', key='home'))


# ── 每晚结算 ───────────────────────────────────────────────────────────────────

def intrigue_success_p(atk, tgt, cfg):
    p = cfg['base'] + (atk['scheme'] - tgt['scheme']) * 0.008
    if atk['personality'] == 'deep': p += 0.05
    if eyes_active(tgt): p -= 0.12
    p -= min(0.15, 0.05 * active_sister_count(tgt['id']))
    if tgt['personality'] == 'dignified': p -= 0.05
    if tgt['virtue'] >= 70: p -= 0.05
    if tgt['rank'] == 9: p -= 0.15
    p -= tgt['trust'] * 0.0015                      # 皇上信任的人难扳倒：信任 100 时 -15%
    if cfg is INTRIGUES['expose']:
        p += (atk['trust'] - 40) * 0.005            # 告发看告发人自己的信任：信任 0 时 -20%，100 时 +30%
    if cfg is INTRIGUES['frame'] and same_palace(atk, tgt):
        p += 0.10
    if cfg is INTRIGUES['rumor'] and has_maid_trait(atk['id'], 'suizui'):
        p += 0.10                                   # 碎嘴的宫人替主子把话传出去
    return max(0.08, min(0.85, p))

def intrigue_caught_p(atk, tgt):
    p = 0.35 + (tgt['scheme'] - atk['scheme']) * 0.005 + (0.25 if eyes_active(tgt) else 0)
    if state()['emperor_mood'] == '震怒': p += 0.1
    return max(0.15, min(0.8, p))

def resolve_intrigue(it, bed_id=None):
    """结算一条阴谋。steal 需要传入今晚被翻牌的人。返回 (result, 被截宠后的新侍寝人或 None)"""
    if it['method'] == 'drug': return resolve_drug(it)
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
    if it['method'] == 'punish' and (atk['status'] != 'normal' or not punishable_maids(tgt['id'])):
        if atk['user_id']: notify(atk['id'], f"你想发落{tn}的宫人，可眼下找不到由头，只好作罢。")
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
            night_mark(tgt['id'], 'poisoned')
        elif m == 'rumor':
            trusted = tgt['trust'] >= TRUSTED_LINE
            loss = cut_favor(tgt['id'], 0.075 if trusted else 0.15, 5 if trusted else 10)
            add_stat(tgt['id'], 'virtue', -3)
            night_mark(tgt['id'], 'victim', trusted=trusted)
            victim = f"宫里起了关于你的流言，是{who}在背后散播。圣宠 -{loss}，德行 -3。" + \
                     ('皇上信你，没全当真。' if trusted else '')
            gz = f"宫中有流言说{tn}品行不端，传得有鼻子有眼。"
        elif m == 'frame':
            trusted = tgt['trust'] >= TRUSTED_LINE
            loss = cut_favor(tgt['id'], 0.1 if trusted else 0.2)
            confine(tgt['id'], CONFINE_DAYS)
            night_mark(tgt['id'], 'victim', trusted=trusted)
            victim = f"你宫里搜出了不该有的东西，{who}栽赃陷害了你。禁足 {CONFINE_DAYS} 天，圣宠 -{loss}。" + \
                     ('皇上信你，圣宠只折了一半。' if trusted else '')
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
                night_mark(tgt['id'], 'miscarriage')
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
            add_trust(tgt['id'], -15)
            add_trust(atk['id'], 5)
            victim = f"{an}在皇上面前告发你{sec['name']}。皇上震怒：{sec['penalty']}。"
            gz = f"{an}告发{tn}{sec['name']}，皇上震怒，{sec['penalty']}。"
        elif m == 'punish':
            maid = random.choice(punishable_maids(tgt['id']))
            maid_leave(maid['id'], 'dead', f"被{an}以冲撞为由拖去慎刑司，杖毙")
            for other in active_maids(tgt['id']):
                add_loyalty(other['id'], -5)
            run('UPDATE consorts SET maid_punished_day=? WHERE id=?', (cur_day(), tgt['id']))
            # 发落是明面上的欺压：主子一定知道是谁，不看眼线
            victim = f"{an}说你宫里的{maid['name']}冲撞了她，把人拖去慎刑司，杖毙了。宫里的人都吓坏了，全宫宫人忠心 -5。"
            gz = f"{tgt['palace']}宫人{maid['name']}没了。"
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
        elif m == 'punish':
            add_stat(atk['id'], 'virtue', -8)
            pen = '德行 -8'
        else:  # witch
            send_to_cold(atk['id'])
            pen = '打入冷宫'
        if mood_extra and m != 'witch':
            cut_favor(atk['id'], 0.1); pen += '（皇上正在气头上，圣宠再 -10%）'
        if atk['user_id']:
            tloss = 10 if m in ('expose', 'punish') else 15
            add_trust(atk['id'], -tloss)
            pen += f'，信任 -{tloss}'
            night_mark(atk['id'], 'caught')
        if atk['user_id']: notify(atk['id'], f"你对{tn}的「{cfg['name']}」败露了。{pen}。", 'bad')
        if tgt['user_id']: notify(tgt['id'], f"{an}想对你「{cfg['name']}」，被当场拿住。", 'good')
        if m == 'expose':
            gazette(f"{an}在御前告发{tn}，查无实据，皇上斥其搬弄是非。", 'scandal')
        else:
            gazette(f"{an}意图{cfg['name']}{tn}，事情败露。{pen}。", 'scandal')
        return done('caught')

    if atk['user_id']: notify(atk['id'], f"你对{tn}的「{cfg['name']}」没成，好在没人察觉。")
    if it['method'] == 'punish' and tgt['user_id']:
        notify(tgt['id'], f"{an}想找由头发落你宫里的人，被你挡了回去。")
    return done('fizzle')

def npc_schemes(day):
    """NPC 按性子出手，写进今晚的阴谋队列"""
    for npc in q("SELECT * FROM consorts WHERE npc_key IS NOT NULL AND status='normal' AND aggression>0"):
        if random.random() >= npc['aggression']: continue
        players = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND entered_day<?""", (day,))
        if not players: return
        key = npc['npc_key']
        if key == 'huanghou':
            preg = [p for p in players if p['pregnant_since']
                    and not drug_block(npc, p, 'hanshui', 'hanshui', 0, day, False)]
            if preg: target, method = random.choice(preg), 'drug'
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
        drug = 'hanshui' if method == 'drug' else ''   # 皇后给有孕的人下寒水散
        run("""INSERT INTO intrigues (day, attacker_id, target_id, method, item_used, drug, created_ts)
               VALUES (?,?,?,?,?,?,?)""", (day, npc['id'], target['id'], method, drug, drug, now_ts()))
    huafei_punish(day)

def bed_weight(c, day):
    w = 10 + c['favor'] * 0.15 + c['appearance'] * 0.3 + c['talent'] * 0.15 + c['seek_bonus']
    if emperor_art_bonus(c): w += 20
    if c['user_id'] and day - c['entered_day'] <= 3: w += 15   # 皇上喜新
    if c['personality'] == 'charming': w *= 1.15
    if c['npc_key']: w *= NPC_BED_MULT
    return max(1, w)

@atomic
def settle_day():
    with settle_lock:
        # 结算期间 notify/gazette 会标成"夜间"，night_mark 记下每个人这一夜的经历，最后据此下口谕
        g.settling, g.night_events = True, {}
        try:
            return _settle_night()
        finally:
            g.settling, g.night_events = False, {}

def audience_weight(c, day):
    """召见权重 = 10 + 信任 × 0.3 + 多少天没见过皇上 × 4（最多算 10 天）。久未见驾的人更容易被想起"""
    return 10 + c['trust'] * 0.3 + min(10, day - c['last_audience_day']) * 4

def _settle_night():
    st = state()
    day = st['day']
    report = []

    # 白天没来得及定夺的场景、昨夜的侍寝/召见场景，到今晚都作废
    run("UPDATE consorts SET pending_scene='' WHERE pending_scene!=''")

    # 先处理之前几天中的毒、病重；当晚新中毒/病倒的人不会当晚就死
    resolve_poison_crises(day)
    resolve_illness_crises(day)
    resolve_drug_cases(day)

    # 1. NPC 出手 + 结算阴谋（截宠除外，要等翻牌子）
    npc_schemes(day)
    pend = q("SELECT * FROM intrigues WHERE status='pending' AND day<=? AND method!='steal'", (day,))
    pend = list(pend); random.shuffle(pend)
    for it in pend:
        resolve_intrigue(it)

    tick_drugs(day)

    # 2. 翻牌子
    cands = [c for c in q("""SELECT * FROM consorts WHERE status='normal' AND rank BETWEEN 1 AND 8
                             AND pregnant_since=0""") if not is_sick(c) and not affliction(c['id'], 'yanzhi', day)]
    bed = None
    if cands:
        bed = random.choices(cands, weights=[bed_weight(c, day) for c in cands])[0]
        steals = list(q("SELECT * FROM intrigues WHERE status='pending' AND method='steal' AND day<=?", (day,)))
        random.shuffle(steals)
        for it in steals:
            _, new_bed = resolve_intrigue(it, bed['id'] if bed else None)
            if new_bed and bed and new_bed != bed['id']:
                nb = get_consort(new_bed)
                if nb['status'] == 'normal' and not nb['pregnant_since'] and not is_sick(nb) and not affliction(nb['id'], 'yanzhi', day):
                    bed = nb
    if bed:
        bed = get_consort(bed['id'])
        # 敬事房这一盘递上去的绿头牌：权重最高的 7 块 + 被翻的那块，打乱顺序，给「昨夜宫中」回放用
        tray = [c['id'] for c in sorted(cands, key=lambda c: -bed_weight(c, day))[:7]]
        if bed['id'] not in tray: tray[-1:] = [bed['id']]
        random.shuffle(tray)
        dream = affliction(bed['id'], 'jingmeng', day)
        if dream:
            cut_favor(bed['id'], 0.30)
            add_trust(bed['id'], -5)
            gain = 0
            open_drug_case(q('SELECT * FROM intrigues WHERE id=?', (dream['intrigue_id'],), one=True))
            notify(bed['id'], '惊梦香发作，惊扰圣驾，圣宠 -30%、信任 -5。', 'bad')
        else:
            gain = add_favor(bed['id'], 20 + bed['appearance'] * 0.15)
        run("UPDATE consorts SET bedded_count=bedded_count+1, last_audience_day=? WHERE id=?", (day, bed['id']))
        run("UPDATE game_state SET last_bed_id=?, last_bed_day=?, last_bed_pool=? WHERE id=1",
            (bed['id'], day, json.dumps(tray)))
        gazette(f"敬事房：今夜皇上翻了{display_name(bed)}的牌子。", 'bed')
        if bed['user_id']:
            msg = f"敬事房来传话：今夜皇上翻了你的牌子。圣宠 +{gain}。"
            newly_pregnant = False
            if not affliction(bed['id'], 'hanshui', day) and bed['age_months'] < FERTILE_BEFORE_AGE * 12 and random.random() < 0.12 + bed['health'] / 1000:
                run("UPDATE consorts SET pregnant_since=? WHERE id=?", (day, bed['id']))
                msg += f"……太医诊出了喜脉，{PREGNANCY_DAYS} 天后临盆。"
                gazette(f"{display_name(bed)}有喜了。", 'birth')
                newly_pregnant = True
            notify(bed['id'], msg, 'good')
            guide_tip(bed['id'], 'bed', '「头一回侍寝，忐忑也是常事。往后皇上想起你，全看这几日的功夫。」')
            if newly_pregnant:
                guide_tip(bed['id'], 'pregnant', '「有喜是大事，往后当心着些，别的事都往后放一放。」')
            start_scene(bed['id'], 'audience', prompt=random.randrange(len(AUDIENCE_PROMPTS)), bed=1, hoarse=bool(affliction(bed['id'], 'yachan', day)))
        housing_visit(bed)
        report.append(f"侍寝：{display_name(bed)}")

    # 2b. 召见：侍寝之外，另召几位玩家单独说话，让更多人有机会见到皇上
    pool = [c for c in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal'")
            if not is_sick(c) and not (bed and c['id'] == bed['id'])]
    called = []
    for _ in range(min(AUDIENCE_PER_NIGHT, len(pool))):
        r = random.choices(pool, weights=[audience_weight(c, day) for c in pool])[0]
        pool.remove(r); called.append(r)
        add_favor(r['id'], 5)
        run("UPDATE consorts SET last_audience_day=? WHERE id=?", (day, r['id']))
        notify(r['id'], '苏培盛来传话：皇上要召你去养心殿说话。圣宠 +5。', 'good')
        guide_tip(r['id'], 'audience', '「皇上召见，规规矩矩应答就是，不必太紧张。」')
        start_scene(r['id'], 'audience', prompt=random.randrange(len(AUDIENCE_PROMPTS)), bed=0, hoarse=bool(affliction(r['id'], 'yachan', day)))
    if called:
        gazette(f"皇上召见了{'、'.join(display_name(c) for c in called)}。", 'audience')
        report.append('召见：' + '、'.join(display_name(c) for c in called))

    # 同宫日间动向先回报，管教在生产与迁宫前处理。
    housing_reports(day)
    npc_housing_discipline(day)

    # 3. 生产
    for c in q("SELECT * FROM consorts WHERE status!='dead' AND pregnant_since>0 AND ?-pregnant_since>=?", (day, PREGNANCY_DAYS)):
        gender = random.choice(['皇子', '公主'])
        n = q("SELECT COUNT(*) n FROM heirs WHERE gender=?", (gender,), one=True)['n']
        ordinal = n + (6 if gender == '皇子' else 3)
        personality = random.choice(list(HEIR_PERSONALITIES))
        run("""INSERT INTO heirs (mother_id, caretaker_id, gender, ordinal, born_day, personality, study, riding, virtue, health)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (c['id'], c['id'], gender, ordinal, day, personality,
             clamp(random.randint(10, 30) + c['talent'] * 0.1, 0, 100),
             clamp(random.randint(10, 30), 0, 100),
             clamp(random.randint(10, 30) + c['virtue'] * 0.1, 0, 100),
             clamp(60 + c['health'] * 0.1, 0, 100)))
        run("UPDATE consorts SET pregnant_since=0 WHERE id=?", (c['id'],))
        extra = ''
        if c['health'] < 50 and random.random() < 0.3:
            add_stat(c['id'], 'health', -20); extra = '难产了一整夜，元气大伤，体质 -20。'
            run('UPDATE consorts SET postpartum_until=? WHERE id=?', (day + POSTPARTUM_SICK_DAYS, c['id']))
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
        night_mark(c['id'], 'birth', label=label, son=gender == '皇子')

    # 3b. 皇嗣周岁抓周（贵人以下的生母，这天孩子按祖制改指给别人抚养）、皇上考校、随驾秋狝
    heir_growth_tick(day)
    heir_rehome_tick(day)
    heir_exam_tick(day)
    heir_hunt_tick(day)

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
        quick = bool(c['last_promote_day']) and day - c['last_promote_day'] <= 4
        set_rank(c['id'], nxt)
        c2 = get_consort(c['id'])
        gazette(f"圣旨：{full_name(c2)}晋为{display_name(c2)}。", 'decree')
        notify(c['id'], f"圣旨到：晋你为{display_name(c2)}。", 'decree')
        night_mark(c['id'], 'promoted', quick=quick, rank=RANK_NAMES[nxt])
        report.append(f"晋封：{display_name(c2)}")

    # 位分全部定下后，按位分、圣宠安置等待正殿的人。
    housing_sync()

    # 5. 日常：长半岁、月例、圣宠流失、精力、禁足/冷宫期满、请安
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
            if c['user_id']:
                notify(c['id'], '禁足期满，你又能出门了。', 'good')
                night_mark(c['id'], 'unconfined')
        elif c['status'] == 'cold' and c['user_id'] and c['status_until_day'] <= day:
            release_from_cold(c['id'], '皇上念及旧情，')
        if c['user_id'] and c['status'] == 'normal' and c['entered_day'] < day and c['greet_day'] < day:
            missed = c['missed_greet'] + 1
            run("UPDATE consorts SET missed_greet=? WHERE id=?", (missed, c['id']))
            if missed >= 2:
                add_stat(c['id'], 'virtue', -3)
                notify(c['id'], f"你已经 {missed} 天没去给皇后请安了，宫里说你恃宠而骄。德行 -3。", 'bad')

    # 5a. 老死、染病：年岁到了、体虚、冷宫、时疫、产后失调
    old_age_tick(day)
    illness_onset_tick(day)

    # 5b. 宫人：月钱、忠心、病好了没有；白天没处理的小事作废
    drug_gifts(day)
    maid_upkeep(day)

    # 6. 口谕：根据每个人这一夜的真实经历挑一句，没什么可说的就不说
    issue_edicts(day)

    # 7. 进入新的一天
    new_day = day + 1
    mood = random.choices(['大悦', '平和', '烦闷', '震怒'], weights=[15, 55, 22, 8])[0]
    pref = random.choice(ARTS) if new_day % 7 == 1 else st['emperor_pref']
    run("UPDATE game_state SET day=?, last_settle_date=?, emperor_mood=?, emperor_pref=? WHERE id=1",
        (new_day, datetime.now(TZ).date().isoformat(), mood, pref))
    if pref != st['emperor_pref']:
        gazette(f"听养心殿的人说，皇上这几日格外喜欢{pref}。", 'news', day=new_day)
    return report

# ── 口谕 ───────────────────────────────────────────────────────────────────────
# 按优先级取第一条命中的：当夜经历 > 入宫周年 > 皇嗣六岁 > 久未见驾。都不命中就不发。

EDICT_ORDER = ['poisoned', 'ill', 'rescued', 'ill_rescued', 'cold_release', 'miscarriage', 'birth', 'caught',
               'victim', 'promoted', 'unconfined']

def edict_for_event(key, data):
    if key == 'poisoned':     return '朕已命太医院全力救治，你要撑住。'
    if key == 'ill':          return '好端端怎么病倒了，太医院不许怠慢。'
    if key == 'rescued':      return '太医说你已无大碍，朕才放心。'
    if key == 'ill_rescued':  return '病去如抽丝，往后多当心身子。'
    if key == 'cold_release': return '冷宫里那些日子，委屈你了。'
    if key == 'miscarriage':  return '孩子的事，朕会给你一个交代。'
    if key == 'birth':
        return f"辛苦你了。{data['label']}的眉眼，像你。" if data['son'] else f"朕很喜欢{data['label']}，你好好养着身子。"
    if key == 'caught':       return '朕没想到，你也会做这种事。'
    if key == 'victim':
        return '宫里那些闲话，朕不信。' if data['trusted'] else '宫里那些话，朕都听说了。你好自为之。'
    if key == 'promoted':
        return '六宫的眼睛都看着你，莫失了分寸。' if data['quick'] else f"如今是{data['rank']}了，往后更要谨言慎行。"
    if key == 'unconfined':   return '这些日子，可想明白了？'
    return None

def memory_edict(c, day):
    """没有当夜大事时，看看有没有值得皇上记起的旧事"""
    nights = day - c['entered_day'] + 1          # 过完今晚，入宫一共多少个半年
    if c['entered_day'] and nights > 0 and nights % 10 == 0:
        years = cn_ordinal(nights // 2)
        q_ = c['dianxuan_quote']
        if q_:
            said = f"你说{q_}" if q_.startswith('「') else f"你{q_}"
            return f"你入宫{years}年了。朕还记得殿选那日，{said.rstrip('。')}。"
        return f"你入宫{years}年了。"
    for h in q("SELECT * FROM heirs WHERE mother_id=? AND ?-born_day=12", (c['id'], day)):
        return f"{heir_label(h)}六岁了，朕想着该给{'他' if h['gender'] == '皇子' else '她'}挑个师傅。"
    unseen = day - c['last_audience_day']
    if c['status'] == 'normal' and unseen >= LONG_UNSEEN_DAYS and unseen % LONG_UNSEEN_DAYS == 0:
        arts = arts_of(c)
        best = max(arts, key=arts.get) if arts else None
        if best and arts[best] >= 3:
            # 皇上想起你了：明晚翻牌子加 20 权重（seek_bonus 在今晚已清零，这里设的值留到明晚）
            run("UPDATE consorts SET seek_bonus=20 WHERE id=?", (c['id'],))
            if arts[best] >= ART_MASTERY:
                return f"朕记得，你从前最擅{best}。"
            return f"听说你一直在练{best}，改日弹给朕听听。" if best == '琴' else f"听说你一直在练{best}，改日让朕瞧瞧。"
    return None

def issue_edicts(day):
    for c in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead')"):
        ev = g.night_events.get(c['id'], {})
        line = next((edict_for_event(k, ev[k]) for k in EDICT_ORDER if k in ev), None)
        if not line and c['status'] != 'cold':
            line = memory_edict(c, day)
        if line:
            notify(c['id'], f"苏培盛来传皇上口谕：「{line}」", 'edict')

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
    reports = q("SELECT * FROM reports WHERE status='open' ORDER BY id")
    done_reports = q("SELECT * FROM reports WHERE status!='open' ORDER BY handled_ts DESC LIMIT 10")
    banned = q("SELECT id, username FROM users WHERE banned=1 ORDER BY id")
    broadcasts = q("""SELECT broadcast_id, MIN(body) body, MIN(silver) silver, MIN(item_key) item_key,
                      COUNT(*) total, SUM(claimed) got, MIN(created_ts) created_ts
                      FROM letters WHERE broadcast_id>0 GROUP BY broadcast_id ORDER BY broadcast_id DESC LIMIT 20""")
    players = q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead') ORDER BY rank DESC")
    return render_template('admin.html', rows=rows, pend=pend, get_consort=get_consort, INTRIGUES=INTRIGUES,
                           SECRETS=SECRETS, reports=reports, done_reports=done_reports, banned=banned,
                           broadcasts=broadcasts, players=players, dn=display_name)

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
    housing_sync()
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

@app.route('/admin/broadcast', methods=['POST'])
@admin_required
def admin_broadcast():
    f = request.form
    body = f.get('body', '').strip()
    try: amt = max(0, int(f.get('silver', 0) or 0))
    except ValueError: amt = 0
    item = f.get('item', '')
    target = f.get('target', 'all')
    ids = f.getlist('to_ids')
    if not body:
        flash('总要写点什么。', 'bad')
        return redirect(url_for('admin'))
    if item and item not in ITEMS:
        flash('没有这样东西。', 'bad')
        return redirect(url_for('admin'))
    if target == 'all':
        recipients = [r['id'] for r in q("SELECT id FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead')")]
    else:
        try: recipients = [int(i) for i in ids]
        except ValueError: recipients = []
        recipients = [r['id'] for r in q(f"SELECT id FROM consorts WHERE id IN ({','.join('?' * len(recipients)) or '0'}) AND user_id IS NOT NULL AND status NOT IN ('xiunv','dead')", recipients)] if recipients else []
    if not recipients:
        flash('没有能收到信的人。', 'bad')
        return redirect(url_for('admin'))
    claimed = 0 if (amt or item) else 1
    first = run("""INSERT INTO letters (from_id, to_id, day, body, silver, item_key, is_broadcast, claimed, created_ts)
                   VALUES (0,?,?,?,?,?,1,?,?)""", (recipients[0], cur_day(), body, amt, item, claimed, now_ts())).lastrowid
    run("UPDATE letters SET broadcast_id=? WHERE id=?", (first, first))
    for rid in recipients[1:]:
        run("""INSERT INTO letters (from_id, to_id, day, body, silver, item_key, is_broadcast, broadcast_id, claimed, created_ts)
               VALUES (0,?,?,?,?,?,1,?,?,?)""", (rid, cur_day(), body, amt, item, first, claimed, now_ts()))
        notify(rid, '内务府差人送来一封信，去「书信」看看。', 'good')
    notify(recipients[0], '内务府差人送来一封信，去「书信」看看。', 'good')
    flash(f'已群发给 {len(recipients)} 位。', 'good')
    return redirect(url_for('admin'))

@app.route('/admin/reset', methods=['POST'])
@admin_required
def admin_reset():
    if request.form.get('confirm') != '重开':
        flash('要在框里输入「重开」才会重置。', 'bad')
        return redirect(url_for('admin'))
    for t in ('intrigues', 'messages', 'gazette', 'relations', 'known_secrets', 'inventory', 'heirs', 'letters', 'letter_stars', 'reports', 'maids',
              'bribes', 'afflictions', 'cases', 'case_suspects', 'case_actions',
              'hobby_projects', 'hobby_items', 'displays', 'daily_counters', 'consorts', 'game_state'):
        run(f"DELETE FROM {t}")
    if request.form.get('keep_users') != '1':
        run("DELETE FROM users")
    run('UPDATE users SET lethal_ready_day=0')
    init_db()
    flash('已重开一届选秀。', 'good')
    return redirect(url_for('admin'))

@app.route('/admin/report/<int:rid>', methods=['POST'])
@admin_required
def admin_report_handle(rid):
    r = q("SELECT * FROM reports WHERE id=?", (rid,), one=True)
    if not r or r['status'] != 'open':
        flash('这条举报已经处理过了。', 'bad')
        return redirect(url_for('admin'))
    action = request.form.get('action')
    done = []
    if action in ('delete', 'ban') and r['letter_id']:
        run("UPDATE letters SET body='【该信件因违规已被管理员删除】' WHERE id=?", (r['letter_id'],))
        done.append('已删除该信件')
    if action == 'ban':
        t = get_consort(r['target_id']) if r['target_id'] else None
        if t and t['user_id']:
            run("UPDATE users SET banned=1 WHERE id=?", (t['user_id'],))
            done.append('已停用被举报账号')
    if action == 'dismiss':
        done.append('经核实不违规，不予处理')
    elif not done:
        flash('没有可执行的处理。', 'bad')
        return redirect(url_for('admin'))
    run("UPDATE reports SET status=?, result=?, handled_ts=? WHERE id=?",
        ('dismissed' if action == 'dismiss' else 'done', '；'.join(done), now_ts(), rid))
    notify(r['reporter_id'], '你的举报已由管理员处理：' + '；'.join(done) + '。', 'info')
    flash('已处理。', 'good')
    return redirect(url_for('admin'))

@app.route('/admin/unban/<int:uid>', methods=['POST'])
@admin_required
def admin_unban(uid):
    run("UPDATE users SET banned=0 WHERE id=?", (uid,))
    flash('已解除停用。', 'good')
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


def die(cid, reason, memorial_reason=None):
    c = get_consort(cid)
    if c['status'] == 'dead':
        return
    name = display_name(c)
    run("""UPDATE consorts SET status='dead', death_day=?, death_reason=?, archived_user_id=user_id,
           pregnant_since=0, poisoned_day=0, poison_treatment=0, ill_day=0, ill_treatment=0,
           energy=0, seek_bonus=0, status_until_day=0, hall='', housing_waiting='' WHERE id=?""",
        (cur_day(), memorial_reason or reason, cid))
    run("UPDATE intrigues SET status='done', result='void' WHERE status='pending' AND (attacker_id=? OR target_id=?)", (cid, cid))
    for m in active_maids(cid):
        maid_leave(m['id'], 'gone', '主子没了，散去')
    housing_sync(fill_main=not settling())
    if c['user_id']: notify(cid, f'你因{reason}离世，终年{age_text(c["age_months"])}。可以另建一位秀女重新入宫。', 'bad')
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
            night_mark(c['id'], 'rescued')
            gazette(f'{display_name(c)}脱离险境，留宫静养。', 'news')


def fall_ill(cid, day, cause):
    """染病，走和中毒一样的生死判定：下一次结算前请太医，九成能活，不请只有三成五"""
    c = get_consort(cid)
    if c['status'] == 'dead' or c['ill_day'] or c['poisoned_day']: return   # 已经病着或中毒着，不重复触发
    run('UPDATE consorts SET ill_day=?, ill_treatment=0, weak_days=0, health=MAX(1,health-15) WHERE id=?', (day, cid))
    if c['user_id']:
        notify(cid, f'你{cause}，病倒了。体质 -15。下一次结算前请太医（{TREAT_COST} 两，姐妹也能替你请）：'
                    f'请了九成能活，不请只有三成五。', 'bad')
        guide_tip(cid, 'sick', '「病来如山倒，别硬撑，该请太医就请，银子不能省。」')
    gazette(f'{display_name(c)}{cause}，卧床不起。')
    night_mark(cid, 'ill')


def resolve_illness_crises(day):
    for c in q("SELECT * FROM consorts WHERE status!='dead' AND ill_day>0 AND ill_day<?", (day,)):
        if random.random() >= POISON_SURVIVE[min(1, c['ill_treatment'])]:
            die(c['id'], '病重不治', memorial_reason='病逝')
        else:
            run('''UPDATE consorts SET ill_day=0, ill_treatment=0,
                   protected_until_day=?, health=MAX(health,35) WHERE id=?''', (day + RESCUE_PROTECT_DAYS, c['id']))
            if c['user_id']:
                notify(c['id'], f'你的病好了。接下来 {RESCUE_PROTECT_DAYS} 天好好静养。', 'good')
                night_mark(c['id'], 'ill_rescued')
            gazette(f'{display_name(c)}病愈，留宫静养。', 'news')


def illness_onset_tick(day):
    """每晚判定会不会染病：连续体虚、冷宫阴寒、全宫时疫、产后失调"""
    epidemic = day % EPIDEMIC_INTERVAL == 0 and random.random() < EPIDEMIC_CHANCE
    if epidemic: gazette('宫里近来时疫流传，人人自危。', 'news')
    for c in q("SELECT * FROM consorts WHERE status!='dead'"):
        if c['ill_day'] or c['poisoned_day']: continue
        if c['health'] < 25:
            weak = c['weak_days'] + 1
            run('UPDATE consorts SET weak_days=? WHERE id=?', (weak, c['id']))
            if weak >= WEAK_SICK_DAYS:
                fall_ill(c['id'], day, '久病体虚'); continue
        elif c['weak_days']:
            run('UPDATE consorts SET weak_days=0 WHERE id=?', (c['id'],))
        if c['status'] == 'cold' and random.random() < COLD_SICK_CHANCE:
            fall_ill(c['id'], day, '在冷宫里冻着了'); continue
        if c['postpartum_until'] >= day and random.random() < POSTPARTUM_SICK_CHANCE:
            fall_ill(c['id'], day, '产后没调养好'); continue
        if epidemic and random.random() < (100 - c['health']) / 100:
            fall_ill(c['id'], day, '染上了时疫')


def old_age_tick(day):
    """50 岁起每晚可能寿终；55 岁起每满 5 岁提醒一句；嫔以上寿终按信任追封"""
    for c in q("SELECT * FROM consorts WHERE status!='dead' AND age_months>=?", (OLD_AGE_START,)):
        years_over = (c['age_months'] - OLD_AGE_START) / 12
        p = years_over * OLD_AGE_BASE
        if c['health'] >= 60: p /= 2
        elif c['health'] < 30: p *= 2
        if random.random() < p:
            if c['rank'] >= 5:
                if c['trust'] >= 70 and c['rank'] < PLAYER_MAX_RANK:
                    set_rank(c['id'], c['rank'] + 1, reason_day=day)
                elif c['trust'] >= 40:
                    pool = [w for w in SHI_WORDS if w not in c['title']] or SHI_WORDS
                    run("UPDATE consorts SET title=? WHERE id=?", (c['title'] + random.choice(pool), c['id']))
            die(c['id'], '寿终')
        elif c['user_id'] and c['age_months'] >= OLD_AGE_REMINDER_START and c['age_months'] % OLD_AGE_REMINDER_STEP == 0:
            notify(c['id'], '许嬷嬷：「近来总觉得精神短了，小主往后多静养些。」')


@app.route('/treat/<int:tid>', methods=['POST'])
@login_required
def treat(tid):
    """请太医：本人（禁足、冷宫也行）或姐妹/好感 30 以上的人都能请，谁请谁出银子。中毒、病重都走这个"""
    c, t = g.me, get_consort(tid)
    crisis = 'poison' if t and t['poisoned_day'] else ('ill' if t and t['ill_day'] else None)
    err = None
    if not t or not crisis or t['status'] == 'dead':
        err = '她现在不需要请太医。'
    elif c['id'] != tid and not (tid in sisters_of(c['id']) or
                                 (relation(c['id'], tid) or {'affinity': 0})['affinity'] >= 30):
        err = '你与她交情不够，要结为姐妹或好感 30 以上才能替她请太医。'
    elif (t['poison_treatment'] if crisis == 'poison' else t['ill_treatment']):
        err = '太医已经在了。'
    elif c['silver'] < TREAT_COST:
        err = f'请太医要 {TREAT_COST} 两银子。'
    if err:
        flash(err, 'bad')
    else:
        add_silver(c['id'], -TREAT_COST)
        col = 'poison_treatment' if crisis == 'poison' else 'ill_treatment'
        run(f'UPDATE consorts SET {col}=1 WHERE id=?', (tid,))
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
    past_maids = q("""SELECT m.* FROM maids m JOIN consorts c ON c.id=m.owner_id
                       WHERE (c.user_id=? OR c.archived_user_id=?) AND m.status!='active'
                       ORDER BY m.left_day DESC, m.id DESC""", (S['uid'], S['uid']))
    return render_template('memorial.html', c=c, history=history, past_maids=past_maids, get_consort=get_consort)


@app.route('/rebirth', methods=['POST'])
@login_required
def rebirth():
    if g.me['status'] != 'dead':
        return redirect(url_for('index'))
    # 保留旧角色、皇嗣和事件引用；仅释放账号的一人一角约束。
    run("UPDATE consorts SET user_id=NULL WHERE id=? AND status='dead'", (g.me['id'],))
    return redirect(url_for('create'))


# ── 宫城地图 / 地点 ────────────────────────────────────────────────────────────

PLACES = {
    'home':    dict(name='本宫', actions=['study', 'groom', 'rest', 'reflect', 'eyes']),
    'jingren': dict(name='景仁宫', actions=['greet']),
    'garden':  dict(name='御花园', actions=['garden']),
    'yangxin': dict(name='养心殿', actions=['seek', 'plead']),
}


def map_tiles(c):
    day, st = cur_day(), state()
    cold = c['status'] == 'cold'
    garden_left = ACTIONS['garden']['daily'] - daily_count(c['id'], 'garden')
    n_players = q("SELECT COUNT(*) n FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead') AND id!=?",
                  (c['id'],), one=True)['n']
    unread = q("SELECT COUNT(*) n FROM letters WHERE to_id=? AND is_read=0", (c['id'],), one=True)['n']
    shut = '冷宫出不去' if cold else ('禁足中' if c['status'] == 'confined' else None)
    return [
        dict(key='garden', name='御花园', area='garden', url=url_for('place', key='garden'),
             note=shut or (f'还能逛 {garden_left} 次' if garden_left > 0 else '今天逛够了'), off=bool(shut)),
        dict(key='yangxin', name='养心殿', area='yangxin', url=url_for('place', key='yangxin'),
             note=shut or f"皇上今日{st['emperor_mood']}", off=bool(shut)),
        dict(key='home', name=residence_name(c), area='home', url=url_for('place', key='home'),
             note=f"精力 {c['energy']}", off=False, home=True),
        dict(key='jingren', name='景仁宫', area='jingren', url=url_for('place', key='jingren'),
             note=shut or ('今日已请安' if c['greet_day'] == day else '还没去请安'), off=bool(shut)),
        dict(key='neiwu', name='内务府', area='neiwu', url=url_for('shop'), note=f"银子 {c['silver']} 两", off=cold),
        dict(key='liugong', name='六宫', area='liugong', url=url_for('social'), note=f'{n_players} 位小主', off=False),
        dict(key='letters', name='书信', area='letters', url=url_for('letters'),
             note=f'{unread} 封未读' if unread else '写信传话', off=False, alert=bool(unread)),
    ]

@app.route('/place/<key>')
@login_required
def place(key):
    c = g.me
    if key not in PLACES:
        return redirect(url_for('index'))
    r = pending_redirect(c)
    if r: return r
    day, st = cur_day(), state()
    acts = [(k, ACTIONS[k]) for k in PLACES[key]['actions'] if c['status'] in ACTIONS[k]['when']]
    counts = {k: daily_count(c['id'], k) for k in PLACES[key]['actions']}
    title, desc, extra = PLACES[key]['name'], '', ''
    maid_ev, maid_info, heir_ev, my_heirs = None, None, None, []
    if key == 'home':
        roll_maid_event(c)
        roll_heir_event(c)
        c = get_consort(c['id'])
        maid_ev = maid_event_view(c)
        maid_info = dict(n=len(active_maids(c['id'])), quota=maid_quota(c['rank']), errands=len(free_errand_maids(c)))
        heir_ev = heir_event_view(c)
        my_heirs = q("SELECT * FROM heirs WHERE caretaker_id=?", (c['id'],))
        title = residence_name(c)
        if c['status'] == 'cold':
            desc = '四面高墙，窗纸破了也没人来补。'
        elif has_residence(c):
            desc = (PALACES[c['palace']]['main'] if c['hall'] == 'main' else '') + HALL_DESCS[c['hall']]
        else:
            desc = '行李暂且收好，等内务府来传话。'
    elif key == 'jingren':
        desc = '皇后的居所。每日晨昏定省，六宫都在这里碰面。'
        came = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND greet_day=? AND status='normal'
                    ORDER BY rank DESC""", (day,))
        extra = ('今日已来请安：' + '、'.join(display_name(x) for x in came)) if came else '今日还没有人来请安。'
    elif key == 'garden':
        desc = '春日里杏花开得正好，千鲤池边常有人走动。' if day % 2 else '入秋了，满园的菊花，风里有桂花香。'
    elif key == 'yangxin':
        desc = f"皇上批折子的地方。今日皇上{st['emperor_mood']}，近来喜欢{st['emperor_pref']}。"
        lb = get_consort(st['last_bed_id']) if st['last_bed_id'] else None
        if lb: extra = f"第 {st['last_bed_day']} 天夜里，皇上翻的是{display_name(lb)}的牌子。"
    plead_targets = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status IN ('confined','cold')""",
                      (c['id'],)) if key == 'yangxin' else []
    return render_template('place.html', c=c, key=key, title=title, desc=desc, extra=extra, acts=acts,
                           counts=counts, sick=is_sick(c), arts=arts_of(c), ARTS=ARTS, ART_MASTERY=ART_MASTERY,
                           plead_targets=plead_targets, plead_p=int(plead_chance(c) * 100),
                           maid_ev=maid_ev, maid_info=maid_info, heir_ev=heir_ev, my_heirs=my_heirs, HEIR_RAISE=HEIR_RAISE,
                           household=palace_household(c['palace']) if key == 'home' and has_residence(c) else [],
                           is_head=has_residence(c) and c['hall'] == 'main' and c['rank'] >= 5)

# ── 场景 ───────────────────────────────────────────────────────────────────────

def start_scene(cid, key, **ctx):
    run("UPDATE consorts SET pending_scene=? WHERE id=?",
        (json.dumps(dict(key=key, day=cur_day(), **ctx), ensure_ascii=False), cid))
    if not settling():
        g.scene_started = True

def get_scene(c):
    try:
        return json.loads(c['pending_scene']) if c['pending_scene'] else None
    except ValueError:
        return None

def plead_candidates(c):
    """侍寝时能替谁求情：禁足或冷宫里的姐妹、好感 30 以上的人"""
    sis = set(sisters_of(c['id']))
    out = []
    for r in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status IN ('confined','cold')", (c['id'],)):
        rel = relation(c['id'], r['id'])
        if r['id'] in sis or (rel and rel['affinity'] >= 30):
            out.append(r)
    return out

def scene_view(c, sc):
    """返回 (标题, 正文, 选项)"""
    if sc['key'] == 'audience':
        prompt = AUDIENCE_PROMPTS[sc['prompt'] % len(AUDIENCE_PROMPTS)]
        if sc.get('bed'):
            title, lead = '侍寝', '红烛将尽，皇上倚着枕头，忽然问你：'
        else:
            title, lead = '召见', '苏培盛引你进了养心殿。皇上放下奏折：'
        opts = list(prompt['opts'])
        if sc.get('hoarse'):
            return title, lead + prompt['ask'], [opts[0]]
        if sc.get('bed') and plead_candidates(c):
            opts.append(PLEAD_IN_BED)
        return title, lead + prompt['ask'], opts
    if sc['key'] == 'exam':
        prompt = EXAM_PROMPTS[sc['prompt'] % len(EXAM_PROMPTS)]
        h = q('SELECT * FROM heirs WHERE id=?', (sc['heir'],), one=True)
        label = heir_label(h) if h else '孩子'
        return f"考校·{prompt['topic']}", '苏培盛来传话，皇上要考校' + label + '的功课。' + prompt['ask'].format(h=label), prompt['opts']
    cfg = SCENES[sc['key']]
    return cfg['place'], cfg['text'], cfg['opts']

def apply_effects(cid, eff):
    parts = []
    for k, v in eff.items():
        if not v: continue
        if k == 'favor':
            v = add_favor(cid, v)
        elif k == 'trust':
            add_trust(cid, v)
        elif k == 'silver':
            add_silver(cid, v)
        elif k in STAT_NAMES:
            add_stat(cid, k, v)
        elif k == 'seek':
            run("UPDATE consorts SET seek_bonus=seek_bonus+? WHERE id=?", (v, cid))
            parts.append('今晚翻牌子的机会大了'); continue
        elif k == 'huafei':
            hf = q("SELECT id FROM consorts WHERE npc_key='huafei'", one=True)
            if hf: add_affinity(cid, hf['id'], v)
            parts.append('华妃记下了这笔账' if v < 0 else '华妃待你和气了些'); continue
        parts.append(f"{EFFECT_NAMES[k]} {v:+d}")
    return '，'.join(parts)

CHECK_NAMES = dict(STAT_NAMES, trust='信任')
HEIR_CHECK_NAMES = dict(study='孩子的学问', riding='孩子的骑射', virtue='孩子的品行')

@app.route('/scene', methods=['GET', 'POST'])
@login_required
def scene():
    c = g.me
    sc = get_scene(c)
    if sc and sc['key'] == 'audience' and affliction(c['id'], 'yachan'):
        sc['hoarse'] = True
    if not sc:
        return redirect(url_for('index'))
    title, text, opts = scene_view(c, sc)
    is_exam = sc['key'] == 'exam'
    heir = q('SELECT * FROM heirs WHERE id=?', (sc['heir'],), one=True) if is_exam else None
    if request.method == 'POST':
        try:
            idx = int(request.form.get('opt', ''))
            if idx < 0: raise IndexError
            opt = opts[idx]
        except (ValueError, IndexError):
            flash('选一个。', 'bad')
            return redirect(url_for('scene'))
        target = None
        if opt.get('plead'):
            try: tid = int(request.form.get('target_id', 0))
            except ValueError: tid = 0
            target = next((p for p in plead_candidates(c) if p['id'] == tid), None)
            if not target:
                flash('选一位要替她求情的人。', 'bad')
                return redirect(url_for('scene'))
        run("UPDATE consorts SET pending_scene='' WHERE id=?", (c['id'],))
        if is_exam and not heir:   # 考校场景等到玩家来应对时，孩子已经不在了（比如被讨回、抱走）
            flash('这事已经过去了。', 'info')
            return redirect(url_for('index'))
        if is_exam:
            ok = heir[opt['stat']] + random.randint(0, SCENE_ROLL) >= opt['dc']
            outcome = opt['win_text'] if ok else opt['lose_text']
            gain = (opt['win'] if ok else opt.get('lose', {})).get('heir_favor', 0)
            if gain:
                run('UPDATE heirs SET favor=favor+? WHERE id=?', (gain, heir['id']))
            summary = f"{heir_label(heir)}圣眷 {gain:+d}" if gain else ''
        else:
            ok = opt['stat'] is None or c[opt['stat']] + random.randint(0, SCENE_ROLL) >= opt['dc']
            outcome = opt['win_text'] if ok else opt['lose_text']
            summary = apply_effects(c['id'], opt['win'] if ok else opt.get('lose', {}))
            if target and ok:
                cut = shorten_punishment(c, target)
                summary = '，'.join(x for x in (summary, f"{full_name(target)}的日子缩短 {cut} 天") if x)
        return render_template('scene.html', c=get_consort(c['id']), title=title, text=text, done=True,
                               chosen=opt['text'], ok=ok, outcome=outcome, summary=summary)
    check_names = HEIR_CHECK_NAMES if is_exam else CHECK_NAMES
    mine_line = (f"{heir_label(heir)}的学问 {heir['study']}、骑射 {heir['riding']}、品行 {heir['virtue']}。"
                "标着「看某项」的选项，这一项加上运气过线就能成。") if is_exam and heir else None
    return render_template('scene.html', c=c, title=title, text=text, opts=opts, done=False, CHECK_NAMES=check_names,
                           mine_line=mine_line, plead_targets=plead_candidates(c) if any(o.get('plead') for o in opts) else [])

# ── 昨夜宫中 ───────────────────────────────────────────────────────────────────

@app.route('/recap')
@login_required
def recap():
    c = g.me
    st = state()
    night = st['day'] - 1
    if night < 1 or c['entered_day'] > night:
        return redirect(url_for('index'))
    mine = q("SELECT * FROM messages WHERE consort_id=? AND day=? AND is_night=1 ORDER BY id", (c['id'], night))
    edict = next((m for m in mine if m['kind'] == 'edict'), None)
    mine = [m for m in mine if m['kind'] != 'edict']
    news = q("SELECT * FROM gazette WHERE day=? AND is_night=1 AND kind NOT IN ('bed') ORDER BY id", (night,))
    tray, chosen = [], None
    if st['last_bed_day'] == night:
        try: ids = json.loads(st['last_bed_pool'] or '[]')
        except ValueError: ids = []
        tray = [x for x in (get_consort(i) for i in ids) if x]
        chosen = get_consort(st['last_bed_id'])
    missed = max(0, night - max(c['recap_seen_day'], c['entered_day'] - 1) - 1)
    sc = get_scene(c)
    return render_template('recap.html', c=c, night=night, mine=mine, edict=edict, news=news, tray=tray,
                           chosen=chosen, missed=missed, scene=sc)

@app.route('/recap/seen', methods=['POST'])
@login_required
def recap_seen():
    run("UPDATE consorts SET recap_seen_day=? WHERE id=?", (cur_day() - 1, g.me['id']))
    return redirect(url_for('index'))

# ── 书信 ───────────────────────────────────────────────────────────────────────

LETTER_DAILY_MAX = 5
LETTER_MAX_LEN = 300
LETTER_ATTACH_SHIELD = 5   # 入宫不满 5 天不能附银子、道具、雅趣作品，防小号一进宫就把家底转给大号
LETTER_PAGE_SIZE = 20      # 收件箱每页 20 封，标星的不参与翻页，永远排最前面

def reachable_letter_ids(c):
    """自己 + 同账号死掉的角色：群发信的附件死了领不了，归新建的秀女领"""
    dead = [r['id'] for r in q('SELECT id FROM consorts WHERE archived_user_id=?', (c['user_id'],))]
    return [c['id'], *dead]

def letter_page(c, side, page, with_id):
    """side='to' 收件箱 / 'from' 已发出。标星的信全部列出、不算进分页；其余按页翻。返回 (starred, rows, total, pages)
    只看自己这个角色收发的信——死掉的旧角色的私信不会跑到新秀女的信箱里，能继承的只有群发补偿信的未领附件"""
    ids = [c['id']]
    deleted_col = 'deleted_by_to' if side == 'to' else 'deleted_by_from'
    starred_ids = {r['letter_id'] for r in q("SELECT letter_id FROM letter_stars WHERE consort_id=?", (c['id'],))}
    where = f"{side}_id IN ({','.join('?' * len(ids))}) AND {deleted_col}=0"
    args = list(ids)
    if with_id:
        other_col = 'from_id' if side == 'to' else 'to_id'
        where += f" AND {other_col}=?"
        args.append(with_id)
    rows = q(f"SELECT * FROM letters WHERE {where} ORDER BY id DESC", args)
    starred = [r for r in rows if r['id'] in starred_ids]
    rest = [r for r in rows if r['id'] not in starred_ids]
    total = len(rest)
    pages = max(1, -(-total // LETTER_PAGE_SIZE))
    page = max(1, min(page, pages))
    return starred, rest[(page - 1) * LETTER_PAGE_SIZE: page * LETTER_PAGE_SIZE], total, pages, page

@app.route('/letters')
@login_required
def letters():
    c = g.me
    try: p = int(request.args.get('p', 1))
    except ValueError: p = 1
    try: sp = int(request.args.get('sp', 1))
    except ValueError: sp = 1
    try: wid = int(request.args.get('with', 0))
    except ValueError: wid = 0
    unclaimed = q(f"""SELECT * FROM letters WHERE is_broadcast=1 AND claimed=0
                      AND to_id IN ({','.join('?' * len(reachable_letter_ids(c)))}) ORDER BY id""", reachable_letter_ids(c))
    inbox_starred, inbox, inbox_total, inbox_pages, p = letter_page(c, 'to', p, wid)
    sent_starred, sent, sent_total, sent_pages, sp = letter_page(c, 'from', sp, wid)
    run("UPDATE letters SET is_read=1 WHERE to_id=? AND is_read=0", (c['id'],))
    others = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status NOT IN ('xiunv','dead')
                  ORDER BY rank DESC, favor DESC""", (c['id'],))
    inv = q("SELECT * FROM inventory WHERE consort_id=? AND qty>0", (c['id'],))
    held = q("SELECT * FROM hobby_items WHERE holder_id=? ORDER BY id DESC", (c['id'],))
    try: to = int(request.args.get('to', 0))
    except ValueError: to = 0
    try: hobby_item = int(request.args.get('hobby_item', 0))
    except ValueError: hobby_item = 0
    starred_ids = {r['letter_id'] for r in q("SELECT letter_id FROM letter_stars WHERE consort_id=?", (c['id'],))}
    return render_template('letters.html', c=c, inbox=inbox, inbox_starred=inbox_starred, sent=sent, sent_starred=sent_starred,
                           inbox_total=inbox_total, inbox_pages=inbox_pages, p=p, sent_total=sent_total, sent_pages=sent_pages, sp=sp,
                           with_id=wid, unclaimed=unclaimed, starred_ids=starred_ids,
                           others=others, inv=inv, held=held, to=to,
                           hobby_item=hobby_item, get_hobby_item=lambda iid: q('SELECT * FROM hobby_items WHERE id=?', (iid,), one=True),
                           get_consort=get_consort, left=LETTER_DAILY_MAX - daily_count(c['id'], 'letter'),
                           can_attach=cur_day() - c['entered_day'] >= LETTER_ATTACH_SHIELD, LETTER_ATTACH_SHIELD=LETTER_ATTACH_SHIELD,
                           LETTER_MAX_LEN=LETTER_MAX_LEN, hobby_item_desc=hobby_item_desc)

@app.route('/letters/claim/<int:lid>', methods=['POST'])
@login_required
def letter_claim(lid):
    c = g.me
    l = q('SELECT * FROM letters WHERE id=?', (lid,), one=True)
    if not l or not l['is_broadcast'] or l['claimed'] or l['to_id'] not in reachable_letter_ids(c):
        flash('这封信没有能领的东西。', 'bad')
        return redirect(url_for('letters'))
    run('UPDATE letters SET claimed=1 WHERE id=?', (lid,))
    parts = []
    if l['silver']:
        add_silver(c['id'], l['silver']); parts.append(f"银子 {l['silver']} 两")
    if l['item_key'] and l['item_key'] in ITEMS:
        inv_add(c['id'], l['item_key'], 1); parts.append(ITEMS[l['item_key']]['name'])
    flash(('领到了：' + '、'.join(parts) + '。') if parts else '已确认收悉。', 'good')
    return redirect(url_for('letters'))

@app.route('/letters/star/<int:lid>', methods=['POST'])
@login_required
def letter_star(lid):
    c = g.me
    l = q('SELECT * FROM letters WHERE id=?', (lid,), one=True)
    if not l or c['id'] not in (l['from_id'], l['to_id']):
        flash('没有这封信。', 'bad')
        return redirect(url_for('letters'))
    if q('SELECT 1 FROM letter_stars WHERE letter_id=? AND consort_id=?', (lid, c['id']), one=True):
        run('DELETE FROM letter_stars WHERE letter_id=? AND consort_id=?', (lid, c['id']))
    else:
        run('INSERT INTO letter_stars (letter_id, consort_id) VALUES (?,?)', (lid, c['id']))
    return redirect(url_for('letters'))

@app.route('/letters/delete/<int:lid>', methods=['POST'])
@login_required
def letter_delete(lid):
    c = g.me
    l = q('SELECT * FROM letters WHERE id=?', (lid,), one=True)
    if not l or c['id'] not in (l['from_id'], l['to_id']):
        flash('没有这封信。', 'bad')
    elif c['id'] == l['to_id'] and l['is_broadcast'] and not l['claimed']:
        flash('附件还没领，先领了再删。', 'bad')
    else:
        col = 'deleted_by_to' if c['id'] == l['to_id'] else 'deleted_by_from'
        run(f'UPDATE letters SET {col}=1 WHERE id=?', (lid,))
        run('DELETE FROM letter_stars WHERE letter_id=? AND consort_id=?', (lid, c['id']))
        flash('信已经从你的信箱里删掉了。', 'info')
    return redirect(url_for('letters'))

@app.route('/letters/send', methods=['POST'])
@login_required
def letter_send():
    c = g.me
    f = request.form
    body = f.get('body', '').strip()
    try:
        tid, amt = int(f.get('to_id', 0)), int(f.get('silver', 0) or 0)
    except ValueError:
        tid, amt = 0, -1
    item = f.get('item', '')
    try: hobby_item_id = int(f.get('hobby_item_id', 0) or 0)
    except ValueError: hobby_item_id = 0
    hitem = q('SELECT * FROM hobby_items WHERE id=?', (hobby_item_id,), one=True) if hobby_item_id else None
    t = get_consort(tid)
    err = None
    if not t or not t['user_id'] or t['id'] == c['id'] or t['status'] in ('xiunv', 'dead'): err = '没有这个人。'
    elif not body or len(body) > LETTER_MAX_LEN: err = f'信要写点什么，最多 {LETTER_MAX_LEN} 字。'
    elif blocked_hit('书信', body): err = BLOCKED_MSG
    elif daily_count(c['id'], 'letter') >= LETTER_DAILY_MAX: err = f'今天已经送出 {LETTER_DAILY_MAX} 封信了。'
    elif amt < 0 or amt > c['silver']: err = '银子数目不对。'
    elif item and (item not in ITEMS or inv_qty(c['id'], item) < 1): err = '你没有这件东西。'
    elif hobby_item_id and (not hitem or hitem['holder_id'] != c['id']): err = '你手里没有这件雅趣作品。'
    elif item and hobby_item_id: err = '一次只能附一样东西。'
    elif (amt or item or hobby_item_id) and cur_day() - c['entered_day'] < LETTER_ATTACH_SHIELD:
        err = f'入宫不满 {LETTER_ATTACH_SHIELD} 天，信里还带不了银子和东西。'
    elif c['status'] == 'cold' and (amt or item or hobby_item_id): err = '冷宫里只能托人带句话，送不出东西。'
    if err:
        flash(err, 'bad')
        return redirect(url_for('letters', to=tid))
    if amt:
        add_silver(c['id'], -amt); add_silver(tid, amt)
    if item:
        inv_add(c['id'], item, -1)
        if item != 'ruyi':           # 玉如意送出即用掉，不进对方背包，没法来回倒腾
            inv_add(tid, item, 1)
    if hitem:
        history = json.loads(hitem['history'] or '[]') + [{'from': c['id'], 'to': tid, 'day': cur_day()}]
        run('UPDATE hobby_items SET holder_id=?, history=? WHERE id=?', (tid, json.dumps(history, ensure_ascii=False), hitem['id']))
        run('DELETE FROM displays WHERE consort_id=? AND item_id=?', (c['id'], hitem['id']))   # 送出去了，自己寝宫不再摆着
    run("""INSERT INTO letters (from_id, to_id, day, body, silver, item_key, hobby_item_id, created_ts)
           VALUES (?,?,?,?,?,?,?,?)""", (c['id'], tid, cur_day(), body, amt, item, hobby_item_id, now_ts()))
    daily_inc(c['id'], 'letter')
    guide_mark(c['id'], 'letter')
    # 好感：每天每个方向第一封信 +2，附玉如意再 +15，附自己做的雅趣作品再 +10；银子和普通物件不额外加，免得两人来回倒腾刷好感
    aff = 0
    if daily_count(c['id'], f'letter_aff:{tid}') == 0:
        aff += 2
        daily_inc(c['id'], f'letter_aff:{tid}')
    if item == 'ruyi':
        aff += 15
    elif hitem:
        aff += HOBBY_GIFT_AFFINITY
    if aff: add_affinity(c['id'], tid, aff)
    extras = '、'.join(x for x in ((f'{amt} 两银子' if amt else ''), (ITEMS[item]['name'] if item else ''),
                                   (hobby_item_desc(hitem) if hitem else '')) if x)
    notify(tid, f"{display_name(c)}差人送来一封信" + (f"，还附了{extras}" if extras else '') + '。去「书信」看看。', 'good')
    flash(f"信送到{t['palace'] if t['status'] != 'cold' else '冷宫'}了。" + (f"好感 +{aff}。" if aff else ''), 'good')
    return redirect(url_for('letters'))



# ── 投诉举报 ───────────────────────────────────────────────────────────────────

REPORT_CATEGORIES = ('违法违规内容', '辱骂骚扰', '侵犯他人权益', '其他')
REPORT_DAILY_MAX = 10
REPORT_MAX_LEN = 200

@app.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    c = g.me
    src = request.values.get('letter', type=int) or 0
    letter = q("SELECT * FROM letters WHERE id=? AND to_id=?", (src, c['id']), one=True) if src else None
    if src and not letter:
        flash('只能举报发给你的信。', 'bad')
        return redirect(url_for('letters'))
    if request.method == 'POST':
        category = request.form.get('category', '')
        reason = request.form.get('reason', '').strip()
        err = None
        if category not in REPORT_CATEGORIES: err = '请选择举报类型。'
        elif not reason or len(reason) > REPORT_MAX_LEN: err = f'请写明举报理由，最多 {REPORT_MAX_LEN} 字。'
        elif daily_count(c['id'], 'report') >= REPORT_DAILY_MAX: err = '今天举报的次数已经用完，请明天再来。'
        elif letter and q("SELECT 1 FROM reports WHERE reporter_id=? AND letter_id=?", (c['id'], letter['id']), one=True):
            err = '这封信已经举报过了，管理员会尽快处理。'
        if err:
            flash(err, 'bad')
            return render_template('report.html', letter=letter, categories=REPORT_CATEGORIES,
                                   get_consort=get_consort, REPORT_MAX_LEN=REPORT_MAX_LEN)
        run("""INSERT INTO reports (reporter_id, target_id, letter_id, category, reason, snapshot, created_ts)
               VALUES (?,?,?,?,?,?,?)""",
            (c['id'], letter['from_id'] if letter else 0, letter['id'] if letter else 0, category, reason,
             letter['body'] if letter else '', now_ts()))
        daily_inc(c['id'], 'report')
        flash('举报已提交，管理员会尽快核实处理。', 'good')
        return redirect(url_for('letters' if letter else 'index'))
    return render_template('report.html', letter=letter, categories=REPORT_CATEGORIES,
                           get_consort=get_consort, REPORT_MAX_LEN=REPORT_MAX_LEN)


# ── 下药：暗柜、药效与案发 ──────────────────────────────────────────────────

def cabinet_stock(cid, day):
    # 独立随机源，刷新页面和重启都不会换货，也不影响结算掷骰。
    return random.Random(f'cabinet:{cid}:{day}').sample(list(DRUGS), CABINET_SLOTS)


def drug_agents(cid, tid=None):
    return q("""SELECT m.*, b.counter FROM bribes b JOIN maids m ON m.id=b.maid_id
                JOIN consorts c ON c.id=m.owner_id
                WHERE b.briber_id=? AND b.turned=1 AND m.status='active'
                AND m.sick_until_day<? AND c.status NOT IN ('dead','cold','xiunv')
                AND (? IS NULL OR m.owner_id=?)""", (cid, cur_day(), tid, tid))


def drug_block(c, t, drug, used, mid, day, submitting=True):
    if drug not in DRUGS or used not in DRUGS or drug == 'wuming': return '请选择手里的药。'
    if used != drug and used != 'wuming': return '药材与药性不符。'
    if used == 'wuming' and drug == 'lihun': return '无名不能配离魂草。'
    if t['npc_key'] or t['status'] in ('dead', 'cold', 'xiunv'): return '她现在不能当目标。'
    if day - t['entered_day'] < DRUG_NEWCOMER_SHIELD: return '她入宫还不满 5 天，动不得。'
    if t['drugged_day'] and day - t['drugged_day'] <= DRUGGED_SHIELD: return '她刚遭过下药，这两天动不得。'
    if drug == 'lihun' and (t['poisoned_day'] or t['protected_until_day'] >= day): return '她正中毒或刚获救，动不得。'
    if drug == 'chunxin' and t['pregnant_since']: return '她已有喜脉，春信丹用不上。'
    if mid and not any(m['id'] == mid for m in drug_agents(c['id'], t['id'])): return '这名宫人现在不能替你办事。'
    if submitting:
        if c['rank'] < DRUGS[used]['rank']: return '你的位分还使不得这种药。'
        if inv_qty(c['id'], used) < 1: return '手里没有这份药。'
        account = q('SELECT * FROM users WHERE id=?', (c['user_id'],), one=True)
        if drug == 'lihun' and account['lethal_ready_day'] > day: return '离魂草的七天冷却还没过，撤回也不重置。'
        if used == 'wuming' and account['nameless_ready_day'] > day: return '无名的十五天冷却还没过，撤回也不重置。'
    return None


@app.route('/shop/drug/<key>', methods=['POST'])
@login_required
def buy_drug(key):
    c, day = g.me, cur_day()
    cfg = DRUGS.get(key)
    if not cfg or key not in cabinet_stock(c['id'], day): msg = '今日暗柜没有这份药。'
    elif c['status'] == 'cold' or c['rank'] < cfg['rank']: msg = '内务府不肯把这份药交给你。'
    elif daily_count(c['id'], 'cabinet:' + key): msg = '今日这一份已经买过了。'
    elif c['silver'] < cfg['price']: msg = '银子不够。'
    else:
        add_silver(c['id'], -cfg['price'])
        inv_add(c['id'], key)
        daily_inc(c['id'], 'cabinet:' + key)
        if random.random() < LEDGER_CHANCE:
            run('UPDATE consorts SET drug_ledger=1 WHERE id=?', (c['id'],))
        flash(f"你收好了{cfg['name']}。", 'good')
        return redirect(url_for('shop'))
    flash(msg, 'bad')
    return redirect(url_for('shop'))


def affliction(cid, drug, day=None):
    return q("""SELECT * FROM afflictions WHERE consort_id=? AND drug=? AND status='active'
                AND (until_day=0 OR until_day>=?) ORDER BY id LIMIT 1""", (cid, drug, cur_day() if day is None else day), one=True)


def poison_player(cid, day):
    run('UPDATE consorts SET poisoned_day=?, poison_treatment=0, health=MAX(1,health-20) WHERE id=?', (day, cid))
    notify(cid, f'你中毒了，体质 -20。下一次结算前请太医（{TREAT_COST} 两）：请了九成能活，不请只有三成五。', 'bad')
    gazette(f'{display_name(get_consort(cid))}突然中毒，性命垂危。')
    night_mark(cid, 'poisoned')
    guide_tip(cid, 'poisoned', '「快请太医！这钱不能省，命才是自己的。」')


def open_drug_case(it, punished=0):
    if it['item_used'] == 'wuming': return None
    old = q('SELECT id FROM cases WHERE intrigue_id=?', (it['id'],), one=True)
    if old: return old['id']
    day = cur_day() + (1 if settling() else 0)
    case_id = run('''INSERT INTO cases(day,victim_id,culprit_id,intrigue_id,drug,agent_maid_id,victim_punished,created_ts)
                     VALUES(?,?,?,?,?,?,?,?)''', (day, it['target_id'], it['attacker_id'], it['id'], it['drug'], it['agent_maid_id'], punished, now_ts())).lastrowid
    culprit = get_consort(it['attacker_id'])
    m = get_maid(it['agent_maid_id']) if it['agent_maid_id'] else None
    score = 30 + random.randint(0, 20) + (0 if m else 20)
    if m: score += {'zuijin': -10, 'suizui': 10}.get(m['trait'], 0)
    run('INSERT INTO case_suspects(case_id,consort_id,suspicion) VALUES(?,?,?)', (case_id, culprit['id'], score))
    victim = get_consort(it['target_id'])
    candidates = q("SELECT * FROM consorts WHERE id NOT IN (?,?) AND status NOT IN ('dead','xiunv','cold') AND ?-entered_day>=5",
                   (culprit['id'], victim['id'], day))
    def affinity(c):
        r = relation(c['id'], victim['id'])
        return r['affinity'] if r else 0
    candidates = sorted(candidates, key=lambda c: (affinity(c), abs(c['favor'] - victim['favor'])))
    for c in candidates:
        active = q("SELECT COUNT(*) FROM case_suspects s JOIN cases c ON c.id=s.case_id WHERE s.consort_id=? AND c.status='open'", (c['id'],), one=True)[0]
        recent = q('SELECT COUNT(*) FROM case_suspects s JOIN cases c ON c.id=s.case_id WHERE s.consort_id=? AND c.culprit_id!=? AND c.day>?', (c['id'], c['id'], day-7), one=True)[0]
        if active >= 2 or recent >= 2: continue
        run('INSERT INTO case_suspects(case_id,consort_id,suspicion) VALUES(?,?,?)', (case_id, c['id'], min(40, 10+random.randint(0,20)+(10 if affinity(c)<0 else 0))))
        if q('SELECT COUNT(*) FROM case_suspects WHERE case_id=?', (case_id,), one=True)[0] >= 4: break
    suspects = q('SELECT consort_id FROM case_suspects WHERE case_id=?', (case_id,))
    names = '、'.join(display_name(get_consort(s['consort_id'])) for s in suspects)
    gazette(f'{display_name(victim)}出了事，皇后命慎刑司彻查。待查：{names}。', day=day)
    for cid in {victim['id'], *(s['consort_id'] for s in suspects)}:
        notify(cid, f'你被卷进了第 {case_id} 桩案子，请去慎刑司陈情，下一次结算定案。', 'bad')
        guide_tip(cid, 'case', '「案子上了身，别慌。该喊冤喊冤，该打点打点，慎刑司认的是嫌疑，不是脾气。」')
    if eyes_active(victim): notify(victim['id'], f'眼线回报：这回下手的是{display_name(culprit)}。')
    return case_id


def resolve_drug(it):
    it = q('SELECT * FROM intrigues WHERE id=?', (it['id'],), one=True)
    if it['status'] != 'pending': return it['result'], None
    c, t, day = get_consort(it['attacker_id']), get_consort(it['target_id']), cur_day()
    def done(result):
        run("UPDATE intrigues SET status='done', result=? WHERE id=?", (result, it['id']))
        if c['user_id']: notify(c['id'], f"对{display_name(t)}的下药：" + {'void':'局面已变，落空了。','fizzle':'没能得手。','caught':'没能得手，事情被察觉了。','success':'药已下进去。'}[result])
        return result, None
    if c['status'] != 'normal' or is_sick(c) or drug_block(c,t,it['drug'],it['item_used'],it['agent_maid_id'],day,False): return done('void')
    agents = drug_agents(c['id'], t['id'])
    m = next((m for m in agents if m['id'] == it['agent_maid_id']), None)
    p = DRUG_BASE + (c['scheme']-t['scheme'])*0.008
    p += min(2,len(agents))*0.10 + (0.08 if m and m['trait']=='shouqiao' else 0)
    p -= (0 if m or same_palace(c, t) else SELF_HAND_PENALTY) + (0.12 if eyes_active(t) else 0)
    p -= min(0.15,0.05*active_sister_count(t['id'])) + (0.05 if t['personality']=='dignified' else 0)
    p -= (0.05 if t['virtue']>=70 else 0) + t['trust']*0.0015
    needle = inv_qty(t['id'], 'yinzhen') > 0
    before = max(0.08,min(0.85,p))
    after = max(0.08,min(0.85,p-(NEEDLE_BLOCK if needle else 0)))
    roll = random.random()
    if (m and m['counter']) or roll >= after:
        if needle and after <= roll < before and not (m and m['counter']):
            inv_add(t['id'],'yinzhen',-1)
            notify(t['id'],'银针挡下了异样，折了一根。')
        caught = not m or bool(m['counter']) or random.random()<0.5
        if caught: open_drug_case(it)
        return done('caught' if caught else 'fizzle')
    if DRUGS[it['drug']]['eat']:
        tasters = [m for m in active_maids(t['id']) if m['loyalty']>=TASTER_LOYALTY and m['sick_until_day']<day]
        if tasters and random.random()<TASTER_CHANCE:
            m = tasters[0]
            if it['drug'] in ('lihun','qingsi'):
                maid_leave(m['id'],'dead','替主子试毒身亡')
                gazette(f"{display_name(t)}的宫人{m['name']}试毒身亡，忠心可鉴。")
            else: run('UPDATE maids SET sick_until_day=? WHERE id=?', (day+3,m['id']))
            notify(t['id'],f"{m['name']}尝出了异样，替你挡下一劫。",'bad')
            open_drug_case(it)
            return done('fizzle')
    drug = it['drug']
    run('UPDATE consorts SET drugged_day=? WHERE id=?', (day,t['id']))
    days = DRUGS[drug]['days']
    run('INSERT INTO afflictions(consort_id,drug,attacker_id,intrigue_id,start_day,until_day) VALUES(?,?,?,?,?,?)',
        (t['id'],drug,c['id'],it['id'],day,day+days-1 if days else 0))
    if drug=='yanzhi': add_stat(t['id'],'appearance',-10)
    elif drug=='yachan': add_stat(t['id'],'talent',-8)
    elif drug=='hanshui':
        add_stat(t['id'],'health',-25)
        if t['pregnant_since']:
            if inv_qty(t['id'],'antai'):
                inv_add(t['id'],'antai',-1)
                notify(t['id'],'安胎药保住了胎儿。')
            else:
                run('UPDATE consorts SET pregnant_since=0, postpartum_until=? WHERE id=?',(day+POSTPARTUM_SICK_DAYS,t['id']))
                run("UPDATE afflictions SET status='done' WHERE consort_id=? AND drug='chunxin'",(t['id'],))
                night_mark(t['id'],'miscarriage')
                notify(t['id'],'你小产了。','bad')
    elif drug=='lihun': poison_player(t['id'],day)
    elif drug=='chunxin':
        run('UPDATE consorts SET pregnant_since=? WHERE id=?',(day,t['id']))
        notify(t['id'],'太医诊出了喜脉。','good')
        gazette(f'{display_name(t)}有喜了。','birth')
    if DRUGS[drug]['case']=='now':
        notify(t['id'],f"太医查出你遭了{DRUGS[drug]['name']}。{DRUGS[drug]['desc']}",'bad')
        open_drug_case(it)
    return done('success')


def diagnose_slow(a):
    run("UPDATE afflictions SET status='done' WHERE id=?",(a['id'],))
    notify(a['consort_id'],'太医查出了青丝引，药性已解，体质不再逐夜下降。','good')
    open_drug_case(q('SELECT * FROM intrigues WHERE id=?',(a['intrigue_id'],),one=True))


@app.route('/diagnose', methods=['POST'])
@login_required
def diagnose():
    c = g.me
    if c['silver']<20: flash('请太医诊脉要 20 两。','bad')
    elif daily_count(c['id'],'diagnose'): flash('今日已经诊过脉了。','bad')
    else:
        add_silver(c['id'],-20)
        daily_inc(c['id'],'diagnose')
        a = affliction(c['id'],'qingsi')
        if a and random.random()<DIAGNOSE_CHANCE:
            diagnose_slow(a)
            flash('太医查出了青丝引，已解去药性。','good')
        else: flash('这次没诊出异样；若仍不舒服，明日再请太医。','info')
    return redirect(url_for('index'))


def tick_drugs(day):
    run("UPDATE afflictions SET status='done' WHERE until_day>0 AND until_day<?",(day,))
    for a in q("SELECT * FROM afflictions WHERE status='active'"):
        c = get_consort(a['consort_id'])
        if c['status']=='dead':
            run("UPDATE afflictions SET status='done' WHERE id=?",(a['id'],)); continue
        if a['drug']=='qingsi':
            run('UPDATE consorts SET health=MAX(1,health-?) WHERE id=?',(SLOW_POISON_TICK,c['id']))
            health = get_consort(c['id'])['health']
            notify(c['id'],'近来总觉得乏力。','bad')
            if health<=1 and not c['poisoned_day']: poison_player(c['id'],day)
            if health<25: diagnose_slow(a)
        elif a['drug']=='chunxin' and day-a['start_day']>=PREGNANCY_DAYS:
            punished = c['trust']<50
            run('UPDATE consorts SET pregnant_since=0 WHERE id=?',(c['id'],))
            run("UPDATE afflictions SET status='done' WHERE id=?",(a['id'],))
            if punished: confine(c['id'],3); add_trust(c['id'],-15)
            notify(c['id'],'喜脉竟是春信丹所致。'+('皇上疑你欺君，禁足三天、信任 -15。' if punished else '皇上相信你是被人所害。'),'bad')
            open_drug_case(q('SELECT * FROM intrigues WHERE id=?',(a['intrigue_id'],),one=True),int(punished))


def drug_gifts(day):
    for m in q("SELECT m.* FROM maids m JOIN consorts c ON c.id=m.owner_id WHERE m.status='active' AND m.trait='shouqiao' AND m.loyalty>=80 AND m.sick_until_day<? AND c.status NOT IN ('dead','cold','xiunv')",(day,)):
        if random.random()<GIFT_DRUG_CHANCE:
            key=random.choice([k for k in DRUGS if k not in ('lihun','wuming')])
            inv_add(m['owner_id'],key)
            notify(m['owner_id'],f"{m['name']}悄悄献上了一份{DRUGS[key]['name']}。")


# 案件保留真凶与冤案记录；模板仅收到公开信息。
@app.route('/cases')
@login_required
def drug_cases():
    cases = []
    for case in q('SELECT * FROM cases ORDER BY id DESC LIMIT 30'):
        suspects = q('SELECT s.*, c.surname, c.given, c.title, c.rank, c.status FROM case_suspects s JOIN consorts c ON c.id=s.consort_id WHERE s.case_id=?', (case['id'],))
        involved = g.me['id'] == case['victim_id'] or any(s['consort_id']==g.me['id'] for s in suspects)
        public = {k:case[k] for k in ('id','day','victim_id','status','closed_day')}
        public['suspects'] = [dict(id=s['consort_id'], name=display_name(s), suspicion=s['suspicion'] if involved else None) for s in suspects]
        public['victim'] = display_name(get_consort(case['victim_id']))
        cases.append(public)
    return render_template('cases.html', cases=cases)


@app.route('/cases/<int:case_id>/act', methods=['POST'])
@login_required
def case_action(case_id):
    c, day = g.me, cur_day()
    case = q('SELECT * FROM cases WHERE id=?',(case_id,),one=True)
    action = request.form.get('action','')
    try: tid = int(request.form.get('target_id',0))
    except ValueError: tid = 0
    if action in ('plead','pay'): tid=c['id']
    suspect = q('SELECT * FROM case_suspects WHERE case_id=? AND consort_id=?',(case_id,tid),one=True)
    count = q('SELECT COUNT(*) FROM case_actions WHERE case_id=? AND consort_id=? AND day=?',(case_id,c['id'],day),one=True)[0]
    err = None
    if not case or case['status']!='open' or case['day']>day: err='这桩案子现在不能陈情。'
    elif action not in ('plead','pay','witness','accuse','search','frame'): err='请选择行动。'
    elif not suspect: err='她不在待查名单中。'
    elif count>=2 or q('SELECT 1 FROM case_actions WHERE case_id=? AND consort_id=? AND day=? AND action=?',(case_id,c['id'],day,action),one=True): err='每案每天最多两项，每项一次。'
    if not err:
        rel=relation(c['id'],tid)
        delta=0
        if action=='plead': delta=-int(c['trust']*0.2)
        elif action=='pay':
            try: amount=int(request.form.get('silver',0))
            except ValueError: amount=0
            if amount<10 or amount>200 or amount>c['silver']: err='打点需 10～200 两，不能超过手里的银子。'
            else: add_silver(c['id'],-amount); delta=-(amount//10)
        elif action=='witness':
            if not rel or rel['affinity']<30: err='好感至少三十才能替她作证。'
            else: delta=-10
        elif action=='accuse': delta=10
        elif action=='search':
            if c['id']!=case['victim_id'] and c['id'] not in sisters_of(case['victim_id']): err='只有受害人和她的姐妹能请求搜宫。'
            else:
                target=get_consort(tid)
                hidden=target['drug_ledger'] or any(inv_qty(tid,k)>0 for k in DRUGS)
                delta=(20 if hidden else 0)+(10 if tid==case['culprit_id'] else 0)
                if not delta: add_affinity(c['id'],tid,-10)
        elif action=='frame':
            agents=drug_agents(c['id'],tid)
            if not agents: err='你在她宫里没有内应。'
            else:
                agent=agents[0]
                delta=25
                if agent['counter']:
                    tid=c['id']
                    run('INSERT OR IGNORE INTO case_suspects(case_id,consort_id,suspicion) VALUES(?,?,0)',(case_id,tid))
        if not err:
            run('UPDATE case_suspects SET suspicion=MAX(0,MIN(100,suspicion+?)) WHERE case_id=? AND consort_id=?',(delta,case_id,tid))
            if action=='plead': run('UPDATE case_suspects SET pleaded=1 WHERE case_id=? AND consort_id=?',(case_id,tid))
            run('INSERT INTO case_actions(case_id,consort_id,day,action,target_id) VALUES(?,?,?,?,?)',(case_id,c['id'],day,action,tid))
            flash('慎刑司记下了你的陈情。','info')
    if err: flash(err,'bad')
    return redirect(url_for('drug_cases'))


def resolve_drug_cases(day):
    for case in q("SELECT * FROM cases WHERE status='open' AND day<=?",(day,)):
        for s in q('SELECT * FROM case_suspects WHERE case_id=?',(case['id'],)):
            c=get_consort(s['consort_id'])
            reduction=(0 if s['pleaded'] else int(c['trust']*0.2))+(20 if c['npc_key']=='huanghou' else 0)
            run('UPDATE case_suspects SET suspicion=MAX(0,suspicion-?), pleaded=1 WHERE case_id=? AND consort_id=?',(reduction,case['id'],c['id']))
        s=q('SELECT * FROM case_suspects WHERE case_id=? ORDER BY suspicion DESC, consort_id LIMIT 1',(case['id'],),one=True)
        convicted=s['consort_id'] if s and s['suspicion']>=50 else 0
        if convicted:
            c=get_consort(convicted)
            if c['status']!='dead':
                if case['drug']=='lihun': send_to_cold(convicted)
                elif case['drug']=='hanshui':
                    if c['rank']>1: set_rank(convicted,c['rank']-1)
                    confine(convicted,3)
                else: confine(convicted,2); cut_favor(convicted,0.15)
                add_trust(convicted,-15)
            gazette(f"慎刑司定案：{display_name(c)}获罪。")
            notify(convicted,'慎刑司将你定罪，信任 -15，并按案情受罚。','bad')
            if convicted==case['culprit_id']:
                m=get_maid(case['agent_maid_id'])
                if m and m['status']=='active': maid_leave(m['id'],'dead','下药案连坐')
                if case['victim_punished']:
                    victim=get_consort(case['victim_id'])
                    if victim['status']=='confined': run("UPDATE consorts SET status='normal',status_until_day=0 WHERE id=?",(victim['id'],))
                    add_trust(victim['id'],15)
                    notify(victim['id'],'春信丹案查明，退还信任，解除禁足。','good')
        else: gazette(f"慎刑司：第 {case['id']} 桩案子证据不足，暂作悬案。")
        for a in q("SELECT * FROM case_actions WHERE case_id=? AND action='accuse'",(case['id'],)):
            if a['target_id']!=convicted: add_stat(a['consort_id'],'virtue',-3)
        run('UPDATE cases SET status=?,closed_day=?,convicted_id=?,wrongful=? WHERE id=?',('convicted' if convicted else 'unsolved',day,convicted,int(bool(convicted and convicted!=case['culprit_id'])),case['id']))


@app.route('/agents')
@login_required
def agents_page():
    c=g.me
    targets=q("SELECT m.*, c.surname,c.given,c.title,c.rank, c.status AS owner_status FROM maids m JOIN consorts c ON c.id=m.owner_id WHERE m.status='active' AND c.user_id IS NOT NULL AND c.id!=? AND c.status NOT IN ('dead','cold','xiunv') AND ?-c.entered_day>=5",(c['id'],cur_day()))
    bribes={b['maid_id']:b for b in q('SELECT * FROM bribes WHERE briber_id=?',(c['id'],))}
    found=q('SELECT m.name,b.maid_id,b.briber_id FROM bribes b JOIN maids m ON m.id=b.maid_id WHERE m.owner_id=? AND m.status=\'active\' AND b.exposed=1 AND b.counter=0',(c['id'],))
    return render_template('agents.html',targets=[dict(m, status=m['owner_status']) for m in targets],bribes=bribes,found=found,c=c)


@app.route('/agents/act', methods=['POST'])
@login_required
def agent_action():
    c=g.me; day=cur_day(); action=request.form.get('action')
    try: mid=int(request.form.get('maid_id',0))
    except ValueError: mid=0
    m=get_maid(mid)
    err=None
    # 差使是派宫人去办的事：本人卧病不耽误宫人跑腿；禁足只出不了宫门，清查自己宫里不受影响，
    # 但收买要伸手到别人宫里，禁足时办不到（见设计文档九点十节）
    if c['status'] not in ('normal','confined'): err='现在顾不上这件事。'
    elif action=='bribe' and c['status']!='normal': err='禁足在身，宫人出不了门，伸不到别人宫里去。'
    elif action=='bribe':
        owner=get_consort(m['owner_id']) if m else None
        if not m or m['status']!='active' or m['owner_id']==c['id'] or not owner['user_id'] or owner['status'] in ('dead','cold','xiunv') or day-owner['entered_day']<5: err='不能收买这名宫人。'
        elif c['silver']<30: err='要三十两银子。'
        elif daily_count(c['id'],f'bribe:{mid}'): err='今天已打点过她。'
        elif q("SELECT COUNT(*) FROM bribes b JOIN maids m ON m.id=b.maid_id WHERE b.briber_id=? AND b.turned=1 AND m.status='active'", (c['id'],), one=True)[0]>=3: err='你已有三个内应。'
        elif not free_errand_maids(c): err='没有空闲宫人去办差。'
        else:
            take_errand(c); add_silver(c['id'],-30); daily_inc(c['id'],f'bribe:{mid}')
            gain=int((15+c['scheme']*0.15)*{'suizui':1.5,'tancai':1.5,'zhonghou':0.5}.get(m['trait'],1))
            run('INSERT INTO bribes(briber_id,maid_id,progress,last_day) VALUES(?,?,?,?) ON CONFLICT(briber_id,maid_id) DO UPDATE SET progress=progress+excluded.progress,last_day=excluded.last_day',(c['id'],mid,gain,day))
            run('UPDATE bribes SET turned=(progress>=?) WHERE briber_id=? AND maid_id=?',(m['loyalty'],c['id'],mid))
            if has_maid_trait(owner['id'],'jiling') and random.random()<0.4:
                notify(owner['id'],'有人在打点咱们宫里的人。'+(f"眼线说是{display_name(c)}。" if eyes_active(owner) else ''))
    elif action=='inspect':
        if not free_errand_maids(c): err='没有空闲宫人去清查。'
        else:
            take_errand(c)
            guide_mark(c['id'],'inspect')
            for b in q("SELECT b.* FROM bribes b JOIN maids m ON m.id=b.maid_id WHERE m.owner_id=? AND m.status='active'",(c['id'],)):
                if random.random()<min(0.85,0.4+c['scheme']*0.004):
                    run('UPDATE bribes SET exposed=1 WHERE briber_id=? AND maid_id=?',(b['briber_id'],b['maid_id']))
    elif action in ('dismiss','counter'):
        if not m or m['owner_id']!=c['id'] or not q('SELECT 1 FROM bribes WHERE maid_id=? AND exposed=1',(mid,),one=True): err='没有查实这件事。'
        elif action=='dismiss': maid_leave(mid,'gone','收买败露，遣出宫去')
        else: run('UPDATE bribes SET counter=1 WHERE maid_id=? AND exposed=1',(mid,))
    else: err='请选择行动。'
    flash(err or '事情已办妥。','bad' if err else 'info')
    return redirect(url_for('agents_page'))


# ── 住处 ────────────────────────────────────────────────────────────────────

def residence_name(c):
    if c['status'] == 'cold': return '冷宫'
    if c['status'] == 'dead': return '已故'
    if c['palace'] in PALACES and c['hall'] in HALL_NAMES:
        return f"{c['palace']}·{HALL_NAMES[c['hall']]}"
    return '候旨安置'


def has_residence(c):
    return bool(c and c['status'] in ('normal', 'confined') and
                c['palace'] in PALACES and c['hall'] in HALL_NAMES)


def same_palace(a, b):
    return has_residence(a) and has_residence(b) and a['palace'] == b['palace']


def palace_household(palace):
    people = {c['hall']: c for c in q("""SELECT * FROM consorts WHERE palace=?
              AND hall!='' AND status IN ('normal','confined') ORDER BY id""", (palace,))}
    return [dict(key=hall, name=name, occupant=people.get(hall)) for hall, name in HALL_NAMES.items()]


def empty_residence(halls, preferred=''):
    occupied = {(c['palace'], c['hall']) for c in q(
        "SELECT palace,hall FROM consorts WHERE hall!='' AND status IN ('normal','confined')")}
    if preferred in PALACES:
        for tier in halls:
            available = [(preferred, h) for h in tier if (preferred, h) not in occupied]
            if available: return random.choice(available)
    for tier in halls:
        available = [(p, h) for p in PALACES for h in tier if (p, h) not in occupied]
        if available: return random.choice(available)
    return None


def move_residence(c, room, announce=True):
    palace, hall = room
    run("UPDATE consorts SET palace=?,hall=?,housing_waiting='' WHERE id=?", (palace, hall, c['id']))
    if not announce: return
    if hall == 'main':
        text = f"奉旨迁居{palace}正殿，为一宫主位。"
        gazette(f"{display_name(c)}{text}", 'decree')
    else:
        text = f"内务府已收拾妥当，迁居{palace}{HALL_NAMES[hall]}。"
    if c['user_id']: notify(c['id'], text, 'decree')


@atomic
def housing_sync(fill_main=True):
    """修复旧档及重复房间；每间一人，重复运行不搬家、不重复报信。

    夜间位分变动只腾房、安置配殿，等晋封全部结束再按位分、圣宠补正殿。
    满房时留待安置，不挤占别人房间，也不打断整晚结算。
    """
    run("UPDATE consorts SET hall='',housing_waiting='' WHERE status NOT IN ('normal','confined') AND (hall!='' OR housing_waiting!='')")
    residents = q("""SELECT * FROM consorts WHERE status IN ('normal','confined')
                     ORDER BY user_id IS NOT NULL, rank DESC, favor DESC, id""")
    occupied = set()
    for c in residents:
        room = (c['palace'], c['hall'])
        valid = has_residence(c) and (c['hall'] != 'main' or c['rank'] >= 5)
        if valid and room not in occupied:
            occupied.add(room)
        elif c['hall']:
            run("UPDATE consorts SET hall='' WHERE id=?", (c['id'],))

    if fill_main:
        waiting = q("""SELECT * FROM consorts WHERE status IN ('normal','confined')
                       AND rank>=5 AND hall!='main' ORDER BY rank DESC,favor DESC,id""")
        for c in waiting:
            room = empty_residence((('main',),))
            if room: move_residence(c, room)

    for c in q("SELECT * FROM consorts WHERE status IN ('normal','confined') AND hall='' ORDER BY rank DESC,favor DESC,id"):
        # 老档、降位留在原宫优先；入宫单独随机分配，不传 preferred。
        room = empty_residence((('east', 'west'), ('back',)), preferred=c['palace'])
        if room: move_residence(c, room)

    for c in q("SELECT * FROM consorts WHERE status IN ('normal','confined')"):
        waiting = 'main' if c['rank'] >= 5 and c['hall'] != 'main' else ('side' if not c['hall'] else '')
        if waiting == 'main' and not fill_main: continue
        if waiting == c['housing_waiting']: continue
        run('UPDATE consorts SET housing_waiting=? WHERE id=?', (waiting, c['id']))
        if waiting and c['user_id']:
            text = '各处正殿尚有人居住，先安居眼下住处，待有空缺再奉旨迁宫。' if waiting == 'main' and c['hall'] else '各处屋舍暂满，内务府已记下，待腾出住处便来传话。'
            notify(c['id'], text)


def housing_visit(bed):
    if not has_residence(bed) or bed['hall'] != 'main' or bed['rank'] < 5: return
    for c in q("""SELECT * FROM consorts WHERE palace=? AND hall IN ('east','west','back')
                  AND user_id IS NOT NULL AND status='normal' AND pregnant_since=0 AND id!=?""", (bed['palace'], bed['id'])):
        if not is_sick(c) and random.random() < 0.10:
            add_favor(c['id'], 10, gain_mult=False)
            notify(c['id'], f"皇上驾临{bed['palace']}，经过廊下时瞧见了你，停步说了两句话。圣宠 +10。", 'good')


def housing_reports(day):
    for head in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND rank>=5 AND hall='main' AND status IN ('normal','confined')"):
        if not has_residence(head): continue
        others = q("""SELECT * FROM consorts WHERE palace=? AND id!=? AND user_id IS NOT NULL
                      AND hall IN ('east','west','back') AND status IN ('normal','confined') ORDER BY id""", (head['palace'], head['id']))
        if others:
            text = '；'.join(f"{display_name(c)}今日{daily_activity(c['id'], day)}" for c in others)
            notify(head['id'], f'宫人来回话：{text}。')


def discipline_error(head, target, action, day):
    if not has_residence(head) or head['hall'] != 'main' or head['rank'] < 5:
        return '你还不是这一宫的主位。'
    if action not in ('kneel', 'reward'): return '要罚要赏，须有个准话。'
    if head['discipline_ready_day'] > day: return f"第 {head['discipline_ready_day']} 天才能再传话。"
    if not target or not target['user_id'] or target['id'] == head['id'] or not same_palace(head, target) or target['hall'] not in ('east', 'west', 'back'):
        return '这位不在你宫中听差。'
    if action == 'kneel' and target['pregnant_since']: return '她有孕在身，不能罚跪。'
    return None


def apply_discipline(head, target, action, day):
    if action == 'kneel':
        add_stat(target['id'], 'health', -8)
        add_affinity(head['id'], target['id'], -5)
        text = f"{display_name(head)}传话，罚你在廊下跪了一阵。体质 -8，好感 -5。"
    else:
        add_affinity(head['id'], target['id'], 5)
        text = f"{display_name(head)}遣人来赏你，叮嘱宫人好生照应。好感 +5。"
    run('UPDATE consorts SET discipline_ready_day=? WHERE id=?', (day + DISCIPLINE_COOLDOWN, head['id']))
    if target['user_id']: notify(target['id'], text, 'bad' if action == 'kneel' else 'good')


@app.route('/housing/discipline/<int:tid>', methods=['POST'])
@login_required
def housing_discipline(tid):
    head, target = g.me, get_consort(tid)
    action = request.form.get('action', '')
    err = discipline_error(head, target, action, cur_day())
    if err: flash(err, 'bad')
    else:
        apply_discipline(head, target, action, cur_day())
        flash('话已传到。', 'info')
    return redirect(url_for('place', key='home'))


def npc_housing_discipline(day):
    temper = dict(huafei=('kneel', 0.30), lipin=('kneel', 0.30),
                  huanghou=('reward', 0.20), duanfei=('reward', 0.20),
                  jingpin=('reward', 0.20), qifei=('reward', 0.20))
    for head in q("SELECT * FROM consorts WHERE npc_key IS NOT NULL AND hall='main' AND rank>=5 AND status IN ('normal','confined') AND discipline_ready_day<=?", (day,)):
        if head['npc_key'] not in temper or not has_residence(head): continue
        action, chance = temper[head['npc_key']]
        candidates = []
        for target in q("SELECT * FROM consorts WHERE palace=? AND user_id IS NOT NULL AND hall IN ('east','west','back') AND status IN ('normal','confined')", (head['palace'],)):
            if discipline_error(head, target, action, day): continue
            rel = relation(head['id'], target['id'])
            if action == 'kneel' and rel and rel['affinity'] > 0: continue
            candidates.append(target)
        # 每三天掷一次，即便没有发话也不在次日重掷。
        run('UPDATE consorts SET discipline_ready_day=? WHERE id=?', (day + DISCIPLINE_COOLDOWN, head['id']))
        if candidates and random.random() < chance:
            apply_discipline(head, random.choice(candidates), action, day)


@app.route('/palaces')
@login_required
def palaces():
    groups = [(group, [dict(name=name, desc=cfg['desc'], rooms=palace_household(name))
                       for name, cfg in PALACES.items() if cfg['group'] == group])
              for group in ('东六宫', '西六宫', '独院')]
    return render_template('palaces.html', groups=groups)

# ── 雅趣 ───────────────────────────────────────────────────────────────────────

def current_hobby_project(cid):
    return q("SELECT * FROM hobby_projects WHERE owner_id=? AND status='active'", (cid,), one=True)

def hobby_charge(c):
    """圣宠到「偶承恩泽」以下（不含 80）时雅趣免精力，够宠的人才占精力池"""
    if c['favor'] >= HOBBY_FREE_FAVOR:
        if c['energy'] < HOBBY_ENERGY:
            raise Reject('今天精力用完了，等夜里结算后恢复。')
        run('UPDATE consorts SET energy=energy-? WHERE id=?', (HOBBY_ENERGY, c['id']))

@app.route('/hobby')
@login_required
def hobby():
    c = g.me
    proj = current_hobby_project(c['id'])
    unlocked = hobby_unlocked_kinds(c)
    made = q('SELECT COUNT(*) n FROM hobby_items WHERE maker_id=?', (c['id'],), one=True)['n']
    held = q("SELECT * FROM hobby_items WHERE holder_id=? ORDER BY id DESC", (c['id'],))
    displayed_ids = {r['item_id'] for r in q('SELECT item_id FROM displays WHERE consort_id=?', (c['id'],))}
    return render_template('hobby.html', c=c, HOBBIES=HOBBIES, proj=proj, unlocked=unlocked,
                           can_pick_first=not unlocked, can_unlock_second=len(unlocked) == 1 and made >= HOBBY_UNLOCK_ITEMS,
                           done_today=proj is not None and proj['last_day'] == cur_day(),
                           held=held, displayed_ids=displayed_ids, DISPLAY_SLOTS=DISPLAY_SLOTS,
                           hobby_item_desc=hobby_item_desc, free=c['favor'] < HOBBY_FREE_FAVOR)

@app.route('/hobby/start', methods=['POST'])
@login_required
def hobby_start():
    c = g.me
    kind = request.form.get('kind', '')
    try: style_idx = int(request.form.get('style', ''))
    except ValueError: style_idx = -1
    unlocked = hobby_unlocked_kinds(c)
    try:
        if current_hobby_project(c['id']): raise Reject('手里已经有一件在做了，先忙完这件。')
        if kind not in HOBBIES: raise Reject('选一样雅趣。')
        if unlocked and kind not in unlocked: raise Reject('这一样你还没学，先去内务府「兼修」解锁。')
        if not 0 <= style_idx < len(HOBBIES[kind]['styles']): raise Reject(f"{HOBBIES[kind]['verb']}。")
        style = HOBBIES[kind]['styles'][style_idx]
        hobby_charge(c)
        if not unlocked:
            run('UPDATE consorts SET hobby_kinds=? WHERE id=?', (kind, c['id']))
        run("""INSERT INTO hobby_projects (owner_id, kind, style, stage, started_day)
               VALUES (?,?,?,0,?)""", (c['id'], kind, style, cur_day()))
        flash(HOBBIES[kind]['texts'][0].format(style=style), 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('hobby'))

@app.route('/hobby/unlock', methods=['POST'])
@login_required
def hobby_unlock():
    c = g.me
    kind = request.form.get('kind', '')
    unlocked = hobby_unlocked_kinds(c)
    made = q('SELECT COUNT(*) n FROM hobby_items WHERE maker_id=?', (c['id'],), one=True)['n']
    if len(unlocked) != 1 or made < HOBBY_UNLOCK_ITEMS:
        flash(f'做出 {HOBBY_UNLOCK_ITEMS} 件作品后才能兼修另一样。', 'bad')
    elif kind not in HOBBIES or kind in unlocked:
        flash('选一样还没学过的。', 'bad')
    else:
        run("UPDATE consorts SET hobby_kinds=? WHERE id=?", (unlocked[0] + ',' + kind, c['id']))
        flash(f"你开始兼修{HOBBIES[kind]['name']}了。", 'good')
    return redirect(url_for('hobby'))

@app.route('/hobby/act', methods=['POST'])
@login_required
def hobby_act():
    c = g.me
    day = cur_day()
    proj = current_hobby_project(c['id'])
    try:
        if not proj: raise Reject('你手里还没有正在做的雅趣。')
        if proj['last_day'] == day: raise Reject('今天已经打理过了，明天再来。')
        hobby_charge(c)
        cfg = HOBBIES[proj['kind']]
        stage = proj['stage'] + 1
        if stage >= len(cfg['texts']) - 1:
            item_id = run("""INSERT INTO hobby_items (kind, style, quality, maker_id, holder_id, created_day, history)
                             VALUES (?,?,?,?,?,?,'[]')""",
                          (proj['kind'], proj['style'], roll_hobby_quality(c['id'], proj['kind']),
                           c['id'], c['id'], day)).lastrowid
            run("UPDATE hobby_projects SET status='done', stage=?, last_day=? WHERE id=?", (stage, day, proj['id']))
            item = q('SELECT * FROM hobby_items WHERE id=?', (item_id,), one=True)
            flash(cfg['texts'][-1].format(style=proj['style']) + f"（{item['quality']}）——去下面看看，摆进寝宫或是送给谁。", 'good')
        else:
            run("UPDATE hobby_projects SET stage=?, last_day=? WHERE id=?", (stage, day, proj['id']))
            flash(cfg['texts'][stage].format(style=proj['style']), 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('hobby'))

@app.route('/hobby/display', methods=['POST'])
@login_required
def hobby_display():
    c = g.me
    try: item_id = int(request.form.get('item_id', 0))
    except ValueError: item_id = 0
    slot = request.form.get('slot', '')
    item = q('SELECT * FROM hobby_items WHERE id=?', (item_id,), one=True)
    if slot not in DISPLAY_SLOTS or not item or item['holder_id'] != c['id']:
        flash('摆不了这个。', 'bad')
    else:
        run('INSERT INTO displays (consort_id, slot, item_id) VALUES (?,?,?) '
            'ON CONFLICT(consort_id, slot) DO UPDATE SET item_id=excluded.item_id', (c['id'], slot, item_id))
        flash(f"{hobby_item_desc(item)}摆在了{DISPLAY_SLOTS[slot]}。", 'good')
    return redirect(url_for('hobby'))

@app.route('/hobby/undisplay/<slot>', methods=['POST'])
@login_required
def hobby_undisplay(slot):
    run('DELETE FROM displays WHERE consort_id=? AND slot=?', (g.me['id'], slot))
    return redirect(url_for('hobby'))

def hobby_provenance(item):
    """陈设旁边那句来历：谁做的、送没送过人"""
    history = json.loads(item['history'] or '[]')
    if item['maker_id'] != item['holder_id'] or history:
        maker = get_consort(item['maker_id'])
        return f"{display_name(maker)}做的，第 {history[-1]['day'] if history else item['created_day']} 天送到了这里"
    return f"第 {item['created_day']} 天做的，一直留在自己身边"

def room_view(cid, mine):
    t = get_consort(cid)
    if not t or t['status'] in ('dead', 'xiunv'):
        flash('没有这个人。', 'bad')
        return redirect(url_for('social'))
    slots = {}
    for slot in DISPLAY_SLOTS:
        row = q("""SELECT h.* FROM displays d JOIN hobby_items h ON h.id=d.item_id
                   WHERE d.consort_id=? AND d.slot=?""", (cid, slot), one=True)
        slots[slot] = dict(item=row, prov=hobby_provenance(row) if row else '') if row else None
    held = q("SELECT * FROM hobby_items WHERE holder_id=? ORDER BY id DESC", (cid,)) if mine else []
    displayed_ids = {r['item_id'] for r in q('SELECT item_id FROM displays WHERE consort_id=?', (cid,))} if mine else set()
    return render_template('room.html', t=t, mine=mine, slots=slots, DISPLAY_SLOTS=DISPLAY_SLOTS,
                           held=held, displayed_ids=displayed_ids, hobby_item_desc=hobby_item_desc, HOBBIES=HOBBIES)

@app.route('/room')
@login_required
def room():
    return room_view(g.me['id'], True)

@app.route('/room/<int:cid>')
@login_required
def room_other(cid):
    return room_view(cid, cid == g.me['id'])


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=int(os.environ.get('PORT', 5024)))
