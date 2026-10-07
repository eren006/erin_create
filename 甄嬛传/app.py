"""甄嬛传·紫禁城 —— 多人宫斗网页游戏

玩家以秀女身份入宫，经殿选后在后宫里争宠、结盟、使计。
皇帝是系统 NPC，每晚固定时刻（SETTLE_HOUR）统一结算：阴谋 → 翻牌子 → 生产 → 晋封 → 月例。
"""
import os, re, json, random, math, time, threading, traceback, secrets
from datetime import datetime, timezone, timedelta, date
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session as S, flash, g, has_request_context, jsonify)
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
def cache_versioned_assets(resp):
    if request.endpoint == 'static' and re.fullmatch(r'palace-[0-9a-f]{12}\.webp', request.view_args.get('filename','')) and resp.status_code in (200,304):
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return resp

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
SETTLE_HOUR   = int(os.environ.get("SETTLE_HOUR", 0))    # 2026-10-06 起每天 0 点换新一天（原 23 点）
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

RANK_NAMES = ['秀女', '官女子', '答应', '常在', '贵人', '嫔', '妃', '四妃', '贵妃', '皇贵妃', '皇后']   # 2026-10-07 起妃和贵妃之间加「四妃」档（淑德贤惠，rank 7），贵妃/皇贵妃/皇后顺延为 8/9/10
RANK_FOUR = 7
FOUR_CONSORT_TITLES = ['淑', '德', '贤', '惠']      # 四妃的名号：叫「封号+名号+妃」，如容德妃；这四个字不能当普通封号
PROMOTE_FAVOR  = {2: 30, 3: 65, 4: 110, 5: 180, 6: 280, 7: 350, 8: 420, 9: 600, 10: 850}   # 晋到该位分所需圣宠
PROMOTE_VIRTUE = {2: 0, 3: 10, 4: 20, 5: 35, 6: 50, 7: 55, 8: 60, 9: 70, 10: 75}          # 晋到该位分所需德行（品行高的皇上再打九折，见 promote_virtue_need）
RANK_SLOTS     = {4: 8, 5: 6, 6: 4, 7: 4, 8: 2, 9: 1, 10: 1}                     # 贵人以上有名额，含 NPC
STIPEND = {1: 15, 2: 30, 3: 45, 4: 75, 5: 200, 6: 300, 7: 375, 8: 450, 9: 650, 10: 1000}  # 每日月例银（2026-10-07 起：嫔以下 ×3，嫔以上 ×5；原来 5/10/15/25/40/60/90/130/200）
MOTHER_BY_SON_INFLUENCE = 6     # 母凭子贵已封顶（嫔以上）时，改为奖励的势力
MOTHER_BY_SON_MAX_RANK = 5   # 母凭子贵最多晋到嫔位（rank 5），再往上要靠自己的圣宠、德行和名额
PLAYER_MAX_RANK = 10   # 皇后位是普通位分，跟其他位分一样按圣宠/德行/名额晋封——名额（RANK_SLOTS[10]=1）常年被 NPC 皇后占着，除非她没了、进了冷宫，才轮得到玩家

PROMOTE_INFLUENCE = {2:2,3:6,4:12,5:25,6:45,7:55,8:70,9:110,10:150}
INFLUENCE_LOW_NIGHTS = 2          # 2026-10-07 起：势力连续这么多晚低于当前位分要求，降一级
PROMOTE_INFLUENCE_REWARD = 3     # 第一次晋到嫔位及以上的每一级，额外奖励势力（2026-10-07 起）
INFLUENCE_GAINS = dict(rumor=5,steal=1,frame=10,drug=10,expose=10,witch=18,punish=10)
FIZZLE_INFLUENCE_FRACTION = 0.25    # 计谋没成但也没败露：照成功的四分之一给势力（至少 1 点）；败露、落空不给
RANDOM_STAT_RANGES = dict(appearance=(30,50),talent=(25,45),scheme=(25,45),virtue=(35,55),health=(60,80))


def entry_stat_roll(uid):
    account=q('SELECT * FROM users WHERE id=?',(uid,),one=True)
    reign=state()['reign_no']
    if account['stat_roll_reign']!=reign or not account['stat_roll']:
        stats={k:random.randint(lo,hi) for k,(lo,hi) in RANDOM_STAT_RANGES.items()}
        run('UPDATE users SET stat_roll_reign=?,stat_roll=? WHERE id=?',(reign,json.dumps(stats),uid))
        return stats
    return json.loads(account['stat_roll'])


CONSPIRE_INFLUENCE_SHARE = 0.75     # 合谋得手/落空时，两人各拿多少份势力（1=独自出手的全额，两人合计 1.5 份）

_SCHEME_RNG = random.SystemRandom()      # 心计成长单独掷骰，不占用全局随机序列
SCHEME_GROW_CHANCE, SCHEME_GROW_CHANCE_FIZZLE, SCHEME_GROW_AMOUNT = 0.25, 0.10, 1   # 害人涨心计：得手 25%、没成没被察觉 10%，每次 +1；败露不涨

def gain_intrigue_influence(it, fraction=1.0, share=1.0, actor_id=None):
    atk,tgt=get_consort(actor_id or it['attacker_id']),get_consort(it['target_id'])
    if not atk or not tgt or not atk['user_id'] or not tgt['user_id'] or atk['id']==tgt['id']: return
    if it['method']=='drug' and it['drug']=='chunxin': return
    key=f"influence_target:{tgt['id']}"
    if daily_count(atk['id'],key): return
    gain=INFLUENCE_GAINS.get(it['method'],0)
    if fraction < 1 and gain: gain=max(1,round(gain*fraction))
    if share < 1 and gain: gain=max(1,round(gain*share))   # 合谋：两人各拿 CONSPIRE_INFLUENCE_SHARE 份
    if gain:
        run('UPDATE consorts SET influence=influence+? WHERE id=?',(gain,atk['id']))
        daily_inc(atk['id'],key)
        if fraction < 1:
            notify(atk['id'],f'这一回使计没成，好在没人察觉，也算攒了点人脉，势力 +{gain}。','info')
        else:
            notify(atk['id'],f'你这一回使计得手，势力 +{gain}。同日对同一人不重复增加。','good')
        # 害人历练心计：和势力共用「同日对同一人只算一次」，防止对着一个人狂刷
        p = SCHEME_GROW_CHANCE if fraction >= 1 else SCHEME_GROW_CHANCE_FIZZLE
        if atk['scheme'] < 100 and _SCHEME_RNG.random() < p:
            add_stat(atk['id'], 'scheme', SCHEME_GROW_AMOUNT)
            notify(atk['id'], f'这一番算计让你长了些见识，心计 +{SCHEME_GROW_AMOUNT}。', 'good')

FAVOR_HOT = 150
FAVOR_LOW = 40
FAVOR_DROP_DEMOTE = 50       # 一天之内圣宠净掉了这么多点以上（常在以上、入宫满 3 天的玩家），夜里结算降一级（2026-10-07 起）
UNFAVORED_GRACE_DAYS = 2
NEWCOMER_CARE_DAYS = 3
FAVOR_CARE = {
    'hot': dict(name='得宠', stipend_factor=1.5, reward=15, sick_chance=.10, survive=.80, untreated=.70, recover_nights=1, recovery_health=50),
    'normal': dict(name='普通', stipend_factor=1.0, reward=0, sick_chance=.15, survive=.70, untreated=.35, recover_nights=1, recovery_health=35),
    'low': dict(name='失宠', stipend_factor=.7, reward=0, sick_chance=.20, survive=.50, untreated=.20, recover_nights=2, recovery_health=35),
}


FAVOR_HOT_PCT = 0.25         # 2026-10-07 起：在宫玩家按圣宠排名，前 25% 得宠、后 25% 失宠，其余普通
FAVOR_LOW_PCT = 0.25
FAVOR_HOT_MIN = 50           # 排进前 20% 也要圣宠到这条线才算得宠
FAVOR_RANK_MIN_POP = 4       # 在宫玩家不足这个数，不分排名，回到固定线（FAVOR_HOT / FAVOR_LOW）


def care_pool():
    return list(q("SELECT id, favor FROM consorts WHERE user_id IS NOT NULL AND status IN ('normal','confined')"))


def care_zones(pool=None):
    """排名模式：返回 (得宠 id 集合, 失宠区 id 集合)；人太少时返回 None，走固定线"""
    pool = care_pool() if pool is None else pool
    n = len(pool)
    if n < FAVOR_RANK_MIN_POP: return None
    top = sorted(pool, key=lambda r: (-r['favor'], r['id']))
    bottom = sorted(pool, key=lambda r: (r['favor'], -r['id']))
    hot = {r['id'] for r in top[:max(1, int(n * FAVOR_HOT_PCT))] if r['favor'] >= FAVOR_HOT_MIN}
    low = {r['id'] for r in bottom[:max(1, int(n * FAVOR_LOW_PCT))]} - hot
    return hot, low


def refresh_care_tiers():
    """每晚结算开头：按当晚的圣宠排名定下今天的待遇，白天保持不变"""
    run("UPDATE consorts SET care_tier=''")
    zones = care_zones()
    if not zones: return None
    hot, low = zones
    for cid in hot: run("UPDATE consorts SET care_tier='hot' WHERE id=?", (cid,))
    for cid in low: run("UPDATE consorts SET care_tier='low' WHERE id=?", (cid,))
    return zones


for _k in ('FAVOR_HOT_PCT', 'FAVOR_LOW_PCT', 'FAVOR_HOT_MIN', 'FAVOR_RANK_MIN_POP'): app.jinja_env.globals[_k] = globals()[_k]


INFLUENCE_DECAY = 1      # 势力每晚自然衰减的点数（不低于当前位分的晋位要求；冷宫、新人期不衰减）


def influence_check(c, day):
    """每晚结算：势力低于当前位分的晋位要求，连续 INFLUENCE_LOW_NIGHTS 晚就降一级（新人前 3 天、冷宫、官女子以下不查）"""
    need = PROMOTE_INFLUENCE.get(c['rank'], 0)
    if (c['user_id'] and c['status'] in ('normal', 'confined') and day - c['entered_day'] >= NEWCOMER_CARE_DAYS
            and c['influence'] > need):        # 势力自然衰减：每晚 1 点，只消耗高出当前位分要求的余量，不会自己掉进降位判定
        run('UPDATE consorts SET influence=MAX(?, influence-?) WHERE id=?', (need, INFLUENCE_DECAY, c['id']))
    if (not c['user_id'] or c['status'] not in ('normal', 'confined') or c['rank'] < 2
            or day - c['entered_day'] < NEWCOMER_CARE_DAYS or c['influence'] >= need):
        if c['influence_low_days']: run('UPDATE consorts SET influence_low_days=0 WHERE id=?', (c['id'],))
        return
    n = c['influence_low_days'] + 1
    if n < INFLUENCE_LOW_NIGHTS:
        run('UPDATE consorts SET influence_low_days=? WHERE id=?', (n, c['id']))
        notify(c['id'], f"你的势力 {c['influence']}，{RANK_NAMES[c['rank']]}要求 {need}。再有 {INFLUENCE_LOW_NIGHTS - n} 晚还不够，就要降为{RANK_NAMES[c['rank'] - 1]}。去协办宫务、使计攒些势力。", 'bad')
        return
    old_name = display_name(c)
    run('UPDATE consorts SET influence_low_days=0 WHERE id=?', (c['id'],))
    demote_rank(c['id'])
    now = get_consort(c['id'])
    notify(c['id'], f"势力 {c['influence']} 连着 {INFLUENCE_LOW_NIGHTS} 晚不够{RANK_NAMES[c['rank']]}的 {need}，位分降为{display_name(now)}。", 'bad')
    gazette(f"{old_name}势力不足、难以服众，皇上降其位分，今称{display_name(now)}。", 'decree')


def favor_care_tier(c, day=None):
    day = cur_day() if day is None else day
    ranked = len(care_pool()) >= FAVOR_RANK_MIN_POP
    if c['status'] == 'cold': return 'low'
    if ranked:
        if c['care_tier'] == 'hot': return 'hot'
        if day-c['entered_day'] < NEWCOMER_CARE_DAYS: return 'normal'
        return 'low' if c['care_tier'] == 'low' and c['unfavored_days'] >= UNFAVORED_GRACE_DAYS else 'normal'
    if c['favor'] >= FAVOR_HOT: return 'hot'
    if day-c['entered_day']<NEWCOMER_CARE_DAYS: return 'normal'
    return 'low' if c['favor']<FAVOR_LOW and c['unfavored_days']>=UNFAVORED_GRACE_DAYS else 'normal'


def favor_stipend(c, day=None):
    if c['status']=='cold': return 0
    cfg=FAVOR_CARE[favor_care_tier(c,day)]
    return math.floor(STIPEND.get(c['rank'],0)*cfg['stipend_factor'])+cfg['reward']


def ordinary_illness_chance(c,day):
    if day-c['entered_day']<NEWCOMER_CARE_DAYS or day<=c['protected_until_day']: return 0
    return FAVOR_CARE[favor_care_tier(c,day)]['sick_chance']

FAVOR_DECAY = 0.04    # 每晚圣宠自然流失比例
EAST_PALACE_CHANCE = 0.15
EAST_PALACE_FAVOR = 10
EAST_PALACE_TRUST = 5
INITIAL_EMPEROR_AGE = 20
AGE_YEARS_PER_DAY = 2
AGE_MONTHS_PER_DAY = AGE_YEARS_PER_DAY * 12
ENERGY_MAX = 8
STUDY_FAVOR_GAIN = 5
AUDIENCE_WAIT_DAYS = 3
PREGNANCY_PITY_ATTEMPTS = 5      # 连续 5 次有效侍寝没怀上，第 6 次必怀（原 4 次/第 5 次；保底太早，底数调低也没用）
PREGNANCY_DAYS = 2      # 旧存档未记录喜脉时刻时沿用两次结算
PREGNANCY_MIN_SECONDS = 24 * 60 * 60
FERTILE_BEFORE_AGE = 45 # 四十五岁起不再新怀孕
LETHAL_COOLDOWN = 2     # 致命药成功后账号冷却2天
CASE_JOIN_WINDOW, CASE_JOIN_MAX = 3, 1   # 一个人 3 天内最多被拉去陪查 1 次（真凶不算）
CASE_NEWCOMER_SHIELD = 2      # 入宫不满 2 天的人不被拉去陪查（2026-10-06 从 5 天压到 2）
BRIBE_NEWCOMER_SHIELD = 2     # 入宫不满 2 天的人，宫人不能被打点（2026-10-06 从 5 天压到 2）
NEWCOMER_LETHAL_SHIELD = 3   # 入宫前 3 天不能被毒害
RESCUE_PROTECT_DAYS = 2      # 中毒获救后这么多天不能再被毒害（2026-09-28 从 3 压到 2）
TREAT_COST = 50
TREAT_COST_BY_RANK = {1: 20, 2: 20, 3: 30, 4: 40}   # 按病人的位分，嫔以上 50（2026-10-06：官女子净赚 2 两/晚，原 50 两要攒 25 晚）

def treat_cost(c):
    return TREAT_COST_BY_RANK.get(c['rank'], TREAT_COST)
POISON_SURVIVE = {0: 0.35, 1: 0.90}   # 没请太医 / 请了太医（病重沿用同一套概率）
CONFINE_DAYS = 1   # 2026-09-28 从 2 压到 1；2026-10-07 起禁足统一半天，按小时算（CONFINE_HOURS），这个只作按天结算的兜底
CONFINE_HOURS = 12 # 所有禁足一律半天，不管因为什么
COLD_DAYS = 3   # 2026-09-28 从 5 压到 3

# ── 老死与病死 ─────────────────────────────────────────────────────────────────
OLD_AGE_START = 600          # 50 岁（600 个月）起，每晚有寿终的可能
OLD_AGE_BASE = 0.003          # 概率 = (年龄 - 50) × 0.3%，体质 ≥60 减半、<30 翻倍
OLD_AGE_REMINDER_START = 660  # 55 岁起，每满 5 岁提醒一句
OLD_AGE_REMINDER_STEP = 60
WEAK_SICK_DAYS = 2            # 连续体质 <25 这么多天，染病（2026-09-28 从 3 压到 2）
COLD_SICK_CHANCE = 0.05       # 冷宫阴寒，每晚染病概率
EPIDEMIC_INTERVAL = 5        # 全宫时疫，每隔这么多天可能来一次（2026-09-28 从 10 压到 5）
EPIDEMIC_CHANCE = 0.3         # 到了日子，真发生时疫的概率
POSTPARTUM_SICK_DAYS = 2      # 小产、难产后这么多天内（2026-09-28 从 3 压到 2）
POSTPARTUM_SICK_CHANCE = 0.10 # ……每晚染病概率
SHI_WORDS = ['孝', '敬', '贞', '惠', '顺', '安', '静', '和']  # 老死时嫔以上追封的谥字

TRUST_START = 20
TRUST_WORDS = [(70, '倚重'), (40, '信得过'), (20, '尚可'), (-1, '存疑')]
TRUSTED_LINE = 50           # 信任到这条线，被散流言/栽赃时圣宠损失减半
NPC_BED_MULT = 0.5          # NPC 翻牌权重打五折，免得宫里原有的妃嫔占掉大半夜晚
AUDIENCE_PER_NIGHT = 2      # 每晚除侍寝外再单独召见几位玩家
LONG_UNSEEN_DAYS = 3        # 这么多天没见过皇上，算"久未见驾"（2026-09-28 从 6 压到 3）

TITLE_POOL = list('莞安祺瑾婉容贞淳柔懿宁怡颖璟瑶玥韵馨娴嘉恬澜宸昭徽祥和敏')      # 淑德贤惠留给四妃，不进普通封号池

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


ARTS = ['琴', '棋', '书', '画', '诗', '舞', '女红', '琵琶', '笛子']
ART_MASTERY = 8       # 修习满这么多次算精通

FAVOR_WORDS = [(600, '圣眷正浓'), (250, '颇得圣心'), (80, '偶承恩泽'), (1, '圣恩尚浅'), (-1, '未曾承宠')]

def favor_word(f):
    for th, w in FAVOR_WORDS:
        if f >= th: return w
    return '未曾承宠'

def display_name(c):
    if c is None: return '（无）'
    if c['status'] == 'dead':
        return f"故·{c['title'] or c['surname']}{(c['four_word'] + '妃') if c['rank'] == RANK_FOUR else RANK_NAMES[c['rank']]}"
    if c['status'] == 'cold':
        return f"{c['surname']}氏"
    r = c['rank']
    if r == 0: return f"秀女{c['surname']}{c['given']}"
    if r == PLAYER_MAX_RANK: return '皇后'
    if r == RANK_FOUR: return f"{c['title'] or c['surname']}{c['four_word']}妃"      # 四妃叫「封号+淑/德/贤/惠+妃」，如容德妃
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

FAMILY_TYPE_NAMES = dict(dali='清流官宦',jizhou='旗营世家',songyang='寒门小吏',merchant='商贾之家',general='将门世家',hanlin='书香门第',physician='医药世家',manchu='勋贵旁支')
FAMILY_ORIGIN_ROLES = dict(dali=('断案世家','监察世家','律学世家'),jizhou=('旗营旧族','骑射世家','驻防世家'),songyang=('县学小吏之家','乡塾之家','寒门书吏之家'),merchant=('绸缎商家','茶商之家','药材商家'),general=('守关将门','水师将门','骑兵将门'),hanlin=('诗礼世家','藏书世家','经学世家'),physician=('杏林世家','针灸世家','本草世家'),manchu=('勋贵分支','公府旁支','旧勋世家'))
FAMILY_ORIGIN_PLACES = ('京城','江宁','苏州','杭州','扬州','湖州','徽州','绍兴','嘉兴','宁波','泉州','福州','广州','济南','济宁','登州','保定','真定','太原','大同','西安','汉中','成都','重庆','武昌','长沙','南昌','九江','洛阳','开封','襄阳','荆州','安庆','镇江','常州','松江','温州','台州','金陵','临清')
for family_key,type_name in FAMILY_TYPE_NAMES.items():
    FAMILIES[family_key]['name'] = type_name


def family_origin_options(tier, db=None, limit=6):
    rows = db.execute("SELECT background FROM families WHERE background!=''").fetchall() if db else q("SELECT background FROM families WHERE background!=''")
    used = {row[0] for row in rows}
    choices = [place+role for place in FAMILY_ORIGIN_PLACES for role in FAMILY_ORIGIN_ROLES[tier] if place+role not in used]
    if len(choices)<limit:
        for branch in range(1,len(used)+limit+2):
            candidate=FAMILY_TYPE_NAMES[tier]+f'第{branch}支'
            if candidate not in used: choices.append(candidate)
            if len(choices)>=limit:break
    return choices[:limit]


def family_background(c):
    uid=consort_uid(c)
    fam=family_row(uid) if uid else None
    return (fam['background'] if fam and fam['background'] else FAMILIES[c['family']]['name'])


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
    'lover':     dict(name='入宫前曾有意中人', weight=28,
                      penalty='圣宠 -60，德行 -15', confess='圣宠 -24'),
    'fake':      dict(name='冒认了出身', weight=22,
                      penalty='降一级位分', confess='圣宠 -36'),
    'book':      dict(name='私藏禁书', weight=18,
                      penalty='禁足半天', confess='禁足半天'),
    'scar':      dict(name='脸上旧伤一直用脂粉遮着', weight=22,
                      penalty='容貌 -10，圣宠 -24', confess='容貌 -5'),
    'physician': dict(name='与太医过从甚密', weight=10,
                      penalty='打入冷宫', confess='禁足半天'),
}

def roll_secret():
    keys = list(SECRETS)
    return random.choices(keys, weights=[SECRETS[k]['weight'] for k in keys])[0]

# ── 物品 ───────────────────────────────────────────────────────────────────────

YINZHEN_OLD_PRICE, YINZHEN_PRICE = 60, 100     # 2026-10-07 银针涨价，已持有的按差价补扣（migrate_yinzhen_price）

ITEMS = {
    'renshen':  dict(name='老山参', price=60, usable=True, desc='体质 +15'),
    'shuhen':   dict(name='舒痕胶', price=150, usable=True, desc='容貌 +3（每天限用一次）'),
    'shujin':   dict(name='蜀锦新衣', price=80, usable=True, desc='今晚翻牌子的机会大增'),
    'qinpu':    dict(name='前朝琴谱', price=50, usable=True, desc='才艺 +3'),
    'cuisheng': dict(name='催产丹', price=150, usable=True, desc='有孕时服用：缩短孕期 6 小时，可连着吃'),
    'antai':    dict(name='安胎药', price=100, usable=False, desc='放在身边：有孕时若遭人下药，可保住胎儿一次'),
    'ruyi':     dict(name='玉如意', price=120, usable=False, desc='赠给别人，对方好感 +15'),
    'yinzhen':  dict(name='银针', price=YINZHEN_PRICE, usable=False, desc='放在身边：被人下药时成算 -15%，挡下一次就断一根'),
    # 宫人闲时做的小东西：内务府不卖，只能攒出来；可以自己用，也能写信附给别人
    'xiangnang': dict(name='香囊', price=0, craft=True, usable=True, desc='手巧的宫人缝的。佩上：今晚翻牌子的机会略添一分'),
    'dianxin':   dict(name='点心匣', price=0, craft=True, usable=True, desc='忠厚的宫人备的。吃下：体质 +2'),
    'tiseng':    dict(name='提神茶', price=0, craft=True, usable=True, desc='机灵的宫人泡的。喝下：精力 +1（不超过上限）'),
    'hebao':     dict(name='荷包', price=0, craft=True, usable=True, desc='嘴紧的宫人缝得严严实实，里头塞着攒下的体己：银子 +15 两'),
}

# ── 药材（内务府暗柜）──────────────────────────────────────────────────────────
# 药名全部原创。case：什么时候开案——now 当晚 / bed 被翻牌那夜 / diag 被诊出时 / due 临盆那夜 / none 不开案
# eat：是吃进去的（试毒宫人尝得出来）；days：药效持续几晚（含当晚）

DRUGS = {
 'yanzhi':dict(name='胭脂霰',rank=2,price=80,case='now',eat=False,days=1,hours=24,desc='容貌暂降5、24小时内不能侍寝；药效结束恢复被扣容貌'),
 'jingmeng':dict(name='惊梦香',rank=2,price=100,case='bed',eat=False,days=1,hours=24,desc='最多持续24小时；下一次侍寝不涨圣宠、圣宠 -18、信任-3，触发一次即失效'),
 'yachan':dict(name='哑蝉汤',rank=3,price=120,case='now',eat=True,days=1,hours=24,desc='才艺暂降5，24小时内召见与侍寝只能选体谅；药效结束恢复被扣才艺'),
 'hanshui':dict(name='寒水散',rank=3,price=200,case='now',eat=True,days=2,hours=48,desc='体质-10、阻孕48小时；有孕时50%概率小产，安胎药可挡一次'),
 'qingsi':dict(name='青丝引',rank=4,price=250,case='diag',eat=True,days=3,hours=0,desc='慢毒：第一次发作体质-10，之后每次日结算体质-4，直到解毒；诊脉可解毒；体质耗尽就转成中毒，生死各凭天命'),
 'chunxin':dict(name='春信丹',rank=4,price=300,case='due',eat=True,days=0,hours=24,desc='假孕24小时后揭穿，不会生出孩子；信任不足50时禁足半天、信任-5'),
 'lihun':dict(name='离魂草',rank=5,price=500,case='now',eat=True,days=0,hours=0,desc='致死毒：下次结算判断生死，需及时请太医；存活率受得宠待遇、治疗及福报影响，成功后账号冷却2天'),
 'wuming':dict(name='无名',rank=6,price=800,case='none',eat=False,days=0,hours=0,desc='可配其他药（离魂草除外），24小时后线索浮现，仍可调查；成功后账号冷却1天'),
}
DRUG_ENERGY = 1
DRUG_BASE = 0.40
CABINET_SLOTS = 3             # 暗柜每人每天刷几种
LEDGER_CHANCE = 0.10          # 暗柜买药被内务府记一笔的概率
NAMELESS_COOLDOWN = 1   # 无名成功后冷却1天
DRUG_NEWCOMER_SHIELD = 1      # 入宫首日双方不可下药
DRUGGED_SHIELD = 1            # 普通药保护1天，致命药用drugged_until_day保护2天
SELF_HAND_PENALTY = 0.15      # 没有内应、自己动手
NEEDLE_BLOCK = 0.15
TASTER_LOYALTY = 80           # 忠心到这里的宫人会替主子试毒
TASTER_CHANCE = 0.20
GIFT_DRUG_CHANCE = 0.05       # 手巧、忠心 ≥80 的宫人每晚献药
DIAGNOSE_CHANCE = 0.70
SLOW_POISON_FIRST, SLOW_POISON_TICK = 10, 4   # 青丝引：第一次发作体质 -10，之后每次日结算 -4，直到被诊出（2026-10-07 改，原为 3 次、每次 -4）

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
HOBBY_ENERGY = 0
HOBBY_DAILY_MAX = 3            # 每天最多打理几次（原来每天 1 次，2026-10-05 放宽）
HOBBY_FREE_FAVOR = 80          # 圣宠到「偶承恩泽」以下（不含）时，雅趣免精力——失宠时更该有地方可去
HOBBY_UNLOCK_ITEMS = 3         # 做出几件作品后，开放兼修第二样
HOBBY_QUALITIES = ['普通', '精巧', '上品']
HOBBY_GIFT_AFFINITY = 10       # 送自己做的作品，好感 +10（比玉如意 15 克制一点，比普通东西更值钱）
DISPLAY_SLOTS = dict(window='窗边', desk='案头', wall='墙上', tea='茶席')

def roll_hobby_quality(cid, kind, day=None):
    """品级只看做过几件同类作品加一点运气，跟属性无关——雅趣拼的是用心，不是天赋。
    赶上节令小事那天成型，运气再添一点，只影响这个品级文案，不影响任何数值"""
    made = q('SELECT COUNT(*) n FROM hobby_items WHERE maker_id=? AND kind=?', (cid, kind), one=True)['n']
    r = random.random() + made * 0.05
    if active_season(day if day is not None else cur_day()): r += SEASON_QUALITY_BONUS
    if r >= 0.92: return '上品'
    if r >= 0.60: return '精巧'
    return '普通'

def hobby_item_desc(item):
    return f"{HOBBIES[item['kind']]['name']}·{item['style']}（{item['quality']}）"

def hobby_unlocked_kinds(c):
    return [k for k in c['hobby_kinds'].split(',') if k]

# ── 行动 ───────────────────────────────────────────────────────────────────────

ACTIONS = {
    'greet':   dict(name='礼仪堂晨省', energy=0, silver=0, daily=1, when={'normal'}, sick_block=True,
                    desc='参加宫中晨省，德行 +1；不花精力'),
    'study':   dict(name='修习才艺', energy=1, silver=0, daily=3, when={'normal', 'confined'},
                    desc='才艺提升；正常时圣宠 +5，练皇上喜好的再 +3；某门修满 8 次即精通'),
    'schemestudy': dict(name='读书习谋', energy=1, silver=0, daily=2, when={'normal', 'confined'},
                    desc='读史书、兵书、旧年档案，琢磨人心。心计 +1（心计越高越难长：50 以下必涨，往上渐成概率）'),
    'perform': dict(name='御前展示才艺', energy=1, silver=0, daily=1, when={'normal'}, sick_block=True, desc='挑一样才艺御前展示，成功圣宠 +12～18，失败 +3；连着两次不能展示同一样才艺；病重时暂停'),
    'palace_work': dict(name='协办宫务', energy=1, silver=0, daily=1, when={'normal'}, sick_block=True, desc='协助整理宫务，势力 +3、德行 +1'),
    'aid': dict(name='帮助姐妹', energy=1, silver=20, daily=1, when={'normal'}, sick_block=True, target=True, desc='送去日常补养，势力 +3、德行 +1，对方体质 +3；每天一次'),
    'groom':   dict(name='梳妆保养', energy=1, silver=15, daily=2, when={'normal', 'confined'},
                    desc='容貌 +1~2（梳妆最多养到 65），体质 +3'),
    'garden':  dict(name='去御花园走走', energy=1, silver=0, daily=2, when={'normal'}, sick_block=True,
                    desc='说不定能遇见皇上，也说不定撞见不该看的'),
    'seek':    dict(name='送汤羹去养心殿', energy=1, silver=20, daily=2, when={'normal'}, sick_block=True,
                    desc='看皇上心情，圣宠上涨，今晚翻牌机会增加'),
    'rest':    dict(name='静养', energy=1, silver=0, daily=3, when={'normal', 'confined', 'cold'},
                    desc='体质 +8'),
    'reflect': dict(name='闭门自省', energy=1, silver=0, daily=2, when={'confined', 'cold'},
                    desc='德行 +2；在冷宫里还有一线机会让皇上想起你'),
    'eyes':    dict(name='安插眼线', energy=0, silver=100, daily=1, when={'normal', 'confined'},
                    desc='两天内更难被算计，被害时能知道是谁'),
    'visit':   dict(name='串门', energy=1, silver=0, daily=3, when={'normal'}, sick_block=True, target=True,
                    desc='双方好感 +6~10；每天第一次串门不花精力'),
    'spy':     dict(name='打探底细', energy=0, silver=30, daily=1, when={'normal'}, target=True, errand=True,
                    desc='派一个宫人去打听对方的秘密（用一次差使，不花精力）'),
    'maid_snack':  dict(name='差使·御膳房取点心', energy=0, silver=0, daily=4, when={'normal', 'confined'}, errand=True,
                        desc='派一个宫人去御膳房讨点心：体质 +1，今晚翻牌的机会略添一分（用一次差使，不花精力）'),
    'maid_shop':   dict(name='差使·内务府跑腿', energy=0, silver=0, daily=4, when={'normal', 'confined'}, errand=True,
                        desc='派一个宫人去内务府打点招呼：今天在内务府买东西九折（用一次差使，不花精力）'),
    'maid_scribe': dict(name='差使·敬事房打点', energy=0, silver=20, daily=4, when={'normal'}, errand=True,
                        desc='花 20 两让宫人去敬事房递个话：今晚翻牌的机会大增（用一次差使，不花精力）'),
    'maid_watch':  dict(name='差使·守夜', energy=0, silver=0, daily=4, when={'normal', 'confined'}, errand=True,
                        desc='派一个宫人守夜：今晚被人使计、下药的成算 −8%，多个宫人守夜不叠加（用一次差使，不花精力）'),
    'maid_gossip': dict(name='差使·探风声', energy=0, silver=0, daily=4, when={'normal'}, errand=True,
                        desc='派一个宫人去各宫听风声，带回一则别宫今天的动静；贪财的宫人再花 10 两能多买到一则（用一次差使，不花精力）'),
    'plead':   dict(name='向皇上求情', energy=1, silver=50, daily=1, when={'normal'}, target=True,
                    desc='为禁足或冷宫中的姐妹求情，缩短日子。成败看皇上对你的信任'),
    'pray':    dict(name='去佛堂礼佛', energy=1, silver=0, daily=1, when={'normal', 'confined'},
                    desc='添香油钱，攒福报：福报高的人不容易老死、病重时活路更大。这五天没对人使过计的「躺平」之人，佛前还有机会延年益寿'),
    'shoukang': dict(name='去寿康宫请安', energy=1, silver=0, daily=1, when={'normal'}, sick_block=True,
                     desc='太妃姑母会悄悄告诉你一件宫里的旧事。3 天一次'),
    'pizhe':   dict(name='陪皇上批折子', energy=1, silver=0, daily=1, when={'normal'}, sick_block=True, min_rank=5,
                    desc='嫔位以上才能陪驾：研墨添香，圣宠 +10～14，信任 +2，势力 +4；皇上正在气头上时只能默默陪着，信任 +1、势力 +2'),
    'chastise': dict(name='责罚低位妃嫔', energy=1, silver=0, daily=1, when={'normal'}, sick_block=True, target=True, min_rank=5,
                     desc='嫔位以上才能责罚比自己位分低的嫔以下妃嫔：罚跪（对方圣宠 -8）、罚俸（对方银子 -80）或禁足半天。对方每天最多被责罚一次，双方好感 -10，对方会知道是谁。你势力 +3'),
    'attend':  dict(name='去养心殿侍疾', energy=1, silver=0, daily=1, when={'normal'}, sick_block=True,
                    desc='皇上病重时才有。成败看信任：成了信任 +5，你抚养的阿哥圣眷 +5'),
}

# ── 阴谋 ───────────────────────────────────────────────────────────────────────

INTRIGUES = {
    'rumor':  dict(name='散布流言', silver=30, energy=0, min_rank=1, base=0.60, npc_ok=True,
                   desc='成：对方圣宠 -18（皇上信任她则 -9），德行 -3。败露：自己德行 -5，圣宠 -12'),
    'steal':  dict(name='截宠', silver=60, energy=0, min_rank=1, base=0.55, npc_ok=True,
                   desc='若今晚翻的是对方的牌子，由你顶上。得手：对方圣宠 -5，且一定知道是你。败露：不受处罚。落空（对方没被翻牌）退还一半银子'),
    'frame':  dict(name='栽赃陷害', silver=100, energy=0, min_rank=2, base=0.50, npc_ok=True,
                   desc='成：对方禁足半天，圣宠 -24（皇上信任她则 -12）。败露：自己禁足半天，圣宠 -18'),
    'drug':   dict(name='下药', silver=0, energy=DRUG_ENERGY, min_rank=2, base=DRUG_BASE, npc_ok=False,
                   desc='用手里的药，交给对方宫里的内应去下，或者自己动手'),
    'expose': dict(name='告发秘密', silver=50, energy=0, min_rank=1, base=0.75, npc_ok=False,
                   desc='需先探到对方的秘密。皇上信不信看你的信任。成：按秘密处罚对方，你信任 +5。不信：自己德行 -8，圣宠 -18，信任 -5'),
    'impeach': dict(name='参奏降位', silver=250, energy=1, min_rank=5, base=0.45, npc_ok=False,
                    desc='嫔位以上，要比对方高两级以上，对方得是常在以上，每 3 天一次，同一个人 3 天内只能被参一回。成：对方降一级，圣宠 -12。败露：自己德行 -8，圣宠 -18，信任 -8'),
    'witch':  dict(name='构陷巫蛊', silver=300, energy=1, min_rank=4, base=0.40, npc_ok=True,
                   desc='成：对方打入冷宫。败露：打入冷宫的是你'),
    'punish': dict(name='发落宫人', silver=50, energy=1, min_rank=5, base=0.55, npc_ok=False,
                   desc='找个由头，把对方宫里一个宫人拖去慎刑司。要比对方高两级以上，每 3 天一次；'
                        '对方会知道是你。成：那个宫人没了，对方全宫宫人忠心 -5。败露：德行 -8，信任 -5'),
}
INTRIGUE_TARGET_DAILY_MAX = 2
INTRIGUE_DAILY_MAX = None      # 每人每天最多谋划几件事；None = 不限（2026-10-07 起，原来 1）。同一目标每天最多被 2 件事盯上仍算

def intrigue_capped(cid):
    return INTRIGUE_DAILY_MAX is not None and daily_count(cid, 'intrigue') >= INTRIGUE_DAILY_MAX
LEGACY_INTRIGUE_NAMES = dict(lethal='毒害', poison='暗下麝香')

# ── 合谋（2026-10-06）：一人发起、另一人确认；确认前不扣任何东西 ───────────────────────────────
CONSPIRE_BONUS = 0.20          # 合谋双方成功率各 +20%，仍受 85% 上限
CONSPIRE_AFFINITY_MIN = 60     # 好感必须大于这个数
CONSPIRE_COST_RATIO = 1.5      # 每人各付单人价的 1.5 倍
CONSPIRE_INVITE_SECONDS = 24 * 3600   # 邀请 1 天内不确认就作废
CONSPIRE_METHODS = ('rumor', 'steal', 'frame', 'expose', 'witch', 'punish')   # 下药另有案子系统，暂不支持合谋

def conspire_cost(cfg):
    return int(round(cfg['silver'] * CONSPIRE_COST_RATIO))

def conspire_affinity(a_id, b_id):
    rel = relation(a_id, b_id)
    return rel['affinity'] if rel else 0

def conspire_partner_block(c, p, cfg, tgt, day):
    """合伙人这一头够不够格；发起时和确认时都要查"""
    if not p or not p['user_id'] or p['id'] == c['id'] or p['id'] == tgt['id']: return '这个人不能当合谋的伙伴。'
    if p['status'] != 'normal' or is_sick(p): return f"{display_name(p)}眼下顾不上这件事。"
    if p['rank'] < cfg['min_rank']: return f"{display_name(p)}位分不够，使不动「{cfg['name']}」。"
    if conspire_affinity(c['id'], p['id']) <= CONSPIRE_AFFINITY_MIN: return f"你和{display_name(p)}的交情还不够，好感要超过 {CONSPIRE_AFFINITY_MIN} 才能合谋。"
    if intrigue_capped(p['id']): return f"{display_name(p)}今天已经另有谋划了。"
    if p['energy'] < cfg['energy']: return f"{display_name(p)}精力不够。"
    if p['silver'] < conspire_cost(cfg): return f"{display_name(p)}银子不够，合谋每人要 {conspire_cost(cfg)} 两。"
    return None

def expire_conspire_invites():
    run("UPDATE intrigues SET status='expired' WHERE status='invited' AND created_ts < ?", (now_ts() - CONSPIRE_INVITE_SECONDS,))

# ── 流言库（2026-10-07）：流言得手时邸报里写「流言四起：……」，每条只用一次，用完一轮再重来 ──────────────────
RUMORS = [
    '{t}夜里常偷偷出宫门，也不知是去见了谁，守夜的小太监都瞧见过。',
    '{t}宫里那只翡翠镯子，原是库房失了的那一只，如今却戴在她腕上。',
    '{t}平日里待宫人刻薄，克扣月钱不说，动辄罚跪，已有两个丫头哭着求调走。',
    '{t}夜里睡梦中总唤着一个男子的名字，守夜的宫女都听得真真的。',
    '{t}给太后抄的经书全是请人代笔，自己一个字都没动过。',
    '{t}装病争宠，太医去了三回都说脉象平和，偏她次次说胸口疼。',
    '{t}私下里说皇后娘娘面相刻薄，这话被一个小宫女听了去，已经传遍了。',
    '{t}在御花园里撞见过几回外头进来的画师，说话竟比对自家姐妹还亲热。',
    '{t}屋里熏的香是私下托人从宫外带进来的，内务府那边压根没有记档。',
    '{t}看着温顺，背地里常拿别的小主的生辰八字翻来覆去地念叨。',
    '{t}拿了内务府的缎子去做衣裳，转手就把原料卖到外头换了银子。',
    '{t}一个人在偏殿里烧纸，嘴里念念有词，也不知烧的是什么。',
    '{t}每回见皇上都要先让宫人去探听今日皇上的心情，生怕说错一个字。',
    '{t}家里托人捎进来的银子数目大得吓人，宫里俸禄哪里攒得出这许多。',
    '{t}对着镜子练了好几个月的哭相，就等着在皇上跟前使出来。',
    '{t}宫里的丫头们私下都说，她屋里最近总有股药味，也不知在吃什么方子。',
    '{t}曾在晨省的路上与另一位小主争执，还推了人一把，只是没人敢作声。',
    '{t}把皇上赏的东西偷偷拿去典当，说是缺银子使，其实是给外头的人补贴。',
    '{t}平日里谁的宫里新添了好东西，她都要打发人去看个究竟，回来便说酸话。',
    '{t}夜里总有人影在她窗外徘徊，也不知是宫人还是别的什么人。',
    '{t}从不亲自喝宫里送来的汤羹，说是怕有人下毒，倒像是自己心里有鬼。',
    '{t}曾在梳妆台下藏了一本写满人名的册子，写的是谁欠了她的情。',
    '{t}对娘家人吹嘘说皇上最听她的话，这话已被人原样传了回来。',
    '{t}嫌宫里的茶不好，非要托人从江南带茶叶，用度早就逾了制。',
    '{t}在佛堂跪了半个时辰就晕倒了，旁人都说是做样子给人看。',
    '{t}背着人把宫里的旧衣裳改了样子穿，却说是皇上新赏的料子。',
    '{t}与御膳房的太监来往过密，月月有东西从后厨悄悄送进她宫里。',
    '{t}同屋的小宫女说，她半夜起来对着墙角絮絮说话，白天却什么都不认。',
    '{t}借着请安的由头，在太妃跟前说了不少别人的闲话，被拆穿了还不认。',
    '{t}自己屋里的猫死得蹊跷，却一口咬定是别宫的人下的手。',
    '{t}上个月丢的那支金钗，有人亲眼见她的丫头拿到当铺去了。',
    '{t}夜里让宫人替她放风，自己却往西边的角门溜了出去。',
    '{t}总说身子不适不去晨省，可傍晚有人看见她在御花园里走得比谁都快。',
    '{t}把别人送她的礼物转手又送给了另一位小主，还当着人家的面说是自己亲手做的。',
    '{t}宫里的老嬷嬷说，她刚入宫时就不是个安分的，连管教的嬷嬷都被她哄得团团转。',
    '{t}近来脾气越发古怪，一点小事就摔东西，贴身的丫头们都不敢近前。',
    '{t}偷偷让人在别宫的墙根下埋了东西，也不知是诅咒还是什么。',
    '{t}说是向着皇后，其实暗地里常给别的娘娘递话，两头讨好。',
    '{t}一条手帕上绣的竟不是花样，而是一首情诗，不知是写给谁的。',
    '{t}晚上不许丫头们点灯，一个人坐在黑里，也不知在盘算什么。',
    '{t}在姐妹们面前装得宽厚大方，一转身就让宫人把人家送的东西扔去了库房。',
    '{t}得了点宠就敢在宫道上不让路，连位分比她高的主子都敢拦着说话。',
    '{t}宫里传言，她那副好嗓子是特地请了师傅调教过的，专为唱给皇上听。',
    '{t}花了大价钱买通了敬事房的小太监，翻牌子那天总能提前知道消息。',
    '{t}生辰那天故意不说，等别人送了礼才装作惊喜，其实早把消息递了出去。',
    '{t}喝的是什么补药没人说得清，只知道从来不让宫人经手，都是自己煎。',
    '{t}和宫里哪位小主都能说上话，偏偏谁的心事都不往心里去，转头就说给下一个人听。',
    '{t}夜里翻墙头摘了别宫的海棠花，被扫地的嬷嬷撞见，还拿银子封了嘴。',
    '{t}嘴上念着佛，怀里却总揣着一把小剪刀，谁也不知道是做什么用的。',
    '{t}近来总往寿康宫跑，说是请安，旁人却见她出来时手里多了一只锦盒。',
    '{t}一件旧事被翻了出来：她入宫前家里曾有一桩官司，至今没人说得清结果。',
    '{t}见了位分低的就端着，见了位分高的就谄着，那副嘴脸宫里人都背后学得惟妙惟肖。',
    '{t}在自己宫里偷偷摆了牌位，不知供的是谁，香火倒是日日不断。',
    '{t}宫里的小太监说，她最爱打听谁今夜被翻了牌子，打听完就闷在屋里不出声。',
    '{t}总说自己不爱争宠，偏偏每回皇上驾临，她宫里的灯总比旁人亮上三分。',
    '{t}从来不用宫里份例的胭脂，说是嫌粗，每月却又偏要多领一份。',
    '{t}曾背地里议论皇上的衣着，说得有鼻子有眼，被人听去传到了上头。',
    '{t}有一回在后院和一个陌生男子说话，那人自称是送花木的匠人，可谁也没见过他进来。',
]

def pick_rumor(name):
    """从流言库里挑一条没用过的，把 {t} 换成被传的人；用光了就清空重来"""
    used = {r['idx'] for r in q("SELECT idx FROM rumor_used")}
    free = [i for i in range(len(RUMORS)) if i not in used]
    if not free:
        run("DELETE FROM rumor_used")
        free = list(range(len(RUMORS)))
    i = random.choice(free)
    run("INSERT INTO rumor_used (idx) VALUES (?)", (i,))
    return RUMORS[i].format(t=name)

INTRIGUE_REALTIME = True      # 2026-10-07 起：使计、下药一提交就判定，不再等日结算（截宠要等翻牌轮抽中，仍在翻牌时判）
RESULT_WORDS = {'success': '得手了', 'caught': '败露了，被当场拿住', 'fizzle': '没成，好在没人察觉', 'void': '落空了'}
RESULT_KIND = {'success': 'good', 'caught': 'bad', 'fizzle': 'info', 'void': 'info'}

def resolve_now(iid):
    """使计提交（或合谋确认）后马上判定；截宠要看翻牌轮抽中谁，留给翻牌轮，返回 None"""
    if not INTRIGUE_REALTIME: return None
    it = q("SELECT * FROM intrigues WHERE id=?", (iid,), one=True)
    if not it or it['status'] != 'pending' or it['method'] == 'steal': return None
    return resolve_intrigue(it)[0]

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
         teach='内务府会按你的位分给宫人份例，往后不少事都要靠宫人跑腿；精力每天 8 点，例银按位分每晚发。',
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

# ── 嬷嬷们：每个新人入宫时随机分到一位，名字、口吻都不一样。老档里没记录的，都算最初那位许嬷嬷 ──
# steps：四步引导各一对 (开场, 过关)；finale 走完那句；skip 跳过引导时的反应；old 年纪大了的提醒
MAMAS = {
    'xu': dict(name='许嬷嬷', arrive='凑上前来', steps=[
        ('「小主头一日进宫，先别急着往养心殿跑。规矩没学会，见了皇上也是白见。去内务府挑个贴身的人，往后有些跑腿的事，还得靠她。」', '「像个样子了。」'),
        ('「今日去景仁宫请个安，皇后娘娘瞧着和气，规矩却不能少。得空再练一门才艺，御花园也去走走，散散心。」', '「老奴多嘴一句：宫里送来的吃食，入口前多看一眼。」'),
        ('「串串门，跟人处熟络些；写封信，宫里书信往来都是有规矩的。邸报也该看看，宫里出了什么事，一目了然。」', '「多个照应，总比孤零零一个人强。」'),
        ('「老奴在这宫里三十年，见过比小主聪明的，也见过比小主得宠的。活到最后的，都是沉得住气的。去安插个眼线，或是清查一下宫人，学着防备些。」', '「往后的路，小主自己走吧。有事只管来找老奴。」')],
        finale='「往后的路，小主自己走吧。有事只管来找老奴。」',
        skip='福了福身：「小主既有主意，老奴便不多嘴了，有事只管来找老奴。」',
        old='「近来总觉得精神短了，小主往后多静养些。」'),
    'qian': dict(name='钱嬷嬷', arrive='拨着手里的算盘珠子走了过来', steps=[
        ('「小主头回进宫，先别急着出门。宫里样样要银子，样样也靠人手。去内务府挑个宫人，赐个名，这笔钱花得值。」', '「这就对了，会算账的人才活得长。」'),
        ('「去景仁宫请个安，不要钱的礼数最划算。再练门才艺、去御花园逛逛，都是不花本钱的买卖。」', '「还有一句：吃食入口前先看一眼，银子可以省，这个不能省。」'),
        ('「串串门是攒人情，写封信是递人情，邸报是看行情。三样都做做，往后用得着。」', '「人情就是本钱，攒下了不吃亏。」'),
        ('「眼线不便宜，可买个消息比买颗珍珠值。安插一个，或是把身边的人清点清点，别叫银子打了水漂。」', '「余下的账，小主自己拨吧。」')],
        finale='「往后的账，小主自己拨吧。有事再来寻我。」',
        skip='把算盘往怀里一揣：「小主心里有数，我就不多嘴了。」',
        old='「近来气色不比从前，小主少操点心。银子花不完，身子可只有一个。」'),
    'jiang': dict(name='姜嬷嬷', arrive='板着脸走了进来', steps=[
        ('「入宫头一日，先学规矩，不要东张西望。去内务府挑个宫人，赐个名字，主仆名分要立得清楚。」', '「勉强过得去。」'),
        ('「晨省不得缺席，景仁宫请安，一日不可误。才艺要练，园子里走动也要有仪态。」', '「再记一条：入口的东西，必先验过。切记。」'),
        ('「同辈之间要有往来，但不可失了分寸。串门要有礼数，信要写得端正，邸报须每日过目。」', '「礼数周全，旁人便挑不出你的错。」'),
        ('「宫里并非个个是好人。安插眼线也好，清查宫人也好，要早做打算，不要等出了事才后悔。」', '「我能教的，也就这些了。」')],
        finale='「往后的路，小主自己走。「规矩」二字，不可忘。」',
        skip='紧抿着嘴，福了一福：「小主既然不要人提点，老身告退。」',
        old='「小主年岁渐长，不可再逞强，须多静养。」'),
    'su': dict(name='苏嬷嬷', arrive='笑眯眯地迎了上来', steps=[
        ('「哎哟，小主可算到了，路上累着了吧？先别忙别的，去内务府挑个贴心的宫人，往后有个能说话的人，心里也踏实些。」', '「好，好，这就像个家了。」'),
        ('「明儿一早去景仁宫给皇后娘娘请个安，不用怕，娘娘面善。再练练才艺，到御花园透透气，别憋着。」', '「还有啊，宫里送来的吃的，多看一眼再入口，嬷嬷是怕你吃亏。」'),
        ('「该走动走动啦，跟姐妹们串串门说说话，写封信回家报个平安，邸报也翻翻，知道宫里近来的事。」', '「多几个熟人，夜里也睡得安稳。」'),
        ('「嬷嬷再多嘴一句：宫里人心难测。找个信得过的人当眼线，或者把身边的人查一查，防着点总没错。」', '「往后的日子，嬷嬷就不絮叨了。」')],
        finale='「往后的路，小主自己走，有事只管来找嬷嬷，嬷嬷在呢。」',
        skip='拍了拍你的手：「小主主意大，嬷嬷放心。要用着嬷嬷，只管开口。」',
        old='「小主，近来看着精神不如从前，可得多歇着，别硬撑。」'),
    'hu': dict(name='胡嬷嬷', arrive='叉着腰走了过来', steps=[
        ('「小主，别愣着，进了宫就得有人使唤。去内务府挑个宫人，赐个名，赶紧的，往后跑腿全靠她。」', '「成了！有那么点样子。」'),
        ('「景仁宫请安，别睡过头；才艺练一练，御花园逛一逛，有精神才有盼头。」', '「还有，宫里的吃食别乱入口，吃了亏可没处说理！」'),
        ('「串门、写信、看邸报，三样都得来。光窝在屋里，谁认得你？」', '「这就对了，多个朋友多条路。」'),
        ('「听我一句，防人之心不可无。找个眼线，或者把身边的人筛一遍，别当冤大头。」', '「得，该教的都教了。」')],
        finale='「往后的路自己闯！有事儿，嘴一张就行。」',
        skip='挥了挥手：「行，小主有主意，我不啰嗦。」',
        old='「小主近来气色差了，别逞强，该歇就歇着。」'),
    'mo': dict(name='莫嬷嬷', arrive='悄无声息地站到了你身后', steps=[
        ('「去内务府，挑个人。往后你会用得着。」', '「不错。」'),
        ('「景仁宫，请安。才艺，练着。御花园，走走。」', '「吃食，入口前，先看一眼。」'),
        ('「串门，写信，看邸报。人心，都在里头。」', '「记住，你说的话，总有人听着。」'),
        ('「安个眼线，或清查身边的人。耳朵，比眼睛管用。」', '「余下的，你自己看。」')],
        finale='「路在你脚下。需要时，我在。」',
        skip='看了你一眼，点点头，不再说话。',
        old='「近来，身子沉了。歇着吧。」'),
}
DEFAULT_MAMA = 'xu'


def mama_of(c):
    return MAMAS.get((c['guide_mama'] if c else '') or DEFAULT_MAMA, MAMAS[DEFAULT_MAMA])


def mama_say(cid, text, kind='info'):
    """嬷嬷开口的通知：名字跟着这位角色的嬷嬷走"""
    c = get_consort(cid)
    notify(cid, f"{mama_of(c)['name']}：{text}", kind)


def guide_start(cid):
    key = random.SystemRandom().choice(list(MAMAS))   # 不走全局 random，别的随机逻辑（和测试里的 mock）互不影响
    run("UPDATE consorts SET guide_step=0, guide_progress='[]', guide_tips='[]', guide_mama=? WHERE id=?", (key, cid))
    m = MAMAS[key]
    notify(cid, f"{m['name']}{m['arrive']}：{m['steps'][0][0]}", 'info')

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
    m = mama_of(c)
    line = m['steps'][new_step][0] if new_step < len(GUIDE_STEPS) else m['finale']
    notify(cid, f"{m['name']}{m['steps'][c['guide_step']][1]}银子 +{GUIDE_REWARD} 两。{line}", 'good')

def guide_view(c):
    if not (0 <= c['guide_step'] < len(GUIDE_STEPS)): return None
    step = GUIDE_STEPS[c['guide_step']]
    try: progress = set(json.loads(c['guide_progress'] or '[]'))
    except ValueError: progress = set()
    checklist = [(' / '.join(REQ_LABELS[k] for k in sorted(req)), bool(progress & req)) for req in step['reqs']]
    m = mama_of(c)
    return dict(title=step['title'], teach=step['teach'], open_line=m['steps'][c['guide_step']][0], name=m['name'], checklist=checklist)

def guide_tip(cid, key, line):
    c = get_consort(cid)
    if not c or not c['user_id']: return
    try: seen = json.loads(c['guide_tips'] or '[]')
    except ValueError: seen = []
    if key in seen: return
    run("UPDATE consorts SET guide_tips=? WHERE id=?", (json.dumps(seen + [key], ensure_ascii=False), cid))
    notify(cid, f"{mama_of(c)['name']}：{line}", 'info')

# ── 场景（带选择的小剧情）─────────────────────────────────────────────────────
# 每个选项：stat 为空=必成；否则 属性值 + 随机 0~40 ≥ dc 算成（dc 70 时属性 50 约五成）。
# win/lose 里的键：favor 圣宠 / trust 信任 / virtue 德行 / health 体质 / appearance 容貌 /
# talent 才艺 / silver 银子 / seek 今晚翻牌加成 / huafei 华妃对你的好感

SCENE_ROLL = 40

SCENES = {
    'garden_emperor': dict(place='御花园', text='杏花树下，你一抬头，正撞见皇上负手而立，身边只跟着御前总管。皇上也看见了你。', opts=[
        dict(text='借眼前的景致吟两句诗', stat='talent', dc=70,
             win=dict(favor=18, seek=15), win_text='皇上接了下半句，笑说你是个妙人。',
             lose=dict(favor=3), lose_text='诗吟到一半卡了壳，皇上倒也没说什么，只点了点头。'),
        dict(text='规规矩矩行礼问安', stat=None,
             win=dict(favor=8), win_text='皇上问了几句起居，便往前走了。'),
        dict(text='折一枝杏花奉上', stat='appearance', dc=72,
             win=dict(favor=15, seek=20), win_text='皇上接过花，多看了你两眼。',
             lose=dict(favor=-3, virtue=-1), lose_text='御前总管轻咳一声：「小主，御花园的花可折不得。」'),
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
             win=dict(), win_text='御前总管朝你感激地点了点头。'),
        dict(text='软语宽慰，替皇上揉一揉额角', stat='appearance', dc=75,
             win=dict(favor=15, seek=10), win_text='皇上的脸色慢慢缓和下来，留你坐了一会儿。',
             lose=dict(favor=-8), lose_text='「朕说了不见人！」你被赶了出来。'),
        dict(text='劝皇上以龙体为重', stat='virtue', dc=75,
             win=dict(favor=6, trust=8), win_text='皇上叹了口气：「满宫里，也就你还敢说这话。」',
             lose=dict(favor=-8), lose_text='皇上冷冷看你一眼：「后宫不得干政。」'),
    ]),
    # ── 2026-09-29 扩充：出门走动时撞见皇上（do_garden 的 emperor 事件从 EMPEROR_SCENES 里挑） ──
    'lake_emperor': dict(place='太液池', text='暮色四合，太液池边只剩皇上一个人坐在石栏上钓鱼。他听见脚步声，回头看了你一眼。', opts=[
        dict(text='远远行礼，转身便走', stat=None,
             win=dict(favor=5), win_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='安静坐在一旁陪着', stat='virtue', dc=65,
             win=dict(favor=12, seek=15), win_text='两人坐了一炷香，皇上钓到一条鱼，难得笑了。',
             lose=dict(favor=2), lose_text='皇上钓了一刻钟，没钓到。他起身走了，你也不好再留。'),
        dict(text='说几句俏皮话逗他开心', stat='appearance', dc=72,
             win=dict(favor=18, seek=8), win_text='皇上捏了捏你的脸：「就你话多。」但嘴角是翘的。',
             lose=dict(favor=-5, trust=-2), lose_text='皇上淡淡道：「朕钓鱼，不是来听戏的。」你讪讪闭嘴。'),
    ]),
    'street_emperor': dict(place='长街', text='天擦黑了，你从御花园回来得晚，长街上迎面撞上皇上銮驾。皇上掀开轿帘，似乎认出了你。', opts=[
        dict(text='跪在路边，恭送圣驾', stat=None,
             win=dict(favor=6), win_text='皇上没说什么，銮驾过去了。'),
        dict(text='大胆抬头，迎视圣颜', stat='appearance', dc=75,
             win=dict(favor=20, seek=15), win_text='皇上怔了一下，随即笑道：「这么晚了，怎么一个人？」',
             lose=dict(favor=-8, virtue=-2), lose_text='皇上沉下脸：「没规矩。」轿帘放下了。'),
        dict(text='「夜深露重，皇上保重龙体。」', stat='virtue', dc=65,
             win=dict(favor=10, trust=5, seek=8), win_text='皇上「嗯」了一声，语气软了几分。',
             lose=dict(favor=2), lose_text='皇上「嗯」了一声，銮驾过去了。'),
    ]),
    'shoukang_emperor': dict(place='寿康宫', text='你顺路去寿康宫给太后送燕窝，出来时正撞见皇上进门。太后笑着问皇上：「怎么来得这样巧？」', opts=[
        dict(text='恭敬行礼，退到一旁', stat=None,
             win=dict(favor=6, trust=2), win_text='太后留你用饭，皇上多看了你两眼。'),
        dict(text='笑着说「嫔妾是来替皇上尽孝的」', stat='scheme', dc=70,
             win=dict(favor=15, trust=8), win_text='太后笑得合不拢嘴：「这孩子，会说话。」皇上也笑了。',
             lose=dict(favor=-5, trust=-3), lose_text='皇上淡淡道：「不必。」太后也没接话。你意识到自己弄巧成拙。'),
        dict(text='低头不语，面露羞怯', stat='appearance', dc=68,
             win=dict(favor=12, seek=12), win_text='太后看在眼里，晚上跟皇上提了你。',
             lose=dict(favor=3), lose_text='皇上没注意到你，径直进去了。'),
    ]),
    # ── 送汤羹时皇上心情平和，偶尔会留你（do_seek） ──
    'yangxin_emperor': dict(place='养心殿', text='你去养心殿送汤羹，正逢皇上批完折子揉眉心。御前总管悄悄给你打帘子，示意你进去。', opts=[
        dict(text='放下东西，行礼告退', stat=None,
             win=dict(favor=5), win_text='皇上点了点头，继续看折子。御前总管送你出来时低声道：「小主有心了。」'),
        dict(text='主动上前替皇上揉肩', stat='scheme', dc=68,
             win=dict(favor=15, seek=10), win_text='皇上闭上眼，由你按了一刻钟。走时他道：「明儿还来。」',
             lose=dict(favor=-5, trust=-3), lose_text='皇上睁开眼，淡淡道：「不必了。」你意识到自己越了界。'),
        dict(text='轻声念一段祈福的经文', stat='virtue', dc=70,
             win=dict(favor=12, trust=5), win_text='皇上听完，神色舒展了些：「难为你有心。」',
             lose=dict(favor=-3, virtue=-1), lose_text='皇上皱了皱眉：「朕这里不需要念经。」你讪讪退下。'),
    ]),
    # ── 撞见 NPC 妃嫔。npc= 是这个场景要谁在场（不在或进了冷宫就不出这个场景），
    #    效果里写 NPC 的 npc_key 表示她对你的好感（见 apply_effects），不再借用皇上的「信任」 ──
    'yikun_huafei': dict(place='翊坤宫', npc='huafei', text='华妃宫里的人把你请去了翊坤宫。她斜倚在榻上，手里把玩着一只赤金护甲，似笑非笑地看着你：「妹妹近来气色不错，想必是圣眷正隆？」', opts=[
        dict(text='「姐姐说笑了，嫔妾不过是寻常度日。」', stat=None,
             win=dict(virtue=1), win_text='华妃哼了一声，没再说什么。'),
        dict(text='「姐姐才是真正的好气色，这护甲配姐姐正好。」', stat='scheme', dc=68,
             win=dict(huafei=8), win_text='华妃哼了一声，倒没为难你。',
             lose=dict(huafei=-5), lose_text='华妃冷笑：「油嘴滑舌，跟你那出身一样。」左右宫女都低下了头。'),
        dict(text='「嫔妾气色好不好，与姐姐何干？」', stat='virtue', dc=75,
             win=dict(virtue=1, huafei=10), win_text='华妃盯了你半晌，忽然笑了：「有脾气。本宫喜欢有脾气的。」',
             lose=dict(health=-10, huafei=-15), lose_text='华妃把茶盏重重搁下：「给本宫跪下！」你在翊坤宫跪了整整一个时辰。'),
    ]),
    'yanqing_duanfei': dict(place='延庆殿', npc='duanfei', text='你路过延庆殿，听见里面传来咳嗽声。掌事姑姑悄悄告诉你：「端妃娘娘又犯了旧疾，已经三日没出门了。」', opts=[
        dict(text='留下补品，转身便走', stat=None,
             win=dict(virtue=1), win_text='掌事姑姑收了东西，代端妃道了谢。'),
        dict(text='进去探望，亲自侍药', stat='virtue', dc=68,
             win=dict(virtue=2, duanfei=10), win_text='端妃握着你的手，低声道：「这宫里，难得有个真心人。」',
             lose=dict(), lose_text='端妃摆了摆手，没让你近身。掌事姑姑送你出来时叹了口气。'),
        dict(text='向掌事姑姑打听端妃的病情和过往', stat='scheme', dc=72,
             win=dict(scheme=2), win_text='掌事姑姑说了许多。你才知道端妃当年也曾盛宠一时。',
             lose=dict(virtue=-2, duanfei=-8), lose_text='掌事姑姑脸色一变：「小主，这些话不是该问的。」你意识到自己犯了忌讳。'),
    ]),
    'street_qifei': dict(place='长街', npc='qifei', text='长街上，齐妃带着小阿哥迎面走来。小阿哥手里拿着风筝，齐妃正叮嘱他小心。', opts=[
        dict(text='行礼问安后，避让到一旁', stat=None,
             win=dict(virtue=1), win_text='齐妃点点头，牵着小阿哥走了。'),
        dict(text='夸小阿哥聪明伶俐', stat='virtue', dc=65,
             win=dict(virtue=1, qifei=6), win_text='齐妃笑得合不拢嘴：「你这人倒是实在。」',
             lose=dict(qifei=-3), lose_text='齐妃警惕地看了你一眼，牵着小阿哥快步走了。'),
        dict(text='主动提出陪小阿哥放风筝', stat='scheme', dc=70,
             win=dict(qifei=10), win_text='小阿哥高兴得不得了，齐妃也放下了戒心。',
             lose=dict(qifei=-10), lose_text='齐妃脸色一沉：「本宫的儿子，不劳外人费心。」说罢拂袖而去。'),
    ]),
    'garden_jingpin': dict(place='御花园', npc='jingpin', text='御花园里，敬嫔正蹲在花圃边修剪一株月季。她抬头看见你，温和地笑了笑。', opts=[
        dict(text='问安后，在一旁静静看花', stat=None,
             win=dict(virtue=1), win_text='敬嫔剪完花，跟你聊了几句天气。'),
        dict(text='上前帮忙修剪', stat='virtue', dc=65,
             win=dict(virtue=2, jingpin=6), win_text='敬嫔教你怎样剪枝，两人聊了一下午。',
             lose=dict(jingpin=-3), lose_text='你剪坏了一枝花。敬嫔没说什么，但笑容淡了些。'),
        dict(text='问敬嫔宫里的近况', stat='scheme', dc=68,
             win=dict(scheme=1, jingpin=4), win_text='敬嫔叹了口气，说了些你不知道的内情。',
             lose=dict(jingpin=-6), lose_text='敬嫔摇头道：「这些事，不该你问。」你意识到她虽温和，却并不糊涂。'),
    ]),
    'lake_caoguiren': dict(place='太液池', npc='caoguiren', text='太液池边，曹贵人抱着小公主在散步。她看见你，笑着打招呼：「妹妹也来透气？」', opts=[
        dict(text='点头致意，转身便走', stat=None,
             win=dict(virtue=1), win_text='曹贵人笑了笑，继续散步。'),
        dict(text='夸公主可爱', stat='virtue', dc=65,
             win=dict(virtue=1, caoguiren=4), win_text='曹贵人笑得真诚了几分：「妹妹是个喜欢孩子的人。」',
             lose=dict(), lose_text='曹贵人淡淡一笑，抱着公主走开了。'),
        dict(text='暗示华妃近日对曹贵人颇有微词', stat='scheme', dc=75,
             win=dict(caoguiren=12), win_text='曹贵人脸色微变，低声道：「妹妹的好意，我记下了。」',
             lose=dict(caoguiren=-8, huafei=-5), lose_text='曹贵人脸色一沉：「妹妹这话，若是让华妃娘娘听见……」她抱着公主快步离去。'),
    ]),
    'garden_lipin': dict(place='御花园', npc='lipin', text='御花园里，丽嫔正对着池水照影，嘴里念叨着新得的珠花。她看见你，扬声道：「妹妹来看看，这花好不好看？」', opts=[
        dict(text='「好看。」', stat=None,
             win=dict(), win_text='丽嫔满意地点点头，继续照她的影子。'),
        dict(text='「这花配姐姐正好，只是不如姐姐本人。」', stat='scheme', dc=65,
             win=dict(lipin=6), win_text='丽嫔笑得花枝乱颤：「就你嘴甜！」',
             lose=dict(), lose_text='丽嫔撇撇嘴：「算你有眼光。」转身走了。'),
        dict(text='「嫔妾还有事，先告辞了。」', stat='virtue', dc=60,
             win=dict(virtue=1), win_text='丽嫔也没在意，继续照她的影子。',
             lose=dict(lipin=-6), lose_text='丽嫔脸色一沉：「怎么，本宫配不上跟你说话？」你不得不赔笑解释。'),
    ]),
    # ── 请安时撞见（do_greet 从 GREET_SCENES 里挑） ──
    'jingren_empress': dict(place='景仁宫', npc='huanghou', text='请安散了，皇后单留你说话。她亲手给你斟了一盏茶，温言道：「本宫听说你近来抄经祈福，倒是个虔心的。」', opts=[
        dict(text='「谢皇后娘娘赐茶。」', stat=None,
             win=dict(virtue=1), win_text='皇后点点头，让你退下了。'),
        dict(text='「嫔妾是为皇上和皇后娘娘祈福。」', stat='virtue', dc=65,
             win=dict(virtue=2, huanghou=10), win_text='皇后欣慰地点头：「难为你有心了。」',
             lose=dict(virtue=-1), lose_text='皇后笑了笑，没接话。你总觉得那笑容意味深长。'),
        dict(text='「嫔妾愚钝，不如姐姐们懂事，只能笨鸟先飞。」', stat='scheme', dc=70,
             win=dict(virtue=1, huanghou=6), win_text='皇后拍拍你的手：「你这孩子，就是太谦了。」',
             lose=dict(huanghou=-6), lose_text='皇后淡淡道：「本宫倒觉得你聪明得很。」你后背一凉。'),
    ]),
    'jingren_xinchangzai': dict(place='景仁宫', npc='xinchangzai', text='请安出来，景仁宫廊下，欣常在正嗑瓜子。她看见你，招招手：「过来，跟你说件事。」', opts=[
        dict(text='「改日再聊。」', stat=None,
             win=dict(virtue=1), win_text='欣常在撇撇嘴，继续嗑她的瓜子。'),
        dict(text='过去听她说', stat='scheme', dc=65,
             win=dict(scheme=1, xinchangzai=6), win_text='欣常在压低声音，把各宫这几日的动静数了一遍，你听出不少门道。',
             lose=dict(), lose_text='欣常在说了几句闲话，没什么要紧的。'),
        dict(text='「欣姐姐有什么好消息？」', stat='virtue', dc=60,
             win=dict(xinchangzai=4), win_text='欣常在笑道：「好消息没有，坏消息倒有一堆。」',
             lose=dict(xinchangzai=-4), lose_text='欣常在白了你一眼：「谁跟你姐姐妹妹的。」'),
    ]),
}

EMPEROR_SCENES = ['garden_emperor', 'lake_emperor', 'street_emperor', 'shoukang_emperor']   # 出门走动撞见皇上

# ── 奇遇：逛御花园、请安路上偶遇的小事，有选择、有后果（2026-10-05 新增）──────────────────
# 全是日常小事，奖惩都不大：银子几十两、属性 +1~+3、偶尔一点圣宠；靠属性加运气判定，和别的场景一样
ADVENTURE_SCENES = {
    'adv_lost_maid': dict(place='御花园·假山后', text='假山后头蹲着个小宫女，抽抽搭搭地哭。一问，是替主子收着的一只玉镯不知丢在了哪儿，找不到就要挨板子。', opts=[
        dict(text='陪她一起沿路找', stat='virtue', dc=55,
             win=dict(virtue=2, silver=20), win_text='你们在花丛底下摸到了镯子。她千恩万谢，硬把攒下的二十两塞给你，说是主子赏的谢礼。',
             lose=dict(virtue=1), lose_text='找了一下午，镯子没找着。她红着眼谢了你，说自己再想想办法。'),
        dict(text='给她几两银子，让她自己去赔', stat=None,
             win=dict(silver=-15, virtue=2), win_text='她接过银子磕了个头跑了。你想，这十五两花得不冤。'),
        dict(text='宫里的事管不过来，装作没看见', stat=None,
             win=dict(scheme=1), win_text='你绕开了假山。宫里的闲事，不是谁都沾得起，你心里暗暗记下这个道理。'),
    ]),
    'adv_old_plum': dict(place='御花园·老梅下', text='一棵老梅树下，树干上刻着几行褪了色的旧诗，不知是哪位前朝娘娘留下的。', opts=[
        dict(text='蹲下来细读，抄在帕子上', stat='talent', dc=55,
             win=dict(talent=2), win_text='你琢磨了半天，竟读出了几分意境，回去照着誊了一遍，笔下也长进了些。',
             lose=dict(talent=1), lose_text='字迹太模糊，你只辨出了半阙，不过也算有所得。'),
        dict(text='和上一首', stat='talent', dc=72,
             win=dict(talent=3, favor=5), win_text='你随口和了一首，正好被路过的老嬷嬷听见，连声称好，没几天就传到了皇上耳朵里。',
             lose=dict(), lose_text='憋了半天，只凑出两句，自己都觉得不成样子，悄悄把帕子收了起来。'),
        dict(text='折一枝梅花带回去插瓶', stat=None,
             win=dict(appearance=1), win_text='屋里添了一抹清香，连你自己的气色都好了些。'),
    ]),
    'adv_koi_bet': dict(place='御花园·千鲤池', text='池边几个小太监围着一尾红鲤指指点点，见你过来，笑嘻嘻地凑上前：「小主要不要押一注？看这条能不能抢到最大那块饵。」', opts=[
        dict(text='押二十两，赌那条红鲤', stat='scheme', dc=62,
             win=dict(silver=40), win_text='红鲤一个翻身抢到了饵！小太监们哄笑着赔了你四十两。',
             lose=dict(silver=-20), lose_text='一条黑鲤从底下蹿了出来。你的二十两打了水漂，小太监们笑得前仰后合。'),
        dict(text='笑着说宫里不许赌钱，劝他们散了', stat='virtue', dc=60,
             win=dict(virtue=2), win_text='几个小太监讪讪地散了，其中一个偷偷冲你作了个揖。',
             lose=dict(), lose_text='他们嘴上应着，等你走远了，又凑到一处。'),
        dict(text='站在一旁看热闹', stat=None,
             win=dict(), win_text='你看了一会儿，红鲤果然没抢到饵。幸亏没押。'),
    ]),
    'adv_eavesdrop': dict(place='御花园·凉亭外', text='凉亭里两个宫女压低了声音说话，你隐约听见「那一位」「库房」「对不上账」几个字。', opts=[
        dict(text='悄悄靠近，多听几句', stat='scheme', dc=66,
             win=dict(scheme=2, silver=15), win_text='原来是内务府有人私吞了一批物件。你不动声色地记在心里，回头又听说有人为这事得了赏，你顺势也沾了点光。',
             lose=dict(virtue=-1), lose_text='脚下踩响了枯枝，两个宫女惊慌地看向你。你只得讪讪走开，窘得耳根都红了。'),
        dict(text='故意咳一声，让她们知道有人来了', stat=None,
             win=dict(virtue=1), win_text='两个宫女一惊，赶紧散了。你没听见什么，也没惹什么。'),
        dict(text='转身离开', stat=None,
             win=dict(), win_text='宫里的话，不该听的不听。你若无其事地走远了。'),
    ]),
    'adv_hurt_sparrow': dict(place='御花园·竹丛边', text='竹丛底下有只雀儿，翅膀耷拉着，扑腾了几下飞不起来。', opts=[
        dict(text='小心捧回宫里养伤', stat=None,
             win=dict(virtue=2, health=1), win_text='你拿帕子垫着，一点点喂它水和米。几天后它能飞了，临走前在窗台上啁啾了两声。'),
        dict(text='交给路过的小太监，让他去处置', stat=None,
             win=dict(virtue=1), win_text='小太监应了一声，捧着雀儿去了。你想，总比丢在这里强。'),
        dict(text='不去管它', stat=None,
             win=dict(), win_text='你在池边站了站，没有回头。'),
    ]),
    'adv_kite': dict(place='御花园·空地', text='几个小宫女在放风筝，线断了，风筝正挂在一棵歪脖子树的高枝上，一个个急得直跺脚。', opts=[
        dict(text='撩起裙摆，亲自攀上去够', stat='health', dc=65,
             win=dict(virtue=1, appearance=1, silver=15), win_text='你稳稳够到了风筝。小宫女们笑成一团，其中一个红着脸塞给你一小包糖。回宫前，有人悄悄在你屋里放了十五两银子，说是宫人们凑的谢礼。',
             lose=dict(health=-2), lose_text='脚下一滑，你蹭破了手心。风筝倒是被风吹了下来，小宫女们一边道谢一边慌忙替你找药。'),
        dict(text='让身边的宫人找根长竿去够', stat=None,
             win=dict(), win_text='宫人折腾了半天，总算把风筝勾了下来。小宫女们行礼道谢，欢天喜地地跑远了。'),
        dict(text='不理会，径直走过', stat=None,
             win=dict(), win_text='你走过去，身后传来小宫女们的叹气声。'),
    ]),
    'adv_pipa': dict(place='御花园·水榭外', text='远处水榭里传来一阵琵琶声，弹得断断续续，像是有人在苦练一支新曲子。', opts=[
        dict(text='循声过去，坐下来静静听完', stat=None,
             win=dict(talent=1), win_text='那姑娘羞怯地向你一礼，说请小主指点。你虽没说什么，却也听出了几处门道。'),
        dict(text='自告奋勇，上手帮她纠正指法', stat='talent', dc=62,
             win=dict(talent=2, favor=3), win_text='你点出了两处毛病，她一试，果然顺畅。这事传开，都说你「是个懂行的」。',
             lose=dict(talent=1, virtue=-1), lose_text='你说得头头是道，她一试却更乱了。你讪讪地想，下回还是别多嘴。'),
        dict(text='悄悄走开，不去打扰', stat=None,
             win=dict(), win_text='琵琶声渐渐落在身后。'),
    ]),
    'adv_hall_gossip': dict(place='礼仪堂·廊下', text='请安出来，廊下几位年长的嬷嬷正聚在一起择菜说闲话，见你过来，其中一个招手：「小主来坐坐？」', opts=[
        dict(text='坐下来，请教宫里的老规矩', stat=None,
             win=dict(virtue=2), win_text='几位嬷嬷见你谦和，你一言我一语讲了许多从前的规矩，句句都是用血泪换来的。'),
        dict(text='趁机打听各宫近来的动静', stat='scheme', dc=62,
             win=dict(scheme=2), win_text='嬷嬷们只当是闲聊，却把各宫的脾性、谁跟谁近谁跟谁远都漏了个七七八八。',
             lose=dict(virtue=-1), lose_text='你问得太急，嬷嬷们互相使了个眼色，话头一下子淡了：「小主还是少打听的好。」'),
        dict(text='笑着应一声，不坐下', stat=None,
             win=dict(), win_text='你屈膝行了个礼便走了。嬷嬷们低头继续择菜。'),
    ]),
    'adv_old_book': dict(place='礼仪堂·旧书柜', text='礼仪堂角落里堆着一柜子旧书，其中一本被虫蛀得厉害，页缝里夹着一张泛黄的纸，上头密密麻麻写着前人的批注。', opts=[
        dict(text='借回去细细研读', stat='scheme', dc=62,
             win=dict(scheme=2, talent=1), win_text='批注的人显然是个洞察人心的老手。你读了三夜，隐约摸到了几分门道。',
             lose=dict(scheme=1), lose_text='批注太过晦涩，你只读懂了皮毛，但也算有收获。'),
        dict(text='交还管事的姑姑', stat=None,
             win=dict(virtue=2, silver=20), win_text='姑姑一看，直说这是前朝留下的东西，赏了你二十两，夸你「是个守规矩的」。'),
        dict(text='原样放回去', stat=None,
             win=dict(), win_text='你把书塞了回去，不过是旧书而已。'),
    ]),
    'adv_rain_doctor': dict(place='回宫路上·躲雨亭', text='半路下起雨来，你跑到亭子里避雨，里头已有个须发花白的老太医，正抱着药箱躲雨，衣角全湿了。', opts=[
        dict(text='把伞让给他，自己淋着回去', stat=None,
             win=dict(virtue=2, health=-1, trust=2), win_text='老太医推辞不过，临走前留下一句：「小主心善，老夫记着了。」你淋了一身雨，却觉得值。'),
        dict(text='趁机向他请教养生的法子', stat=None,
             win=dict(health=3), win_text='老太医讲了几条冬补夏防的法子，句句简单实用。你回去照做，身子骨渐渐硬朗了些。'),
        dict(text='请他顺带替你把个脉', stat='health', dc=55,
             win=dict(health=4), win_text='老太医搭了会儿脉，开了几味不值钱的药引，说你只是有点气虚，调养几日便好。',
             lose=dict(health=1), lose_text='老太医说你脉象平稳，没什么大碍，叮嘱你好好吃饭。'),
    ]),
    'adv_embroidery': dict(place='宫道旁·绣房', text='路过绣房，里头一群绣娘正为年节赶制新衣，见你探头，一个年长的笑着招呼：「小主要不要进来看看？」', opts=[
        dict(text='进去请教针法', stat=None,
             win=dict(talent=1), win_text='年长的绣娘手把手教了你一个简单的针脚，你练了几遍，已像模像样。'),
        dict(text='帮着打下手，穿针引线', stat=None,
             win=dict(virtue=1, silver=15), win_text='忙了半个时辰，绣娘们感念你的好意，塞了你十五两赏钱，说是绣房的「辛苦钱」。'),
        dict(text='讨几块边角料带回去', stat=None,
             win=dict(appearance=1), win_text='你挑了块花色最好看的碎缎，回去做了条发带，戴上很衬你。'),
    ]),
}
SCENES.update(ADVENTURE_SCENES)
ADVENTURE_GARDEN = ['adv_lost_maid', 'adv_old_plum', 'adv_koi_bet', 'adv_eavesdrop', 'adv_hurt_sparrow', 'adv_kite', 'adv_pipa']
ADVENTURE_ROAD = ['adv_hall_gossip', 'adv_old_book', 'adv_rain_doctor', 'adv_embroidery']   # 请安路上、回宫路上
ADVENTURE_ROAD_CHANCE = 0.25      # 请安之后有这么大概率碰上一件
ADVENTURE_GARDEN_WEIGHT = 26      # 逛御花园时，奇遇在各种偶遇里占的权重
NPC_SCENES = ['garden_huafei', 'yikun_huafei', 'yanqing_duanfei', 'street_qifei', 'garden_jingpin', 'lake_caoguiren', 'garden_lipin']
GREET_SCENES = ['greet_huafei', 'jingren_empress', 'jingren_xinchangzai']                 # 请安时撞见
SCENES['garden_huafei']['npc'] = SCENES['greet_huafei']['npc'] = 'huafei'

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
    # ── 2026-09-29 扩充 ──
    dict(ask='「今日前朝大臣们又吵了一架，你说朕该听谁的？」', opts=[
        dict(text='体谅：「皇上圣明，自有决断。嫔妾不懂朝政，只知皇上心里装着天下。」', stat='virtue', dc=65,
             win=dict(favor=8, trust=4), win_text='皇上笑了笑：「就你懂事。」', lose=dict(favor=2), lose_text='皇上「嗯」了一声，似乎没听进去。'),
        dict(text='讨巧：「皇上听谁的，嫔妾不管。嫔妾只管皇上今晚来不来。」', stat='appearance', dc=70,
             win=dict(favor=18), win_text='皇上捏了捏你的脸：「就你嘴甜。」', lose=dict(favor=-4, trust=-2), lose_text='皇上淡淡道：「油嘴滑舌。」'),
        dict(text='直言：「吵得最凶的那个，未必是最有理的那个。」', stat='scheme', dc=72,
             win=dict(favor=2, trust=10), win_text='皇上沉默片刻：「难得有人跟朕说实话。」', lose=dict(favor=-10, trust=3), lose_text='皇上沉下脸来。可这话，他记住了。'),
    ]),
    dict(ask='「你若生了皇子，朕该高兴还是该忧心？」', opts=[
        dict(text='体谅：「皇上高兴，嫔妾就高兴。皇子是皇上的儿子，自然是喜事。」', stat='virtue', dc=68,
             win=dict(favor=10, trust=5), win_text='皇上点点头：「你这话说得妥当。」', lose=dict(favor=3), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「皇上若忧心，嫔妾就不生了。」', stat='appearance', dc=72,
             win=dict(favor=20), win_text='皇上大笑：「就你会说话！」', lose=dict(favor=-5, trust=-3), lose_text='皇上脸色一沉：「这话也说得出口？」'),
        dict(text='直言：「皇上若忧心，是心里有顾忌。可皇子是皇上的血脉，不该成为负担。」', stat='scheme', dc=75,
             win=dict(favor=5, trust=12), win_text='皇上长久地看着你：「你比朕想的明白。」', lose=dict(favor=-12, trust=5), lose_text='皇上沉下脸：「你懂什么？」但你看见他眼里有一丝动容。'),
    ]),
    dict(ask='「太后总觉得朕对你不够好，你说是不是？」', opts=[
        dict(text='体谅：「太后是心疼嫔妾。皇上对嫔妾好不好，嫔妾心里清楚。」', stat='virtue', dc=65,
             win=dict(favor=8, trust=6), win_text='皇上叹了口气：「难为你明白。」', lose=dict(favor=2), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「皇上对嫔妾好不好，太后说了不算，皇上说了也不算——嫔妾自己说了算。」', stat='appearance', dc=68,
             win=dict(favor=15), win_text='皇上笑了：「就你胆大。」', lose=dict(favor=-3, trust=-2), lose_text='皇上淡淡道：「你这话说得轻狂。」'),
        dict(text='直言：「太后是心疼皇上。皇上对嫔妾好不好不要紧，对天下好不好才要紧。」', stat='scheme', dc=70,
             win=dict(favor=3, trust=8), win_text='皇上怔了一下，随即点头：「你说得对。」', lose=dict(favor=-8, trust=4), lose_text='皇上沉下脸：「你这是在教训朕？」但他没有发怒。'),
    ]),
    dict(ask='「先帝在时，后宫比现在安分多了。你说朕是不是不如父皇？」', opts=[
        dict(text='体谅：「先帝仁慈，皇上英明。各有各的好处，嫔妾不敢妄议。」', stat='virtue', dc=70,
             win=dict(favor=10, trust=5), win_text='皇上点点头：「你这话说得中肯。」', lose=dict(favor=3), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「先帝是先帝，皇上是皇上。嫔妾只认皇上。」', stat='appearance', dc=72,
             win=dict(favor=18), win_text='皇上笑了：「就你会说话。」', lose=dict(favor=-5, trust=-3), lose_text='皇上淡淡道：「油嘴滑舌。」'),
        dict(text='直言：「先帝时安分，是因为先帝年长。等皇上到了先帝的年纪，未必不如。」', stat='scheme', dc=75,
             win=dict(favor=2, trust=10), win_text='皇上沉默良久：「你说得对。朕还年轻。」', lose=dict(favor=-10, trust=5), lose_text='皇上沉下脸：「你懂什么？」但他眼里有一丝动容。'),
    ]),
    dict(ask='「朕小时候，父皇从不抱朕。你说朕是不是不该学他？」', opts=[
        dict(text='体谅：「皇上心里有遗憾，所以想对皇子好。这是皇上仁慈。」', stat='virtue', dc=65,
             win=dict(favor=12, trust=6), win_text='皇上眼眶微红：「难为你懂朕。」', lose=dict(favor=3), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「皇上若不抱皇子，嫔妾就天天抱着皇子在皇上面前晃。」', stat='appearance', dc=68,
             win=dict(favor=15), win_text='皇上笑了：「就你闹腾。」', lose=dict(favor=-3, trust=-2), lose_text='皇上淡淡道：「没个正经。」'),
        dict(text='直言：「不该学先帝冷着皇子，也不该为了补偿而溺爱。皇上要做的是比先帝更好。」', stat='scheme', dc=70,
             win=dict(favor=3, trust=8), win_text='皇上点点头：「你说得对。」', lose=dict(favor=-8, trust=4), lose_text='皇上沉下脸：「你懂什么？」但他没有发怒。'),
    ]),
    dict(ask='「华妃近日越发骄纵了，你怎么看？」', opts=[
        dict(text='体谅：「华妃姐姐性子直，心里没有坏心思。皇上多担待些。」', stat='virtue', dc=68,
             win=dict(favor=8, trust=5), win_text='皇上叹了口气：「就你心善。」', lose=dict(favor=2), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「华妃姐姐再骄纵，也比不上皇上对嫔妾好。」', stat='appearance', dc=72,
             win=dict(favor=15), win_text='皇上笑了：「就你会说话。」', lose=dict(favor=-5, trust=-3), lose_text='皇上淡淡道：「朕问你华妃，你说朕做什么？」'),
        dict(text='直言：「华妃姐姐骄纵，是因为娘家显赫。皇上若真想管，该从她娘家入手。」', stat='scheme', dc=75,
             win=dict(favor=2, trust=12), win_text='皇上眼睛一亮：「你说得对。」', lose=dict(favor=-12, trust=5), lose_text='皇上沉下脸：「你懂什么？」但他记住了。'),
    ]),
    dict(ask='「皇后什么都好，就是太端着了。你不觉得吗？」', opts=[
        dict(text='体谅：「皇后娘娘是国母，端庄是应该的。皇上该体谅她。」', stat='virtue', dc=65,
             win=dict(favor=8, trust=4), win_text='皇上点点头：「你说得对。」', lose=dict(favor=2), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「皇后娘娘端着，嫔妾不端着。皇上喜欢哪个？」', stat='appearance', dc=70,
             win=dict(favor=18), win_text='皇上笑了：「就你嘴甜。」', lose=dict(favor=-4, trust=-2), lose_text='皇上淡淡道：「朕问你皇后，你说自己做什么？」'),
        dict(text='直言：「皇后娘娘端着，是心里有顾忌。皇上若想她放下架子，得先让她安心。」', stat='scheme', dc=72,
             win=dict(favor=3, trust=10), win_text='皇上沉默片刻：「你说得对。」', lose=dict(favor=-10, trust=4), lose_text='皇上沉下脸：「你懂什么？」但他没有发怒。'),
    ]),
    dict(ask='「今年入秋早，你说朕该多陪你还是多去前朝？」', opts=[
        dict(text='体谅：「皇上以国事为重。嫔妾这里，皇上什么时候来都好。」', stat='virtue', dc=60,
             win=dict(favor=10, trust=5), win_text='皇上点点头：「就你懂事。」', lose=dict(favor=3), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「皇上多陪嫔妾。前朝有大臣，嫔妾这里只有皇上。」', stat='appearance', dc=65,
             win=dict(favor=15), win_text='皇上笑了：「就你黏人。」', lose=dict(favor=-3, trust=-2), lose_text='皇上淡淡道：「不懂事。」'),
        dict(text='直言：「皇上该去前朝。嫔妾这里，什么时候来都在。」', stat='scheme', dc=68,
             win=dict(favor=2, trust=8), win_text='皇上点点头：「你说得对。」', lose=dict(favor=-5, trust=3), lose_text='皇上「嗯」了一声，没再说什么。'),
    ]),
    dict(ask='「敬嫔说你是个安分的，你觉得呢？」', opts=[
        dict(text='体谅：「敬嫔姐姐抬举嫔妾了。嫔妾只求安分守己，不给皇上添乱。」', stat='virtue', dc=65,
             win=dict(favor=8, trust=4), win_text='皇上点点头：「你这话说得妥当。」', lose=dict(favor=2), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「嫔妾安不安分，皇上说了算。」', stat='appearance', dc=70,
             win=dict(favor=18), win_text='皇上笑了：「就你嘴甜。」', lose=dict(favor=-4, trust=-2), lose_text='皇上淡淡道：「油嘴滑舌。」'),
        dict(text='直言：「嫔妾知道什么该做、什么不该做。但若有人欺到头上，嫔妾也不会忍着。」', stat='scheme', dc=72,
             win=dict(favor=2, trust=10), win_text='皇上眼睛一亮：「你说得对。」', lose=dict(favor=-8, trust=4), lose_text='皇上沉下脸：「你这是在威胁谁？」但他眼里有一丝欣赏。'),
    ]),
    dict(ask='「朕想废一条宫规，你说该废哪条？」', opts=[
        dict(text='体谅：「宫规是祖宗定的，嫔妾不敢妄议。皇上若觉得不妥，自有道理。」', stat='virtue', dc=70,
             win=dict(favor=8, trust=5), win_text='皇上点点头：「你这话说得中肯。」', lose=dict(favor=2), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「嫔妾不管宫规废不废，嫔妾只管皇上高不高兴。」', stat='appearance', dc=75,
             win=dict(favor=20), win_text='皇上笑了：「就你会说话。」', lose=dict(favor=-5, trust=-3), lose_text='皇上淡淡道：「朕问你正事，你说这个？」'),
        dict(text='直言：「后宫不得干政这条。不是要妃嫔干政，是让皇上能听见不同的声音。」', stat='scheme', dc=78,
             win=dict(favor=5, trust=12), win_text='皇上长久地看着你：「你比朕想的明白。」', lose=dict(favor=-12, trust=5), lose_text='皇上沉下脸：「你懂什么？」但他记住了。'),
    ]),
    dict(ask='「你家里前些日子递了折子上来，你说朕该准还是该驳？」', opts=[
        dict(text='体谅：「皇上圣明，自有决断。嫔妾不敢干预朝政。」', stat='virtue', dc=68,
             win=dict(favor=10, trust=5), win_text='皇上点点头：「你这话说得妥当。」', lose=dict(favor=3), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「皇上准不准，嫔妾不管。嫔妾只管皇上今晚来不来。」', stat='appearance', dc=72,
             win=dict(favor=18), win_text='皇上大笑：「就你会说话！」', lose=dict(favor=-5, trust=-3), lose_text='皇上脸色一沉：「这话也说得出口？」'),
        dict(text='直言：「皇上若准，是看在嫔妾的面子上；若驳，是秉公办事。嫔妾都认。」', stat='scheme', dc=75,
             win=dict(favor=2, trust=10), win_text='皇上点点头：「你这话说得明白。」', lose=dict(favor=-10, trust=5), lose_text='皇上沉下脸：「你这是在逼朕？」但他没有发怒。'),
    ]),
    dict(ask='「你若能许一个愿，想要什么？」', opts=[
        dict(text='体谅：「嫔妾只求皇上平安喜乐，天下太平。」', stat='virtue', dc=65,
             win=dict(favor=12, trust=6), win_text='皇上眼眶微红：「难为你有心。」', lose=dict(favor=3), lose_text='皇上「嗯」了一声，没再说什么。'),
        dict(text='讨巧：「嫔妾只求皇上天天来嫔妾这里。」', stat='appearance', dc=68,
             win=dict(favor=20), win_text='皇上笑了：「就你黏人。」', lose=dict(favor=-5, trust=-3), lose_text='皇上淡淡道：「没个正经。」'),
        dict(text='直言：「嫔妾想要一个皇子。不是为了争宠，是为了让皇上后继有人。」', stat='scheme', dc=72,
             win=dict(favor=5, trust=10), win_text='皇上点点头：「你这话说得明白。」', lose=dict(favor=-10, trust=4), lose_text='皇上沉下脸：「你急什么？」但他没有发怒。'),
    ]),
]

# 侍寝时额外多一个选项：替身在禁足或冷宫的姐妹求情，成败只看信任（信任 + 随机 0~40 ≥ 50）
PLEAD_IN_BED = dict(text='替身陷困境的姐妹求情', stat='trust', dc=50, plead=True,
                    win=dict(), win_text='皇上沉吟片刻：「罢了，看在你的面上。」',
                    lose=dict(trust=-3), lose_text='皇上翻了个身：「这事你别管。」')

EFFECT_NAMES = dict(favor='圣宠', trust='信任', virtue='德行', health='体质',
                    appearance='容貌', talent='才艺', scheme='心计', silver='银子')

# ── NPC ────────────────────────────────────────────────────────────────────────

NPCS = [
    dict(npc_key='huanghou', hall='main', surname='西林觉罗', given='蕴仪', title='', rank=10, palace='景仁宫',
         appearance=62, talent=70, scheme=92, virtue=80, health=75, favor=250, aggression=0.35,
         intro='中宫皇后，待人宽和，六宫都说她贤德。'),
    dict(npc_key='huafei', hall='main', surname='佟佳', given='灼华', title='华', rank=6, palace='翊坤宫',
         appearance=90, talent=55, scheme=70, virtue=30, health=85, favor=420, aggression=0.4,
         intro='宠冠六宫，兄长手握重兵。最见不得别人得宠。'),
    dict(npc_key='duanfei', hall='main', surname='沈', given='疏影', title='端', rank=6, palace='延庆殿',
         appearance=55, talent=60, scheme=65, virtue=75, health=20, favor=40, aggression=0,
         intro='常年卧病，深居简出，却什么都看在眼里。'),
    dict(npc_key='qifei', hall='main', surname='周', given='巧云', title='齐', rank=6, palace='长春宫',
         appearance=58, talent=35, scheme=30, virtue=50, health=70, favor=90, aggression=0.05,
         intro='三阿哥生母，心直口快，常被人当枪使。'),
    dict(npc_key='jingpin', hall='main', surname='许', given='慧娴', title='敬', rank=5, palace='咸福宫',
         appearance=60, talent=58, scheme=50, virtue=70, health=72, favor=110, aggression=0,
         intro='性子温吞，与人为善，在宫里熬了许多年。'),
    dict(npc_key='lipin', hall='main', surname='田', given='翠浓', title='丽', rank=5, palace='启祥宫',
         appearance=75, talent=40, scheme=40, virtue=35, health=75, favor=170, aggression=0.12,
         intro='华妃跟前的人，嘴快心浅。'),
    dict(npc_key='caoguiren', hall='east', surname='曹', given='映雪', title='曹', rank=4, palace='启祥宫',
         appearance=62, talent=55, scheme=80, virtue=45, health=65, favor=150, aggression=0.2,
         intro='公主生母，华妃的智囊，笑里藏刀。'),
    dict(npc_key='xinchangzai', hall='east', surname='孟', given='秀珠', title='欣', rank=3, palace='储秀宫',
         appearance=55, talent=45, scheme=40, virtue=55, health=70, favor=70, aggression=0,
         intro='资历老，位分低，说话爽利。'),
]

# 系统皇子：开服就在。三阿哥是长子、老实鲁钝，朝中老臣认他；四阿哥学问骑射都不低，可惜没人抱他
NPC_KEYS = {n['npc_key'] for n in NPCS}

NPC_HEIRS = dict(
    third=dict(ordinal=3, age_days=7, personality='honest', study=30, riding=40, virtue=45, health=65, ambition=40, faction=3, zhuazhou='seal'),
    fourth=dict(ordinal=4, age_days=4, personality='clever', study=60, riding=55, virtue=60, health=80, ambition=65, faction=0, zhuazhou='book'),
)
NPC_ORPHAN_DEADLINE_DAYS = 6   # 开服第 7 天还没人求到，皇后就把四阿哥抱走（2026-09-28 从 14 压到 6）

# 下一届的 NPC 妃嫔：新帝潜邸的旧人。位分、封号、住处沿用 NPCS（代码里不少地方按 npc_key 认人，比如华妃发难），
# 只换名字、性格介绍和数值。第二届用甲套，第三届用乙套，之后轮着来
NPC_SETS = [
    dict(  # 甲
        huanghou=dict(surname='富察', given='婉清', appearance=66, talent=68, scheme=88, virtue=84, health=72, favor=240, aggression=0.30,
                      intro='新帝潜邸时的嫡福晋，端庄持重，一府的事早就是她管着。'),
        huafei=dict(surname='钮祜禄', given='明玥', appearance=88, talent=52, scheme=68, virtue=32, health=84, favor=400, aggression=0.42,
                    intro='出身显赫，仗着娘家的势，最爱与人争一口气。'),
        duanfei=dict(surname='舒穆禄', given='静姝', appearance=52, talent=64, scheme=60, virtue=78, health=22, favor=40, aggression=0,
                     intro='体弱多病，不与人争，冷眼看着一切。'),
        qifei=dict(surname='完颜', given='芷兰', appearance=56, talent=38, scheme=32, virtue=52, health=70, favor=95, aggression=0.05,
                   intro='长子生母，心直口快，藏不住话。'),
        jingpin=dict(surname='瓜尔佳', given='素心', appearance=58, talent=56, scheme=48, virtue=72, health=72, favor=105, aggression=0,
                     intro='老实温厚，潜邸时就伺候在跟前。'),
        lipin=dict(surname='郭络罗', given='嫣然', appearance=76, talent=42, scheme=42, virtue=36, health=74, favor=165, aggression=0.12,
                   intro='华妃跟前得意的人，口齿伶俐，心里没多少弯弯绕。'),
        caoguiren=dict(surname='赫舍里', given='云舒', appearance=64, talent=58, scheme=78, virtue=46, health=66, favor=145, aggression=0.2,
                       intro='公主生母，心思缜密，笑起来最让人不放心。'),
        xinchangzai=dict(surname='董鄂', given='秋棠', appearance=54, talent=46, scheme=38, virtue=56, health=70, favor=70, aggression=0,
                         intro='资历老，位分低，说话直来直去。'),
    ),
    dict(  # 乙
        huanghou=dict(surname='马佳', given='淑仪', appearance=60, talent=72, scheme=90, virtue=78, health=76, favor=245, aggression=0.33,
                      intro='潜邸旧人里最有分量的一位，面上温和，什么都记在心里。'),
        huafei=dict(surname='那拉', given='锦瑟', appearance=92, talent=58, scheme=72, virtue=28, health=86, favor=430, aggression=0.45,
                    intro='容色艳压六宫，脾气也一样张扬。'),
        duanfei=dict(surname='叶赫', given='清漪', appearance=50, talent=66, scheme=62, virtue=76, health=18, favor=35, aggression=0,
                     intro='常年吃药，闭门读书，宫里的事她比谁都清楚。'),
        qifei=dict(surname='陈', given='婉凝', appearance=55, talent=36, scheme=34, virtue=50, health=72, favor=88, aggression=0.05,
                   intro='长子生母，性子软，常被人推出去顶事。'),
        jingpin=dict(surname='徐', given='若水', appearance=60, talent=54, scheme=46, virtue=70, health=70, favor=112, aggression=0,
                     intro='凡事忍让，与谁都说得上话。'),
        lipin=dict(surname='赵', given='明珠', appearance=74, talent=44, scheme=44, virtue=38, health=76, favor=172, aggression=0.13,
                   intro='华妃的应声虫，嘴快心浅。'),
        caoguiren=dict(surname='何', given='玉容', appearance=66, talent=60, scheme=76, virtue=48, health=64, favor=150, aggression=0.18,
                       intro='公主生母，最擅长借刀杀人。'),
        xinchangzai=dict(surname='孙', given='小满', appearance=56, talent=44, scheme=36, virtue=58, health=72, favor=68, aggression=0,
                         intro='入府最早，位分却低，脾气爽利，不怕得罪人。'),
    ),
]
ERA_NAMES = ['嘉和', '景元', '昭泰', '乾宁', '永熙', '崇德', '宣和', '明昌', '天佑', '启祥']
NPC_PRINCE_NAMES = ['承稷', '承煦', '承晏', '承祺', '承昀', '承恪', '承瑾', '承烨', '承璋', '承珩']
NPC_PRINCESS_NAMES = ['和婉', '宁悦', '淑安', '静姝', '玉衡', '兰沁']


def npcs_for_reign(reign_no):
    return []


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

DIANXUAN_QUESTIONS = [q_ for q_ in DIANXUAN_QUESTIONS if q_['key'] != 'huafei']
for q_ in DIANXUAN_QUESTIONS:
    q_['who'] = q_['who'].replace('太后', '皇上')
    for opt_ in q_['opts']:
        opt_['react'] = opt_['react'].replace('太后', '皇上').replace('华妃掩口一笑', '旁边的秀女轻轻一笑')
SCENES = {key: val for key, val in SCENES.items() if not val.get('npc')}
NPC_SCENES = []
GREET_SCENES = []
NPCS = []
NPC_HEIRS = {}
NPC_KEYS = set()
NPC_SETS = []

def dianxuan_questions_for(consort_id):
    rnd = random.Random(consort_id * 7919)
    return rnd.sample(DIANXUAN_QUESTIONS, 3)

# ── 游戏状态 / 工具 ────────────────────────────────────────────────────────────

settle_lock = threading.RLock()

def migrate_pregnancy_clocks(db):
    day = db.execute('SELECT day FROM game_state WHERE id=1').fetchone()[0]
    now = time.time()
    for cid, since in db.execute("SELECT id,pregnant_since FROM consorts WHERE pregnant_since>0 AND pregnancy_started_ts=0 AND status!='dead'").fetchall():
        diagnosis = db.execute("SELECT created_ts FROM messages WHERE consort_id=? AND day=? AND text LIKE '%诊出了喜脉%' ORDER BY id DESC LIMIT 1", (cid,since)).fetchone()
        started = diagnosis[0] if diagnosis and diagnosis[0]>0 else now-min(24,max(0,day-since)*24)*3600
        db.execute('UPDATE consorts SET pregnancy_started_ts=? WHERE id=?',(started,cid))


def migrate_drug_cooldowns(db):
    if db.execute('SELECT drug_rules_version FROM game_state WHERE id=1').fetchone()[0]: return
    db.execute('UPDATE users SET drug_ready_day=0,lethal_ready_day=0,nameless_ready_day=0')
    for uid, drug, used, day in db.execute("SELECT COALESCE(c.user_id,c.archived_user_id),i.drug,i.item_used,i.day FROM intrigues i JOIN consorts c ON c.id=i.attacker_id WHERE i.method='drug' AND i.status='done' AND i.result='success'").fetchall():
        if not uid: continue
        ready=day+(2 if drug=='lihun' else 1)
        db.execute('UPDATE users SET drug_ready_day=MAX(drug_ready_day,?) WHERE id=?',(ready,uid))
        if drug=='lihun':db.execute('UPDATE users SET lethal_ready_day=MAX(lethal_ready_day,?) WHERE id=?',(ready,uid))
        if used=='wuming':db.execute('UPDATE users SET nameless_ready_day=MAX(nameless_ready_day,?) WHERE id=?',(day+1,uid))
    db.execute('UPDATE game_state SET drug_rules_version=1 WHERE id=1')


def migrate_yinzhen_price(db):
    """银针涨价：手里还有银针的人，按差价补扣银子（银子不够就扣到 0），只做一次"""
    if db.execute('SELECT yinzhen_price_version FROM game_state').fetchone()[0]: return
    day = db.execute('SELECT day FROM game_state').fetchone()[0]
    for cid, qty, silver in db.execute("SELECT i.consort_id, i.qty, c.silver FROM inventory i JOIN consorts c ON c.id=i.consort_id WHERE i.item_key='yinzhen' AND i.qty>0").fetchall():
        due = qty * (YINZHEN_PRICE - YINZHEN_OLD_PRICE)
        pay = min(due, max(0, silver))
        db.execute('UPDATE consorts SET silver=silver-? WHERE id=?', (pay, cid))
        db.execute("INSERT INTO messages (consort_id, day, kind, text, created_ts) VALUES (?,?,?,?,?)",
                   (cid, day, 'info', f'内务府银针涨价（{YINZHEN_OLD_PRICE}→{YINZHEN_PRICE} 两），你手里的 {qty} 根按差价补扣了 {pay} 两' + ('' if pay == due else f'（银子不够，原应补 {due} 两）') + '。', time.time()))
    db.execute('UPDATE game_state SET yinzhen_price_version=1 WHERE id=1')


def migrate_new_arts_notice(db):
    """才艺上新：琵琶、笛子，各才艺也新增了宴会曲目。只公告一次"""
    if db.execute('SELECT arts_notice_version FROM game_state').fetchone()[0]: return
    if not db.execute('SELECT 1 FROM gazette LIMIT 1').fetchone(): return      # 全新的库没人看公告，不用发
    day = db.execute('SELECT day FROM game_state').fetchone()[0]
    db.execute("INSERT INTO gazette (day, kind, text, is_night, created_ts) VALUES (?,?,?,?,?)",
               (day, 'decree', '内务府新进了一批乐器与曲谱：宫中才艺上新「琵琶」「笛子」，各样才艺也添了新的宴会曲目。去本宫修习，御前展示时记得换着样儿来，皇上不爱连着听同一样。', 0, time.time()))
    db.execute('UPDATE game_state SET arts_notice_version=1 WHERE id=1')


def migrate_drug_balance(db):
    if db.execute('SELECT drug_balance_version FROM game_state').fetchone()[0]:return
    now=time.time();day=db.execute('SELECT day FROM game_state').fetchone()[0]
    for aid,cid,drug,start,iid in db.execute("SELECT id,consort_id,drug,start_day,intrigue_id FROM afflictions WHERE status='active'").fetchall():
        hours=DRUGS.get(drug,{}).get('hours',0)
        onset=now-max(0,day-start)*86400
        if drug=='chunxin':
            row=db.execute('SELECT pregnancy_started_ts FROM consorts WHERE id=?',(cid,)).fetchone()
            if row and row[0]:onset=row[0]
        stat,delta=({'yanzhi':('appearance',10),'yachan':('talent',8)}.get(drug,('',0)))
        db.execute('UPDATE afflictions SET expires_ts=?,restore_stat=?,restore_delta=?,ticks=?,until_day=0 WHERE id=?',(onset+hours*3600 if hours else 0,stat,delta,min(3,max(0,day-start)) if drug=='qingsi' else 0,aid))
    db.execute('UPDATE game_state SET drug_balance_version=1')


def init_db():
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    # 幂等迁移：旧角色从更新时开始计龄，不按旧存档天数追溯增长。
    migrations = {
        'afflictions': {'expires_ts': 'REAL NOT NULL DEFAULT 0','restore_stat': "TEXT NOT NULL DEFAULT ''",'restore_delta': 'INTEGER NOT NULL DEFAULT 0','ticks': 'INTEGER NOT NULL DEFAULT 0','last_tick_day': 'INTEGER NOT NULL DEFAULT -1'},'families': {'career_path': "TEXT NOT NULL DEFAULT ''", 'background': "TEXT NOT NULL DEFAULT ''"},
        'banquet_entries': {'partner_id': 'INTEGER NOT NULL DEFAULT 0', 'tier': 'INTEGER NOT NULL DEFAULT 1', 'buff': 'INTEGER NOT NULL DEFAULT 0', 'note': "TEXT NOT NULL DEFAULT ''"},
        'consorts': {'favor_mark': 'INTEGER NOT NULL DEFAULT -1', 'dying_since_ts': 'REAL NOT NULL DEFAULT 0', 'four_word': "TEXT NOT NULL DEFAULT ''", 'title_choices': "TEXT NOT NULL DEFAULT ''", 'confine_until_ts': 'REAL NOT NULL DEFAULT 0', 'badge': "TEXT NOT NULL DEFAULT ''", 'guide_mama': "TEXT NOT NULL DEFAULT ''", 'garden_plots': 'INTEGER NOT NULL DEFAULT 3',
                     'age_months': 'INTEGER NOT NULL DEFAULT 240',
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
                     'pregnancy_misses': 'INTEGER NOT NULL DEFAULT 0',
                     'last_perform_art': "TEXT NOT NULL DEFAULT ''",
                     'birth_gender_pref': "TEXT NOT NULL DEFAULT ''",
                     'banquet_wins': 'INTEGER NOT NULL DEFAULT 0',
                     'influence': 'INTEGER NOT NULL DEFAULT 0',
                     'pregnancy_started_ts': 'REAL NOT NULL DEFAULT 0', 'bed_daily_day': 'INTEGER NOT NULL DEFAULT 0', 'bed_daily_count': 'INTEGER NOT NULL DEFAULT 0', 'entry_origin': "TEXT NOT NULL DEFAULT 'new'",
                     'last_promote_day': 'INTEGER NOT NULL DEFAULT 0',
                     'contraception': 'INTEGER NOT NULL DEFAULT 0',
                     'dianxuan_quote': "TEXT NOT NULL DEFAULT ''",
                     'maid_offer': "TEXT NOT NULL DEFAULT ''",
                     'maid_event': "TEXT NOT NULL DEFAULT ''",
                     'punish_ready_day': 'INTEGER NOT NULL DEFAULT 0', 'impeach_ready_day': 'INTEGER NOT NULL DEFAULT 0', 'impeached_day': 'INTEGER NOT NULL DEFAULT 0',
                     'maid_punished_day': 'INTEGER NOT NULL DEFAULT 0',
                     'drugged_until_day': 'INTEGER NOT NULL DEFAULT 0', 'drugged_day': 'INTEGER NOT NULL DEFAULT 0',
                     'drug_ledger': 'INTEGER NOT NULL DEFAULT 0',
                     'hall': "TEXT NOT NULL DEFAULT ''",
                     'discipline_ready_day': 'INTEGER NOT NULL DEFAULT 0',
                     'housing_waiting': "TEXT NOT NULL DEFAULT ''",
                     'hobby_kinds': "TEXT NOT NULL DEFAULT ''",
                     'guide_step': 'INTEGER NOT NULL DEFAULT 0',
                     'guide_progress': "TEXT NOT NULL DEFAULT '[]'",
                     'guide_tips': "TEXT NOT NULL DEFAULT '[]'",
                     'unfavored_days': 'INTEGER NOT NULL DEFAULT 0',
                     'care_tier': "TEXT NOT NULL DEFAULT ''",
                     'skin': "TEXT NOT NULL DEFAULT ''",
                     'influence_low_days': 'INTEGER NOT NULL DEFAULT 0',
                     'ill_care': "TEXT NOT NULL DEFAULT 'normal'",
                     'ill_day': 'INTEGER NOT NULL DEFAULT 0',
                     'ill_treatment': 'INTEGER NOT NULL DEFAULT 0',
                     'weak_days': 'INTEGER NOT NULL DEFAULT 0',
                     'postpartum_until': 'INTEGER NOT NULL DEFAULT 0',
                     'heir_event': "TEXT NOT NULL DEFAULT ''",
                     'reign_no': 'INTEGER NOT NULL DEFAULT 1',
                     'seq': 'INTEGER NOT NULL DEFAULT 0',
                     'entry_age': 'INTEGER NOT NULL DEFAULT 0',
                     'lineage': "TEXT NOT NULL DEFAULT ''",
                     'patron': "TEXT NOT NULL DEFAULT ''",
                     'peak_rank': 'INTEGER NOT NULL DEFAULT 0',
                     'prestige_top': 'INTEGER NOT NULL DEFAULT 0',
                     'kids': "TEXT NOT NULL DEFAULT '[]'",
                     'survived': 'INTEGER NOT NULL DEFAULT 0',
                     'heirloom_maid_id': 'INTEGER NOT NULL DEFAULT 0',
                     'culprit_id': 'INTEGER NOT NULL DEFAULT 0',
                     'inherit': "TEXT NOT NULL DEFAULT '{}'",
                     'shoukang_day': 'INTEGER NOT NULL DEFAULT 0',
                     'gather_event': "TEXT NOT NULL DEFAULT ''",
                     'prenatal': "TEXT NOT NULL DEFAULT '{}'",
                     'diet': "TEXT NOT NULL DEFAULT 'normal'",
                     'diet_eff': "TEXT NOT NULL DEFAULT 'normal'",
                     'repair': "TEXT NOT NULL DEFAULT ''",
                     'blessing': 'INTEGER NOT NULL DEFAULT 0',
                     'longevity': 'INTEGER NOT NULL DEFAULT 0'},
        'heirs': {'unpaid_days': 'INTEGER NOT NULL DEFAULT 0', 'born_ts': 'REAL NOT NULL DEFAULT 0', 'appearance': 'INTEGER NOT NULL DEFAULT 0', 'temperament': "TEXT NOT NULL DEFAULT ''", 'temper_tier': 'INTEGER NOT NULL DEFAULT -1', 'name_choices': "TEXT NOT NULL DEFAULT ''", 'gen_word': "TEXT NOT NULL DEFAULT ''", 'gift_study': 'INTEGER NOT NULL DEFAULT 100', 'gift_riding': 'INTEGER NOT NULL DEFAULT 100',
                  'gift_virtue': 'INTEGER NOT NULL DEFAULT 100',
                  'caretaker_id': 'INTEGER NOT NULL DEFAULT 0',
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
                  'reclaim_after_day': 'INTEGER NOT NULL DEFAULT 0',
                  'adult_day': 'INTEGER NOT NULL DEFAULT 0',
                  'title': "TEXT NOT NULL DEFAULT ''",
                  'marriage': "TEXT NOT NULL DEFAULT ''",
                  'marry_day': 'INTEGER NOT NULL DEFAULT 0',
                  'errand': "TEXT NOT NULL DEFAULT ''",
                  'plead_ready_day': 'INTEGER NOT NULL DEFAULT 0',
                  'npc_key': "TEXT NOT NULL DEFAULT ''",
                  'ambition': 'INTEGER NOT NULL DEFAULT 30',
                  'faction': 'INTEGER NOT NULL DEFAULT 0',
                  'status': "TEXT NOT NULL DEFAULT ''",
                  'exam_bonus': 'INTEGER NOT NULL DEFAULT 0',
                  'feud_until_day': 'INTEGER NOT NULL DEFAULT 0',
                  'gift': "TEXT NOT NULL DEFAULT ''",
                  'orphan_deadline_day': 'INTEGER NOT NULL DEFAULT 0',
                  'reprimand_ready_day': 'INTEGER NOT NULL DEFAULT 0',
                  'forged': 'INTEGER NOT NULL DEFAULT 0'},
        'cases': {'victim_trust_loss': 'INTEGER NOT NULL DEFAULT 15','convicted_id': 'INTEGER NOT NULL DEFAULT 0', 'wrongful': 'INTEGER NOT NULL DEFAULT 0',
                  'appeal_ready_day': 'INTEGER NOT NULL DEFAULT 0'},
        'intrigues': {'resolved_ts': 'REAL NOT NULL DEFAULT 0','drug': "TEXT NOT NULL DEFAULT ''",
                      'agent_maid_id': 'INTEGER NOT NULL DEFAULT 0',
                      'partner_id': 'INTEGER NOT NULL DEFAULT 0', 'partner_silver': 'INTEGER NOT NULL DEFAULT 0'},
        'letters': {'hobby_item_id': 'INTEGER NOT NULL DEFAULT 0',
                    'is_broadcast': 'INTEGER NOT NULL DEFAULT 0',
                    'broadcast_id': 'INTEGER NOT NULL DEFAULT 0',
                    'claimed': 'INTEGER NOT NULL DEFAULT 1',
                    'deleted_by_from': 'INTEGER NOT NULL DEFAULT 0',
                    'deleted_by_to': 'INTEGER NOT NULL DEFAULT 0',
                    'sender_label': "TEXT NOT NULL DEFAULT ''"},
        'messages': {'is_night': 'INTEGER NOT NULL DEFAULT 0'},
        'gazette': {'is_night': 'INTEGER NOT NULL DEFAULT 0'},
        'game_state': {'last_noon_age_date': "TEXT NOT NULL DEFAULT ''", 'rank_scale': 'INTEGER NOT NULL DEFAULT 0', 'last_promo_key': "TEXT NOT NULL DEFAULT ''", 'last_decay_date': "TEXT NOT NULL DEFAULT ''", 'last_midday_promotion_date': "TEXT NOT NULL DEFAULT ''", 'drug_balance_version': 'INTEGER NOT NULL DEFAULT 0', 'arts_notice_version': 'INTEGER NOT NULL DEFAULT 0', 'yinzhen_price_version': 'INTEGER NOT NULL DEFAULT 0', 'drug_rules_version': 'INTEGER NOT NULL DEFAULT 0','last_banquet_date': "TEXT NOT NULL DEFAULT ''", 'last_energy_key': "TEXT NOT NULL DEFAULT ''", 'last_bed_ids': "TEXT NOT NULL DEFAULT '[]'", 'last_bed_round_key': "TEXT NOT NULL DEFAULT ''", 'last_bed_pool': "TEXT NOT NULL DEFAULT '[]'",
                       'reign_no': 'INTEGER NOT NULL DEFAULT 1',
                       'reign_start_day': 'INTEGER NOT NULL DEFAULT 1',
                       'emperor_start_age': 'INTEGER NOT NULL DEFAULT 20',
                       'emperor_death_day': 'INTEGER NOT NULL DEFAULT 0',
                       'mourning': 'INTEGER NOT NULL DEFAULT 0',
                       'era_name': "TEXT NOT NULL DEFAULT ''",
                       'emperor_name': "TEXT NOT NULL DEFAULT ''",
                       'emperor_traits': "TEXT NOT NULL DEFAULT '{}'",
                       'dowager': "TEXT NOT NULL DEFAULT ''",
                       'dowager_uid': 'INTEGER NOT NULL DEFAULT 0',
                       'event_started': 'INTEGER NOT NULL DEFAULT 1',
                       'maintenance': 'INTEGER NOT NULL DEFAULT 0'},
        'users': {'managed': 'INTEGER NOT NULL DEFAULT 0', 'qq_number': "TEXT NOT NULL DEFAULT ''", 'stat_roll_reign': 'INTEGER NOT NULL DEFAULT 0', 'stat_roll': "TEXT NOT NULL DEFAULT ''", 'east_palace_reign': 'INTEGER NOT NULL DEFAULT 0',
                  'east_palace_old': 'INTEGER NOT NULL DEFAULT 0',
                  'forge_used': 'INTEGER NOT NULL DEFAULT 0',
                  'drug_ready_day': 'INTEGER NOT NULL DEFAULT 0', 'lethal_ready_day': 'INTEGER NOT NULL DEFAULT 0',
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
    legacy = [row[0] for row in db.execute("SELECT id FROM consorts WHERE npc_key IS NOT NULL")]
    for cid in legacy:
        db.execute("UPDATE heirs SET caretaker_id=CASE WHEN (SELECT rank FROM consorts WHERE id=mother_id)>=5 THEN mother_id ELSE 0 END WHERE caretaker_id=? AND COALESCE(npc_key,'')=''", (cid,))
        db.execute("UPDATE intrigues SET status='done',result='void' WHERE attacker_id=? OR target_id=?", (cid,cid))
        db.execute("DELETE FROM relations WHERE a_id=? OR b_id=?", (cid,cid))
    db.execute("DELETE FROM heirs WHERE COALESCE(npc_key,'')!=''")
    for row in db.execute("SELECT id,pending_scene FROM consorts WHERE pending_scene!=''").fetchall():
        try:
            scene = json.loads(row[1])
        except (ValueError, TypeError):
            scene = {}
        if scene.get('key') not in SCENES and scene.get('key') not in ('audience', 'exam'):
            db.execute("UPDATE consorts SET pending_scene='' WHERE id=?", (row[0],))
    db.execute("DELETE FROM consorts WHERE npc_key IS NOT NULL")
    db.execute("DELETE FROM heir_claims WHERE heir_id NOT IN (SELECT id FROM heirs) OR consort_id NOT IN (SELECT id FROM consorts)")
    db.execute("DELETE FROM knife_debts")
    db.execute("DELETE FROM custody_battles WHERE heir_id NOT IN (SELECT id FROM heirs)")
    retire_musk(db)
    migrate_families(db)
    if not db.execute("SELECT 1 FROM game_state WHERE id=1").fetchone():
        now = datetime.now(TZ)
        # 开服时若已过今天的结算时刻，视为今天已结算，免得一开服就空结算一次
        last = now.date().isoformat() if past_settle_time(now) else ''
        db.execute("INSERT INTO game_state (id, day, last_settle_date, emperor_mood, emperor_pref) VALUES (1,1,?,?,?)",
                   (last, '平和', random.choice(ARTS)))
    for family_uid,tier in db.execute("SELECT user_id,tier FROM families WHERE background='' ORDER BY user_id").fetchall():
        db.execute('UPDATE families SET background=? WHERE user_id=?',(family_origin_options(tier,db,1)[0],family_uid))
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS family_background_unique ON families(background) WHERE background!=''")
    migrate_pregnancy_clocks(db)
    migrate_drug_cooldowns(db)
    migrate_drug_balance(db)
    migrate_new_arts_notice(db)
    migrate_yinzhen_price(db)
    migrate_rank_scale(db)
    migrate_heir_born_ts(db)
    seed_npcs(db)
    seed_npc_heirs(db)
    migrate_no_clean_secret(db)
    migrate_heir_looks(db)
    db.commit()
    db.close()
    with app.app_context():
        housing_sync()      # 老存档里的玩家第一次启动时分好住处；之后每次都是空操作

def migrate_heir_born_ts(db):
    """孩子按出生时刻起算年龄（每 12 小时一岁）：老档里只有出生天数的，按「那天零点」折成时间戳；妃嫔中午年龄结算的当天日期补上，免得部署当天多涨一次"""
    st = db.execute("SELECT day FROM game_state WHERE id=1").fetchone()
    if st:
        midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        for hid, born_day in db.execute("SELECT id, born_day FROM heirs WHERE born_ts=0").fetchall():
            db.execute("UPDATE heirs SET born_ts=? WHERE id=?", (midnight - max(0, st[0] - born_day) * 86400, hid))
        # 新加的「按日期只做一次」记录：已有玩家的老库盖成昨天，当天的任务（比如中午涨岁）不会被这次迁移跳过；全新的库盖成今天
        stamp = datetime.now(TZ).date() - timedelta(days=1 if db.execute('SELECT 1 FROM users LIMIT 1').fetchone() else 0)
        db.execute("UPDATE game_state SET last_noon_age_date=? WHERE id=1 AND last_noon_age_date=''", (stamp.isoformat(),))
        db.execute("UPDATE consorts SET favor_mark=favor WHERE favor_mark<0")      # 圣宠骤降降位的基线：部署时先记一次

def migrate_rank_scale(db):
    """2026-10-07 在妃和贵妃之间加「四妃」档：旧档里贵妃(7)及以上全部顺延一位；占了淑德贤惠当封号的人换一个。只做一次"""
    row = db.execute("SELECT rank_scale FROM game_state WHERE id=1").fetchone()
    if row is not None and row[0] == 0:
        for col in ('rank', 'rank_before_cold', 'peak_rank', 'prestige_top'):
            db.execute(f"UPDATE consorts SET {col}={col}+1 WHERE {col}>=7")
        db.execute("UPDATE game_state SET rank_scale=1 WHERE id=1")
    used = {r[0] for r in db.execute("SELECT title FROM consorts WHERE title!='' AND status NOT IN ('cold','dead')")}
    pool = [t for t in TITLE_POOL if t not in used]
    random.shuffle(pool)
    day = db.execute("SELECT day FROM game_state WHERE id=1").fetchone()
    for cid, uid, title, rank in db.execute("SELECT id, user_id, title, rank FROM consorts WHERE title IN (%s) AND rank!=?" % ','.join('?' * len(FOUR_CONSORT_TITLES)), (*FOUR_CONSORT_TITLES, -1)).fetchall():
        if not pool: break
        new = pool.pop()
        db.execute("UPDATE consorts SET title=? WHERE id=?", (new, cid))
        if uid and day:
            db.execute("INSERT INTO messages (consort_id, day, kind, text, is_night, created_ts) VALUES (?,?,?,?,0,?)",
                       (cid, day[0], 'decree', f"「{title}」是四妃的名号，不能再当封号，内务府替你换了一个：「{new}」。", now_ts()))

def seed_npcs(db):
    """后宫由玩家建立，不预置妃嫔。"""
    return


class _RunDB:
    """让 seed_* 函数在请求里也能用：execute 走 run()，跟着当前事务走"""
    @staticmethod
    def execute(sql, args=()):
        return run(sql, args)


def npc_heir_specs(day, reign_no, reign_start_day, emperor_start_age=20):
    return []


def seed_npc_heirs(db):
    """皇嗣全部来自本届玩家，不预置潜邸子女。"""
    return

def migrate_no_clean_secret(db):
    """取消「身家清白」：老档里 secret='none' 的角色重抽一个真秘密，已查到的人看到的就是新秘密"""
    for (cid,) in db.execute("SELECT id FROM consorts WHERE secret NOT IN (%s)" % ','.join('?'*len(SECRETS)), list(SECRETS)).fetchall():
        db.execute('UPDATE consorts SET secret=? WHERE id=?', (roll_secret(), cid))


def migrate_families(db):
    """老档：每个有过角色的账号补一个家族（姓氏、门第取第一位角色的），角色补上入宫序号和辈分说法"""
    for (uid,) in db.execute("SELECT id FROM users").fetchall():
        if db.execute("SELECT 1 FROM families WHERE user_id=?", (uid,)).fetchone(): continue
        rows = db.execute("SELECT id, surname, given, family, rank FROM consorts WHERE user_id=? OR archived_user_id=? ORDER BY id", (uid, uid)).fetchall()
        if not rows: continue
        surname, tier = rows[0][1], rows[0][3]
        if tier not in FAMILIES: tier = 'dali'
        h = new_head(surname, tier, 0)
        db.execute("""INSERT INTO families (user_id, surname, tier, head_name, head_role, head_gen, head_age_months, head_office, created_ts)
                      VALUES (?,?,?,?,?,?,?,?,?)""", (uid, surname, tier, h['head_name'], h['head_role'], 0, h['head_age_months'],
                                                      TIER_OFFICE[tier], now_ts()))
        prev = None
        for i, (cid, _sn, given, _fam, rank) in enumerate(rows):
            lineage = '长女' if i == 0 else (f"{prev}之妹" if i == 1 else f"{prev}的堂妹")
            db.execute("UPDATE consorts SET seq=?, lineage=?, peak_rank=MAX(peak_rank,?), prestige_top=MAX(prestige_top,?) WHERE id=? AND lineage=''",
                       (i + 1, lineage, rank, rank, cid))
            prev = given


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
    if st['maintenance']: return '系统维护中'
    if not st['event_started']: return '活动还没开始'
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
    if delta > 0 and emperor_traits().get('personality') == 'stubborn':
        delta = max(1, round(delta * 0.7))                  # 倔强的皇上，信任涨得慢
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

# 2026-10-07：扣圣宠一律扣定额，不再按比例（圣宠越高、扣得越多，高位的人被一次流言就掉几十点，太狠）
CAUGHT_TRUST_LOSS, CAUGHT_TRUST_LOSS_LIGHT = 8, 5     # 使计败露扣信任：一般计策 8，告发不信/发落宫人 5（信任起点才 20，扣太多一次就见底）
FAVOR_LOSS = dict(
    rumor=18, rumor_trusted=9,              # 被散布流言（皇上信任你时减半）
    frame=24, frame_trusted=12,             # 被栽赃陷害
    caught_rumor=12, caught_frame=18, caught_steal=18, caught_expose=18, mood_extra=12,   # 使计败露的自罚；皇上震怒再加
    dream=18,                               # 惊梦香发作
    lavish=6, repair=2, usury=12,           # 逾制被参、屋子坏了没修、印子钱东窗事发
    secret_lover=60, secret_lover_confess=24, secret_fake_confess=36, secret_scar=24,   # 秘密被揭 / 主动坦白
    convicted=18, case_culprit=18,          # 定罪、旧案翻出真凶
)

def cut_favor(cid, amount):
    """扣定额圣宠，天真性格减半，不会扣成负数。返回实际扣掉的数"""
    c = get_consort(cid)
    if c['personality'] == 'naive': amount = amount // 2
    loss = min(int(amount), c['favor'])
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

def remember(a, b, kind, note=''):
    """记一件够分量的事。a、b 不分先后，查的时候两个方向都要看"""
    run("INSERT INTO memories (a_id, b_id, kind, day, note) VALUES (?,?,?,?,?)", (a, b, kind, cur_day(), note))


def memories_between(a, b):
    return q("SELECT * FROM memories WHERE (a_id=? AND b_id=?) OR (a_id=? AND b_id=?) ORDER BY id", (a, b, b, a))


def memory_line(a, b):
    """挑一件两人之间记着的事，回一句能接在场景/小聚开头的话；没有就是空"""
    lines = dict(treat='想起她病中替你请过太医的事', visit_cold='想起她在你困顿时仍来看过你',
                 first_gift='想起她把自己做的第一件东西送了给你', testify='想起她当年替你在案子上作过证',
                 festival='想起你们曾一起过节')
    rows = [r for r in memories_between(a, b) if r['kind'] in lines]   # 交好线的记账（qifei_plead 等）不算
    if not rows: return ''
    return lines[random.choice(rows)['kind']]


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

EYES_DAYS = 2      # 眼线有效天数，含安插当天（2026-10-07 起，原来 5 天）

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

TITLE_CHOICES_N = 3

def offer_title_choices(cid):
    """晋到嫔位时，已经有封号的玩家可以从三个没人用的封号里挑一个新的（托管角色不挑，保持原封号）"""
    c = get_consort(cid)
    u = q("SELECT managed FROM users WHERE id=?", (c['user_id'],), one=True) if c and c['user_id'] else None
    if not c or not u or u['managed'] or c['npc_key']: return
    used = {r['title'] for r in q("SELECT title FROM consorts WHERE title!='' AND status NOT IN ('cold','dead')")}
    pool = [t for t in TITLE_POOL if t not in used]
    if not pool: return
    picks = random.sample(pool, min(TITLE_CHOICES_N, len(pool)))
    run("UPDATE consorts SET title_choices=? WHERE id=?", (''.join(picks), cid))
    notify(cid, f"你晋为嫔位，可以换一个新封号了：{'、'.join(picks)}，回宫城挑一个（也可以保留「{c['title']}」）。", 'good')

def assign_four_word(cid):
    """四妃的名号：淑、德、贤、惠，一人一个，挑当前四妃里没人用的"""
    used = {r['four_word'] for r in q("SELECT four_word FROM consorts WHERE rank=? AND status NOT IN ('cold','dead') AND id!=?", (RANK_FOUR, cid))}
    free = [w for w in FOUR_CONSORT_TITLES if w not in used]
    w = random.choice(free) if free else random.choice(FOUR_CONSORT_TITLES)
    run("UPDATE consorts SET four_word=? WHERE id=?", (w, cid))
    return w

def set_rank(cid, new_rank, reason_day=None):
    new_rank = max(1, min(PLAYER_MAX_RANK, new_rank))
    old = get_consort(cid)['rank']
    run("UPDATE consorts SET rank=?, rank_since_day=? WHERE id=?", (new_rank, reason_day or cur_day(), cid))
    if new_rank > old:
        run("UPDATE consorts SET last_promote_day=? WHERE id=?", (cur_day(), cid))
    c = get_consort(cid)
    if new_rank == RANK_FOUR and old != RANK_FOUR:
        assign_four_word(cid)                                     # 晋四妃：从淑/德/贤/惠里挑还空着的一个当名号
    elif old == RANK_FOUR and new_rank != RANK_FOUR:
        run("UPDATE consorts SET four_word='' WHERE id=?", (cid,))      # 离开四妃，名号让出来
    if new_rank >= 5 and not c['title']:
        assign_title(cid)
    elif new_rank >= 5 and old < 5 <= new_rank < RANK_FOUR and c['title']:
        offer_title_choices(cid)
    if not c['npc_key']:
        run("UPDATE consorts SET peak_rank=MAX(peak_rank, ?) WHERE id=?", (new_rank, cid))
        if new_rank >= 5 and new_rank > c['prestige_top'] and c['user_id']:
            run("UPDATE consorts SET influence=influence+? WHERE id=?", (PROMOTE_INFLUENCE_REWARD, cid))
            notify(cid, f"晋为{RANK_NAMES[new_rank]}，势力 +{PROMOTE_INFLUENCE_REWARD}。", 'good')
        if new_rank > c['prestige_top']:
            gain = sum(v for r_, v in PRESTIGE_RANK_GAIN.items() if c['prestige_top'] < r_ <= new_rank)
            run("UPDATE consorts SET prestige_top=? WHERE id=?", (new_rank, cid))
            if gain: add_prestige(c, gain, f"{full_name(c)}晋为{RANK_NAMES[new_rank]}")
    housing_sync(fill_main=not settling())

def demote_rank(cid):
    """降一级。降到的那一级若已超员，就在这一级所有人里比：圣宠最低的再降一级（同圣宠的，晋这一级最晚的先下），一级一级挤下去，直到有空位。
    被挤下去的别人会收到通知；被降者自己如果在新位分里排最末，同样继续往下。"""
    c = get_consort(cid)
    if not c or c['rank'] <= 1: return
    set_rank(cid, c['rank'] - 1)
    rank = c['rank'] - 1
    while rank > 1 and rank in RANK_SLOTS:
        members = list(q("SELECT * FROM consorts WHERE rank=? AND status NOT IN ('cold','xiunv','dead')", (rank,)))
        if len(members) <= RANK_SLOTS[rank]: break
        worst = min(members, key=lambda m: (m['favor'], -m['rank_since_day'], -m['id']))
        old_name = display_name(worst)
        set_rank(worst['id'], rank - 1)
        if worst['id'] != cid:
            now_name = display_name(get_consort(worst['id']))
            if worst['user_id']:
                notify(worst['id'], f"{RANK_NAMES[rank]}的位子满了，你在同位分里圣宠最低，被挤下一级，今称{now_name}。", 'bad')
            gazette(f"{RANK_NAMES[rank]}名额已满，{old_name}圣宠最低，降为{now_name}。", 'decree')
        rank -= 1

def confine(cid, days=None):
    """禁足统一半天（CONFINE_HOURS 小时），days 只是沿用的旧参数，不再决定时长；到点由 release_confinements 每分钟检查放人"""
    c = get_consort(cid)
    if c['status'] in ('cold', 'dead'): return
    until = max(c['status_until_day'] if c['status'] == 'confined' else 0, cur_day() + 1)    # 按天结算的兜底
    ts = max(c['confine_until_ts'] if c['status'] == 'confined' else 0, now_ts() + CONFINE_HOURS * 3600)
    run("UPDATE consorts SET status='confined', status_until_day=?, confine_until_ts=? WHERE id=?", (until, ts, cid))

@atomic
def release_confinements():
    """禁足满半天就放人（每分钟查一次）"""
    for c in q("SELECT * FROM consorts WHERE status='confined' AND confine_until_ts>0 AND confine_until_ts<=?", (now_ts(),)):
        run("UPDATE consorts SET status='normal', status_until_day=0, confine_until_ts=0 WHERE id=?", (c['id'],))
        if c['user_id']: notify(c['id'], '禁足期满，你又能出门了。', 'good')

def send_to_cold(cid):
    c = get_consort(cid)
    if c['status'] == 'dead': return
    # 废为庶人：封号一并褫夺，出冷宫后要重新挣
    if c['user_id']: add_prestige(c, PRESTIGE_COLD, f"{full_name(c)}被打入冷宫")
    run("""UPDATE consorts SET four_word='', status='cold', status_until_day=?, rank_before_cold=?,
           favor=0, pregnant_since=0, seek_bonus=0, hall='', housing_waiting='', title=? WHERE id=?""",
        (cur_day() + COLD_DAYS, c['rank'], c['title'] if c['npc_key'] else '', cid))
    housing_sync(fill_main=not settling())
    guide_tip(cid, 'cold', '「冷宫的日子不好熬，但没到头呢。多闭门自省，未必没有转机。」')

def release_from_cold(cid, reason):
    c = get_consort(cid)
    if c['npc_key'] or c['status'] == 'dead': return   # NPC 进了冷宫就不再出来
    new_rank = min(2, max(1, c['rank_before_cold']))
    run("""UPDATE consorts SET four_word='', status='normal', status_until_day=0, rank=?, rank_since_day=?,
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
        if request.method not in ('GET','HEAD','OPTIONS') and state()['maintenance'] and request.endpoint!='logout':
            return render_template('maintenance.html'),503,{'Retry-After':'60'}
        c = my_consort()
        if c is None:
            if request.endpoint not in ('create', 'logout', 'reigns', 'memorial', 'clan', 'clans'):
                return redirect(url_for('create'))
        elif c['status'] == 'xiunv' and request.endpoint not in ('dianxuan', 'logout'):
            return redirect(url_for('dianxuan'))
        elif c['status'] == 'dead' and request.endpoint not in ('memorial', 'rebirth', 'logout', 'clan', 'clans', 'family_page', 'reigns'):
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
    ctx = dict(family_career_title=family_career_title, FAMILY_CAREER_TITLES=FAMILY_CAREER_TITLES,family_origin_options=family_origin_options, family_background=family_background,BED_DAILY_MAX=BED_DAILY_MAX, BED_COUNT_WEIGHTS=BED_COUNT_WEIGHTS,badge_name=badge_name, pregnancy_progress=pregnancy_progress, pregnancy_due_text=pregnancy_due_text, bed_chance_text=bed_chance_text, next_bedding_text=next_bedding_text, PROMOTE_INFLUENCE=PROMOTE_INFLUENCE, entry_stat_roll=entry_stat_roll, RANDOM_STAT_RANGES=RANDOM_STAT_RANGES, FAVOR_CARE=FAVOR_CARE, favor_care_tier=favor_care_tier, favor_stipend=favor_stipend, EAST_PALACE_CHANCE=EAST_PALACE_CHANCE, EAST_PALACE_FAVOR=EAST_PALACE_FAVOR, EAST_PALACE_TRUST=EAST_PALACE_TRUST, AGE_YEARS_PER_DAY=AGE_YEARS_PER_DAY, ENERGY_MAX=ENERGY_MAX, dn=display_name, full_name=full_name, RANK_NAMES=RANK_NAMES, STAT_NAMES=STAT_NAMES,
               favor_word=favor_word, trust_word=trust_word, residence_name=residence_name, HALL_NAMES=HALL_NAMES, ITEMS=ITEMS, DRUGS=DRUGS, HOBBIES=HOBBIES, DISPLAY_SLOTS=DISPLAY_SLOTS,
               HOBBY_ENERGY=HOBBY_ENERGY, HOBBY_DAILY_MAX=HOBBY_DAILY_MAX, HOBBY_UNLOCK_ITEMS=HOBBY_UNLOCK_ITEMS, daily_count=daily_count, intrigue_label=intrigue_label, FAMILIES=FAMILIES, PERSONALITIES=PERSONALITIES, age_text=age_text, palace_date=palace_date,
               HEIR_STATS=HEIR_STATS, HEIR_PERSONALITIES=HEIR_PERSONALITIES, gift_word=gift_word, gift_text=gift_text, heir_age_days=heir_age_days,
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

@app.before_request
def maintenance_player_guard():
    endpoint=request.endpoint or ''
    if request.method in ('GET','HEAD','OPTIONS') or not endpoint or endpoint=='static' or endpoint.startswith('admin') or endpoint in ('login','logout'):
        return
    if state()['maintenance']:
        return render_template('maintenance.html'),503,{'Retry-After':'60'}


@app.before_request
def retired_court_features():
    if request.endpoint in {'npc_visit', 'knife_borrow', 'knife_pay'}:
        return '固定妃嫔、借刀和预置皇子抱养玩法已取消。', 410

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        u = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if u and not u['managed'] and check_password_hash(u['password_hash'], password):      # 托管角色没有人能登录
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
        qq_number=request.form.get('qq_number','').strip()
        if not re.fullmatch(r'[1-9][0-9]{4,11}',qq_number):
            flash('请填写具体 QQ 号：5～12 位数字，不能以 0 开头。','bad')
        elif not (2 <= len(username) <= 20):
            flash('账号要 2 到 20 个字。', 'bad')
        elif len(password) < 4:
            flash('密码至少 4 位。', 'bad')
        elif blocked_hit('账号', username):
            flash(BLOCKED_MSG, 'bad')
        elif q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            flash('这个账号已经有人用了。', 'bad')
        else:
            cur = run("INSERT INTO users (username, password_hash, qq_number, created_ts) VALUES (?,?,?,?)",
                      (username, generate_password_hash(password, method='pbkdf2:sha256'), qq_number, now_ts()))
            S.permanent = True
            S['uid'] = cur.lastrowid
            return redirect(url_for('create'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    S.clear()
    return redirect(url_for('login'))

# ── 创建秀女 ───────────────────────────────────────────────────────────────────

# ── 家族（九点九节）：一个账号就是一个家族，跨届一直在 ─────────────────────────────

FAMILY_MAX_MEMBERS = 4          # 每一届最多送四位入宫
FAMILY_MOURN_DAYS = 1           # 死后当天治丧，第二天就能送下一位（2026-09-28 从 2 压到 1）
DOWAGER_DX_BONUS = 10           # 太后的侄女殿选加分
TRUST_DOWAGER, TRUST_DISGRACED = 30, 10
DOWAGER_AUDIENCE_INTERVAL, DOWAGER_AUDIENCE_FAVOR = 3, 10   # 2026-09-28 从 7 压到 3
SHOUKANG_INTERVAL = 3   # 2026-09-28 从 7 压到 3
DOWRY_RATIO, DOWRY_MAX = 0.10, 200
FELLOW_AFFINITY = 20
HEIRLOOM_MAID_LOYALTY = 80
PRESTIGE_DX_STEP, PRESTIGE_DX_MAX = 20, 10         # 每 20 点名望殿选 +1，最多 +10
PRESTIGE_SILVER_MAX = 100                           # 起始银子 + 名望，最多 +100
PRESTIGE_RANK_GAIN = {5: 5, 6: 10, 7: 15, 8: 20, 9: 20, 10: 40}    # 成员第一次晋到该位分给家里的名望
PRESTIGE_BORN_PRINCE, PRESTIGE_PRINCE_TITLE, PRESTIGE_DOWAGER, PRESTIGE_OLD_AGE = 5, 10, 50, 5
PRESTIGE_COLD, PRESTIGE_EXPOSED = -10, -5

SURNAME_POOL = list('江林沈宋顾谢程萧韩魏薛卢尹段姜裴孟柳谭邵白俞秦郑穆蒋许潘戴夏苏陆袁丁莫汪范叶方彭石任钟廖崔贾邹史龙万熊常季严金安尚')

OFFICE_TITLES = ['白身', '九品', '八品', '七品', '六品', '五品', '四品', '三品', '二品', '一品']
OFFICE_MAX = len(OFFICE_TITLES) - 1
TIER_OFFICE = dict(dali=6, jizhou=6, songyang=2, merchant=0, general=7, hanlin=6, physician=3, manchu=5)
TIER_JOB = dict(dali='大理寺', jizhou='济州协领', songyang='松阳县衙', merchant='江南商号', general='镇边军中',
                hanlin='翰林院', physician='太医院', manchu='满洲旗下')
FAMILY_CAREER_TITLES = {
 'dali': ('未仕','录事','主簿','评事','司务','寺丞','少卿','寺卿','部院侍郎','部院尚书'),
 'jizhou': ('营中子弟','笔帖式','骁骑校','防御','佐领','参领','协领','副都统','都统','统领'),
 'songyang': ('乡塾先生','县衙书吏','县衙主簿','县学教谕','县丞','知县','知州','知府','布政使','巡抚'),
 'merchant': ('小商户','铺面掌柜','商号东家','地方大商','商会理事','商会会首','跨府商号东家','跨省商团东家','商帮领袖','商界巨擘'),
 'general': ('军中子弟','伍长','把总','千总','守备','都司','游击','参将','副将','总兵'),
 'hanlin': ('童生','生员','举人','贡士','进士','庶吉士','翰林编修','翰林侍读','翰林学士','文阁大学士'),
 'physician': ('医馆学徒','坐堂医师','地方名医','医馆馆主','府中医官','宫中供奉医师','太医院医官','太医院御医','太医院院判','太医院院使'),
 'manchu': ('公府闲居子弟','公府管事','荫补小吏','荫补主簿','荫补郎官','荫补员外郎','荫补郎中','部院侍郎','部院尚书','文阁大学士'),
}


def family_career_title(fam, level=None):
    level = fam['head_office'] if level is None else level
    tier = 'dali' if fam['career_path']=='civil' else fam['tier']
    title = FAMILY_CAREER_TITLES[tier][max(0,min(OFFICE_MAX,level))]
    if tier in ('dali','jizhou','general','manchu') and level:
        title += ' · '+OFFICE_TITLES[level]
    return title


HEAD_ROLES = ['父亲', '兄长', '侄子', '族叔']         # 家主一代代换：父亲没了是兄长，兄长没了是侄子，再往后是族叔
HEAD_AGE_RANGE = [(46, 56), (26, 36), (20, 28), (40, 55)]
HEAD_GIVEN = ['明德', '守正', '兆麟', '世昌', '怀仁', '延年', '景行', '鸿儒', '子安', '文彬', '崇礼', '嘉树', '绍祖', '惟清', '伯谦']
HEAD_OLD_YEARS, HEAD_OLD_RATE = 55, 0.005           # 家主 55 岁起每晚可能病逝，每多一岁概率 +0.5%
HEAD_ILL_DEATH, HEAD_ILL_RECOVER = 0.20, 0.10       # 病着且没请医时每晚 20% 撒手；自己好转 10%
HEAD_PROMOTE_BASE, HEAD_DEMOTE_BASE = 0.04, 0.010    # 每晚升迁 / 降职的底（试玩里官职一路往下掉，才调成这样）
PRESTIGE_LABELS = [(120, '簪缨世家'), (60, '望族'), (20, '小康之家'), (0, '寒门')]


def consort_uid(c):
    return (c['user_id'] or c['archived_user_id']) if c else None


def family_label(fam):
    """门第档次：名望 + 家主官职（一品 = 72 分）一起看，免得三品将门被叫成寒门"""
    return prestige_label(fam['prestige'] + fam['head_office'] * 8)


def family_row(uid):
    return q("SELECT * FROM families WHERE user_id=?", (uid,), one=True) if uid else None


def prestige_label(p):
    return next(t for lo, t in PRESTIGE_LABELS if p >= lo)


def family_log_add(uid, text, honor=0):
    if not uid: return
    run("INSERT INTO family_log (user_id, reign_no, day, text, honor) VALUES (?,?,?,?,?)",
        (uid, state()['reign_no'], cur_day(), text, honor))


def add_prestige_uid(uid, delta, why=''):
    fam = family_row(uid)
    if not fam or not delta: return
    run("UPDATE families SET prestige=MAX(0, prestige+?) WHERE user_id=?", (int(delta), uid))
    if why: family_log_add(uid, f"{why}（名望 {int(delta):+d}）")


def add_prestige(c, delta, why=''):
    """给这位成员的家族加减名望；NPC 没有家族"""
    if c and not c['npc_key']: add_prestige_uid(consort_uid(c), delta, why)


def head_text(fam):
    return f"{fam['head_role']}{fam['head_name']}（{fam['background']} · {family_career_title(fam)}，{fam['head_age_months'] // 12} 岁）"


def new_head(surname, tier, gen):
    lo, hi = HEAD_AGE_RANGE[min(gen, len(HEAD_AGE_RANGE) - 1)]
    return dict(head_name=surname + random.choice(HEAD_GIVEN), head_role=HEAD_ROLES[min(gen, len(HEAD_ROLES) - 1)],
                head_gen=gen, head_age_months=random.randint(lo, hi) * 12, head_ill_day=0)


def create_family(uid, surname, tier, background=None):
    background = background or family_origin_options(tier,limit=1)[0]
    h = new_head(surname, tier, 0)
    run("""INSERT INTO families (user_id, surname, tier, head_name, head_role, head_gen, head_age_months, head_office, created_ts, background)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (uid, surname, tier, h['head_name'], h['head_role'], 0, h['head_age_months'], TIER_OFFICE[tier], now_ts(), background))


def npc_surnames():
    return set()


def surname_taken(surname):
    return bool(q("SELECT 1 FROM families WHERE surname=?", (surname,), one=True)) or surname in npc_surnames() \
        or bool(q("SELECT 1 FROM consorts WHERE npc_key IS NOT NULL AND surname=?", (surname,), one=True))


def suggest_surnames(n=3):
    free = [s_ for s_ in SURNAME_POOL if not surname_taken(s_)]
    return random.sample(free, min(n, len(free)))


def family_members(uid, reign_no=None):
    sql = "SELECT * FROM consorts WHERE (user_id=? OR archived_user_id=?)"
    args = [uid, uid]
    if reign_no is not None:
        sql += " AND reign_no=?"; args.append(reign_no)
    return list(q(sql + " ORDER BY id", args))


def family_gate(uid):
    """现在能不能再送一位入宫：本届人数、治丧"""
    members = family_members(uid, state()['reign_no'])
    if len(members) >= FAMILY_MAX_MEMBERS:
        return False, f'这一届你家已经送了 {FAMILY_MAX_MEMBERS} 位入宫，都没了，本届门庭凋零。等下一届再送人吧。'
    last = members[-1] if members else None
    if last and last['status'] == 'dead' and cur_day() - last['death_day'] < FAMILY_MOURN_DAYS:
        wait = FAMILY_MOURN_DAYS - (cur_day() - last['death_day'])
        return False, f'家里正在给{full_name(last)}治丧，还要 {wait} 天才能送下一位入宫。'
    return True, ''


def member_class(m):
    reason = m['death_reason'] or ''
    if '圣母皇太后' in reason: return 'dowager'
    if '太妃' in reason: return 'concubine'
    if '押错' in reason or '失势' in reason: return 'disgraced'
    return ''


def family_inheritance(uid, reign_no):
    """上一辈（最近有成员入宫的那一届）里最有分量的一位，决定这位新人的辈分说法和照拂"""
    prev = q("""SELECT MAX(reign_no) r FROM consorts WHERE (user_id=? OR archived_user_id=?) AND reign_no<? AND status!='xiunv'""",
             (uid, uid, reign_no), one=True)['r']
    if not prev: return dict(relative=None, patron='', depth=0)
    order = dict(dowager=0, concubine=1, disgraced=2)
    best = min(family_members(uid, prev), key=lambda m: (order.get(member_class(m), 3), -m['peak_rank'], m['id']))
    return dict(relative=best, patron=member_class(best) if prev == reign_no - 1 else '', depth=reign_no - prev)


def make_lineage(members, inh):
    if not members:
        rel = inh['relative']
        if not rel: return '长女'
        role = dict(dowager='太后', concubine='太妃').get(member_class(rel), RANK_NAMES[rel['peak_rank']])
        word = {1: '侄女', 2: '侄孙女'}.get(inh['depth'], '族中晚辈')
        return f"前朝{role}{full_name(rel)}之{word}"
    prev = members[-1]
    return f"{prev['given']}之妹" if len(members) == 1 else f"{prev['given']}的堂妹"


def heirloom_maids(uid):
    """这一届里已故成员宫里忠心够高的宫人，新人可以带一个过来"""
    ids = [m['id'] for m in family_members(uid, state()['reign_no']) if m['status'] == 'dead']
    if not ids: return []
    marks = ','.join('?' * len(ids))
    return list(q(f"""SELECT * FROM maids WHERE owner_id IN ({marks}) AND status='gone' AND loyalty>=?
                      AND left_reason LIKE '主子没了%' ORDER BY loyalty DESC""", (*ids, HEIRLOOM_MAID_LOYALTY)))


def apply_inheritance(c):
    """入宫那一刻，姐姐留下的东西接上：姐妹情、遗书、旧宫人"""
    try: inh = json.loads(c['inherit'] or '{}')
    except ValueError: inh = {}
    pred = get_consort(inh['from']) if inh.get('from') else None
    if pred:
        for sid in sisters_of(pred['id']):
            s_ = get_consort(sid)
            if s_ and s_['status'] != 'dead' and s_['id'] != c['id']:
                add_affinity(c['id'], sid, FELLOW_AFFINITY)
        if pred['culprit_id']:
            culprit = get_consort(pred['culprit_id'])
            if culprit:
                run("""INSERT INTO letters (from_id, to_id, day, body, sender_label, created_ts) VALUES (0,?,?,?,?,?)""",
                    (c['id'], cur_day(),
                     f"妹妹：姐姐走得不明不白。我生前安了眼线，查到害我的人是{display_name(culprit)}{full_name(culprit)}。"
                     f"这笔账，往后就交给你了。", f"{full_name(pred)}遗书", now_ts()))
                notify(c['id'], f"你收到了姐姐{full_name(pred)}的一封遗书，去「书信」看看。", 'bad')
    if c['heirloom_maid_id']:
        m = get_maid(c['heirloom_maid_id'])
        c = get_consort(c['id'])
        if m and m['status'] == 'gone' and len(active_maids(c['id'])) < maid_quota(c['rank']):
            run("""UPDATE maids SET owner_id=?, status='active', left_day=0, left_reason='', joined_day=? WHERE id=?""",
                (c['id'], cur_day(), m['id']))
            notify(c['id'], f"姐姐宫里的{m['name']}认得你的眉眼，主动跟了过来。", 'good')
        elif m:
            notify(c['id'], f"{m['name']}想跟你过来，可你宫里的宫人名额已满。", 'info')


def family_dx_bonus(fam, patron):
    bonus = min(PRESTIGE_DX_MAX, fam['prestige'] // PRESTIGE_DX_STEP)
    if patron == 'dowager': bonus += DOWAGER_DX_BONUS
    return bonus


@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if g.me is not None:
        return redirect(url_for('index'))
    if state()['mourning']:
        flash('国丧一日，明晚起开下一届选秀。先看看上一届的遗诏吧。', 'info')
        return redirect(url_for('reigns'))
    uid = S['uid']
    fam = family_row(uid)
    entry_stat_roll(uid)
    f = request.form
    if fam is None:                      # 第一次：先定家族的姓氏和门第，定了就不能改
        if request.method == 'POST' and f.get('step') == 'family':
            surname = (f.get('surname_custom', '').strip() or f.get('surname', '').strip())
            tier = f.get('family')
            background = f.get('background_'+str(tier), '').strip()
            err = None
            if not 1 <= len(surname) <= 2: err = '姓氏 1~2 个字。'
            elif blocked_hit('姓氏', surname): err = BLOCKED_MSG
            elif tier not in FAMILIES: err = '请选择门第。'
            elif background and background not in family_origin_options(tier): err = '这份家族出身已被其他玩家选走，请换一份。'
            elif surname_taken(surname): err = f'「{surname}」已经有人家用了（宫里的、别的玩家家族的都算），换一个吧。'
            if err:
                flash(err, 'bad')
                return render_template('create.html', fam=None, choices=suggest_surnames(), form=f)
            create_family(uid, surname, tier, background or None)
            flash(f'{surname}氏一门，{family_row(uid)["background"]}。家里的事，往后都记在族谱上。', 'good')
            return redirect(url_for('create'))
        return render_template('create.html', fam=None, choices=suggest_surnames(), form={})
    ok, why = family_gate(uid)
    if not ok:
        flash(why, 'bad')
        return redirect(url_for('clan'))
    reign_no = state()['reign_no']
    members = family_members(uid, reign_no)
    inh = family_inheritance(uid, reign_no)
    lineage = make_lineage(members, inh)
    if request.method == 'POST' and f.get('step') != 'family':
        given, per = f.get('given', '').strip(), f.get('personality')
        try:
            age = int(f.get('age', 20))
            pts = {}
        except ValueError:
            pts = None
        try: maid_id = int(f.get('heirloom_maid') or 0)
        except ValueError: maid_id = 0
        err = None
        if not 1 <= len(given) <= 3: err = '名 1~3 个字。'
        elif blocked_hit('姓名', fam['surname'] + given): err = BLOCKED_MSG
        elif pts is not None and not 18 <= age <= 22: err = '入宫年龄为十八至二十二岁。'
        elif per not in PERSONALITIES: err = '请选择性格。'
        elif pts is None: err = '年龄格式不正确。'
        elif q("SELECT 1 FROM consorts WHERE surname=? AND given=?", (fam['surname'], given), one=True):
            err = '宫里已经有同名的人了，换个名字吧。'
        elif maid_id and maid_id not in {m['id'] for m in heirloom_maids(uid)}: err = '那位宫人跟不过来。'
        if err:
            flash(err, 'bad')
            return render_template('create.html', fam=fam, form=f, lineage=lineage, heirlooms=heirloom_maids(uid),
                                   inh=inh, members=members, DOWAGER_AUDIENCE_INTERVAL=DOWAGER_AUDIENCE_INTERVAL, SHOUKANG_INTERVAL=SHOUKANG_INTERVAL)
        account = q('SELECT * FROM users WHERE id=?', (uid,), one=True)
        if account['east_palace_reign'] != reign_no:
            old = int(random.random() < EAST_PALACE_CHANCE)
            run('UPDATE users SET east_palace_reign=?,east_palace_old=? WHERE id=?', (reign_no, old, uid))
        else:
            old = account['east_palace_old']
        tier = fam['tier']
        stats = dict(entry_stat_roll(uid))
        for k in stats:
            modifier=FAMILIES[tier]['mods'].get(k,0)+PERSONALITIES[per]['mods'].get(k,0)
            stats[k]+=max(-10,min(10,modifier))
        stats = {k: clamp(v, 5, 100) for k, v in stats.items()}
        pred = members[-1] if members and members[-1]['status'] == 'dead' else None
        dowry = 0
        if pred and pred['silver'] > 0:
            dowry = min(DOWRY_MAX, int(pred['silver'] * DOWRY_RATIO))
            run("UPDATE consorts SET silver=0 WHERE id=?", (pred['id'],))
        silver = FAMILIES[tier]['silver'] + min(PRESTIGE_SILVER_MAX, fam['prestige']) + dowry
        inherit = dict(dowry=dowry, **({'from': pred['id']} if pred else {}))
        run("""INSERT INTO consorts (user_id, surname, given, family, personality,
               appearance, talent, scheme, virtue, health, silver, secret, status, created_ts,
               reign_no, seq, entry_age, lineage, patron, inherit, heirloom_maid_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'xiunv', ?, ?,?,?,?,?,?,?)""",
            (uid, fam['surname'], given, tier, per, stats['appearance'], stats['talent'],
             stats['scheme'], stats['virtue'], stats['health'], silver, roll_secret(), now_ts(),
             reign_no, len(members) + 1, age, lineage, inh['patron'], json.dumps(inherit), maid_id))
        run('UPDATE consorts SET age_months=?,entry_origin=? WHERE user_id=? AND status=?', (age * 12, 'east_palace' if old else 'new', uid, 'xiunv'))
        return redirect(url_for('dianxuan'))
    return render_template('create.html', fam=fam, form={}, lineage=lineage, heirlooms=heirloom_maids(uid),
                           inh=inh, members=members, DOWAGER_AUDIENCE_INTERVAL=DOWAGER_AUDIENCE_INTERVAL, SHOUKANG_INTERVAL=SHOUKANG_INTERVAL)


# ── 家主：会老、会病、会升降，也会来求你 ──────────────────────────────────────────

REQUEST_INTERVAL, REQUEST_CHANCE, REQUEST_DAYS = 4, 0.25, 5
PROMOTE_COST_BASE, PROMOTE_COST_STEP = 60, 25
DEBT_COST_BASE, DEBT_COST_STEP = 50, 8
ILL_COST = 120
BACKING_COST, BACKING_LOCK_DAYS, BACKING_SCOLD = 100, 3, 0.10   # 锁定天数 2026-09-28 从 7 压到 3
BACKING_WIN_OFFICE, BACKING_WIN_PRESTIGE, BACKING_LOSE_OFFICE, BACKING_LOSE_PRESTIGE = 2, 10, 1, 8
SUPPORT_CAP = 15
SEND_MIN, SEND_MAX = 10, 500
SEND_PER_PRESTIGE = 100
WITHDRAW_MAX, WITHDRAW_INTERVAL = 200, 3
PETITION_COST, PETITION_WIN, PETITION_SCOLD, PETITION_INTERVAL = 150, 0.55, 0.20, 3   # 间隔 2026-09-28 从 7 压到 3
VENTURE_MIN, VENTURE_MAX = 50, 400
VENTURE_MAX_OPEN = 2      # 每个人同时最多开几笔生意（2026-10-07 起，原 1 笔）
LETTER_SILVER = (20, 60)

VENTURES = {
    # 三种生意的期望收益按每笔（1 天）算：绸缎庄约 +17%（2026-10-07 起，原 +9%；持平档也改成小赚，不再有「持平」），盐引约 +28%，印子钱约 +44%，险越大赚头越大；
    # 险的两种还要另担御史参奏的风险，所以只有敢赌的人才会选
    'silk':  dict(name='绸缎庄', days=1, scold=0.0, outcomes=[(0.70, 0.25), (0.25, 0.05), (0.05, -0.3)],
                  desc='稳当：七成赚两成半，二成半也能赚半成，一成不到亏三成。不会惹上官司。'),
    'salt':  dict(name='漕运盐引', days=1, scold=0.12, outcomes=[(0.45, 1.0), (0.25, 0.10), (0.20, -0.5), (0.10, -1.0)],
                  desc='有赚头：近半赚一倍，两成半赚一成，两成亏一半，一成血本无归；一成二的可能被御史参一本（名望 −8，信任 −6）。'),
    'usury': dict(name='印子钱', days=1, scold=0.25, outcomes=[(0.42, 2.0), (0.16, 0.10), (0.42, -1.0)],
                  desc='暴利也暴险：四成多翻三倍，一成半赚一成，四成多本金全赔；两成半的可能东窗事发（名望 −15，信任 −8，圣宠 −12，家底抄没一半）。'),
}
FAMILY_LETTER_NEWS = [
    '父兄来信，说朝中近来风向有变，让你在宫里少说多看。',
    '家里来信，说今年收成还好，让你不必挂念，保重身子要紧。',
    '族里长辈捎话：宫里的一举一动，家里都听着，切莫因小失大。',
    '家书里夹着几片晒干的桂花，说是院里那棵树今年开得格外好。',
]


def head_office_level(fam):
    return fam['head_office']


def alive_members(uid):
    return [m for m in family_members(uid) if m['user_id'] and m['status'] in ('normal', 'confined', 'cold')]


def notify_family(uid, text, kind='info'):
    for m in alive_members(uid):
        notify(m['id'], text, kind)


def head_dies(fam, day):
    uid = fam['user_id']
    gen = fam['head_gen'] + 1
    h = new_head(fam['surname'], fam['tier'], gen)
    office = max(0, fam['head_office'] - 1)     # 接班的人官职比上一任低一级
    run("""UPDATE families SET head_name=?, head_role=?, head_gen=?, head_age_months=?, head_ill_day=0, head_office=? WHERE user_id=?""",
        (h['head_name'], h['head_role'], gen, h['head_age_months'], office, uid))
    text = f"{fam['head_role']}{fam['head_name']}病逝，由{h['head_role']}{h['head_name']}接掌家事（{family_career_title(fam,office)}）。"
    family_log_add(uid, text)
    notify_family(uid, f"家里传来讣告：{text}", 'bad')


def family_tick(day):
    """每晚：家主与宫中人物同步增长两岁，可能病、可能没；没病没死的可能升迁或降职；家里也可能来求你"""
    for fam in list(q("SELECT * FROM families")):
        uid = fam['user_id']
        age = fam['head_age_months'] + AGE_MONTHS_PER_DAY
        run("UPDATE families SET head_age_months=? WHERE user_id=?", (age, uid))
        fam = family_row(uid)
        years = age / 12
        ill = bool(fam['head_ill_day'])
        if ill and random.random() < HEAD_ILL_RECOVER:
            run("UPDATE families SET head_ill_day=0 WHERE user_id=?", (uid,))
            notify_family(uid, f"家里来信：{fam['head_role']}的病渐渐好了。", 'good')
            ill = False
        elif not ill and years >= 50 and random.random() < 0.01 * (years - 49):
            run("UPDATE families SET head_ill_day=? WHERE user_id=?", (day, uid))
            notify_family(uid, f"家里来信：{fam['head_role']}病倒了，请医吃药要银子。", 'bad')
            ill = True
        p_die = max(0.0, (years - HEAD_OLD_YEARS) * HEAD_OLD_RATE) + (HEAD_ILL_DEATH if ill else 0)
        if random.random() < p_die:
            head_dies(fam, day)
            continue
        if fam['head_office'] < OFFICE_MAX and years < 66 and random.random() < HEAD_PROMOTE_BASE + min(0.03, fam['prestige'] / 2500):
            run("UPDATE families SET head_office=head_office+1, prestige=prestige+3 WHERE user_id=?", (uid,))
            text = f"{fam['head_role']}{fam['head_name']}升任{family_career_title(fam,fam['head_office']+1)}。"
            family_log_add(uid, text)
            notify_family(uid, f"家里来信：{text}", 'good')
        elif fam['head_office'] > 0 and random.random() < max(0.005, HEAD_DEMOTE_BASE - fam['prestige'] / 8000):
            run("UPDATE families SET head_office=head_office-1, prestige=MAX(0,prestige-3) WHERE user_id=?", (uid,))
            text = f"{fam['head_role']}{fam['head_name']}被降为{family_career_title(fam,fam['head_office']-1)}。"
            family_log_add(uid, text)
            notify_family(uid, f"家里来信：{text}", 'bad')
    family_request_tick(day)


# ── 家里来求助 ────────────────────────────────────────────────────────────────

def request_text(fam, r):
    d = json.loads(r['data'] or '{}')
    role = fam['head_role']
    if r['kind'] == 'promotion':
        return f"{role}来信：想在仕途上再进一步，吏部那边要打点，托你拿 {d['cost']} 两周转。成了家主升一级，不成银子就打了水漂。"
    if r['kind'] == 'trouble':
        return f"{role}在外头闯了祸，被人告到了御史台，托你在皇上跟前说句话。你肯出面，成败看皇上对你的信任；不肯，家里只有硬扛。"
    if r['kind'] == 'debt':
        return f"家里生意周转不开，欠了外债，想跟你借 {d['cost']} 两。"
    if r['kind'] == 'illness':
        return f"{role}病得起不来床，请医吃药要 {d['cost']} 两，托你帮衬。不请医，一天比一天危险。"
    return f"{role}来信问：这场储位之争，咱们家该站哪一边？站对了家里跟着水涨船高，站错了要吃亏。"


def open_request(uid):
    return q("SELECT * FROM family_requests WHERE user_id=? AND status='open' ORDER BY id DESC", (uid,), one=True)


def lapse_request(fam, r, day):
    run("UPDATE family_requests SET status='lapsed' WHERE id=?", (r['id'],))
    uid = fam['user_id']
    if r['kind'] == 'trouble':
        run("UPDATE families SET head_office=MAX(0, head_office-1) WHERE user_id=?", (uid,))
        add_prestige_uid(uid, -2, '家主闯了祸，没人出面说情')
    elif r['kind'] == 'debt':
        add_prestige_uid(uid, -1, '欠了外债，没人接济')
    notify(r['consort_id'], '你迟迟没有回信，家里只好自己想办法了。', 'info')


def family_request_tick(day):
    for fam in list(q("SELECT * FROM families")):
        uid = fam['user_id']
        r = open_request(uid)
        if r:
            if day >= r['expires_day']: lapse_request(fam, r, day)
            continue
        if day - fam['request_day'] < REQUEST_INTERVAL: continue
        mem = [m for m in alive_members(uid) if m['status'] in ('normal', 'confined')]
        if not mem or random.random() >= REQUEST_CHANCE: continue
        c = mem[-1]
        kinds, weights = ['trouble', 'debt'], [2, 2]
        if fam['head_office'] < OFFICE_MAX: kinds.append('promotion'); weights.append(3)
        if fam['head_ill_day']: kinds.append('illness'); weights.append(4)
        rivals = sorted(rival_princes(day), key=heir_standing, reverse=True)
        if rivals and not fam['backing_heir_id']: kinds.append('backing'); weights.append(3)
        kind = random.choices(kinds, weights=weights)[0]
        data = {}
        if kind == 'promotion': data['cost'] = PROMOTE_COST_BASE + PROMOTE_COST_STEP * fam['head_office']
        elif kind == 'debt': data['cost'] = DEBT_COST_BASE + DEBT_COST_STEP * fam['head_office']
        elif kind == 'illness': data['cost'] = ILL_COST
        elif kind == 'backing': data['options'] = [h['id'] for h in rivals[:3]]
        run("INSERT INTO family_requests (user_id, consort_id, kind, day, expires_day, data) VALUES (?,?,?,?,?,?)",
            (uid, c['id'], kind, day, day + REQUEST_DAYS, json.dumps(data)))
        run("UPDATE families SET request_day=? WHERE user_id=?", (day, uid))
        notify(c['id'], f"家里来信了，是求你帮忙的事。去「家里」看看，{REQUEST_DAYS} 天内回信。", 'info')


def scold_chance(base, fam):
    return base * (1 - min(0.5, fam['prestige'] / 200))


def answer_request(c, fam, r, answer, heir_id=0):
    """返回 (提示, 类别)。answer 是 'yes' / 'no'"""
    uid, d, day = fam['user_id'], json.loads(r['data'] or '{}'), cur_day()
    kind = r['kind']
    role = fam['head_role']
    if answer != 'yes':
        run("UPDATE family_requests SET status='declined' WHERE id=?", (r['id'],))
        if kind == 'trouble':
            run("UPDATE families SET head_office=MAX(0, head_office-1) WHERE user_id=?", (uid,))
            add_prestige_uid(uid, -2, f'{role}闯了祸，你没有出面')
            return f'你没有出面。家里硬扛下来，{role}被降了一级，名望 −2。', 'bad'
        if kind == 'debt':
            add_prestige_uid(uid, -1, '欠了外债，你没有接济')
            return '你没有借。家里另想办法，名望 −1。', 'info'
        return '你回信推了。', 'info'
    if kind in ('promotion', 'debt', 'illness'):
        cost = d['cost']
        if c['silver'] < cost: return f'手头只有 {c["silver"]} 两，不够 {cost} 两。', 'bad'
    if kind == 'trouble' and c['energy'] < 1: return '精力不够了。', 'bad'
    if kind == 'backing':
        if heir_id not in d.get('options', []) or not _rival(heir_id):
            return '选一位家里问的那几位阿哥。', 'bad'
    run("UPDATE family_requests SET status='done' WHERE id=?", (r['id'],))
    if kind == 'promotion':
        add_silver(c['id'], -d['cost'])
        if random.random() < min(0.85, 0.5 + fam['prestige'] / 400):
            run("UPDATE families SET head_office=MIN(?, head_office+1) WHERE user_id=?", (OFFICE_MAX, uid))
            add_prestige_uid(uid, 3, f'{role}打点得力，升任{family_career_title(fam,min(OFFICE_MAX,fam["head_office"]+1))}')
            msg, k = f'银子送到了。{role}升任{family_career_title(fam,min(OFFICE_MAX,fam["head_office"]+1))}，名望 +3。', 'good'
        else:
            msg, k = '银子送出去了，却没有下文。这笔钱算是打了水漂。', 'bad'
        if random.random() < scold_chance(0.10, fam):
            add_prestige_uid(uid, -5, '买官的事被御史听说了')
            add_trust(c['id'], -3)
            msg += '偏偏这事被御史听说了，名望 −5，信任 −3。'
        return msg, k
    if kind == 'trouble':
        run('UPDATE consorts SET energy=energy-1 WHERE id=?', (c['id'],))
        if random.random() < plead_chance(c):
            add_prestige_uid(uid, 1, f'你在皇上跟前替{role}说了情')
            return '皇上听了你的话，没有深究。名望 +1。', 'good'
        add_trust(c['id'], -3)
        run("UPDATE families SET head_office=MAX(0, head_office-1) WHERE user_id=?", (uid,))
        add_prestige_uid(uid, -2, f'替{role}说情没能成')
        return f'皇上脸色一沉，没有松口。信任 −3，{role}被降一级，名望 −2。', 'bad'
    if kind == 'debt':
        add_silver(c['id'], -d['cost'])
        add_prestige_uid(uid, 1, '你接济了家里')
        return f'借了 {d["cost"]} 两，家里渡过了难关。名望 +1。', 'good'
    if kind == 'illness':
        add_silver(c['id'], -d['cost'])
        run("UPDATE families SET head_ill_day=0 WHERE user_id=?", (uid,))
        add_prestige_uid(uid, 1, f'你出银子替{role}请了名医')
        return f'{role}吃了药，病去了大半。名望 +1。', 'good'
    run("UPDATE families SET backing_heir_id=?, backing_day=? WHERE user_id=?", (heir_id, day, uid))
    return f'你回信定下：家里这一届站在{heir_full_title(_rival(heir_id))}一边。', 'good'


# ── 家里帮不帮夺嫡 ────────────────────────────────────────────────────────────

def family_backing_id(fam):
    """家里这一届支持哪位阿哥：明说了的；没说就跟着自家的孩子走"""
    if fam['backing_heir_id'] and _rival(fam['backing_heir_id']): return fam['backing_heir_id']
    ids = [m['id'] for m in family_members(fam['user_id'], state()['reign_no'])]
    for h in q("SELECT * FROM heirs WHERE gender='皇子' AND status!='deposed' ORDER BY id"):
        if (h['mother_id'] in ids or h['caretaker_id'] in ids) and heir_age_years(h) >= RIVAL_MIN_AGE:
            return h['id']
    return 0


def family_support(h):
    """外朝助力：站在这位阿哥一边的各家，家主官职越高帮得越多，最多 +15"""
    total = 0
    for fam in q("SELECT * FROM families"):
        if family_backing_id(fam) == h['id']: total += fam['head_office']
    return min(SUPPORT_CAP, total)


def settle_family_backing(winner, day):
    """开匾那晚：站对了的家族家主升官，站错了的降官"""
    for fam in list(q("SELECT * FROM families")):
        bid = family_backing_id(fam)
        if not bid: continue
        uid = fam['user_id']
        if winner and bid == winner['id']:
            run("UPDATE families SET head_office=MIN(?, head_office+?) WHERE user_id=?", (OFFICE_MAX, BACKING_WIN_OFFICE, uid))
            add_prestige_uid(uid, BACKING_WIN_PRESTIGE, f"家里押对了阿哥，{fam['head_role']}{fam['head_name']}连升{BACKING_WIN_OFFICE}级")
            family_log_add(uid, '家里在夺嫡里站对了新帝', 1)
        else:
            run("UPDATE families SET head_office=MAX(0, head_office-?) WHERE user_id=?", (BACKING_LOSE_OFFICE, uid))
            add_prestige_uid(uid, -BACKING_LOSE_PRESTIGE, f"家里押错了阿哥，{fam['head_role']}{fam['head_name']}被新帝贬了一级")
    run("UPDATE families SET backing_heir_id=0, backing_day=0")


# ── 联络家里：送银子、支取、生意、荐官、家书 ──────────────────────────────────────

def _family_actor():
    c = g.me
    fam = family_row(consort_uid(c)) if c else None
    if not c or not fam or c['status'] not in ('normal', 'confined'):
        flash('你现在联络不上家里。', 'bad')
        return None, None
    return c, fam


@app.route('/family')
@login_required
def family_page():
    c = g.me
    uid = consort_uid(c)
    fam = family_row(uid)
    if not fam:
        return redirect(url_for('clan'))
    day = cur_day()
    req = open_request(uid)
    rivals = sorted(rival_princes(day), key=heir_standing, reverse=True)
    backing = family_backing_id(fam)
    ventures = list(q("SELECT * FROM family_ventures WHERE user_id=? AND status='open' ORDER BY id", (uid,)))
    history = list(q("SELECT * FROM family_ventures WHERE user_id=? AND status='done' ORDER BY id DESC LIMIT 6", (uid,)))
    log = list(q("SELECT * FROM family_log WHERE user_id=? ORDER BY id DESC LIMIT 12", (uid,)))
    opts = [_rival(i) for i in json.loads(req['data'] or '{}').get('options', [])] if req and req['kind'] == 'backing' else []
    return render_template('family.html', c=c, fam=fam, head=head_text(fam), req=req, req_text=request_text(fam, req) if req else '',
                           req_opts=[h for h in opts if h], rivals=rivals, backing=backing, ventures=ventures, history=history, log=log,
                           VENTURES=VENTURES, day=day, prestige_label=family_label(fam),
                           can_act=c is not None and c['status'] in ('normal', 'confined'), heir_standing=heir_standing,
                           OFFICE_TITLES=OFFICE_TITLES, TIER_JOB=TIER_JOB, open_venture=sum(1 for v in ventures if v['consort_id'] == c['id']) >= VENTURE_MAX_OPEN,
                           SEND_MIN=SEND_MIN, SEND_MAX=SEND_MAX, SEND_PER_PRESTIGE=SEND_PER_PRESTIGE, WITHDRAW_MAX=WITHDRAW_MAX,
                           WITHDRAW_INTERVAL=WITHDRAW_INTERVAL, PETITION_COST=PETITION_COST, PETITION_INTERVAL=PETITION_INTERVAL,
                           BACKING_COST=BACKING_COST, BACKING_LOCK_DAYS=BACKING_LOCK_DAYS, VENTURE_MIN=VENTURE_MIN, VENTURE_MAX=VENTURE_MAX,
                           daily_count=daily_count, backing_heir=_rival(backing) if backing else None)


def _toint(name, default=0):
    try: return int(request.form.get(name, default))
    except (TypeError, ValueError): return default


@app.route('/family/request/<int:rid>', methods=['POST'])
@login_required
def family_request_answer(rid):
    c, fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    r = q("SELECT * FROM family_requests WHERE id=?", (rid,), one=True)
    if not r or r['user_id'] != fam['user_id'] or r['status'] != 'open':
        flash('这封信已经回过了。', 'bad'); return redirect(url_for('family_page'))
    msg, kind = answer_request(c, fam, r, request.form.get('answer'), _toint('heir_id'))
    flash(msg, kind)
    return redirect(url_for('family_page'))


@app.route('/family/send', methods=['POST'])
@login_required
def family_send():
    c, fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    amt = _toint('amount')
    if not SEND_MIN <= amt <= SEND_MAX: flash(f'一次送 {SEND_MIN}~{SEND_MAX} 两。', 'bad')
    elif c['silver'] < amt: flash(f'手头只有 {c["silver"]} 两。', 'bad')
    elif daily_count(c['id'], 'fam_send'): flash('今天已经往家里送过银子了。', 'bad')
    else:
        add_silver(c['id'], -amt)
        daily_inc(c['id'], 'fam_send')
        run("UPDATE families SET estate=estate+? WHERE user_id=?", (amt, fam['user_id']))
        gain = amt // SEND_PER_PRESTIGE
        if gain: add_prestige_uid(fam['user_id'], gain)
        flash(f"送了 {amt} 两回家，记进家底。" + (f"家里体面了些，名望 +{gain}。" if gain else ''), 'good')
    return redirect(url_for('family_page'))


@app.route('/family/withdraw', methods=['POST'])
@login_required
def family_withdraw():
    c, fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    amt = _toint('amount')
    if not 1 <= amt <= WITHDRAW_MAX: flash(f'一次最多支取 {WITHDRAW_MAX} 两。', 'bad')
    elif amt > fam['estate']: flash(f'家底只有 {fam["estate"]} 两。', 'bad')
    elif cur_day() - fam['withdraw_day'] < WITHDRAW_INTERVAL: flash(f'家里刚给过，{WITHDRAW_INTERVAL} 天才能再取一次。', 'bad')
    else:
        run("UPDATE families SET estate=estate-?, withdraw_day=? WHERE user_id=?", (amt, cur_day(), fam['user_id']))
        add_silver(c['id'], amt)
        flash(f'家里捎来 {amt} 两体己。', 'good')
    return redirect(url_for('family_page'))


@app.route('/family/venture', methods=['POST'])
@login_required
def family_venture():
    c, fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    kind, amt = request.form.get('kind'), _toint('amount')
    v = VENTURES.get(kind)
    err = None
    if not v: err = '选一门生意。'
    elif not VENTURE_MIN <= amt <= VENTURE_MAX: err = f'本金 {VENTURE_MIN}~{VENTURE_MAX} 两。'
    elif c['silver'] < amt: err = f'手头只有 {c["silver"]} 两。'
    elif c['energy'] < 1: err = '精力不够了。'
    elif q("SELECT COUNT(*) n FROM family_ventures WHERE consort_id=? AND status='open'", (c['id'],), one=True)['n'] >= VENTURE_MAX_OPEN: err = f'你已经有 {VENTURE_MAX_OPEN} 笔生意在做了。'
    if err:
        flash(err, 'bad'); return redirect(url_for('family_page'))
    run('UPDATE consorts SET energy=energy-1 WHERE id=?', (c['id'],))
    add_silver(c['id'], -amt)
    run("INSERT INTO family_ventures (user_id, consort_id, kind, principal, start_day, mature_day) VALUES (?,?,?,?,?,?)",
        (fam['user_id'], c['id'], kind, amt, cur_day(), cur_day() + v['days']))
    flash(f"{amt} 两投给了家里的{v['name']}，{v['days']} 天后见分晓。", 'good')
    return redirect(url_for('family_page'))


def family_venture_tick(day):
    for v in list(q("SELECT * FROM family_ventures WHERE status='open' AND mature_day<=?", (day,))):
        cfg = VENTURES[v['kind']]
        fam = family_row(v['user_id'])
        c = get_consort(v['consort_id'])
        roll, rate = random.random(), 0.0
        acc = 0.0
        for p, r_ in cfg['outcomes']:
            acc += p
            if roll < acc:
                rate = r_; break
        if rate > 0 and fam and fam['tier'] == 'merchant': rate *= 1.15
        payout = max(0, v['principal'] + int(round(v['principal'] * rate)))
        alive = c and c['user_id'] and c['status'] != 'dead'
        if alive: add_silver(c['id'], payout)
        elif fam and payout: run("UPDATE families SET estate=estate+? WHERE user_id=?", (payout, fam['user_id']))
        word = f"赚了 {payout - v['principal']} 两" if rate > 0 else ('持平' if rate == 0 else f"亏了 {v['principal'] - payout} 两")
        text = f"家里的{cfg['name']}结账了：本金 {v['principal']} 两，{word}，到手 {payout} 两。"
        scold = fam and cfg['scold'] and random.random() < scold_chance(cfg['scold'], fam)
        if scold:
            loss = 8 if v['kind'] == 'salt' else 15
            add_prestige_uid(fam['user_id'], -loss, f"{cfg['name']}被御史参了一本")
            text += f"偏偏被御史参了一本，名望 −{loss}。"
            if alive:
                add_trust(c['id'], -(6 if v['kind'] == 'salt' else 8))
                if v['kind'] == 'usury':
                    cut_favor(c['id'], FAVOR_LOSS['usury'])
            if v['kind'] == 'usury':
                run("UPDATE families SET estate=estate/2 WHERE user_id=?", (fam['user_id'],))
                text += '家底被抄没了一半。'
        run("UPDATE family_ventures SET status='done', result=? WHERE id=?", (text, v['id']))
        if alive: notify(c['id'], text, 'good' if rate > 0 and not scold else 'bad')


@app.route('/family/enter_civil', methods=['POST'])
@login_required
def family_enter_civil():
    c,fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    if fam['tier']!='merchant' or fam['career_path']=='civil':
        flash('这条入仕途径只对尚未入仕的商贾家族开放。','bad')
    elif fam['head_office']<4 or fam['prestige']<20:
        flash('需要商势达到商会理事、家族名望20，才能申请入仕。','bad')
    elif c['silver']<200 or c['energy']<1:
        flash('入仕需要200两银子和1精力。','bad')
    else:
        add_silver(c['id'],-200)
        run('UPDATE consorts SET energy=energy-1 WHERE id=?',(c['id'],))
        run("UPDATE families SET career_path='civil',head_office=1 WHERE user_id=?",(fam['user_id'],))
        family_log_add(fam['user_id'],'家主经荐举入仕，从录事起步，转入文官路线。')
        flash('家主获荐入仕，从录事起步，今后沿文官路线发展。','good')
    return redirect(url_for('family_page'))


@app.route('/family/petition', methods=['POST'])
@login_required
def family_petition():
    c, fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    day = cur_day()
    err = None
    if fam['head_office'] >= OFFICE_MAX: err = '家主已到这条发展路线的最高级。'
    elif c['silver'] < PETITION_COST: err = f'银子不够，要 {PETITION_COST} 两。'
    elif c['energy'] < 1: err = '精力不够了。'
    elif day - fam['petition_day'] < PETITION_INTERVAL: err = f'刚打点过，{PETITION_INTERVAL} 天后才能再来。'
    if err:
        flash(err, 'bad'); return redirect(url_for('family_page'))
    run('UPDATE consorts SET energy=energy-1 WHERE id=?', (c['id'],))
    add_silver(c['id'], -PETITION_COST)
    run("UPDATE families SET petition_day=? WHERE user_id=?", (day, fam['user_id']))
    role = fam['head_role']
    if random.random() < PETITION_WIN:
        run("UPDATE families SET head_office=head_office+1 WHERE user_id=?", (fam['user_id'],))
        add_prestige_uid(fam['user_id'], 3, f"{role}得了荐举，升任{family_career_title(fam,fam['head_office']+1)}")
        msg, kind = f"你托人在朝中递了话，{role}升任{family_career_title(fam,fam['head_office']+1)}，名望 +3。", 'good'
    else:
        msg, kind = '银子花出去了，吏部那边没有回音。', 'bad'
    if random.random() < scold_chance(PETITION_SCOLD, fam):
        add_prestige_uid(fam['user_id'], -8, '荐官的事被御史弹劾')
        add_trust(c['id'], -5)
        msg += '偏偏被御史弹劾了，名望 −8，信任 −5。'
        kind = 'bad'
    flash(msg, kind)
    return redirect(url_for('family_page'))


@app.route('/family/letter', methods=['POST'])
@login_required
def family_letter():
    c, fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    if c['energy'] < 1: flash('精力不够了。', 'bad'); return redirect(url_for('family_page'))
    if daily_count(c['id'], 'fam_letter'): flash('今天已经写过家书了。', 'bad'); return redirect(url_for('family_page'))
    run('UPDATE consorts SET energy=energy-1 WHERE id=?', (c['id'],))
    daily_inc(c['id'], 'fam_letter')
    r = random.random()
    if r < 0.35:
        npcs = [n for n in q("SELECT * FROM consorts WHERE npc_key IS NOT NULL AND status!='dead' AND 1=1")
                if not q("SELECT 1 FROM known_secrets WHERE knower_id=? AND target_id=?", (c['id'], n['id']), one=True)]
        if npcs:
            n = random.choice(npcs)
            run("INSERT OR IGNORE INTO known_secrets (knower_id, target_id, day) VALUES (?,?,?)", (c['id'], n['id'], cur_day()))
            flash(f"{fam['head_role']}托人打听到了：{display_name(n)}{SECRETS[n['secret']]['name']}。", 'good')
            return redirect(url_for('family_page'))
    if r < 0.70:
        amt = random.randint(*LETTER_SILVER)
        add_silver(c['id'], amt)
        flash(f"家书里夹着 {amt} 两体己。", 'good')
    else:
        flash(random.choice(FAMILY_LETTER_NEWS), 'info')
    return redirect(url_for('family_page'))


@app.route('/family/backing', methods=['POST'])
@login_required
def family_backing():
    c, fam = _family_actor()
    if not c: return redirect(url_for('family_page'))
    hid = _toint('heir_id')
    h = _rival(hid) if hid else None
    day = cur_day()
    err = None
    if hid and not h: err = f'要 {RIVAL_MIN_AGE} 岁以上、没被废黜的阿哥。'
    elif c['silver'] < BACKING_COST: err = f'银子不够，要 {BACKING_COST} 两打点。'
    elif c['energy'] < 1: err = '精力不够了。'
    elif fam['backing_day'] and day - fam['backing_day'] < BACKING_LOCK_DAYS: err = f'刚表过态，{BACKING_LOCK_DAYS} 天内不能改。'
    if err:
        flash(err, 'bad'); return redirect(url_for('family_page'))
    run('UPDATE consorts SET energy=energy-1 WHERE id=?', (c['id'],))
    add_silver(c['id'], -BACKING_COST)
    run("UPDATE families SET backing_heir_id=?, backing_day=? WHERE user_id=?", (hid, day, fam['user_id']))
    msg = f"家里定下支持{heir_full_title(h)}，家主的官职会成为他的助力。" if h else '家里这一届谁也不押，由着自家的孩子走。'
    if h and random.random() < scold_chance(BACKING_SCOLD * (2.5 if heir_faction_count(h) > FACTION_SCOLD else 1), fam):
        add_prestige_uid(fam['user_id'], -5, '家里明着站队，被御史参了结党')
        run("UPDATE families SET head_office=MAX(0, head_office-1) WHERE user_id=?", (fam['user_id'],))
        msg += f"偏偏被御史参了结党，{fam['head_role']}被降一级，名望 −5。"
    flash(msg, 'good')
    return redirect(url_for('family_page'))


# ── 太后侄女、太妃侄女的照拂 ─────────────────────────────────────────────────────

def family_patron_tick(day):
    """太后的侄女每 3 天被召去说话一次，圣宠 +10"""
    for c in q("SELECT * FROM consorts WHERE patron='dowager' AND user_id IS NOT NULL AND status='normal' AND entered_day<?", (day,)):
        if (day - c['entered_day']) % DOWAGER_AUDIENCE_INTERVAL == 0:
            add_favor(c['id'], DOWAGER_AUDIENCE_FAVOR, gain_mult=False)
            notify(c['id'], f"太后召你去慈宁宫说话，赏了茶点。圣宠 +{DOWAGER_AUDIENCE_FAVOR}。", 'good')


def do_shoukang(c, cfg):
    day = cur_day()
    if c['patron'] != 'concubine': raise Reject('你姑母不是太妃，用不着去寿康宫。')
    if day - c['shoukang_day'] < SHOUKANG_INTERVAL:
        raise Reject(f"刚去过寿康宫，{SHOUKANG_INTERVAL - (day - c['shoukang_day'])} 天后才好再去。")
    charge(c, cfg)
    run("UPDATE consorts SET shoukang_day=? WHERE id=?", (day, c['id']))
    npcs = [n for n in q("SELECT * FROM consorts WHERE npc_key IS NOT NULL AND status!='dead' AND 1=1")
            if not q("SELECT 1 FROM known_secrets WHERE knower_id=? AND target_id=?", (c['id'], n['id']), one=True)]
    if not npcs: return '姑母拉着你说了半天旧事，都是些无关紧要的闲话。', 'info'
    n = random.choice(npcs)
    run("INSERT OR IGNORE INTO known_secrets (knower_id, target_id, day) VALUES (?,?,?)", (c['id'], n['id'], day))
    return f"太妃拉着你的手，悄悄说起一件旧事：{display_name(n)}{SECRETS[n['secret']]['name']}。", 'good'


# ── 家族发达了，定期送钱来 ────────────────────────────────────────────────────────

REMIT_INTERVAL = 3            # 每 3 天一次（2026-09-28 从 5 压到 3）
REMIT_PER_OFFICE, REMIT_PRESTIGE_DIV, REMIT_MAX = 8, 10, 150
REMIT_MIN_OFFICE, REMIT_MIN_PRESTIGE = 2, 30            # 家主至少七品，或名望够了，家里才有余钱


def remit_amount(fam):
    if fam['head_office'] < REMIT_MIN_OFFICE and fam['prestige'] < REMIT_MIN_PRESTIGE: return 0
    amt = fam['head_office'] * REMIT_PER_OFFICE + fam['prestige'] // REMIT_PRESTIGE_DIV
    if fam['tier'] == 'merchant': amt = int(amt * 1.2)
    if fam['head_ill_day']: amt //= 2                    # 家主病着，家里的钱都花在药上
    return min(REMIT_MAX, amt)


def family_remit_tick(day):
    if day % REMIT_INTERVAL: return
    for fam in q("SELECT * FROM families"):
        amt = remit_amount(fam)
        mem = [m for m in alive_members(fam['user_id']) if m['status'] in ('normal', 'confined')]
        if not amt or not mem: continue
        c = mem[-1]
        add_silver(c['id'], amt)
        notify(c['id'], f"家里托人送来 {amt} 两体己。{fam['head_role']}说，家里一切都好。", 'good')


def _clan_context(uid):
    fam = family_row(uid)
    if not fam: return None
    members = [m for m in family_members(uid) if m['status'] != 'xiunv']
    groups = {}
    for m in members: groups.setdefault(m['reign_no'], []).append(m)
    honors = list(q("SELECT * FROM family_log WHERE user_id=? AND honor=1 ORDER BY id DESC", (uid,)))
    log = list(q("SELECT * FROM family_log WHERE user_id=? AND honor=0 ORDER BY id DESC LIMIT 15", (uid,)))
    return dict(fam=fam, groups=sorted(groups.items(), reverse=True), honors=honors, log=log, uid=uid,
                tier_name=FAMILIES[fam['tier']]['name']+' · '+fam['background'], prestige_label=family_label(fam),
                head=head_text(fam), mine=(uid == S.get('uid')), RANK_NAMES=RANK_NAMES, json=json)


@app.route('/clan')
@login_required
def clan():
    ctx = _clan_context(S['uid'])
    if not ctx:
        return redirect(url_for('create'))
    return render_template('clan.html', c=g.me, **ctx)


@app.route('/clan/<int:uid>')
@login_required
def clan_of(uid):
    ctx = _clan_context(uid)
    if not ctx:
        flash('没有这户人家。', 'bad')
        return redirect(url_for('clans'))
    return render_template('clan.html', c=g.me, **ctx)


@app.route('/clans')
@login_required
def clans():
    rows = []
    for fam in q("SELECT * FROM families ORDER BY prestige DESC, user_id"):
        ms = [m for m in family_members(fam['user_id']) if m['status'] != 'xiunv']
        rows.append(dict(fam=fam, n=len(ms), alive=any(m['user_id'] and m['status'] != 'dead' for m in ms),
                         tier_name=FAMILIES[fam['tier']]['name']+' · '+fam['background'], label=family_label(fam)))
    return render_template('clans.html', c=g.me, rows=rows, mine=S['uid'])


@app.route('/dianxuan', methods=['GET', 'POST'])
@login_required
def dianxuan():
    if state()['mourning']:
        flash('国丧一日，明晚起开下一届选秀。', 'info')
        return redirect(url_for('reigns'))
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
        fam = family_row(consort_uid(c))
        total += FAMILIES[c['family']]['dx'] + (family_dx_bonus(fam, c['patron']) if fam else 0)
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
        if c['entry_origin'] == 'east_palace': favor += EAST_PALACE_FAVOR
        trust0 = {'dowager': TRUST_DOWAGER, 'disgraced': TRUST_DISGRACED}.get(c['patron'], TRUST_START)
        if c['entry_origin'] == 'east_palace': trust0 = min(100, trust0 + EAST_PALACE_TRUST)
        run("""UPDATE consorts SET status='normal', rank=?, rank_since_day=?, palace=?, hall=?, favor=?,
               entered_day=?, dianxuan_score=?, energy=?, trust=?, last_audience_day=?, recap_seen_day=?,
               dianxuan_quote=?, peak_rank=?, prestige_top=? WHERE id=?""",
            (rank, day, palace, hall, favor, day, total, ENERGY_MAX, trust0, day, day - 1, quote, rank, rank, c['id']))
        title = ''
        if rank >= 4 or (rank == 3 and random.random() < 0.3):
            title = assign_title(c['id'])
        c = get_consort(c['id'])
        decree = f"{family_background(c)}之女{full_name(c)}，留牌子，" \
                 f"{'赐封号「' + title + '」，' if title else ''}封为{display_name(c)}，赐居{palace}{HALL_NAMES[hall]}。"
        gazette(f"殿选：{decree}", 'decree')
        notify(c['id'], f"殿选中选。{decree}", 'decree')
        if c['lineage'].startswith('前朝'):
            notify(c['id'], f"你是{c['lineage']}。" + {'dowager': '太后念着娘家的情分，会照拂你。', 'concubine': '太妃姑母在寿康宫等着你去请安。',
                                                      'disgraced': '只是姑母那一辈站错了队，新帝对你家有成见。'}.get(c['patron'], ''), 'info')
        apply_inheritance(c)
        guide_start(c['id'])
        guide_tip(c['id'], 'help', '「规矩多，一时记不全。页脚有一页『玩法说明』，位分、银子、算计、子嗣、夺嫡都写在里头，遇事翻一翻。」')
        guide_tip(c['id'], 'family', '「宫里的俸禄只够过日子。缺银子了，去『家里』看看：往家里递个话、投一笔生意，家里有难处也会来求你，帮得上忙的，往后都是你的靠山。」')
        if risky_huafei and npc_row('huafei'):
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
        promo = dict(influence=PROMOTE_INFLUENCE[nxt], rank=RANK_NAMES[nxt], favor=promote_favor_need(c, nxt), virtue=promote_virtue_need(nxt),
                     slot=slot_free(nxt, c['id']))
        promo['met'] = c['favor'] >= promo['favor'] and c['virtue'] >= promo['virtue'] and c['influence'] >= promo['influence']
        if promo['met'] and not promo['slot']:      # 条件都够了，只差名额：首页单独弹一条提示，列出现在占着名额的人
            holders = q("SELECT * FROM consorts WHERE rank=? AND status NOT IN ('cold','xiunv','dead') AND id!=? ORDER BY favor DESC", (nxt, c['id']))
            promo['holders'] = [display_name(x) for x in holders]
            promo['cap'] = RANK_SLOTS.get(nxt)
    heirs = q("SELECT * FROM heirs WHERE mother_id=? ORDER BY id", (c['id'],))
    maid_gap = 0 if c['status'] == 'cold' else maid_quota(c['rank']) - len(active_maids(c['id']))
    unnamed_heirs = [h for h in heirs if not h['name']]
    for h in unnamed_heirs: ensure_name_choices(h['id'])      # 老档里没点过字的，补上，提醒才有的选
    confine_until = datetime.fromtimestamp(c['confine_until_ts'], TZ).strftime('%m-%d %H:%M') if c['confine_until_ts'] else ''
    return render_template('index.html', DYING_HOURS=DYING_HOURS, HEALTH_DYING_AT=HEALTH_DYING_AT, c=c, msgs=msgs, promo=promo, heirs=heirs, edict=edict, maid_gap=maid_gap, unnamed_heirs=unnamed_heirs, confine_until=confine_until,
                           sick=is_sick(c), eyes=eyes_active(c), secret=SECRETS[c['secret']], guide=guide_view(c),
                           day=day, PREGNANCY_DAYS=PREGNANCY_DAYS, tiles=map_tiles(c))

@app.route('/guide/skip', methods=['POST'])
@login_required
def guide_skip():
    run("UPDATE consorts SET guide_step=-1 WHERE id=?", (g.me['id'],))
    m = mama_of(g.me)
    flash(m['name'] + m['skip'], 'info')
    return redirect(url_for('index'))

class Reject(Exception):
    pass

def action_config(c, key):
    cfg = ACTIONS.get(key)
    if cfg and key == 'visit' and daily_count(c['id'], 'visit') == 0:
        return dict(cfg, energy=0)
    return cfg


def pick_audience(pool, day):
    overdue = [c for c in pool if day - c['last_audience_day'] >= AUDIENCE_WAIT_DAYS]
    if overdue:
        # 久未见驾先轮到；等待相同者仍按原权重抽签。
        oldest = min(c['last_audience_day'] for c in overdue)
        pool = [c for c in overdue if c['last_audience_day'] == oldest]
    return random.choices(pool, weights=[audience_weight(c, day) for c in pool])[0]


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
    cfg = action_config(c, key)
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
        if cfg.get('min_rank') and c['rank'] < cfg['min_rank']:
            raise Reject(f"要{RANK_NAMES[cfg['min_rank']]}位以上才能做这件事。")
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
        feed_for_action(c, key)
        if key in REQ_LABELS: guide_mark(c['id'], key)
        if getattr(g, 'scene_started', False):
            return redirect(url_for('scene'))
        flash(msg, kind)
    except Reject as e:
        flash(str(e), 'bad')
    back = request.form.get('back', '')
    if back in PLACES:
        return redirect(url_for('place', key=back, **({'living': 1} if key == 'pray' else {})))
    if back == 'maids': return redirect(url_for('maids_page'))
    return redirect(url_for('social') if back == 'social' else url_for('index'))

def do_greet(c, cfg):
    charge(c, cfg)
    run('UPDATE consorts SET influence=influence+1 WHERE id=?',(c['id'],))
    gain = 2 if c['personality'] == 'dignified' else 1
    add_stat(c['id'], 'virtue', gain)
    run("UPDATE consorts SET greet_day=?, missed_greet=0 WHERE id=?", (cur_day(), c['id']))
    msg = f"你到礼仪堂参加了晨省。德行 +{gain}。"
    if random.random() < ADVENTURE_ROAD_CHANCE:      # 请安路上碰上一件小事；场景会盖住这条 flash，所以晨省的结果改发消息
        notify(c['id'], msg, 'good')
        start_scene(c['id'], random.choice(ADVENTURE_ROAD))
        return '', 'info'
    return msg, 'good' 

def do_study(c, cfg):
    art = request.form.get('art')
    if art not in ARTS:
        raise Reject('选一门要修习的才艺。')
    charge(c, cfg)
    gain = 2 if c['talent'] < 60 else 1
    if c['personality'] == 'clever': gain += 1
    if has_maid_trait(c['id'], 'shouqiao'): gain += 1       # 手巧的宫人研墨递琴，帮着练
    add_stat(c['id'], 'talent', gain)
    arts = arts_of(c)
    before = arts.get(art, 0)
    arts[art] = before + 1
    run("UPDATE consorts SET arts=? WHERE id=?", (json.dumps(arts, ensure_ascii=False), c['id']))
    msg = f"你练了一日{art}。才艺 +{gain}。"
    if before < ART_MASTERY <= arts[art]:
        msg += f"你的{art}已臻精通。"
        gazette(f"听说{display_name(c)}的{art}已臻化境。")
    if c['status'] == 'normal':
        favor_gain = add_favor(c['id'], STUDY_FAVOR_GAIN)
        msg += f'修习有成，圣宠 +{favor_gain}。'
    if art == state()['emperor_pref'] and c['status'] == 'normal':
        add_favor(c['id'], 3)
        msg += "皇上近来正喜欢这个，有人把你练习的事传到了养心殿。圣宠 +3。"
    return msg, 'good'


def do_perform(c, cfg):
    if emperor_ill(): raise Reject('皇上病重，暂不安排御前才艺。')
    art = request.form.get('art') if has_request_context() else random.choice(ARTS)
    if art not in ARTS: raise Reject('选一样要在御前展示的才艺。')
    if art == c['last_perform_art']: raise Reject(f'上一回你献的就是{art}，皇上刚听过，换一样才艺吧。')
    charge(c, cfg)
    run('UPDATE consorts SET last_perform_art=? WHERE id=?', (art, c['id']))
    success = random.random() < min(.85, .40 + c['talent'] / 200)
    gain = add_favor(c['id'], random.randint(12,18) if success else 3)
    return f"你向皇上展示{art}，{'赢得赞许' if success else '略有失误，仍被记住'}。圣宠 +{gain}。", 'good'


SCHEME_STUDY_CHANCE = [(50, 1.0), (70, 0.6), (90, 0.35), (101, 0.15)]


def scheme_study_chance(v):
    for th, p in SCHEME_STUDY_CHANCE:
        if v < th: return p


def do_schemestudy(c, cfg):
    charge(c, cfg)
    if random.random() < scheme_study_chance(c['scheme']):
        add_stat(c['id'], 'scheme', 1)
        return '你翻了一日史书兵法，琢磨着前人的算计。心计 +1。', 'good'
    return '你翻了一日史书兵法，只觉意犹未尽，却没悟出什么新东西。', 'info'


def do_palace_work(c, cfg):
    charge(c, cfg)
    run('UPDATE consorts SET influence=influence+3 WHERE id=?', (c['id'],))
    add_stat(c['id'], 'virtue', 1)
    return '你协助整理宫务，势力 +3、德行 +1。', 'good'


def do_aid(c, cfg):
    target = pick_target(c)
    if not target['user_id'] or target['status'] not in ('normal','confined'):
        raise Reject('只能帮助在宫中或禁足中的玩家。')
    charge(c, cfg)
    run('UPDATE consorts SET influence=influence+3 WHERE id=?', (c['id'],))
    add_stat(c['id'], 'virtue', 1)
    add_stat(target['id'], 'health', 3)
    notify(target['id'], f"{display_name(c)}送来了日常补养，体质 +3。", 'good')
    return '你为姐妹送去补养，势力 +3、德行 +1，对方体质 +3。', 'good'


GROOM_LOOKS_CAP = 65     # 梳妆保养能把自己的容貌养到的上限

def do_groom(c, cfg):
    charge(c, cfg)
    gain = 2 if c['appearance'] < 70 else 1
    if has_maid_trait(c['id'], 'shouqiao'): gain += 1       # 手巧的宫人帮着梳妆
    gain = max(0, min(gain, GROOM_LOOKS_CAP - c['appearance']))     # 自己梳妆打扮最多把容貌养到 65
    if gain: add_stat(c['id'], 'appearance', gain)
    add_stat(c['id'], 'health', 3)
    if not gain: return f"你细细梳妆，只是这张脸光靠打扮已经到头了（容貌最多养到 {GROOM_LOOKS_CAP}）。体质 +3。", 'good'
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
    run("UPDATE consorts SET eyes_until_day=? WHERE id=?", (cur_day() + EYES_DAYS - 1, c['id']))
    return f"你打点了几个宫人做眼线，接下来{EYES_DAYS}天宫里的风吹草动都瞒不过你。", 'good'

SEEK_SCENE_CHANCE = 0.3   # 皇上心情平和时，送汤羹有三成会被留下（yangxin_emperor 场景）

SEEK_TRUST_GAIN = 1      # 送汤羹见到皇上、圣宠有涨时附带的信任（皇上发火那次没有）

def do_seek(c, cfg):
    if emperor_ill():
        raise Reject('皇上病重，不见外人。要尽心就去侍疾。')
    charge(c, cfg)
    mood = state()['emperor_mood']
    run("UPDATE consorts SET seek_bonus=seek_bonus+15 WHERE id=?", (c['id'],))
    if mood == '大悦':
        g_ = add_favor(c['id'], random.randint(10, 15)); add_trust(c['id'], SEEK_TRUST_GAIN)
        return f"皇上心情正好，留你说了会儿话。圣宠 +{g_}，信任 +{SEEK_TRUST_GAIN}。", 'good'
    if mood == '平和':
        if random.random() < SEEK_SCENE_CHANCE:
            start_scene(c['id'], 'yangxin_emperor')
            return '', 'info'
        g_ = add_favor(c['id'], random.randint(8, 12)); add_trust(c['id'], SEEK_TRUST_GAIN)
        return f"御前总管接了汤羹，说皇上喝着很合口。圣宠 +{g_}，信任 +{SEEK_TRUST_GAIN}。", 'good'
    if mood == '烦闷':
        if random.random() < 0.5:
            return "御前总管说皇上在批折子，汤羹放下就走吧。", 'info'
        g_ = add_favor(c['id'], random.randint(8, 12)); add_trust(c['id'], SEEK_TRUST_GAIN)
        return f"皇上心里烦，喝了你的汤倒舒坦了些。圣宠 +{g_}，信任 +{SEEK_TRUST_GAIN}。", 'good'
    start_scene(c['id'], 'seek_angry')
    return '', 'info'

def do_garden(c, cfg):
    charge(c, cfg)
    events = [('emperor', 18 + c['appearance'] / 6 + c['talent'] / 10), ('flower', 22), ('secret', 12),
              ('quiet', 18), ('meet', 12), ('adventure', ADVENTURE_GARDEN_WEIGHT)]
    ev = random.choices([e for e, _ in events], weights=[w for _, w in events])[0]
    if ev == 'emperor':
        start_scene(c['id'], pick_scene(EMPEROR_SCENES))
        return '', 'info'
    if ev == 'adventure':
        start_scene(c['id'], random.choice(ADVENTURE_GARDEN))
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
            return f"你在假山后听见{display_name(t)}的宫女在嚼舌根：原来她{SECRETS[t['secret']]['name']}。", 'good'
        return "你在假山后听见有人在说话，走近却没了人影。", 'info'
    if ev == 'npc':
        key = pick_scene(NPC_SCENES)
        if key:
            start_scene(c['id'], key)
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
    if t['status'] == 'confined':
        remember(c['id'], t['id'], 'visit_cold')
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
    p = spy_success_p(c, t, m)
    if random.random() < p:
        run("INSERT OR IGNORE INTO known_secrets (knower_id, target_id, day) VALUES (?,?,?)",
            (c['id'], t['id'], cur_day()))
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

CHASTISE_MODES = ('kneel', 'fine', 'confine')
CHASTISE_FAVOR, CHASTISE_FINE, CHASTISE_AFFINITY, CHASTISE_INFLUENCE = 8, 80, -10, 3

def chastise_targets(c):
    return [t for t in q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status IN ('normal','confined') AND rank<5""", (c['id'],))
            if t['rank'] < c['rank'] and not t['npc_key'] and daily_count(t['id'], 'chastised') == 0]

def do_chastise(c, cfg):
    if c['rank'] < cfg['min_rank']:
        raise Reject(f"要{RANK_NAMES[cfg['min_rank']]}位以上才能责罚低位妃嫔。")
    t = pick_target(c)
    mode = request.form.get('mode', '')
    if mode not in CHASTISE_MODES: raise Reject('选一种责罚：罚跪、罚俸，或者禁足。')
    if t['rank'] >= 5 or t['rank'] >= c['rank']: raise Reject('只能责罚嫔位以下、位分比你低的人。')
    if t['status'] not in ('normal', 'confined'): raise Reject('她眼下不在宫里当差，罚不了。')
    if daily_count(t['id'], 'chastised'): raise Reject('她今天已经被责罚过了，别太过了。')
    if mode == 'confine' and t['status'] == 'confined': raise Reject('她已经在禁足了。')
    charge(c, cfg)
    daily_inc(t['id'], 'chastised')
    me = display_name(c)
    if mode == 'kneel':
        lost = cut_favor(t['id'], CHASTISE_FAVOR)
        pen, what = f"圣宠 -{lost}", '罚跪'
    elif mode == 'fine':
        fined = min(CHASTISE_FINE, t['silver'])
        add_silver(t['id'], -fined)
        pen, what = f"银子 -{fined}", '罚俸'
    else:
        confine(t['id'])
        pen, what = '禁足半天', '禁足'
    add_affinity(c['id'], t['id'], CHASTISE_AFFINITY)
    run('UPDATE consorts SET influence=influence+? WHERE id=?', (CHASTISE_INFLUENCE, c['id']))
    notify(t['id'], f"{me}寻了个由头责罚你：{what}。{pen}。", 'bad')
    if mode == 'kneel': gazette(f"{me}寻了个由头，罚{display_name(t)}在院中跪了半日。", 'news')
    return f"你寻了个由头责罚了{display_name(t)}（{what}），对方{pen}，双方好感 {CHASTISE_AFFINITY}，你势力 +{CHASTISE_INFLUENCE}。", 'info'


def do_pizhe(c, cfg):
    if c['rank'] < cfg['min_rank']:
        raise Reject(f"要{RANK_NAMES[cfg['min_rank']]}位以上才能陪皇上批折子。")
    if emperor_ill():
        raise Reject('皇上病重，不见外人。要尽心就去侍疾。')
    charge(c, cfg)
    if state()['emperor_mood'] == '震怒':
        add_trust(c['id'], 1)
        run('UPDATE consorts SET influence=influence+2 WHERE id=?', (c['id'],))
        return '皇上正在气头上，你只在一旁默默研墨，一个字也没敢多说。信任 +1，势力 +2。', 'info'
    g_ = add_favor(c['id'], random.randint(10, 14))
    add_trust(c['id'], 2)
    run('UPDATE consorts SET influence=influence+4 WHERE id=?', (c['id'],))
    return f"你在养心殿陪皇上批了半日折子，研墨添香，皇上偶尔抬头与你说两句朝中的事。圣宠 +{g_}，信任 +2，势力 +4。", 'good'


def do_attend(c, cfg):
    if not emperor_ill():
        raise Reject('皇上龙体安康，用不着侍疾。')
    charge(c, cfg)
    if random.random() < plead_chance(c):
        add_trust(c['id'], ATTEND_TRUST_GAIN)
        kids = list(q("SELECT * FROM heirs WHERE caretaker_id=? AND gender='皇子' AND status!='deposed' AND adult_day>=0", (c['id'],)))
        for h in kids: add_merit(h['id'], ATTEND_HEIR_GAIN)
        extra = f"，你抚养的{len(kids)}位阿哥圣眷 +{ATTEND_HEIR_GAIN}" if kids else ''
        return f"你在榻前伺候汤药，皇上睁眼看了你一眼，什么也没说。信任 +{ATTEND_TRUST_GAIN}{extra}。", 'good'
    return '御前总管拦在殿外：「皇上需要静养，小主的心意奴才转达。」', 'info'


# ── 宫里的日常开销：饮食、维修、礼佛 ─────────────────────────────────────────────

DIET_RATIO = 0.4        # 普通饮食每晚花掉例银的四成，奢华 2.5 倍、节俭四成
DIETS = {
    'frugal': dict(name='节俭', mult=0.4, order=0, desc='清粥小菜，省钱，只是身子扛不住：每晚体质 −5（最低到 20）。'),
    'normal': dict(name='普通', mult=1.0, order=1, desc='按位分的份例吃，不好不坏。'),
    'lavish': dict(name='奢华', mult=2.5, order=2, desc='燕窝鱼翅、四时鲜果：每晚体质 +1、每 3 晚容貌 +1、翻牌权重 +8、宫人忠心 +1；'
                                                     '只是贵人以下摆这个排场，难免有人说你逾制。'),
}
LAVISH_ILL_FORM_CHANCE = 0.06     # 贵人以下吃奢华，每晚被人参「逾制」的概率
LAVISH_BED_BONUS = 8
LAVISH_HEALTH_EVERY, LAVISH_LOOKS_EVERY = 1, 3      # 奢华饮食：每 1 晚体质 +1、每 3 晚容貌 +1（原 2 晚、6 晚）
FRUGAL_HEALTH_LOSS = 5     # 吃节俭每晚体质 -5，最低扣到 20


def diet_cost(rank, tier):
    return max(1, round(STIPEND.get(rank, 5) * DIET_RATIO * DIETS[tier]['mult']))


def diet_costs(rank):
    return {k: diet_cost(rank, k) for k in DIETS}


def diet_tick(day):
    """每晚开伙：按选的档次扣银子，银子不够就自动降一档，再不够就只能勒紧裤腰带；再按实际吃的档次给好处或坏处"""
    for c in list(q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status IN ('normal','confined')")):
        choice = c['diet'] if c['diet'] in DIETS else 'normal'
        eff = choice
        while eff != 'frugal' and c['silver'] < diet_cost(c['rank'], eff):
            eff = 'normal' if eff == 'lavish' else 'frugal'
        cost = min(c['silver'], diet_cost(c['rank'], eff))
        if cost: add_silver(c['id'], -cost)
        if eff != choice:
            notify(c['id'], f"银子不够，这几日的饮食只好从{DIETS[choice]['name']}降到{DIETS[eff]['name']}。", 'info')
        run("UPDATE consorts SET diet_eff=? WHERE id=?", (eff, c['id']))
        if eff == 'frugal' and c['health'] > 20:
            add_stat(c['id'], 'health', -min(FRUGAL_HEALTH_LOSS, c['health'] - 20))
        elif eff == 'lavish':
            if day % LAVISH_HEALTH_EVERY == 0 and c['health'] < 95: add_stat(c['id'], 'health', 1)
            if day % LAVISH_LOOKS_EVERY == 0 and c['appearance'] < 95: add_stat(c['id'], 'appearance', 1)
            for m in active_maids(c['id']): add_loyalty(m['id'], 1)
            if c['rank'] <= 4 and random.random() < LAVISH_ILL_FORM_CHANCE:
                add_stat(c['id'], 'virtue', -2)
                cut_favor(c['id'], FAVOR_LOSS['lavish'])
                notify(c['id'], f"有人在皇后跟前说你吃穿用度逾了制。德行 −2，圣宠 −{FAVOR_LOSS['lavish']}。", 'bad')


@app.route('/contraception', methods=['POST'])
@login_required
def set_contraception():
    c = g.me
    if birth_count(c['id']) < CONTRACEPTION_MIN_BIRTHS:
        flash(f'要生过 {CONTRACEPTION_MIN_BIRTHS} 个孩子之后，才能选择避孕。', 'bad')
    elif c['pregnant_since']:
        flash('你正怀着身孕，等生产之后再说。', 'bad')
    else:
        on = 0 if c['contraception'] else 1
        run('UPDATE consorts SET contraception=? WHERE id=?', (on, c['id']))
        flash('已开始避孕，侍寝不会再怀上。' if on else '不再避孕，侍寝又有机会怀上。', 'good')
    return redirect(url_for('place', key='home', living=1))


@app.route('/diet', methods=['POST'])
@login_required
def set_diet():
    c = g.me
    tier = request.form.get('tier')
    if tier not in DIETS or c['status'] not in ('normal', 'confined'):
        flash('现在改不了饮食。', 'bad')
    else:
        run("UPDATE consorts SET diet=? WHERE id=?", (tier, c['id']))
        flash(f"往后饮食按「{DIETS[tier]['name']}」，每晚约 {diet_cost(c['rank'], tier)} 两。", 'good')
    return redirect(url_for('place', key='home', living=1))


REPAIRS = {
    'window': dict(name='窗纸破了', base=20, sev=1, weight=3, line='窗纸被风吹破了，屋里灌风。'),
    'leak':   dict(name='屋顶漏雨', base=55, sev=2, weight=2, line='屋顶漏雨，被褥都潮了。'),
    'stove':  dict(name='地龙坏了', base=40, sev=2, weight=2, line='烧地龙的火道塌了，屋里一夜比一夜冷。'),
    'well':   dict(name='井水浑浊', base=35, sev=1, weight=2, line='院里的井水浑了，吃着一股土腥气。'),
    'beam':   dict(name='梁柱朽坏', base=140, sev=3, weight=1, line='一根梁柱朽了，屋里吱呀作响，让人不敢安睡。'),
}
REPAIR_CHANCE, REPAIR_COST_PER_RANK = 0.04, 0.15


def repair_cost(kind, rank):
    return round(REPAIRS[kind]['base'] * (1 + REPAIR_COST_PER_RANK * rank))


def repair_state(c):
    try: st = json.loads(c['repair']) if c['repair'] else None
    except ValueError: st = None
    return st if st and st.get('kind') in REPAIRS else None


def repair_tick(day):
    """宫里的屋子偶尔会坏：没修的每晚体质 −1（重一点的还会让宫人寒心、圣宠掉），修好为止"""
    for c in list(q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status IN ('normal','confined') AND hall!=''")):
        st = repair_state(c)
        if st:
            sev = REPAIRS[st['kind']]['sev']
            if c['health'] > 20: add_stat(c['id'], 'health', -1)
            if sev >= 2:
                for m in active_maids(c['id']): add_loyalty(m['id'], -1)
            if sev >= 3: cut_favor(c['id'], FAVOR_LOSS['repair'])
            st['days'] = st.get('days', 0) + 1
            run("UPDATE consorts SET repair=? WHERE id=?", (json.dumps(st), c['id']))
        elif random.random() < REPAIR_CHANCE:
            kind = random.choices(list(REPAIRS), weights=[r['weight'] for r in REPAIRS.values()])[0]
            cost = repair_cost(kind, c['rank'])
            run("UPDATE consorts SET repair=? WHERE id=?", (json.dumps(dict(kind=kind, cost=cost, day=day, days=0)), c['id']))
            notify(c['id'], f"{REPAIRS[kind]['line']}找内务府来修，要 {cost} 两；不修，身子和宫人都要跟着受罪。去本宫看看。", 'bad')


@app.route('/repair', methods=['POST'])
@login_required
def do_repair():
    c = g.me
    st = repair_state(c)
    if not st:
        flash('宫里没有要修的东西。', 'bad')
    elif c['silver'] < st['cost']:
        flash(f"银子不够，要 {st['cost']} 两。", 'bad')
    else:
        add_silver(c['id'], -st['cost'])
        run("UPDATE consorts SET repair='' WHERE id=?", (c['id'],))
        flash(f"内务府的匠人来了，{REPAIRS[st['kind']]['name']}修好了，花了 {st['cost']} 两。", 'good')
    return redirect(url_for('place', key='home'))


PRAY_TIERS = {20: dict(blessing=1, chance=0.08), 60: dict(blessing=3, chance=0.15), 150: dict(blessing=8, chance=0.25)}
BLESSING_CAP, QUIET_DAYS, LONGEVITY_MAX = 100, 3, 5   # 躺平要求 2026-10-06 从 10 天压到 5 天，2026-10-07 再压到 3 天
BLESSING_OLD_AGE_DIV, BLESSING_OLD_AGE_MAX = 200, 0.5     # 福报每 2 点，老死的概率少 1%，最多少一半
BLESSING_SURVIVE_DIV, BLESSING_SURVIVE_MAX = 500, 0.15    # 福报每 5 点，病重、中毒时多 1% 的活路，最多多 15%


def is_quiet(c, day=None):
    """躺平：这五天没有对人使过计"""
    day = cur_day() if day is None else day
    return not q("SELECT 1 FROM intrigues WHERE (attacker_id=? OR partner_id=?) AND status NOT IN ('invited','declined','expired') AND day>=?", (c['id'], c['id'], day - QUIET_DAYS), one=True)


def blessing_survive_bonus(c):
    return min(BLESSING_SURVIVE_MAX, c['blessing'] / BLESSING_SURVIVE_DIV)


def do_pray(c, cfg):
    try: amount = int(request.form.get('amount', 0))
    except ValueError: amount = 0
    tier = PRAY_TIERS.get(amount)
    if not tier: raise Reject('香油钱有 20、60、150 两三档。')
    if c['silver'] < amount: raise Reject(f'手头只有 {c["silver"]} 两，不够 {amount} 两。')
    charge(c, cfg)
    add_silver(c['id'], -amount)
    run("UPDATE consorts SET blessing=MIN(?, blessing+?) WHERE id=?", (BLESSING_CAP, tier['blessing'], c['id']))
    add_stat(c['id'], 'health', 1)
    msg = f"你在佛前添了 {amount} 两香油，心里静了下来。福报 +{tier['blessing']}，体质 +1。"
    if is_quiet(c) and c['longevity'] < LONGEVITY_MAX and random.random() < tier['chance']:
        run("UPDATE consorts SET age_months=MAX(216, age_months-12), longevity=longevity+1 WHERE id=?", (c['id'],))
        msg += '香烟直直地往上走，你忽然觉得身子轻了些，像是又年轻了一岁。'
    return msg, 'good'


def do_maid_snack(c, cfg):
    charge(c, cfg)
    m = take_errand(c)
    add_stat(c['id'], 'health', 1)
    run("UPDATE consorts SET seek_bonus=seek_bonus+6 WHERE id=?", (c['id'],))
    return f"{m['name']}去御膳房讨了碟点心回来。体质 +1，今晚翻牌的机会略添一分。", 'good'

def do_maid_shop(c, cfg):
    charge(c, cfg)
    m = take_errand(c)
    return f"{m['name']}去内务府打了招呼，今天在内务府买东西九折。", 'good'

def do_maid_scribe(c, cfg):
    if emperor_ill():
        raise Reject('皇上病重，敬事房今天不递牌子。')
    charge(c, cfg)
    m = take_errand(c)
    run("UPDATE consorts SET seek_bonus=seek_bonus+15 WHERE id=?", (c['id'],))
    return f"{m['name']}捧着银子去了敬事房。今晚翻牌子的机会大增。", 'good'

def do_maid_watch(c, cfg):
    charge(c, cfg)
    m = take_errand(c, prefer='zuijin')
    return f"{m['name']}今夜替你守着门。今晚有人想算计你，成算要低些。", 'good'

def do_maid_gossip(c, cfg):
    charge(c, cfg)
    m = take_errand(c, prefer='suizui')
    lines = [maid_gossip(c, m)]
    if m['trait'] == 'tancai' and c['silver'] >= 10:
        add_silver(c['id'], -10)
        lines.append(maid_gossip(c, m))
    return ' '.join(lines), 'info'

ACTION_HANDLERS = dict(maid_snack=do_maid_snack, maid_shop=do_maid_shop, maid_scribe=do_maid_scribe, maid_watch=do_maid_watch, maid_gossip=do_maid_gossip, schemestudy=do_schemestudy, perform=do_perform, palace_work=do_palace_work, aid=do_aid, greet=do_greet, study=do_study, groom=do_groom, rest=do_rest, reflect=do_reflect,
                       eyes=do_eyes, seek=do_seek, garden=do_garden, visit=do_visit, spy=do_spy, plead=do_plead, attend=do_attend, pizhe=do_pizhe, chastise=do_chastise, shoukang=do_shoukang, pray=do_pray)

# ── 秘密坦白 ───────────────────────────────────────────────────────────────────

def apply_secret_penalty(cid, confessed):
    c = get_consort(cid)
    s = c['secret']
    if not confessed: add_prestige(c, PRESTIGE_EXPOSED, f"{full_name(c)}的秘密被人告发")
    if s == 'lover':
        if confessed: cut_favor(cid, FAVOR_LOSS['secret_lover_confess'])
        else:
            cut_favor(cid, FAVOR_LOSS['secret_lover']); add_stat(cid, 'virtue', -15)
    elif s == 'fake':
        if confessed: cut_favor(cid, FAVOR_LOSS['secret_fake_confess'])
        elif c['rank'] > 1: demote_rank(cid)
    elif s == 'book':
        confine(cid, 1 if confessed else 3)
    elif s == 'scar':
        add_stat(cid, 'appearance', -5 if confessed else -10)
        if not confessed: cut_favor(cid, FAVOR_LOSS['secret_scar'])
    elif s == 'physician':
        if confessed: confine(cid, 3)
        else: send_to_cold(cid)
    run("UPDATE consorts SET secret_revealed=1 WHERE id=?", (cid,))

@app.route('/confess', methods=['POST'])
@login_required
def confess():
    flash('主动向皇帝坦诚秘密的玩法已取消；秘密仍可能被探查或告发。', 'info')
    return redirect(url_for('index'))

# ── 六宫（社交）────────────────────────────────────────────────────────────────

# ── 交好 NPC（九点二十一节）──────────────────────────────────────────────────────
# 每天拜访一位 NPC、选一种示好方式。好感四档：冷淡 <0 / 客气 0~29 / 亲近 30+ / 知己 60+，
# 亲近、知己各解锁一项回报（见 BOND_PERKS 和各处 bond() 的调用）。换届时 NPC 换人、relations 清空，自然归零。
# 台词只用封号，不写人名：NPC 每届换人，孩子也不一定是同一个

BOND_CLOSE, BOND_INTIMATE = 30, 60
BOND_TIERS = [(BOND_INTIMATE, '知己'), (BOND_CLOSE, '亲近'), (0, '客气'), (-101, '冷淡')]
BOND_VISIT_ENERGY = 1
BOND_SNUB = -5                 # 撞上忌讳
BOND_INTIMATE_DECAY = 2        # 知己要常走动：每晚 −2
BOND_SPILL = {                 # 讨好一位，牵连别人（只算涨的时候）
    'huanghou': [('huafei', -0.5)],
    'huafei':   [('huanghou', -0.5)],
    'lipin':    [('huafei', 0.25), ('huanghou', -0.25)],   # 丽嫔是华妃的人，嘴又不严
}
BOND_LIPIN_BOOST = 1.5         # 丽嫔知己：替你在华妃跟前说好话，华妃好感的涨幅 ×1.5
BOND_HUANGHOU_GUARD = 0.08     # 皇后亲近：别人对你使计成功率 −8%
BOND_HUAFEI_GUARD = 0.10       # 华妃知己：−10%
BOND_HUANGHOU_PROMOTE = 0.9    # 皇后知己：晋封所需圣宠打九折
BOND_CAUGHT_HUANGHOU = -30     # 你使计败露，皇后好感 −30
BOND_DUANFEI_SECRET = 0.30
BOND_DUANFEI_HINT_DAYS = 3
BOND_QIFEI_PLEAD, BOND_QIFEI_BACKFIRE, BOND_QIFEI_INTERVAL = 0.30, 0.20, 3
BOND_JINGPIN_CASE = 10         # 敬嫔亲近：案子里你的嫌疑多减 10
BOND_CAO_BOOST, BOND_CAO_LEAK, BOND_CAO_LEAK_CAUGHT = 0.05, 0.10, 0.15
BOND_CAO_TRUE = 0.5

NPC_BOND = {
    'huanghou': dict(
        likes='懂规矩、顾体面、人前恭敬', dislikes='让她在皇上面前失了体面、僭越',
        perks=('别人对你使计，成功率 −8%', '替你说好话：晋封所需圣宠打九折'),
        risk='你使计败露，她的好感 −30；讨好她，华妃会冷淡',
        greet={
            '冷淡': ['「妹妹来了。本宫这里没什么新鲜的，坐一坐就回吧，别误了自己的事。」',
                   '「妹妹近来忙，本宫是知道的。难为你还记得景仁宫的门朝哪边开。」'],
            '客气': ['「来了就坐。宫里规矩多，妹妹若有不明白的，只管问本宫。」',
                   '「妹妹来得巧，本宫才叫人沏了新茶。尝尝，是皇上前日赏的。」'],
            '亲近': ['「妹妹近日懂事多了，本宫都看在眼里，皇上那里也提过一句。」',
                   '「坐近些。本宫这里没外人，妹妹不必拘着规矩。」'],
            '知己': ['「这宫里本宫能放心说几句体己话的，也就妹妹了。」',
                   '「妹妹来得正好。有些事，本宫想听听你的意思——只在这屋里说。」'],
        },
        opts=[
            dict(text='备一份得体的礼送去', stat=None, silver=40, gain=8,
                 like='「妹妹有心了。东西不在贵，贵在合规矩——这份礼，送得体面。」'),
            dict(text='在人前替她维护规矩', stat='scheme', dc=65, gain=9,
                 like='「宫里人人都像妹妹这样懂规矩，本宫也就省心了。」',
                 dislike='「规矩是本宫来立的。妹妹的心意，本宫领了。」她笑着，没再往下说。'),
            dict(text='陪她抄经，为皇上祈福', stat='virtue', dc=60, gain=7,
                 like='「妹妹这笔字静。为皇上祈福的事，本宫会替你记着。」',
                 dislike='「抄错了三处。心不静，抄多少都是白费纸墨。」'),
            dict(text='当着众人夸她持家有道', stat='talent', dc=68, gain=10,
                 like='「妹妹过誉了。本宫不过是替皇上看着这个家。」',
                 dislike='「这样的话，妹妹往后在人前少说。叫皇上听见，倒像本宫在邀功。」'),
        ]),
    'huafei': dict(
        likes='奉承、稀罕东西、顺着她说', dislikes='不识抬举、跟皇后走得近',
        perks=('不再把你当成出手的目标', '给你撑腰：别人对你使计，成功率 −10%'),
        risk='讨好她，皇后会冷淡',
        greet={
            '冷淡': ['「哟，今儿什么风把你吹到翊坤宫来了？本宫这儿的门槛，你也肯迈？」',
                   '「来都来了，杵着做什么？还要本宫请你坐不成？」'],
            '客气': ['「坐吧。本宫这儿的茶，可比你宫里的强多了。」',
                   '「来陪本宫说话？也好，横竖皇上今儿在前朝，本宫闷得慌。」'],
            '亲近': ['「你来得正好！瞧瞧本宫新得的这对翡翠镯子，满宫里谁有？」',
                   '「还是你识趣。那些个木头美人，本宫看一眼都嫌烦。」'],
            '知己': ['「往后在这宫里，有本宫一日，就没人敢给你脸色看。」',
                   '「过来，坐本宫身边。有谁不长眼，你只管告诉本宫。」'],
        },
        opts=[
            dict(text='送一件稀罕的珠宝', stat=None, silver=60, gain=9,
                 like='「这成色倒还配得上翊坤宫。算你有眼光。」'),
            dict(text='夸她圣眷无双', stat='appearance', dc=65, gain=8,
                 like='「这还用你说？不过——从你嘴里说出来，本宫爱听。」',
                 dislike='「圣眷？本宫什么时候失过圣眷？你这话是什么意思？」'),
            dict(text='替她去敲打她看不顺眼的人', stat='scheme', dc=72, gain=12,
                 like='「好！那起子人就该有人治一治。你这份心，本宫记下了。」',
                 dislike='「谁叫你自作主张的？闹大了，还不是要本宫替你收拾！」'),
            dict(text='弹琴唱曲陪她解闷', stat='talent', dc=62, gain=7,
                 like='「唱得不错，比那些只会念经的强。再来一段！」',
                 dislike='「行了行了，听得本宫脑仁疼。下去吧。」'),
        ]),
    'duanfei': dict(
        likes='安静、点到为止、念旧', dislikes='吵闹、打听她的伤心事',
        perks=('拜访时三成会告诉你一位小主的底细', '你被人算计后，她会说出三个可疑的人，真凶就在其中'),
        risk='回报慢，没有直接的数值好处',
        greet={
            '冷淡': ['「……咳。有事？没事就回吧，我乏了。」',
                   '「……延庆殿药气重。妹妹站远些，别熏着你。」'],
            '客气': ['「坐。……这宫里，肯往延庆殿走的人不多。」',
                   '「窗边亮些，坐那儿吧。……咳咳。」'],
            '亲近': ['「你来了。……今日精神好些，陪我坐一坐。」',
                   '「从前我也爱穿这样的颜色。……如今，穿不动了。」'],
            '知己': ['「有些话，我只说一遍。……你记着就好。」',
                   '「这么多年，你是头一个让我想多说几句的人。……咳，坐吧。」'],
        },
        opts=[
            dict(text='送一剂安神的药', stat=None, silver=20, gain=7,
                 like='「……难为你记挂。这方子，比太医院开的实在。」'),
            dict(text='什么也不说，陪她坐着', stat='virtue', dc=60, gain=8,
                 like='她没说话，只把手边的暖炉往你那边推了推。',
                 dislike='「……咳咳。你心里有事，坐不住的。回吧。」'),
            dict(text='请她讲讲宫里从前的事', stat='scheme', dc=70, gain=10,
                 like='「从前……翊坤宫那位还没进宫的时候，这宫里也有过好日子。你想听，改日再说。」',
                 dislike='「旧事？……旧事是拿来忘的。你打听这些做什么。」'),
            dict(text='替她誊抄医书', stat='talent', dc=64, gain=8,
                 like='「字写得清秀。……我这眼睛，看不清小字了。多谢。」',
                 dislike='「……抄错了两味药。药错了，是要命的。」'),
        ]),
    'qifei': dict(
        likes='夸她的儿子、直来直去、听她说话', dislikes='说她儿子不好、拿她当枪使',
        perks=('你被禁足或打入冷宫时，她会去皇上跟前替你求情（三成能少关一天）', '你明着站队她的儿子时，每次打点功绩多 +1'),
        risk='她嘴笨，求情碰了钉子会连累你：信任 −3',
        greet={
            '冷淡': ['「你来做什么？我可没什么好处给你！」',
                   '「哼，平日里见了我头都不点，今儿倒想起我来了？」'],
            '客气': ['「坐坐坐！我们阿哥刚下学，你来得不巧，不然让他给你背两段书！」',
                   '「哎，你尝尝这个枣泥糕，我们阿哥最爱吃，我特意叫小厨房多做的。」'],
            '亲近': ['「哈哈哈，你来啦！快来，我跟你说，阿哥今儿又被师傅夸了！」',
                   '「我就说你这人实在！不像有些人，笑里藏刀的——我可没说是谁啊。」'],
            '知己': ['「你是自己人，我什么都不瞒你。我们阿哥往后有出息了，忘不了你！」',
                   '「谁要敢欺负你，你跟我说！大不了我去皇上跟前哭去！」'],
        },
        opts=[
            dict(text='夸她家阿哥聪明', stat='virtue', dc=58, gain=8,
                 like='「哈哈哈！可不是嘛！我就说我们阿哥最聪明，你眼光真好！」',
                 dislike='「你什么意思？拿话套我呢？我们阿哥好不好，轮得到你来评？」'),
            dict(text='耐着性子听她唠叨', stat='virtue', dc=55, gain=6,
                 like='「跟你说话就是痛快！别走了，留下来用晚膳！」',
                 dislike='「你打什么哈欠？嫌我话多就直说，我又不是听不懂！」'),
            dict(text='给阿哥送一套笔墨', stat=None, silver=20, gain=8,
                 like='「哎哟，阿哥见了准高兴坏了！我替他谢谢你啊！」'),
            dict(text='替她出一口恶气', stat='scheme', dc=68, gain=11,
                 like='「解气！真解气！我早就想骂她了，就是嘴笨说不过！」',
                 dislike='「哎呀你这是害我！人家转头就去皇后那儿告我一状，我可怎么办！」'),
        ]),
    'jingpin': dict(
        likes='温和、花草、清静', dislikes='争斗、逼她站队',
        perks=('案子里你被当成嫌疑人时，她替你作证：嫌疑多减 10', '孩子按祖制要送走时，交给她抚养，你去探视不花精力'),
        risk='没什么风险，就是回报不显眼',
        greet={
            '冷淡': ['「妹妹来了……坐吧。我这里没什么热闹，怕是留不住妹妹。」',
                   '「哦……是妹妹。罢了，来都来了，喝盏茶再走。」'],
            '客气': ['「妹妹坐。院里那盆茉莉今早开了，香得很，妹妹闻见没有？」',
                   '「慢些走，台阶上有青苔……我总说要叫人扫，又舍不得。」'],
            '亲近': ['「妹妹来了，我正要剪几枝月季插瓶，你帮我挑挑，哪枝好看？」',
                   '「这宫里的事呀，看多了也就那样。妹妹坐，咱们只说花，不说人。」'],
            '知己': ['「妹妹……我这个人没什么本事，可你的事，我放在心上了。」',
                   '「往后有什么难处，别一个人扛着。我这咸福宫，总还能替你挡挡风。」'],
        },
        opts=[
            dict(text='送几株稀罕的花苗', stat=None, silver=20, gain=7,
                 like='「这是……绿萼梅的苗？妹妹有心了。等开了头一朵，请你来看。」'),
            dict(text='陪她侍弄花草', stat='virtue', dc=55, gain=7,
                 like='「妹妹手真轻。这株兰草最娇气，别人碰一下就蔫。」',
                 dislike='「哎……这根断了。罢了罢了，不怪你，是它命薄。」'),
            dict(text='在人前替她说句公道话', stat='scheme', dc=66, gain=9,
                 like='「何必呢……不过，还是谢谢妹妹。我这人嘴笨，吃了亏也说不出。」',
                 dislike='「妹妹这样一说，倒叫人以为是我在背后搬弄是非了……何必呢。」'),
            dict(text='夸她待人宽厚', stat='virtue', dc=60, gain=6,
                 like='「我哪有妹妹说的那样好……不过是不爱争罢了。」',
                 dislike='「妹妹这样说，我倒不知怎么接了……咱们还是说花吧。」'),
        ]),
    'lipin': dict(
        likes='漂亮东西、被夸美、热闹', dislikes='被比下去、在华妃面前丢脸',
        perks=('拜访时告诉你华妃眼下最看谁不顺眼', '替你在华妃跟前说好话：华妃好感的涨幅 ×1.5'),
        risk='她嘴不严：讨好她，华妃好感跟着涨一点，皇后好感跟着掉一点',
        greet={
            '冷淡': ['「哟，稀客呀。华妃娘娘前儿还说起你呢——说的什么，你自己猜去。」',
                   '「你来干什么？我这儿可没有你想打听的事。」'],
            '客气': ['「来得正好，你瞧我这新描的眉，是不是比上回那个好看？」',
                   '「坐吧坐吧。华妃娘娘说了，要大方待人，我可不能怠慢你。」'],
            '亲近': ['「你来！快帮我看看，这支步摇跟华妃娘娘赏的那支，哪支更衬我？」',
                   '「我跟你说个事儿，你可千万别往外传啊——算了，传了也没事，反正大家都知道了。」'],
            '知己': ['「这宫里我就跟你最好了！华妃娘娘那儿，我替你说了好几回好话呢！」',
                   '「有什么想打听的只管问我，这宫里的事，还能瞒得过我这双耳朵？」'],
        },
        opts=[
            dict(text='送一匣脂粉珠花', stat=None, silver=40, gain=8,
                 like='「哎呀，这珠花！正好配我那件桃红的褂子！你可真会挑！」'),
            dict(text='夸她是六宫里最美的', stat='appearance', dc=60, gain=8,
                 like='「真的呀？比那谁还好看？我就知道！镜子里我也这么觉得！」',
                 dislike='「你自个儿长得这样，还来夸我？存心寒碜我是不是！」'),
            dict(text='陪她聊闲天', stat='talent', dc=58, gain=6,
                 like='「跟你说话真有意思！比曹贵人强多了，她说话总说一半！」',
                 dislike='「你到底听没听我说话呀？我都说三遍了！」'),
            dict(text='替她在华妃跟前说好话', stat='scheme', dc=68, gain=10,
                 like='「华妃娘娘今儿真夸我了！是你说的吧？我就知道你够意思！」',
                 dislike='「你在娘娘跟前提我做什么！娘娘还以为我在背后撺掇人，骂了我一顿！」'),
        ]),
    'caoguiren': dict(
        likes='聪明人、实在的好处、她的女儿', dislikes='蠢人、被人利用',
        perks=('拜访时告诉你皇后、华妃在盯着谁（五成可信）', '替你出谋划策：你使计成功率 +5%'),
        risk='她两头下注：知己之后你每次使计，有一成会被她走漏，败露的可能 +15%',
        greet={
            '冷淡': ['「妹妹来了？稀客。只是我这儿地方小，怕是……妹妹说呢？」',
                   '「妹妹今日怎么想起我来了？我还当是……呵，瞧我，胡乱猜什么。坐吧。」'],
            '客气': ['「妹妹坐。公主刚睡下，咱们小声说话。」',
                   '「妹妹这身料子好，是内务府新进的吧？华妃娘娘那边……可还没有呢。」'],
            '亲近': ['「妹妹来得巧，我正有句话想说，又怕说出来……妹妹不会往外传吧？」',
                   '「妹妹是聪明人，有些事不用我说透。你心里明白，我心里也明白。」'],
            '知己': ['「这宫里，谁都靠不住。可妹妹……我是愿意信一回的。」',
                   '「只要公主平平安安长大，我这辈子也就……妹妹，往后你多照应她些。」'],
        },
        opts=[
            dict(text='给小公主送衣料玩物', stat=None, silver=20, gain=8,
                 like='「妹妹费心了。她呀，最喜欢这样鲜亮的颜色……」她低头笑了笑，这回笑到了眼睛里。'),
            dict(text='替她出个主意', stat='scheme', dc=70, gain=10,
                 like='「妹妹这主意……倒跟我想到一处去了。妹妹说，咱们是不是该常走动？」',
                 dislike='「主意好是好，只是……我怎么听着，像是要拿我去试水呢？」'),
            dict(text='陪她说些闲话', stat='talent', dc=60, gain=6,
                 like='「跟妹妹说话省力。有些话，说一半妹妹就懂了。」',
                 dislike='「妹妹今日心不在焉的，可是有什么……不方便说的？」'),
            dict(text='替她跑腿传句话', stat='virtue', dc=60, gain=7,
                 like='「妹妹办事稳妥。这份情，我记着——总有还的时候。」',
                 dislike='「话是传到了，只是传的时候……旁边可有人听见？妹妹下回留神些。」'),
        ]),
    'xinchangzai': dict(
        likes='爽快、说真话、敬重老人', dislikes='虚伪、新人摆架子',
        perks=('拜访时告诉你某位小主昨天都干了什么', '有人今晚要对你下手，她会提前告诉你有几拨（不说是谁）'),
        risk='没什么风险',
        greet={
            '冷淡': ['「嗐，你来干嘛？我这破地方可没什么值得你惦记的。」',
                   '「要我说，你还是回吧。跟我走得近，可沾不着什么光。」'],
            '客气': ['「坐！别客气，我这儿没那么多讲究。瓜子管够。」',
                   '「嗐，又是来听闲话的吧？行，今儿有新鲜的。」'],
            '亲近': ['「你这人对我胃口！要我说，这宫里就缺你这样不装腔的。」',
                   '「来来来，我跟你说，新来的那几个昨儿闹的笑话可大了——」'],
            '知己': ['「我在这宫里熬了这些年，什么没见过？要我说，你是个能成事的，我帮你盯着。」',
                   '「谁敢打你的主意，我这双眼睛替你看着呢。别的没有，就是眼尖。」'],
        },
        opts=[
            dict(text='跟她说几句掏心窝的实话', stat='virtue', dc=60, gain=9,
                 like='「嗐！痛快！就冲你这句实话，我认你这个朋友！」',
                 dislike='「要我说，你这话也太冲了。实话也得挑时候说，懂不懂？」'),
            dict(text='听她讲宫里的旧闻', stat='virtue', dc=52, gain=6,
                 like='「还是你爱听！那些个新人，我一开口就跑，嗐。」',
                 dislike='「行了，看你那眼神就知道没听进去。去吧去吧。」'),
            dict(text='敬她是宫里的老人', stat='scheme', dc=58, gain=7,
                 like='「嗐，什么老人不老人的，熬出来的罢了。不过你这话我爱听。」',
                 dislike='「少来这套！拍马屁拍到我这儿来了？我可不吃这一口。」'),
            dict(text='送一篓上好的银炭', stat=None, silver=20, gain=7,
                 like='「炭？嗐，你怎么知道我这屋冬天冷？内务府那帮人，净克扣我们这些没人疼的。」'),
        ]),
}


def npc_row(key):
    return q("SELECT * FROM consorts WHERE npc_key=?", (key,), one=True)


def bond(cid, key):
    """cid 跟某位 NPC 的好感；NPC 不在（换届前后、还没 seed）就当 0"""
    npc = npc_row(key)
    if not npc or npc['id'] == cid: return 0
    rel = relation(cid, npc['id'])
    return rel['affinity'] if rel else 0


def bond_tier(aff):
    return next(name for line, name in BOND_TIERS if aff >= line)


def change_bond(cid, key, delta):
    """加减 cid 跟 NPC 的好感，带上牵连（BOND_SPILL）。返回 [(npc, 实际变化), ...]"""
    npc = npc_row(key)
    if not npc or not delta: return []
    if key == 'huafei' and delta > 0 and bond(cid, 'lipin') >= BOND_INTIMATE:
        delta = math.ceil(delta * BOND_LIPIN_BOOST)
    add_affinity(cid, npc['id'], delta)
    out = [(npc, delta)]
    if delta > 0:
        for other, ratio in BOND_SPILL.get(key, ()):
            d, o = int(delta * ratio), npc_row(other)
            if d and o:
                add_affinity(cid, o['id'], d)
                out.append((o, d))
    return out


def bond_text(changes):
    return '，'.join(f"{display_name(n)}好感 {d:+d}" for n, d in changes)


def huafei_likely_target(exclude_id=0):
    """照 npc_schemes 里华妃挑人的规矩，算她眼下最可能冲谁去"""
    hf = npc_row('huafei')
    if not hf or hf['status'] != 'normal': return None
    pool = []
    for p in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND id!=?", (exclude_id,)):
        if bond(p['id'], 'huafei') >= BOND_CLOSE: continue
        grudge = (relation(hf['id'], p['id']) or {'affinity': 0})['affinity'] <= -20
        if p['favor'] >= 60 or grudge:
            pool.append((p['favor'] + (100 if grudge else 0), p))
    return max(pool, key=lambda x: x[0])[1] if pool else None


def huanghou_likely_target(exclude_id=0):
    hh = npc_row('huanghou')
    if not hh or hh['status'] != 'normal': return None
    players = q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND id!=?", (exclude_id,))
    preg = [p for p in players if p['pregnant_since']]
    if preg: return preg[0]
    return max(players, key=lambda p: p['favor']) if players else None


def random_player(exclude_id):
    rows = q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead') AND id!=?", (exclude_id,))
    return random.choice(rows) if rows else None


def bond_visit_perk(c, key, aff):
    """拜访成功后，亲近/知己的 NPC 顺口告诉你的事。返回一句话或空"""
    day = cur_day()
    if key == 'duanfei':
        if aff >= BOND_INTIMATE:
            npc = npc_row(key)
            for it in q("""SELECT * FROM intrigues WHERE target_id=? AND status='done' AND result='success' AND day>=?
                           ORDER BY id DESC""", (c['id'], day - BOND_DUANFEI_HINT_DAYS)):
                if q("SELECT 1 FROM memories WHERE a_id=? AND b_id=? AND kind='duan_hint' AND note=?",
                     (c['id'], npc['id'], str(it['id'])), one=True):
                    continue
                others = [r['id'] for r in q("""SELECT id FROM consorts WHERE id NOT IN (?,?) AND status IN ('normal','confined')
                                                AND rank>=1""", (c['id'], it['attacker_id']))]
                names = [display_name(get_consort(i)) for i in random.sample(others, min(2, len(others)))]
                names.append(display_name(get_consort(it['attacker_id'])))
                random.shuffle(names)
                remember(c['id'], npc['id'], 'duan_hint', str(it['id']))
                return f"端妃压低声音：「那几日……{'、'.join(names)}，都往你那边走动过。……我只能说到这儿。」"
        if aff >= BOND_CLOSE and random.random() < BOND_DUANFEI_SECRET:
            cands = q("""SELECT id FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status NOT IN ('xiunv','dead')
                         AND secret_revealed=0 AND id NOT IN (SELECT target_id FROM known_secrets WHERE knower_id=?)""",
                      (c['id'], c['id']))
            if cands:
                t = get_consort(random.choice(cands)['id'])
                run("INSERT OR IGNORE INTO known_secrets (knower_id, target_id, day) VALUES (?,?,?)", (c['id'], t['id'], day))
                return f"端妃淡淡提了一句：「{display_name(t)}？……她{SECRETS[t['secret']]['name']}。」"
    elif key == 'lipin' and aff >= BOND_CLOSE:
        t = huafei_likely_target(exclude_id=c['id'])
        return (f"丽嫔凑过来：「华妃娘娘这几日最看不顺眼的，是{display_name(t)}。」" if t
                else '丽嫔撇撇嘴：「华妃娘娘这几日心情好，没盯着谁。」')
    elif key == 'caoguiren' and aff >= BOND_CLOSE:
        parts = []
        for who, fn in (('皇后', huanghou_likely_target), ('华妃', huafei_likely_target)):
            t = fn(exclude_id=c['id'])
            if random.random() >= BOND_CAO_TRUE: t = random_player(c['id'])   # 她的话只有五成可信
            if t: parts.append(f"{who}那边留意着{display_name(t)}")
        return f"曹贵人笑着说：「我也是听人说的——{'，'.join(parts)}。妹妹听听就算了。」" if parts else ''
    elif key == 'xinchangzai':
        if aff >= BOND_INTIMATE:
            n = q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND status='pending'", (c['id'],), one=True)['n']
            if n: return f"欣常在一把拉住你：「嗐，你当心！今儿夜里，怕是有 {n} 拨人冲你来。是谁我可不知道。」"
        if aff >= BOND_CLOSE:
            t = random_player(c['id'])
            if t: return f"欣常在嗑着瓜子说：「{display_name(t)}昨儿{daily_activity(t['id'], day - 1)}。」"
    return ''


@app.route('/npc/visit', methods=['POST'])
@login_required
def npc_visit():
    c = g.me
    key = request.form.get('npc', '')
    cfg = NPC_BOND.get(key)
    npc = npc_row(key) if cfg else None
    try:
        opt = cfg['opts'][int(request.form.get('opt', ''))] if cfg else None
    except (ValueError, IndexError):
        opt = None
    err = None
    if not npc or not opt: err = '没有这位娘娘。'
    elif c['status'] != 'normal': err = '你现在出不了门。'
    elif is_sick(c): err = '你病着，出不了门。'
    elif npc['status'] != 'normal': err = f"{display_name(npc)}眼下不见客。"
    elif daily_count(c['id'], 'npc_visit'): err = '今天已经去过一位娘娘那儿了。'
    elif c['energy'] < BOND_VISIT_ENERGY: err = '精力不够了。'
    elif opt.get('silver') and c['silver'] < opt['silver']: err = f"银子不够，要 {opt['silver']} 两。"
    if err:
        flash(err, 'bad'); return redirect(url_for('social'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (BOND_VISIT_ENERGY, c['id']))
    if opt.get('silver'): add_silver(c['id'], -opt['silver'])
    daily_inc(c['id'], 'npc_visit')
    before = bond(c['id'], key)
    greet = random.choice(cfg['greet'][bond_tier(before)])
    if key == 'huanghou' and bond(c['id'], 'huafei') >= BOND_CLOSE:
        greet = random.choice(HUANGHOU_WARN)          # 跟华妃走得近，皇后要敲打几句
    ok = opt['stat'] is None or c[opt['stat']] + random.randint(0, SCENE_ROLL) >= opt['dc']
    changes = change_bond(c['id'], key, opt['gain'] if ok else BOND_SNUB)
    after = bond(c['id'], key)
    lines = [greet, opt['like'] if ok else opt['dislike'], bond_text(changes) + '。']
    if opt.get('silver'): lines[-1] = f"银子 -{opt['silver']}，" + lines[-1]
    if bond_tier(after) != bond_tier(before):
        lines.append(f"你和{display_name(npc)}如今算得上「{bond_tier(after)}」了。")
    if ok:
        perk = bond_visit_perk(c, key, after)
        if perk: lines.append(perk)
    flash('　'.join(lines), 'good' if ok else 'bad')
    return redirect(url_for('social'))


def npc_bond_tick(day):
    """每晚：齐妃替禁足/冷宫里交好的人求情；知己的好感慢慢淡"""
    qf = npc_row('qifei')
    if qf and qf['status'] == 'normal':
        for p in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status IN ('confined','cold') AND status_until_day>?", (day,)):
            if bond(p['id'], 'qifei') < BOND_CLOSE: continue
            if q("SELECT 1 FROM memories WHERE a_id=? AND b_id=? AND kind='qifei_plead' AND day>?",
                 (p['id'], qf['id'], day - BOND_QIFEI_INTERVAL), one=True):
                continue
            remember(p['id'], qf['id'], 'qifei_plead')
            r = random.random()
            if r < BOND_QIFEI_PLEAD:
                run('UPDATE consorts SET status_until_day=status_until_day-1 WHERE id=?', (p['id'],))
                notify(p['id'], '齐妃在皇上跟前替你哭了一场，皇上心一软，你能早一天出来。', 'good')
            elif r < BOND_QIFEI_PLEAD + BOND_QIFEI_BACKFIRE:
                add_trust(p['id'], -3)
                notify(p['id'], '齐妃去皇上跟前替你求情，话没说对，皇上连你也嫌上了。信任 -3。', 'bad')
    npc_ids = [n['id'] for n in q("SELECT id FROM consorts WHERE npc_key IS NOT NULL")]
    if npc_ids:
        marks = ','.join('?' * len(npc_ids))
        run(f"""UPDATE relations SET affinity=affinity-? WHERE affinity>=? AND (a_id IN ({marks}) OR b_id IN ({marks}))""",
            (BOND_INTIMATE_DECAY, BOND_INTIMATE, *npc_ids, *npc_ids))


def bond_caught_huanghou(cid):
    """使计败露：皇后最恨不体面的人"""
    if bond(cid, 'huanghou') > 0:
        change_bond(cid, 'huanghou', BOND_CAUGHT_HUANGHOU)
        notify(cid, f'这事传到了景仁宫。皇后好感 {BOND_CAUGHT_HUANGHOU:+d}。', 'bad')


def promote_favor_need(c, rank):
    need = PROMOTE_FAVOR[rank]
    return math.ceil(need * BOND_HUANGHOU_PROMOTE) if bond(c['id'], 'huanghou') >= BOND_INTIMATE else need


# ── 借华妃的刀（九点二十二节）────────────────────────────────────────────────────
# 华妃知己才能求她出手：占当天的拜访、150 两，好感压回 45；当晚她照自己的心计出手。
# 得手后她要一笔人情（KNIFE_DEBTS），办了相安无事，不办好感直接 −30，被她记恨。
# 她出手败露时，好感越高越不会供出你。受害人只知道是华妃，除非她把你供出来

KNIFE_COST = 150
KNIFE_AFTER_BOND = 45          # 从知己压回亲近
KNIFE_REFUSE = 0.20            # 华妃那天心情不好
KNIFE_COOLDOWN = 3             # 两次借刀至少隔 3 天；同一个目标 3 天内只挨一次
KNIFE_PUNISH_CHANCE = 0.25     # 目标宫里有宫人时，有时改成发落宫人
KNIFE_BROKEN_BOND = -30        # 赖账：低于记仇线 −20，华妃会冲你来
KNIFE_BETRAY_MAX, KNIFE_BETRAY_MIN = 0.50, 0.21   # 供出你的概率：好感 30 时 50%，59 时 21%

KNIFE_ASK = {
    'eager': ['「不过一个{t}，也值得你愁成这样？礼放下，这事本宫应了，你等着瞧就是。」',
              '「就这点事？本宫还当你要求什么了不得的。回去等着，自有人替你出这口气。」'],
    'stingy': ['「求本宫替你动手，就拿这么点东西来撑脸面？也罢，搁下吧，谁让本宫平日里高看了你一眼。」',
               '「一百五十两就想请动本宫？看在你平日还算识趣的份上——下回可没这么便宜。」'],
    'refuse': ['「本宫今日没工夫听你那些窝囊事，你受了气，倒来搅本宫清静？把你的礼原样拿回去，别杵在这儿碍眼！」',
               '「本宫是你使唤的人么？今儿不想听，出去！」'],
}
KNIFE_HIT_LINES = {
    'rumor': '「如今皇上听见{t}便皱眉，宫里也没谁肯夸她半句贤德，你出了这口气，该记着是谁赏你的吧？」',
    'frame': '「{t}那道宫门已经封了，本宫替你费的这番手脚，你预备拿什么来还？」',
    'punish': '「本宫才发落了{t}跟前的人，她便连求情都不敢，你倒落得清闲——这笔人情，先给本宫记在账上。」',
}
KNIFE_COVER = '「这回的责问本宫替你担了，你把嘴闭严些，别叫本宫白护了一个没出息的！」'
KNIFE_BETRAY = ['「皇上，从送礼求告到盘算如何害{t}，桩桩都是{p}的主意，本宫竟叫这副恭顺模样蒙蔽了。」',
                '「如今人证物证只管往{p}身上查，一个敢借本宫名头作恶的人，难道还会肯向皇上吐半句实话？」']
HUANGHOU_WARN = [
    '「你近来常往翊坤宫走动，想是与华妃投缘，本宫瞧着也欣慰。只是不知你还记不记得，姐妹情分之外，另有宫里的规矩。」',
    '「华妃待你亲厚，是你的福气。本宫只盼你把她的好处学去，至于旁的，总还该拿规矩量一量。」',
    '「今儿肯来陪本宫说话，倒是难得。想来翊坤宫再热闹，也没叫你忘了请安的规矩。」',
]
# 人情债。kind：silver 交银子 / hobby 交一件自己做的某类作品 / nogreet 期限内不去请安 /
# rumor 期限内自己对 {x} 散一次流言 / seek 期限内去养心殿送一次汤羹 / maid 把 {m} 送去翊坤宫
KNIFE_DEBTS = {
    'silver80': dict(kind='silver', amount=80, days=2,
        ask='「替你料理{t}，上下打点不花银子么？八十两，给本宫送来，别等着本宫催。」',
        ok='「总算没叫本宫白开这个口，账平了，收起你那副等赏的样子。」',
        broken='她冷笑一声：「八十两就试出了你的斤两，往后你在本宫眼里，便同{t}一个待遇。」'),
    'painting': dict(kind='hobby', hobby='painting', days=3,
        ask='「听说你的字画还算入眼，亲手画一幅送来。若拿旁人的笔墨搪塞，本宫会瞧不出来？」',
        ok='「这画还有几分气势，勉强抵得过本宫替你费的心。」',
        broken='她把空着的画匣推落在地：「本宫给你留着位置，你倒拿本宫当笑话。从前那点情分尽了，往后有你受的！」'),
    'nogreet': dict(kind='nogreet', days=2,
        ask='「从明日起，连着两日不许去景仁宫请安。皇后那几句贤良话，少听两日，你还能不认得路了？」',
        ok='「还算分得清谁替你办过事，这两日本宫记下了。」',
        broken='她笑意骤冷：「景仁宫的门槛竟比本宫的话还重。既舍不得皇后，就看她那张慈悲脸护不护得住你。」'),
    'rumor': dict(kind='rumor', days=2,
        ask='「把{x}私下怨怼圣意的话传出去，本宫要听见旁人议论。替自己出气时你倒殷勤，轮到替本宫办事，该不会连嘴都张不开吧？」',
        ok='「传得还算像样，你欠的这一回便揭过去。」',
        broken='她猛地一拍案：「求本宫时满口应承，替本宫传句话便装起了贤良。你既敢耍本宫，就连你那点底细一道传出去！」'),
    'seek': dict(kind='seek', days=3,
        ask='「去养心殿见了皇上，替本宫说说料理六宫的辛苦。皇后会占贤名，本宫做的事倒该没人提？」',
        ok='「你那几句话皇上听进去了，算你这张嘴还有些用处。」',
        broken='她当场摔碎了茶盏：「替本宫说句好话倒难住你了！好，从今往后你别想再沾本宫半分光，本宫有的是话说给皇上听！」'),
    'maid': dict(kind='maid', days=1,
        ask='「你宫里的{m}，本宫瞧着还算伶俐，送来翊坤宫当差。一个宫人罢了，难道还要本宫拿东西同你换？」',
        ok='「人留下，你可以回去了，这回还算懂得报答。」',
        broken='她拂袖起身：「连{m}都舍不得送来，倒舍得让本宫替你担事。这份交情到此为止，你那一宫的人，本宫会挨个留心！」'),
    'silver120': dict(kind='silver', amount=120, days=1,
        ask='「本宫要用一百二十两，你明日送齐。怎么，先前敢求本宫替你撑腰，如今倒要捂紧荷包了？」',
        ok='「数目不错，本宫也懒得再同你算先前那笔账。」',
        broken='她慢慢合上账册：「原来你打量着本宫只肯施恩、不会记仇。也好，这回便叫你长长见识。」'),
    'incense': dict(kind='hobby', hobby='incense', days=3,
        ask='「亲手调一盒清雅的熏香送来，别拿满宫都有的甜腻气糊弄本宫。受了本宫的照拂，总该肯费些心思吧？」',
        ok='「这气味尚不俗，算你还没把本宫的恩情全忘干净。」',
        broken='她把香炉掀翻在地：「本宫等了三日，就等来你这份怠慢。往日是本宫看走了眼，今日起，你就等着本宫一件件讨回来！」'),
}


def knife_open_debt(cid):
    return q("SELECT * FROM knife_debts WHERE consort_id=? AND status IN ('hit','owed') ORDER BY id DESC LIMIT 1", (cid,), one=True)


def knife_block_reason(c, t=None):
    """借不了的原因；借得了返回空"""
    day = cur_day()
    hf = npc_row('huafei')
    if not hf or hf['status'] != 'normal': return '华妃眼下不见客。'
    if bond(c['id'], 'huafei') < BOND_INTIMATE: return '跟华妃的交情还不到知己，她不会替你出手。'
    if c['status'] != 'normal' or is_sick(c): return '你现在出不了门。'
    if knife_open_debt(c['id']): return '你还欠着华妃的人情。'
    if q("SELECT 1 FROM knife_debts WHERE consort_id=? AND day>?", (c['id'], day - KNIFE_COOLDOWN), one=True):
        return f'刚求过华妃，隔 {KNIFE_COOLDOWN} 天再说。'
    if daily_count(c['id'], 'npc_visit'): return '今天已经去过一位娘娘那儿了。'
    if c['energy'] < BOND_VISIT_ENERGY: return '精力不够了。'
    if c['silver'] < KNIFE_COST: return f'求华妃出手要 {KNIFE_COST} 两的重礼。'
    if t is not None:
        if not t or not t['user_id'] or t['id'] == c['id'] or t['status'] != 'normal': return '这个人眼下对付不了。'
        if q("SELECT 1 FROM knife_debts WHERE victim_id=? AND day>?", (t['id'], day - KNIFE_COOLDOWN), one=True):
            return '她这几日刚吃过亏，华妃不肯接连对她下手。'
        if q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status='pending'",
             (t['id'], day), one=True)['n'] >= INTRIGUE_TARGET_DAILY_MAX:
            return '今晚冲她去的人已经够多了。'
    return ''


@app.route('/knife/borrow', methods=['POST'])
@login_required
def knife_borrow():
    c = g.me
    try: t = get_consort(int(request.form.get('target_id', 0)))
    except ValueError: t = None
    err = knife_block_reason(c, t)
    if err:
        flash(err, 'bad'); return redirect(url_for('social'))
    day = cur_day()
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (BOND_VISIT_ENERGY, c['id']))
    daily_inc(c['id'], 'npc_visit')
    names = dict(t=display_name(t))
    if random.random() < KNIFE_REFUSE:
        flash(random.choice(KNIFE_ASK['refuse']).format(**names) + '　她没收你的礼。', 'bad')
        return redirect(url_for('social'))
    aff = bond(c['id'], 'huafei')
    add_silver(c['id'], -KNIFE_COST)
    add_affinity(c['id'], npc_row('huafei')['id'], KNIFE_AFTER_BOND - aff)
    if punishable_maids(t['id']) and random.random() < KNIFE_PUNISH_CHANCE: method = 'punish'
    elif t['rank'] >= 3: method = 'frame'
    else: method = 'rumor'
    it_id = run("INSERT INTO intrigues (day, attacker_id, target_id, method, created_ts) VALUES (?,?,?,?,?)",
                (day, npc_row('huafei')['id'], t['id'], method, now_ts())).lastrowid
    run("""INSERT INTO knife_debts (consort_id, intrigue_id, victim_id, day, status, created_ts)
           VALUES (?,?,?,?,'hit',?)""", (c['id'], it_id, t['id'], day, now_ts()))
    line = random.choice(KNIFE_ASK['eager' if aff >= 70 else 'stingy']).format(**names)
    flash(f"{line}　银子 -{KNIFE_COST}，华妃好感压回 {KNIFE_AFTER_BOND}。今晚她会动手。", 'good')
    return redirect(url_for('social'))


def knife_pick_debt(c, victim):
    """挑一笔玩家办得到的人情。返回 (key, x_id, maid_id)"""
    kinds = hobby_unlocked_kinds(c)
    made = {r['kind'] for r in q("SELECT kind FROM hobby_items WHERE maker_id=? AND holder_id=?", (c['id'], c['id']))}
    maids = active_maids(c['id'])
    xs = [p for p in q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND id NOT IN (?,?)""",
                       (c['id'], victim))] if c['rank'] >= INTRIGUES['rumor']['min_rank'] else []
    ok = []
    for key, d in KNIFE_DEBTS.items():
        if d['kind'] == 'hobby' and d['hobby'] not in kinds and d['hobby'] not in made: continue
        if d['kind'] == 'maid' and not maids: continue
        if d['kind'] == 'rumor' and not xs: continue
        ok.append(key)
    key = random.choice(ok)
    kind = KNIFE_DEBTS[key]['kind']
    x = random.choice(xs)['id'] if kind == 'rumor' else 0
    m = random.choice(maids)['id'] if kind == 'maid' else 0
    return key, x, m


def knife_names(debt):
    x = get_consort(debt['x_id']) if debt['x_id'] else None
    m = get_maid(debt['maid_id']) if debt['maid_id'] else None
    return dict(t=display_name(get_consort(debt['victim_id'])), x=display_name(x) if x else '',
                m=m['name'] if m else '', p=display_name(get_consort(debt['consort_id'])))


def knife_betray_p(aff):
    return max(KNIFE_BETRAY_MIN, min(KNIFE_BETRAY_MAX, KNIFE_BETRAY_MAX - (aff - BOND_CLOSE) / 100))


def knife_hits_tick(day):
    """当晚阴谋结算完：得手的记一笔人情，败露的看华妃护不护你"""
    for d in q("SELECT * FROM knife_debts WHERE status='hit'"):
        it = q("SELECT * FROM intrigues WHERE id=?", (d['intrigue_id'],), one=True)
        if not it or it['status'] != 'done': continue
        c = get_consort(d['consort_id'])
        names = knife_names(d)
        if it['result'] == 'success':
            key, x, m = knife_pick_debt(c, d['victim_id'])
            run("""UPDATE knife_debts SET status='owed', debt=?, x_id=?, maid_id=?, start_day=?, due_day=? WHERE id=?""",
                (key, x, m, day + 1, day + KNIFE_DEBTS[key]['days'], d['id']))
            names = knife_names(q("SELECT * FROM knife_debts WHERE id=?", (d['id'],), one=True))
            notify(c['id'], '华妃差人来请你去翊坤宫。' + KNIFE_HIT_LINES[it['method']].format(**names) + '　她接着说：'
                   + KNIFE_DEBTS[key]['ask'].format(**names) + f"（{KNIFE_DEBTS[key]['days']} 天内办妥，去六宫页看）", 'info')
        elif it['result'] == 'caught':
            if random.random() < knife_betray_p(bond(c['id'], 'huafei')):
                run("UPDATE knife_debts SET status='exposed' WHERE id=?", (d['id'],))
                knife_expose(c, it, names)
            else:
                run("UPDATE knife_debts SET status='covered' WHERE id=?", (d['id'],))
                notify(c['id'], '华妃那边的事败露了，她没供出你。' + KNIFE_COVER, 'info')
        else:
            run("UPDATE knife_debts SET status='void' WHERE id=?", (d['id'],))
            notify(c['id'], f"华妃对{names['t']}没能得手。礼，她是不会退的。", 'info')


def knife_expose(c, it, names):
    """华妃把你供了出来：按你亲自出手败露论处"""
    m = it['method']
    if m == 'rumor':
        add_stat(c['id'], 'virtue', -5); cut_favor(c['id'], FAVOR_LOSS['caught_rumor']); pen = f"德行 -5，圣宠 -{FAVOR_LOSS['caught_rumor']}"
    elif m == 'frame':
        confine(c['id']); cut_favor(c['id'], FAVOR_LOSS['caught_frame']); pen = f"禁足半天，圣宠 -{FAVOR_LOSS['caught_frame']}"
    else:
        add_stat(c['id'], 'virtue', -8); pen = '德行 -8'
    tloss = CAUGHT_TRUST_LOSS_LIGHT if m == 'punish' else CAUGHT_TRUST_LOSS
    add_trust(c['id'], -tloss)
    bond_caught_huanghou(c['id'])
    night_mark(c['id'], 'caught')
    notify(c['id'], '华妃在御前把你供了出来：' + ''.join(KNIFE_BETRAY).format(**names) + f"　{pen}，信任 -{tloss}。", 'bad')
    victim = get_consort(it['target_id'])
    if victim and victim['user_id']:
        notify(victim['id'], f"华妃对你下手的事查清了：背后指使她的，是{names['p']}。", 'info')
    gazette(f"华妃供称，对{names['t']}下手是受{names['p']}指使。{names['p']}{pen}。", 'scandal')


def knife_settle_debt(debt, paid):
    names = knife_names(debt)
    cfg = KNIFE_DEBTS[debt['debt']]
    if paid:
        run("UPDATE knife_debts SET status='paid' WHERE id=?", (debt['id'],))
        notify(debt['consort_id'], '华妃的人情还上了。' + cfg['ok'].format(**names), 'good')
        return cfg['ok'].format(**names)
    run("UPDATE knife_debts SET status='broken' WHERE id=?", (debt['id'],))
    hf = npc_row('huafei')
    if hf:
        add_affinity(debt['consort_id'], hf['id'], KNIFE_BROKEN_BOND - bond(debt['consort_id'], 'huafei'))
    notify(debt['consort_id'], cfg['broken'].format(**names) + f"　华妃好感变成 {KNIFE_BROKEN_BOND}，她记恨上你了。", 'bad')
    return cfg['broken'].format(**names)


def knife_debts_tick(day):
    """每晚：自动算的几种人情（不请安 / 散流言 / 送汤羹）看办没办成，到期没办的算赖账"""
    for d in q("SELECT * FROM knife_debts WHERE status='owed'"):
        cfg = KNIFE_DEBTS[d['debt']]
        c = get_consort(d['consort_id'])
        if not c or c['status'] == 'dead':
            run("UPDATE knife_debts SET status='void' WHERE id=?", (d['id'],)); continue
        done = False
        if cfg['kind'] == 'rumor':
            done = bool(q("""SELECT 1 FROM intrigues WHERE attacker_id=? AND target_id=? AND method='rumor' AND day>=?""",
                          (c['id'], d['x_id'], d['start_day']), one=True))
        elif cfg['kind'] == 'seek':
            done = bool(q("""SELECT 1 FROM daily_counters WHERE consort_id=? AND key='seek' AND count>0 AND day BETWEEN ? AND ?""",
                          (c['id'], d['start_day'], d['due_day']), one=True))
        elif cfg['kind'] == 'nogreet':
            if c['greet_day'] >= d['start_day']:
                knife_settle_debt(d, False); continue
            done = day >= d['due_day']
        if done:
            knife_settle_debt(d, True)
        elif day >= d['due_day']:
            knife_settle_debt(d, False)


@app.route('/knife/pay', methods=['POST'])
@login_required
def knife_pay():
    """交银子 / 交作品 / 送宫人；赖账也走这里"""
    c = g.me
    d = knife_open_debt(c['id'])
    if not d or d['status'] != 'owed':
        flash('你没欠华妃什么。', 'bad'); return redirect(url_for('social'))
    cfg = KNIFE_DEBTS[d['debt']]
    if request.form.get('refuse'):
        flash(knife_settle_debt(d, False), 'bad'); return redirect(url_for('social'))
    err = None
    if cfg['kind'] == 'silver':
        if c['silver'] < cfg['amount']: err = f"银子不够，要 {cfg['amount']} 两。"
        else: add_silver(c['id'], -cfg['amount'])
    elif cfg['kind'] == 'hobby':
        try: iid = int(request.form.get('item_id', 0))
        except ValueError: iid = 0
        item = q("SELECT * FROM hobby_items WHERE id=? AND maker_id=? AND holder_id=? AND kind=?",
                 (iid, c['id'], c['id'], cfg['hobby']), one=True)
        if not item: err = f"要一件你亲手做的{HOBBIES[cfg['hobby']]['item_word']}。"
        else:
            run("DELETE FROM displays WHERE item_id=?", (item['id'],))
            run("UPDATE hobby_items SET holder_id=? WHERE id=?", (npc_row('huafei')['id'], item['id']))
    elif cfg['kind'] == 'maid':
        m = get_maid(d['maid_id'])
        if not m or m['status'] != 'active' or m['owner_id'] != c['id']: err = '这名宫人已经不在你宫里了。'
        else: maid_leave(m['id'], 'gone', '被送去翊坤宫当差')
    else:
        err = '这件事做了就算，不用来这里交。'
    if err:
        flash(err, 'bad'); return redirect(url_for('social'))
    flash(knife_settle_debt(d, True), 'good')
    return redirect(url_for('social'))


def knife_view(c):
    """六宫页上华妃那一栏要显示的：能不能借、欠着什么"""
    d = knife_open_debt(c['id'])
    debt = None
    if d and d['status'] == 'owed':
        cfg = KNIFE_DEBTS[d['debt']]
        items = q("SELECT * FROM hobby_items WHERE maker_id=? AND holder_id=? AND kind=?",
                  (c['id'], c['id'], cfg['hobby']), ) if cfg['kind'] == 'hobby' else []
        debt = dict(row=d, cfg=cfg, ask=cfg['ask'].format(**knife_names(d)), works=items,
                    payable=cfg['kind'] in ('silver', 'hobby', 'maid'))
    targets = [] if bond(c['id'], 'huafei') < BOND_INTIMATE else \
        q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND id!=? ORDER BY rank DESC", (c['id'],))
    return dict(debt=debt, pending=bool(d and d['status'] == 'hit'), targets=targets,
                block=knife_block_reason(c) if targets else '', cost=KNIFE_COST)


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
    npcs = [(n, NPC_BOND[n['npc_key']], bond(c['id'], n['npc_key'])) for n in
            q("SELECT * FROM consorts WHERE npc_key IS NOT NULL AND status!='dead' ORDER BY rank DESC, id")
            if n['npc_key'] in NPC_BOND]
    return render_template('social.html', c=c, others=others, rels=rels, known=known, SECRETS=SECRETS,
                           inv=inv, sister_count=len(sisters_of(c['id'])), ACTIONS={k: action_config(c, k) for k in ACTIONS},
                           npcs=npcs, bond_tier=bond_tier, npc_visited=daily_count(c['id'], 'npc_visit'),
                           BOND_CLOSE=BOND_CLOSE, BOND_INTIMATE=BOND_INTIMATE, knife=knife_view(c))

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

CUISHENG_HOURS = 6      # 催产丹每颗缩短的孕期小时数

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
    if it.get('craft'):
        flash('这是宫人自己做的，内务府不卖。', 'bad')
        return redirect(url_for('shop'))
    if c['status'] == 'cold':
        flash('冷宫的人，内务府不理会。', 'bad')
    elif c['silver'] < shop_price(c, it):
        flash(f"银子不够，{it['name']}要 {shop_price(c, it)} 两。", 'bad')
    else:
        add_silver(c['id'], -shop_price(c, it))
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
    elif key == 'cuisheng':
        if not c['pregnant_since'] or not c['pregnancy_started_ts'] or affliction(c['id'], 'chunxin', cur_day()):
            flash('没有身孕，用不着催产丹。', 'bad')
            return redirect(url_for('shop'))
        run('UPDATE consorts SET pregnancy_started_ts=pregnancy_started_ts-? WHERE id=?', (CUISHENG_HOURS * 3600, c['id']))
        msg = f'孕期缩短 {CUISHENG_HOURS} 小时，{pregnancy_due_text(get_consort(c["id"]))}。'
    elif key == 'dianxin':
        add_stat(c['id'], 'health', 2); msg = '体质 +2。'
    elif key == 'tiseng':
        run('UPDATE consorts SET energy=MIN(?, energy+1) WHERE id=?', (ENERGY_MAX, c['id'])); msg = '精神好些了，精力 +1。'
    elif key == 'hebao':
        add_silver(c['id'], 15); msg = '银子 +15 两。'
    elif key == 'xiangnang':
        if c['status'] != 'normal':
            flash('现在佩给谁看呢。', 'bad')
            return redirect(url_for('shop'))
        run("UPDATE consorts SET seek_bonus=seek_bonus+8 WHERE id=?", (c['id'],)); msg = '今晚翻牌子的机会略添一分。'
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
    expire_conspire_invites()
    mine = q("SELECT * FROM intrigues WHERE attacker_id=? OR (partner_id=? AND status NOT IN ('invited','declined','expired')) ORDER BY id DESC LIMIT 15", (c['id'], c['id']))
    invites = q("SELECT * FROM intrigues WHERE partner_id=? AND status='invited' ORDER BY id DESC", (c['id'],))
    partners = [p for p in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status='normal' ORDER BY rank DESC", (c['id'],)) if conspire_affinity(c['id'], p['id']) > CONSPIRE_AFFINITY_MIN]
    known = q("""SELECT k.target_id, c.secret, c.secret_revealed FROM known_secrets k
                 JOIN consorts c ON c.id=k.target_id WHERE k.knower_id=?""", (c['id'],))
    return render_template('intrigue.html', c=c, targets=intrigue_targets(c), INTRIGUES=INTRIGUES, mine=mine, invites=invites, partners=partners,
                           CONSPIRE_METHODS=CONSPIRE_METHODS, CONSPIRE_BONUS=CONSPIRE_BONUS, CONSPIRE_COST_RATIO=CONSPIRE_COST_RATIO, conspire_cost=conspire_cost,
                           known=known, SECRETS=SECRETS, day=day, get_consort=get_consort,
                           used_today=intrigue_capped(c['id']), inventory={k: inv_qty(c['id'], k) for k in (*ITEMS, *DRUGS)}, agents=drug_agents(c['id']))

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
    try: pid = int(request.form.get('partner_id', 0))
    except ValueError: pid = 0
    partner = get_consort(pid) if pid else None
    if not cfg: err = '选一个计策。'
    elif c['status'] != 'normal': err = '你自身难保，先顾好自己吧。'
    elif is_sick(c): err = '你病着，没力气算计别人。'
    elif not t or t['id'] == c['id'] or t['status'] in ('xiunv', 'cold', 'dead'): err = '这个人不能当目标。'
    elif t['npc_key'] and not cfg['npc_ok']: err = f"「{cfg['name']}」不能用在她身上。"
    elif c['rank'] < cfg['min_rank']: err = f"位分到{RANK_NAMES[cfg['min_rank']]}才使得动「{cfg['name']}」。"
    elif intrigue_capped(c['id']): err = f'一天只能谋划 {INTRIGUE_DAILY_MAX} 件事，多了容易露马脚。'
    elif c['energy'] < cfg['energy']: err = f"精力不够，需要 {cfg['energy']} 点。"
    elif c['silver'] < cfg['silver']: err = f"银子不够，需要 {cfg['silver']} 两。"
    elif cfg.get('item') and inv_qty(c['id'], cfg['item']) < 1: err = f"手里没有{ITEMS[cfg['item']]['name']}。"
    elif t['user_id'] and t['entered_day'] >= day: err = '她今天才入宫，皇上正新鲜着，这会儿动手太扎眼。'
    elif q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status IN ('pending','done')",
           (tid, day), one=True)['n'] >= INTRIGUE_TARGET_DAILY_MAX:
        err = '今天盯着她的人已经够多了，换个日子吧。'
    elif method == 'drug':
        err = drug_block(c, t, drug, used, mid, day)
    elif method == 'expose':
        if t['secret_revealed']: err = '她的事早就人尽皆知了。'
        elif not q("SELECT 1 FROM known_secrets WHERE knower_id=? AND target_id=?", (c['id'], tid), one=True):
            err = '你手里没有她的把柄，先去打探。'
    elif method == 'steal' and (t['pregnant_since'] or is_sick(t)):
        err = '她今晚本就侍不了寝。'
    elif method == 'punish':
        err = punish_block(c, t, day)
    elif method == 'impeach':
        err = impeach_block(c, t, day)
    if not err and pid:
        if method not in CONSPIRE_METHODS: err = '这件事不能合谋。'
        elif c['silver'] < conspire_cost(cfg): err = f"合谋每人要 {conspire_cost(cfg)} 两，你的银子不够。"
        elif q("SELECT 1 FROM intrigues WHERE attacker_id=? AND status='invited'", (c['id'],), one=True): err = '你已有一份合谋邀请在等对方回话。'
        else: err = conspire_partner_block(c, partner, cfg, t, day)
    if err:
        flash(err, 'bad')
        return redirect(url_for('intrigue'))
    if pid:   # 合谋：只发邀请，对方点头后双方才扣银子、精力和今天的谋划名额
        run("""INSERT INTO intrigues (day, attacker_id, target_id, method, silver_paid, item_used, created_ts, status, partner_id)
               VALUES (?,?,?,?,0,'',?,'invited',?)""", (day, c['id'], tid, method, now_ts(), pid))
        notify(pid, f"{display_name(c)}邀你合谋对{display_name(t)}「{cfg['name']}」：成算各 +{int(CONSPIRE_BONUS*100)}%，每人 {conspire_cost(cfg)} 两，败露两人一起受罚。去「使计」页回话，一天内有效。", 'info')
        flash(f"已把合谋的意思递给{display_name(partner)}，等她点头；一天内不回话就作废，期间不扣你的银子。", 'info')
        return redirect(url_for('intrigue'))
    run("UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?", (cfg['energy'], cfg['silver'], c['id']))
    if cfg.get('item'): inv_add(c['id'], cfg['item'], -1)
    iid = run("""INSERT INTO intrigues (day, attacker_id, target_id, method, silver_paid, item_used, created_ts)
           VALUES (?,?,?,?,?,?,?)""", (day, c['id'], tid, method, cfg['silver'], cfg.get('item', ''), now_ts())).lastrowid
    if method == 'drug':
        inv_add(c['id'], used, -1)
        run('UPDATE intrigues SET drug=?, item_used=?, agent_maid_id=? WHERE id=?', (drug, used, mid, iid))
    if method == 'punish':   # 和毒害一样，撤回也不重置冷却
        run('UPDATE consorts SET punish_ready_day=? WHERE id=?', (day + PUNISH_COOLDOWN, c['id']))
    if method == 'impeach':
        run('UPDATE consorts SET impeach_ready_day=? WHERE id=?', (day + IMPEACH_COOLDOWN, c['id']))
    daily_inc(c['id'], 'intrigue')
    result = resolve_now(iid)
    if result:
        flash(f"你对{display_name(t)}的「{cfg['name']}」{RESULT_WORDS.get(result, '办完了')}。详情见本宫消息。", RESULT_KIND.get(result, 'info'))
    else:
        flash('已安排下去。截宠要等对方被翻牌时才见分晓。', 'info')
    return redirect(url_for('intrigue'))

@app.route('/intrigue/conspire/<int:iid>/<action>', methods=['POST'])
@login_required
def intrigue_conspire(iid, action):
    c = g.me
    day = cur_day()
    expire_conspire_invites()
    it = q("SELECT * FROM intrigues WHERE id=? AND partner_id=? AND status='invited'", (iid, c['id']), one=True)
    if not it:
        flash('这份合谋的邀请已经没有了。', 'bad')
        return redirect(url_for('intrigue'))
    a, t, cfg = get_consort(it['attacker_id']), get_consort(it['target_id']), INTRIGUES[it['method']]
    if action == 'decline':
        run("UPDATE intrigues SET status='declined' WHERE id=?", (iid,))
        notify(a['id'], f"{display_name(c)}婉拒了合谋对{display_name(t)}「{cfg['name']}」的提议。", 'info')
        flash('你回绝了。', 'info')
        return redirect(url_for('intrigue'))
    if action != 'accept':
        flash('请选择回话。', 'bad')
        return redirect(url_for('intrigue'))
    err = None
    if c['status'] != 'normal' or is_sick(c): err = '你眼下顾不上这件事。'
    elif a['status'] != 'normal' or is_sick(a): err = f"{display_name(a)}眼下顾不上这件事。"
    elif t['status'] in ('xiunv', 'cold', 'dead'): err = '这个人已经不能当目标了。'
    elif intrigue_capped(a['id']): err = f"{display_name(a)}今天已经另有谋划了。"
    elif a['energy'] < cfg['energy']: err = f"{display_name(a)}精力不够了。"
    elif a['silver'] < conspire_cost(cfg): err = f"{display_name(a)}银子不够了。"
    elif q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status IN ('pending','done')", (t['id'], day), one=True)['n'] >= INTRIGUE_TARGET_DAILY_MAX:
        err = '今天盯着她的人已经够多了，换个日子吧。'
    elif it['method'] == 'expose' and t['secret_revealed']: err = '这件事已经没有可告发的了。'
    elif it['method'] == 'steal' and (t['pregnant_since'] or is_sick(t)): err = '她今晚本就侍不了寝。'
    elif it['method'] == 'punish': err = punish_block(a, t, day)
    if not err: err = conspire_partner_block(a, c, cfg, t, day)
    if err:
        flash(err, 'bad')
        return redirect(url_for('intrigue'))
    cost = conspire_cost(cfg)
    for x in (a, c):
        run("UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?", (cfg['energy'], cost, x['id']))
        daily_inc(x['id'], 'intrigue')
    if it['method'] == 'punish': run('UPDATE consorts SET punish_ready_day=? WHERE id=?', (day + PUNISH_COOLDOWN, a['id']))
    run("UPDATE intrigues SET status='pending', day=?, silver_paid=?, partner_silver=?, created_ts=? WHERE id=?", (day, cost, cost, now_ts(), iid))
    notify(a['id'], f"{display_name(c)}答应了合谋：对{display_name(t)}的「{cfg['name']}」已安排下去，你们各付了 {cost} 两。", 'good')
    result = resolve_now(iid)
    if result:
        flash(f"应下了，你付了 {cost} 两。你们对{display_name(t)}的「{cfg['name']}」{RESULT_WORDS.get(result, '办完了')}。", RESULT_KIND.get(result, 'info'))
    else:
        flash(f"应下了，你付了 {cost} 两。截宠要等对方被翻牌时才见分晓。", 'info')
    return redirect(url_for('intrigue'))

@app.route('/intrigue/cancel/<int:iid>', methods=['POST'])
@login_required
def intrigue_cancel(iid):
    c = g.me
    inv = q("SELECT * FROM intrigues WHERE id=? AND attacker_id=? AND status='invited'", (iid, c['id']), one=True)
    if inv:
        run("UPDATE intrigues SET status='cancelled' WHERE id=?", (iid,))
        flash('合谋的邀请收回了，没有扣你任何东西。', 'info')
        return redirect(url_for('intrigue'))
    it = q("SELECT * FROM intrigues WHERE id=? AND attacker_id=? AND status='pending'", (iid, c['id']), one=True)
    if it:
        run("UPDATE intrigues SET status='cancelled' WHERE id=?", (iid,))
        if it['partner_id'] and it['partner_silver']:
            add_silver(it['partner_id'], it['partner_silver'])
            notify(it['partner_id'], f"{display_name(c)}把这回的合谋撤了，你付的银子退还了，精力和今天的名额回不来。", 'info')
        add_silver(c['id'], it['silver_paid'])
        if it['item_used']: inv_add(c['id'], it['item_used'], 1)
        flash('你把人叫了回来，银子和东西收回了，花掉的精力回不来。', 'info')
    return redirect(url_for('intrigue'))

# ── 宫人 ───────────────────────────────────────────────────────────────────────
# 玩家在内务府亲手挑、亲手赐名。名字两个字、全宫不重复（已故、已离开的也算）。
# 每个宫人每天能跑一次差使；每晚领 1 两月钱，忠心随主子的处境涨落。

MAID_QUOTA = {1: 1, 2: 2, 3: 2, 4: 3}   # 官女子 1、答应/常在 2、贵人 3，嫔以上 4
MAID_TRAITS = {
    'shouqiao': dict(name='手巧', desc='手脚利落，心细如发：主子梳妆、练才艺时多帮一把（各 +1），当下药内应也更稳（+8%）。'),
    'zuijin':   dict(name='嘴紧', desc='什么话到她这儿都烂在肚子里：别人来打听你的底细成算 −15%，也很难被人收买；守夜最合适。'),
    'suizui':   dict(name='碎嘴', desc='消息灵通，主子散布流言时成算 +10%，派去探风声最合适。可她自己的嘴也管不住。'),
    'tancai':   dict(name='贪财', desc='见钱眼开，忠心最高只到 70；肯花银子替你多打听一则风声。', cap=70),
    'zhonghou': dict(name='忠厚', desc='老实本分，忠心不会低于 40；被人发落时有一半机会被保下来。', floor=40),
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
PUNISH_COOLDOWN = 3        # 发落宫人：出手的人 3 天一次；每个人的宫人 3 天内最多被发落一个（2026-10-06 从 7 压到 3）
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

MAID_GUARD_LOYALTY, MAID_GUARD_EACH, MAID_GUARD_MAX = 60, 0.03, 0.09   # 忠心 ≥60 的宫人护主：每人让你被使计的成算 −3%，最多 −9%
MAID_LEAK_LOYALTY, MAID_LEAK_EACH, MAID_LEAK_MAX = 30, 0.02, 0.06       # 忠心 <30 的宫人容易泄密：每人让别人对你得手 +2%，最多 +6%
MAID_HEART_LOYALTY = 80        # 忠心 ≥80 是体己人，月钱免了
MAID_WATCH_GUARD = 0.08        # 当天派了宫人守夜：被使计、下药的成算 −8%
MAID_SAVE_CHANCE = 0.5         # 被发落时，忠厚的宫人有这么大概率被人保下来
SHOP_ERRAND_DISCOUNT = 0.9     # 当天派过宫人去内务府跑腿：买东西九折

def maid_defense(cid):
    """宫人护主（正）与泄密（负）合起来，对被使计成算的影响：返回要从对方成算里减掉的值"""
    day = cur_day()
    maids = active_maids(cid)
    loyal = sum(1 for m in maids if m['loyalty'] >= MAID_GUARD_LOYALTY and m['sick_until_day'] < day)
    leaky = sum(1 for m in maids if m['loyalty'] < MAID_LEAK_LOYALTY)
    return min(MAID_GUARD_MAX, MAID_GUARD_EACH * loyal) - min(MAID_LEAK_MAX, MAID_LEAK_EACH * leaky)

def watch_guard(cid):
    return MAID_WATCH_GUARD if daily_count(cid, 'maid_watch') > 0 else 0

def shop_price(c, it):
    price = it['price']
    return max(1, round(price * SHOP_ERRAND_DISCOUNT)) if daily_count(c['id'], 'maid_shop') > 0 else price

# ── 托管角色（看起来和真玩家一模一样，由系统代为过日子）────────────────────────────────
# 它有自己的账号、家族、位分、宫室，翻牌、晋封、被使计、生孩子都和玩家一样；区别只在 users.managed=1：
# 没人能登录，平时白天晚上按概率做日常（晨省、练才艺、串门……），串门会像真人一样给玩家留消息。
# 玩家这边没有任何"NPC"的标记（npc_key 为空）；管理员后台标注「托管」。
BOT_AWAKE_HOURS = (8, 23)           # 这个钟点范围内才有动静（和真人作息差不多）
BOT_ACTION_CHANCE = 1 / 75          # 每分钟动手的概率，约每 75 分钟一件事
BOT_ACTIONS = (('greet', 4), ('study', 3), ('garden', 3), ('visit', 3), ('groom', 1), ('seek', 2))   # 日常动作及权重，复用玩家动作的同一套处理函数
BOT_INTRIGUE_CHANCE = 1 / 900       # 白天每分钟起意害人的概率，约每个白天一次；每天谋划次数和玩家共用 INTRIGUE_DAILY_MAX（现在不限）
BOT_INTRIGUE_METHODS = (('rumor', 5), ('steal', 3), ('frame', 2))    # 只用便宜的三种；下药、巫蛊、告发、发落不做
BOT_GRUDGE_DAYS, BOT_GRUDGE_ATTACKED, BOT_GRUDGE_VICTIM = 5, 4, 2   # 结仇：最近 5 天内，谁算计过她每次 +4 权重，她算计过谁每次 +2（盯着同一个人下手），其余人权重 1
BOT_SILVER_FLOOR = 400              # 托管角色的银子低于这个数就自动补到这个数，保证她出得起手

def spawn_managed_consort(surname, given, rank=4, tier='dali', personality='gentle', age=22, scheme=None):
    """新建一个托管角色并直接安顿进宫（不走殿选）。surname 不能和已有家族重复"""
    if surname_taken(surname):
        raise ValueError(f'姓氏「{surname}」已经有人家用了')
    if q("SELECT 1 FROM consorts WHERE surname=? AND given=?", (surname, given), one=True):
        raise ValueError('宫里已经有同名的人了')
    day = cur_day()
    uid = run("INSERT INTO users (username, password_hash, qq_number, created_ts, managed) VALUES (?,?,?,?,1)",
              ('sys_' + secrets.token_hex(4), generate_password_hash(secrets.token_hex(16), method='pbkdf2:sha256'), '', now_ts())).lastrowid
    create_family(uid, surname, tier)
    st = dict(appearance=random.randint(42, 58), talent=random.randint(40, 56), scheme=scheme if scheme is not None else random.randint(36, 54),
              virtue=random.randint(42, 60), health=random.randint(72, 90))
    cid = run("""INSERT INTO consorts (user_id, surname, given, family, personality, appearance, talent, scheme, virtue, health,
                 silver, secret, status, created_ts, reign_no, seq, entry_age, lineage, patron, inherit, heirloom_maid_id)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'xiunv', ?, ?,?,?,?,?,?,?)""",
              (uid, surname, given, tier, personality, st['appearance'], st['talent'], st['scheme'], st['virtue'], st['health'],
               FAMILIES[tier]['silver'] + 60, roll_secret(), now_ts(), state()['reign_no'], 1, age, '', '', '{}', 0)).lastrowid
    room = empty_residence((('east', 'west'), ('back',)))
    if room is None: raise RuntimeError('宫中屋舍已满')
    palace, hall = room
    run("""UPDATE consorts SET status='normal', rank=?, rank_since_day=1, palace=?, hall=?, favor=?, entered_day=1,
           dianxuan_score=70, energy=?, trust=?, last_audience_day=?, recap_seen_day=?, peak_rank=?, prestige_top=?,
           age_months=?, entry_origin='new', guide_step=-1 WHERE id=?""",
        (rank, palace, hall, 55, ENERGY_MAX, TRUST_START, day, day - 1, rank, rank, (age + AGE_YEARS_PER_DAY * (day - 1)) * 12, cid))
    if rank >= 4: assign_title(cid)
    housing_sync()
    return cid

def managed_consorts():
    return q("SELECT c.* FROM consorts c JOIN users u ON u.id=c.user_id WHERE u.managed=1 AND c.status IN ('normal','confined')")

def bot_care(c):
    """病了请太医、孩子没名字就自己挑一个、银子不够就补上——托管角色没有人替她操心"""
    if c['silver'] < BOT_SILVER_FLOOR:
        add_silver(c['id'], BOT_SILVER_FLOOR - c['silver'])
        c = get_consort(c['id'])
    while c['health'] <= HEALTH_DYING_AT + 8 and c['energy'] > 0 and bot_do(c, 'rest'):      # 体质太低就静养，别让托管角色没人管就死了
        c = get_consort(c['id'])
    for col, flag in (('poisoned_day', 'poison_treatment'), ('ill_day', 'ill_treatment')):
        if c[col] and not c[flag] and c['silver'] >= treat_cost(c):
            add_silver(c['id'], -treat_cost(c))
            run(f"UPDATE consorts SET {flag}=1 WHERE id=?", (c['id'],))
    for h in q("SELECT id FROM heirs WHERE mother_id=? AND name=''", (c['id'],)):
        ensure_name_choices(h['id'])
        hh = get_heir(h['id'])
        if hh['name_choices']:
            run("UPDATE heirs SET name=?, name_choices='' WHERE id=?", (hh['gen_word'] + random.choice(hh['name_choices']), h['id']))

def bot_do(c, key):
    """让托管角色做一件日常：套用玩家同一套检查和处理函数，所以效果、通知、日常记录都和真人一样"""
    cfg = action_config(c, key)
    day = cur_day()
    if not cfg or c['status'] not in cfg['when'] or c['energy'] < cfg['energy'] or c['silver'] < cfg['silver']: return False
    if daily_count(c['id'], key) >= cfg['daily']: return False
    data = {}
    if key == 'study': data['art'] = random.choice(ARTS)
    if key == 'visit':
        others = [x for x in q("""SELECT x.* FROM consorts x JOIN users u ON u.id=x.user_id WHERE u.managed=0 AND x.id!=?
                                 AND x.status='normal'""", (c['id'],)) if daily_count(c['id'], f"visit:{x['id']}") == 0]
        if not others: return False
        data['target_id'] = random.choice(others)['id']
    with app.test_request_context('/', method='POST', data=data):
        try:
            ACTION_HANDLERS[key](c, cfg)
        except Reject:
            return False
        daily_inc(c['id'], key)
        feed_for_action(c, key)
    run("UPDATE consorts SET pending_scene='' WHERE id=? AND pending_scene!=''", (c['id'],))   # 没人替她拿主意的场景直接作废
    return True

def bot_grudge_weights(c, targets):
    """结仇：最近几天谁算计过她、她算计过谁，下手的权重就高一些；其余人一视同仁（随机挑，不看心计高低）"""
    since = cur_day() - BOT_GRUDGE_DAYS
    weights = []
    for t in targets:
        w = 1
        w += BOT_GRUDGE_ATTACKED * q("SELECT COUNT(*) n FROM intrigues WHERE attacker_id=? AND target_id=? AND day>=? AND status!='cancelled'", (t['id'], c['id'], since), one=True)['n']
        w += BOT_GRUDGE_VICTIM * q("SELECT COUNT(*) n FROM intrigues WHERE attacker_id=? AND target_id=? AND day>=? AND status!='cancelled'", (c['id'], t['id'], since), one=True)['n']
        weights.append(w)
    return weights

def bot_intrigue(c):
    """托管角色偶尔害人：只用流言、截宠、栽赃三种便宜的，目标在真玩家里随机挑（带结仇权重），套用玩家同一套检查和结算"""
    day = cur_day()
    if intrigue_capped(c['id']) or c['status'] != 'normal' or is_sick(c): return False
    methods = [(m, w) for m, w in BOT_INTRIGUE_METHODS if c['rank'] >= INTRIGUES[m]['min_rank']
               and c['silver'] >= INTRIGUES[m]['silver'] and c['energy'] >= INTRIGUES[m]['energy']]
    if not methods: return False
    targets = [t for t in q("""SELECT x.* FROM consorts x JOIN users u ON u.id=x.user_id WHERE u.managed=0 AND x.id!=?
                               AND x.status IN ('normal','confined') AND x.entered_day<?""", (c['id'], day))
               if q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status IN ('pending','done')", (t['id'], day), one=True)['n'] < INTRIGUE_TARGET_DAILY_MAX]
    if not targets: return False
    for _ in range(4):                                  # 挑到不合适的（比如截宠碰上有孕的）就换一个
        t = random.choices(targets, weights=bot_grudge_weights(c, targets))[0]
        method = random.choices([m for m, _ in methods], weights=[w for _, w in methods])[0]
        if method == 'steal' and (t['pregnant_since'] or is_sick(t)): continue
        cfg = INTRIGUES[method]
        run("UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?", (cfg['energy'], cfg['silver'], c['id']))
        iid = run("""INSERT INTO intrigues (day, attacker_id, target_id, method, silver_paid, item_used, created_ts)
               VALUES (?,?,?,?,?,?,?)""", (day, c['id'], t['id'], method, cfg['silver'], '', now_ts())).lastrowid
        daily_inc(c['id'], 'intrigue')
        resolve_now(iid)
        return True
    return False

def bot_tick(now):
    st = state()
    if not st['event_started'] or st['maintenance'] or st['mourning']: return
    for c in managed_consorts():
        bot_care(c)
        c = get_consort(c['id'])
        if c['status'] != 'normal' or is_sick(c): continue
        if not (BOT_AWAKE_HOURS[0] <= now.hour < BOT_AWAKE_HOURS[1]): continue
        if c['energy'] > 0 and random.random() < BOT_ACTION_CHANCE:
            keys, weights = zip(*BOT_ACTIONS)
            bot_do(c, random.choices(keys, weights=weights)[0])
        if random.random() < BOT_INTRIGUE_CHANCE:      # 起意害人和做日常各算各的概率
            bot_intrigue(get_consort(c['id']))

def spy_success_p(c, t, m):
    p = 0.35 + (c['scheme'] - t['scheme']) * 0.01 - (0.15 if eyes_active(t) else 0)
    if m['trait'] == 'jiling': p += 0.10
    if has_maid_trait(t['id'], 'zuijin'): p -= 0.15            # 对方宫里有嘴紧的宫人，话不好套
    return clamp(p * 100, 10, 85) / 100

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

IMPEACH_COOLDOWN = 3
IMPEACH_FAVOR_LOSS = 12

def impeach_block(c, t, day):
    if c['rank'] < t['rank'] + 2:
        return '要比她高两级以上，才参奏得动她。'
    if t['rank'] < 3:
        return '她位分太低，不值得参奏。'
    if c['impeach_ready_day'] > day:
        return f"你上次参奏还没过 {IMPEACH_COOLDOWN} 天，第 {c['impeach_ready_day']} 天才能再动手。"
    if t['impeached_day'] and day - t['impeached_day'] < IMPEACH_COOLDOWN:
        return '她前几天刚被参过，这会儿再参太扎眼。'
    return None

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

MAID_CRAFT_MIN_LOYALTY, MAID_CRAFT_BASE, MAID_CRAFT_PER_LOYALTY, MAID_CRAFT_MAX = 40, 0.12, 0.003, 0.35   # 宫人每晚闲时做点东西的概率：忠心 40 起 12%，每高 1 点 +0.3%，最多 35%
MAID_CRAFT = {        # 特质 → 做出什么：item 进背包，silver 直接给银子，gossip 带回一则风声
    'shouqiao': dict(kind='item', key='xiangnang', verb='缝了个'),
    'zhonghou': dict(kind='item', key='dianxin', verb='备了一匣'),
    'jiling':   dict(kind='item', key='tiseng', verb='泡了一壶'),
    'zuijin':   dict(kind='item', key='hebao', verb='缝了个'),
    'tancai':   dict(kind='silver', low=5, high=12),
    'suizui':   dict(kind='gossip'),
}

def maid_craft_chance(loyalty):
    if loyalty < MAID_CRAFT_MIN_LOYALTY: return 0.0
    return min(MAID_CRAFT_MAX, MAID_CRAFT_BASE + (loyalty - MAID_CRAFT_MIN_LOYALTY) * MAID_CRAFT_PER_LOYALTY)

def maid_craft(c, m):
    """宫人闲时偶尔做点小东西。病着的、忠心不到 40 的不做。返回写给主子的那句话，没做就是 None"""
    cur = get_maid(m['id'])
    if cur['status'] != 'active' or cur['sick_until_day'] >= cur_day(): return None
    if random.random() >= maid_craft_chance(cur['loyalty']): return None
    spec = MAID_CRAFT.get(cur['trait'])
    if not spec: return None
    if spec['kind'] == 'item':
        inv_add(c['id'], spec['key'], 1)
        text = f"{cur['name']}闲着没事，{spec['verb']}{ITEMS[spec['key']]['name']}，放进了你的箱笼。"
    elif spec['kind'] == 'silver':
        n = random.randint(spec['low'], spec['high'])
        add_silver(c['id'], n)
        text = f"{cur['name']}替你跑腿时抠下了点零碎，孝敬了 {n} 两。"
    else:
        text = f"{cur['name']}在各宫门口转了转，听来一桩事：" + maid_gossip(c, cur)
    if c['user_id']: notify(c['id'], text, 'good')
    return text

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
        paid = [m for m in maids if m['loyalty'] < MAID_HEART_LOYALTY]      # 忠心 ≥80 的体己人不领月钱
        wage = MAID_WAGE * len(paid)
        if c['silver'] < wage:
            for m in maids: add_loyalty(m['id'], -5)
            if c['user_id']:
                notify(c['id'], f"宫人的月钱发不出来（{len(paid)} 人要 {wage} 两），全宫宫人忠心 -5。", 'bad')
            continue
        add_silver(c['id'], -wage)
        for m in maids:
            add_loyalty(m['id'], -2 if c['status'] == 'confined' else 1)
        if c['status'] != 'confined':
            for m in maids: maid_craft(c, m)
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
    # ── 2026-09-29 扩充 ──
    'sleepy': dict(text='{m}端着茶进来时眼皮直打架，差点把茶盏摔了。你这才想起她昨夜伺候到三更。', opts=[
        dict(text='让她下去歇着，赏二两银子', silver=-2, loyalty=10, say='{m}红着眼眶谢了恩，下去补觉了。'),
        dict(text='让她去洗把脸，接着当差', loyalty=-5, say='{m}应了一声，可手还在抖。')]),
    'jewelry': dict(text='{m}在甬道上捡到一支赤金簪子，看着像是{t}宫里丢的。', needs_target=True, opts=[
        dict(text='亲自送回去', affinity=3, say='{t}接过簪子，多看了你两眼。'),
        dict(text='让{m}悄悄还回去', loyalty=2, affinity=1, say='簪子还了，{t}没说什么。'),
        dict(text='悄悄托人换了银子', silver=15, virtue=-2, loyalty=-3, say='银子是到手了，{m}看你的眼神却有些变了。')]),
    'maid_ill': dict(text='{m}咳嗽好几日了，还硬撑着当差。你听见她夜里咳得厉害。', opts=[
        dict(text='让她歇着，请太医来看（5 两）', silver=-5, loyalty=12, virtue=1, say='太医开了方子，{m}感激得直磕头。'),
        dict(text='让她自己去太医院拿点药', loyalty=-3, say='{m}去了，可回来时脸色更差了。')]),
    'brocade': dict(text='{m}捧着一匹蜀锦进来，说是{t}赏的，让你裁件衣裳。', needs_target=True, opts=[
        dict(text='收下，赏{m}二两', silver=-2, affinity=2, say='蜀锦收下了，你心里却打了个突。'),
        dict(text='婉拒，说无功不受禄', affinity=-3, virtue=1, say='{m}把蜀锦送回去了，{t}那边没说什么。')]),
    'pilfer': dict(text='{m}跪在你面前，说错拿了库房里的东西，求你饶过这一回。', opts=[
        dict(text='罚她月钱，下不为例', loyalty=3, silver=5, say='{m}谢了恩，往后当差更勤快了。'),
        dict(text='这事不能姑息，送去辛者库罚三天苦役', loyalty=-15, virtue=1, say='{m}回来后当差照旧，只是再没正眼看过你。')]),
    'snacks': dict(text='{m}说{t}宫里的小太监总给她塞点心，还问起你的起居。', needs_target=True, opts=[
        dict(text='让她收着，顺便套套对方的话', gossip=True, say=''),
        dict(text='让她以后别收了，免得被人拿捏', loyalty=-3, say='{m}应了，可你总觉得她不太情愿。')]),
    'brother': dict(text='{m}跪着求你，说她哥哥在宫外惹了官司，想求你帮忙说句话。', opts=[
        dict(text='应下了，托人去打点（15 两）', silver=-15, loyalty=15, say='{m}磕头如捣蒜，你心里多了个死忠。'),
        dict(text='让她别为难你，这事不好办', loyalty=-10, say='{m}抹着眼泪下去了。')]),
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

# ── 日常消息（2026-10-06）：嫔妃明面上的日常都记下来，大家都看得到 ─────────────────────────
# 只记这里列出的几样；使计、下药、买药、打探、安插眼线、读书习谋这类暗事一概不记
FEED_KEEP_DAYS = 5
FEED_TEXT = {
    'greet':       lambda t: '到礼仪堂参加了晨省',
    'study':       lambda t: '在宫里练了练才艺',
    'groom':       lambda t: '对镜梳妆，好生打扮了一番',
    'garden':      lambda t: '去御花园逛了逛',
    'seek':        lambda t: '往养心殿送了汤羹',
    'rest':        lambda t: '在宫里静养',
    'reflect':     lambda t: '闭门抄经自省',
    'visit':       lambda t: f"去{display_name(t)}宫里坐了坐" if t else '四处串了串门',
    'plead':       lambda t: f"去养心殿替{display_name(t)}求了情" if t else '去养心殿求了情',
    'pray':        lambda t: '到佛堂上了香',
    'maid_snack':  lambda t: '派宫人去御膳房取了点心',
    'maid_shop':   lambda t: '派宫人去内务府跑了趟腿',
    'perform':     lambda t: '在养心殿御前展示了才艺',
    'palace_work': lambda t: '在礼仪堂协办宫务',
    'aid':         lambda t: f"给{display_name(t)}送去了日常补养" if t else '给姐妹送去了日常补养',
    'attend':      lambda t: '去养心殿侍疾',
    'pizhe':       lambda t: '陪皇上批了折子',
    'chastise':    lambda t: ((f"寻了个由头，罚{display_name(t)}跪了半日" if request.form.get('mode') == 'kneel' else f"寻了个由头，罚了{display_name(t)}的俸银" if request.form.get('mode') == 'fine' else f"寻了个由头，把{display_name(t)}禁了足") if t else '责罚了低位的妃嫔'),
    'shoukang':    lambda t: '去寿康宫给太妃请安',
}

def feed(cid, text):
    run("INSERT INTO daily_feed (day, consort_id, text, created_ts) VALUES (?,?,?,?)", (cur_day(), cid, text, now_ts()))

def feed_for_action(c, key):
    fn = FEED_TEXT.get(key)
    if not fn: return
    t = None
    try: t = get_consort(int(request.form.get('target_id', 0))) if key in ('visit', 'plead', 'aid', 'chastise') else None
    except ValueError: t = None
    feed(c['id'], fn(t))

@app.route('/daily')
@login_required
def daily_page():
    day = cur_day()
    rows = q("SELECT * FROM daily_feed WHERE day>=? ORDER BY day DESC, id DESC LIMIT 400", (max(1, day - 2),))
    days = {}
    for r in rows:
        days.setdefault(r['day'], []).append(dict(r, who=get_consort(r['consort_id']),
                                                 hhmm=datetime.fromtimestamp(r['created_ts'], TZ).strftime('%H:%M')))
    return render_template('daily.html', days=days, today=day)

GOSSIP_WORDS = dict(greet='去景仁宫请了安', study='练了才艺', groom='梳妆打扮', garden='逛了御花园',
                    seek='往养心殿送了汤羹', rest='在宫里静养', reflect='闭门抄经', visit='四处串门',
                    plead='去养心殿替人求情', letter='写了信',
                    npc_visit='去各宫娘娘那儿走动')

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
                           errands=len(free_errand_maids(c)), maid_defense=maid_defense(c['id']), heart=sum(1 for m in mine if m['loyalty'] >= MAID_HEART_LOYALTY),
                           errand_actions=[(k, ACTIONS[k]) for k in ('maid_snack', 'maid_shop', 'maid_scribe', 'maid_watch', 'maid_gossip')],
                           MAID_GUARD_LOYALTY=MAID_GUARD_LOYALTY, MAID_HEART_LOYALTY=MAID_HEART_LOYALTY, costs=dict(reroll=MAID_REROLL_COST,
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
    for r in range(PLAYER_MAX_RANK, 0, -1):
        members = [x for x in rows if x['rank'] == r and x['status'] != 'cold']
        if members or r in RANK_SLOTS:
            groups.append(dict(rank=r, name=RANK_NAMES[r], members=members, cap=RANK_SLOTS.get(r)))
    cold = [x for x in rows if x['status'] == 'cold']
    st = state()
    last_beds = last_bed_consorts(st)
    return render_template('ranks.html', groups=groups, cold=cold, me=g.me, last_beds=last_beds)

GAZETTE_FAVORITES = 5      # 邸报顶部「圣眷最隆」列几位（只写名号，不写圣宠数值）


@app.route('/gazette')
@login_required
def gazette_page():
    day = cur_day()
    rows = q("SELECT * FROM gazette WHERE day>=? ORDER BY day DESC, id DESC", (max(1, day - 7),))
    days = {}
    for r in rows:
        days.setdefault(r['day'], []).append(r)
    if g.me: guide_mark(g.me['id'], 'gazette')
    rank_rows = q("SELECT * FROM consorts WHERE status NOT IN ('xiunv','dead') ORDER BY rank DESC, favor DESC")
    groups = []
    for r in range(PLAYER_MAX_RANK, 0, -1):
        members = [x for x in rank_rows if x['rank'] == r and x['status'] != 'cold']
        if members or r in RANK_SLOTS:
            groups.append(dict(rank=r, name=RANK_NAMES[r], members=members, cap=RANK_SLOTS.get(r)))
    cold = [x for x in rank_rows if x['status'] == 'cold']
    st = state()
    last_beds = last_bed_consorts(st)
    favorites = sorted((x for x in rank_rows if x['status'] in ('normal', 'confined') and x['favor'] > 0),
                       key=lambda x: (-x['favor'], x['id']))[:GAZETTE_FAVORITES]
    bed_top = sorted((x for x in rank_rows if x['bed_daily_day'] == day and x['bed_daily_count'] > 0),
                     key=lambda x: (-x['bed_daily_count'], -x['favor'], x['id']))[:GAZETTE_FAVORITES]
    expecting = []
    for x in rank_rows:
        if x['pregnant_since'] and x['status'] != 'cold':
            pr = pregnancy_progress(x)
            expecting.append(dict(c=x, stage=pr['stage'], hours=pr['hours'], minutes=pr['minutes'], legacy=pr['legacy'],
                                  percent=pr['percent'], due=pregnancy_due_text(x)))
    return render_template('gazette.html', days=sorted(days.items(), reverse=True), day=day,
                            groups=groups, cold=cold, last_beds=last_beds, expecting=expecting, favorites=favorites, bed_top=bed_top, me=g.me)

CN_NUM = '零一二三四五六七八九十'

def heir_rank_word(n):
    """排行的叫法：第一位叫「大」（大阿哥、大公主），其余照常（二、三……）"""
    return '大' if n == 1 else cn_ordinal(n)

def cn_ordinal(n):
    if n <= 10: return CN_NUM[n]
    if n < 20: return '十' + CN_NUM[n - 10]
    return CN_NUM[n // 10] + '十' + (CN_NUM[n % 10] if n % 10 else '')

def maternal_kin(c, h):
    """生母，或者跟生母同一家族、同一届的姐妹（孩子的姨母）"""
    if not h['mother_id'] or not c: return False
    if h['mother_id'] == c['id']: return True
    m = get_consort(h['mother_id'])
    uid = consort_uid(c)
    return bool(m and uid and consort_uid(m) == uid and m['reign_no'] == c['reign_no'])


# ── 字辈与起名库（2026-10-06）：名字 = 本届字辈 + 皇上点的三个字里母亲选的一个 ────────────────────
NAME_GENERATIONS = {   # 每一届一个字辈，儿子、女儿各排各的，按届数轮着用；孩子出生时就定下，之后换届也不变
    '皇子': ['弘', '永', '绵', '奕', '载', '溥', '毓', '启'],
    '公主': ['芳', '怡', '秀', '玲', '巧', '梅', '菱', '彤'],
}
NAME_CHOICES_N = 3
NAME_CHARS = {
    '皇子': {
        '毅': '刚毅果敢', '渊': '学识渊博', '承': '承继基业', '睿': '明智通达', '恪': '恭谨敬事', '谨': '谨慎持重', '瑾': '怀瑾握瑜，品德如美玉',
        '琮': '礼器，端方有度', '璋': '圭璋，品德高洁', '煦': '温暖和煦，待人宽厚', '晟': '光明兴盛', '昀': '日光，前程明朗', '琰': '美玉，才德出众',
        '珩': '佩玉，庄重雅正', '泓': '水深而清，胸怀宽广', '瀚': '浩瀚无边，志向高远', '宸': '北辰所居，贵不可言', '衡': '权衡公平，持正不阿', '烨': '光辉灿烂',
        '湛': '清澈深厚', '恒': '持之以恒', '邦': '国之根本', '肃': '严整端肃', '昭': '光明磊落', '铭': '铭记于心，不负所托', '谦': '谦和礼让', '博': '博闻广识',
        '敏': '敏而好学', '嵘': '峥嵘，才干突出', '栋': '国之栋梁', '彦': '才德出众的贤士', '钧': '千钧之重，担得起事', '勋': '功勋卓著', '钦': '恭敬诚笃',
        '翊': '辅佐护佑，家国之翼', '琛': '珍宝，贤能可贵', '焘': '光照天下', '诚': '至诚守信', '赫': '显赫威严', '岳': '山岳，稳重如山', '澈': '澄澈明净，心地坦荡',
        '稷': '社稷，心系天下', '晔': '光明灿烂', '暄': '温暖明亮', '曜': '日月星辰之光，光耀门楣', '旻': '秋天，天道高远', '昱': '日光明亮', '晖': '日光，光辉普照',
        '暻': '明亮，前路光明', '皓': '洁白光明，品行清白', '琅': '美玉相击，清朗有声', '瑜': '美玉，美德无瑕', '瑛': '玉的光彩，才华外露', '琨': '美玉，贵重高洁',
        '璟': '玉的光彩，才德兼备', '珺': '美玉，君子之德', '玮': '珍奇美玉，才德珍贵', '琪': '美玉，品格高贵', '骁': '骏马，勇武善战', '骥': '千里马，志在千里',
        '骏': '良马，才智出众', '驰': '奔驰，意气风发', '翰': '笔墨文章，文采斐然', '轩': '器宇轩昂', '峻': '高峻，品格崇高', '巍': '巍峨，气势雄伟',
        '峰': '山峰，登高望远', '嵩': '高山，稳固崇高', '崇': '崇高，崇尚德行', '岱': '泰山，镇守一方', '屹': '屹立不倒', '霖': '及时甘雨，泽被万民',
        '沛': '充沛，福泽丰厚', '淳': '淳朴敦厚', '澍': '及时雨，滋润万物', '渟': '水积而静，沉稳深邃', '泽': '恩泽，惠及后人', '洵': '诚信，确实可靠',
        '济': '济世，救助天下', '仁': '仁厚爱人', '义': '重义守信', '礼': '知礼守节', '智': '睿智明达', '信': '诚信不欺', '忠': '忠诚不二', '孝': '孝顺恭敬',
        '廉': '廉洁正直', '德': '品德高尚', '正': '端正不阿', '端': '端方正直', '朗': '开朗明达', '俊': '才智出众', '杰': '人中豪杰', '英': '英才卓越',
        '威': '威严持重', '锐': '锐意进取', '勤': '勤勉不怠', '韬': '韬略，深谋远虑', '策': '筹谋善策', '谋': '深谋远虑',
    },
    '公主': {
        '婉': '温婉贤淑', '嘉': '美好吉祥', '柔': '柔顺温和', '宁': '安宁康泰', '瑶': '美玉，珍贵无比', '琼': '美玉，高贵无瑕', '璇': '美玉，璇玑星辰',
        '琬': '美玉，圭玉端庄', '玥': '传说中的神珠，稀世珍宝', '澜': '清波，从容舒展', '妍': '美丽聪慧', '姝': '容貌与品性皆美', '灵': '聪慧灵秀', '慧': '聪慧明理',
        '淑': '贤淑善良', '懿': '美德，温柔贤善', '贞': '坚贞不移', '仪': '仪态端方', '徽': '美善，德行美好', '蕙': '香草，品性高洁', '兰': '幽兰，清雅脱俗',
        '芷': '香草，芬芳清远', '莹': '晶莹剔透', '茹': '柔韧而有包容', '清': '清朗澄明', '雅': '文雅端庄', '宜': '和顺适宜', '安': '平安无虞', '福': '福泽绵长',
        '禧': '吉祥喜庆', '静': '娴静从容', '珍': '被捧在掌心的珍宝', '琦': '美玉，奇异珍贵', '韵': '风雅有致', '黛': '青黛，眉目如画', '荣': '荣华昌盛',
        '琳': '美玉，声如玉响', '岚': '山间云气，飘逸灵动', '蓉': '芙蓉，出水清丽', '娴': '文静优雅', '媛': '才貌兼备的佳人', '娜': '柔美婀娜', '婷': '美好秀丽',
        '娇': '娇美可人', '妙': '美妙绝伦', '嫣': '笑靥美好', '姣': '容貌姣好', '婕': '美好，宫中女官之选', '嫱': '古时宫中女官，美丽高雅', '倩': '笑容美好',
        '俪': '佳偶，相配成双', '佳': '美好', '欣': '欢欣喜悦', '悦': '愉悦安乐', '愉': '愉快从容', '怜': '怜爱，惹人疼惜', '愫': '真情实意', '慈': '慈爱温厚',
        '惠': '恩惠，贤惠', '恬': '恬静安适', '宓': '安静，安然', '容': '从容大方', '如': '如意顺遂', '意': '称心如意', '心': '心地善良', '思': '思虑周到',
        '念': '惦念，重情', '月': '月色皎洁', '星': '星辰璀璨', '晴': '晴朗明媚', '曦': '晨光熹微', '昕': '黎明，朝气', '旭': '朝阳初升', '暖': '温暖',
        '霞': '彩霞满天', '虹': '彩虹，吉兆', '露': '晨露，晶莹', '雪': '洁白无瑕', '霜': '凌霜，坚韧', '梨': '梨花，洁白清雅', '桃': '桃花，艳丽',
        '杏': '杏花，灿烂', '棠': '海棠，富贵', '荷': '荷花，出淤泥而不染', '莲': '莲花，高洁', '菊': '菊花，傲霜', '茉': '茉莉，清香', '莉': '茉莉，淡雅',
        '薇': '蔷薇，美丽', '萱': '萱草，忘忧', '蕊': '花蕊，娇嫩', '蓓': '蓓蕾，含苞待放', '璐': '美玉，润泽', '璎': '珠玉串饰', '珊': '珊瑚，珍贵',
        '珂': '玉石，洁白', '琴': '琴声，雅致', '笙': '乐器，悠扬', '箫': '洞箫，清远', '诗': '诗意盎然', '书': '书香门第', '画': '如画', '绣': '锦绣',
        '锦': '锦绣前程', '绮': '华美', '纱': '轻柔', '缘': '缘分', '柳': '柳枝，柔韧',
    },
}

def gen_word_for(reign_no, gender):
    words = NAME_GENERATIONS[gender]
    return words[(max(1, reign_no) - 1) % len(words)]

def used_name_chars(gender, gen):
    return {r['name'][len(gen):] for r in q("SELECT name FROM heirs WHERE gender=? AND gen_word=? AND name!=''", (gender, gen))}

def roll_name_choices(h):
    """皇上随机点三个字，同届同性别已经用过的字不再点"""
    pool = list(NAME_CHARS[h['gender']])
    used = used_name_chars(h['gender'], h['gen_word'])
    gens = {w for ws in NAME_GENERATIONS.values() for w in ws}        # 任何一届、任何性别的字辈都不当名字点
    avail = [ch for ch in pool if ch not in used and ch not in gens] or pool
    return random.sample(avail, min(NAME_CHOICES_N, len(avail)))

# ── 皇嗣的容貌与气质（2026-10-07）：容貌随母亲；气质按容貌分档，每 20 点一档，每档 10 种里随机给一种 ──────────
TEMPER_TIERS = [      # 容貌 0～19 / 20～39 / 40～59 / 60～79 / 80 以上
    [('朴拙', '不事雕琢，一派天然'), ('木讷', '话不多，凡事慢半拍'), ('怯生', '见了生人先往后躲'), ('憨直', '想什么说什么'), ('孩子气', '没长大似的，笑起来很甜'),
     ('清瘦', '身形单薄，眉眼安静'), ('淡泊', '与世无争的样子'), ('沉默', '一整天说不了几句话'), ('粗朴', '手脚结实，不爱打扮'), ('笨拙可爱', '做什么都慢吞吞，反倒招人疼')],
    [('平和', '脾气好，从不与人争执'), ('安静', '坐得住，一本书能看半天'), ('本分', '规规矩矩，从不惹事'), ('憨厚', '实在，人缘不坏'), ('温吞', '凡事不急不躁'),
     ('拘谨', '在人前放不开'), ('敦实', '身板结实，看着就让人放心'), ('素净', '衣着朴素，不爱艳色'), ('质朴', '不懂修饰，却很真诚'), ('腼腆', '一说话就脸红')],
    [('端庄', '坐有坐相，站有站相'), ('清秀', '眉目干净，看着舒服'), ('斯文', '谈吐有礼，一身书卷气'), ('伶俐', '眼珠一转就是主意'), ('从容', '遇事不慌，自有章法'),
     ('爽朗', '笑声敞亮，没有心事'), ('稳重', '小小年纪就沉得住气'), ('灵动', '一双眼睛会说话'), ('温雅', '举止温和有度'), ('大方', '落落大方，不怯场')],
    [('俊逸', '身姿挺拔，神采飞扬'), ('明艳', '往那儿一站就亮堂'), ('秀雅', '清雅脱俗，不落俗套'), ('飒爽', '利落干脆，英气逼人'), ('清贵', '眉宇间自带一份矜贵'),
     ('娴静', '安安静静，却叫人移不开眼'), ('灵秀', '聪明漂亮，天生的好模样'), ('风流', '举手投足都有韵致'), ('温润', '如玉一般，让人想亲近'), ('挺拔', '站如青松，一看就是好苗子')],
    [('倾城', '一出现满座皆静'), ('绝尘', '清冷出尘，不似凡人'), ('惊鸿', '惊鸿一瞥，难以忘怀'), ('风华', '举手投足皆是风采'), ('璧人', '如玉如璧，人见人夸'),
     ('天人之姿', '宫里人都说是画里走出来的'), ('芳华', '灼灼其华，明媚照人'), ('瑶光', '像天上的星子，亮得晃眼'), ('凤仪', '自有一股母仪天下的气度'), ('龙章', '龙章凤姿，将来必成大器')],
]
TEMPER_STEP = 20

def temper_tier_of(appearance):
    return max(0, min(len(TEMPER_TIERS) - 1, int(appearance) // TEMPER_STEP))

def roll_temperament(appearance):
    return random.choice(TEMPER_TIERS[temper_tier_of(appearance)])[0]

def temper_desc(name):
    for tier in TEMPER_TIERS:
        for n, d in tier:
            if n == name: return d
    return ''

def refresh_temperament(hid):
    """容貌变了、跨了档就在新档里重新随机一种气质；没跨档不动。出生时和老档补齐都走这里"""
    h = get_heir(hid)
    if not h: return
    tier = temper_tier_of(h['appearance'])
    if h['temper_tier'] == tier and h['temperament']: return
    run("UPDATE heirs SET temper_tier=?, temperament=? WHERE id=?", (tier, roll_temperament(h['appearance']), hid))

def set_heir_appearance(hid, value):
    run("UPDATE heirs SET appearance=? WHERE id=?", (clamp(int(value), 0, 100), hid))
    refresh_temperament(hid)

def migrate_heir_looks(db):
    """老档里的皇嗣补上容貌（随母亲）和气质"""
    for hid, mother in db.execute("SELECT id, mother_id FROM heirs WHERE temper_tier=-1").fetchall():
        row = db.execute("SELECT appearance FROM consorts WHERE id=?", (mother,)).fetchone() if mother else None
        app_ = clamp(int((row[0] if row else 40) * 0.7) + random.randint(-8, 8), 5, 100)
        db.execute("UPDATE heirs SET appearance=?, temper_tier=?, temperament=? WHERE id=?",
                   (app_, temper_tier_of(app_), roll_temperament(app_), hid))

def get_heir(hid):
    return q("SELECT * FROM heirs WHERE id=?", (hid,), one=True)

def ensure_name_choices(hid):
    h = get_heir(hid)
    if not h or h['name'] or h['name_choices']: return
    gen = h['gen_word'] or gen_word_for(state()['reign_no'], h['gender'])
    run("UPDATE heirs SET gen_word=? WHERE id=?", (gen, hid))
    run("UPDATE heirs SET name_choices=? WHERE id=?", (''.join(roll_name_choices(get_heir(hid))), hid))

def name_choice_view(h):
    """页面用：[(字, 寓意)]；没有待选的返回 []"""
    return [(ch, NAME_CHARS[h['gender']].get(ch, '')) for ch in (h['name_choices'] or '')]

def heir_label(h):
    if h['name']: return h['name']
    return f"{heir_rank_word(h['ordinal'])}阿哥" if h['gender'] == '皇子' else f"{heir_rank_word(h['ordinal'])}公主"

def heir_rank_title(h):
    """排行加性别：大皇子、二皇子、大公主……（有名字的孩子在页面上用它标出排行）"""
    return f"{heir_rank_word(h['ordinal'])}{'皇子' if h['gender'] == '皇子' else '公主'}"

app.jinja_env.globals['heir_rank_title'] = heir_rank_title
app.jinja_env.globals['heir_label'] = heir_label
app.jinja_env.globals['treat_cost'] = treat_cost
app.jinja_env.globals['temper_desc'] = temper_desc
app.jinja_env.globals['shop_price'] = shop_price
app.jinja_env.globals['cn_ordinal'] = cn_ordinal
app.jinja_env.globals['TIER_OFFICE_TEXT'] = {k: FAMILY_CAREER_TITLES[k][TIER_OFFICE[k]] for k in TIER_JOB}

@app.route('/title_pick', methods=['POST'])
@login_required
def title_pick():
    c = g.me
    choices = c['title_choices'] or ''
    pick = request.form.get('pick', '').strip()
    if not choices:
        flash('眼下没有可换的封号。', 'bad')
    elif pick == 'keep':
        run("UPDATE consorts SET title_choices='' WHERE id=?", (c['id'],))
        flash(f"你留下了原来的封号「{c['title']}」。", 'info')
    elif pick not in choices:
        flash('请从备选的三个封号里选一个。', 'bad')
    elif q("SELECT 1 FROM consorts WHERE title=? AND id!=? AND status NOT IN ('cold','dead')", (pick, c['id']), one=True):
        flash('这个封号刚被别人用了，重新备选几个。', 'bad')
        run("UPDATE consorts SET title_choices='' WHERE id=?", (c['id'],))
        offer_title_choices(c['id'])
    else:
        old = c['title']
        run("UPDATE consorts SET title=?, title_choices='' WHERE id=?", (pick, c['id']))
        gazette(f"{old}{RANK_NAMES[c['rank']]}改封号为「{pick}」，今称{pick}{RANK_NAMES[c['rank']]}。", 'decree')
        flash(f"皇上允了，你的封号改为「{pick}」。", 'good')
    return redirect(url_for('index'))

SKIN_MAX_LEN = 12
app.jinja_env.globals['SKIN_MAX_LEN'] = SKIN_MAX_LEN


def skin_key(name):
    return re.sub(r'[\s·•．.\-_]+', '', (name or '')).lower()


@app.route('/skin', methods=['POST'])
@login_required
def set_skin():
    """皮相：给自己定一个形象参照（比如某位女明星的名字），六宫榜上能看到；全服不能重复，留空表示清掉"""
    c = g.me
    if not c or c['status'] in ('xiunv', 'dead'):
        return redirect(url_for('index'))
    name = re.sub(r'\s+', '', request.form.get('skin', ''))
    if not name:
        run("UPDATE consorts SET skin='' WHERE id=?", (c['id'],))
        flash('已清掉皮相。', 'info')
    elif len(name) > SKIN_MAX_LEN:
        flash(f'皮相最多 {SKIN_MAX_LEN} 个字。', 'bad')
    elif blocked_hit('皮相', name):
        flash(BLOCKED_MSG, 'bad')
    elif any(skin_key(r['skin']) == skin_key(name) for r in q("SELECT skin FROM consorts WHERE skin!='' AND id!=? AND status!='dead'", (c['id'],))):
        flash('这个皮相已经有人用了，换一个吧。', 'bad')
    else:
        run("UPDATE consorts SET skin=? WHERE id=?", (name, c['id']))
        flash(f'皮相定为「{name}」。', 'good')
    return redirect(url_for('index'))


@app.route('/heirs', methods=['GET', 'POST'])
@login_required
def heirs():
    c = g.me
    if request.method == 'POST':
        try: hid = int(request.form.get('heir_id', 0))
        except ValueError: hid = 0
        pick = request.form.get('pick', '').strip()
        h = q("SELECT * FROM heirs WHERE id=? AND mother_id=?", (hid, c['id']), one=True)
        if not h or h['name']:
            flash('名字已经定了，改不了。', 'bad')
        elif pick not in (h['name_choices'] or ''):
            flash('请从皇上点的三个字里选一个。', 'bad')
        elif q("SELECT 1 FROM heirs WHERE gen_word=? AND name=?", (h['gen_word'], h['gen_word'] + pick), one=True):
            flash('这个字刚被同辈的别人用了，重新点几个字吧。', 'bad')
            run("UPDATE heirs SET name_choices='' WHERE id=?", (hid,))
            ensure_name_choices(hid)
        else:
            name = h['gen_word'] + pick
            run("UPDATE heirs SET name=?, name_choices='' WHERE id=?", (name, hid))
            flash(f"皇上允了，赐名「{name}」——{NAME_CHARS[h['gender']].get(pick, '')}。", 'good')
        return redirect(url_for('heirs'))
    for mine in q("SELECT id FROM heirs WHERE mother_id=? AND name=''", (c['id'],)):
        ensure_name_choices(mine['id'])      # 老档里没点过字的，补上
    rows = q("SELECT h.*, c.surname FROM heirs h LEFT JOIN consorts c ON c.id=h.mother_id ORDER BY h.id")
    day = cur_day()
    acts = {}
    for h in rows:
        a = {}
        if h['mother_id'] == c['id'] and h['caretaker_id'] in (c['id'], 0) and c['rank'] < raise_min_rank(h) and c['status'] == 'normal' \
                and not h['zhuazhou'] and heir_age_days(h, day) < zhuazhou_age_days(h):
            a['entrust'] = True
            if h['foster_request_to']: a['waiting_on'] = get_consort(h['foster_request_to'])
        if h['foster_request_to'] == c['id']: a['reply'] = True
        if h['caretaker_id'] == c['id'] and h['marriage'] == 'choice': a['marry'] = True
        ev = errand_view(h) if h['errand'] else None
        if ev and h['caretaker_id'] == c['id'] and ev.get('key') in ERRANDS:
            a['errand'] = dict(name=ERRANDS[ev['key']]['name'], line=ERRANDS[ev['key']]['line'], approach=ev.get('approach'),
                               can_shift=bool(other_adult_princes(h)))
        if maternal_kin(c, h) and h['caretaker_id'] != c['id'] and c['status'] != 'dead' and not h['adult_day']:
            a['visit'] = True
            if c['rank'] >= raise_min_rank(h): a['reclaim'] = True
            a['reclaim_wait'] = max(0, h['reclaim_after_day'] - day)
        if h['caretaker_id'] == c['id'] and h['mother_id'] != c['id'] and not h['adult_day']: a['can_ban'] = True
        if h['caretaker_id'] == 0 and not h['adult_day'] and heir_age_days(h, day) < HEIR_ADULT_AGE_DAYS and c['rank'] >= raise_min_rank(h) and c['status'] == 'normal':
            a['adopt'] = not maternal_kin(c, h)
            a['adopt_pending'] = bool(q('SELECT 1 FROM heir_claims WHERE consort_id=? AND heir_id=?', (c['id'], h['id']), one=True))
        battle = q('SELECT * FROM custody_battles WHERE heir_id=?', (h['id'],), one=True)
        if battle and battle['status']=='active':
            a['reclaim'] = False
            a['battle'] = battle
            a['battle_participant'] = c['id'] in (battle['challenger_id'],battle['defender_id'])
        if a: acts[h['id']] = a
    targets_for = {h['id']: entrust_candidates(c, raise_min_rank(h)) for h in rows if acts.get(h['id'], {}).get('entrust')}
    return render_template('heirs.html', c=c, rows=rows, get_consort=get_consort, acts=acts, targets_for=targets_for, raise_rank_name=raise_rank_name, name_choice_view=name_choice_view, cur_gen={g_: gen_word_for(state()['reign_no'], g_) for g_ in NAME_GENERATIONS},
                           ERRAND_APPROACHES=ERRAND_APPROACHES, MONGOL_LETTER_INTERVAL=MONGOL_LETTER_INTERVAL, CUSTODY_ACTIONS=CUSTODY_ACTIONS)

# ── 皇嗣成长（九点六节 A~D：还没做成年、抚养关系博弈、夺嫡） ─────────────────────

HEIR_STATS = dict(study='学问', riding='骑射', virtue='品行', health='体质')

# ── 资质：孩子生下来就有的天赋，决定教养时涨得快不快（学问/骑射/品行各一档，100=中人，体质不看资质）──
GIFT_STATS = ('study', 'riding', 'virtue')
GIFT_MIN, GIFT_MAX = 60, 150
GIFT_WORDS = [(80, '平庸'), (100, '中人之资'), (120, '聪颖'), (140, '出众'), (999, '天纵')]


def gift_word(v):
    for th, w in GIFT_WORDS:
        if v < th: return w


def roll_heir_gifts(mother, traits=None):
    """生母的才艺（学问）、体质（骑射）、德行（品行）各带一点遗传，皇上的特长再带一点，剩下是运气"""
    tr = traits if traits is not None else emperor_traits()
    base = dict(study=mother['talent'] if mother else 50, riding=mother['health'] if mother else 60, virtue=mother['virtue'] if mother else 50)
    mid = dict(study=50, riding=60, virtue=50)
    out = {}
    for k in GIFT_STATS:
        v = 100 + (base[k] - mid[k]) * 0.25 + (tr.get(k, 50) - 50) * 0.2 + random.randint(-25, 25)
        out[k] = int(clamp(round(v), GIFT_MIN, GIFT_MAX))
    return out


def gift_text(h):
    return '　'.join(f"{HEIR_STATS[k]}{gift_word(h['gift_' + k])}" for k in GIFT_STATS)


HEIR_PERSONALITIES = {
    'clever':   dict(name='聪敏', desc='读书涨得更快'),
    'honest':   dict(name='憨厚', desc='立规矩效果加倍，读书慢一些'),
    'naughty':  dict(name='顽皮', desc='陪他玩情分涨得多，读书慢一些'),
    'timid':    dict(name='怯懦', desc='将来考校吃亏，但情分涨得快'),
    'stubborn': dict(name='倔强', desc='被罚时情分掉得多，骑射涨得更快'),
}

# ── 皇嗣性格的「细分」（2026-10-07）：大类（决定玩法效果）不变，每个孩子在大类里再带一个细分标签 + 两条小习惯 ──
# 按孩子 id 固定随机，不存库；细分和习惯都只写同一大类里不矛盾的样子。文中的「他」按性别换成「她」
HEIR_PERSONA = {
    'clever': dict(
        tags=[('早慧', '开蒙比旁人早，字认得快'), ('过目不忘', '一页书看过就能背下来'), ('好问', '什么都要问个为什么'), ('机灵', '脑子转得快，一点就透')],
        habits=['听先生讲课，常能抢在前头说出下一句。', '爱翻大人的书，翻不懂就拿去问。', '下棋总比同龄人多看两步。', '谁说过什么，隔了几天还能一字不差复述。',
                '做事爱先琢磨门道，再动手。', '偶尔自作聪明，被乳母点破了会红着脸笑。', '对着一幅画能看上半个时辰。', '数数、算账比谁都快。']),
    'honest': dict(
        tags=[('老实', '说一不二，吩咐什么就做什么'), ('实心眼', '心思单纯，不会拐弯'), ('厚道', '待人真心，吃了亏也不计较'), ('稳当', '凡事慢一拍，却从不出错')],
        habits=['读书慢，可一遍遍地念，念熟了就不忘。', '犯了错，规矩一立就乖乖改了。', '分到好吃的，头一个想着分给身边的人。', '别人逗他，常要过一会儿才反应过来笑。',
                '干活不偷懒，让搬就搬、让扫就扫。', '被夸一句，能高兴上大半天。', '不爱与人争，吵起来先退一步。', '对乳母言听计从。']),
    'naughty': dict(
        tags=[('皮实', '摔了跤拍拍土就爬起来'), ('淘气', '满院子跑，一刻也坐不住'), ('鬼点子多', '总能想出新的玩法'), ('爱闹', '到哪儿哪儿热闹')],
        habits=['爱爬树掏鸟窝，把乳母急得直跺脚。', '书拿在手里坐不过一炷香，就惦记着往外跑。', '最爱缠着人陪他玩，玩起来什么都忘了。', '藏起先生的戒尺，还一脸无辜。',
                '捉了只蛐蛐儿，揣在怀里到处给人看。', '一高兴就大笑，笑声满院子都听得见。', '衣裳总沾着泥，换了干净的不出半日又脏了。', '跟谁都能玩到一块儿去。']),
    'timid': dict(
        tags=[('认生', '见了生人就躲到乳母身后'), ('胆小', '打雷都要钻进被窝'), ('心细', '敏感，别人一个眼神都要多想'), ('黏人', '离不开亲近的人')],
        habits=['夜里不敢一个人睡，非要有人在旁边守着。', '被先生点了名，吓得声音都发颤。', '谁对他好，都记在心里。', '一见生人就低下头，半天不吱声。',
                '受了委屈只会偷偷抹眼泪，不肯说。', '总爱牵着亲近之人的衣角。', '听到大声说话就缩一下肩膀。', '得了点心舍不得吃，先留着给身边人。']),
    'stubborn': dict(
        tags=[('犟脾气', '认准的事九头牛拉不回'), ('要强', '凡事不肯输给别人'), ('硬骨头', '挨了罚也不肯认错'), ('有主见', '自己的主意拿得稳')],
        habits=['摔倒了不许人扶，自己咬着牙爬起来。', '练骑射练到手掌磨出泡，也不肯歇。', '被罚站，站得笔直，一声不吭。', '说好的事谁劝也不改，非要自己试过才死心。',
                '输了就红着眼睛，非要再比一次。', '不爱撒娇，心里再委屈也绷着脸。', '不喜欢被人摆布，让他往东偏要往西。', '一旦认了谁，便格外护着谁。']),
}

def heir_persona(h):
    """孩子的性格展示：大类名 + 细分标签 + 一段描述（按孩子 id 固定，不变）。没有性格的返回 None"""
    pers = HEIR_PERSONALITIES.get(h['personality']) if h['personality'] else None
    spec = HEIR_PERSONA.get(h['personality'])
    if not pers or not spec: return None
    rng = random.Random(h['id'] * 100003 + 17)
    tag, lead = rng.choice(spec['tags'])
    habits = rng.sample(spec['habits'], 2)
    text = f"{lead}。" + ''.join(habits)
    if h['gender'] != '皇子': text = text.replace('他', '她')
    return dict(name=pers['name'], tag=tag, text=text, effect=pers['desc'])

app.jinja_env.globals['heir_persona'] = heir_persona

HEIR_DAYS_PER_YEAR = 1 / AGE_YEARS_PER_DAY  # 所有角色统一时间尺度
ZHUAZHOU_ITEMS = [
    dict(key='book', name='书卷', stat='study', line='一把抓住了那卷书，攥得紧紧的'),
    dict(key='bow', name='弓箭', stat='riding', line='径直扑向那张小弓，谁都拉不开他的手'),
    dict(key='seal', name='印章', stat='virtue', line='摸到那方印章，端端正正地捧在手里'),
    dict(key='abacus', name='算盘', stat='virtue', line='拨弄起了算盘珠子，拨得叮当响'),
    dict(key='rouge', name='胭脂', stat='health', line='伸手碰了碰那盒胭脂，咯咯笑了起来'),
]
ZHUAZHOU_GAIN = 10
ZHUAZHOU_AGE_DAYS = math.ceil(1 * HEIR_DAYS_PER_YEAR)      # 满周岁那天，一定触发抓周

HEIR_RAISE_ENERGY = 1
HEIR_RAISE = {
    'study':      dict(name='读书', gain=dict(study=3)),
    'ride':       dict(name='骑射', gain=dict(riding=3)),
    'ride_girl':  dict(name='琴棋', gain=dict(study=2, virtue=1)),   # 公主版的「骑射」
    'discipline': dict(name='立规矩', gain=dict(virtue=3), affinity=-1),
    'play':       dict(name='陪他玩', affinity=5),
    'grooming':   dict(name='梳洗仪容', silver=20, looks=2, looks_beauty=3),   # 2026-10-07：给孩子梳洗打扮、教仪容，容貌 +2；抚养人容貌 ≥70 时 +3
}
HEIR_GROOM_BEAUTY_LINE = 70       # 抚养人容貌到这条线，教出来的仪容更好
HEIR_LOOKS_GROW_CHANCE = 0.5      # 孩子每过一天（宫中长两岁）有这么大概率自己长开一点，容貌 +1，最高 100

HEIR_EVENT_CHANCE = 0.25
HEIR_FOSTER_TALK_AGE_DAYS = 8 * HEIR_DAYS_PER_YEAR   # 抱养的孩子 8 岁起才会问「我的亲额娘是谁」

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
    # ── 2026-09-29 扩充（study/riding 也能加，见 heir_event_choose） ──
    'bored': dict(text='他撅着嘴说上书房无聊，师傅讲的他都会了。', opts=[
        dict(text='让他背一段给额娘听', affinity=2, study=2, say='他背得滚瓜烂熟，你心里既欣慰又有点担心。'),
        dict(text='让他去御花园玩一会儿', affinity=5, virtue=-1, say='他乐颠颠跑了，只怕师傅要有话说。')]),
    'nightmare': dict(text='夜里乳母来报，说他做噩梦哭了，非要你去陪。', opts=[
        dict(text='亲自去哄他', affinity=8, mother_health=-3, say='他抱着你不撒手，你陪到天亮。'),
        dict(text='让乳母哄着', affinity=-5, say='他哭到半夜才睡，梦里还在喊额娘。')]),
    'rosary': dict(text='他拿着一串佛珠回来，说是{t}给的，还叮嘱别告诉皇阿玛。', needs_target=True, opts=[
        dict(text='收下，但不许他再往{t}那儿跑', affinity=-3, target_affinity=2, say='佛珠收下了，你心里却打了个突。'),
        dict(text='让他原样还回去', affinity=-5, target_affinity=-3, say='他闷闷不乐地去了，{t}那边没说什么。')]),
    'jealous': dict(text='他在御花园看见{t}逗弄别的孩子，回来就闹脾气，说你不疼他。', needs_target=True, opts=[
        dict(text='抱着他哄了半天', affinity=8, mother_health=-2, say='他睡着了，你胳膊酸得抬不起来。'),
        dict(text='「你是大孩子了，别闹。」', affinity=-5, virtue=1, say='他抹着眼泪走了，乳母说你太严厉。')]),
    'riding': dict(text='他说想学骑马，求你准他。', opts=[
        dict(text='准了，让人陪着（12 两）', silver=-12, affinity=6, riding=3, say='他乐得跳起来，你心里却七上八下。'),
        dict(text='「等你再大些。」', affinity=-3, say='他撅着嘴走了。')]),
    'swear': dict(text='宫人悄悄告诉你，他学会了说脏话，说是跟小太监学的。', opts=[
        dict(text='罚他抄十遍《弟子规》', affinity=-5, virtue=3, say='他边抄边哭。'),
        dict(text='把那个小太监打发走', affinity=2, virtue=1, say='小太监被领走了，他吓得不敢说话。')]),
    'future': dict(text='他问你：「额娘，我长大了能当皇上吗？」', opts=[
        dict(text='「那要看你争不争气。」', affinity=3, virtue=-1, say='他眼睛亮了，攥着小拳头说要好好读书。'),
        dict(text='「别胡说，这话不能乱讲。」', affinity=-3, virtue=2, say='他吓得捂住嘴，你心里一紧。')]),
}


def heir_age_days(h, day=None):
    """孩子出生以来过了几天（可以是小数）：有出生时刻的按真实时间算，每 12 小时一岁；老数据、测试里只有出生天数的按天数算"""
    ts = h['born_ts'] if 'born_ts' in h.keys() else 0
    if ts and ts > 0:
        ref = now_ts()
        if day is not None and day < cur_day(): ref -= (cur_day() - day) * 86400
        return max(0.0, (ref - ts) / 86400)
    return (day or cur_day()) - h['born_day']

def zhuazhou_age_days(h):
    """周岁抓周的门槛：有出生时刻的满 12 小时就是一岁，老数据按整天算"""
    ts = h['born_ts'] if 'born_ts' in h.keys() else 0
    return HEIR_DAYS_PER_YEAR if ts and ts > 0 else ZHUAZHOU_AGE_DAYS

def zhuazhou_due(h, day):
    """该不该抓周了：还没抓过，且刚满周岁（有出生时刻的：满 12 小时到 24 小时之间；老数据：正好第 ZHUAZHOU_AGE_DAYS 天）"""
    if h['zhuazhou']: return False
    age = heir_age_days(h, day)
    start = zhuazhou_age_days(h)
    return start <= age < start + (1 if start == ZHUAZHOU_AGE_DAYS else HEIR_DAYS_PER_YEAR)


def heir_age_years(h, day=None):
    """与皇帝、妃子一致，每次结算增长两岁。"""
    return int(heir_age_days(h, day) * AGE_YEARS_PER_DAY)


app.jinja_env.globals['heir_age_years'] = heir_age_years

HEIR_NURSE_WAGE = 30         # 乳母月钱：每个亲自抚养的孩子，每晚
HEIR_TUTOR_FEE = 50          # 师傅束脩：满 6 岁起换成请师傅，每个孩子每晚
HEIR_TUTOR_AGE = 6
HEIR_UNPAID_AFFINITY = -2    # 欠着不给，孩子跟抚养人的情分每晚 -2
HEIR_UNPAID_NIGHTS = 2       # 连着欠这么多晚，孩子被抱去皇嗣养育所
app.jinja_env.globals['HEIR_NURSE_WAGE'] = HEIR_NURSE_WAGE
app.jinja_env.globals['HEIR_TUTOR_FEE'] = HEIR_TUTOR_FEE
app.jinja_env.globals['HEIR_TUTOR_AGE'] = HEIR_TUTOR_AGE
app.jinja_env.globals['HEIR_UNPAID_NIGHTS'] = HEIR_UNPAID_NIGHTS


def heir_upkeep_cost(h, day=None):
    return HEIR_TUTOR_FEE if heir_age_years(h, day) >= HEIR_TUTOR_AGE else HEIR_NURSE_WAGE


app.jinja_env.globals['heir_upkeep_cost'] = heir_upkeep_cost


def heir_upkeep(day):
    """每晚：玩家抚养人给没成年的孩子付乳母月钱（6 岁前）/ 师傅束脩（6 岁起）。冷宫里管不了；银子不够就欠着，孩子情分 -2。养育所和 NPC 抚养人不算。"""
    for c in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead','cold')"):
        kids = list(q("SELECT * FROM heirs WHERE caretaker_id=? AND adult_day=0 AND COALESCE(npc_key,'')=''", (c['id'],)))
        if not kids: continue
        bal = get_consort(c['id'])['silver']
        paid, owed = [], []
        for h in kids:
            cost = heir_upkeep_cost(h, day)
            if bal >= cost:
                bal -= cost; paid.append((h, cost))
            else:
                owed.append(h)
        total = sum(x[1] for x in paid)
        if total: add_silver(c['id'], -total)
        for h in paid: run('UPDATE heirs SET unpaid_days=0 WHERE id=?', (h[0]['id'],))
        taken, warned = [], []
        for h in owed:
            add_heir_affinity(h['id'], 'caretaker', HEIR_UNPAID_AFFINITY)
            n = h['unpaid_days'] + 1
            if n >= HEIR_UNPAID_NIGHTS:
                run('UPDATE heirs SET caretaker_id=0, caretaker_affinity=50, visit_banned=0, concealed=0, unpaid_days=0 WHERE id=?', (h['id'],))
                taken.append(h)
                gazette(f"{display_name(c)}连欠乳母月钱、师傅束脩，{heir_label(h)}被抱去皇嗣养育所，由乳母与师傅照料，{raise_rank_name(h)}位以上可申请领养。", 'decree')
                mother = get_consort(h['mother_id']) if h['mother_id'] and h['mother_id'] != c['id'] else None
                if mother and mother['user_id']:
                    notify(mother['id'], f"{display_name(c)}连欠{heir_label(h)}的乳母月钱、师傅束脩，孩子被抱去皇嗣养育所了。", 'info')
            else:
                run('UPDATE heirs SET unpaid_days=? WHERE id=?', (n, h['id']))
                warned.append(h)
        if taken:
            notify(c['id'], f"{'、'.join(heir_label(h) for h in taken)}连着 {HEIR_UNPAID_NIGHTS} 晚没付上乳母月钱/师傅束脩，被抱去皇嗣养育所了。" + (f"其余已付 {total} 两。" if total else ''), 'bad')
        if warned:
            notify(c['id'], f"银子不够，{'、'.join(heir_label(h) for h in warned)}的乳母月钱/师傅束脩发不出来，孩子对你的情分 {HEIR_UNPAID_AFFINITY}。再欠一晚，孩子就要被抱去皇嗣养育所。" + (f"其余已付 {total} 两。" if total else ''), 'bad')
        elif total and not taken:
            notify(c['id'], f"今晚付了乳母月钱、师傅束脩共 {total} 两。", 'info')


# ── 皇上考校 / 随驾秋狝 ──────────────────────────────────────────────────────

HEIR_EXAM_INTERVAL = 3   # 2026-09-28 从 7 压到 3，配合一届约 13 天
HEIR_EXAM_MIN_AGE, HEIR_EXAM_MAX_AGE = 6, 15
HEIR_HUNT_INTERVAL = 6   # 2026-09-28 从 14 压到 6
HEIR_HUNT_MIN_AGE = 12
HEIR_HUNT_ROLL = 20
HEIR_HUNT_REWARD = 15

# 每 6 天随机抽一位 6~15 岁的皇嗣，给抚养人一段场景替他应对。题目判定用孩子的属性，不是抚养人自己的——
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
    # ── 2026-09-29 扩充。考校对公主也开放，措辞别写成只对皇子（「手足」而不是「兄弟」） ──
    dict(topic='学问', ask='「若让你治理一县之地，你当如何？」', opts=[
        dict(text='让他自己阐述施政之策', stat='study', dc=65, win=dict(heir_favor=10), win_text='他答得头头是道，皇上龙颜大悦：「有见地。」',
             lose=dict(), lose_text='他说了几句便卡住了，皇上没说什么，只是端起茶盏。'),
        dict(text='在一旁替他铺垫几句', stat='study', dc=50, win=dict(heir_favor=6), win_text='你帮着开了个头，他顺着答下去，皇上点头称许。',
             lose=dict(), lose_text='铺垫得有些刻意，皇上看了你一眼，没说什么。')]),
    dict(topic='学问', ask='「『水能载舟，亦能覆舟』，你怎么看？」', opts=[
        dict(text='让他自己解这句话', stat='study', dc=60, win=dict(heir_favor=8), win_text='他答得中规中矩，皇上颔首：「不错。」',
             lose=dict(), lose_text='他答得有些偏，皇上皱了皱眉，没再追问。'),
        dict(text='替他点出关键', stat='study', dc=45, win=dict(heir_favor=5), win_text='你点了一句，他顺着说下去，皇上倒也满意。',
             lose=dict(), lose_text='点得太明显了，皇上不置可否。')]),
    dict(topic='学问', ask='「太祖当年平定天下，你以为靠的是什么？」', opts=[
        dict(text='让他自己说', stat='study', dc=62, win=dict(heir_favor=9), win_text='他说得有理有据，皇上眼中露出赞许。',
             lose=dict(), lose_text='他说不到点子上，皇上叹了口气，没再问。'),
        dict(text='替他圆个场', stat='study', dc=48, win=dict(heir_favor=5), win_text='你帮着搭了两句话，皇上点头：「你教得不错。」',
             lose=dict(), lose_text='圆得不太漂亮，皇上端起茶盏，没再说什么。')]),
    dict(topic='骑射', ask='「听说你近来骑射有进益，射几箭给朕看看。」', opts=[
        dict(text='让他全力发挥', stat='riding', dc=65, win=dict(heir_favor=10), win_text='连中三箭，皇上大笑：「好！不愧是朕的孩子！」',
             lose=dict(), lose_text='手一抖，只中了一箭。皇上没说什么，只是点了点头。'),
        dict(text='让他求稳，别出丑', stat='riding', dc=50, win=dict(heir_favor=6), win_text='稳稳当当射完，皇上点头：「尚可。」',
             lose=dict(), lose_text='射得歪歪扭扭，皇上看了你一眼，没说什么。')]),
    dict(topic='骑射', ask='「骑射之道，你以为最要紧的是什么？」', opts=[
        dict(text='让他自己说', stat='riding', dc=60, win=dict(heir_favor=8), win_text='他说「心稳手稳」，皇上颔首：「说得好。」',
             lose=dict(), lose_text='他说不到点子上，皇上皱了皱眉。'),
        dict(text='替他点一句', stat='riding', dc=45, win=dict(heir_favor=5), win_text='你点了一句，他顺着说下去，皇上点头称许。',
             lose=dict(), lose_text='点得太刻意，皇上看了你一眼，没说什么。')]),
    dict(topic='骑射', ask='「若让你与禁军教头比试一场，你敢不敢？」', opts=[
        dict(text='让他应下', stat='riding', dc=68, win=dict(heir_favor=10), win_text='虽然输了，招式却有章法，皇上笑道：「有胆气。」',
             lose=dict(), lose_text='他怯了场，皇上没说什么，只是摇了摇头。'),
        dict(text='让他婉拒，说还需历练', stat='riding', dc=50, win=dict(heir_favor=5), win_text='皇上点头：「知道进退，也好。」',
             lose=dict(), lose_text='皇上看了你一眼，没说什么。')]),
    dict(topic='品行', ask='「若你的手足犯了错，你当如何？」', opts=[
        dict(text='让他说大义', stat='virtue', dc=65, win=dict(heir_favor=9), win_text='他说「当规劝，若不听则禀明皇阿玛」，皇上颔首：「不错。」',
             lose=dict(), lose_text='他说得太生硬，皇上皱了皱眉。'),
        dict(text='让他说亲情', stat='virtue', dc=50, win=dict(heir_favor=6), win_text='他说「手足一体，当替他担着」，皇上点头：「有情义。」',
             lose=dict(), lose_text='他说得太软，皇上看了你一眼，没说什么。')]),
    dict(topic='品行', ask='「若下人犯了错，你当如何处置？」', opts=[
        dict(text='让他说恩威并施', stat='virtue', dc=62, win=dict(heir_favor=8), win_text='他说「当赏罚分明」，皇上颔首：「说得好。」',
             lose=dict(), lose_text='他说不到点子上，皇上没再追问。'),
        dict(text='让他说宽厚', stat='virtue', dc=48, win=dict(heir_favor=5), win_text='他说「当给一次机会」，皇上点头：「心善。」',
             lose=dict(), lose_text='他说得太软，皇上看了你一眼，没说什么。')]),
    dict(topic='品行', ask='「若有人在你面前说另一位手足的坏话，你当如何？」', opts=[
        dict(text='让他说当制止', stat='virtue', dc=65, win=dict(heir_favor=9), win_text='他说「当不听不信」，皇上颔首：「不错。」',
             lose=dict(), lose_text='他说得太生硬，皇上皱了皱眉。'),
        dict(text='让他说当劝和', stat='virtue', dc=50, win=dict(heir_favor=6), win_text='他说「当劝他们和睦」，皇上点头：「有心。」',
             lose=dict(), lose_text='他说得太软，皇上看了你一眼，没说什么。')]),
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
    eligible = [h for h in q("SELECT * FROM heirs WHERE gender='皇子' AND status!='deposed'") if heir_age_years(h, day) >= HEIR_HUNT_MIN_AGE]
    if not eligible: return
    winner = max(eligible, key=lambda h: h['riding'] + random.randint(0, HEIR_HUNT_ROLL))
    run('UPDATE heirs SET favor=favor+? WHERE id=?', (HEIR_HUNT_REWARD, winner['id']))
    label = heir_label(winner)
    gazette(f"随驾秋狝，{label}猎获最多，圣眷 +{HEIR_HUNT_REWARD}。", 'news')
    caretaker = get_consort(winner['caretaker_id']) if winner['caretaker_id'] else None
    if caretaker and caretaker['user_id']:
        notify(caretaker['id'], f"{label}随驾秋狝，猎获最多，圣眷 +{HEIR_HUNT_REWARD}。", 'good')


def add_heir_affinity(hid, which, delta):
    col = 'mother_affinity' if which == 'mother' else 'caretaker_affinity'
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    run(f'UPDATE heirs SET {col}=? WHERE id=?', (clamp(h[col] + delta), hid))
    if h['caretaker_id'] == h['mother_id']:
        other = 'caretaker_affinity' if which == 'mother' else 'mother_affinity'
        run(f'UPDATE heirs SET {other}=? WHERE id=?', (clamp(h[other] + delta), hid))


RAISE_MIN_RANK_SON, RAISE_MIN_RANK_DAUGHTER = 6, 5     # 2026-10-07 起：妃位以上才能抚养皇子，嫔位以上抚养公主

def raise_min_rank(h):
    """抚养这个孩子至少要的位分：皇子 6（妃）、公主 5（嫔）"""
    return RAISE_MIN_RANK_SON if h['gender'] == '皇子' else RAISE_MIN_RANK_DAUGHTER

def raise_rank_name(h):
    return RANK_NAMES[raise_min_rank(h)]


def pick_foster(exclude=(), min_rank=RAISE_MIN_RANK_DAUGHTER):
    """挑一位够位分、正在当差的妃嫔当养母：带孩子最少的优先，同样多时 NPC 在前"""
    marks = ','.join('?' * len(exclude)) or '-1'
    rows = q(f"""SELECT c.id, COUNT(h2.id) n FROM consorts c LEFT JOIN heirs h2 ON h2.caretaker_id=c.id
                 WHERE c.rank>=? AND c.status='normal' AND c.id NOT IN ({marks})
                 GROUP BY c.id ORDER BY n, c.npc_key IS NULL, c.id""", (min_rank,) + tuple(exclude))
    return get_consort(rows[0]['id']) if rows else None


def raise_looks(h, amt):
    """给孩子加容貌（最高 100），跨档时气质在新档里重抽并告诉抚养人和生母。返回实际加了多少"""
    before = get_heir(h['id'])
    new = min(100, before['appearance'] + amt)
    set_heir_appearance(h['id'], new)
    after = get_heir(h['id'])
    if after['temper_tier'] != before['temper_tier'] and before['temper_tier'] != -1:
        label = heir_label(after)
        for cid in {after['caretaker_id'], after['mother_id']} - {0}:
            cc = get_consort(cid)
            if cc and cc['user_id']:
                notify(cid, f"{label}长开了，气质由「{before['temperament']}」变成了「{after['temperament']}」。", 'good')
    return new - before['appearance']

def heir_looks_grow(day):
    """每天一次：没成年的孩子有一定概率自己长开一点（容貌 +1，最高 100）"""
    for h in q("SELECT * FROM heirs WHERE adult_day=0 AND appearance<100 AND temper_tier>=0"):
        if random.random() < HEIR_LOOKS_GROW_CHANCE: raise_looks(h, 1)

HEIR_AUTO_NAME_AGE = 2      # 孩子到这个岁数还没人起名，系统自动从备选字里挑一个

def heir_growth_tick(day):
    """抓周时低位生母的孩子进入养育所；已经主动托付的维持现有抚养。"""
    heir_looks_grow(day)
    heir_age_events(day)

def heir_age_events(day):
    """到岁数的事：2 岁没起名自动起名、周岁抓周。孩子按出生时刻每 12 小时一岁，所以这个每小时也会跑（见 maybe_settle），夜里结算再补一次"""
    for h in q("SELECT * FROM heirs WHERE name=''"):      # 到 2 岁还没人起名，系统从备选字里随机挑一个
        if heir_age_years(h, day) < HEIR_AUTO_NAME_AGE: continue
        ensure_name_choices(h['id'])
        hh = get_heir(h['id'])
        if not hh['name_choices']: continue
        name = hh['gen_word'] + random.choice(hh['name_choices'])
        run("UPDATE heirs SET name=?, name_choices='' WHERE id=?", (name, h['id']))
        for par in heir_parents(h): notify(par['id'], f"{heir_label(h)}已满 {HEIR_AUTO_NAME_AGE} 岁，一直没起名，宫里按祖制替孩子定了名字：{name}。", 'info')
    for h in [x for x in q("SELECT * FROM heirs WHERE zhuazhou=''") if zhuazhou_due(x, day)]:
        item = random.choice(ZHUAZHOU_ITEMS)
        run(f"UPDATE heirs SET zhuazhou=?, foster_request_to=0, {item['stat']}={item['stat']}+? WHERE id=?",
            (item['key'], ZHUAZHOU_GAIN, h['id']))
        mother = get_consort(h['mother_id'])
        label = heir_label(h)
        gazette(f"{label}周岁抓周，{item['line']}。", 'news')
        if mother and h['caretaker_id'] == mother['id'] and (mother['rank'] < raise_min_rank(h) or mother['status'] != 'normal'):
            run('UPDATE heirs SET caretaker_id=0,caretaker_affinity=50 WHERE id=?', (h['id'],))
            gazette(f'{label}送入皇嗣养育所，由乳母与师傅照料，{raise_rank_name(h)}位以上可申请领养。', 'decree')
        if mother and mother['user_id']:
            notify(mother['id'], f"{label}今日抓周，{item['line']}。{HEIR_STATS[item['stat']]} +{ZHUAZHOU_GAIN}。", 'good')


def heir_rehome_tick(day):
    """抚养人进了冷宫或没了，孩子一律换人带：生母已是嫔以上又正当差，还给生母；否则皇上另指一位"""
    for h in q("SELECT * FROM heirs WHERE caretaker_id!=0 AND adult_day=0"):
        cur = get_consort(h['caretaker_id'])
        if not cur: continue
        if cur['status'] not in ('cold', 'dead'): continue
        mother = get_consort(h['mother_id']) if h['mother_id'] else None
        label = heir_label(h)
        cur_gone = '进了冷宫' if cur['status'] == 'cold' else '薨逝了'
        if mother and h['caretaker_id'] != h['mother_id'] and mother['status'] == 'normal' and mother['rank'] >= raise_min_rank(h):
            run('UPDATE heirs SET caretaker_id=?, caretaker_affinity=mother_affinity WHERE id=?', (mother['id'], h['id']))
            gazette(f"{display_name(cur)}{cur_gone}，{label}由生母{display_name(mother)}领回抚养。", 'decree')
            if mother['user_id']:
                notify(mother['id'], f"{display_name(cur)}{cur_gone}，皇上让你把{label}领回去了。", 'good')
            continue
        run('UPDATE heirs SET caretaker_id=0,caretaker_affinity=50,visit_banned=0,concealed=0 WHERE id=?', (h['id'],))
        gazette(f'{label}转入皇嗣养育所，等待合格妃嫔申请领养。', 'decree')
        continue


# ── 抚养博弈：托付、探视、讨回（九点六节 C） ──────────────────────────────────────

HEIR_VISIT_ENERGY = 1
HEIR_VISIT_GAIN = 4
HEIR_RECLAIM_ENERGY = 1
HEIR_RECLAIM_COOLDOWN = 2
HEIR_ENTRUST_MIN_AFFINITY = 40
HEIR_EXPOSED_PENALTY = 20    # 养母瞒着身世，被生母探视时说破，孩子对养母的情分

def entrust_candidates(c, min_rank=RAISE_MIN_RANK_DAUGHTER):
    """能托付孩子的人：在线的、位分够抚养这个孩子、正当差、好感够"""
    out = []
    for t in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND rank>=? AND id!=?", (min_rank, c['id'])):
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
    if not h or h['mother_id'] != c['id'] or h['caretaker_id'] not in (c['id'], 0): err = '这不是你亲自带着的孩子。'
    elif h['zhuazhou'] or heir_age_days(h) >= zhuazhou_age_days(h): err = '孩子已经周岁，祖制已定，托付不及了。'
    elif c['rank'] >= raise_min_rank(h): err = f'你已是{raise_rank_name(h)}位，本就可以亲自抚养，不必托付。'
    elif c['status'] != 'normal': err = '眼下这个境况，托付不了人。'
    elif not t or t['id'] not in {x['id'] for x in entrust_candidates(c, raise_min_rank(h))}:
        err = f'要托付给{raise_rank_name(h)}位以上、且与你好感不低于 {HEIR_ENTRUST_MIN_AFFINITY} 的姐妹。'
    if err:
        flash(err, 'bad'); return redirect(url_for('heirs'))
    label = heir_label(h)
    run('UPDATE heirs SET foster_request_to=? WHERE id=?', (t['id'], hid))
    notify(t['id'], f"{display_name(c)}想把{label}托付给你抚养。去「子嗣」页点头或回绝。周岁抓周前不答复，祖制就另指别人了。", 'info')
    flash(f"已请{display_name(t)}过目。对方点头之前，孩子仍由皇嗣养育所照料。" if h['caretaker_id'] == 0 else f"已请{display_name(t)}过目。对方点头之前，孩子还在你身边。", 'good')
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
    if c['rank'] < raise_min_rank(h) or c['status'] != 'normal' or h['zhuazhou'] or h['caretaker_id'] not in (0, h['mother_id']) or mother['status'] == 'dead':
        flash('这桩托付已经办不成了。', 'bad'); return redirect(url_for('heirs'))
    run('UPDATE heirs SET caretaker_id=?, caretaker_affinity=50 WHERE id=?', (c['id'], hid))
    add_affinity(c['id'], mother['id'], 5)
    gazette(f"{display_name(mother)}将{label}托付给{display_name(c)}抚养。", 'news')
    if mother['user_id']: notify(mother['id'], f"{display_name(c)}应下了，{label}往后由她抚养。晋到{raise_rank_name(h)}位后可以去求皇上讨回。", 'good')
    flash(f"{label}往后由你抚养，去本宫就能教养。", 'good')
    return redirect(url_for('heirs'))


def heir_visit_cost(c, h):
    """孩子在敬嫔那儿、你又跟她是知己：去探视不花精力"""
    jp = npc_row('jingpin')
    return 0 if jp and h['caretaker_id'] == jp['id'] and bond(c['id'], 'jingpin') >= BOND_INTIMATE else HEIR_VISIT_ENERGY


@app.route('/heirs/visit/<int:hid>', methods=['POST'])
@login_required
def heir_visit(hid):
    c = get_consort(g.me['id'])
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    err = None
    if not h or not maternal_kin(c, h) or h['caretaker_id'] == c['id']: err = '孩子就在你身边。'
    elif c['status'] != 'normal': err = '你现在出不了门。'
    elif c['energy'] < heir_visit_cost(c, h): err = '精力不够了。'
    elif daily_count(c['id'], f'hvisit:{hid}'): err = '今天已经去看过了。'
    else:
        fo = get_consort(h['caretaker_id'])
        if fo and fo['status'] != 'normal': err = '抚养人眼下不在宫里，见不着。'
        elif fo and h['visit_banned'] and fo['user_id']: err = f"{display_name(fo)}不许你探视。"
    if err:
        flash(err, 'bad'); return redirect(url_for('heirs'))
    label = heir_label(h)
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (heir_visit_cost(c, h), c['id']))
    daily_inc(c['id'], f'hvisit:{hid}')
    add_heir_affinity(hid, 'mother', HEIR_VISIT_GAIN)
    msg = f"你去{display_name(fo) + '宫' if fo else '养育所'}看了{label}，跟生母的情分 +{HEIR_VISIT_GAIN}。"
    if h['concealed']:
        run('UPDATE heirs SET concealed=0 WHERE id=?', (hid,))
        add_heir_affinity(hid, 'caretaker', -HEIR_EXPOSED_PENALTY)
        msg += f"你忍不住说破了身世，{label}才知道被瞒了这么久。"
        if fo and fo['user_id']:
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
@atomic
def heir_reclaim(hid):
    c = get_consort(g.me['id'])
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    err = None
    if not h or not maternal_kin(c, h) or h['caretaker_id'] == c['id']: err = '孩子本就在你身边。'
    elif h['adult_day'] or heir_age_days(h) >= HEIR_ADULT_AGE_DAYS: err = '孩子已经成年，不能再变更抚养。'
    elif c['rank'] < raise_min_rank(h): err = f'{raise_rank_name(h)}位以上才能求皇上把孩子还回来。'
    elif c['status'] != 'normal': err = '你现在去不了养心殿。'
    elif cur_day() < h['reclaim_after_day']: err = f"皇上刚驳回过，{h['reclaim_after_day'] - cur_day()} 天后才能再求。"
    elif c['energy'] < HEIR_RECLAIM_ENERGY: err = '精力不够了。'
    if err:
        flash(err, 'bad'); return redirect(url_for('heirs'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (HEIR_RECLAIM_ENERGY, c['id']))
    label = heir_label(h)
    old = get_consort(h['caretaker_id'])
    if h['caretaker_id'] == 0:
        run('UPDATE heirs SET caretaker_id=?,caretaker_affinity=mother_affinity,visit_banned=0,concealed=0 WHERE id=?', (c['id'],hid))
        run('DELETE FROM heir_claims WHERE heir_id=?', (hid,))
        flash(f'{label}已从养育所领回，由你亲自教养。', 'good')
        return redirect(url_for('heirs'))
    battle = q('SELECT * FROM custody_battles WHERE heir_id=?', (hid,), one=True)
    if battle and battle['status'] == 'active':
        run('UPDATE consorts SET energy=energy+? WHERE id=?', (HEIR_RECLAIM_ENERGY,c['id']))
        flash('抚养权争夺已经开始，请在双方进度下选择行动。', 'info')
        return redirect(url_for('heirs'))
    run("INSERT OR REPLACE INTO custody_battles(heir_id,challenger_id,defender_id,started_day) VALUES(?,?,?,?)", (hid,c['id'],old['id'],cur_day()))
    notify(old['id'], f'{display_name(c)}申请讨回{label}，抚养权争夺开始。双方进度从 0 开始，先达到 100 者胜。去子嗣页应战。', 'bad')
    flash('抚养权争夺开始：双方从 0 出发，每日各最多行动两次，先到 100 者胜。', 'good')
    return redirect(url_for('heirs'))


CUSTODY_TARGET = 100
CUSTODY_ACTIONS = {
    'appeal': dict(name='御前陈情', silver=0, stat='trust'),
    'bond': dict(name='陪伴孩子', silver=0, stat='affinity'),
    'provide': dict(name='筹备教养', silver=50, stat='virtue'),
}


def finish_custody_battle(battle, winner, reason):
    h = q('SELECT * FROM heirs WHERE id=?', (battle['heir_id'],), one=True)
    run("UPDATE custody_battles SET status='finished',winner_id=? WHERE heir_id=? AND status='active'", (winner,battle['heir_id']))
    if h:
        run('UPDATE heirs SET reclaim_after_day=? WHERE id=?', (cur_day()+HEIR_RECLAIM_COOLDOWN,h['id']))
        if winner == battle['challenger_id']:
            run('UPDATE heirs SET caretaker_id=?,caretaker_affinity=mother_affinity,visit_banned=0,concealed=0 WHERE id=?', (winner,h['id']))
            add_affinity(battle['challenger_id'],battle['defender_id'],-10)
        text = f"{heir_label(h)}抚养权争夺结束：{display_name(get_consort(winner))}胜出。{reason}"
        gazette(text,'decree')
        for cid in (battle['challenger_id'],battle['defender_id']): notify(cid,text,'good' if cid==winner else 'bad')


def custody_battle_tick(day):
    for b in q("SELECT * FROM custody_battles WHERE status='active'"):
        h = q('SELECT * FROM heirs WHERE id=?',(b['heir_id'],),one=True)
        if not h or h['caretaker_id'] != b['defender_id']:
            run("UPDATE custody_battles SET status='void' WHERE heir_id=?",(b['heir_id'],))
            continue
        challenger, defender = get_consort(b['challenger_id']), get_consort(b['defender_id'])
        if not challenger or challenger['status'] != 'normal' or challenger['rank'] < raise_min_rank(h):
            finish_custody_battle(b,b['defender_id'],'申请人已失去抚养资格。')
        elif not defender or defender['status'] in ('dead','cold'):
            finish_custody_battle(b,b['challenger_id'],'原抚养人已无法继续照料。')
        elif h['adult_day'] or heir_age_days(h,day)>=HEIR_ADULT_AGE_DAYS:
            win = b['challenger_id'] if b['challenger_progress']>b['defender_progress'] else b['defender_id']
            finish_custody_battle(b,win,'孩子成年，按当前进度裁决；平局维持原抚养。')


@app.route('/heirs/custody/<int:hid>', methods=['POST'])
@login_required
@atomic
def custody_action(hid):
    c = get_consort(g.me['id'])
    b = q("SELECT * FROM custody_battles WHERE heir_id=? AND status='active'",(hid,),one=True)
    h = q('SELECT * FROM heirs WHERE id=?',(hid,),one=True)
    key = request.form.get('action')
    cfg = CUSTODY_ACTIONS.get(key)
    if not b or c['id'] not in (b['challenger_id'],b['defender_id']):
        flash('你不是这场抚养权争夺的参与者。','bad'); return redirect(url_for('heirs'))
    if not h or h['adult_day'] or heir_age_days(h)>=HEIR_ADULT_AGE_DAYS or h['caretaker_id']!=b['defender_id']:
        custody_battle_tick(cur_day())
        flash('抚养状态已变化，请查看最新裁决。','info'); return redirect(url_for('heirs'))
    if c['status']!='normal' or (c['id']==b['challenger_id'] and c['rank']<raise_min_rank(h)):
        flash('当前无法参与抚养权争夺。','bad'); return redirect(url_for('heirs'))
    side = 'challenger' if c['id']==b['challenger_id'] else 'defender'
    if key=='yield':
        finish_custody_battle(b,b['defender_id'] if side=='challenger' else b['challenger_id'],'对方主动让步。')
        return redirect(url_for('heirs'))
    counter = f'custody:{hid}:{b["started_day"]}'
    if not cfg or c['energy']<1 or c['silver']<cfg['silver'] or daily_count(c['id'],counter)>=2:
        flash('每日最多两次行动；每次需 1 精力，筹备教养另需 50 两。','bad'); return redirect(url_for('heirs'))
    affinity = h['mother_affinity'] if side=='challenger' else h['caretaker_affinity']
    value = affinity if cfg['stat']=='affinity' else c[cfg['stat']]
    gain = min(36,24+value//10+(6 if key=='provide' else 0))
    run('UPDATE consorts SET energy=energy-1,silver=silver-? WHERE id=?',(cfg['silver'],c['id']))
    daily_inc(c['id'],counter)
    col = side+'_progress'
    progress = min(CUSTODY_TARGET,b[col]+gain)
    run(f'UPDATE custody_battles SET {col}=? WHERE heir_id=?',(progress,hid))
    if progress>=CUSTODY_TARGET: finish_custody_battle(b,c['id'],'争夺进度率先达到 100。')
    flash(f"{cfg['name']}：进度 +{gain}，当前 {progress}/100。",'good')
    return redirect(url_for('heirs'))


# ── 成年（九点六节 E）：皇子封爵开府、孝敬、差事、替母求情；公主指婚 ─────────────────────

HEIR_ADULT_AGE_YEARS = 14
HEIR_ADULT_AGE_DAYS = HEIR_ADULT_AGE_YEARS * HEIR_DAYS_PER_YEAR  # 7 次结算满 14 岁
PRINCE_TITLES = [(80, '亲王'), (60, '郡王'), (40, '贝勒'), (0, '贝子')]
FILIAL_SILVER = {'亲王': 24, '郡王': 16, '贝勒': 10, '贝子': 5}   # 每晚孝敬的银子，按情分分给生母、养母
PRINCE_PLEAD_INTERVAL = 3   # 2026-09-28 从 7 压到 3
PRINCE_PLEAD_FAVOR_BONUS = 0.003
ERRAND_INTERVAL = 3
MARRY_MIN_FAVOR, MARRY_MIN_TRUST = 35, 30   # 公主自己的圣眷、抚养人的信任够了才能自己选（试玩里原来的 60 / 50 一次也没人够到）
MARRY_CHOICE_DAYS = 3         # 母亲三天不表态，就按留京下嫁办
MONGOL_TRUST_GAIN = 10
MONGOL_LETTER_INTERVAL = 3   # 2026-09-28 从 7 压到 3
CAPITAL_DECAY_FACTOR = 0.5    # 女儿留京、天天回宫请安，母亲的圣宠流失减半

ERRANDS = {
    'relief':  dict(name='赈灾', stat='virtue', line='南边闹了水患，皇上命他去督办赈济'),
    'river':   dict(name='治河', stat='study',  line='黄河又要汛了，皇上命他去看河工'),
    'audit':   dict(name='查贪', stat='virtue', line='户部出了亏空，皇上命他去查账'),
    'exam':    dict(name='监考', stat='study',  line='今年春闱，皇上命他去监考'),
}
# base：成功率的底；win/lose：成败的圣眷变化
ERRAND_APPROACHES = {
    'steady': dict(name='稳妥办理', base=0.65, win=3, lose=-1),
    'grab':   dict(name='抢功', base=0.45, win=8, lose=-6),
    'shift':  dict(name='推给别的阿哥', base=0.60, win=4, lose=-8, rival=-4),
}
FAMILY_LETTERS = [
    '额娘安好。这里风沙大，帐子里日日烧着奶茶，我一切都好，勿念。',
    '今日随夫君去草场看了马群，想起额娘教我的那几句诗，写在这里给额娘解闷。',
    '入冬了，这边冷得早。额娘给的那件斗篷我一直收着，舍不得穿。',
    '这里的人待我很好，只是夜里常想起宫里的灯。额娘要保重身子。',
    '前几日下了头场雪，满地都白了。我在雪里站了一会儿，想着京里今日不知下不下。',
]


def prince_title_for(favor):
    return next(t for lo, t in PRINCE_TITLES if favor >= lo)


def heir_parents(h):
    """生母、养母里还在、又是玩家的人（同一个人只算一次）"""
    seen, out = set(), []
    for cid in (h['mother_id'], h['caretaker_id']):
        if not cid or cid in seen: continue
        seen.add(cid)
        c = get_consort(cid)
        if c and c['user_id'] and c['status'] != 'dead': out.append(c)
    return out


def heir_full_title(h):
    return f"{h['title']}{heir_label(h)}" if h['title'] and h['gender'] == '皇子' else heir_label(h)


def marry_off(h, kind, chosen):
    """指婚定下来。chosen=True 表示是母亲自己选的（抚蒙古才有信任加成）"""
    title = '固伦公主' if kind == 'mongol' else '和硕公主'
    run('UPDATE heirs SET marriage=?, title=?, marry_day=? WHERE id=?', (kind, title, cur_day(), h['id']))
    label = heir_label(h)
    if kind == 'mongol':
        gazette(f"{label}年满{HEIR_ADULT_AGE_YEARS}岁，册封{title}，远嫁蒙古。", 'decree')
        for p in heir_parents(h):
            extra = ''
            if chosen and p['id'] == h['caretaker_id']:
                add_trust(p['id'], MONGOL_TRUST_GAIN); extra = f"皇上感念你深明大义，信任 +{MONGOL_TRUST_GAIN}。"
            notify(p['id'], f"{label}册封{title}，远嫁蒙古，此后每 {MONGOL_LETTER_INTERVAL} 天会有家书寄来。{extra}", 'decree')
    else:
        gazette(f"{label}年满{HEIR_ADULT_AGE_YEARS}岁，册封{title}，留京下嫁。", 'decree')
        for p in heir_parents(h):
            notify(p['id'], f"{label}册封{title}，留京下嫁，天天能回宫请安。你的圣宠流失减半。", 'decree')


def choose_marriage_default(h):
    """没有能拿主意的玩家母亲：够格的（圣眷、抚养人信任）留京，不够格的皇上直接指婚抚蒙古"""
    caretaker = get_consort(h['caretaker_id'])
    if caretaker and heir_standing(h) >= MARRY_MIN_FAVOR and caretaker['trust'] >= MARRY_MIN_TRUST:
        marry_off(h, 'capital', False)
    else:
        marry_off(h, 'mongol', False)


def heir_come_of_age(h, day):
    label = heir_label(h)
    run('UPDATE heirs SET adult_day=?, foster_request_to=0 WHERE id=?', (day, h['id']))
    h = q('SELECT * FROM heirs WHERE id=?', (h['id'],), one=True)
    if h['gender'] == '皇子':
        title = prince_title_for(heir_standing(h))
        run('UPDATE heirs SET title=? WHERE id=?', (title, h['id']))
        if not h['npc_key']:
            amb = clamp(35 + AMBITION_BASE.get(h['personality'], 0) + random.randint(-10, 10))
            run('UPDATE heirs SET ambition=? WHERE id=?', (amb, h['id']))
        gazette(f"{label}年满{HEIR_ADULT_AGE_YEARS}岁，封为{title}，出宫开府。", 'decree')
        if title == '亲王':
            for uid_ in {consort_uid(p_) for p_ in heir_parents(h)}:
                add_prestige_uid(uid_, PRESTIGE_PRINCE_TITLE, f"{label}封了亲王")
        for p in heir_parents(h):
            notify(p['id'], f"{label}年满{HEIR_ADULT_AGE_YEARS}岁，皇上封为{title}，出宫开府了。往后每晚有孝敬银子，每 {ERRAND_INTERVAL} 天还会有一件差事等你帮他拿主意（去「子嗣」页）。", 'decree')
        return
    caretaker = get_consort(h['caretaker_id'])
    eligible = heir_standing(h) >= MARRY_MIN_FAVOR and caretaker and caretaker['trust'] >= MARRY_MIN_TRUST
    if caretaker and caretaker['user_id'] and caretaker['status'] != 'dead' and eligible:
        run("UPDATE heirs SET marriage='choice' WHERE id=?", (h['id'],))
        notify(caretaker['id'], f"{label}年满{HEIR_ADULT_AGE_YEARS}岁，该指婚了。皇上念你的功劳，许你自己拿主意：留京下嫁，还是抚蒙古？去「子嗣」页选，{MARRY_CHOICE_DAYS} 天内不表态，就按留京下嫁办。", 'decree')
        gazette(f"{label}年满{HEIR_ADULT_AGE_YEARS}岁，皇上正在为她择婿。", 'news')
    else:
        choose_marriage_default(h)


def heir_marriage_deadline_tick(day):
    for h in q("SELECT * FROM heirs WHERE marriage='choice' AND ?>=adult_day+?", (day, MARRY_CHOICE_DAYS)):
        marry_off(h, 'capital', False)


def heir_filial_tick(day):
    """开府的皇子每晚孝敬：按跟生母、养母的情分分账，只有玩家收得到"""
    totals = {}
    for h in q("SELECT * FROM heirs WHERE adult_day>0 AND gender='皇子' AND title!='' AND status!='deposed'"):
        total = FILIAL_SILVER.get(h['title'], 0)
        ps = heir_parents(h)
        if not total or not ps: continue
        if len(ps) == 1:
            shares = {ps[0]['id']: total}
        else:
            aff = {h['mother_id']: max(h['mother_affinity'], 1), h['caretaker_id']: max(h['caretaker_affinity'], 1)}
            mine = round(total * aff[h['mother_id']] / (aff[h['mother_id']] + aff[h['caretaker_id']]))
            shares = {h['mother_id']: mine, h['caretaker_id']: total - mine}
        for cid, amt in shares.items():
            if amt <= 0: continue
            add_silver(cid, amt)
            t = totals.setdefault(cid, [0, []])
            t[0] += amt; t[1].append(heir_full_title(h))
    for cid, (amt, names) in totals.items():
        notify(cid, f"{'、'.join(names)}孝敬了 {amt} 两。", 'good')


def heir_plead_tick(day):
    """开府的皇子替被禁足、关冷宫的母亲（生母和养母）求情，3 天一次，成败都算一次"""
    for h in q("SELECT * FROM heirs WHERE adult_day>0 AND gender='皇子' AND title!='' AND plead_ready_day<=?", (day,)):
        targets = []
        for cid in dict.fromkeys((h['mother_id'], h['caretaker_id'])):
            t = get_consort(cid) if cid else None
            if not t or t['status'] not in ('confined', 'cold'): continue
            if t['status'] == 'cold' and not t['user_id']: continue   # NPC 进了冷宫就不再出来
            targets.append(t)
        if not targets: continue
        t = max(targets, key=lambda x: x['status'] == 'cold')
        run('UPDATE heirs SET plead_ready_day=? WHERE id=?', (day + PRINCE_PLEAD_INTERVAL, h['id']))
        who = heir_full_title(h)
        if random.random() < min(0.95, plead_chance(t) + h['favor'] * PRINCE_PLEAD_FAVOR_BONUS):
            cut = 1 if t['status'] == 'confined' else 2
            run("UPDATE consorts SET status_until_day=status_until_day-? WHERE id=?", (cut, t['id']))
            if t['user_id']: notify(t['id'], f"{who}在皇上跟前替你求了情，日子缩短了 {cut} 天。", 'good')
            t2 = get_consort(t['id'])
            if t2['status_until_day'] <= day:
                if t2['status'] == 'cold':
                    release_from_cold(t['id'], f"{who}替母求情，")
                else:
                    run("UPDATE consorts SET status='normal', status_until_day=0 WHERE id=?", (t['id'],))
                    if t['user_id']: notify(t['id'], '禁足解了。', 'good')
        elif t['user_id']:
            notify(t['id'], f"{who}替你求情，皇上没有松口。", 'info')


def errand_view(h):
    try: data = json.loads(h['errand']) if h['errand'] else None
    except ValueError: data = None
    return data


def other_adult_princes(h):
    return list(q("SELECT * FROM heirs WHERE adult_day>0 AND gender='皇子' AND title!='' AND status!='deposed' AND id!=?", (h['id'],)))


def errand_default_approach(h):
    """玩家没交代办法时，皇子自己看着办：野心大的抢功，没野心的能推就推"""
    if h['ambition'] >= 60: return 'grab'
    if h['ambition'] < 30 and other_adult_princes(h): return 'shift'
    return 'steady'


def heir_errand_tick(day):
    """先把手上的差事办了，再看今天该不该派新的。差事办法由抚养人选；没选的按稳妥办，NPC 抚养的自己随机"""
    for h in q("SELECT * FROM heirs WHERE adult_day>0 AND gender='皇子' AND title!='' AND status!='deposed' AND errand!=''"):
        data = errand_view(h)
        if data and data.get('day', 0) >= day: continue   # 今晚刚派的，明晚才交差
        run("UPDATE heirs SET errand='' WHERE id=?", (h['id'],))
        ern = ERRANDS.get((data or {}).get('key'))
        if not ern: continue
        key = data.get('approach') or errand_default_approach(h)
        if key == 'shift' and not other_adult_princes(h): key = 'steady'
        ap = ERRAND_APPROACHES[key]
        p = ap['base'] + (h[ern['stat']] - 50) * 0.004 + min(FACTION_ERRAND_BONUS_CAP, heir_faction_count(h) * FACTION_ERRAND_BONUS)
        p = max(0.15, min(0.9, p))
        ok = random.random() < p
        delta = ap['win'] if ok else ap['lose'] * (2 if h['status'] == 'crown' else 1)
        run('UPDATE heirs SET favor=MAX(0, favor+?) WHERE id=?', (delta, h['id']))
        who = heir_full_title(h)
        rival_line = ''
        if key == 'shift' and ok:
            rival = random.choice(other_adult_princes(h))
            run('UPDATE heirs SET favor=MAX(0, favor+?) WHERE id=?', (ap['rival'], rival['id']))
            rival_line = f"（{heir_full_title(rival)}替他背了锅，圣眷 {ap['rival']}）"
            for p_ in heir_parents(rival):
                notify(p_['id'], f"{heir_full_title(rival)}被{who}推来一件{ern['name']}的差事，办得不漂亮，圣眷 {ap['rival']}。", 'bad')
        text = f"{who}办{ern['name']}差事（{ap['name']}），{'办成了' if ok else '办砸了'}，圣眷 {delta:+d}。{rival_line}"
        for p_ in heir_parents(h):
            notify(p_['id'], text, 'good' if ok else 'bad')
        if abs(delta) >= 6:
            gazette(f"{who}办{ern['name']}差事，{'得了皇上称赞' if ok else '办得不力，被皇上申饬'}。", 'news')
    for h in q("SELECT * FROM heirs WHERE adult_day>0 AND gender='皇子' AND title!='' AND status!='deposed' AND errand=''"):
        if (day - h['adult_day']) % ERRAND_INTERVAL: continue
        key = random.choice(list(ERRANDS))
        data = dict(key=key, day=day)
        caretaker = get_consort(h['caretaker_id'])
        if not (caretaker and caretaker['user_id'] and caretaker['status'] != 'dead'):
            data['approach'] = errand_default_approach(h)   # 没有玩家拿主意，皇子自己看着办
        run('UPDATE heirs SET errand=? WHERE id=?', (json.dumps(data), h['id']))
        if caretaker and caretaker['user_id'] and caretaker['status'] != 'dead':
            notify(caretaker['id'], f"{heir_full_title(h)}接了一件{ERRANDS[key]['name']}的差事：{ERRANDS[key]['line']}。明晚交差前，去「子嗣」页替他选办法。", 'info')


def heir_family_letter_tick(day):
    """抚蒙古的公主，每 3 天给母亲寄一封家书"""
    for h in q("SELECT * FROM heirs WHERE marriage='mongol' AND marry_day>0 AND ?>marry_day", (day,)):
        if (day - h['marry_day']) % MONGOL_LETTER_INTERVAL: continue
        label = f"{h['title']}{heir_label(h)}"
        for p in heir_parents(h):
            run("""INSERT INTO letters (from_id, to_id, day, body, sender_label, created_ts) VALUES (0,?,?,?,?,?)""",
                (p['id'], day, random.choice(FAMILY_LETTERS), label, now_ts()))
            notify(p['id'], f"{label}从蒙古寄来一封家书，去「书信」看看。", 'good')


def heir_adult_tick(day):
    for h in [x for x in q("SELECT * FROM heirs WHERE adult_day=0") if heir_age_days(x, day) >= HEIR_ADULT_AGE_DAYS]:
        heir_come_of_age(h, day)
    heir_marriage_deadline_tick(day)
    heir_filial_tick(day)
    heir_plead_tick(day)
    heir_errand_tick(day)
    heir_family_letter_tick(day)


def capital_mother_ids():
    """有女儿留京下嫁的母亲（生母、养母都算）：圣宠流失减半"""
    ids = set()
    for h in q("SELECT mother_id, caretaker_id FROM heirs WHERE marriage='capital'"):
        ids.update((h['mother_id'], h['caretaker_id']))
    return ids


@app.route('/heirs/marry/<int:hid>', methods=['POST'])
@login_required
def heir_marry(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    kind = request.form.get('kind')
    if not h or h['caretaker_id'] != c['id'] or h['marriage'] != 'choice' or kind not in ('capital', 'mongol'):
        flash('这桩婚事轮不到你拿主意。', 'bad'); return redirect(url_for('heirs'))
    marry_off(h, kind, True)
    flash('皇上准了。', 'good')
    return redirect(url_for('heirs'))


@app.route('/heirs/errand/<int:hid>', methods=['POST'])
@login_required
def heir_errand(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    data = errand_view(h) if h else None
    key = request.form.get('approach')
    if not h or h['caretaker_id'] != c['id'] or not data or key not in ERRAND_APPROACHES:
        flash('没有这件差事。', 'bad'); return redirect(url_for('heirs'))
    if key == 'shift' and not other_adult_princes(h):
        flash('没有别的成年阿哥可推。', 'bad'); return redirect(url_for('heirs'))
    data['approach'] = key
    run('UPDATE heirs SET errand=? WHERE id=?', (json.dumps(data), hid))
    flash(f"已交代：{ERRAND_APPROACHES[key]['name']}。", 'good')
    return redirect(url_for('heirs'))


# ── 夺嫡（九点六节 F，第一阶段）：圣眷、党羽、野心、站队、立储/废储、万寿节、手段 ───────────

RIVAL_MIN_AGE = 12                    # 12 岁起算进储位人选、可以站队
NPC_MERIT_CAP = 15                    # 系统皇子（三阿哥、四阿哥等）累计功绩最多算 15，试玩里他们靠秋狝、差事攒到 100+，玩家的孩子再怎么养也追不上
NPC_CARETAKER_BONUS_CAP = 10          # 抚养他们的 NPC 妃嫔（皇后、齐妃）给的位分加成最多算 10
RANK_BONUS = {5: 5, 6: 10, 7: 12, 8: 15, 9: 20, 10: 20}          # 抚养人位分给皇子圣眷的加成
FACTION_WARN, FACTION_SCOLD = 5, 8    # 党羽超过 5 圣眷每晚 -2；超过 8 皇上当众训斥
FACTION_WARN_LOSS, FACTION_SCOLD_LOSS, FACTION_SCOLD_INTERVAL = 2, 15, 5   # 训斥间隔 2026-09-28 从 10 压到 5
FACTION_ERRAND_BONUS, FACTION_ERRAND_BONUS_CAP = 0.02, 0.10
CROWN_MIN_STANDING, CROWN_MIN_LEAD, CROWN_DEPOSE_BELOW = 70, 15, 50
CROWN_INTERVAL = 5   # 2026-09-28 从 10 压到 5
BIRTHDAY_INTERVAL = 8   # 2026-09-28 从 20 压到 8
FEUD_DAYS, FEUD_LOSS = 3, 3
STANCE_LOCK_DAYS = 3   # 2026-09-28 从 7 压到 3
CROWN_HIT_BONUS = 0.15                # 别人对太子使离间，成功率 +15%
AMBITION_BASE = dict(clever=15, stubborn=20, naughty=5, timid=-15, honest=-10)
AMBITION_SPY_CHANCE, AMBITION_MAKE_FRIEND_CHANCE, AMBITION_DISCORD_CHANCE = 0.0, 0.40, 0.15
FACTION_SELF_CAP = 12
PERSUADE_ENERGY, PERSUADE_STEP, PERSUADE_DEAF_BELOW = 1, 10, 40

SUCCESSION_MOVES = {
    'discord': dict(name='离间', silver=30, energy=1),
    'bribe':   dict(name='收买上书房', silver=100, energy=1),
    'counsel': dict(name='公主进言', silver=0, energy=1),
    'feud':    dict(name='挑拨兄弟', silver=80, energy=1, min_scheme=50),
    'frame':   dict(name='构陷皇子', silver=400, energy=2, min_rank=6),
    'peek':    dict(name='窥匾', silver=500, energy=1, min_rank=5),
    'forge':   dict(name='矫诏', silver=1000, energy=2, min_rank=8),
}
FRAME_PRINCE_BASE, FRAME_PRINCE_PER_SCHEME = 0.30, 0.004
FRAME_PRINCE_CAUGHT, FRAME_PRINCE_CAUGHT_TRUST, FRAME_PRINCE_CAUGHT_VIRTUE = 0.20, 8, 5
DISCORD_BASE, DISCORD_LOSS, DISCORD_CAUGHT = 0.60, 8, 0.15
BRIBE_BONUS, COUNSEL_GAIN, COUNSEL_INTERVAL = 15, 8, 3   # 间隔 2026-09-28 从 7 压到 3
STANCE_ACTS = {
    'tidy':   dict(name='替他打点', silver=25, energy=1, kind='open', merit=2, line='你替他上下打点了一番'),
    'tip':    dict(name='考校前递消息', silver=0, energy=1, kind='open', exam=5, line='你把师傅的偏好悄悄递给了他'),
    'gift':   dict(name='暗里塞银子', silver=50, energy=0, kind='secret', merit=2, line='你悄悄给他塞了银子'),
}
GIFTS = {
    'calligraphy': dict(name='自己写的字', stat='study', silver=0),
    'fur':         dict(name='亲手猎的貂皮', stat='riding', silver=0),
    'antique':     dict(name='花重金买的古玩', stat=None, silver=100),
}
ANTIQUE_BASE, ANTIQUE_ROLL, GIFT_ROLL = 60, 20, 30
BIRTHDAY_WIN, BIRTHDAY_LOSE = 10, -5


def heir_standing(h):
    """圣眷 = 学问×0.3 + 骑射×0.2 + 品行×0.3 + 累计功绩（考校、秋狝、差事、站队相助）+ 抚养人位分加成 + 抚养人信任×0.1。
    heirs.favor 存的是「累计功绩」那一项，皇子真正的圣眷用这个函数算"""
    merit = min(h['favor'], NPC_MERIT_CAP) if h['npc_key'] else h['favor']    # 系统皇子的功绩封顶，免得玩家的孩子永远追不上
    v = h['study'] * 0.3 + h['riding'] * 0.2 + h['virtue'] * 0.3 + merit
    care = get_consort(h['caretaker_id']) if h['caretaker_id'] else None
    if care and care['status'] != 'dead':
        bonus = RANK_BONUS.get(care['rank'], 0)
        if care['npc_key']: bonus = min(bonus, NPC_CARETAKER_BONUS_CAP)
        v += bonus + care['trust'] * 0.1
    return int(round(v)) + family_support(h)


def heir_faction_count(h):
    """党羽 = 生母、养母及她们姐妹的家族数 + 明着站过来的人 + 自己结交的朝臣。
    家族系统（九点九节）还没做，家族先按角色的 family 字段算，NPC 每人算一家"""
    fams = set()
    for cid in (h['mother_id'], h['caretaker_id']):
        if not cid: continue
        for x in (cid, *sisters_of(cid)):
            c = get_consort(x)
            if c and c['status'] != 'dead': fams.add(f"u{consort_uid(c)}" if consort_uid(c) else f"#{x}")
    open_n = q("SELECT COUNT(*) n FROM stances WHERE kind='open' AND heir_id=?", (h['id'],), one=True)['n']
    return len(fams) + open_n + h['faction']


def rival_princes(day=None, exclude_id=0):
    """夺嫡人选：12 岁以上、没被废的皇子"""
    return [h for h in q("SELECT * FROM heirs WHERE gender='皇子' AND status!='deposed' AND id!=?", (exclude_id,))
            if heir_age_years(h, day) >= RIVAL_MIN_AGE]


def add_merit(hid, delta):
    run('UPDATE heirs SET favor=MAX(0, favor+?) WHERE id=?', (delta, hid))


def sow_discord(target, source_label, attacker=None):
    """对某位皇子散流言：成功圣眷 -8（太子更容易中）。attacker 是玩家时，败露有概率被对方的母亲查到"""
    p = DISCORD_BASE + (CROWN_HIT_BONUS if target['status'] == 'crown' else 0)
    ok = random.random() < p
    if ok: add_merit(target['id'], -DISCORD_LOSS)
    label = heir_full_title(target)
    for par in heir_parents(target):
        if ok: notify(par['id'], f"宫里有人在传{label}的闲话，皇上听了几句，{label}的圣眷 -{DISCORD_LOSS}。", 'bad')
    if attacker and random.random() < DISCORD_CAUGHT:
        for par in heir_parents(target):
            notify(par['id'], f"你查到，散布{label}流言的是{display_name(attacker)}。", 'bad')
            add_affinity(attacker['id'], par['id'], -20)
    return ok


def heir_orphan_tick(day):
    """养育所接受玩家孩子，申请在夜间统一抽签，无申请时持续照料。"""
    for h in q("SELECT * FROM heirs WHERE caretaker_id=0 AND adult_day=0"):
        claims = q("SELECT c.* FROM heir_claims hc JOIN consorts c ON c.id=hc.consort_id WHERE hc.heir_id=? AND c.status='normal' AND c.user_id IS NOT NULL AND c.rank>=? ORDER BY hc.day,c.id", (h['id'], raise_min_rank(h)))
        if claims:
            win = pick_weighted(claims, [max(1, c['trust'] + c['rank'] * 5) for c in claims])
            run('UPDATE heirs SET caretaker_id=?,caretaker_affinity=50,visit_banned=0,concealed=0 WHERE id=?', (win['id'], h['id']))
            gazette(f"皇上准{display_name(win)}从养育所领养{heir_label(h)}。", 'decree')
            for c in claims:
                notify(c['id'], f"{heir_label(h)}由{display_name(win)}领养。", 'good' if c['id'] == win['id'] else 'info')
            mother = get_consort(h['mother_id'])
            if mother and mother['user_id'] and mother['id'] != win['id']:
                notify(mother['id'], f"{heir_label(h)}已由{display_name(win)}领养，晋到{raise_rank_name(h)}位后可申请领回。", 'info')
        else:
            run('UPDATE heirs SET study=MIN(100,study+2),riding=MIN(100,riding+2),virtue=MIN(100,virtue+2) WHERE id=?', (h['id'],))
        run('DELETE FROM heir_claims WHERE heir_id=?', (h['id'],))


def heir_ambition_tick(day):
    """成年皇子有自己的心思：野心 ≥ 60 去结交朝臣，≥ 80 会私下对兄弟使绊子。事后才通知抚养人"""
    for h in q("SELECT * FROM heirs WHERE adult_day>0 AND gender='皇子' AND title!='' AND status!='deposed'"):
        who = heir_full_title(h)
        if h['ambition'] >= 60 and h['faction'] < FACTION_SELF_CAP and random.random() < AMBITION_MAKE_FRIEND_CHANCE:
            run('UPDATE heirs SET faction=faction+1 WHERE id=?', (h['id'],))
            for par in heir_parents(h): notify(par['id'], f"{who}近来常与朝臣走动，又结交了一位。", 'info')
        if h['ambition'] >= 80 and random.random() < AMBITION_DISCORD_CHANCE:
            rivals = rival_princes(day, exclude_id=h['id'])
            if rivals:
                target = random.choice(rivals)
                sow_discord(target, who)
                for par in heir_parents(h): notify(par['id'], f"{who}私下对{heir_full_title(target)}使了绊子，事后才有人告诉你。", 'info')


def heir_feud_tick(day):
    for h in q("SELECT * FROM heirs WHERE feud_until_day>=?", (day,)):
        add_merit(h['id'], -FEUD_LOSS)


def heir_faction_tick(day):
    """结党过多：超过 5 个每晚圣眷 -2，超过 8 个皇上当众训斥（5 天一次）"""
    for h in q("SELECT * FROM heirs WHERE gender='皇子' AND status!='deposed'"):
        n = heir_faction_count(h)
        if n <= FACTION_WARN: continue
        add_merit(h['id'], -FACTION_WARN_LOSS)
        if n > FACTION_SCOLD and day >= h['reprimand_ready_day']:
            add_merit(h['id'], -FACTION_SCOLD_LOSS)
            run('UPDATE heirs SET reprimand_ready_day=? WHERE id=?', (day + FACTION_SCOLD_INTERVAL, h['id']))
            label = heir_full_title(h)
            gazette(f"皇上当众训斥{label}结党营私。", 'news')
            for par in heir_parents(h): notify(par['id'], f"{label}结党过多，皇上当众训斥，圣眷 -{FACTION_SCOLD_LOSS}。", 'bad')


def depose_crown(h):
    run("UPDATE heirs SET status='deposed', errand='' WHERE id=?", (h['id'],))
    label = heir_full_title(h)
    gazette(f"皇上下旨废黜太子{label}，圈禁高墙。", 'decree')
    care = get_consort(h['caretaker_id']) if h['caretaker_id'] else None
    if care and care['user_id'] and care['status'] != 'dead' and care['rank'] > 1:
        demote_rank(care['id'])
    for par in heir_parents(h):
        notify(par['id'], f"太子{label}被废，圈禁。" + ('你受牵连，降了一级。' if par['id'] == h['caretaker_id'] else ''), 'bad')


def heir_court_tick(day):
    """朝议立储：每 5 天，最高圣眷 ≥ 70 且领先第二名 15 以上，明立太子；否则留中不发。太子圣眷低于 50 就废"""
    for h in q("SELECT * FROM heirs WHERE status='crown'"):
        if heir_standing(h) < CROWN_DEPOSE_BELOW: depose_crown(h)
    if day % CROWN_INTERVAL: return
    ranked = sorted(rival_princes(day), key=heir_standing, reverse=True)
    if not ranked or any(h['status'] == 'crown' for h in ranked): return
    top = heir_standing(ranked[0])
    second = heir_standing(ranked[1]) if len(ranked) > 1 else 0
    if top >= CROWN_MIN_STANDING and top - second >= CROWN_MIN_LEAD:
        run("UPDATE heirs SET status='crown' WHERE id=?", (ranked[0]['id'],))
        label = heir_full_title(ranked[0])
        gazette(f"大臣联名请立储，皇上准奏，册立{label}为皇太子。", 'decree')
        for par in heir_parents(ranked[0]): notify(par['id'], f"{label}被册立为太子。树大招风，往后别人对他使绊子更容易得手，他办砸差事也要扣双倍。", 'decree')
    else:
        gazette('大臣上折请立储，皇上留中不发。', 'news')


def heir_birthday_tick(day):
    """万寿节（皇上生辰）：12 岁以上的皇子各献寿礼，皇上当众评点，头名圣眷 +10，末名 -5"""
    if day % BIRTHDAY_INTERVAL: return
    princes = rival_princes(day)
    if not princes: return
    scores = {}
    for h in princes:
        gift = h['gift'] if h['gift'] in GIFTS else random.choice(['calligraphy', 'fur'])
        care = get_consort(h['caretaker_id']) if h['caretaker_id'] else None
        if GIFTS[gift]['silver']:
            if care and care['silver'] >= GIFTS[gift]['silver']: add_silver(care['id'], -GIFTS[gift]['silver'])
            else: gift = 'calligraphy'   # 银子不够，只好自己写幅字
        stat = GIFTS[gift]['stat']
        scores[h['id']] = (ANTIQUE_BASE + random.randint(0, ANTIQUE_ROLL)) if not stat else h[stat] + random.randint(0, GIFT_ROLL)
        run("UPDATE heirs SET gift='' WHERE id=?", (h['id'],))
    best = max(princes, key=lambda h: scores[h['id']])
    add_merit(best['id'], BIRTHDAY_WIN)
    gazette(f"万寿节，{heir_full_title(best)}献的寿礼最得皇上欢心，圣眷 +{BIRTHDAY_WIN}。", 'news')
    for par in heir_parents(best): notify(par['id'], f"万寿节上，{heir_full_title(best)}的寿礼拔得头筹，圣眷 +{BIRTHDAY_WIN}。", 'good')
    if len(princes) > 1:
        worst = min(princes, key=lambda h: scores[h['id']])
        if worst['id'] != best['id']:
            add_merit(worst['id'], BIRTHDAY_LOSE)
            for par in heir_parents(worst): notify(par['id'], f"万寿节上，{heir_full_title(worst)}的寿礼不称圣意，圣眷 {BIRTHDAY_LOSE}。", 'bad')


def heir_succession_tick(day):
    heir_ambition_tick(day)
    heir_feud_tick(day)
    heir_faction_tick(day)
    heir_court_tick(day)
    heir_birthday_tick(day)


@app.route('/heirs/persuade/<int:hid>', methods=['POST'])
@login_required
def heir_persuade(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    kind = request.form.get('kind')
    err = None
    if not h or h['caretaker_id'] != c['id'] or not h['adult_day'] or h['gender'] != '皇子': err = '这不是你抚养的成年阿哥。'
    elif kind not in ('calm', 'strive'): err = '劝他什么？'
    elif c['energy'] < PERSUADE_ENERGY: err = '精力不够了。'
    elif daily_count(c['id'], f'persuade:{hid}'): err = '今天已经劝过他了。'
    if err:
        flash(err, 'bad'); return redirect(url_for('succession'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (PERSUADE_ENERGY, c['id']))
    daily_inc(c['id'], f'persuade:{hid}')
    label = heir_label(h)
    if h['caretaker_affinity'] < PERSUADE_DEAF_BELOW and random.random() < 0.5:
        flash(f"{label}把脸一扭：「额娘又不是我亲额娘。」他没听进去。", 'bad')
    else:
        delta = -PERSUADE_STEP if kind == 'calm' else PERSUADE_STEP
        run('UPDATE heirs SET ambition=? WHERE id=?', (clamp(h['ambition'] + delta), hid))
        flash(f"{label}听进去了。野心 {delta:+d}。", 'good')
    return redirect(url_for('succession'))


@app.route('/succession')
@login_required
def succession():
    c = g.me
    day = cur_day()
    princes = sorted(rival_princes(day), key=heir_standing, reverse=True)
    board = [dict(h=h, standing=heir_standing(h), faction=heir_faction_count(h), parents=heir_parents(h)) for h in princes]
    for row in board:
        h = row['h']
        row['mine'] = h['caretaker_id'] == c['id']
        row['cared_by'] = get_consort(h['caretaker_id']) if h['caretaker_id'] else None
    stances = {r['kind']: r for r in q("SELECT * FROM stances WHERE consort_id=?", (c['id'],))}
    mine_adult_princes = [h for h in q("SELECT * FROM heirs WHERE caretaker_id=? AND gender='皇子' AND adult_day>0 AND status!='deposed'", (c['id'],))]
    my_kids_exam = [h for h in q("SELECT * FROM heirs WHERE caretaker_id=? AND adult_day=0", (c['id'],)) if 6 <= heir_age_years(h, day) <= 15]
    princesses = [h for h in q("SELECT * FROM heirs WHERE caretaker_id=? AND gender='公主'", (c['id'],)) if heir_age_years(h, day) >= RIVAL_MIN_AGE]
    orphans = q("SELECT * FROM heirs WHERE caretaker_id=0 AND adult_day=0")
    my_claims = {r['heir_id'] for r in q("SELECT heir_id FROM heir_claims WHERE consort_id=?", (c['id'],))}
    return render_template('succession.html', c=c, day=day, board=board, stances=stances, mine_adult_princes=mine_adult_princes,
                           my_kids_exam=my_kids_exam, princesses=princesses, orphans=orphans, my_claims=my_claims,
                           get_consort=get_consort, heir_standing=heir_standing, STANCE_ACTS=STANCE_ACTS, GIFTS=GIFTS,
                           SUCCESSION_MOVES=SUCCESSION_MOVES, STANCE_LOCK_DAYS=STANCE_LOCK_DAYS, PERSUADE_ENERGY=PERSUADE_ENERGY,
                           next_birthday=day + (-day) % BIRTHDAY_INTERVAL, next_court=day + (-day) % CROWN_INTERVAL,
                           daily_count=daily_count, heir_age_years=heir_age_years, RANK_BONUS=RANK_BONUS,
                           emperor_ill=emperor_ill(), COUNSEL_INTERVAL=COUNSEL_INTERVAL)


def _rival(hid):
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    return h if h and h['gender'] == '皇子' and h['status'] != 'deposed' and heir_age_years(h) >= RIVAL_MIN_AGE else None


@app.route('/succession/stance', methods=['POST'])
@login_required
def succession_stance():
    c = g.me
    kind = request.form.get('kind')
    try: hid = int(request.form.get('heir_id', 0))
    except ValueError: hid = 0
    h = _rival(hid)
    cur = q("SELECT * FROM stances WHERE consort_id=? AND kind=?", (c['id'], kind), one=True) if kind in ('open', 'secret') else None
    err = None
    if kind not in ('open', 'secret'): err = '明着站还是暗里站？'
    elif request.form.get('withdraw') == '1':
        if not cur: err = '你本就没站队。'
        elif cur and cur['since_day'] + STANCE_LOCK_DAYS > cur_day(): err = f"站队 {STANCE_LOCK_DAYS} 天内不能改。"
        else:
            run("DELETE FROM stances WHERE consort_id=? AND kind=?", (c['id'], kind))
            flash('已撤下。', 'good'); return redirect(url_for('succession'))
    elif not h: err = f'要 {RIVAL_MIN_AGE} 岁以上、没被废黜的阿哥才能站队。'
    elif h['caretaker_id'] == c['id'] or h['mother_id'] == c['id']: err = '自己的孩子，不必站队。'
    elif c['status'] != 'normal': err = '你现在做不了这个。'
    elif cur and cur['since_day'] + STANCE_LOCK_DAYS > cur_day(): err = f"站队 {STANCE_LOCK_DAYS} 天内不能改。"
    else:
        other = q("SELECT * FROM stances WHERE consort_id=? AND kind!=?", (c['id'], kind), one=True)
        if other and other['heir_id'] == hid: err = '明站和暗站不必是同一位。'
    if err:
        flash(err, 'bad'); return redirect(url_for('succession'))
    run("INSERT OR REPLACE INTO stances (consort_id, kind, heir_id, since_day) VALUES (?,?,?,?)", (c['id'], kind, hid, cur_day()))
    label = heir_full_title(h)
    if kind == 'open':
        gazette(f"{display_name(c)}向{label}示好。", 'news')
        for par in heir_parents(h): notify(par['id'], f"{display_name(c)}公开向{label}示好，他的党羽多了一位。", 'good')
        flash(f"已明着站在{label}一边。", 'good')
    else:
        flash(f"已暗里站在{label}一边，没人知道。", 'good')
    return redirect(url_for('succession'))


@app.route('/succession/act', methods=['POST'])
@login_required
def succession_act():
    """站队后每天替他做的一件事"""
    c = g.me
    key = request.form.get('act')
    cfg = STANCE_ACTS.get(key)
    st = q("SELECT * FROM stances WHERE consort_id=? AND kind=?", (c['id'], cfg['kind']), one=True) if cfg else None
    h = _rival(st['heir_id']) if st else None
    err = None
    if not cfg or not st: err = '你还没站队。'
    elif not h: err = '他已经不在储位人选里了。'
    elif c['status'] != 'normal': err = '你现在做不了这个。'
    elif daily_count(c['id'], f"stance:{cfg['kind']}"): err = '今天已经替他办过一件事了。'
    elif c['energy'] < cfg['energy']: err = '精力不够了。'
    elif c['silver'] < cfg['silver']: err = f"银子不够，要 {cfg['silver']} 两。"
    elif cfg.get('exam') and not (6 <= heir_age_years(h) <= 15): err = '他已经不参加考校了。'
    if err:
        flash(err, 'bad'); return redirect(url_for('succession'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (cfg['energy'], c['id']))
    if cfg['silver']: add_silver(c['id'], -cfg['silver'])
    daily_inc(c['id'], f"stance:{cfg['kind']}")
    extra = ''
    if cfg.get('merit'):
        qf = npc_row('qifei')
        bonus = 1 if cfg['kind'] == 'open' and qf and h['mother_id'] == qf['id'] and bond(c['id'], 'qifei') >= BOND_INTIMATE else 0
        add_merit(h['id'], cfg['merit'] + bonus)
        if bonus: extra = '齐妃知道了，又替你在阿哥跟前多说了几句好话，功绩多 +1'
    if cfg.get('exam'): run('UPDATE heirs SET exam_bonus=MAX(exam_bonus,?) WHERE id=?', (cfg['exam'], h['id']))
    flash(f"{cfg['line']}。" + (extra + '。' if extra else ''), 'good')
    return redirect(url_for('succession'))


@app.route('/succession/claim/<int:hid>', methods=['POST'])
@login_required
def succession_claim(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    err = None
    if not h or h['caretaker_id'] != 0 or h['adult_day'] or heir_age_days(h) >= HEIR_ADULT_AGE_DAYS: err = '这个孩子已经有人照管了。'
    elif c['rank'] < raise_min_rank(h): err = f'{raise_rank_name(h)}位以上才能领养这位{h["gender"]}。'
    elif c['status'] != 'normal': err = '你现在去不了养心殿。'
    elif q("SELECT 1 FROM heir_claims WHERE consort_id=? AND heir_id=?", (c['id'], hid), one=True): err = '你已经求过了，等皇上定夺。'
    elif c['energy'] < 1: err = '精力不够了。'
    if err:
        flash(err, 'bad'); return redirect(url_for('succession'))
    run('UPDATE consorts SET energy=energy-1 WHERE id=?', (c['id'],))
    run("INSERT INTO heir_claims (consort_id, heir_id, day) VALUES (?,?,?)", (c['id'], hid, cur_day()))
    flash(f"你在养心殿求了皇上。今晚结算时，皇上会在求过的人里挑一位（信任高、位分高的更有把握）。", 'good')
    return redirect(url_for('succession'))


@app.route('/succession/move', methods=['POST'])
@login_required
def succession_move():
    c = g.me
    key = request.form.get('move')
    mv = SUCCESSION_MOVES.get(key)
    def toint(name):
        try: return int(request.form.get(name, 0))
        except ValueError: return 0
    err, target, mine, other = None, _rival(toint('target_id')), None, _rival(toint('other_id'))
    day = cur_day()
    if not mv: err = '要做什么？'
    elif c['status'] != 'normal': err = '你现在做不了这个。'
    elif c['energy'] < mv['energy']: err = '精力不够了。'
    elif c['silver'] < mv['silver']: err = f"银子不够，要 {mv['silver']} 两。"
    elif key == 'discord':
        if not target: err = '选一位 12 岁以上的阿哥。'
        elif target['caretaker_id'] == c['id']: err = '那是你自己的孩子。'
    elif key == 'bribe':
        mine = q('SELECT * FROM heirs WHERE id=?', (toint('target_id'),), one=True)
        if not mine or mine['caretaker_id'] != c['id'] or mine['adult_day'] or not 6 <= heir_age_years(mine, day) <= 15:
            err = '只能替自己抚养的、6~15 岁的孩子打点上书房。'
    elif key == 'counsel':
        mine = q('SELECT * FROM heirs WHERE id=?', (toint('princess_id'),), one=True)
        if not mine or mine['caretaker_id'] != c['id'] or mine['gender'] != '公主' or heir_age_years(mine, day) < RIVAL_MIN_AGE:
            err = '要你抚养的、12 岁以上的公主才能进言。'
        elif day < mine['plead_ready_day']: err = f"公主刚进过言，{mine['plead_ready_day'] - day} 天后才能再进。"
        elif not target: err = '替哪位阿哥说话？'
    elif key == 'feud':
        if c['scheme'] < mv['min_scheme']: err = f"心计要 {mv['min_scheme']} 以上才使得出这招。"
        elif not target or not other or target['id'] == other['id']: err = '选两位不同的、12 岁以上的阿哥。'
    elif key == 'frame':
        if c['rank'] < mv['min_rank']: err = '妃位以上才压得住这样的局。'
        elif not target: err = '选一位 12 岁以上的阿哥。'
        elif target['caretaker_id'] == c['id'] or target['mother_id'] == c['id']: err = '那是你自己的孩子，不能这么办。'
    elif key == 'peek':
        if c['rank'] < mv['min_rank']: err = '嫔位以上才够得着养心殿的匾。'
    elif key == 'forge':
        me = q('SELECT forge_used FROM users WHERE id=?', (c['user_id'],), one=True)
        if c['rank'] < mv['min_rank']: err = '贵妃以上才有这个胆子。'
        elif not emperor_ill(): err = '只有皇上病重的这几天，才有人能近得了遗诏。'
        elif me['forge_used']: err = '一个人一辈子只能试这一次，你已经试过了。'
        elif not target or target['caretaker_id'] != c['id']: err = '只能把匾改成你自己抚养的阿哥。'
    if err:
        flash(err, 'bad'); return redirect(url_for('succession'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (mv['energy'], c['id']))
    if mv['silver']: add_silver(c['id'], -mv['silver'])
    if key == 'discord':
        ok = sow_discord(target, display_name(c), attacker=c)
        flash(f"流言散出去了，{heir_full_title(target)}的圣眷 -{DISCORD_LOSS}。" if ok else '流言没能传到皇上耳朵里，银子白花了。', 'good' if ok else 'bad')
    elif key == 'frame':
        label = heir_full_title(target)
        if random.random() < min(0.75, FRAME_PRINCE_BASE + c['scheme'] * FRAME_PRINCE_PER_SCHEME):
            run("UPDATE heirs SET status='deposed', errand='' WHERE id=?", (target['id'],))
            gazette(f"慎刑司查实{label}结交外臣、图谋不轨，圈禁高墙，逐出储位人选。", 'decree')
            care = get_consort(target['caretaker_id']) if target['caretaker_id'] else None
            if care and care['status'] != 'dead' and care['rank'] > 1:
                demote_rank(care['id'])
            for par in heir_parents(target):
                notify(par['id'], f"{label}被查出结交外臣，圈禁出局。" + ('你受牵连，降了一级。' if care and par['id'] == care['id'] else ''), 'bad')
            flash(f"构陷成了，{label}被圈禁出局。", 'good')
        else:
            flash('这一局没能坐实，银子打了水漂。', 'bad')
            if random.random() < FRAME_PRINCE_CAUGHT:
                add_trust(c['id'], -FRAME_PRINCE_CAUGHT_TRUST)
                add_stat(c['id'], 'virtue', -FRAME_PRINCE_CAUGHT_VIRTUE)
                for par in heir_parents(target):
                    if par['id'] != c['id']: notify(par['id'], f"查出是{display_name(c)}想构陷{label}，事情没成。", 'info')
                flash(f"反倒被人查出是你在背后使坏。信任 -{FRAME_PRINCE_CAUGHT_TRUST}，德行 -{FRAME_PRINCE_CAUGHT_VIRTUE}。", 'bad')
    elif key == 'bribe':
        run('UPDATE heirs SET exam_bonus=MAX(exam_bonus,?) WHERE id=?', (BRIBE_BONUS, mine['id']))
        flash(f"上书房那边打点妥当，{heir_label(mine)}下一次考校判定 +{BRIBE_BONUS}。", 'good')
    elif key == 'counsel':
        run('UPDATE heirs SET plead_ready_day=? WHERE id=?', (day + COUNSEL_INTERVAL, mine['id']))
        add_merit(target['id'], COUNSEL_GAIN)
        flash(f"{heir_label(mine)}在皇上面前替{heir_full_title(target)}说了好话，他的圣眷 +{COUNSEL_GAIN}。", 'good')
        for par in heir_parents(target): notify(par['id'], f"{heir_label(mine)}公主在皇上面前替{heir_full_title(target)}说了好话，圣眷 +{COUNSEL_GAIN}。", 'good')
    elif key == 'peek':
        r = random.random()
        leader, chance = succession_favorite(day)
        if r < PEEK_LEARN:
            flash(f"御前总管一时不慎露了口风：皇上眼下最看重的是{heir_full_title(leader)}，胜面约 {round(chance * 100)}%。"
                  f"（这是眼下的行情，后面还会变；圣意难测，最后未必是他。）" if leader
                  else '匾后的名字，是从宗室里过继的一位，眼下还不是任何一位阿哥。', 'good')
        elif r < PEEK_LEARN + PEEK_CAUGHT:
            gazette(f"{display_name(c)}私窥立储密匾，被侍卫拿下，打入冷宫。", 'decree')
            send_to_cold(c['id'])
            flash('你被侍卫当场拿住，打入冷宫。', 'bad')
        else:
            flash('银子花了，什么也没打听到。', 'info')
    elif key == 'forge':
        run('UPDATE users SET forge_used=1 WHERE id=?', (c['user_id'],))
        if random.random() < FORGE_BASE + c['scheme'] * FORGE_PER_SCHEME:
            run('UPDATE heirs SET forged=0')
            run('UPDATE heirs SET forged=1 WHERE id=?', (target['id'],))
            flash(f"御前总管应下了。遗诏上的名字，到时会是{heir_full_title(target)}。这件事只有你知道。", 'good')
        else:
            gazette(f"{display_name(c)}矫诏事发，赐死。", 'decree')
            die(c['id'], '矫诏败露，赐死')
            flash('事发了。你被赐了白绫。', 'bad')
    elif key == 'feud':
        for hh in (target, other): run('UPDATE heirs SET feud_until_day=? WHERE id=?', (day + FEUD_DAYS, hh['id']))
        flash(f"{heir_full_title(target)}和{heir_full_title(other)}从此结了怨，之后 {FEUD_DAYS} 天两人的圣眷每天各 -{FEUD_LOSS}。", 'good')
        for hh in (target, other):
            for par in heir_parents(hh): notify(par['id'], f"{heir_full_title(hh)}和兄弟起了嫌隙，之后 {FEUD_DAYS} 天圣眷每天 -{FEUD_LOSS}。", 'bad')
    return redirect(url_for('succession'))


@app.route('/succession/gift/<int:hid>', methods=['POST'])
@login_required
def succession_gift(hid):
    c = g.me
    h = q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
    gift = request.form.get('gift')
    if not h or h['caretaker_id'] != c['id'] or gift not in GIFTS or heir_age_years(h) < RIVAL_MIN_AGE:
        flash('备不了这份寿礼。', 'bad'); return redirect(url_for('succession'))
    run('UPDATE heirs SET gift=? WHERE id=?', (gift, hid))
    flash(f"寿礼备下了：{GIFTS[gift]['name']}。" + ('万寿节那晚扣 100 两，银子不够就只好写幅字。' if GIFTS[gift]['silver'] else ''), 'good')
    return redirect(url_for('succession'))


@app.route('/prenatal', methods=['POST'])
@login_required
def prenatal():
    c = g.me
    kind = request.form.get('kind')
    cfg = PRENATAL.get(kind)
    err = None
    if not c['pregnant_since']: err = '你没有身孕。'
    elif not cfg: err = '选一样安胎的法子。'
    elif c['status'] not in ('normal', 'confined'): err = '现在做不了这个。'
    elif c['energy'] < PRENATAL_ENERGY: err = '精力不够了。'
    elif c['silver'] < cfg['silver']: err = f"银子不够，{cfg['name']}要 {cfg['silver']} 两。"
    elif kind == 'rest' and daily_count(c['id'], 'prenatal'): err = '今天已经安过胎了。'
    elif kind != 'rest' and prenatal_state(c).get(cfg['stat'], 0) > 0: err = f"这一胎已经{cfg['name']}过了，每个孕期各一次。"
    if err:
        flash(err, 'bad'); return redirect(url_for('place', key='home'))
    run('UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?', (PRENATAL_ENERGY, cfg['silver'], c['id']))
    if kind == 'rest': daily_inc(c['id'], 'prenatal')
    st = prenatal_state(c)
    if kind == 'rest':
        if st.get('rest', 0) < 3:      # 调养到第三次就到头了，再躺也没有更多好处
            add_stat(c['id'], 'health', 5)
        st['rest'] = min(3, st.get('rest', 0) + 1)
    else:
        st[cfg['stat']] = min(PRENATAL_STAT_CAP, st.get(cfg['stat'], 0) + cfg['gain'])
    run("UPDATE consorts SET prenatal=? WHERE id=?", (json.dumps(st), c['id']))
    flash(cfg['line'], 'good')
    return redirect(url_for('place', key='home'))


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
    elif h['adult_day']: err = '他已经长大成人，不用你再教养了。'
    elif not cfg: err = '选一样教养的法子。'
    elif c['energy'] < HEIR_RAISE_ENERGY: err = '精力不够了。'
    elif c['silver'] < cfg.get('silver', 0): err = f"银子不够，需要 {cfg['silver']} 两。"
    elif cfg.get('looks') and h['appearance'] >= 100: err = '孩子的容貌已经到头了，再梳洗也没有更多好处。'
    elif daily_count(c['id'], f'raise:{hid}'): err = '今天已经教养过他了。'
    if err:
        flash(err, 'bad')
        return redirect(url_for('place', key='home'))
    run('UPDATE consorts SET energy=energy-?, silver=silver-? WHERE id=?', (HEIR_RAISE_ENERGY, cfg.get('silver', 0), c['id']))
    daily_inc(c['id'], f'raise:{hid}')
    parts = []
    if cfg.get('looks'):
        amt = cfg['looks_beauty'] if c['appearance'] >= HEIR_GROOM_BEAUTY_LINE else cfg['looks']
        parts.append(f"容貌 +{raise_looks(h, amt)}")
    for stat, amt in cfg.get('gain', {}).items():
        if h['personality'] == 'clever' and stat == 'study': amt = round(amt * 1.5)
        elif h['personality'] == 'honest' and stat == 'study': amt = round(amt * 0.7)
        elif h['personality'] == 'naughty' and stat == 'study': amt = round(amt * 0.5)
        elif h['personality'] == 'stubborn' and stat == 'riding': amt = round(amt * 1.3)
        if stat in GIFT_STATS and amt > 0: amt = max(1, round(amt * h['gift_' + stat] / 100))   # 资质
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
    mine = list(q("SELECT * FROM heirs WHERE caretaker_id=? AND adult_day=0", (c['id'],)))
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
    for stat in ('study', 'riding', 'virtue'):
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

def intrigue_success_p(atk, tgt, cfg, conspired=False):
    p = cfg['base'] + (atk['scheme'] - tgt['scheme']) * 0.008
    if atk['personality'] == 'deep': p += 0.05
    if eyes_active(tgt): p -= 0.12
    p -= min(0.15, 0.05 * active_sister_count(tgt['id']))
    if tgt['personality'] == 'dignified': p -= 0.05
    if tgt['virtue'] >= 70: p -= 0.05
    if tgt['rank'] == PLAYER_MAX_RANK: p -= 0.15
    p -= tgt['trust'] * 0.0015                      # 皇上信任的人难扳倒：信任 100 时 -15%
    if cfg is INTRIGUES['expose']:
        p += (atk['trust'] - 40) * 0.005            # 告发看告发人自己的信任：信任 0 时 -20%，100 时 +30%
    if cfg is INTRIGUES['frame'] and same_palace(atk, tgt):
        p += 0.10
    if cfg is INTRIGUES['rumor'] and has_maid_trait(atk['id'], 'suizui'):
        p += 0.10                                   # 碎嘴的宫人替主子把话传出去
    if tgt['user_id']:
        p -= maid_defense(tgt['id']) + watch_guard(tgt['id'])   # 宫人护主、泄密、守夜
    if tgt['user_id']:                              # 交好 NPC 的护持（九点二十一节）
        if bond(tgt['id'], 'huanghou') >= BOND_CLOSE: p -= BOND_HUANGHOU_GUARD
        if bond(tgt['id'], 'huafei') >= BOND_INTIMATE: p -= BOND_HUAFEI_GUARD
    if atk['user_id'] and bond(atk['id'], 'caoguiren') >= BOND_INTIMATE: p += BOND_CAO_BOOST
    if conspired: p += CONSPIRE_BONUS
    return max(0.08, min(0.85, p))

def intrigue_caught_p(atk, tgt):
    p = 0.35 + (tgt['scheme'] - atk['scheme']) * 0.005 + (0.25 if eyes_active(tgt) else 0)
    if state()['emperor_mood'] == '震怒': p += 0.1
    if atk['user_id'] and bond(atk['id'], 'caoguiren') >= BOND_INTIMATE and random.random() < BOND_CAO_LEAK:
        p += BOND_CAO_LEAK_CAUGHT                   # 曹贵人两头下注，把风声漏了出去
    return max(0.15, min(0.8, p))

STEAL_HATRED = -15               # 截宠得手后，截的人和被截的人好感 -15（邸报公开，没有别的处罚）
STEAL_VICTIM_FAVOR_LOSS = 5     # 被截宠得手的人，圣宠 -5
STEAL_VOID_REFUND = 0.5      # 截宠落空退还银子的比例

def resolve_intrigue(it, bed_id=None):
    """结算一条阴谋。steal 需要传入今晚被翻牌的人。返回 (result, 被截宠后的新侍寝人或 None)"""
    if 'status' in it.keys() and it['status']!='pending': return it['result'],None
    if it['method'] == 'drug': return resolve_drug(it)
    cfg = INTRIGUES[it['method']]
    atk, tgt = get_consort(it['attacker_id']), get_consort(it['target_id'])
    an, tn = display_name(atk), display_name(tgt)
    new_bed = None
    partner = get_consort(it['partner_id']) if 'partner_id' in it.keys() and it['partner_id'] else None
    conspired = bool(partner and partner['status'] == 'normal' and not is_sick(partner)
                     and conspire_affinity(atk['id'], partner['id']) > CONSPIRE_AFFINITY_MIN)
    if partner and not conspired:   # 伙伴临阵出了岔子或交情淡了：合谋作废，按单人判定，钱不退
        for x in (atk, partner):
            notify(x['id'], f"{display_name(atk)}与{display_name(partner)}对{tn}的合谋临阵出了岔子（有人顾不上，或交情不够了），只能按单人算，成算没有加成。", 'info')
    if conspired: an = f"{an}、{display_name(partner)}"

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
        back = int(it['silver_paid'] * STEAL_VOID_REFUND)           # 落空（对方没被翻牌，或被别人抢先截走）退还一部分银子
        back_p = int(it['partner_silver'] * STEAL_VOID_REFUND) if it['partner_id'] else 0
        if back: add_silver(atk['id'], back)
        if back_p: add_silver(it['partner_id'], back_p)
        if atk['user_id']: notify(atk['id'], f"今晚翻的不是{tn}的牌子，你的截宠落了空。退还 {back} 两银子。")
        if back_p: notify(it['partner_id'], f"今晚翻的不是{tn}的牌子，你与{display_name(atk)}的截宠落了空。退还 {back_p} 两银子。")
        return done('void')

    if it['method'] == 'lethal' and (atk['status'] != 'normal' or is_sick(atk) or
            tgt['poisoned_day'] or tgt['protected_until_day'] >= cur_day()):
        if atk['user_id']: notify(atk['id'], f"你对{tn}的毒害落空了：局面已经变了，银子白花了。")
        return done('void')
    if it['method'] == 'punish' and (atk['status'] != 'normal' or not punishable_maids(tgt['id'])):
        if atk['user_id']: notify(atk['id'], f"你想发落{tn}的宫人，可眼下找不到由头，只好作罢。")
        return done('void')
    tell_name = eyes_active(tgt) or it['method'] in ('steal', 'impeach')      # 截宠得手、参奏都是明面上的事，对方一定知道是谁
    if it['method'] == 'expose':
        success, caught = random.random() < intrigue_success_p(atk, tgt, cfg, conspired), True
    else:
        success = random.random() < intrigue_success_p(atk, tgt, cfg, conspired)
        caught = (not success) and random.random() < intrigue_caught_p(atk, tgt)

    if success:
        who = an if tell_name else '有人'
        m = it['method']
        if tell_name and tgt['user_id']: run("UPDATE consorts SET culprit_id=? WHERE id=?", (atk['id'], tgt['id']))
        if m == 'lethal':
            run('UPDATE consorts SET poisoned_day=?, poison_treatment=0, health=MAX(1,health-20) WHERE id=?',
                (cur_day(), tgt['id']))
            victim = f"你中毒了，体质 -20。下一次结算前一定要请太医（{treat_cost(tgt)} 两，姐妹也能替你请）：请了九成能活，不请只有三成五。" + \
                     (f"眼线查到是{an}下的手。" if tell_name else '')
            gz = f'{tn}突然中毒，性命垂危。'
            night_mark(tgt['id'], 'poisoned')
        elif m == 'rumor':
            trusted = tgt['trust'] >= TRUSTED_LINE
            loss = cut_favor(tgt['id'], FAVOR_LOSS['rumor_trusted'] if trusted else FAVOR_LOSS['rumor'])
            add_stat(tgt['id'], 'virtue', -3)
            night_mark(tgt['id'], 'victim', trusted=trusted)
            victim = f"宫里起了关于你的流言，是{who}在背后散播。圣宠 -{loss}，德行 -3。" + \
                     ('皇上信你，没全当真。' if trusted else '')
            gz = f"流言四起：{pick_rumor(tn)}"
        elif m == 'frame':
            trusted = tgt['trust'] >= TRUSTED_LINE
            loss = cut_favor(tgt['id'], FAVOR_LOSS['frame_trusted'] if trusted else FAVOR_LOSS['frame'])
            confine(tgt['id'], CONFINE_DAYS)
            night_mark(tgt['id'], 'victim', trusted=trusted)
            victim = f"你宫里搜出了不该有的东西，{who}栽赃陷害了你。禁足半天，圣宠 -{loss}。" + \
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
            lost = cut_favor(tgt['id'], STEAL_VICTIM_FAVOR_LOSS)
            victim = f"原本今晚翻的是你的牌子，却被{who}半路截了去。圣宠 -{lost}。"
            gz = f"{an}半路截了{tn}的牌子，顶上侍寝。"      # 邸报一定登，谁都看得见
            for x in ((atk, partner) if conspired else (atk,)):
                add_affinity(x['id'], tgt['id'], STEAL_HATRED)      # 拉仇恨：和被截的人好感下降
        elif m == 'expose':
            sec = SECRETS[tgt['secret']]
            apply_secret_penalty(tgt['id'], confessed=False)
            add_trust(tgt['id'], -15)
            add_trust(atk['id'], 5)
            victim = f"{an}在皇上面前告发你{sec['name']}。皇上震怒：{sec['penalty']}。"
            gz = f"{an}告发{tn}{sec['name']}，皇上震怒，{sec['penalty']}。"
        elif m == 'punish':
            maid = random.choice(punishable_maids(tgt['id']))
            run('UPDATE consorts SET maid_punished_day=? WHERE id=?', (cur_day(), tgt['id']))
            if maid['trait'] == 'zhonghou' and random.random() < MAID_SAVE_CHANCE:      # 忠厚本分，宫里人替她求了情
                victim = f"{an}说你宫里的{maid['name']}冲撞了她，要拖去慎刑司杖毙。{maid['name']}平日忠厚本分，宫里人替她求了情，只挨了顿板子，保下了一条命。"
                gz = f"{tgt['palace']}宫人{maid['name']}险些被发落，被人保下了。"
            else:
                maid_leave(maid['id'], 'dead', f"被{an}以冲撞为由拖去慎刑司，杖毙")
                for other in active_maids(tgt['id']):
                    add_loyalty(other['id'], -5)
                # 发落是明面上的欺压：主子一定知道是谁，不看眼线
                victim = f"{an}说你宫里的{maid['name']}冲撞了她，把人拖去慎刑司，杖毙了。宫里的人都吓坏了，全宫宫人忠心 -5。"
                gz = f"{tgt['palace']}宫人{maid['name']}没了。"
        elif m == 'impeach':
            old_name = display_name(tgt)
            run('UPDATE consorts SET impeached_day=? WHERE id=?', (cur_day(), tgt['id']))
            lost = cut_favor(tgt['id'], IMPEACH_FAVOR_LOSS)
            if tgt['rank'] > 1: demote_rank(tgt['id'])
            now_name = display_name(get_consort(tgt['id']))
            victim = f"{an}上了一道折子参你，皇上准了：你降为{now_name}，圣宠 -{lost}。" + (f"眼线说，是{an}。" if tell_name else '')
            gz = f"{old_name}被参奏失德，皇上降其位分，今称{now_name}。"
        elif m == 'witch':
            send_to_cold(tgt['id'])
            victim = f"你宫中搜出了写着皇上生辰八字的巫蛊人偶。百口莫辩，你被打入冷宫。" + \
                     (f"眼线说，是{an}的人动的手。" if tell_name else '')
            gz = f"{tn}宫中搜出巫蛊之物，皇上大怒，废为庶人，打入冷宫。"
        if tgt['user_id']: notify(tgt['id'], victim, 'bad')
        if atk['user_id']: notify(atk['id'], f"你{'与' + display_name(partner) + '合谋' if conspired else ''}对{tn}的「{cfg['name']}」成了。", 'good')
        if conspired: notify(partner['id'], f"你与{display_name(atk)}合谋对{tn}的「{cfg['name']}」成了。", 'good')
        if gz: gazette(gz, 'scandal')
        if conspired:
            gain_intrigue_influence(it, share=CONSPIRE_INFLUENCE_SHARE)
            gain_intrigue_influence(it, share=CONSPIRE_INFLUENCE_SHARE, actor_id=partner['id'])
        else:
            gain_intrigue_influence(it)
        return done('success')

    if caught:
        mood_extra = state()['emperor_mood'] == '震怒'
        m = it['method']

        def punish_for(a):
            """败露的惩罚落到 a 头上，返回写给她的说明"""
            if m == 'steal': return '皇上没有追究'      # 截宠败露不罚：不扣圣宠、不禁足、不扣信任、皇后好感也不动（2026-10-07 起）
            if m == 'lethal':
                send_to_cold(a['id'])
                pen = '毒害败露，废位并打入冷宫'
            elif m == 'rumor':
                add_stat(a['id'], 'virtue', -5); cut_favor(a['id'], FAVOR_LOSS['caught_rumor'])
                pen = f"德行 -5，圣宠 -{FAVOR_LOSS['caught_rumor']}"
            elif m == 'frame':
                confine(a['id']); cut_favor(a['id'], FAVOR_LOSS['caught_frame'])
                pen = f"禁足半天，圣宠 -{FAVOR_LOSS['caught_frame']}"
            elif m == 'poison':
                if a['rank'] > 1: demote_rank(a['id'])
                confine(a['id'], 3)
                pen = '降一级位分，禁足半天'
            elif m == 'steal':
                cut_favor(a['id'], FAVOR_LOSS['caught_steal']); confine(a['id'], 1)
                pen = f"圣宠 -{FAVOR_LOSS['caught_steal']}，禁足半天"
            elif m == 'expose':
                add_stat(a['id'], 'virtue', -8); cut_favor(a['id'], FAVOR_LOSS['caught_expose'])
                pen = f"德行 -8，圣宠 -{FAVOR_LOSS['caught_expose']}"
            elif m == 'punish':
                add_stat(a['id'], 'virtue', -8)
                pen = '德行 -8'
            elif m == 'impeach':
                add_stat(a['id'], 'virtue', -8); lost = cut_favor(a['id'], FAVOR_LOSS['caught_expose'])
                pen = f"德行 -8，圣宠 -{lost}"
            else:  # witch
                send_to_cold(a['id'])
                pen = '打入冷宫'
            if mood_extra and m != 'witch':
                cut_favor(a['id'], FAVOR_LOSS['mood_extra']); pen += f"（皇上正在气头上，圣宠再 -{FAVOR_LOSS['mood_extra']}）"
            if a['user_id']:
                tloss = CAUGHT_TRUST_LOSS_LIGHT if m in ('expose', 'punish') else CAUGHT_TRUST_LOSS
                add_trust(a['id'], -tloss)
                bond_caught_huanghou(a['id'])
                pen += f'，信任 -{tloss}'
                night_mark(a['id'], 'caught')
            return pen

        pen = punish_for(atk)
        if atk['user_id']: notify(atk['id'], f"你{'与' + display_name(partner) + '合谋' if conspired else ''}对{tn}的「{cfg['name']}」败露了。{pen}。", 'bad')
        if conspired:
            pen_p = punish_for(partner)
            notify(partner['id'], f"你与{display_name(atk)}合谋对{tn}的「{cfg['name']}」败露了。{pen_p}。", 'bad')
        if tgt['user_id']: notify(tgt['id'], f"{an}想对你「{cfg['name']}」，被当场拿住。", 'good')
        if m == 'expose':
            gazette(f"{an}在御前告发{tn}，查无实据，皇上斥其搬弄是非。", 'scandal')
        else:
            gazette(f"{an}意图{cfg['name']}{tn}，事情败露。{pen}。", 'scandal')
        return done('caught')

    if atk['user_id']: notify(atk['id'], f"你{'与' + display_name(partner) + '合谋' if conspired else ''}对{tn}的「{cfg['name']}」没成，好在没人察觉。")
    if conspired: notify(partner['id'], f"你与{display_name(atk)}合谋对{tn}的「{cfg['name']}」没成，好在没人察觉。")
    if it['method'] == 'punish' and tgt['user_id']:
        notify(tgt['id'], f"{an}想找由头发落你宫里的人，被你挡了回去。")
    if it['method'] == 'impeach':      # 参奏是递到御前的折子，成与不成都是公开的
        gazette(f"{an}上折参奏{tn}，皇上留中不发。", 'scandal')
        if tgt['user_id']: notify(tgt['id'], f"{an}上折子参你，皇上看过没有下旨，把折子压下了。", 'info')
    if conspired:
        gain_intrigue_influence(it, FIZZLE_INFLUENCE_FRACTION, share=CONSPIRE_INFLUENCE_SHARE)
        gain_intrigue_influence(it, FIZZLE_INFLUENCE_FRACTION, share=CONSPIRE_INFLUENCE_SHARE, actor_id=partner['id'])
    else:
        gain_intrigue_influence(it, FIZZLE_INFLUENCE_FRACTION)
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
            pool = [p for p in players if (p['favor'] >= 60 or p['id'] in grudge) and bond(p['id'], 'huafei') < BOND_CLOSE]
            if not pool: continue
            target = max(pool, key=lambda p: p['favor'] + (100 if p['id'] in grudge else 0))
            method = 'frame' if target['rank'] >= 3 else 'rumor'
        else:
            pool = [p for p in players if p['favor'] >= 30]
            if not pool: continue
            target, method = random.choices(pool, weights=[2 if p['patron'] == 'dowager' else 1 for p in pool])[0], 'rumor'   # 太后的人更招眼
        if q("SELECT COUNT(*) n FROM intrigues WHERE target_id=? AND day=? AND status='pending'",
             (target['id'], day), one=True)['n'] >= INTRIGUE_TARGET_DAILY_MAX:
            continue
        drug = 'hanshui' if method == 'drug' else ''   # 皇后给有孕的人下寒水散
        run("""INSERT INTO intrigues (day, attacker_id, target_id, method, item_used, drug, created_ts)
               VALUES (?,?,?,?,?,?,?)""", (day, npc['id'], target['id'], method, drug, drug, now_ts()))
    huafei_punish(day)

# ── 皇上的寿数、驾崩、开匾、下一届（九点六节 G） ─────────────────────────────────

NEXT_EMPEROR_START_AGE = 20   # 无候选时，从宗室过继的成年新帝
HAZARD_AFTER_YEARS = 24  # 兼容旧引用；皇帝改为固定届期，不随机提前驾崩
HAZARD_PER_YEAR = 0.0
MAX_REIGN_DAYS = 15  # 开局当天为第 1 天，第 15 天驾崩

ILL_DAYS = 3                  # 驾崩前一定有 3 天病重
ATTEND_TRUST_GAIN, ATTEND_HEIR_GAIN = 5, 5
PEEK_LEARN, PEEK_CAUGHT = 0.20, 0.15
FORGE_BASE, FORGE_PER_SCHEME = 0.15, 0.003
SUPPORT_TITLES = [(12, '皇贵太妃'), (6, '贵太妃'), (0, '太妃')]   # 明站的人按支持了几天封
REIGN_EVENT_KINDS = ('decree', 'death', 'birth')
REIGN_EVENT_LIMIT = 14


def promote_virtue_need(rank):
    need = PROMOTE_VIRTUE[rank]
    return int(need * 0.9) if emperor_traits().get('virtue', 0) >= 60 else need


def emperor_age_years(st=None, day=None):
    st = st or state()
    day = st['day'] if day is None else day
    return st['emperor_start_age'] + (day - st['reign_start_day'] + (1 if settling() else 0)) * AGE_YEARS_PER_DAY


def emperor_ill(st=None, day=None):
    """驾崩日 d 定下之后，d-2、d-1、d 这三天皇上病重"""
    st = st or state()
    day = st['day'] if day is None else day
    return bool(st['emperor_death_day']) and day >= st['emperor_death_day'] - ILL_DAYS + 1


def emperor_traits(st=None):
    try: return json.loads((st or state())['emperor_traits'] or '{}')
    except ValueError: return {}


def fall_emperor_ill(day, death_day):
    death_day = max(day + 1, death_day)
    run('UPDATE game_state SET emperor_death_day=? WHERE id=1', (death_day,))
    gazette('皇上龙体违和，太医院日夜守候，六宫不得喧哗。', 'decree')
    for c in q("SELECT id FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead')"):
        notify(c['id'], '皇上病重。这几天翻牌子、召见都停了。去养心殿侍疾，或许能换来皇上一点心意；'
                        '这也是夺嫡最后的几天。', 'decree')


def emperor_tick(day):
    """结算末尾：驾崩日到了就开匾换届；还没病的，在固定届期前三天宣布病重。返回 True 表示这一晚换届了"""
    st = state()
    if st['emperor_death_day']:
        if day >= st['emperor_death_day']:
            end_reign(day)
            return True
        return False
    reign_days = day - st['reign_start_day']
    if reign_days >= MAX_REIGN_DAYS - 1 - ILL_DAYS:
        fall_emperor_ill(day, st['reign_start_day'] + MAX_REIGN_DAYS - 1)
    return False


def pick_weighted(items, weights):
    return random.choices(items, weights=weights)[0]


SUCCESSION_EXPONENT, CROWN_WEIGHT = 2, 1.3    # 匾后按圣眷的平方加权抽签；太子有名分，权重再 ×1.3


def succession_odds(day):
    """每位候选人这一刻的胜面 [(皇子, 概率)]：矫诏成功的那位是 100%；否则按 圣眷² 加权（太子 ×1.3）。
    圣眷 100 对 50，胜面 80% 对 20%——圣意难测，弱的也有机会，这样玩家的孩子才有戏"""
    cands = rival_princes(day)
    if not cands: return []
    forged = [h for h in cands if h['forged']]
    if forged:
        top = max(forged, key=lambda h: (heir_standing(h), -h['born_day']))
        return [(h, 1.0 if h['id'] == top['id'] else 0.0) for h in cands]
    w = [max(1, heir_standing(h)) ** SUCCESSION_EXPONENT * (CROWN_WEIGHT if h['status'] == 'crown' else 1) for h in cands]
    total = sum(w)
    return [(h, x / total) for h, x in zip(cands, w)]


def succession_favorite(day):
    """眼下胜面最大的那位（窥匾看到的）和他的胜面"""
    odds = succession_odds(day)
    if not odds: return None, 0.0
    return max(odds, key=lambda t: (t[1], -t[0]['born_day']))


def choose_successor(day):
    """匾后是谁：矫诏成功的那位；否则按胜面抽签（`succession_odds`）。没有 12 岁以上的皇子就是 None，从宗室过继"""
    odds = succession_odds(day)
    if not odds: return None
    return pick_weighted([h for h, _ in odds], [p for _, p in odds])


def support_title(days):
    return next(t for lo, t in SUPPORT_TITLES if days >= lo)


def reign_players(st):
    return list(q("""SELECT * FROM consorts WHERE (user_id IS NOT NULL OR archived_user_id IS NOT NULL)
                     AND status!='xiunv' AND entered_day>=?""", (st['reign_start_day'],)))


def new_emperor_name(winner):
    if winner and winner['name']: return winner['name']
    taken = {r['emperor_name'] for r in q('SELECT emperor_name FROM reigns')} | {state()['emperor_name']}
    pool = [n for n in NPC_PRINCE_NAMES if n not in taken] or NPC_PRINCE_NAMES
    return random.choice(pool)


@atomic
def end_reign(day):
    """驾崩那一晚：开匾、定太后、清算、定格这一届、清空、装下一届。国丧一天，第二天的结算开选秀"""
    st = state()
    winner = choose_successor(day)
    players = reign_players(st)
    age_txt = age_text(int(emperor_age_years(st, day) * 12))
    name = new_emperor_name(winner)

    # 太后与太妃：生母、养母里在世的，跟他情分高的成太后，另一位成太妃
    mom = get_consort(winner['mother_id']) if winner and winner['mother_id'] else None
    care = get_consort(winner['caretaker_id']) if winner and winner['caretaker_id'] else None
    parents = list({x['id']: x for x in (mom, care) if x and x['status'] in ('normal', 'confined')}.values())
    dowager = concubine = None
    if len(parents) == 1:
        dowager = parents[0]
    elif len(parents) == 2:
        aff = {mom['id']: winner['mother_affinity'], care['id']: winner['caretaker_affinity']}
        dowager = max(parents, key=lambda x: aff[x['id']])
        concubine = next(x for x in parents if x['id'] != dowager['id'])

    # 站队的结算、落选皇子的清算
    titles = {}
    stances = list(q("SELECT * FROM stances"))
    if winner:
        for sn in stances:
            if sn['heir_id'] == winner['id'] and sn['kind'] == 'open':
                titles[sn['consort_id']] = support_title(day - sn['since_day'])
            elif sn['heir_id'] == winner['id'] and sn['kind'] == 'secret':
                titles.setdefault(sn['consort_id'], '暗中相助有功，新帝另有赏赐')
        for sn in stances:
            if sn['kind'] == 'open' and sn['heir_id'] != winner['id']:
                titles[sn['consort_id']] = '押错了阿哥，新帝记了一笔'
    imprisoned = [h for h in rival_princes(day, exclude_id=winner['id'] if winner else 0)
                  if h['adult_day'] and h['ambition'] >= 80 and heir_faction_count(h) >= 5]
    for h in imprisoned:
        for par in heir_parents(h): titles.setdefault(par['id'], '所抚养的阿哥被圈禁，失势')
    if dowager: titles[dowager['id']] = '圣母皇太后'
    if concubine: titles[concubine['id']] = '太妃'
    settle_family_backing(winner, day)

    fates = []
    for c in players:
        alive = c['status'] != 'dead'
        fate = titles.get(c['id'], '迁居寿康宫，安享晚年') if alive else f"{c['death_reason']}（第 {c['death_day']} 天）"
        fates.append(dict(user=c['user_id'] or c['archived_user_id'], name=full_name(c), rank=RANK_NAMES[c['rank']],
                          fate=fate, alive=alive, bedded=c['bedded_count'], entered=c['entered_day'], cid=c['id']))

    edict = [f"先帝{age_txt}龙驭上宾。遗诏：传位于{name}" + (f"（{heir_label(winner)}）。" if winner else "，自宗室过继。")]
    if dowager:
        edict.append(f"尊{name}之{'生母' if dowager['id'] == winner['mother_id'] else '养母'}{full_name(dowager)}为圣母皇太后，居慈宁宫。")
    elif winner:
        edict.append('生母、养母皆已不在，追尊而已，此届不设太后。')
    if concubine:
        edict.append(f"{full_name(concubine)}封太妃。")
    for sn in stances:
        c = get_consort(sn['consort_id'])
        if winner and sn['heir_id'] == winner['id'] and sn['kind'] == 'open' and c and c['status'] != 'dead' and c['id'] not in (dowager and dowager['id'], concubine and concubine['id']):
            edict.append(f"{full_name(c)}早年示好新帝，封{titles[c['id']]}。")
    for h in rival_princes(day, exclude_id=winner['id'] if winner else 0):
        if not h['adult_day']: continue
        if h in imprisoned or h['id'] in {x['id'] for x in imprisoned}:
            edict.append(f"{heir_full_title(h)}野心勃勃、结党甚众，新帝不放心，圈禁。")
        elif h['title']:
            edict.append(f"{heir_full_title(h)}安分守己，仍以{h['title']}奉养。")
    events = [r for r in q("SELECT day, text FROM gazette WHERE kind IN (?,?,?) ORDER BY id", REIGN_EVENT_KINDS)][-REIGN_EVENT_LIMIT:]
    if events:
        edict.append('——这一届的大事——')
        edict += [f"第 {r['day']} 天　{r['text']}" for r in events]

    records = []
    if players:
        bed = max(players, key=lambda c: c['bedded_count'])
        if bed['bedded_count']: records.append(f"侍寝最多：{full_name(bed)}，{bed['bedded_count']} 次")
        top = max(players, key=lambda c: (c['rank'], -c['rank_since_day']))
        records.append(f"位分最高：{full_name(top)}，{RANK_NAMES[top['rank']]}")
        kids = {c['id']: q("SELECT COUNT(*) n FROM heirs WHERE caretaker_id=?", (c['id'],), one=True)['n'] for c in players}
        most = max(players, key=lambda c: kids[c['id']])
        if kids[most['id']]: records.append(f"养大皇嗣最多：{full_name(most)}，{kids[most['id']]} 位")

    # 家族的荣耀与皇嗣名录，要在清空之前记下
    if dowager and not dowager['npc_key']:
        add_prestige(dowager, PRESTIGE_DOWAGER, f"{full_name(dowager)}成了圣母皇太后")
        family_log_add(consort_uid(dowager), f"{full_name(dowager)}成为圣母皇太后，{name}尊为太后", 1)
    if concubine and not concubine['npc_key']:
        family_log_add(consort_uid(concubine), f"{full_name(concubine)}封太妃", 1)
    for sn in stances:
        c = get_consort(sn['consort_id'])
        if winner and sn['heir_id'] == winner['id'] and sn['kind'] == 'open' and c and c['status'] != 'dead' and titles.get(c['id'], '') .endswith('太妃') \
                and c['id'] not in ((dowager and dowager['id']), (concubine and concubine['id'])):
            family_log_add(consort_uid(c), f"{full_name(c)}早年示好新帝，封{titles[c['id']]}", 1)
    for h in q("SELECT * FROM heirs"):
        if h['title'] and (h['title'] == '亲王' or '公主' in h['title']):
            for uid_ in {consort_uid(p_) for p_ in heir_parents(h)}:
                family_log_add(uid_, f"{heir_full_title(h)}（{h['gender']}）{'封' + h['title'] if h['gender'] == '皇子' else '册封' + h['title']}", 1)
    for c in players:
        kids = [heir_full_title(h) + ('（' + h['gender'] + '）') for h in q("SELECT * FROM heirs WHERE mother_id=? ORDER BY id", (c['id'],))]
        run("UPDATE consorts SET kids=? WHERE id=?", (json.dumps(kids, ensure_ascii=False), c['id']))

    run("""INSERT INTO reigns (reign_no, era_name, emperor_name, start_age, end_age_text, start_day, end_day, successor, dowager,
                              edict, fates, records, created_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (st['reign_no'], st['era_name'], st['emperor_name'], st['emperor_start_age'], age_txt, st['reign_start_day'], day,
         name, full_name(dowager) if dowager else '', json.dumps(edict, ensure_ascii=False),
         json.dumps(fates, ensure_ascii=False), json.dumps(records, ensure_ascii=False), now_ts()))
    reign_id = q('SELECT MAX(id) m FROM reigns', one=True)['m']

    # 玩家自己的信原样存起来，只有本人翻得到
    for c in players:
        uid = c['user_id'] or c['archived_user_id']
        for l in q("SELECT * FROM letters WHERE (to_id=? AND deleted_by_to=0) OR (from_id=? AND deleted_by_from=0) ORDER BY id", (c['id'], c['id'])):
            frm = (l['sender_label'] or '内务府') if l['from_id'] == 0 else display_name(get_consort(l['from_id']))
            to = display_name(get_consort(l['to_id']))
            run("INSERT INTO reign_letters (reign_no, user_id, day, from_name, to_name, body) VALUES (?,?,?,?,?,?)",
                (st['reign_no'], uid, l['day'], frm, to, l['body']))
    for f in fates:
        if f['alive']:
            run("""UPDATE consorts SET status='dead', death_day=?, death_reason=?, archived_user_id=user_id, user_id=NULL,
                   pregnant_since=0, energy=0, hall='', housing_waiting='', survived=1 WHERE id=?""",
                (day, f"先帝驾崩，{f['fate']}", f['cid']))
    run("UPDATE maids SET status='gone', left_day=?, left_reason='主子随先帝殡天，散去' WHERE status='active'", (day,))
    run("DELETE FROM consorts WHERE npc_key IS NOT NULL")
    for t in ('intrigues', 'messages', 'gazette', 'relations', 'known_secrets', 'inventory', 'heirs', 'letters', 'letter_stars',
              'bribes', 'afflictions', 'cases', 'case_suspects', 'case_actions', 'stances', 'heir_claims', 'custody_battles',
              'hobby_projects', 'hobby_items', 'displays', 'daily_counters', 'memories', 'gatherings', 'knife_debts',
              'garden_plots', 'garden_stock', 'banquet_entries', 'banquet_invites', 'banquet_gear', 'achievements'):
        run(f"DELETE FROM {t}")
    run('UPDATE users SET lethal_ready_day=0, nameless_ready_day=0, forge_used=0')

    # 新帝沿用获胜皇嗣的实际年龄。
    successor_age = heir_age_years(winner, day) if winner else NEXT_EMPEROR_START_AGE
    traits = dict(personality=winner['personality'], study=winner['study'], riding=winner['riding'], virtue=winner['virtue']) if winner else \
        dict(personality=random.choice(list(HEIR_PERSONALITIES)), study=random.randint(40, 70), riding=random.randint(40, 70), virtue=random.randint(40, 70))
    era = random.choice([e for e in ERA_NAMES if e != st['era_name']])
    dowager_text = f"圣母皇太后{full_name(dowager)}" if dowager else ''
    run("""UPDATE game_state SET day=?, last_settle_date=?, reign_no=?, reign_start_day=?, emperor_start_age=?, emperor_death_day=0,
           mourning=1, era_name=?, emperor_name=?, emperor_traits=?, dowager=?, dowager_uid=?, emperor_mood='平和', last_bed_id=0, last_bed_day=0,
           last_bed_pool='[]', last_bed_ids='[]' WHERE id=1""",
        (day + 1, datetime.now(TZ).date().isoformat(), st['reign_no'] + 1, day + 2, successor_age, era, name,
         json.dumps(traits, ensure_ascii=False), dowager_text, consort_uid(dowager) if dowager and not dowager['npc_key'] else 0))
    seed_npcs(_RunDB); seed_npc_heirs(_RunDB)
    housing_sync(fill_main=False)
    gazette(f"先帝驾崩。{edict[0]}国丧一日，新帝改元{era}。", 'decree')
    return reign_id


def finish_mourning(day, st):
    """国丧过后的第一次结算：下一届选秀开始"""
    run("UPDATE game_state SET mourning=0, day=?, last_settle_date=?, emperor_mood='平和' WHERE id=1",
        (day + 1, datetime.now(TZ).date().isoformat()))
    gazette(f"国丧期满，新帝{st['emperor_name']}改元{st['era_name']}，新一届选秀开始。", 'decree', day=day + 1)
    return ['国丧期满，开下一届选秀']


def emperor_state_text(st):
    if st['mourning']: return '国丧'
    if emperor_ill(st): return '龙体违和'
    return f"今日{st['emperor_mood']}"


app.jinja_env.globals['emperor_state_text'] = emperor_state_text


@app.route('/reigns')
@login_required
def reigns():
    rows = []
    for r in q("SELECT * FROM reigns ORDER BY id DESC"):
        rows.append(dict(r=r, edict=json.loads(r['edict']), fates=json.loads(r['fates']), records=json.loads(r['records'])))
    letters = q("SELECT * FROM reign_letters WHERE user_id=? ORDER BY reign_no DESC, id", (S['uid'],))
    return render_template('reigns.html', c=g.me, rows=rows, letters=letters, uid=S['uid'], st=state())


# ── 生育：侍寝人数、怀孕率、孕期 ─────────────────────────────────────────────────
BED_TRUST_GAIN = 3      # 每次被翻牌侍寝（没被惊梦香搅黄）涨的信任
BIRTH_FAVOR_PRINCE, BIRTH_FAVOR_PRINCESS = 40, 30      # 生下皇子 / 公主给的圣宠（2026-10-07 起：皇子 100→40，公主 60→30）
BED_DAILY_MAX = 4      # 每人每游戏日最多被翻几次（原来 2，2026-10-06 放宽到 3，2026-10-07 放宽到 4）
BED_COUNT_WEIGHTS = ((1, 0.1), (2, 0.6), (3, 0.3))      # 2026-10-07 起（后调为 10/60/30）：每轮 10% 翻 1 位、60% 翻 2 位、30% 翻 3 位（早先试过固定 2 位、3 位；最早按玩家数 1~6 位）
BED_MAX_PER_ROUND = max(n for n, _ in BED_COUNT_WEIGHTS)
_BED_RNG = random.SystemRandom()      # 翻几位、选哪句话单独掷骰，不占用全局随机序列
PREGNANCY_BASE, PREGNANCY_PER_HEALTH, PREGNANCY_PER_BLESSING = 0.08, 0.0008, 0.0005   # 2026-10-07：底数 6% 升到 12% 后怀孕的人太多，当晚又降到 8%；体质每点 +0.08%（原 0.05%）；福报每 1 点 +0.05%
OLD_MOTHER_AGE, OLD_MOTHER_FACTOR, PREGNANCY_MAX = 35, 0.6, 0.18      # 上限 15% 提到 20%，不然体质高的人都顶在上限上，体质就没差别了
PRENATAL_ENERGY, PRENATAL_STAT_CAP = 1, 6
PRENATAL = {
    'rest':   dict(name='安胎静养', silver=100, line='你卧床静养，一步不出，体质 +5，难产的风险小了些。'),
    'study':  dict(name='诵读诗书', silver=50, stat='study', gain=2, line='你日日诵诗读书，孩子出世后学问底子更好。'),
    'ride':   dict(name='听乐观射', silver=50, stat='riding', gain=2, line='你常让人在院里演武、奏乐，孩子出世后骑射底子更好。'),
    'virtue': dict(name='礼佛积德', silver=50, stat='virtue', gain=2, line='你日日礼佛抄经，孩子出世后品行底子更好。'),
}
TWIN_CHANCE, TWIN_EXTRA_HEALTH_LOSS = 0.10, 15   # 2026-10-06：每次临盆 10% 是双胞胎，体质再多扣 15
BIRTH_HEALTH_LOSS, BIRTH_HEALTH_PER_PRIOR, BIRTH_HEALTH_FLOOR = 25, 8, 5   # 2026-10-06：每次生产必扣体质，生得越多扣得越狠，防一个人孩子太多
LABOR_RISK_BASE, LABOR_RISK_PER_REST = 0.30, 0.10    # 体质不到 50 的人难产概率，每次安胎静养减 10 个点
LABOR_DEATH_CHANCE = 0.05     # 难产了还有这么大概率挺不过来（2026-10-07 起；不大，但不是零）
LABOR_RISK_PER_PRIOR, LABOR_RISK_CAP = 0.20, 0.80    # 2026-10-07：之前每生过一个孩子，难产概率再 +20 个点（体质好的人也一样），最高 80%


def labor_risk(c, prior_births, rests=0):
    """这次临盆难产的概率：体质不到 50 有 30% 底数，之前生过几个孩子每个再加 20%，安胎静养每次减 10%，限制在 0~80%"""
    base = LABOR_RISK_BASE if c['health'] < 50 else 0.0
    return max(0.0, min(LABOR_RISK_CAP, base + LABOR_RISK_PER_PRIOR * prior_births - LABOR_RISK_PER_REST * rests))


CONTRACEPTION_MIN_BIRTHS = 2    # 生过两次孩子之后，才能选择避孕

def birth_count(cid):
    return q('SELECT COUNT(*) n FROM heirs WHERE mother_id=?', (cid,), one=True)['n']

def contraception_on(c):
    return bool(c['contraception'] if 'contraception' in c.keys() else 0) and birth_count(c['id']) >= CONTRACEPTION_MIN_BIRTHS


def pregnancy_chance(c):
    """一次侍寝怀上的概率：12% + 体质×0.08% + 福报×0.05%（体质 60 约 17%，体质 100 约 20%，上限 22%）；35 岁起打六折；45 岁起不再有孕"""
    if c['age_months'] >= FERTILE_BEFORE_AGE * 12: return 0.0
    if contraception_on(c): return 0.0
    if (c['pregnancy_misses'] if 'pregnancy_misses' in c.keys() else 0) >= PREGNANCY_PITY_ATTEMPTS: return 1.0
    p = PREGNANCY_BASE + c['health'] * PREGNANCY_PER_HEALTH + (c['blessing'] if 'blessing' in c.keys() else 0) * PREGNANCY_PER_BLESSING
    if c['age_months'] >= OLD_MOTHER_AGE * 12: p *= OLD_MOTHER_FACTOR
    return min(PREGNANCY_MAX, p)


def bed_count(cands):
    """这一轮翻几位：按 BED_COUNT_WEIGHTS 抽（10% 一位、60% 两位、30% 三位）"""
    return _BED_RNG.choices([n for n, _ in BED_COUNT_WEIGHTS], weights=[w for _, w in BED_COUNT_WEIGHTS])[0]

# 一小时 = 宫里一个月（一天 24 小时正好两年）：每轮翻牌的邸报按「几月」配时令，再配一句今天为什么翻这么多人
BED_MONTHS = ['正月里新年伊始', '二月春寒料峭', '三月桃花正盛', '四月芳菲将尽', '五月端阳将近', '六月暑气蒸腾',
              '七月流火未歇', '八月桂香满园', '九月重阳登高', '十月秋风渐紧', '冬月雪意初浓', '腊月岁末天寒']
BED_REASONS = {
    1: ['皇上批折子批到很晚，没什么心力', '皇上有些头疼，不愿多费心神', '皇上心里惦着一个人，别的懒得看', '太后嘱咐皇上保重龙体', '边关军报压着，皇上无心他顾', '皇上近来懒怠应酬'],
    2: ['皇上心情平和，不偏不倚', '皇后劝皇上雨露均沾', '皇上想听两位的新曲', '敬事房呈上的牌子个个都不错', '皇上想着让后宫都沾沾恩泽', '政务刚好料理完，皇上有些闲暇'],
    3: ['皇上今日兴致极高', '宫里添了喜事，皇上龙心大悦', '太后说后宫该热闹些', '前朝刚传来捷报，皇上满心欢喜', '皇上多饮了几杯，正在兴头上', '各宫姐妹都盼着，皇上索性都见了'],
}
BED_COUNT_WORDS = {1: '一', 2: '两', 3: '三'}

GAME_EPOCH = datetime(2026, 10, 6, 0, 0, tzinfo=TZ)      # 宫里的「第 1 年」从这一刻算起（开服那天零点）；天数计数器中间跳过天也不影响

def game_year(now=None):
    """宫里第几年：从 GAME_EPOCH 起每过 12 个小时就是一年（一小时一个月），按真实时间算，不看游戏天数计数器"""
    now = now or datetime.now(TZ)
    return int((now - GAME_EPOCH).total_seconds() // (12 * 3600)) + 1

def bed_round_note(n, hour, now=None):
    """一轮翻牌的邸报：第几年 + 几月时令 + 为什么 + 翻了几人"""
    month = BED_MONTHS[hour % 12]
    reason = _BED_RNG.choice(BED_REASONS.get(n, BED_REASONS[2]))
    return f"第{game_year(now)}年{month}，{reason}，所以皇上翻了{BED_COUNT_WORDS.get(n, n)}人。"


def pregnancy_due_text(c):
    if not c['pregnancy_started_ts']:
        return '按原孕期结算临盆（旧存档）'
    due = datetime.fromtimestamp(c['pregnancy_started_ts'] + PREGNANCY_MIN_SECONDS, TZ)
    return due.strftime('%m月%d日 %H:%M') + '（北京时间）预计临盆'


def pregnancy_progress(c):
    if not c['pregnancy_started_ts']:
        return dict(percent=0, stage='孕中调养', hours=0, minutes=0, legacy=True)
    elapsed = max(0, time.time()-c['pregnancy_started_ts'])
    remaining = max(0, PREGNANCY_MIN_SECONDS-elapsed)
    stage = '初孕·诊出喜脉' if elapsed<8*3600 else ('安胎·胎息渐稳' if elapsed<16*3600 else '待产·静候临盆')
    if remaining==0: stage='临盆时刻已到，等待接生'
    minutes = math.ceil(remaining/60)
    return dict(percent=min(100,int(elapsed/PREGNANCY_MIN_SECONDS*100)),stage=stage,hours=minutes//60,minutes=minutes%60,legacy=False)


@atomic
def resolve_births(day, include_legacy=True):
    resolve_realtime_drugs(day)
    for c in q("SELECT * FROM consorts WHERE status!='dead' AND pregnant_since>0 AND NOT EXISTS(SELECT 1 FROM afflictions a WHERE a.consort_id=consorts.id AND a.drug='chunxin' AND a.status='active') AND ((pregnancy_started_ts>0 AND pregnancy_started_ts<=?) OR (pregnancy_started_ts=0 AND ? AND ?-pregnant_since>=?))", (time.time()-PREGNANCY_MIN_SECONDS, int(include_legacy), day, PREGNANCY_DAYS)):
        twins = random.random() < TWIN_CHANCE
        pref = c['birth_gender_pref'] if 'birth_gender_pref' in c.keys() else ''      # 管理员在库里给某人设的出生性别（界面和帮助页都不提）
        genders = [pref if pref in ('皇子', '公主') else random.choice(['皇子', '公主']) for _ in range(2 if twins else 1)]
        pre = prenatal_state(c)
        prior_births = q('SELECT COUNT(*) n FROM heirs WHERE mother_id=?', (c['id'],), one=True)['n']
        born = []   # [(label, 资质文字)]
        born_ids = []
        for gender in genders:
            # 排行按本届、同性别已有的最大排行往下数（不再从 6、3 起跳；换届后重新从「大」排起）
            top = q("SELECT COALESCE(MAX(ordinal),0) m FROM heirs WHERE gender=? AND (born_day>=? OR COALESCE(npc_key,'')!='')", (gender, state()['reign_start_day']), one=True)['m']
            ordinal = top + 1
            personality = random.choice(list(HEIR_PERSONALITIES))
            gifts = roll_heir_gifts(c)
            run("""INSERT INTO heirs (mother_id, caretaker_id, gender, ordinal, born_day, born_ts, personality, study, riding, virtue, health,
                                    gift_study, gift_riding, gift_virtue)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c['id'], c['id'], gender, ordinal, day, now_ts(), personality,
                 clamp(random.randint(10, 30) + c['talent'] * 0.1 + pre.get('study', 0), 0, 100),
                 clamp(random.randint(10, 30) + pre.get('riding', 0), 0, 100),
                 clamp(random.randint(10, 30) + c['virtue'] * 0.1 + pre.get('virtue', 0), 0, 100),
                 clamp(60 + c['health'] * 0.1, 0, 100),
                 gifts['study'], gifts['riding'], gifts['virtue']))
            hid = q("SELECT id FROM heirs WHERE mother_id=? ORDER BY id DESC", (c['id'],), one=True)['id']
            ensure_name_choices(hid)
            hid_new = q("SELECT id FROM heirs WHERE mother_id=? ORDER BY id DESC", (c['id'],), one=True)['id']
            born_ids.append(hid_new)
            set_heir_appearance(hid_new, c['appearance'] * 0.7 + random.randint(-8, 8))      # 容貌随母亲，气质按容貌分档随机
            born.append((f"{heir_rank_word(ordinal)}{'阿哥' if gender == '皇子' else '公主'}",
                         gift_text(dict(gift_study=gifts['study'], gift_riding=gifts['riding'], gift_virtue=gifts['virtue']))))
        run("UPDATE consorts SET pregnant_since=0, pregnancy_started_ts=0, prenatal='{}' WHERE id=?", (c['id'],))
        birth_loss = min(BIRTH_HEALTH_LOSS + BIRTH_HEALTH_PER_PRIOR * prior_births + (TWIN_EXTRA_HEALTH_LOSS if twins else 0),
                         max(0, c['health'] - BIRTH_HEALTH_FLOOR))
        if birth_loss > 0: add_stat(c['id'], 'health', -birth_loss)
        run('UPDATE consorts SET postpartum_until=? WHERE id=?', (day + POSTPARTUM_SICK_DAYS, c['id']))
        extra = f'生产耗去元气，体质 -{birth_loss}。' if birth_loss > 0 else ''
        hard_labor = random.random() < labor_risk(c, prior_births, pre.get('rest', 0))
        if hard_labor:
            add_stat(c['id'], 'health', -20); extra += '难产了一整夜，元气大伤，体质再 -20。'
        if twins:
            label = '、'.join(b[0] for b in born)
            kind = '龙凤胎' if len(set(genders)) == 2 else ('双生阿哥' if genders[0] == '皇子' else '双生公主')
            label = f"{kind}（{label}）"
        else:
            label = born[0][0]
        if '皇子' in genders:
            add_prestige(c, PRESTIGE_BORN_PRINCE, f"{full_name(c)}诞下皇子")
            add_favor(c['id'], BIRTH_FAVOR_PRINCE, gain_mult=False)
            if c['rank'] >= MOTHER_BY_SON_MAX_RANK:      # 已经封顶，不再晋位，改加势力
                run("UPDATE consorts SET influence=influence+? WHERE id=?", (MOTHER_BY_SON_INFLUENCE, c['id']))
                extra += f"母凭子贵，势力 +{MOTHER_BY_SON_INFLUENCE}。"
            elif slot_free(c['rank'] + 1, c['id']):      # 母凭子贵只看名额，不看势力门槛，最多晋到嫔（2026-10-07 起）
                set_rank(c['id'], c['rank'] + 1)
                extra += f"母凭子贵，晋为{display_name(get_consort(c['id']))}。"
        else:
            add_favor(c['id'], BIRTH_FAVOR_PRINCESS, gain_mult=False)
        if not state()['mourning']:      # 生子的圣宠加上之后，圣宠、德行、势力若已够下一级的标准，单独判定一次晋封（不用等下一轮晋封检查）
            promoted = try_promote(c, day, quiet_full=True)
            if promoted:
                extra += f"生子圣宠加身，晋为{display_name(promoted)}。"
                housing_sync()
        gift_line = '；'.join((f"{b[0]}：{b[1]}" if twins else b[1]) for b in born)
        gazette(f"{display_name(c)}诞下{label}。{extra}资质：{gift_line}。", 'birth')
        notify(c['id'], f"你诞下了{label}。{extra}", 'good')
        notify(c['id'], f"请嬷嬷看了孩子的根骨：{gift_line}。", 'info')
        notify(c['id'], "皇上为孩子点了几个字，去「子嗣」页挑一个定名，名字是本届字辈加你选的字。", 'info')
        night_mark(c['id'], 'birth', label=label, son='皇子' in genders)
        mom = get_consort(c['id'])       # 母凭子贵晋位之后的位分才算数：位分够了就能亲自抚养（皇子要妃位，公主要嫔位）
        sent = [hid_ for hid_ in born_ids if mom['rank'] < raise_min_rank(get_heir(hid_))]
        if sent:       # 位分不够不能亲自抚养：一出生就由皇嗣养育所照料，抓周前还能托付、位分够了还能领回
            for hid_ in sent: run("UPDATE heirs SET caretaker_id=0, caretaker_affinity=50 WHERE id=?", (hid_,))
            need = '、'.join(sorted({raise_rank_name(get_heir(hid_)) for hid_ in sent}))
            sent_label = label if len(sent) == len(born_ids) else '、'.join(heir_label(get_heir(hid_)) for hid_ in sent)
            gazette(f"{sent_label}按祖制送入皇嗣养育所，由乳母与师傅照料，{need}位以上可申请领养。", 'decree')
            notify(c['id'], f"按祖制，{RANK_NAMES[mom['rank']]}不能亲自抚养{sent_label}（皇子须妃位以上，公主须嫔位以上），先由皇嗣养育所照料。周岁抓周前，你可以去「子嗣」页托付给好感不低于 {HEIR_ENTRUST_MIN_AFFINITY} 的{need}位以上姐妹，或者晋位后领回。", 'info')
        if hard_labor and random.random() < LABOR_DEATH_CHANCE:      # 难产有小概率没挺过来：孩子保留，由后面的换人规则另派抚养人
            die(c['id'], '难产')


def prenatal_state(c):
    try: return json.loads(c['prenatal'] or '{}')
    except ValueError: return {}


app.jinja_env.globals['prenatal_state'] = prenatal_state
app.jinja_env.globals['INFLUENCE_LOW_NIGHTS'] = INFLUENCE_LOW_NIGHTS
app.jinja_env.globals['NEWCOMER_CARE_DAYS'] = NEWCOMER_CARE_DAYS


def do_bedding(bed, day, primary, tray, quiet=False):
    """一位被翻牌的人：圣宠、怀孕、通知、场景。primary 那位还负责记「昨夜宫中」的绿头牌盘"""
    if bed['bed_daily_day']==day and bed['bed_daily_count']>=BED_DAILY_MAX: return
    run('UPDATE consorts SET bed_daily_count=CASE WHEN bed_daily_day=? THEN bed_daily_count+1 ELSE 1 END,bed_daily_day=? WHERE id=?',(day,day,bed['id']))
    dream = affliction(bed['id'], 'jingmeng', day)
    if dream:
        cut_favor(bed['id'], FAVOR_LOSS['dream'])
        add_trust(bed['id'], -3)
        finish_affliction(dream)
        gain = 0
        open_drug_case(q('SELECT * FROM intrigues WHERE id=?', (dream['intrigue_id'],), one=True))
        notify(bed['id'], f"惊梦香发作，惊扰圣驾，圣宠 -{FAVOR_LOSS['dream']}、信任 -3，惊梦香已失效。", 'bad')
    else:
        gain = add_favor(bed['id'], 6 + bed['appearance'] * 0.04)
        add_trust(bed['id'], BED_TRUST_GAIN)
    run("UPDATE consorts SET bedded_count=bedded_count+1, last_audience_day=? WHERE id=?", (day, bed['id']))
    if primary:
        run("UPDATE game_state SET last_bed_id=?, last_bed_day=?, last_bed_pool=?, last_bed_ids=? WHERE id=1",
            (bed['id'], day, json.dumps(tray), json.dumps([bed['id']])))
    else:
        ids = json.loads(state()['last_bed_ids'] or '[]')
        run("UPDATE game_state SET last_bed_ids=? WHERE id=1", (json.dumps(ids + [bed['id']]),))
    if not quiet: gazette(f"敬事房：本轮皇上翻了{display_name(bed)}的牌子。", 'bed')      # 行宫随驾由 bedding_round 统一发一条
    if bed['user_id']:
        msg = f"敬事房来传话：本轮皇上翻了你的牌子。圣宠 +{gain}" + ('。' if dream else f"，信任 +{BED_TRUST_GAIN}。")
        newly_pregnant = False
        if not dream and not affliction(bed['id'], 'hanshui', day) and random.random() < pregnancy_chance(bed):
            run("UPDATE consorts SET pregnant_since=?, pregnancy_started_ts=?, prenatal='{}', pregnancy_misses=0 WHERE id=?", (day, time.time(), bed['id']))
            msg += "……太医诊出了喜脉，怀孕满24小时自动临盆。孕中可以在本宫安胎、胎教。"
            gazette(f"{display_name(bed)}有喜了。", 'birth')
            newly_pregnant = True
        if not newly_pregnant and bed['age_months'] < FERTILE_BEFORE_AGE * 12 and not affliction(bed['id'], 'hanshui', day) and not dream and not contraception_on(bed):
            run('UPDATE consorts SET pregnancy_misses=pregnancy_misses+1 WHERE id=?', (bed['id'],))
        notify(bed['id'], msg, 'good')
        guide_tip(bed['id'], 'bed', '「头一回侍寝，忐忑也是常事。往后皇上想起你，全看这几日的功夫。」')
        if newly_pregnant:
            guide_tip(bed['id'], 'pregnant', '「有喜是大事，往后当心着些，别的事都往后放一放。」')
        if not get_scene(get_consort(bed['id'])): start_scene(bed['id'], 'audience', prompt=random.randrange(len(AUDIENCE_PROMPTS)), bed=1, hoarse=bool(affliction(bed['id'], 'yachan', day)))
    housing_visit(bed)


def bed_weight(c, day):
    w = 10 + c['favor'] * 0.15 + c['appearance'] * 0.5 + c['talent'] * 0.15 + c['seek_bonus']
    if emperor_art_bonus(c): w += 20
    if c['diet_eff'] == 'lavish': w += LAVISH_BED_BONUS
    if c['user_id'] and day - c['entered_day'] <= 3: w += 15   # 皇上喜新
    tr = emperor_traits()
    if tr.get('study', 0) >= 60: w += c['talent'] * 0.1      # 学问高的皇上偏爱才艺
    if tr.get('riding', 0) >= 60: w += c['health'] * 0.2     # 骑射高的皇上欣赏体质好的
    if c['personality'] == 'charming': w *= 1.15
    if c['npc_key']: w *= NPC_BED_MULT
    return max(1, w)

BED_ROUND_HOURS = tuple(range(24))    # 翻牌（侍寝）每 1 小时一轮：0/1/2/…/23 点（2026-10-07 起；先前每 2 小时、最早每 4 小时）
PACE_ROUND_HOURS = (0,4,8,12,16,20)         # 精力回复、晋封检查仍是每 4 小时一次，和翻牌轮分开


def eligible_bedding(c,day):
    return c['status']=='normal' and 1<=c['rank']<=PLAYER_MAX_RANK and not c['pregnant_since'] and not is_sick(c) and not affliction(c['id'],'yanzhi',day) and (c['bed_daily_day']!=day or c['bed_daily_count']<BED_DAILY_MAX)


def last_bed_consorts(st):
    """最近一轮被翻牌的所有人（一轮可能翻不止一位）；老数据没有 last_bed_ids 就退回只有主翻的那位"""
    try: ids = json.loads(st['last_bed_ids'] or '[]')
    except ValueError: ids = []
    if not ids and st['last_bed_id']: ids = [st['last_bed_id']]
    return [x for x in (get_consort(i) for i in ids) if x]

XINGGONG_CHANCE = 0.10       # 每轮翻牌有这么大概率变成「皇上带妃子去行宫」，每个游戏日最多一次
XINGGONG_COUNT = 6           # 随驾的人数；符合侍寝条件的人不到这个数就不触发
XINGGONG_PLACES = ['畅春园', '汤泉行宫', '承德避暑山庄', '圆明园', '西苑行宫', '木兰围场行宫']


@atomic
def bedding_round(day,key):
    st=state()
    if not st['event_started'] or st['maintenance'] or st['mourning'] or emperor_ill(st,day): return []
    if st['last_bed_round_key']==key: return []
    run('UPDATE game_state SET last_bed_round_key=? WHERE id=1',(key,))
    cands=[c for c in q("SELECT * FROM consorts WHERE user_id IS NOT NULL") if eligible_bedding(c,day)]
    trip=len(cands)>=XINGGONG_COUNT and not daily_count(0,'xinggong') and random.random()<XINGGONG_CHANCE
    if trip: daily_inc(0,'xinggong')
    count=XINGGONG_COUNT if trip else bed_count(cands); beds=[];used=set()
    n_shown=min(count,len(cands))
    if n_shown and not trip:
        hour_part=str(key).rsplit(':',1)[-1]
        gazette(bed_round_note(n_shown,int(hour_part) if hour_part.isdigit() else datetime.now(TZ).hour),'news')      # 一小时当一个月：邸报按几月配时令和理由
    for _ in range(count):
        pool=[get_consort(c['id']) for c in cands if c['id'] not in used]
        pool=[c for c in pool if eligible_bedding(c,day)]
        if not pool: break
        bed=random.choices(pool,weights=[bed_weight(c,day) for c in pool])[0]
        steals=list(q("SELECT * FROM intrigues WHERE status='pending' AND method='steal' AND day<=?",(day,)))
        random.shuffle(steals)
        for it in steals:
            if it['target_id']!=bed['id']: continue
            atk=get_consort(it['attacker_id'])
            if atk['id'] in used or not eligible_bedding(atk,day): continue
            _,new_bed=resolve_intrigue(it,bed['id'])
            if new_bed:bed=get_consort(new_bed)
        tray=[c['id'] for c in sorted(pool,key=lambda c:-bed_weight(c,day))[:7]]
        if bed['id'] not in tray:tray.append(bed['id'])
        do_bedding(bed,day,not beds,tray,quiet=trip)
        used.add(bed['id']);beds.append(get_consort(bed['id']))
    if trip and beds:
        place=random.choice(XINGGONG_PLACES)
        names='、'.join(display_name(b) for b in beds)
        gazette(f"皇上忽起游兴，驾幸{place}，随驾{len(beds)}人：{names}，均算侍寝一次。",'decree')
        for b in beds:
            if b['user_id']: notify(b['id'],f"皇上忽起游兴，驾幸{place}，点了你随驾，这一次算侍寝。",'good')
    return beds


def bed_chance_text(c):
    """首页显示：下一轮翻牌，你被翻到的大致概率。一轮翻 count 位，按「每次抽中的概率」估算，不含截宠"""
    day = cur_day()
    if not eligible_bedding(c, day): return '暂不在牌子里（禁足、有孕、病中或今日已翻满）'
    cands = [x for x in q("SELECT * FROM consorts WHERE user_id IS NOT NULL") if eligible_bedding(x, day)]
    total = sum(bed_weight(x, day) for x in cands)
    if total <= 0: return '—'
    p = bed_weight(c, day) / total
    chance = sum(w * (1 - (1 - p) ** n) for n, w in BED_COUNT_WEIGHTS)
    return f"约 {chance * 100:.0f}%（每轮翻 1～{BED_MAX_PER_ROUND} 位，牌子里共 {len(cands)} 人）"


def next_bedding_text():
    st=state()
    if st['maintenance']:return '维护暂停'
    if not st['event_started']:return '活动尚未开始'
    if st['mourning'] or emperor_ill(st,cur_day()):return '病重或国丧，暂停翻牌'
    now=datetime.now(TZ)
    slots=[(now+timedelta(days=d)).replace(hour=h,minute=0,second=0,microsecond=0) for d in (0,1) for h in BED_ROUND_HOURS]
    return min(t for t in slots if t>now).strftime('%m-%d %H:%M')+'（北京时间）'


def latest_slot(now,hours):
    slots=[now.replace(hour=h,minute=0,second=0,microsecond=0) for h in hours]
    slots+=[(now-timedelta(days=1)).replace(hour=hours[-1],minute=0,second=0,microsecond=0)]
    return max(slot for slot in slots if slot<=now).strftime('%Y-%m-%d:%H')

def latest_bedding_slot(now):
    return latest_slot(now,BED_ROUND_HOURS)

def latest_pace_slot(now):
    return latest_slot(now,PACE_ROUND_HOURS)


@atomic
def settle_day(bed_key=None, partial=False):
    """partial=True：补结算——只做换日这类增量项，月例、长年龄、宫人月钱、疾病老死、圣宠流失、伙食修缮这些「每晚一次」的账不再算（2026-10-07 换时间表那天用过一次）"""
    with settle_lock:
        # 结算期间 notify/gazette 会标成"夜间"，night_mark 记下每个人这一夜的经历，最后据此下口谕
        g.bed_round_key=bed_key
        g.settle_partial = partial
        g.settling, g.night_events = True, {}
        g.ill_digest = {}
        try:
            r = _settle_night()
            flush_ill_digest()
            return r
        finally:
            g.bed_round_key=None
            g.settle_partial = False
            g.settling, g.night_events = False, {}

def audience_weight(c, day):
    """召见权重 = 10 + 信任 × 0.3 + 多少天没见过皇上 × 4（最多算 10 天）。久未见驾的人更容易被想起"""
    return 10 + c['trust'] * 0.3 + min(10, day - c['last_audience_day']) * 4

@atomic
def try_promote(c, day, quiet_full=False):
    """单独判定一个人能不能晋一级：圣宠、德行、势力都够标准且名额有空才晋。返回晋封后的 consorts 行，没晋返回 None"""
    c = get_consort(c['id'])
    if not c['user_id'] or c['status'] != 'normal' or not 1 <= c['rank'] <= PLAYER_MAX_RANK - 1: return None
    nxt = c['rank'] + 1
    if c['favor'] < promote_favor_need(c, nxt) or c['virtue'] < promote_virtue_need(nxt) or c['influence'] < PROMOTE_INFLUENCE[nxt]: return None
    if not slot_free(nxt, c['id']):
        if not quiet_full and daily_count(c['id'], 'slot_full_notice') == 0:
            notify(c['id'], f"论圣宠你已够得上{RANK_NAMES[nxt]}，可{RANK_NAMES[nxt]}的位子都满了。")
            daily_inc(c['id'], 'slot_full_notice')
        return None
    quick = bool(c['last_promote_day']) and day - c['last_promote_day'] <= 4
    old_title = c['title']
    set_rank(c['id'], nxt)
    if not old_title and nxt < 5 and random.random() < .30:
        assign_title(c['id'])
    c2 = get_consort(c['id'])
    title_note = f"赐封号「{c2['title']}」，" if not old_title and c2['title'] else ''
    gazette(f"圣旨：{title_note}{full_name(c2)}晋为{display_name(c2)}。", 'decree')
    notify(c['id'], f"圣旨到：{title_note}晋你为{display_name(c2)}。", 'decree')
    night_mark(c['id'], 'promoted', quick=quick, rank=RANK_NAMES[nxt])
    return c2


def resolve_promotions(day):
    """只处理晋封；每次最多一级，不推进年龄、收入或游戏日。"""
    if state()['mourning']: return []
    promoted = []
    for c in q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND status IN ('normal','confined')
                  AND rank BETWEEN 1 AND ? ORDER BY favor DESC""", (PLAYER_MAX_RANK - 1,)):
        c2 = try_promote(c, day)
        if c2: promoted.append(f"晋封：{display_name(c2)}")

    housing_sync()
    return promoted


def _settle_night():
    st = state()
    day = st['day']
    partial = getattr(g, 'settle_partial', False)
    report = []
    if st['mourning']:
        return finish_mourning(day, st)
    ill = emperor_ill(st, day)   # 皇上病重的这几晚，不翻牌子、不召见

    # 白天没来得及定夺的场景、昨夜的侍寝/召见场景，到今晚都作废
    run("UPDATE consorts SET pending_scene='' WHERE pending_scene!=''")

    # 先处理之前几天中的毒、病重；当晚新中毒/病倒的人不会当晚就死
    resolve_poison_crises(day)
    resolve_illness_crises(day)
    resolve_drug_cases(day)

    run("DELETE FROM daily_feed WHERE day < ?", (day - FEED_KEEP_DAYS,))

    # 1. NPC 出手 + 结算阴谋（截宠除外，要等翻牌子）
    pend = q("SELECT * FROM intrigues WHERE status='pending' AND day<=? AND method!='steal'", (day,))
    pend = list(pend); random.shuffle(pend)
    for it in pend:
        resolve_intrigue(it)

    tick_drugs(day)

    beds = bedding_round(day, getattr(g,'bed_round_key',None) or f'manual:{day}')
    bed_ids = {b['id'] for b in beds}
    report += [f"侍寝：{display_name(b)}" for b in beds]
    for it in q("SELECT * FROM intrigues WHERE status='pending' AND method='steal' AND day<=?",(day,)):
        resolve_intrigue(it,None)

    # 2b. 召见：侍寝之外，另召几位玩家单独说话，让更多人有机会见到皇上
    pool = [] if ill else [c for c in q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status='normal'")
            if not is_sick(c) and c['id'] not in bed_ids]
    called = []
    for _ in range(min(AUDIENCE_PER_NIGHT, len(pool))):
        r = pick_audience(pool, day)
        pool.remove(r); called.append(r)
        add_favor(r['id'], 5)
        run("UPDATE consorts SET last_audience_day=? WHERE id=?", (day, r['id']))
        notify(r['id'], '御前总管来传话：皇上要召你去养心殿说话。圣宠 +5。', 'good')
        guide_tip(r['id'], 'audience', '「皇上召见，规规矩矩应答就是，不必太紧张。」')
        start_scene(r['id'], 'audience', prompt=random.randrange(len(AUDIENCE_PROMPTS)), bed=0, hoarse=bool(affliction(r['id'], 'yachan', day)))
    if called:
        gazette(f"皇上召见了{'、'.join(display_name(c) for c in called)}。", 'audience')
        report.append('召见：' + '、'.join(display_name(c) for c in called))

    # 同宫日间动向先回报，管教在生产与迁宫前处理。
    housing_reports(day)

    # 3. 生产（旧孕期兼容；新孕期按真实24小时）
    resolve_births(day)

    # 3b. 皇嗣周岁抓周（贵人以下的生母，这天孩子按祖制改指给别人抚养）、皇上考校、随驾秋狝
    heir_growth_tick(day)
    custody_battle_tick(day)
    heir_rehome_tick(day)
    heir_orphan_tick(day)
    heir_adult_tick(day)
    heir_succession_tick(day)
    if not partial:
        diet_tick(day)
        repair_tick(day)
    family_tick(day)
    family_venture_tick(day)
    family_patron_tick(day)
    family_remit_tick(day)
    heir_exam_tick(day)
    heir_hunt_tick(day)

    # 4. 晚间晋封，宴会奖励已到账
    report += resolve_promotions(day)

    # 位分全部定下后，按位分、圣宠安置等待正殿的人。
    housing_sync()


    # 5. 日常：同步增长两岁、月例、圣宠流失、精力、禁足/冷宫期满、请安
    capital_mothers = capital_mother_ids()
    zones = None if partial else refresh_care_tiers()
    for c in q("SELECT * FROM consorts WHERE status NOT IN ('xiunv','dead')"):
        c = get_consort(c['id'])
        if not partial:      # 补结算不再算这几笔每晚一次的账
            run('UPDATE consorts SET age_months=age_months+? WHERE id=?', (AGE_MONTHS_PER_DAY // 2, c['id']))   # 一天 = 宫中两年：零点涨一岁，中午 12 点再涨一岁（见 age_noon_tick）
            influence_check(c, day)
            c = get_consort(c['id'])
            in_low = (c['id'] in zones[1]) if zones else c['favor'] < FAVOR_LOW
            streak = c['unfavored_days']+1 if in_low else 0
            run('UPDATE consorts SET unfavored_days=? WHERE id=?',(streak,c['id']))
            c=get_consort(c['id'])
            drop = c['favor_mark'] - c['favor'] if c['favor_mark'] >= 0 else 0      # 比昨夜结算后的圣宠净掉了多少（含被使计、受罚、被截宠，扣掉当天涨的）
            if c['user_id'] and not c['npc_key'] and c['status'] == 'normal' and c['rank'] >= 3 and drop >= FAVOR_DROP_DEMOTE and day - c['entered_day'] >= NEWCOMER_CARE_DAYS:
                old_name = display_name(c)      # 一天之内圣宠大跌，皇上龙颜不悦：降一级
                demote_rank(c['id'])
                c = get_consort(c['id'])
                notify(c['id'], f"你这一天里圣宠一下子跌了 {drop} 点，皇上龙颜不悦，位分降为{display_name(c)}。", 'bad')
                gazette(f"{old_name}圣眷骤衰，皇上降其位分，今称{display_name(c)}。", 'decree')
            if c['status'] != 'cold':
                income=favor_stipend(c,day)
                add_silver(c['id'],income)
                if income != STIPEND.get(c['rank'],0) and c['user_id']:
                    notify(c['id'],f"今日{FAVOR_CARE[favor_care_tier(c,day)]['name']}待遇，月例与赏银合计 {income} 两。",'good' if favor_care_tier(c,day)=='hot' else 'info')
            if not c['pregnant_since']:
                decay = math.ceil(c['favor'] * FAVOR_DECAY * (CAPITAL_DECAY_FACTOR if c['id'] in capital_mothers else 1))
                run("UPDATE consorts SET favor=MAX(0, favor-?) WHERE id=?", (decay, c['id']))
            if c['npc_key'] and c['status'] == 'normal':
                add_favor(c['id'], random.randint(0, 8), gain_mult=False)
            run("UPDATE consorts SET favor_mark=favor WHERE id=?", (c['id'],))      # 记下今夜结算后的圣宠，明晚算「一天掉了多少」
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
                notify(c['id'], f"你已经 {missed} 天没参加晨省了，宫里说你恃宠而骄。德行 -3。", 'bad')

    # 5a. 老死、染病：年岁到了、体虚、冷宫、时疫、产后失调
    if not partial:
        old_age_tick(day)
        illness_onset_tick(day)

    # 5b. 宫人：月钱、忠心、病好了没有；白天没处理的小事作废
    if not partial:
        drug_gifts(day)
        maid_upkeep(day)
        heir_upkeep(day)

    # 6. 口谕：根据每个人这一夜的真实经历挑一句，没什么可说的就不说
    issue_edicts(day)

    # 6b. 皇上的寿数：驾崩日到了就开匾换届；没病的按年龄掷一次
    if emperor_tick(day):
        return report

    # 7. 进入新的一天
    new_day = day + 1
    mood = random.choices(['大悦', '平和', '烦闷', '震怒'], weights=[15, 55, 22, 8])[0]
    pref = random.choice(ARTS) if new_day % 7 == 1 else st['emperor_pref']
    run("UPDATE game_state SET day=?, last_settle_date=?, emperor_mood=?, emperor_pref=? WHERE id=1",
        (new_day, datetime.now(TZ).date().isoformat(), mood, pref))
    if pref != st['emperor_pref']:
        gazette(f"听养心殿的人说，皇上这几日格外喜欢{pref}。", 'news', day=new_day)
    fest = active_festival(new_day)
    if fest: gazette(FESTIVALS[fest]['line'], 'news', day=new_day)
    season = active_season(new_day)
    if season: gazette(f"{SEASONS[season]['name']}到了，暇趣里应景的一笔，格外让人惦记。", 'news', day=new_day)
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
    nights = day - c['entered_day'] + 1          # 已完成的结算次数
    if c['entered_day'] and nights > 0 and nights % 5 == 0:
        years = cn_ordinal(nights * AGE_YEARS_PER_DAY)
        q_ = c['dianxuan_quote']
        if q_:
            said = f"你说{q_}" if q_.startswith('「') else f"你{q_}"
            return f"你入宫{years}年了。朕还记得殿选那日，{said.rstrip('。')}。"
        return f"你入宫{years}年了。"
    for h in [x for x in q("SELECT * FROM heirs WHERE mother_id=?", (c['id'],)) if 6 * HEIR_DAYS_PER_YEAR <= heir_age_days(x, day) < 6 * HEIR_DAYS_PER_YEAR + 1]:
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
            notify(c['id'], f"御前总管来传皇上口谕：「{line}」", 'edict')

# ── 告警：出了事要有人知道 ─────────────────────────────────────────────────────────
# 结算出错、结算拖延、页面 500、备份失败都记进 alerts 表（后台首页有红色提示和列表）；
# 配了环境变量 ALERT_WEBHOOK 就同时推送到群机器人。用独立的数据库连接写，不跟随出错的那个事务。

ALERT_WEBHOOK = os.environ.get("ALERT_WEBHOOK", "")
ALERT_STYLE = os.environ.get("ALERT_WEBHOOK_STYLE", "json")     # json / wecom / dingtalk / feishu
ALERT_COOLDOWN = 3600                                           # 同一件事 1 小时内不重复推送
SETTLE_OVERDUE_MINUTES = 30                                     # 过了结算时刻这么久还没结算，就是出事了
SLOW_SETTLE_SECONDS = 10
BACKUP_KEEP = 48


def alert_payload(style, text):
    if style in ('wecom', 'dingtalk'): return {'msgtype': 'text', 'text': {'content': text}}
    if style == 'feishu': return {'msg_type': 'text', 'content': {'text': text}}
    return {'text': text}


def _post_webhook(url, style, text):
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(alert_payload(style, text), ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=5).read()


def send_alert_webhook(text):
    """推送放在线程里，慢了、挂了都不拖累主流程"""
    if not ALERT_WEBHOOK: return False
    def go():
        try: _post_webhook(ALERT_WEBHOOK, ALERT_STYLE, text)
        except Exception: traceback.print_exc()
    threading.Thread(target=go, daemon=True).start()
    return True


def raise_alert(kind, key, message, detail=''):
    """记一条告警。同一个 key 没处理前只累加次数；超过冷却时间再推送一次"""
    try:
        db = sqlite3.connect(DB_PATH, timeout=15)
        db.row_factory = sqlite3.Row
        now, push = now_ts(), False
        row = db.execute("SELECT * FROM alerts WHERE key=? AND resolved=0", (key,)).fetchone()
        if row:
            db.execute("UPDATE alerts SET count=count+1, last_ts=?, message=?, detail=? WHERE id=?", (now, message, detail, row['id']))
            if now - row['notified_ts'] >= ALERT_COOLDOWN:
                push = True
                db.execute("UPDATE alerts SET notified_ts=? WHERE id=?", (now, row['id']))
        else:
            db.execute("INSERT INTO alerts (kind, key, message, detail, first_ts, last_ts, notified_ts) VALUES (?,?,?,?,?,?,?)",
                       (kind, key, message, detail, now, now, now))
            push = True
        db.commit(); db.close()
        if push: send_alert_webhook(f"【甄嬛传告警】{message}")
    except Exception:
        traceback.print_exc()


def settle_overdue_minutes(now, st):
    """今天的结算时刻已经过了几分钟、却还没结算；没到点或已结算返回 0"""
    if st['last_settle_date'] == now.date().isoformat(): return 0
    target = now.replace(hour=SETTLE_HOUR, minute=SETTLE_MINUTE, second=0, microsecond=0)
    return max(0, int((now - target).total_seconds() // 60))


def run_settle_cycle():
    """后台线程每分钟调用一次：该结算就结算；出错、太慢、拖延都报警。活动没开始计时、或者在维护中，整个跳过，不结算也不报警"""
    with app.app_context():
        st = state()
        if not st['event_started'] or st['maintenance']: return
        start = time.time()
        try:
            maybe_settle()
        except Exception as e:
            raise_alert('settle', 'settle-exception', f"夜间结算出错：{type(e).__name__}: {str(e)[:150]}", traceback.format_exc()[-1800:])
            return
        took = time.time() - start
        if took > SLOW_SETTLE_SECONDS:
            raise_alert('slow', 'settle-slow', f"这次结算用了 {took:.0f} 秒，比平时慢得多", '')
        now = datetime.now(TZ)
        late = settle_overdue_minutes(now, state())
        if late >= SETTLE_OVERDUE_MINUTES:
            raise_alert('settle', f"settle-overdue:{now.date().isoformat()}", f"今晚的结算已经拖了 {late} 分钟还没跑完，玩家在等牌子", '')


def backup_db(backup_dir):
    """用 SQLite 自带的在线备份（WAL 下直接拷文件可能漏写入），只留最近 BACKUP_KEEP 份"""
    os.makedirs(backup_dir, exist_ok=True)
    dst = os.path.join(backup_dir, f"zhenhuan_{time.strftime('%Y%m%d_%H%M%S')}.db")
    src, out = sqlite3.connect(DB_PATH), sqlite3.connect(dst)
    with out: src.backup(out)
    src.close(); out.close()
    files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')], reverse=True)
    for old in files[BACKUP_KEEP:]:
        os.remove(os.path.join(backup_dir, old))
    return dst


@app.route('/help')
def help_page():
    """玩法说明：不用登录就能看；数字全部从游戏里的常量读，调数值后自动跟着变"""
    return render_template('help.html', ACTIONS={k: a for k, a in ACTIONS.items() if k not in ('attend', 'shoukang')},
                           RANK_NAMES=RANK_NAMES, RANK_SLOTS=RANK_SLOTS, STIPEND=STIPEND, FAVOR_CARE=FAVOR_CARE, favor_care_tier=favor_care_tier, favor_stipend=favor_stipend, PROMOTE_FAVOR=PROMOTE_FAVOR,
                           PROMOTE_VIRTUE=PROMOTE_VIRTUE, MAID_QUOTA=MAID_QUOTA, MAID_WAGE=MAID_WAGE,
                           diet_norm={r: diet_cost(r, 'normal') for r in range(1, 10)}, DIETS=DIETS, DIET_RATIO=DIET_RATIO,
                           INTRIGUES=INTRIGUES, VENTURES=VENTURES, VENTURE_MAX=VENTURE_MAX, PRAY_TIERS=PRAY_TIERS, QUIET_DAYS=QUIET_DAYS,
                           FAMILY_MAX=FAMILY_MAX_MEMBERS, ENERGY_MAX=ENERGY_MAX, FAVOR_DECAY=FAVOR_DECAY, CONSPIRE_AFFINITY_MIN=CONSPIRE_AFFINITY_MIN, CONSPIRE_BONUS=CONSPIRE_BONUS, CONSPIRE_COST_RATIO=CONSPIRE_COST_RATIO, HEALTH_DECAY_HOUR=HEALTH_DECAY_HOUR, TWIN_CHANCE=TWIN_CHANCE, TWIN_EXTRA_HEALTH_LOSS=TWIN_EXTRA_HEALTH_LOSS, BIRTH_HEALTH_LOSS=BIRTH_HEALTH_LOSS, BIRTH_HEALTH_PER_PRIOR=BIRTH_HEALTH_PER_PRIOR, BIRTH_HEALTH_FLOOR=BIRTH_HEALTH_FLOOR, CONTRACEPTION_MIN_BIRTHS=CONTRACEPTION_MIN_BIRTHS, CUISHENG_HOURS=CUISHENG_HOURS, INFLUENCE_DECAY=INFLUENCE_DECAY, HEALTH_DECAY_BASE=HEALTH_DECAY_BASE,
                           HEALTH_DECAY_PER_YEAR=HEALTH_DECAY_PER_YEAR, HEALTH_DECAY_FLOOR=HEALTH_DECAY_FLOOR, HEALTH_DYING_AT=HEALTH_DYING_AT, DYING_HOURS=DYING_HOURS, CONFINE_DAYS=CONFINE_DAYS, CONFINE_HOURS=CONFINE_HOURS,
                           COLD_DAYS=COLD_DAYS, BANQUET_JOIN_SILVER=BANQUET_JOIN_SILVER, EAT_DAILY_MAX=EAT_DAILY_MAX, COOK_DAILY_MAX=COOK_DAILY_MAX, GARDEN_SELL_DAILY_CAP=GARDEN_SELL_DAILY_CAP, GARDEN_TAN_CHANCE=GARDEN_TAN_CHANCE, GARDEN_TAN_LOSS=GARDEN_TAN_LOSS, PREGNANCY_BASE=PREGNANCY_BASE, PREGNANCY_MAX=PREGNANCY_MAX, PREGNANCY_PITY_ATTEMPTS=PREGNANCY_PITY_ATTEMPTS, PREGNANCY_DAYS=PREGNANCY_DAYS,
                           settle_h=SETTLE_HOUR, settle_m=SETTLE_MINUTE, REMIT_INTERVAL=REMIT_INTERVAL,
                           HEIR_EXAM_INTERVAL=HEIR_EXAM_INTERVAL, HEIR_EXAM_MIN_AGE=HEIR_EXAM_MIN_AGE, HEIR_EXAM_MAX_AGE=HEIR_EXAM_MAX_AGE,
                           ERRAND_INTERVAL=ERRAND_INTERVAL, CROWN_INTERVAL=CROWN_INTERVAL, BIRTHDAY_INTERVAL=BIRTHDAY_INTERVAL,
                           HAZARD_AFTER_YEARS=HAZARD_AFTER_YEARS, MAX_REIGN_DAYS=MAX_REIGN_DAYS,
                           REQUEST_INTERVAL=REQUEST_INTERVAL, REQUEST_DAYS=REQUEST_DAYS, DOWAGER_AUDIENCE_INTERVAL=DOWAGER_AUDIENCE_INTERVAL,
                           HEIR_ADULT_AGE_DAYS=int(HEIR_ADULT_AGE_DAYS), HEIR_DAYS_PER_YEAR=HEIR_DAYS_PER_YEAR, STANCE_LOCK_DAYS=STANCE_LOCK_DAYS)


@app.route('/healthz')
def healthz():
    """给监控探针用：结算拖延或数据库出问题返回 503。活动没开始计时、或者在维护中，不算拖延——那是故意停的。只有几个布尔和数字，不含玩家信息"""
    try:
        st = state()
        paused = (not st['event_started']) or st['maintenance']
        late = 0 if paused else settle_overdue_minutes(datetime.now(TZ), st)
        open_alerts = q("SELECT COUNT(*) n FROM alerts WHERE resolved=0", one=True)['n']
        ok = late < SETTLE_OVERDUE_MINUTES
        return jsonify(ok=ok, paused=paused, maintenance=bool(st['maintenance']), event_started=bool(st['event_started']),
                       settle_overdue_minutes=late, last_settle_date=st['last_settle_date'], day=st['day'],
                       mourning=bool(st['mourning']), open_alerts=open_alerts), (200 if ok else 503)
    except Exception as e:
        return jsonify(ok=False, error=type(e).__name__), 503


@app.errorhandler(500)
def on_server_error(e):
    orig = getattr(e, 'original_exception', None) or e
    tb = ''.join(traceback.format_exception(type(orig), orig, orig.__traceback__))
    raise_alert('error', f"http500:{request.endpoint}:{type(orig).__name__}",
                f"页面出错 {request.method} {request.path}：{type(orig).__name__}: {str(orig)[:120]}", tb[-1800:])
    return '出了点问题，已经记下了，稍后再试。', 500


ENERGY_REGEN = 2   # 除结算那一轮外，每个翻牌时点（4/8/12/16/20 点）每人回 2 点精力，封顶 ENERGY_MAX；0 点日结算回满

@atomic
def energy_tick(key):
    """每 4 小时回精力（用 PACE_ROUND_HOURS 的时点，不是翻牌轮）；不受皇上病重/国丧影响"""
    st = state()
    if st['last_energy_key'] == key or key.endswith(':%02d' % SETTLE_HOUR): return
    run('UPDATE game_state SET last_energy_key=? WHERE id=1', (key,))
    run("UPDATE consorts SET energy=MIN(?, energy+?) WHERE user_id IS NOT NULL AND status!='dead' AND energy<?",
        (ENERGY_MAX, ENERGY_REGEN, ENERGY_MAX))


HEALTH_DECAY_HOUR = SETTLE_HOUR   # 和日结算同一时刻（0 点），所有人体质自然衰减一次
HEALTH_DECAY_BASE = 15       # 20 岁时每晚平均掉这么多点体质，也是任何年龄每晚至少掉的数（2026-10-06 从 0.2 提到 0.5，2026-10-07 几次上调，最后到 15）
HEALTH_DECAY_PER_YEAR = 0.75 # 20 岁以后每长一岁，每晚平均多掉这么多（原 0.03，后 0.08、0.12、0.25、0.5，2026-10-07 提到 0.75）
HEALTH_DECAY_FLOOR = 1       # 自然衰减一直掉，最低到 1（2026-10-07 起不再停在 20；掉到 HEALTH_DYING_AT 以下就是濒死）
HEALTH_DYING_AT = 10         # 体质掉到这个数及以下：濒死
DYING_HOURS = 12             # 濒死状态撑过这么多小时还没好转（体质回到 HEALTH_DYING_AT 以上）就殒命

def health_decay_rate(age_months):
    return HEALTH_DECAY_BASE + max(0, age_months / 12 - 20) * HEALTH_DECAY_PER_YEAR

def health_decay_tick():
    """每人按年龄算出平均掉多少，整数部分必掉，小数部分按概率再掉 1"""
    for c in q("SELECT id, health, age_months FROM consorts WHERE status NOT IN ('dead','xiunv')"):
        rate = health_decay_rate(c['age_months'])
        loss = int(rate) + (1 if random.random() < rate - int(rate) else 0)
        loss = min(loss, c['health'] - HEALTH_DECAY_FLOOR)
        if loss > 0: add_stat(c['id'], 'health', -loss)
    dying_tick()


def dying_tick():
    """每分钟查一次：体质掉到濒死线以下就开始计时，12 小时内没好转就殒命；好转了（体质回到线以上）计时清零"""
    now = now_ts()
    for c in q("SELECT * FROM consorts WHERE status NOT IN ('dead','xiunv') AND (health<=? OR dying_since_ts>0)", (HEALTH_DYING_AT,)):
        if c['health'] <= HEALTH_DYING_AT:
            if not c['dying_since_ts']:
                run("UPDATE consorts SET dying_since_ts=? WHERE id=?", (now, c['id']))
                if c['user_id']: notify(c['id'], f"你的体质只剩 {c['health']} 点，已经濒死了。{DYING_HOURS} 小时内再不好转就要殒命：快去「本宫」静养、梳妆，或者请姐妹送补养，把体质养回 {HEALTH_DYING_AT + 1} 点以上。", 'bad')
                gazette(f"{display_name(c)}病入膏肓，太医说怕是撑不过{DYING_HOURS}个时辰。", 'news')
            elif now - c['dying_since_ts'] >= DYING_HOURS * 3600:
                die(c['id'], '体弱衰竭，久未调养，不治身亡')
        else:
            run("UPDATE consorts SET dying_since_ts=0 WHERE id=?", (c['id'],))
            if c['user_id']: notify(c['id'], f"你的体质回到了 {c['health']} 点，总算从鬼门关前缓了过来。", 'good')


@atomic
def promotion_tick(key, settle_due=False):
    """晋封每 4 小时检查一次（PACE_ROUND_HOURS 的时点）；这一分钟日结算要跑的话由结算自己查，免得同一分钟晋两级"""
    st = state()
    if st['last_promo_key'] == key or settle_due: return
    run("UPDATE game_state SET last_promo_key=? WHERE id=1", (key,))
    if resolve_promotions(st['day']):
        for r in _player_rows(): check_achievements(r['id'])


def age_noon_tick(now):
    """每天中午 12 点，所有在世的妃嫔再涨一岁（零点结算已涨一岁，合起来一天两岁，即每 12 小时一岁）；每天只做一次，错过了下一分钟补"""
    today = now.date().isoformat()
    if now.hour < 12 or state()['last_noon_age_date'] == today: return
    run("UPDATE game_state SET last_noon_age_date=? WHERE id=1", (today,))
    run("UPDATE consorts SET age_months=age_months+? WHERE status NOT IN ('xiunv','dead')", (AGE_MONTHS_PER_DAY // 2,))

@atomic
def maybe_settle():
    """翻牌每 2 小时一轮（每轮 2 位）、精力和晋封每 4 小时、22点宴会、0点日结算；补执行时也先发宴会奖励。"""
    now=datetime.now(TZ)
    st=state()
    if not st['event_started'] or st['maintenance']:return
    resolve_births(st['day'],include_legacy=False)
    key=latest_bedding_slot(now)
    pace_key=latest_pace_slot(now)
    energy_tick(pace_key)
    dying_tick()
    age_noon_tick(now)
    heir_age_events(st['day'])
    bedding_round(st['day'],key)
    maybe_banquet(now)
    today = now.date().isoformat()
    st = state()
    settle_due = past_settle_time(now) and state()['last_settle_date'] != today
    promotion_tick(pace_key, settle_due)
    release_confinements()
    bot_tick(now)
    if settle_due:
        settle_day(bed_key=key)
        for r in _player_rows():check_achievements(r['id'])
    if now.hour >= HEALTH_DECAY_HOUR and state()['last_decay_date'] != today:
        run("UPDATE game_state SET last_decay_date=? WHERE id=1", (today,))
        health_decay_tick()


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
    rows = q("SELECT c.*, u.username, u.qq_number, u.managed FROM consorts c LEFT JOIN users u ON u.id=c.user_id ORDER BY c.user_id IS NULL, c.rank DESC, c.favor DESC")
    pend = q("SELECT * FROM intrigues WHERE status='pending' ORDER BY id")
    reports = q("SELECT * FROM reports WHERE status='open' ORDER BY id")
    done_reports = q("SELECT * FROM reports WHERE status!='open' ORDER BY handled_ts DESC LIMIT 10")
    banned = q("SELECT id, username FROM users WHERE banned=1 ORDER BY id")
    broadcasts = q("""SELECT broadcast_id, MIN(body) body, MIN(silver) silver, MIN(item_key) item_key,
                      COUNT(*) total, SUM(claimed) got, MIN(created_ts) created_ts
                      FROM letters WHERE broadcast_id>0 GROUP BY broadcast_id ORDER BY broadcast_id DESC LIMIT 20""")
    players = q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead') ORDER BY rank DESC")
    families = []
    for fam in q("SELECT f.*, u.username FROM families f LEFT JOIN users u ON u.id=f.user_id ORDER BY f.prestige DESC, f.user_id"):
        ms = [m for m in family_members(fam['user_id']) if m['status'] != 'xiunv']
        families.append(dict(fam=fam, n=len(ms), this_reign=sum(1 for m in ms if m['reign_no'] == state()['reign_no']),
                             alive=[full_name(m) for m in ms if m['user_id'] and m['status'] != 'dead'],
                             head=head_text(fam), label=family_label(fam), tier_name=FAMILIES[fam['tier']]['name']+' · '+fam['background']))
    alerts = list(q("SELECT * FROM alerts ORDER BY resolved, last_ts DESC LIMIT 30"))
    late = settle_overdue_minutes(datetime.now(TZ), state())
    return render_template('admin.html', registrations=q('SELECT id,username,qq_number FROM users ORDER BY id DESC LIMIT 100'), alerts=alerts, open_alerts=sum(1 for a in alerts if not a['resolved']), settle_late=late,
                           alert_webhook=bool(ALERT_WEBHOOK), alert_style=ALERT_STYLE, ts_text=lambda t: datetime.fromtimestamp(t, TZ).strftime('%m-%d %H:%M'),
                           families=families, OFFICE_TITLES=OFFICE_TITLES, emperor_age=emperor_age_years(), rows=rows, pend=pend, get_consort=get_consort, INTRIGUES=INTRIGUES,
                           SECRETS=SECRETS, reports=reports, done_reports=done_reports, banned=banned,
                           broadcasts=broadcasts, players=players, dn=display_name)

@app.route('/admin/emperor', methods=['POST'])
@admin_required
def admin_emperor():
    act = request.form.get('act')
    st = state()
    day = st['day']
    if act == 'start_age':
        try: age = int(request.form.get('age', ''))
        except ValueError: age = 0
        if not 20 <= age <= 70: flash('起始年龄要在 20~70 之间。', 'bad')
        else:
            run('UPDATE game_state SET emperor_start_age=? WHERE id=1', (age,))
            flash(f"这一届皇上的起始年龄改为 {age} 岁（今年 {emperor_age_years(state()):g} 岁）。", 'good')
    elif act == 'ill':
        if st['mourning'] or st['emperor_death_day']: flash('已经在病重或国丧了。', 'bad')
        else:
            fall_emperor_ill(day, day + ILL_DAYS - 1)   # 白天触发：今天起就病重，连今天三天，第三天夜里驾崩
            flash(f"皇上病重，第 {day + ILL_DAYS - 1} 天夜里驾崩。", 'good')
    elif act == 'postpone':
        if not st['emperor_death_day']: flash('皇上没有在病重。', 'bad')
        else:
            run('UPDATE game_state SET emperor_death_day=emperor_death_day+1 WHERE id=1')
            flash('驾崩日往后推了一天。', 'good')
    elif act == 'recover':
        run('UPDATE game_state SET emperor_death_day=0 WHERE id=1')
        gazette('皇上龙体渐愈，太医院上下松了口气。', 'news')
        flash('皇上痊愈了。', 'good')
    elif act == 'end_now':
        if st['mourning']: flash('已经在国丧了。', 'bad')
        else:
            end_reign(day)
            flash('已开匾换届，国丧一日。', 'good')
    elif act == 'skip_mourning':
        if not st['mourning']: flash('现在不在国丧。', 'bad')
        else:
            finish_mourning(day, st)
            flash('已跳过国丧，新一届选秀开始。', 'good')
    elif act == 'event_start':
        run("UPDATE game_state SET event_started=1, day=1, reign_no=1, reign_start_day=1, emperor_start_age=20, "
            "emperor_death_day=0, mourning=0, last_settle_date='', era_name='', emperor_name='', emperor_traits='{}', "
            "dowager='', dowager_uid=0 WHERE id=1")
        flash('活动正式开始：已回到第 1 届第 1 天，今晚起照常结算。', 'good')
    elif act == 'event_pause':
        run('UPDATE game_state SET event_started=0 WHERE id=1')
        flash('已暂停：天数、皇上寿数都停在这里，不会再自动结算。', 'good')
    elif act == 'event_resume':
        run('UPDATE game_state SET event_started=1 WHERE id=1')
        flash('已恢复：今晚起照常结算。', 'good')
    elif act == 'maintenance_on':
        with settle_lock:
            run('UPDATE game_state SET maintenance=1 WHERE id=1')
        flash('维护暂停已开启：玩家操作与自动结算已停止，管理员仍可操作。', 'good')
    elif act == 'maintenance_off':
        with settle_lock:
            run('UPDATE game_state SET maintenance=0 WHERE id=1')
        flash('维护暂停已解除：玩家可以继续操作，自动结算恢复；活动计时开关保留原状态。', 'good')
    return redirect(url_for('admin'))

@app.route('/admin/family/<int:uid>', methods=['POST'])
@admin_required
def admin_family(uid):
    fam = family_row(uid)
    if not fam:
        flash('没有这户人家。', 'bad')
        return redirect(url_for('admin'))
    act = request.form.get('act')
    def num(name, lo, hi):
        try: return max(lo, min(hi, int(request.form.get(name, ''))))
        except ValueError: return None
    if act == 'edit':
        prestige, estate = num('prestige', 0, 100000), num('estate', 0, 1000000)
        office, age = num('office', 0, OFFICE_MAX), num('age', 15, 100)
        if None in (prestige, estate, office, age):
            flash('数值有误。', 'bad'); return redirect(url_for('admin'))
        run("UPDATE families SET prestige=?, estate=?, head_office=?, head_age_months=? WHERE user_id=?",
            (prestige, estate, office, age * 12, uid))
        flash(f"已修改{fam['surname']}氏。", 'good')
    elif act == 'head_ill':
        run("UPDATE families SET head_ill_day=? WHERE user_id=?", (0 if fam['head_ill_day'] else cur_day(), uid))
        flash('家主已' + ('痊愈。' if fam['head_ill_day'] else '病倒。'), 'good')
    elif act == 'head_dies':
        head_dies(fam, cur_day())
        flash('家主已病逝，由下一位接掌。', 'good')
    else:
        flash('没有这个操作。', 'bad')
    return redirect(url_for('admin'))

@app.route('/admin/alerts/resolve/<int:aid>', methods=['POST'])
@admin_required
def admin_alert_resolve(aid):
    run("UPDATE alerts SET resolved=1 WHERE id=?", (aid,))
    return redirect(url_for('admin'))


@app.route('/admin/alerts/resolve_all', methods=['POST'])
@admin_required
def admin_alert_resolve_all():
    run("UPDATE alerts SET resolved=1 WHERE resolved=0")
    flash('告警都标成已处理了。', 'good')
    return redirect(url_for('admin'))


@app.route('/admin/alerts/test', methods=['POST'])
@admin_required
def admin_alert_test():
    if not ALERT_WEBHOOK:
        flash('还没配置 ALERT_WEBHOOK，告警只记在这个页面上。配置方法见页面下方的说明。', 'bad')
    else:
        send_alert_webhook('【甄嬛传告警】这是一条测试推送，收到说明告警通道是通的。')
        flash('测试推送已发出，看看群里有没有收到。', 'good')
    return redirect(url_for('admin'))


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
    for field in ('appearance', 'talent', 'scheme', 'virtue', 'health'):    # 五项属性：表单里有就改，空着不动
        raw = (f.get(field) or '').strip()
        if raw:
            try: set_stat(cid, field, int(raw))
            except ValueError:
                flash('属性数值有误。', 'bad')
                return redirect(url_for('admin'))
    # 页面打开期间游戏在继续（晋封、被罚、花银子……），所以只改后台里真正动过的格子，没动的保持库里的最新值
    def changed(field, new, orig_key):
        raw = (f.get(orig_key) or '').strip()
        try: return new != int(raw) if raw else True
        except ValueError: return True
    favor_new = max(0, favor) if changed('favor', favor, 'orig_favor') else c['favor']
    silver_new = max(0, silver) if changed('silver', silver, 'orig_silver') else c['silver']
    rank_new = max(0, min(PLAYER_MAX_RANK, rank)) if changed('rank', rank, 'orig_rank') else c['rank']
    if f.get('orig_status') and f.get('orig_status') == f.get('status'): status = c['status']
    run("UPDATE consorts SET favor=?, silver=?, rank=?, status=? WHERE id=?", (favor_new, silver_new, rank_new, status, cid))
    rank = rank_new
    raw = (f.get('energy') or '').strip()                  # 精力：表单里有就改，空着不动；可以超过日常上限
    if raw:
        try: run("UPDATE consorts SET energy=? WHERE id=?", (max(0, min(99, int(raw))), cid))
        except ValueError:
            flash('精力数值有误。', 'bad')
            return redirect(url_for('admin'))
    if status in ('confined', 'cold') and c['status'] != status:
        run("UPDATE consorts SET status_until_day=? WHERE id=?",
            (cur_day() + (1 if status == 'confined' else COLD_DAYS), cid))
        if status == 'confined': run("UPDATE consorts SET confine_until_ts=? WHERE id=?", (now_ts() + CONFINE_HOURS * 3600, cid))
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
              'bribes', 'afflictions', 'cases', 'case_suspects', 'case_actions', 'stances', 'heir_claims', 'custody_battles',
              'hobby_projects', 'hobby_items', 'displays', 'daily_counters', 'memories', 'gatherings', 'knife_debts',
              'garden_plots', 'garden_stock', 'banquet_entries', 'banquet_invites', 'banquet_gear', 'achievements', 'consorts', 'game_state'):
        run(f"DELETE FROM {t}")
    if request.form.get('keep_users') != '1':
        run("DELETE FROM users")
    run('DELETE FROM reigns'); run('DELETE FROM reign_letters')
    run('UPDATE users SET lethal_ready_day=0, nameless_ready_day=0, forge_used=0')
    init_db()
    try: age = int(request.form.get('start_age', ''))
    except ValueError: age = 0
    if 20 <= age <= 70: run('UPDATE game_state SET emperor_start_age=? WHERE id=1', (age,))
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
    return f"宫历{(day - 1) * AGE_YEARS_PER_DAY + 1}年"


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
        if random.random() >= POISON_SURVIVE[min(1, c['poison_treatment'])] + blessing_survive_bonus(c):
            die(c['id'], '中毒救治无效')
        else:
            run('''UPDATE consorts SET poisoned_day=0, poison_treatment=0,
                   protected_until_day=?, health=MAX(health,35) WHERE id=?''', (day + RESCUE_PROTECT_DAYS, c['id']))
            notify(c['id'], f'你挺过来了。接下来 {RESCUE_PROTECT_DAYS} 天不会再被毒害，好好静养。', 'good')
            night_mark(c['id'], 'rescued')
            gazette(f'{display_name(c)}脱离险境，留宫静养。', 'news')


def ill_digest(kind, text):
    """结算里的染病/病愈/时疫不逐条发公告，攒起来每晚合发一条；非结算时直接发"""
    if not settling():
        gazette({'sick': f'{text}，卧床不起。', 'well': f'{text}病愈，留宫静养。', 'epidemic': '宫里近来时疫流传，人人自危。'}[kind])
        return
    g.ill_digest.setdefault(kind, []).append(text)

def flush_ill_digest():
    d = getattr(g, 'ill_digest', None) or {}
    parts = []
    if d.get('epidemic'): parts.append('宫里近来时疫流传，人人自危')
    if d.get('sick'): parts.append('、'.join(d['sick']) + '，卧床不起')
    if d.get('well'): parts.append('、'.join(d['well']) + '病愈，留宫静养')
    if parts: gazette('昨夜宫中：' + '；'.join(parts) + '。', 'news')
    g.ill_digest = {}

def fall_ill(cid, day, cause):
    c=get_consort(cid)
    if c['status'] in ('dead','xiunv') or c['ill_day'] or c['poisoned_day']: return
    tier=favor_care_tier(c,day)
    treatment=1 if tier=='hot' or c['npc_key'] else 0
    run('UPDATE consorts SET ill_day=?,ill_treatment=?,ill_care=?,weak_days=0,health=MAX(1,health-15) WHERE id=?',(day,treatment,tier,cid))
    cfg=FAVOR_CARE[tier]
    if c['user_id']:
        care='皇上已命太医诊治，免付诊金。' if treatment else f'请在下一次结算前请太医（{treat_cost(c)} 两，可由姐妹代付）。'
        notify(cid,f"你{cause}，体质 -15。{care}本次为{cfg['name']}待遇：治疗后存活率 {int(cfg['survive']*100)}%，未治疗 {int(cfg['untreated']*100)}%；治疗成功需 {cfg['recover_nights']} 次结算康复（福报另有加成）。",'bad')
        guide_tip(cid,'sick','「早请太医，姐妹也能替你垫诊金。」')
    ill_digest('sick', f'{display_name(c)}{cause}')
    night_mark(cid,'ill')


def resolve_illness_crises(day):
    for c in q("SELECT * FROM consorts WHERE status!='dead' AND ill_day>0 AND ill_day<?",(day,)):
        tier=c['ill_care']
        if favor_care_tier(c,day)=='hot':
            tier='hot'
            run("UPDATE consorts SET ill_care='hot',ill_treatment=1 WHERE id=?",(c['id'],))
        cfg=FAVOR_CARE[tier]
        treated=bool(c['ill_treatment']) or tier=='hot'
        if treated and day-c['ill_day']<cfg['recover_nights']:
            notify(c['id'],'太医正在治疗，今晚继续卧床，下一次结算判断康复。','info')
            continue
        chance=min(.995,(cfg['survive'] if treated else cfg['untreated'])+blessing_survive_bonus(c))
        if random.random()>=chance:
            die(c['id'],'病重不治',memorial_reason='病逝')
        else:
            run("UPDATE consorts SET ill_day=0,ill_treatment=0,ill_care='normal',protected_until_day=?,health=MAX(health,?) WHERE id=?",(day+RESCUE_PROTECT_DAYS,cfg['recovery_health'],c['id']))
            if c['user_id']:
                notify(c['id'],f"你的病好了（{cfg['name']}待遇）。接下来 {RESCUE_PROTECT_DAYS} 天静养。",'good')
                night_mark(c['id'],'ill_rescued')
            ill_digest('well', display_name(c))


def illness_onset_tick(day):
    """每晚判定会不会染病：连续体虚、冷宫阴寒、全宫时疫、产后失调"""
    epidemic = day % EPIDEMIC_INTERVAL == 0 and random.random() < EPIDEMIC_CHANCE
    if epidemic: ill_digest('epidemic', '')
    for c in q("SELECT * FROM consorts WHERE status NOT IN ('dead','xiunv')"):
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
            fall_ill(c['id'], day, '染上了时疫'); continue
        if ordinary_illness_chance(c,day)>0 and random.random()<ordinary_illness_chance(c,day):
            fall_ill(c['id'],day,'偶感风寒')


def old_age_tick(day):
    """50 岁起每晚可能寿终；55 岁起每满 5 岁提醒一句；嫔以上寿终按信任追封"""
    for c in q("SELECT * FROM consorts WHERE status!='dead' AND age_months>=?", (OLD_AGE_START,)):
        years_over = (c['age_months'] - OLD_AGE_START) / 12
        p = years_over * OLD_AGE_BASE * (1 - min(BLESSING_OLD_AGE_MAX, c['blessing'] / BLESSING_OLD_AGE_DIV))
        if c['health'] >= 60: p /= 2
        elif c['health'] < 30: p *= 2
        if random.random() < p:
            if c['rank'] >= 5:
                if c['trust'] >= 70 and c['rank'] < PLAYER_MAX_RANK:
                    set_rank(c['id'], c['rank'] + 1, reason_day=day)
                elif c['trust'] >= 40:
                    pool = [w for w in SHI_WORDS if w not in c['title']] or SHI_WORDS
                    run("UPDATE consorts SET title=? WHERE id=?", (c['title'] + random.choice(pool), c['id']))
            add_prestige(c, PRESTIGE_OLD_AGE, f"{full_name(c)}寿终正寝")
            die(c['id'], '寿终')
        elif c['user_id'] and c['age_months'] >= OLD_AGE_REMINDER_START and c['age_months'] % OLD_AGE_REMINDER_STEP == 0:
            notify(c['id'], f"{mama_of(c)['name']}：{mama_of(c)['old']}")


@app.route('/treat/<int:tid>', methods=['POST'])
@login_required
def treat(tid):
    """请太医：本人（禁足、冷宫也行）或姐妹/好感 30 以上的人都能请，谁请谁出银子。中毒、病重都走这个"""
    c, t = g.me, get_consort(tid)
    crisis = 'poison' if t and t['poisoned_day'] else ('ill' if t and t['ill_day'] else None)
    if t and crisis=='ill' and t['status']!='dead' and favor_care_tier(t)=='hot':
        if c['id']==tid or tid in sisters_of(c['id']) or (relation(c['id'],tid) or {'affinity':0})['affinity']>=30:
            run("UPDATE consorts SET ill_care='hot',ill_treatment=1 WHERE id=?",(tid,))
            flash('皇上已命太医免费诊治，无需垫付诊金。','good')
            return redirect(url_for('index' if c['id']==tid else 'social'))
    err = None
    if not t or not crisis or t['status'] == 'dead':
        err = '她现在不需要请太医。'
    elif c['id'] != tid and not (tid in sisters_of(c['id']) or
                                 (relation(c['id'], tid) or {'affinity': 0})['affinity'] >= 30):
        err = '你与她交情不够，要结为姐妹或好感 30 以上才能替她请太医。'
    elif (t['poison_treatment'] if crisis == 'poison' else t['ill_treatment']):
        err = '太医已经在了。'
    elif c['silver'] < treat_cost(t):
        err = f'请太医要 {treat_cost(t)} 两银子。'
    if err:
        flash(err, 'bad')
    else:
        add_silver(c['id'], -treat_cost(t))
        col = 'poison_treatment' if crisis == 'poison' else 'ill_treatment'
        run(f'UPDATE consorts SET {col}=1 WHERE id=?', (tid,))
        if crisis=='poison':
            text='太医来了，九成能救回来，下一次结算见分晓。'
        else:
            cfg=FAVOR_CARE[t['ill_care']]
            text=f"太医来了，{cfg['name']}待遇治疗后基础存活率 {int(cfg['survive']*100)}%，病后第 {cfg['recover_nights']} 次结算判断康复，福报另有加成。"
        if c['id'] != tid:
            notify(tid, f'{display_name(c)}替你请了太医。{text}', 'good')
            add_affinity(c['id'], tid, 5)
            remember(c['id'], tid, 'treat')
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
    ok, why = family_gate(consort_uid(g.me))
    if not ok:
        flash(why, 'bad')
        return redirect(url_for('memorial'))
    # 保留旧角色、皇嗣和事件引用；仅释放账号的一人一角约束。
    run("UPDATE consorts SET user_id=NULL WHERE id=? AND status='dead'", (g.me['id'],))
    return redirect(url_for('create'))


# ── 宫城地图 / 地点 ────────────────────────────────────────────────────────────

PLACES = {
    'home':    dict(name='本宫', actions=['study', 'schemestudy', 'groom', 'rest', 'reflect', 'eyes', 'shoukang']),
    'jingren': dict(name='礼仪堂', actions=['greet', 'palace_work', 'aid', 'chastise']),
    'garden':  dict(name='御花园', actions=['garden']),
    'yangxin': dict(name='养心殿', actions=['seek', 'perform', 'pizhe', 'attend', 'plead']),
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
        dict(key='jingren', name='礼仪堂', area='jingren', url=url_for('place', key='jingren'),
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
    acts = [(k, action_config(c, k)) for k in PLACES[key]['actions'] if c['status'] in ACTIONS[k]['when'] and not (k == 'attend' and not emperor_ill()) and not (k == 'shoukang' and c['patron'] != 'concubine')]
    counts = {k: daily_count(c['id'], k) for k in PLACES[key]['actions']}
    title, desc, extra = PLACES[key]['name'], '', ''
    maid_ev, maid_info, heir_ev, my_heirs, heir_todo, gather_ev = None, None, None, [], 0, None
    if key == 'home':
        roll_maid_event(c)
        roll_heir_event(c)
        c = get_consort(c['id'])
        maid_ev = maid_event_view(c)
        maid_info = dict(n=len(active_maids(c['id'])), quota=maid_quota(c['rank']), errands=len(free_errand_maids(c)))
        heir_ev = heir_event_view(c)
        my_heirs = q("SELECT * FROM heirs WHERE caretaker_id=? AND adult_day=0", (c['id'],))
        heir_todo = sum(1 for h in q("SELECT * FROM heirs WHERE caretaker_id=? AND adult_day>0", (c['id'],))
                        if h['marriage'] == 'choice' or (h['errand'] and not (errand_view(h) or {}).get('approach')))
        gather_ev = gather_view(c)
        title = residence_name(c)
        if c['status'] == 'cold':
            desc = '四面高墙，窗纸破了也没人来补。'
        elif has_residence(c):
            desc = (PALACES[c['palace']]['main'] if c['hall'] == 'main' else '') + HALL_DESCS[c['hall']]
        else:
            desc = '行李暂且收好，等内务府来传话。'
    elif key == 'jingren':
        desc = '每日晨省，宫中新人到此学习礼仪、互相见面。'
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
                           aid_targets=q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status IN ('normal','confined')", (c['id'],)), plead_targets=plead_targets, chastise_targets=chastise_targets(c) if key == 'jingren' else [], plead_p=int(plead_chance(c) * 100),
                           maid_ev=maid_ev, maid_info=maid_info, heir_ev=heir_ev, my_heirs=my_heirs, heir_todo=heir_todo, HEIR_RAISE=HEIR_RAISE, HEIR_GROOM_BEAUTY_LINE=HEIR_GROOM_BEAUTY_LINE, PRENATAL=PRENATAL,
                           DIETS=DIETS, PREGNANCY_DAYS=PREGNANCY_DAYS, diet_costs=diet_costs(c['rank']), repair=repair_state(c), REPAIRS=REPAIRS, PRAY_TIERS=PRAY_TIERS, QUIET_DAYS=QUIET_DAYS,
                           is_quiet=is_quiet(c) if c['status'] in ('normal', 'confined') else False, birth_count=birth_count, CONTRACEPTION_MIN_BIRTHS=CONTRACEPTION_MIN_BIRTHS, open_living=request.args.get('living') == '1',
                           household=palace_household(c['palace']) if key == 'home' and has_residence(c) else [],
                           is_head=has_residence(c) and c['hall'] == 'main' and c['rank'] >= 5,
                           gather_ev=gather_ev, GATHER_THEMES=GATHER_THEMES, active_festival=FESTIVALS.get(active_festival(day)),
                           festival_done=daily_count(c['id'], 'festival'))

# ── 场景 ───────────────────────────────────────────────────────────────────────

def start_scene(cid, key, **ctx):
    run("UPDATE consorts SET pending_scene=? WHERE id=?",
        (json.dumps(dict(key=key, day=cur_day(), **ctx), ensure_ascii=False), cid))
    if not settling():
        g.scene_started = True

def pick_scene(keys):
    """从一组场景里随机挑一个；要某位 NPC 在场的，她不在（死了、进了冷宫、禁足）就不挑"""
    ok = []
    for k in keys:
        npc_key = SCENES[k].get('npc')
        if npc_key:
            npc = q("SELECT status FROM consorts WHERE npc_key=?", (npc_key,), one=True)
            if not npc or npc['status'] != 'normal': continue
        ok.append(k)
    return random.choice(ok) if ok else None

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
            title, lead = '召见', '御前总管引你进了养心殿。皇上放下奏折：'
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
        return f"考校·{prompt['topic']}", '御前总管来传话，皇上要考校' + label + '的功课。' + prompt['ask'].format(h=label), prompt['opts']
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
        elif k in NPC_KEYS:   # NPC 对你的好感（场景里写 huafei=-10 这种），牵连见 change_bond
            for npc, d in change_bond(cid, k, v):
                parts.append(f"{display_name(npc)}记下了这笔账" if d < 0 else f"{display_name(npc)}待你和气了些")
            continue
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
        if sc['key'].startswith('adv_'):
            daily_inc(c['id'], 'adventure')
        if is_exam and not heir:   # 考校场景等到玩家来应对时，孩子已经不在了（比如被讨回、抱走）
            flash('这事已经过去了。', 'info')
            return redirect(url_for('index'))
        if is_exam:
            ok = heir[opt['stat']] + heir['exam_bonus'] + random.randint(0, SCENE_ROLL) >= opt['dc'] + (5 if emperor_traits().get('personality') == 'clever' else 0)   # 聪敏的皇上，考校题更难
            if heir['exam_bonus']: run('UPDATE heirs SET exam_bonus=0 WHERE id=?', (heir['id'],))
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
    # 白天几轮翻牌（1/5/9/13/17 点）不算夜间，但侍寝、有喜也得进报告
    mine = q("SELECT * FROM messages WHERE consort_id=? AND day=? AND (is_night=1 OR text LIKE '敬事房来传话：本轮皇上翻了你的牌子%') ORDER BY id", (c['id'], night))
    edict = next((m for m in mine if m['kind'] == 'edict'), None)
    mine = [m for m in mine if m['kind'] != 'edict']
    news = q("SELECT * FROM gazette WHERE day=? AND (is_night=1 OR kind='birth') AND kind NOT IN ('bed') ORDER BY id", (night,))
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
LETTER_ATTACH_SHIELD = 2   # 入宫不满 2 天不能附银子、道具、雅趣作品，防小号一进宫就把家底转给大号（2026-10-06 从 5 天压到 2）
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
    elif (amt or item or (hobby_item_id and hitem['maker_id'] != c['id'])) and cur_day() - c['entered_day'] < LETTER_ATTACH_SHIELD:
        err = f'入宫不满 {LETTER_ATTACH_SHIELD} 天，只能赠送自己制作的雅趣作品，不能附银子、普通道具或转赠他人作品。'
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
        first_gift_ever = not q("SELECT 1 FROM letters WHERE from_id=? AND hobby_item_id!=0", (c['id'],), one=True)
        history = json.loads(hitem['history'] or '[]') + [{'from': c['id'], 'to': tid, 'day': cur_day()}]
        run('UPDATE hobby_items SET holder_id=?, history=? WHERE id=?', (tid, json.dumps(history, ensure_ascii=False), hitem['id']))
        run('DELETE FROM displays WHERE consort_id=? AND item_id=?', (c['id'], hitem['id']))   # 送出去了，自己寝宫不再摆着
        if first_gift_ever and hitem['maker_id'] == c['id']:
            remember(c['id'], tid, 'first_gift')
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
    flash(f"信已送达{display_name(t)}。" + (f"随信赠送：{extras}，已到账。" if extras else '本次未附赠品。') + (f"好感 +{aff}。" if aff else ''), 'good')
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
    if day - t['entered_day'] < DRUG_NEWCOMER_SHIELD: return '她入宫还不满1天，暂受新人保护。'
    if day - c['entered_day'] < DRUG_NEWCOMER_SHIELD: return '你入宫还不满1天，暂不能下药。'
    if max(t['drugged_until_day'], t['drugged_day'] + DRUGGED_SHIELD if t['drugged_day'] else 0) > day: return '她刚遭过下药，仍在保护期内。'
    if drug == 'lihun' and (t['poisoned_day'] or t['protected_until_day'] >= day): return '她正中毒或刚获救，动不得。'
    if drug == 'chunxin' and t['pregnant_since']: return '她已有喜脉，春信丹用不上。'
    if mid and not any(m['id'] == mid for m in drug_agents(c['id'], t['id'])): return '这名宫人现在不能替你办事。'
    if submitting:
        if c['rank'] < DRUGS[used]['rank']: return '你的位分还使不得这种药。'
        if inv_qty(c['id'], used) < 1: return '手里没有这份药。'
        account = q('SELECT * FROM users WHERE id=?', (c['user_id'],), one=True)
        if account['drug_ready_day'] > day: return f"下药冷却未结束，第{account['drug_ready_day']}天才能再动手。"
        if drug == 'lihun' and account['lethal_ready_day'] > day: return '离魂草的两天冷却还没过。'
        if used == 'wuming' and account['nameless_ready_day'] > day: return '无名的一天冷却还没过。'
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


def affliction(cid,drug,day=None):
    return q("SELECT * FROM afflictions WHERE consort_id=? AND drug=? AND status='active' AND ((expires_ts>0 AND expires_ts>?) OR (expires_ts=0 AND (until_day=0 OR until_day>=?))) ORDER BY id LIMIT 1",(cid,drug,time.time(),cur_day() if day is None else day),one=True)


@atomic
def finish_affliction(a):
    fresh=q('SELECT * FROM afflictions WHERE id=?',(a['id'],),one=True)
    if not fresh or fresh['status']!='active':return
    run("UPDATE afflictions SET status='done' WHERE id=?",(a['id'],))
    c=get_consort(a['consort_id'])
    if c and c['status']!='dead' and a['restore_stat']:
        add_stat(c['id'],a['restore_stat'],a['restore_delta'])
        notify(c['id'],f"{DRUGS[a['drug']]['name']}药效已过，被扣的{STAT_NAMES[a['restore_stat']]}已恢复。",'good')


@atomic
def resolve_realtime_drugs(day):
    for a in q("SELECT * FROM afflictions WHERE status='active' AND drug='chunxin'"):
        due=a['expires_ts'] or get_consort(a['consort_id'])['pregnancy_started_ts']+86400
        if time.time()<due:continue
        c=get_consort(a['consort_id']);punished=c['trust']<50 and c['status']!='dead'
        finish_affliction(a)
        run("UPDATE consorts SET pregnant_since=0,pregnancy_started_ts=0,prenatal='{}' WHERE id=?",(c['id'],))
        if punished:confine(c['id'],1);add_trust(c['id'],-5)
        notify(c['id'],'春信丹造成的假孕被查明，没有孩子出生。'+('皇上疑你欺君，禁足半天、信任-5。' if punished else '皇上相信你是被人所害。'),'bad')
        open_drug_case(q('SELECT * FROM intrigues WHERE id=?',(a['intrigue_id'],),one=True),int(punished))
    for a in q("SELECT * FROM afflictions WHERE status='active' AND drug!='chunxin' AND expires_ts>0 AND expires_ts<=?",(time.time(),)):finish_affliction(a)
    for it in q("SELECT i.* FROM intrigues i WHERE method='drug' AND item_used='wuming' AND status='done' AND result IN ('success','caught','fizzle') AND CASE WHEN resolved_ts>0 THEN resolved_ts ELSE created_ts END<=? AND NOT EXISTS(SELECT 1 FROM cases WHERE intrigue_id=i.id)",(time.time()-86400,)):
        open_drug_case(it,force=True)


def poison_player(cid, day):
    run('UPDATE consorts SET poisoned_day=?, poison_treatment=0, health=MAX(1,health-20) WHERE id=?', (day, cid))
    notify(cid, f'你中毒了，体质 -20。下一次结算前请太医（{treat_cost(get_consort(cid))} 两）：请了九成能活，不请只有三成五。', 'bad')
    gazette(f'{display_name(get_consort(cid))}突然中毒，性命垂危。')
    night_mark(cid, 'poisoned')
    guide_tip(cid, 'poisoned', '「快请太医！这钱不能省，命才是自己的。」')


def open_drug_case(it, punished=0, force=False):
    if it['item_used']=='wuming' and not force:return None
    old = q('SELECT id FROM cases WHERE intrigue_id=?', (it['id'],), one=True)
    if old: return old['id']
    day = cur_day() + (1 if settling() else 0)
    case_id = run('''INSERT INTO cases(day,victim_id,culprit_id,intrigue_id,drug,agent_maid_id,victim_punished,created_ts)
                     VALUES(?,?,?,?,?,?,?,?)''', (day, it['target_id'], it['attacker_id'], it['id'], it['drug'], it['agent_maid_id'], punished, now_ts())).lastrowid
    if it['drug']=='chunxin':run('UPDATE cases SET victim_trust_loss=5 WHERE id=?',(case_id,))
    culprit = get_consort(it['attacker_id'])
    m = get_maid(it['agent_maid_id']) if it['agent_maid_id'] else None
    score = 30 + random.randint(0, 20) + (0 if m else 20)
    if m: score += {'zuijin': -10, 'suizui': 10}.get(m['trait'], 0)
    run('INSERT INTO case_suspects(case_id,consort_id,suspicion) VALUES(?,?,?)', (case_id, culprit['id'], score))
    victim = get_consort(it['target_id'])
    candidates = q("SELECT * FROM consorts WHERE id NOT IN (?,?) AND status NOT IN ('dead','xiunv','cold') AND ?-entered_day>=?",
                   (culprit['id'], victim['id'], day, CASE_NEWCOMER_SHIELD))
    def affinity(c):
        r = relation(c['id'], victim['id'])
        return r['affinity'] if r else 0
    candidates = sorted(candidates, key=lambda c: (affinity(c), abs(c['favor'] - victim['favor'])))
    for c in candidates:
        active = q("SELECT COUNT(*) FROM case_suspects s JOIN cases c ON c.id=s.case_id WHERE s.consort_id=? AND c.status='open'", (c['id'],), one=True)[0]
        recent = q('SELECT COUNT(*) FROM case_suspects s JOIN cases c ON c.id=s.case_id WHERE s.consort_id=? AND c.culprit_id!=? AND c.day>?', (c['id'], c['id'], day-CASE_JOIN_WINDOW), one=True)[0]   # 陪查：3 天内最多 1 次（2026-10-06 从 7 天 2 次压）
        if active >= 2 or recent >= CASE_JOIN_MAX: continue
        run('INSERT INTO case_suspects(case_id,consort_id,suspicion) VALUES(?,?,?)', (case_id, c['id'], min(40, 10+random.randint(0,20)+(10 if affinity(c)<0 else 0))))
        if q('SELECT COUNT(*) FROM case_suspects WHERE case_id=?', (case_id,), one=True)[0] >= 4: break
    suspects = q('SELECT consort_id FROM case_suspects WHERE case_id=?', (case_id,))
    names = '、'.join(display_name(get_consort(s['consort_id'])) for s in suspects)
    gazette(f'{display_name(victim)}出了事，皇上命慎刑司彻查。待查：{names}。', day=day)
    for cid in {victim['id'], *(s['consort_id'] for s in suspects)}:
        notify(cid, f'你被卷进了第 {case_id} 桩案子，请去慎刑司陈情，下一次结算定案。', 'bad')
        guide_tip(cid, 'case', '「案子上了身，别慌。该喊冤喊冤，该打点打点，慎刑司认的是嫌疑，不是脾气。」')
    if eyes_active(victim):
        notify(victim['id'], f'眼线回报：这回下手的是{display_name(culprit)}。')
        run("UPDATE consorts SET culprit_id=? WHERE id=?", (culprit['id'], victim['id']))
    return case_id


def resolve_drug(it):
    it = q('SELECT * FROM intrigues WHERE id=?', (it['id'],), one=True)
    if it['status'] != 'pending': return it['result'], None
    c, t, day = get_consort(it['attacker_id']), get_consort(it['target_id']), cur_day()
    def done(result):
        if result=='fizzle':
            gain_intrigue_influence(it, FIZZLE_INFLUENCE_FRACTION)
        if result=='success':
            gain_intrigue_influence(it)
            cooldown = LETHAL_COOLDOWN if it['drug']=='lihun' else 1
            if c['user_id']:
                run('UPDATE users SET drug_ready_day=MAX(drug_ready_day,?) WHERE id=?',(day+cooldown,c['user_id']))
                if it['drug']=='lihun': run('UPDATE users SET lethal_ready_day=MAX(lethal_ready_day,?) WHERE id=?',(day+cooldown,c['user_id']))
                if it['item_used']=='wuming': run('UPDATE users SET nameless_ready_day=MAX(nameless_ready_day,?) WHERE id=?',(day+1,c['user_id']))
        run("UPDATE intrigues SET status='done', result=?,resolved_ts=? WHERE id=?", (result,time.time(), it['id']))
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
    if t['user_id']: p -= maid_defense(t['id']) + watch_guard(t['id'])
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
    run('UPDATE consorts SET drugged_day=?,drugged_until_day=? WHERE id=?', (day,day+(2 if drug=='lihun' else 1),t['id']))
    hours=DRUGS[drug]['hours']
    aid=run('INSERT INTO afflictions(consort_id,drug,attacker_id,intrigue_id,start_day,until_day,expires_ts) VALUES(?,?,?,?,?,0,?)',
        (t['id'],drug,c['id'],it['id'],day,time.time()+hours*3600 if hours else 0)).lastrowid
    if drug in ('yanzhi','yachan'):
        stat='appearance' if drug=='yanzhi' else 'talent'
        before=t[stat];add_stat(t['id'],stat,-5)
        run('UPDATE afflictions SET restore_stat=?,restore_delta=? WHERE id=?',(stat,before-get_consort(t['id'])[stat],aid))
    elif drug=='hanshui':
        add_stat(t['id'],'health',-10)
        if t['pregnant_since']:
            if inv_qty(t['id'],'antai'):
                inv_add(t['id'],'antai',-1);notify(t['id'],'安胎药保住了胎儿。')
            elif random.random()<.5:
                run('UPDATE consorts SET pregnant_since=0,pregnancy_started_ts=0,postpartum_until=? WHERE id=?',(day+POSTPARTUM_SICK_DAYS,t['id']))
                run("UPDATE afflictions SET status='done' WHERE consort_id=? AND drug='chunxin'",(t['id'],))
                night_mark(t['id'],'miscarriage');notify(t['id'],'寒水散使你小产了。','bad')
            else:notify(t['id'],'寒水散伤了身子，但胎儿暂时保住了。','info')
    elif drug=='lihun': poison_player(t['id'],day)
    elif drug=='chunxin':
        run('UPDATE consorts SET pregnant_since=?,pregnancy_started_ts=? WHERE id=?',(day,time.time(),t['id']))
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
    resolve_realtime_drugs(day)
    for a in q("SELECT * FROM afflictions WHERE status='active' AND expires_ts=0 AND until_day>0 AND until_day<?",(day,)):finish_affliction(a)
    for a in q("SELECT * FROM afflictions WHERE status='active' AND drug='qingsi'"):
        c=get_consort(a['consort_id'])
        if c['status']=='dead':finish_affliction(a);continue
        if a['last_tick_day']==day:continue
        dmg=SLOW_POISON_FIRST if a['ticks']==0 else SLOW_POISON_TICK
        run('UPDATE consorts SET health=MAX(1,health-?) WHERE id=?',(dmg,c['id']))
        run('UPDATE afflictions SET ticks=ticks+1,last_tick_day=? WHERE id=?',(day,a['id']))
        notify(c['id'],f'青丝引发作，体质-{dmg}。','bad')
        if get_consort(c['id'])['health']<=1:      # 元气耗尽：慢毒转成中毒，走生死判定（请太医九成能活，不请只有三成五），同时开案子
            run("UPDATE afflictions SET status='done' WHERE id=?",(a['id'],))
            poison_player(c['id'],day)
            open_drug_case(q('SELECT * FROM intrigues WHERE id=?',(a['intrigue_id'],),one=True))


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
        public['can_appeal'] = can_appeal(g.me, case)
        cases.append(public)
    return render_template('cases.html', cases=cases, APPEAL_SILVER=APPEAL_SILVER)


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
            else: delta=-10; remember(c['id'], tid, 'testify')
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
            reduction=(0 if s['pleaded'] else int(c['trust']*0.2)+(BOND_JINGPIN_CASE if c['user_id'] and bond(c['id'],'jingpin')>=BOND_CLOSE else 0))+(20 if c['npc_key']=='huanghou' else 0)
            run('UPDATE case_suspects SET suspicion=MAX(0,suspicion-?), pleaded=1 WHERE case_id=? AND consort_id=?',(reduction,case['id'],c['id']))
        s=q('SELECT * FROM case_suspects WHERE case_id=? ORDER BY suspicion DESC, consort_id LIMIT 1',(case['id'],),one=True)
        convicted=s['consort_id'] if s and s['suspicion']>=50 else 0
        if convicted:
            c=get_consort(convicted)
            if c['status']!='dead':
                if case['drug']=='lihun': send_to_cold(convicted)
                elif case['drug']=='hanshui':
                    if c['rank']>1: demote_rank(convicted)
                    confine(convicted,3)
                else: confine(convicted,2); cut_favor(convicted,FAVOR_LOSS['convicted'])
                add_trust(convicted,-15)
            gazette(f"慎刑司定案：{display_name(c)}获罪。")
            notify(convicted,'慎刑司将你定罪，信任 -15，并按案情受罚。','bad')
            if convicted==case['culprit_id'] and c['user_id']: bond_caught_huanghou(convicted)
            if convicted==case['culprit_id']:
                m=get_maid(case['agent_maid_id'])
                if m and m['status']=='active': maid_leave(m['id'],'dead','下药案连坐')
                if case['victim_punished']:
                    victim=get_consort(case['victim_id'])
                    if victim['status']=='confined': run("UPDATE consorts SET status='normal',status_until_day=0 WHERE id=?",(victim['id'],))
                    add_trust(victim['id'],case['victim_trust_loss'])
                    notify(victim['id'],'春信丹案查明，退还信任，解除禁足。','good')
        else: gazette(f"慎刑司：第 {case['id']} 桩案子证据不足，暂作悬案。")
        for a in q("SELECT * FROM case_actions WHERE case_id=? AND action='accuse'",(case['id'],)):
            if a['target_id']!=convicted: add_stat(a['consort_id'],'virtue',-3)
        run('UPDATE cases SET status=?,closed_day=?,convicted_id=?,wrongful=? WHERE id=?',('convicted' if convicted else 'unsolved',day,convicted,int(bool(convicted and convicted!=case['culprit_id'])),case['id']))


APPEAL_MIN_DAYS_CLOSED = 3   # 2026-10-06 从 5 压到 3
APPEAL_ENERGY, APPEAL_SILVER = 1, 100
APPEAL_WRONGFUL_BASE, APPEAL_WRONGFUL_PER_SCHEME = 0.55, 0.003
APPEAL_GUILTY_BASE = 0.08          # 真被定了罪的人想翻案脱罪，希望很小
APPEAL_INTERVAL = 3   # 2026-09-28 从 10 压到 5，2026-10-06 再压到 3


def can_appeal(c, case):
    return case['status'] == 'convicted' and case['convicted_id'] and \
        (c['id'] == case['convicted_id'] or c['id'] in sisters_of(case['convicted_id'])) and \
        cur_day() >= case['closed_day'] + APPEAL_MIN_DAYS_CLOSED and cur_day() >= case['appeal_ready_day']


@app.route('/cases/<int:case_id>/appeal', methods=['POST'])
@login_required
def case_appeal(case_id):
    c = g.me
    day = cur_day()
    case = q('SELECT * FROM cases WHERE id=?', (case_id,), one=True)
    err = None
    if not case or not can_appeal(c, case): err = '这桩案子现在翻不了。'
    elif c['energy'] < APPEAL_ENERGY: err = '精力不够了。'
    elif c['silver'] < APPEAL_SILVER: err = f'翻案要托人打点，得 {APPEAL_SILVER} 两。'
    if err:
        flash(err, 'bad'); return redirect(url_for('drug_cases'))
    run('UPDATE consorts SET energy=energy-? WHERE id=?', (APPEAL_ENERGY, c['id']))
    add_silver(c['id'], -APPEAL_SILVER)
    convicted = get_consort(case['convicted_id'])
    name = display_name(convicted)
    wrongful = bool(case['wrongful'])
    p = (APPEAL_WRONGFUL_BASE + c['scheme'] * APPEAL_WRONGFUL_PER_SCHEME) if wrongful else APPEAL_GUILTY_BASE
    if random.random() < min(0.9, p):
        run("UPDATE cases SET status='overturned' WHERE id=?", (case_id,))
        add_trust(convicted['id'], 15)
        if convicted['status'] == 'cold':
            release_from_cold(convicted['id'], '沉冤得雪，')
        elif convicted['status'] == 'confined':
            run("UPDATE consorts SET status='normal', status_until_day=0 WHERE id=?", (convicted['id'],))
            notify(convicted['id'], '慎刑司复查了旧案，禁足解了。', 'good')
        if case['drug'] == 'hanshui' and slot_free(convicted['rank'] + 1, convicted['id']):
            set_rank(convicted['id'], convicted['rank'] + 1)
        gazette(f"慎刑司复查第 {case_id} 桩旧案，还{name}一个清白。", 'decree')
        if wrongful and case['culprit_id'] and case['culprit_id'] != convicted['id']:
            culprit = get_consort(case['culprit_id'])
            if culprit and culprit['status'] not in ('dead', 'cold'):
                cut_favor(culprit['id'], FAVOR_LOSS['case_culprit'])
                add_trust(culprit['id'], -10)
                notify(culprit['id'], f"{name}的旧案翻了出来，苗头渐渐指向你。圣宠 −{FAVOR_LOSS['case_culprit']}，信任 −10。", 'bad')
        flash('翻案成了，慎刑司当众更正了案情。', 'good')
    else:
        run('UPDATE cases SET appeal_ready_day=? WHERE id=?', (day + APPEAL_INTERVAL, case_id))
        flash(f'慎刑司驳回了申诉，说证据不足以推翻原判。{APPEAL_INTERVAL} 天后才能再申。', 'bad')
    return redirect(url_for('drug_cases'))


@app.route('/agents')
@login_required
def agents_page():
    c=g.me
    targets=q("SELECT m.*, c.surname,c.given,c.title,c.rank, c.status AS owner_status FROM maids m JOIN consorts c ON c.id=m.owner_id WHERE m.status='active' AND c.user_id IS NOT NULL AND c.id!=? AND c.status NOT IN ('dead','cold','xiunv') AND ?-c.entered_day>=?",(c['id'],cur_day(),BRIBE_NEWCOMER_SHIELD))
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
        if not m or m['status']!='active' or m['owner_id']==c['id'] or not owner['user_id'] or owner['status'] in ('dead','cold','xiunv') or day-owner['entered_day']<BRIBE_NEWCOMER_SHIELD: err='不能收买这名宫人。'
        elif c['silver']<30: err='要三十两银子。'
        elif daily_count(c['id'],f'bribe:{mid}'): err='今天已打点过她。'
        elif q("SELECT COUNT(*) FROM bribes b JOIN maids m ON m.id=b.maid_id WHERE b.briber_id=? AND b.turned=1 AND m.status='active'", (c['id'],), one=True)[0]>=3: err='你已有三个内应。'
        elif not free_errand_maids(c): err='没有空闲宫人去办差。'
        else:
            take_errand(c); add_silver(c['id'],-30); daily_inc(c['id'],f'bribe:{mid}')
            gain=int((15+c['scheme']*0.15)*{'suizui':1.5,'tancai':1.5,'zhonghou':0.5,'zuijin':0.5}.get(m['trait'],1))
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

# ── 节庆宴会：除夕、上元、中秋，轮着来（万寿节是皇上的生辰，在九点六节 F 里）────────────
FESTIVALS = {
    'reunion':   dict(name='除夕家宴', action_name='守岁', line='除夕家宴，宫里张灯结彩，隐约传来鞭炮声。'),
    'lantern':   dict(name='上元节', action_name='去猜灯谜', line='上元灯会，六宫处处挂满了花灯。'),
    'midautumn': dict(name='中秋节', action_name='赏月家宴', line='中秋家宴，圆月高悬，宫里飘着桂花香。'),
}
FESTIVAL_ORDER = ['reunion', 'lantern', 'midautumn']
FESTIVAL_INTERVAL = 7   # 2026-09-28 从 18 压到 7，配合一届约 13 天
FESTIVAL_FAVOR_RANGE = (6, 12)
FESTIVAL_SISTER_AFFINITY = 3
FESTIVAL_LANTERN_SILVER = 15


def active_festival(day):
    if day <= 0 or day % FESTIVAL_INTERVAL: return None
    return FESTIVAL_ORDER[(day // FESTIVAL_INTERVAL - 1) % len(FESTIVAL_ORDER)]


@app.route('/festival', methods=['POST'])
@login_required
def do_festival():
    c = g.me
    day = cur_day()
    key = active_festival(day)
    if not key or c['status'] not in ('normal', 'confined'):
        flash('今天不是节庆。', 'bad'); return redirect(url_for('place', key='home'))
    if daily_count(c['id'], 'festival'):
        flash('今天已经过节了。', 'bad'); return redirect(url_for('place', key='home'))
    daily_inc(c['id'], 'festival')
    cfg = FESTIVALS[key]
    gain = add_favor(c['id'], random.randint(*FESTIVAL_FAVOR_RANGE))
    parts = [f"圣宠 +{gain}"]
    if key == 'reunion':
        add_stat(c['id'], 'virtue', 2)
        parts.append('德行 +2')
        mates = sisters_of(c['id'])
        for sid in mates:
            s = get_consort(sid)
            if s and s['status'] not in ('dead', 'xiunv'):
                add_affinity(c['id'], sid, FESTIVAL_SISTER_AFFINITY)
                remember(c['id'], sid, 'festival')
        if mates: parts.append('跟姐妹们的好感也涨了些')
    elif key == 'lantern':
        add_silver(c['id'], FESTIVAL_LANTERN_SILVER)
        parts.append(f'灯谜猜中了，得了 {FESTIVAL_LANTERN_SILVER} 两彩头')
    elif key == 'midautumn':
        add_trust(c['id'], 2)
        parts.append('信任 +2')
    flash(f"{cfg['line']}你{cfg['action_name']}。" + '，'.join(parts) + '。', 'good')
    return redirect(url_for('place', key='home'))


# ── 雅趣后半：小聚、人情、节令小事（九点十三节 C/D/E）────────────────────────────

SEASONS = {
    'snow':  dict(name='初雪', flavor='今日初雪，落在殿角的琉璃瓦上，是这一年头一场。'),
    'lotus': dict(name='荷花开', flavor='御花园的荷花开了满池，风一过满是清香。'),
    'qixi':  dict(name='七夕', flavor='七夕这日，宫里的姑娘们都在院里穿针乞巧。'),
    'chrys': dict(name='重阳', flavor='重阳到了，内务府送来了茱萸和菊花酒。'),
}
SEASON_ORDER = ['snow', 'lotus', 'qixi', 'chrys']
SEASON_INTERVAL = 6   # 2026-09-28 从 15 压到 6
SEASON_QUALITY_BONUS = 0.15   # 节令当天成型的作品，品级骰子多这么些，只影响文案和展示，不影响数值


def active_season(day):
    if day <= 0 or day % SEASON_INTERVAL: return None
    return SEASON_ORDER[(day // SEASON_INTERVAL - 1) % len(SEASON_ORDER)]


GATHER_THEMES = {
    'chat': dict(name='清谈', verb='请她清谈几句'),
    'probe': dict(name='探口风', verb='请她坐下探探口风'),
}
GATHER_HOST_DAILY_MAX = 1
GATHER_GUEST_DAILY_MAX = 2
GATHER_PROBE_HIT = 0.45          # 探口风探出点什么的概率；探出来的话也不一定可信
GATHER_PROBE_RELIABLE = 0.55


def hobby_can_gather(c):
    return bool(hobby_unlocked_kinds(c)) or q('SELECT 1 FROM hobby_items WHERE maker_id=?', (c['id'],), one=True)


def pending_gathering(c):
    return q("SELECT * FROM gatherings WHERE guest_id=? AND day=? AND status='pending' ORDER BY id",
             (c['id'], cur_day()), one=True)


@app.route('/hobby/gather', methods=['POST'])
@login_required
def hobby_gather():
    c = g.me
    theme = request.form.get('theme')
    try:
        gids = [int(x) for x in request.form.getlist('guest_id') if x]
    except ValueError:
        gids = []
    gids = gids[:2]
    err = None
    if not hobby_can_gather(c): err = '你还没有雅趣上的门道，先做一件东西再说。'
    elif theme not in GATHER_THEMES: err = '选一个由头。'
    elif not gids: err = '请一两位一起。'
    elif c['status'] not in ('normal', 'confined'): err = '你现在张罗不了这个。'
    elif daily_count(c['id'], 'gather_host') >= GATHER_HOST_DAILY_MAX: err = '今天已经张罗过一场了。'
    if err:
        flash(err, 'bad'); return redirect(url_for('hobby'))
    day = cur_day()
    sent = 0
    for gid in gids:
        guest = get_consort(gid)
        if not guest or guest['id'] == c['id'] or not guest['user_id'] or guest['status'] not in ('normal', 'confined'): continue
        run("INSERT INTO gatherings (host_id, guest_id, theme, day, status) VALUES (?,?,?,?,'pending')", (c['id'], gid, theme, day))
        sent += 1
    if not sent:
        flash('请的人现在都不方便。', 'bad'); return redirect(url_for('hobby'))
    daily_inc(c['id'], 'gather_host')
    season = active_season(day)
    extra = f"（今日{SEASONS[season]['name']}，倒是个由头）" if season else ''
    flash(f"你请了 {sent} 位来{GATHER_THEMES[theme]['verb']}{extra}，她们今天上线时会看到。", 'good')
    return redirect(url_for('hobby'))


def gather_view(c):
    g_ = pending_gathering(c)
    if not g_: return None
    host = get_consort(g_['host_id'])
    if not host or host['status'] not in ('normal', 'confined'): return None
    line = memory_line(c['id'], g_['host_id'])
    prefix = f"（{line}）" if line else ''
    season = active_season(cur_day())
    season_line = f"（{SEASONS[season]['flavor']}）" if season else ''
    text = f"{prefix}{display_name(host)}请你{GATHER_THEMES[g_['theme']]['verb']}。{season_line}"
    return text, g_


@app.route('/hobby/gather/respond', methods=['POST'])
@login_required
def hobby_gather_respond():
    c = g.me
    view = gather_view(c)
    if not view:
        return redirect(url_for('place', key='home'))
    _, g_ = view
    if daily_count(c['id'], 'gather_guest') >= GATHER_GUEST_DAILY_MAX:
        run("UPDATE gatherings SET status='lapsed' WHERE id=?", (g_['id'],))
        flash('今天已经赴过两场了，这场只好错过。', 'bad')
        return redirect(url_for('place', key='home'))
    opt = request.form.get('opt')
    run("UPDATE gatherings SET status='done' WHERE id=?", (g_['id'],))
    daily_inc(c['id'], 'gather_guest')
    host = get_consort(g_['host_id'])
    if g_['theme'] == 'chat':
        gain = random.randint(6, 8) if opt == 'warm' else random.randint(4, 6)
        add_affinity(c['id'], g_['host_id'], gain)
        say = '你敞开了聊，两人越说越投机。' if opt == 'warm' else '你只静静听着，偶尔应一声，她倒也不介意。'
        flash(f"{say}好感 +{gain}。", 'good')
    else:   # probe
        if opt == 'press' and random.random() < GATHER_PROBE_HIT:
            reliable = random.random() < GATHER_PROBE_RELIABLE
            others = [x['id'] for x in q("SELECT id FROM consorts WHERE user_id IS NOT NULL AND status='normal' AND id NOT IN (?,?)", (c['id'], g_['host_id']))]
            if others:
                who = random.choice(others)
                hint = f"你隐约觉得该多留意{display_name(get_consort(who))}。" if reliable else f"她话里话外像是在提{display_name(get_consort(who))}，只是听着也不一定作数。"
            else:
                hint = '她欲言又止，到底没说出口。'
            add_affinity(c['id'], g_['host_id'], 2)
            flash(f"你多问了两句。{hint}", 'good')
        elif opt == 'press':
            add_affinity(c['id'], g_['host_id'], 1)
            flash('你多问了两句，她只是笑笑，什么也没说破。', 'info')
        else:
            add_affinity(c['id'], g_['host_id'], 3)
            flash('你含糊带过，没有追问。她倒松了口气。', 'good')
    return redirect(url_for('place', key='home'))


def hobby_charge(c):
    """雅趣统一免费，每日打理次数由 daily_counters 的 hobby 计数管理（HOBBY_DAILY_MAX）。"""
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
    day = cur_day()
    others = q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status IN ('normal','confined') AND id!=?", (c['id'],))
    season = active_season(day)
    return render_template('hobby.html', c=c, HOBBIES=HOBBIES, proj=proj, unlocked=unlocked,
                           can_pick_first=not unlocked, can_unlock_second=len(unlocked) == 1 and made >= HOBBY_UNLOCK_ITEMS,
                           done_today=proj is not None and daily_count(c['id'], 'hobby') >= HOBBY_DAILY_MAX,
                           held=held, displayed_ids=displayed_ids, DISPLAY_SLOTS=DISPLAY_SLOTS,
                           hobby_item_desc=hobby_item_desc, free=HOBBY_ENERGY == 0,
                           GATHER_THEMES=GATHER_THEMES, others=others, can_gather=hobby_can_gather(c),
                           gather_left=GATHER_HOST_DAILY_MAX - daily_count(c['id'], 'gather_host'),
                           season=SEASONS[season] if season else None, dn=display_name)

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
        if daily_count(c['id'], 'hobby') >= HOBBY_DAILY_MAX: raise Reject(f'今天已经打理过 {HOBBY_DAILY_MAX} 次了，明天再来。')
        hobby_charge(c)
        daily_inc(c['id'], 'hobby')
        cfg = HOBBIES[proj['kind']]
        stage = proj['stage'] + 1
        if stage >= len(cfg['texts']) - 1:
            item_id = run("""INSERT INTO hobby_items (kind, style, quality, maker_id, holder_id, created_day, history)
                             VALUES (?,?,?,?,?,?,'[]')""",
                          (proj['kind'], proj['style'], roll_hobby_quality(c['id'], proj['kind'], day),
                           c['id'], c['id'], day)).lastrowid
            run("UPDATE hobby_projects SET status='done', stage=?, last_day=? WHERE id=?", (stage, day, proj['id']))
            item = q('SELECT * FROM hobby_items WHERE id=?', (item_id,), one=True)
            season = active_season(day)
            season_line = f"今日{SEASONS[season]['name']}，" if season else ''
            flash(season_line + cfg['texts'][-1].format(style=proj['style']) + f"（{item['quality']}）——去下面看看，摆进寝宫或是送给谁。", 'good')
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



# ── 菜园 · 新年宴会 · 每日差事（2026-10-05 新增）────────────────────────────────────
# 菜园按真实时间长，不等结算；新年宴会每晚 22 点开席，报节目要练才艺熟练度（arts 里的修习次数就是熟练度）；
# 每日差事每人每天 4 件，进度直接数 daily_counters。

CROPS = {
    'qingcai': dict(name='青菜',  seed=5,  hours=2,  yield_=3, sell=3,  desc='长得最快，几乎不赚，胜在顺手。'),
    'luobo':   dict(name='萝卜',  seed=10, hours=4,  yield_=3, sell=6,  desc='脆生生的，四个时辰一茬。'),
    'baicai':  dict(name='白菜',  seed=15, hours=6,  yield_=4, sell=8,  desc='菜园里的中坚，一茬四棵。'),
    'nangua':  dict(name='南瓜',  seed=25, hours=8,  yield_=4, sell=12, desc='长得慢，一个顶好几个。'),
    'lingzhi': dict(name='灵芝',  seed=60, hours=12, yield_=3, sell=35, desc='内务府都抢着收的稀罕物。'),
}
GARDEN_BASE_PLOTS, GARDEN_MAX_PLOTS = 3, 6
GARDEN_PLOT_PRICE = {4: 100, 5: 200, 6: 400}
GARDEN_WATER_CUT = 0.25            # 浇一次水，剩下的时间减 25%，每茬只能浇一次
GARDEN_GIFT_AFFINITY = 4
GARDEN_GIFT_DAILY_MAX = 3
GARDEN_TRIBUTE_FAVOR = (3, 6)      # 进献给皇上，每天一次
TRIBUTE_SAME_ITEM_DAYS = 3         # 同一样东西，这么多个游戏日内不能再进献
TRIBUTE_FATIGUE_DAYS = 5           # 看最近这么多天里（不含今天）进献了几天
TRIBUTE_FATIGUE_STEP = 0.2         # 每多一天，圣宠收益打 8 折、6 折……
TRIBUTE_FATIGUE_FLOOR = 0.4        # 最低打到 4 折


def tribute_factor(cid):
    n = q("SELECT COUNT(*) n FROM daily_counters WHERE consort_id=? AND key='g_tribute' AND day<? AND day>=?",
          (cid, cur_day(), cur_day() - TRIBUTE_FATIGUE_DAYS), one=True)['n']
    return max(TRIBUTE_FATIGUE_FLOOR, 1 - TRIBUTE_FATIGUE_STEP * n)

# ── 厨房：把收下来的菜做成吃食。吃食存在同一张 garden_stock 里，键名加 d_ 前缀 ──
# needs：用掉的食材；eat：自己吃的效果（energy 精力 / health 体质 / buff 今晚宴会加分，要先报了节目）；
# gift：送人的好感；tribute：进献皇上的圣宠区间；sell：卖价
DISHES = {
    'qingchao': dict(name='清炒时蔬', needs={'qingcai': 3}, eat=dict(energy=1), gift=6, tribute=(5, 8), sell=14,
                     desc='最简单的一盘，吃下去精神一振。'),
    'luobogao': dict(name='萝卜糕', needs={'luobo': 3, 'qingcai': 1}, eat=dict(health=5), gift=8, tribute=(6, 10), sell=28,
                     desc='软糯清甜，补身子。'),
    'baicaijiao': dict(name='白菜饺子', needs={'baicai': 3}, eat=dict(energy=2), gift=10, tribute=(8, 12), sell=36,
                       desc='皮薄馅大，一碟下去精力足。'),
    'nangua_geng': dict(name='南瓜羹', needs={'nangua': 2}, eat=dict(buff=6), gift=10, tribute=(10, 15), sell=45,
                        desc='暖胃润嗓，宴前喝一碗，台上更稳（宴会得分 +6，要先报节目）。'),
    'babao': dict(name='八宝菜', needs={'qingcai': 1, 'luobo': 1, 'baicai': 1, 'nangua': 1}, eat=dict(energy=3), gift=12, tribute=(12, 18), sell=60,
                  desc='四样菜合炒，一盘顶三顿。'),
    'lingzhitang': dict(name='灵芝炖汤', needs={'lingzhi': 1, 'baicai': 1}, eat=dict(health=5, buff=10), gift=15, tribute=(15, 22), sell=90,
                        desc='大补之物：体质 +15，宴会得分 +10（要先报节目）。'),
}
COOK_DAILY_MAX = 5
EAT_DAILY_MAX = 1      # 每天所有吃食加起来只能吃一回（原 3 回）
BANQUET_BUFF_CAP = 16


def dish_key(k): return 'd_' + k


def produce_cfg(key):
    """库里的东西：生菜或吃食，统一返回 (名字, 卖价, 送人好感, 进献圣宠区间)"""
    if key in CROPS:
        cfg = CROPS[key]
        return dict(name=cfg['name'], sell=cfg['sell'], gift=GARDEN_GIFT_AFFINITY, tribute=GARDEN_TRIBUTE_FAVOR, dish=False)
    if key.startswith('d_') and key[2:] in DISHES:
        d = DISHES[key[2:]]
        return dict(name=d['name'], sell=d['sell'], gift=d['gift'], tribute=d['tribute'], dish=True)
    return None



def garden_plots_of(c):
    rows = {r['slot']: r for r in q("SELECT * FROM garden_plots WHERE consort_id=?", (c['id'],))}
    now = now_ts()
    out = []
    for slot in range(1, c['garden_plots'] + 1):
        r = rows.get(slot)
        if not r:
            out.append(dict(slot=slot, crop=None)); continue
        left = max(0, r['ready_ts'] - now)
        out.append(dict(slot=slot, crop=r['crop'], cfg=CROPS[r['crop']], watered=r['watered'], ready=left == 0,
                        left_min=-(-left // 60), pct=int(100 * min(1, (now - r['planted_ts']) / max(1, r['ready_ts'] - r['planted_ts'])))))
    return out


def stock_of(cid):
    return {r['crop']: r['qty'] for r in q("SELECT * FROM garden_stock WHERE consort_id=? AND qty>0", (cid,))}


def stock_add(cid, crop, n):
    run("""INSERT INTO garden_stock (consort_id, crop, qty) VALUES (?,?,?)
           ON CONFLICT(consort_id, crop) DO UPDATE SET qty=qty+?""", (cid, crop, n, n))
    run("DELETE FROM garden_stock WHERE qty<=0")


def _garden_guard(c):
    if c['status'] == 'cold': raise Reject('冷宫里没有地可种。')
    if c['status'] == 'dead': raise Reject('这个人已经不在了。')


def _garden_redirect(): return redirect(url_for('garden'))


@app.route('/garden')
@login_required
def garden():
    c = g.me
    inv = stock_of(c['id'])
    others = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status NOT IN ('xiunv','dead','cold')
                  ORDER BY rank DESC, id""", (c['id'],))
    nxt = c['garden_plots'] + 1
    return render_template('garden.html', c=c, plots=garden_plots_of(c), CROPS=CROPS, stock=inv, others=others,
                           DISHES=DISHES, produce_cfg=produce_cfg, TRIBUTE_SAME_ITEM_DAYS=TRIBUTE_SAME_ITEM_DAYS, tribute_now=tribute_factor(c['id']), cooked_today=daily_count(c['id'], 'g_cook'), COOK_DAILY_MAX=COOK_DAILY_MAX,
                           eaten_today=daily_count(c['id'], 'g_eat'), EAT_DAILY_MAX=EAT_DAILY_MAX,
                           next_plot=nxt if nxt <= GARDEN_MAX_PLOTS else None, plot_price=GARDEN_PLOT_PRICE.get(nxt),
                           gifts_left=GARDEN_GIFT_DAILY_MAX - daily_count(c['id'], 'g_gift'),
                           tributed=daily_count(c['id'], 'g_tribute') > 0, GARDEN_WATER_CUT=GARDEN_WATER_CUT,
                           GARDEN_GIFT_AFFINITY=GARDEN_GIFT_AFFINITY, GARDEN_GIFT_DAILY_MAX=GARDEN_GIFT_DAILY_MAX)


GARDEN_TAN_START = date(2026, 10, 8)       # 北京时间这天起，种菜才会掉容貌
GARDEN_TAN_CHANCE, GARDEN_TAN_LOSS = 0.25, 1   # 每次下种有 25% 的概率容貌 -1

def garden_tan_on(now=None):
    return (now or datetime.now(TZ)).date() >= GARDEN_TAN_START


@app.route('/garden/plant', methods=['POST'])
@login_required
def garden_plant():
    c = g.me
    try:
        _garden_guard(c)
        crop, slot = request.form.get('crop'), int(request.form.get('slot', 0) or 0)
        cfg = CROPS.get(crop)
        if not cfg: raise Reject('选一样要种的。')
        if not 1 <= slot <= c['garden_plots']: raise Reject('没有这块地。')
        if q("SELECT 1 FROM garden_plots WHERE consort_id=? AND slot=?", (c['id'], slot), one=True): raise Reject('这块地上已经种着东西了。')
        if c['silver'] < cfg['seed']: raise Reject(f"银子不够，{cfg['name']}的种子要 {cfg['seed']} 两。")
        add_silver(c['id'], -cfg['seed'])
        now = now_ts()
        run("INSERT INTO garden_plots (consort_id, slot, crop, planted_ts, ready_ts) VALUES (?,?,?,?,?)",
            (c['id'], slot, crop, now, now + cfg['hours'] * 3600))
        daily_inc(c['id'], 'g_plant')
        msg = f"{cfg['name']}种下了，{cfg['hours']} 小时后成熟。"
        if garden_tan_on() and c['appearance'] > 0 and random.random() < GARDEN_TAN_CHANCE:
            add_stat(c['id'], 'appearance', -GARDEN_TAN_LOSS)
            msg += f"日头晒了半晌，手上脸上都沾了泥，容貌 -{GARDEN_TAN_LOSS}。"
        flash(msg, 'good')
    except (Reject, ValueError) as e:
        flash(str(e) if isinstance(e, Reject) else '没有这块地。', 'bad')
    return _garden_redirect()


@app.route('/garden/water', methods=['POST'])
@login_required
def garden_water():
    c = g.me
    try:
        _garden_guard(c)
        slot = int(request.form.get('slot', 0) or 0)
        r = q("SELECT * FROM garden_plots WHERE consort_id=? AND slot=?", (c['id'], slot), one=True)
        if not r: raise Reject('这块地上没有东西。')
        now = now_ts()
        if r['ready_ts'] <= now: raise Reject('已经熟了，不用浇了。')
        if r['watered']: raise Reject('这一茬已经浇过水了。')
        cut = int((r['ready_ts'] - now) * GARDEN_WATER_CUT)
        run("UPDATE garden_plots SET ready_ts=ready_ts-?, watered=1 WHERE consort_id=? AND slot=?", (cut, c['id'], slot))
        daily_inc(c['id'], 'g_water')
        flash(f"浇了水，{CROPS[r['crop']]['name']}快了 {max(1, cut // 60)} 分钟。", 'good')
    except (Reject, ValueError) as e:
        flash(str(e) if isinstance(e, Reject) else '没有这块地。', 'bad')
    return _garden_redirect()


@app.route('/garden/harvest', methods=['POST'])
@login_required
def garden_harvest():
    c = g.me
    try:
        _garden_guard(c)
        now = now_ts()
        slot = request.form.get('slot', 'all')
        rows = list(q("SELECT * FROM garden_plots WHERE consort_id=? AND ready_ts<=?", (c['id'], now)))
        if slot != 'all': rows = [r for r in rows if str(r['slot']) == slot]
        if not rows: raise Reject('还没有熟的。')
        got = {}
        for r in rows:
            cfg = CROPS[r['crop']]
            n = cfg['yield_'] + (1 if random.random() < 0.2 else 0)   # 两成的茬多收一棵
            stock_add(c['id'], r['crop'], n)
            got[cfg['name']] = got.get(cfg['name'], 0) + n
            run("DELETE FROM garden_plots WHERE consort_id=? AND slot=?", (c['id'], r['slot']))
            daily_inc(c['id'], 'g_harvest')
        flash('收了：' + '、'.join(f"{k} {v} 棵" for k, v in got.items()) + '。', 'good')
        check_achievements(c['id'])
    except Reject as e:
        flash(str(e), 'bad')
    return _garden_redirect()


GARDEN_SELL_DAILY_CAP = 400      # 每人每个游戏日靠卖生菜、熟菜（吃食）最多赚这么多两


@app.route('/garden/sell', methods=['POST'])
@login_required
def garden_sell():
    c = g.me
    try:
        _garden_guard(c)
        crop = request.form.get('crop')
        have = stock_of(c['id'])
        if crop == 'all': picks = {k: n for k, n in have.items() if k in CROPS}      # 「全卖」只卖生菜，吃食要点名卖
        elif produce_cfg(crop or '') and have.get(crop): picks = {crop: have[crop]}
        else: raise Reject('没有可卖的。')
        if not picks: raise Reject('库里没有可以全卖的生菜。')
        room = GARDEN_SELL_DAILY_CAP - daily_count(c['id'], 'g_sell_silver')
        if room <= 0: raise Reject(f'内务府今天收你的菜已经收满 {GARDEN_SELL_DAILY_CAP} 两了，明天再来。')
        total, left = 0, False
        for k, n in sorted(picks.items(), key=lambda kv: -produce_cfg(kv[0])['sell']):      # 额度不够时先收贵的
            price = produce_cfg(k)['sell']
            take = min(n, room // price)
            if take < n: left = True
            if take <= 0: continue
            stock_add(c['id'], k, -take)
            total += price * take; room -= price * take
        if total <= 0: raise Reject(f'今天还能卖的额度只剩 {room} 两，不够收一件。')
        add_silver(c['id'], total)
        daily_inc(c['id'], 'g_sell_silver', total)
        daily_inc(c['id'], 'g_sell')
        flash(f"内务府收了东西，到手 {total} 两。" + (f"今天卖菜的额度（{GARDEN_SELL_DAILY_CAP} 两）用满了，剩下的留着明天卖。" if left else ''), 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return _garden_redirect()


@app.route('/garden/gift', methods=['POST'])
@login_required
def garden_gift():
    c = g.me
    try:
        _garden_guard(c)
        crop = request.form.get('crop')
        cfg = produce_cfg(crop or '')
        if not cfg or not stock_of(c['id']).get(crop): raise Reject('手里没有这样东西。')
        if daily_count(c['id'], 'g_gift') >= GARDEN_GIFT_DAILY_MAX: raise Reject(f'今天已经送了 {GARDEN_GIFT_DAILY_MAX} 回了。')
        t = pick_target(c)
        if t['status'] == 'cold': raise Reject('冷宫里送不进去。')
        stock_add(c['id'], crop, -1)
        add_affinity(c['id'], t['id'], cfg['gift'])
        daily_inc(c['id'], 'g_gift')
        what = '亲手做的' if cfg['dish'] else '自己种的'
        notify(t['id'], f"{display_name(c)}差人送来一份{what}{cfg['name']}。好感 +{cfg['gift']}。", 'good')
        flash(f"把{cfg['name']}送给了{display_name(t)}。好感 +{cfg['gift']}。", 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return _garden_redirect()


@app.route('/garden/tribute', methods=['POST'])
@login_required
def garden_tribute():
    c = g.me
    try:
        _garden_guard(c)
        if c['status'] != 'normal': raise Reject('现在不是能往养心殿送东西的时候。')
        crop = request.form.get('crop')
        cfg = produce_cfg(crop or '')
        if not cfg or not stock_of(c['id']).get(crop): raise Reject('手里没有这样东西。')
        if daily_count(c['id'], 'g_tribute'): raise Reject('今天已经进献过了。')
        recent = q("SELECT 1 FROM daily_counters WHERE consort_id=? AND key=? AND day>?",
                   (c['id'], 'tribute_item:' + crop, cur_day() - TRIBUTE_SAME_ITEM_DAYS), one=True)
        if recent: raise Reject(f"{cfg['name']}{TRIBUTE_SAME_ITEM_DAYS} 天内已经进献过了，皇上吃腻了，换样别的。")
        stock_add(c['id'], crop, -1)
        daily_inc(c['id'], 'g_tribute')
        daily_inc(c['id'], 'tribute_item:' + crop)
        factor = tribute_factor(c['id'])
        gain = add_favor(c['id'], max(1, round(random.randint(*cfg['tribute']) * factor)))
        line = '皇上尝了一口，点头道「这手艺不错」。' if cfg['dish'] else '皇上尝了一口，笑说「倒有几分野趣」。'
        tired = '皇上近来天天吃你送的东西，兴头淡了些。' if factor < 1 else ''
        flash(f"把{cfg['name']}送进了养心殿，{line}{tired}圣宠 +{gain}。", 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return _garden_redirect()


@app.route('/garden/cook', methods=['POST'])
@login_required
def garden_cook():
    c = g.me
    try:
        _garden_guard(c)
        key = request.form.get('dish')
        d = DISHES.get(key)
        if not d: raise Reject('不会做这道菜。')
        if daily_count(c['id'], 'g_cook') >= COOK_DAILY_MAX: raise Reject(f'今天已经做了 {COOK_DAILY_MAX} 道了，歇歇吧。')
        have = stock_of(c['id'])
        lack = [f"{CROPS[k]['name']}×{n}" for k, n in d['needs'].items() if have.get(k, 0) < n]
        if lack: raise Reject('食材不够：还缺 ' + '、'.join(lack) + '。')
        for k, n in d['needs'].items(): stock_add(c['id'], k, -n)
        stock_add(c['id'], dish_key(key), 1)
        daily_inc(c['id'], 'g_cook')
        flash(f"{d['name']}做好了，收进了库里。", 'good')
        check_achievements(c['id'])
    except Reject as e:
        flash(str(e), 'bad')
    return _garden_redirect()


@app.route('/garden/eat', methods=['POST'])
@login_required
def garden_eat():
    c = g.me
    try:
        _garden_guard(c)
        key = request.form.get('dish')
        d = DISHES.get(key or '')
        if not d or not stock_of(c['id']).get(dish_key(key)): raise Reject('手里没有这道菜。')
        if daily_count(c['id'], 'g_eat') >= EAT_DAILY_MAX: raise Reject(f'今天已经吃了 {EAT_DAILY_MAX} 回，再吃要撑着了。')
        eff, parts = d['eat'], []
        entry = None
        if eff.get('buff'):
            entry = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (banquet_date(), c['id']), one=True)
            if not entry: raise Reject('这道菜是宴前吃的，先去「宴会」报个节目。')
            if entry['buff'] >= BANQUET_BUFF_CAP: raise Reject('宴前的小食已经吃够了。')
        stock_add(c['id'], dish_key(key), -1)
        daily_inc(c['id'], 'g_eat')
        if eff.get('energy'):
            run("UPDATE consorts SET energy=MIN(?, energy+?) WHERE id=?", (ENERGY_MAX, eff['energy'], c['id']))
            parts.append(f"精力 +{eff['energy']}")
        if eff.get('health'):
            add_stat(c['id'], 'health', eff['health']); parts.append(f"体质 +{eff['health']}")
        if eff.get('buff'):
            run("UPDATE banquet_entries SET buff=MIN(?, buff+?) WHERE id=?", (BANQUET_BUFF_CAP, eff['buff'], entry['id']))
            parts.append(f"今晚宴会得分 +{eff['buff']}")
        flash(f"你用了一份{d['name']}。" + '，'.join(parts) + '。', 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return _garden_redirect()


@app.route('/garden/expand', methods=['POST'])
@login_required
def garden_expand():
    c = g.me
    try:
        _garden_guard(c)
        nxt = c['garden_plots'] + 1
        price = GARDEN_PLOT_PRICE.get(nxt)
        if not price: raise Reject('地已经开满了。')
        if c['silver'] < price: raise Reject(f'开新地要 {price} 两。')
        add_silver(c['id'], -price)
        run("UPDATE consorts SET garden_plots=? WHERE id=?", (nxt, c['id']))
        flash(f'又辟出一块地，现在共 {nxt} 块。', 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return _garden_redirect()


# ── 才艺熟练度 ─────────────────────────────────────────────────────────────────

ART_LEVELS = [(0, '生疏'), (2, '入门'), (5, '熟练'), (ART_MASTERY, '精通'), (15, '大成')]


def art_level(n):
    name = ART_LEVELS[0][1]
    for th, nm in ART_LEVELS:
        if n >= th: name = nm
    return name


def add_art_xp(c, art, n=1):
    """加熟练度，返回要附在文案后面的话（跨过精通/大成时有）"""
    arts = arts_of(c)
    before = arts.get(art, 0)
    arts[art] = before + n
    run("UPDATE consorts SET arts=? WHERE id=?", (json.dumps(arts, ensure_ascii=False), c['id']))
    for th, nm in ART_LEVELS[1:]:
        if before < th <= arts[art]:
            if nm in ('精通', '大成'): gazette(f"听说{display_name(c)}的{art}已入{nm}之境。")
            return f"你的{art}升到「{nm}」了。"
    return ''


# ── 新年宴会：每晚 22 点开席 ───────────────────────────────────────────────────

BANQUET_HOUR = 22
BANQUET_ENERGY = 1
BANQUET_REHEARSE_MAX = 2
# 节目：(名字, 档次)。档次越高得分加成越大，但熟练度不够（排练一次算 +2）会出岔子扣分
BANQUET_PIECES = {
    '琴': [('《梅花三弄》', 1), ('《平沙落雁》', 2), ('《广陵散》', 3), ('《流水》', 2)],
    '棋': [('对弈一局', 1), ('一局珍珑', 2), ('盲棋连弈', 3), ('双人联棋', 2)],
    '书': [('寿字大书', 1), ('《兰亭序》临本', 2), ('一笔虎', 3), ('飞白体福字', 2)],
    '画': [('即兴写梅', 1), ('《岁朝图》', 2), ('《百鸟朝凤》', 3), ('《千里江山》长卷', 3)],
    '诗': [('新岁贺诗', 1), ('即席联句', 2), ('《守岁》长歌', 3), ('藏头贺岁诗', 1)],
    '舞': [('长袖独舞', 1), ('《飞天》', 2), ('《霓裳羽衣》', 3), ('《踏歌》群舞', 2)],
    '女红': [('亲手缝的福袋', 1), ('双面绣', 2), ('百福图绣屏', 3), ('并蒂莲荷包', 1)],
    '琵琶': [('《春江花月夜》', 1), ('《十面埋伏》', 2), ('《霸王卸甲》', 3), ('《阳春白雪》', 2)],
    '笛子': [('《妆台秋思》', 1), ('《姑苏行》', 2), ('《鹧鸪飞》', 3), ('《喜相逢》', 1)],
}
BANQUET_TIER_MIN = {1: 0, 2: 5, 3: ART_MASTERY}     # 要达到的熟练度
BANQUET_TIER_BONUS = {1: 3, 2: 9, 3: 16}             # 够格的加分
BANQUET_TIER_PENALTY = {1: 0, 2: 6, 3: 14}           # 不够格的扣分
BANQUET_REHEARSE_EFFECT = 2                          # 每排练一次，当作熟练度 +2 来算够不够格
BANQUET_TITLE_MAX = 12
BANQUET_REWARDS = {   # 名次：(圣宠区间, 银子)
    1: ((20, 30), 80), 2: ((12, 18), 40), 3: ((6, 10), 20),
}
BANQUET_JOIN_SILVER = 15       # 参与奖：献了艺但没进前三的人拿这些（2026-10-07 起从 10 提到 15；比第三名的名次奖 20 少一点）；和名次奖不叠加，前三名只拿各自的名次奖
BANQUET_STALE_PER_WIN, BANQUET_STALE_MAX = 4, 16      # 夺过魁的人再献艺容易让人看腻：每夺一次魁，得分暗中 −4，最多 −16（不在界面上提示）
BANQUET_XP = 1          # 献艺本身也算一次练习

# 戏装铺：宴服、头面、道具（按才艺分），买下就是自己的，开席时每类取最好的一件算加分
BANQUET_GEAR = {
    'dress1': dict(name='湖绸舞衣', slot='dress', price=80,  bonus=2),
    'dress2': dict(name='云锦华服', slot='dress', price=200, bonus=4),
    'dress3': dict(name='缂丝华袍', slot='dress', price=500, bonus=6),
    'head1':  dict(name='绒花珠钗', slot='head',  price=60,  bonus=1),
    'head2':  dict(name='点翠头面', slot='head',  price=180, bonus=3),
    'head3':  dict(name='赤金步摇', slot='head',  price=400, bonus=4),
}
BANQUET_PROPS = {   # 才艺：(普通道具, 上等道具)
    '琴': ('松风琴', '焦尾琴'), '棋': ('云子玉棋', '玲珑棋盘'), '书': ('紫毫笔', '端溪砚'), '画': ('狼毫画笔', '青绿颜料'),
    '诗': ('洒金笺', '松烟墨'), '舞': ('长水袖', '银铃脚环'), '女红': ('金线', '苏绣绷架'),
    '琵琶': ('檀木琵琶', '紫檀嵌螺钿琵琶'), '笛子': ('湘妃竹笛', '羊脂白玉笛'),
}
for _art, (_n1, _n2) in BANQUET_PROPS.items():
    BANQUET_GEAR[f'prop_{_art}_1'] = dict(name=_n1, slot='prop', art=_art, price=120, bonus=5)
    BANQUET_GEAR[f'prop_{_art}_2'] = dict(name=_n2, slot='prop', art=_art, price=300, bonus=8)
GEAR_SLOT_NAMES = {'dress': '宴服', 'head': '头面', 'prop': '道具'}

# 合奏：两个人的节目算一队，得分取两人平均，再加默契分
DUET_SYNERGY_DIFF = 8      # 两人献的才艺不同，「珠联璧合」
DUET_SYNERGY_SAME = 5      # 献同一门，「琴瑟和鸣」
DUET_AFFINITY_CAP = 8      # 好感每 8 点 +1 分，最多 +8
DUET_AFFINITY_AFTER = 5    # 合奏完双方好感 +5


def gear_owned(cid):
    return {r['gear_key'] for r in q("SELECT gear_key FROM banquet_gear WHERE consort_id=?", (cid,))}


def gear_bonus(cid, art):
    """每类（宴服、头面、与献艺相配的道具）取最好的一件"""
    best = {}
    for k in gear_owned(cid):
        it = BANQUET_GEAR.get(k)
        if not it or (it['slot'] == 'prop' and it['art'] != art): continue
        best[it['slot']] = max(best.get(it['slot'], 0), it['bonus'])
    return sum(best.values())



def banquet_date(now=None):
    now = now or datetime.now(TZ)
    return (now.date() if now.hour < BANQUET_HOUR else now.date() + timedelta(days=1)).isoformat()


def banquet_score(c, art, rehearsed, tier=1, buff=0):
    """返回 (得分, 是否出岔子)。熟练度够档就加成，不够就扣分，排练能临时补"""
    n = arts_of(c).get(art, 0)
    skill = n + rehearsed * BANQUET_REHEARSE_EFFECT
    ok = skill >= BANQUET_TIER_MIN[tier]
    s = min(n, 15) * 3 + c['talent'] * 0.4 + rehearsed * 8 + random.uniform(0, 20) + buff + gear_bonus(c['id'], art)
    s += BANQUET_TIER_BONUS[tier] if ok else -BANQUET_TIER_PENALTY[tier]
    if art == state()['emperor_pref']: s += 10
    s -= min(BANQUET_STALE_MAX, (c['banquet_wins'] if 'banquet_wins' in c.keys() else 0) * BANQUET_STALE_PER_WIN)
    return round(s, 1), not ok


def banquet_category_factor(count):
    if count==1:return 1.05
    if count>=5:return .90
    if count>=3:return .95
    return 1.0


def banquet_category_counts(entries):
    counts={art:0 for art in ARTS}
    for e in entries:
        c=get_consort(e['consort_id'])
        if c and c['status'] not in ('dead','cold','xiunv'):counts[e['art']]+=1
    return counts


@app.route('/banquet/change',methods=['POST'])
@login_required
def banquet_change():
    c=g.me
    try:
        if c['status']!='normal':raise Reject('现在不能更换节目。')
        date=banquet_date()
        e=q('SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=? AND place IS NULL',(date,c['id']),one=True)
        if not e:raise Reject('当前宴席没有可更换的节目；开席后不能改。')
        art,_,idx=(request.form.get('piece') or '').partition('|')
        if art not in ARTS or not idx.isdigit() or int(idx)>=len(BANQUET_PIECES[art]):raise Reject('选一个有效节目。')
        piece,tier=BANQUET_PIECES[art][int(idx)]
        title=(request.form.get('title') or '').strip()[:BANQUET_TITLE_MAX]
        if title:
            if blocked_hit('banquet_title',title):raise Reject(BLOCKED_MSG)
            piece=title
        changed=art!=e['art'] or piece!=e['piece'] or tier!=e['tier']
        run('UPDATE banquet_entries SET art=?,piece=?,tier=?,rehearsed=? WHERE id=?',(art,piece,tier,0 if changed else e['rehearsed'],e['id']))
        flash('节目已更换；新节目需重新排练，宴前小食和合奏关系保留。' if changed else '节目没有变化，保留已有排练。','good')
    except Reject as exc:flash(str(exc),'bad')
    return redirect(url_for('banquet'))


def banquet_view(c, date):
    mine = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, c['id']), one=True)
    rows = list(q("""SELECT e.*, c.surname, c.given, c.title, c.rank FROM banquet_entries e JOIN consorts c ON c.id=e.consort_id
                     WHERE e.banquet_date=? ORDER BY e.id""", (date,)))
    return mine, rows


@app.route('/banquet')
@login_required
def banquet():
    c = g.me
    now = datetime.now(TZ)
    date = banquet_date(now)
    mine, rows = banquet_view(c, date)
    last = q("SELECT MAX(banquet_date) d FROM banquet_entries WHERE place IS NOT NULL", one=True)['d']
    results = list(q("""SELECT e.*, c.surname, c.given, c.title, c.rank FROM banquet_entries e JOIN consorts c ON c.id=e.consort_id
                        WHERE e.banquet_date=? ORDER BY e.place""", (last,))) if last else []
    invites = list(q("""SELECT i.*, c.surname, c.given FROM banquet_invites i JOIN consorts c ON c.id=i.from_id
                        WHERE i.banquet_date=? AND i.to_id=? AND i.status='pending'""", (date, c['id'])))
    partner = get_consort(mine['partner_id']) if mine and mine['partner_id'] else None
    others = q("""SELECT * FROM consorts WHERE user_id IS NOT NULL AND id!=? AND status='normal' ORDER BY rank DESC, id""", (c['id'],))
    owned = gear_owned(c['id'])
    hist = q("SELECT COUNT(*) n, SUM(place=1) w, MIN(place) best FROM banquet_entries WHERE consort_id=? AND place IS NOT NULL", (c['id'],), one=True)
    return render_template('banquet.html', category_counts=banquet_category_counts(rows), category_factor=banquet_category_factor, c=c, date=date, mine=mine, rows=rows, results=results, last_date=last, hist=hist,
                           invites=invites, partner=partner, others=others, owned=owned, BANQUET_GEAR=BANQUET_GEAR, GEAR_SLOT_NAMES=GEAR_SLOT_NAMES,
                           gear_bonus=gear_bonus, DUET_SYNERGY_DIFF=DUET_SYNERGY_DIFF, DUET_SYNERGY_SAME=DUET_SYNERGY_SAME,
                           BANQUET_PIECES=BANQUET_PIECES, BANQUET_TIER_MIN=BANQUET_TIER_MIN, BANQUET_TIER_BONUS=BANQUET_TIER_BONUS,
                           BANQUET_TITLE_MAX=BANQUET_TITLE_MAX, BANQUET_REHEARSE_EFFECT=BANQUET_REHEARSE_EFFECT,
                           arts=arts_of(c), ARTS=ARTS, art_level=art_level, st=state(), BANQUET_ENERGY=BANQUET_ENERGY,
                           BANQUET_REHEARSE_MAX=BANQUET_REHEARSE_MAX, BANQUET_HOUR=BANQUET_HOUR, BANQUET_REWARDS=BANQUET_REWARDS,
                           tonight=date == now.date().isoformat())


@app.route('/banquet/enter', methods=['POST'])
@login_required
def banquet_enter():
    c = g.me
    try:
        if c['status'] != 'normal': raise Reject('现在不是能赴宴献艺的时候。')
        art, _, idx = (request.form.get('piece') or '').partition('|')
        if art not in ARTS or not idx.isdigit() or int(idx) >= len(BANQUET_PIECES[art]): raise Reject('选一个要献的节目。')
        piece, tier = BANQUET_PIECES[art][int(idx)]
        title = (request.form.get('title') or '').strip()[:BANQUET_TITLE_MAX]
        if title:
            if blocked_hit('banquet_title', title): raise Reject(BLOCKED_MSG)
            piece = title
        date = banquet_date()
        if q("SELECT 1 FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, c['id']), one=True):
            raise Reject('这一晚的节目已经报上去了。')
        if c['energy'] < BANQUET_ENERGY: raise Reject('精力不够了。')
        run('UPDATE consorts SET energy=energy-? WHERE id=?', (BANQUET_ENERGY, c['id']))
        run("INSERT INTO banquet_entries (banquet_date, consort_id, art, piece, tier) VALUES (?,?,?,?,?)", (date, c['id'], art, piece, tier))
        daily_inc(c['id'], 'b_enter')
        n = arts_of(c).get(art, 0)
        warn = f"（这一档要熟练度 {BANQUET_TIER_MIN[tier]}，你现在 {n}，多排练几次能补上）" if n < BANQUET_TIER_MIN[tier] else ''
        flash(f"节目报上去了：{art}·{piece}。{BANQUET_HOUR} 点开席。{warn}", 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('banquet'))


@app.route('/banquet/rehearse', methods=['POST'])
@login_required
def banquet_rehearse():
    c = g.me
    try:
        if c['status'] not in ('normal', 'confined'): raise Reject('现在排练不了。')
        date = banquet_date()
        e = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, c['id']), one=True)
        if not e: raise Reject('还没报节目。')
        if e['rehearsed'] >= BANQUET_REHEARSE_MAX: raise Reject('这个节目已经排练得很熟了。')
        if c['energy'] < 1: raise Reject('精力不够了。')
        run('UPDATE consorts SET energy=energy-1 WHERE id=?', (c['id'],))
        run("UPDATE banquet_entries SET rehearsed=rehearsed+1 WHERE id=?", (e['id'],))
        up = add_art_xp(c, e['art'], 1)
        daily_inc(c['id'], 'b_rehearse')
        flash(f"你把{e['art']}·{e['piece']}又排了一遍，熟练度 +1。{up}", 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('banquet'))


@app.route('/banquet/invite', methods=['POST'])
@login_required
def banquet_invite():
    c = g.me
    try:
        date = banquet_date()
        me_e = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, c['id']), one=True)
        if not me_e: raise Reject('先给自己报个节目，再找人合奏。')
        if me_e['partner_id']: raise Reject('你已经有搭档了。')
        t = pick_target(c)
        if t['status'] != 'normal': raise Reject('她现在不能赴宴。')
        t_e = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, t['id']), one=True)
        if t_e and t_e['partner_id']: raise Reject('她已经有搭档了。')
        if q("SELECT 1 FROM banquet_invites WHERE banquet_date=? AND from_id=? AND to_id=? AND status='pending'", (date, c['id'], t['id']), one=True):
            raise Reject('已经递过邀请了，等她回话。')
        run("INSERT INTO banquet_invites (banquet_date, from_id, to_id) VALUES (?,?,?)", (date, c['id'], t['id']))
        notify(t['id'], f"{display_name(c)}想在新年宴会上与你合奏，去「宴会」看看。", 'info')
        flash(f"邀请递给{display_name(t)}了。她点头之后你们就是一队。", 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('banquet'))


@app.route('/banquet/accept/<int:iid>', methods=['POST'])
@login_required
def banquet_accept(iid):
    c = g.me
    try:
        date = banquet_date()
        inv = q("SELECT * FROM banquet_invites WHERE id=? AND to_id=? AND banquet_date=? AND status='pending'", (iid, c['id'], date), one=True)
        if not inv: raise Reject('这份邀请已经过期了。')
        if c['status'] != 'normal': raise Reject('现在不是能赴宴献艺的时候。')
        host_e = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, inv['from_id']), one=True)
        host = get_consort(inv['from_id'])
        if not host_e or host_e['partner_id'] or not host or host['status'] != 'normal':
            run("UPDATE banquet_invites SET status='void' WHERE id=?", (iid,))
            raise Reject('她已经另有安排了。')
        mine = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, c['id']), one=True)
        if mine and mine['partner_id']: raise Reject('你已经有搭档了。')
        if not mine:
            art, _, idx = (request.form.get('piece') or '').partition('|')
            if art not in ARTS or not idx.isdigit() or int(idx) >= len(BANQUET_PIECES[art]): raise Reject('先选一个你要献的节目。')
            if c['energy'] < BANQUET_ENERGY: raise Reject('精力不够了。')
            piece, tier = BANQUET_PIECES[art][int(idx)]
            run('UPDATE consorts SET energy=energy-? WHERE id=?', (BANQUET_ENERGY, c['id']))
            run("INSERT INTO banquet_entries (banquet_date, consort_id, art, piece, tier) VALUES (?,?,?,?,?)", (date, c['id'], art, piece, tier))
            daily_inc(c['id'], 'b_enter')
        run("UPDATE banquet_entries SET partner_id=? WHERE banquet_date=? AND consort_id=?", (host['id'], date, c['id']))
        run("UPDATE banquet_entries SET partner_id=? WHERE banquet_date=? AND consort_id=?", (c['id'], date, host['id']))
        run("UPDATE banquet_invites SET status='void' WHERE banquet_date=? AND status='pending' AND (from_id IN (?,?) OR to_id IN (?,?))",
            (date, c['id'], host['id'], c['id'], host['id']))
        run("UPDATE banquet_invites SET status='accepted' WHERE id=?", (iid,))
        daily_inc(c['id'], 'b_duet'); daily_inc(host['id'], 'b_duet')
        notify(host['id'], f"{display_name(c)}答应与你合奏了。", 'good')
        flash(f"你与{display_name(host)}结成一队，今晚一起上台。", 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('banquet'))


@app.route('/banquet/decline/<int:iid>', methods=['POST'])
@login_required
def banquet_decline(iid):
    run("UPDATE banquet_invites SET status='declined' WHERE id=? AND to_id=? AND status='pending'", (iid, g.me['id']))
    return redirect(url_for('banquet'))


@app.route('/banquet/solo', methods=['POST'])
@login_required
def banquet_solo():
    c = g.me
    date = banquet_date()
    e = q("SELECT * FROM banquet_entries WHERE banquet_date=? AND consort_id=?", (date, c['id']), one=True)
    if e and e['partner_id']:
        run("UPDATE banquet_entries SET partner_id=0 WHERE banquet_date=? AND consort_id IN (?,?)", (date, c['id'], e['partner_id']))
        notify(e['partner_id'], f"{display_name(c)}退出了合奏，你改为独自献艺。", 'info')
        flash('你退出了合奏，改为独自献艺。', 'info')
    return redirect(url_for('banquet'))


@app.route('/banquet/buy', methods=['POST'])
@login_required
def banquet_buy():
    c = g.me
    try:
        key = request.form.get('gear')
        it = BANQUET_GEAR.get(key or '')
        if not it: raise Reject('铺子里没有这样东西。')
        if c['status'] not in ('normal', 'confined'): raise Reject('现在逛不了铺子。')
        if key in gear_owned(c['id']): raise Reject('已经有了。')
        if c['silver'] < it['price']: raise Reject(f"银子不够，{it['name']}要 {it['price']} 两。")
        add_silver(c['id'], -it['price'])
        run("INSERT INTO banquet_gear (consort_id, gear_key) VALUES (?,?)", (c['id'], key))
        flash(f"买下了{it['name']}，上台时会用上（得分 +{it['bonus']}）。", 'good')
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('banquet'))


def run_banquet(date):
    entries = list(q("SELECT * FROM banquet_entries WHERE banquet_date=? AND place IS NULL ORDER BY id", (date,)))
    mem = {}      # entry id -> (得分, entry, consort, 出岔子)
    for e in entries:
        c = get_consort(e['consort_id'])
        if not c or c['status'] in ('dead', 'cold', 'xiunv'): continue
        sc, stumble = banquet_score(c, e['art'], e['rehearsed'], e['tier'], e['buff'])
        mem[e['id']] = (sc, e, c, stumble)
    # 把互相认了的搭档并成一队，其余单人一队；队里每人各自领赏，名次共用
    by_consort = {m[2]['id']: m for m in mem.values()}
    units, seen = [], set()
    for eid, m in mem.items():
        if eid in seen: continue
        partner = by_consort.get(m[1]['partner_id']) if m[1]['partner_id'] else None
        if partner and partner[1]['partner_id'] == m[2]['id']:
            rel = relation(m[2]['id'], partner[2]['id'])
            aff = max(0, (rel['affinity'] if rel else 0))
            same = m[1]['art'] == partner[1]['art']
            syn = (DUET_SYNERGY_SAME if same else DUET_SYNERGY_DIFF) + min(DUET_AFFINITY_CAP, aff // 8)
            team = round((m[0] + partner[0]) / 2 + syn, 1)
            seen.update((eid, partner[1]['id']))
            units.append(dict(score=team, members=[m, partner], duet=True, word='琴瑟和鸣' if same else '珠联璧合'))
        else:
            seen.add(eid)
            units.append(dict(score=m[0], members=[m], duet=False, word=''))
    category_counts=banquet_category_counts(entries)
    for unit in units:
        factor=sum(banquet_category_factor(category_counts[m[1]['art']]) for m in unit['members'])/len(unit['members'])
        unit['category_factor']=factor
        unit['score']=round(unit['score']*factor,1)
    units.sort(key=lambda u: -u['score'])
    if not units: return
    for place, u in enumerate(units, start=1):
        favor_rng, silver = BANQUET_REWARDS.get(place, (None, BANQUET_JOIN_SILVER))      # 前三名拿名次奖，其余拿参与奖，不叠加
        word = {1: '拔得头筹', 2: '位列第二', 3: '位列第三'}.get(place, f'名列第 {place}')
        stumbled = any(m[3] for m in u['members'])
        for (_, e, c, stumble) in u['members']:
            if u['duet']:
                note = '合奏时出了岔子，没配合好' if stumbled else u['word']
            else:
                note = '台上出了岔子，没练熟' if stumble else ('一气呵成' if e['tier'] >= 2 else '')
            modifier=round((banquet_category_factor(category_counts[e['art']])-1)*100)
            note += f"；同类{category_counts[e['art']]}人，类别调整{modifier:+d}%" + ('，合奏按双方调整平均计算' if u['duet'] else '')
            run("UPDATE banquet_entries SET score=?, place=?, note=? WHERE id=?", (u['score'], place, note, e['id']))
            parts = []
            if favor_rng and c['status'] == 'normal':
                parts.append(f"圣宠 +{add_favor(c['id'], random.randint(*favor_rng))}")
            add_silver(c['id'], silver)
            parts.append(f"赏银 {silver} 两" + ('' if place <= 3 else '（参与奖）'))
            if place == 1: run('UPDATE consorts SET banquet_wins=banquet_wins+1 WHERE id=?', (c['id'],))
            if place == 1 and c['user_id'] and family_row(c['user_id']):
                add_prestige_uid(c['user_id'], 2, '新年宴会夺魁')
                parts.append('名望 +2')
            up = add_art_xp(c, e['art'], BANQUET_XP)
            if u['duet']:
                other = next(m[2] for m in u['members'] if m[2]['id'] != c['id'])
                if c['id'] < other['id']: add_affinity(c['id'], other['id'], DUET_AFFINITY_AFTER)   # 一对人只加一次
                parts.append(f"与{display_name(other)}好感 +{DUET_AFFINITY_AFTER}")
                head = f"新年宴会上你与{display_name(other)}合奏了{e['art']}·{e['piece']}，{word}。"
            else:
                head = f"新年宴会上你献了{e['art']}·{e['piece']}，{word}。"
            notify(c['id'], head + (note + '。' if note else '') + '，'.join(parts) + '。' + up, 'good' if place <= 3 else 'info')
            check_achievements(c['id'])
    top = units[0]
    n = sum(len(u['members']) for u in units)
    if top['duet']:
        a, b2 = top['members'][0], top['members'][1]
        gazette(f"新年宴会：{display_name(a[2])}与{display_name(b2[2])}合奏{a[1]['piece']}，{top['word']}，拔得头筹，共 {n} 人献艺。")
    else:
        m0 = top['members'][0]
        gazette(f"新年宴会：{display_name(m0[2])}以{m0[1]['art']}·{m0[1]['piece']}拔得头筹，共 {n} 人献艺。")


def maybe_banquet(now):
    """22 点开席；每天只开一次，服务重启不会重复。活动没开始/维护中不开（maybe_settle 入口已拦住）"""
    if now.hour < BANQUET_HOUR: return
    today = now.date().isoformat()
    if state()['last_banquet_date'] == today: return
    run('UPDATE game_state SET last_banquet_date=? WHERE id=1', (today,))
    run_banquet(today)


# ── 每日差事 ─────────────────────────────────────────────────────────────────

QUEST_COUNT = 4
QUEST_ALL_BONUS = dict(silver=50, energy=1)
QUEST_POOL = [
    dict(key='study',    text='修习才艺两次',           counter='study',     goal=2, silver=25),
    dict(key='schemestudy', text='读书习谋一次',       counter='schemestudy', goal=1, silver=20),
    dict(key='greet',    text='去礼仪堂请安',           counter='greet',     goal=1, silver=15),
    dict(key='garden',   text='去御花园逛一逛',         counter='garden',    goal=1, silver=15),
    dict(key='visit',    text='串门走动两回',           counter='visit',     goal=2, silver=25),
    dict(key='hobby',    text='打理一次暇趣',           counter='hobby',     goal=1, silver=20),
    dict(key='plant',    text='在菜园里种下两茬',       counter='g_plant',   goal=2, silver=20),
    dict(key='harvest',  text='收获一回菜',             counter='g_harvest', goal=1, silver=20),
    dict(key='water',    text='给菜浇两次水',           counter='g_water',   goal=2, silver=15),
    dict(key='sell',     text='把菜卖一回',             counter='g_sell',    goal=1, silver=15),
    dict(key='cook',     text='下厨做一道菜',           counter='g_cook',    goal=1, silver=25),
    dict(key='gift',     text='送姐妹一份自己种的菜',   counter='g_gift',    goal=1, silver=20),
    dict(key='enter',    text='给新年宴会报个节目',     counter='b_enter',   goal=1, silver=30),
    dict(key='duet',     text='找人合奏一回',           counter='b_duet',    goal=1, silver=35),
    dict(key='rehearse', text='为宴会排练一次',         counter='b_rehearse', goal=1, silver=25),
]
QUEST_BY_KEY = {x['key']: x for x in QUEST_POOL}


def quests_today(c):
    day = cur_day()
    rng = random.Random(f"quest:{c['id']}:{day}")
    picks = rng.sample(QUEST_POOL, QUEST_COUNT)
    out = []
    for p in picks:
        prog = min(p['goal'], daily_count(c['id'], p['counter']))
        out.append(dict(p, progress=prog, done=prog >= p['goal'], claimed=daily_count(c['id'], 'q:' + p['key']) > 0))
    return out


@app.route('/quests')
@login_required
def quests():
    c = g.me
    qs = quests_today(c)
    all_done = all(x['claimed'] for x in qs)
    return render_template('quests.html', c=c, quests=qs, all_done=all_done,
                           bonus_claimed=daily_count(c['id'], 'q:all') > 0, QUEST_ALL_BONUS=QUEST_ALL_BONUS)


@app.route('/quests/claim', methods=['POST'])
@login_required
def quests_claim():
    c = g.me
    key = request.form.get('key')
    qs = quests_today(c)
    try:
        if key == 'all':
            if not all(x['claimed'] for x in qs): raise Reject('四件差事都领完赏才能领这份。')
            if daily_count(c['id'], 'q:all'): raise Reject('今天已经领过了。')
            daily_inc(c['id'], 'q:all')
            add_silver(c['id'], QUEST_ALL_BONUS['silver'])
            run("UPDATE consorts SET energy=MIN(?, energy+?) WHERE id=?", (ENERGY_MAX, QUEST_ALL_BONUS['energy'], c['id']))
            flash(f"今日差事全部办妥，内务府额外赏了 {QUEST_ALL_BONUS['silver']} 两，精力 +{QUEST_ALL_BONUS['energy']}。", 'good')
            check_achievements(c['id'])
        else:
            x = next((x for x in qs if x['key'] == key), None)
            if not x: raise Reject('今天没有这件差事。')
            if not x['done']: raise Reject('还没办完。')
            if x['claimed']: raise Reject('已经领过赏了。')
            daily_inc(c['id'], 'q:' + key)
            add_silver(c['id'], x['silver'])
            flash(f"「{x['text']}」办妥了，赏 {x['silver']} 两。", 'good')
            check_achievements(c['id'])
    except Reject as e:
        flash(str(e), 'bad')
    return redirect(url_for('quests'))




# ── 成就与称号 · 六宫榜单（2026-10-05 新增）──────────────────────────────────────
# 成就按已有数据现算：达成就发赏银、记一笔，称号可以佩戴（consorts.badge），在六宫页、榜单、成就页显示。
# 榜单只摆本届在世的玩家，数据全来自已有记录。

def total_count(cid, key):
    row = q("SELECT COALESCE(SUM(count),0) n FROM daily_counters WHERE consort_id=? AND key=?", (cid, key), one=True)
    return row['n']


def counter_days(cid, key):
    return q("SELECT COUNT(*) n FROM daily_counters WHERE consort_id=? AND key=? AND count>0", (cid, key), one=True)['n']


def _arts_levels(c):
    return sorted(arts_of(c).values(), reverse=True)


def _banquet_n(cid, where):
    return q(f"SELECT COUNT(*) n FROM banquet_entries WHERE consort_id=? AND {where}", (cid,), one=True)['n']


ACHIEVEMENTS = [
    dict(key='g_first',  name='初试锄头',   desc='收获一次菜',               silver=20,  fn=lambda c: (total_count(c['id'], 'g_harvest'), 1)),
    dict(key='g_farm',   name='菜园老把式', desc='累计收获 20 茬',           silver=100, fn=lambda c: (total_count(c['id'], 'g_harvest'), 20)),
    dict(key='g_land',   name='良田六块',   desc='把地开到 6 块',            silver=60,  fn=lambda c: (c['garden_plots'], GARDEN_MAX_PLOTS)),
    dict(key='g_chef',   name='小厨娘',     desc='累计做成 10 道菜',         silver=100, fn=lambda c: (total_count(c['id'], 'g_cook'), 10)),
    dict(key='g_gift',   name='献芹之心',   desc='累计有 5 天进献过皇上',    silver=80,  fn=lambda c: (counter_days(c['id'], 'g_tribute'), 5)),
    dict(key='b_first',  name='初登宴席',   desc='参加一场新年宴会',         silver=20,  fn=lambda c: (_banquet_n(c['id'], 'place IS NOT NULL'), 1)),
    dict(key='b_win',    name='宴会魁首',   desc='在新年宴会上夺魁',         silver=150, fn=lambda c: (_banquet_n(c['id'], 'place=1'), 1)),
    dict(key='b_win3',   name='三度夺魁',   desc='累计夺魁 3 次',            silver=300, fn=lambda c: (_banquet_n(c['id'], 'place=1'), 3)),
    dict(key='b_duet',   name='琴瑟之好',   desc='与姐妹合奏登台一回',       silver=60,  fn=lambda c: (_banquet_n(c['id'], 'place IS NOT NULL AND partner_id>0'), 1)),
    dict(key='b_dress',  name='衣香鬓影',   desc='戏装铺里买够 6 件行头',    silver=100, fn=lambda c: (len(gear_owned(c['id'])), 6)),
    dict(key='a_master', name='一技之长',   desc='某门才艺练到精通',         silver=80,  fn=lambda c: ((_arts_levels(c) or [0])[0], ART_MASTERY)),
    dict(key='a_grand',  name='登峰造极',   desc='某门才艺练到大成',         silver=200, fn=lambda c: ((_arts_levels(c) or [0])[0], 15)),
    dict(key='a_all',    name='多才多艺',   desc='四门才艺都练到熟练',       silver=150, fn=lambda c: (sum(1 for n in _arts_levels(c) if n >= 5), 4)),
    dict(key='q_first',  name='差事头一回', desc='领完一天的全部差事',       silver=20,  fn=lambda c: (counter_days(c['id'], 'q:all'), 1)),
    dict(key='q_week',   name='勤勉差使',   desc='累计 7 天领完全部差事',    silver=100, fn=lambda c: (counter_days(c['id'], 'q:all'), 7)),
    dict(key='adv5',     name='见多识广',   desc='经历 5 件奇遇',            silver=60,  fn=lambda c: (total_count(c['id'], 'adventure'), 5)),
    dict(key='hobby3',   name='雅士',       desc='亲手做成 3 件暇趣作品',    silver=60,  fn=lambda c: (q("SELECT COUNT(*) n FROM hobby_items WHERE maker_id=?", (c['id'],), one=True)['n'], 3)),
    dict(key='schemer',  name='老谋深算',   desc='心计到 70',                silver=100, fn=lambda c: (c['scheme'], 70)),
    dict(key='mother',   name='凤子龙孙',   desc='诞下一位皇嗣',             silver=80,  fn=lambda c: (q("SELECT COUNT(*) n FROM heirs WHERE mother_id=?", (c['id'],), one=True)['n'], 1)),
    dict(key='rank5',    name='位列嫔位',   desc='晋到嫔位',                 silver=100, fn=lambda c: (c['rank'], 5)),
    dict(key='rank6',    name='位列妃位',   desc='晋到妃位',                 silver=200, fn=lambda c: (c['rank'], 6)),
]
ACH_BY_KEY = {a['key']: a for a in ACHIEVEMENTS}


def achievements_owned(cid):
    return {r['key'] for r in q("SELECT key FROM achievements WHERE consort_id=?", (cid,))}


def achievements_progress(c):
    owned = achievements_owned(c['id'])
    out = []
    for a in ACHIEVEMENTS:
        cur, goal = a['fn'](c)
        out.append(dict(a, cur=min(cur, goal), goal=goal, done=cur >= goal, owned=a['key'] in owned))
    return out


def check_achievements(cid):
    """把现在已经达成、还没记下的成就记下并发赏。哪里涨了数据就在哪里调，结算时也会扫一遍"""
    c = get_consort(cid)
    if not c or not c['user_id'] or c['status'] in ('dead', 'xiunv'): return []
    got = []
    for a in achievements_progress(c):
        if a['done'] and not a['owned']:
            run("INSERT OR IGNORE INTO achievements (consort_id, key, ts) VALUES (?,?,?)", (cid, a['key'], now_ts()))
            add_silver(cid, a['silver'])
            notify(cid, f"达成成就「{a['name']}」：{a['desc']}。赏 {a['silver']} 两，称号可以去「成就」页佩戴。", 'good')
            got.append(a['key'])
    return got


def badge_name(c):
    key = c['badge'] if c else ''
    return ACH_BY_KEY[key]['name'] if key in ACH_BY_KEY else ''


@app.route('/achievements')
@login_required
def achievements():
    c = g.me
    check_achievements(c['id'])
    c = get_consort(c['id'])
    prog = achievements_progress(c)
    return render_template('achievements.html', c=c, prog=prog, done_n=sum(1 for a in prog if a['owned']), badge=c['badge'])


@app.route('/achievements/badge', methods=['POST'])
@login_required
def achievements_badge():
    c = g.me
    key = request.form.get('key', '')
    if key == '':
        run("UPDATE consorts SET badge='' WHERE id=?", (c['id'],))
        flash('称号摘下了。', 'info')
    elif key in achievements_owned(c['id']):
        run("UPDATE consorts SET badge=? WHERE id=?", (key, c['id']))
        flash(f"现在佩戴的称号是「{ACH_BY_KEY[key]['name']}」。", 'good')
    else:
        flash('这个称号还没有挣到。', 'bad')
    return redirect(url_for('achievements'))


def _player_rows():
    return list(q("SELECT * FROM consorts WHERE user_id IS NOT NULL AND status NOT IN ('xiunv','dead')"))


def rankings_boards():
    players = _player_rows()
    ids = [p['id'] for p in players]
    wins = {r['consort_id']: r['n'] for r in q("SELECT consort_id, COUNT(*) n FROM banquet_entries WHERE place=1 GROUP BY consort_id")}
    shows = {r['consort_id']: r['n'] for r in q("SELECT consort_id, COUNT(*) n FROM banquet_entries WHERE place IS NOT NULL GROUP BY consort_id")}
    harvest = {r['consort_id']: r['n'] for r in q("SELECT consort_id, SUM(count) n FROM daily_counters WHERE key='g_harvest' GROUP BY consort_id")}
    ach = {r['consort_id']: r['n'] for r in q("SELECT consort_id, COUNT(*) n FROM achievements GROUP BY consort_id")}

    def board(title, unit, valfn, fmt=str):
        rows = sorted(((valfn(p), p) for p in players), key=lambda t: (-t[0], t[1]['id']))
        rows = [(v, p) for v, p in rows if v > 0][:10]
        return dict(title=title, unit=unit, rows=[dict(c=p, value=fmt(v)) for v, p in rows])

    return [
        board('才艺榜', '总熟练度', lambda p: sum(arts_of(p).values())),
        board('宴会榜', '夺魁（登台）', lambda p: wins.get(p['id'], 0) * 1000 + shows.get(p['id'], 0),
              fmt=lambda v: f"{v // 1000} 次（登台 {v % 1000} 场）"),
        # 财富榜已隐藏（2026-10-07），和心计榜一样不公开排名；想恢复就取消下面这行注释
        # board('财富榜', '银子', lambda p: p['silver']),
        board('种菜榜', '累计收获', lambda p: harvest.get(p['id'], 0)),
        board('成就榜', '已得成就', lambda p: ach.get(p['id'], 0)),
        # 心计榜已隐藏（2026-10-07）：心计是暗牌，不公开排名。想恢复就取消下面这行注释
        # board('心计榜', '心计', lambda p: p['scheme']),
    ]


@app.route('/rankings')
@login_required
def rankings():
    return render_template('rankings.html', boards=rankings_boards(), me=g.me, badge_name=badge_name)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=int(os.environ.get('PORT', 5024)))
