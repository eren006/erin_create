import os, json, random, math, time, secrets
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session as S, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "modaya_jidi_secret_2026")
app.permanent_session_lifetime = timedelta(days=30)

DB_PATH    = os.path.join(os.path.dirname(__file__), "modaya.db")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "modaya_admin_888")
TZ         = timezone(timedelta(hours=8))
now_ts     = lambda: int(time.time())
now_str    = lambda: datetime.now(TZ).strftime("%m-%d %H:%M")

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

BASE_SLOTS = 16

def init_db():
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()
    if not db.execute("SELECT 1 FROM base_state WHERE id=1").fetchone():
        db.execute("INSERT INTO base_state (id, day_count, season, morale, last_tick_ts) VALUES (1,1,'初春',60,?)", (now_ts(),))
    for key, amt in INITIAL_RESOURCES.items():
        if not db.execute("SELECT 1 FROM resources WHERE key=?", (key,)).fetchone():
            db.execute("INSERT INTO resources (key, amount) VALUES (?,?)", (key, amt))
    existing_slots = {row[0] for row in db.execute("SELECT slot_index FROM buildings")}
    for i in range(BASE_SLOTS):
        if i not in existing_slots:
            db.execute("INSERT INTO buildings (slot_index, type, level, hp, max_hp, updated_ts) VALUES (?,?,0,0,0,?)",
                       (i, 'empty', now_ts()))
    if not db.execute("SELECT 1 FROM meta WHERE key='patrol_points_today'").fetchone():
        db.execute("INSERT INTO meta (key,value) VALUES ('patrol_points_today','0')")
    if not db.execute("SELECT 1 FROM meta WHERE key='horde_reduction_today'").fetchone():
        db.execute("INSERT INTO meta (key,value) VALUES ('horde_reduction_today','0')")
    if not db.execute("SELECT 1 FROM meta WHERE key='weapon_rd_progress'").fetchone():
        db.execute("INSERT INTO meta (key,value) VALUES ('weapon_rd_progress','0')")
    survivor_cols = {row[1] for row in db.execute("PRAGMA table_info(survivors)")}
    if 'weapon_level' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN weapon_level INTEGER DEFAULT 0")
    if 'gear_level' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN gear_level INTEGER DEFAULT 0")
    if 'wallet' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN wallet INTEGER DEFAULT 0")
        db.execute("UPDATE survivors SET wallet=contribution")
    if 'weapon_type' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN weapon_type TEXT DEFAULT ''")
    if 'weapon_durability' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN weapon_durability INTEGER DEFAULT 0")
    if 'weapon_max_durability' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN weapon_max_durability INTEGER DEFAULT 0")
    for stat_col in ('stat_intelligence', 'stat_strength', 'stat_agility', 'stat_education',
                     'stat_willpower', 'stat_appearance', 'stat_luck'):
        if stat_col not in survivor_cols:
            db.execute(f"ALTER TABLE survivors ADD COLUMN {stat_col} INTEGER DEFAULT 3")
    if 'respawn_count' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN respawn_count INTEGER DEFAULT 0")
    if 'illness' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN illness TEXT DEFAULT ''")
    if 'illness_started_ts' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN illness_started_ts INTEGER DEFAULT 0")
    if 'room_tier' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN room_tier INTEGER DEFAULT 0")
    if 'age_years' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN age_years INTEGER DEFAULT 20")
        db.execute("UPDATE survivors SET age_years=?", (random.randint(18, 25),))
    if 'age_updated_ts' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN age_updated_ts INTEGER DEFAULT 0")
        db.execute("UPDATE survivors SET age_updated_ts=?", (now_ts(),))
    if 'birth_rights' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN birth_rights INTEGER DEFAULT 0")
    if 'happiness' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN happiness INTEGER DEFAULT 70")
    if 'is_depressed' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN is_depressed INTEGER DEFAULT 0")
    if 'infected' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN infected INTEGER DEFAULT 0")
    if 'infected_since_day' not in survivor_cols:
        db.execute("ALTER TABLE survivors ADD COLUMN infected_since_day INTEGER DEFAULT 0")
    expedition_cols = {row[1] for row in db.execute("PRAGMA table_info(expeditions)")}
    if 'map_key' not in expedition_cols:
        db.execute("ALTER TABLE expeditions ADD COLUMN map_key TEXT NOT NULL DEFAULT ''")
    if not db.execute("SELECT 1 FROM map_progress WHERE map_key='suburbs'").fetchone():
        db.execute("INSERT INTO map_progress (map_key, progress, unlocked) VALUES ('suburbs', 0, 1)")
    db.commit()
    db.close()

def get_meta(key, default=None):
    row = q("SELECT value FROM meta WHERE key=?", (key,), one=True)
    return row['value'] if row else default

def set_meta(key, value):
    run("INSERT INTO meta (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")

def daily_count(survivor_id, key):
    row = q("SELECT count FROM daily_counters WHERE survivor_id=? AND key=? AND day=?",
            (survivor_id, key, today_str()), one=True)
    return row['count'] if row else 0

def daily_inc(survivor_id, key, amount=1):
    day = today_str()
    run("""INSERT INTO daily_counters (survivor_id,key,day,count) VALUES (?,?,?,?)
        ON CONFLICT(survivor_id,key,day) DO UPDATE SET count=count+?""",
        (survivor_id, key, day, amount, amount))

# ── 常量配置 ─────────────────────────────────────────────────────────────────────

DAY_SECONDS = int(os.environ.get("DAY_SECONDS", "86400"))  # 现实24小时=游戏1天,可调(大剧情世界观:时间流速不对劲)

MAX_ENERGY = 100
ENERGY_REGEN_SECONDS = int(os.environ.get("ENERGY_REGEN_SECONDS", "60"))  # 每60秒回1点
MAX_HEALTH = 100
BASE_RESOURCE_CAP = 500

AGE_YEAR_SECONDS = int(os.environ.get("AGE_YEAR_SECONDS", str(4 * 3600)))  # 现实4小时=衰老1岁,即现实1天=衰老6年,可调
AGE_ADULT = 18
AGE_MAX = 80  # 到这个年龄自然老死,复用现有死亡/重生机制

ALERT_CLAIM_TIMEOUT_SECONDS = int(os.environ.get("ALERT_CLAIM_TIMEOUT_SECONDS", "1800"))  # 认领超过这么久没处理就自动释放,可调

WATER_PER_SURVIVOR_PER_DAY = 3
FOOD_CLAIM_PRICE = 3  # 每天领一份餐要花的贡献值钱包余额,钱包不够或者食物档次都没库存,都会挨饿

INITIAL_RESOURCES = {
    'raw_potato': 60, 'raw_corn': 40, 'raw_soy': 30, 'raw_cabbage': 25, 'raw_tomato': 0, 'raw_wheat': 0, 'raw_pumpkin': 0,
    'raw_grape': 0, 'raw_apple': 0, 'raw_sugarcane': 0,
    'food_meat': 0, 'food_meal': 0, 'food_feast': 0, 'dish_pie': 0, 'dish_power': 0,
    'water': 250, 'wood': 200, 'metal': 100,
    'medicine': 40, 'ammo': 50, 'research': 0, 'crystal_core': 0, 'blueprint': 0,
    'seed_potato': 15, 'seed_corn': 10, 'seed_soy': 8, 'seed_cabbage': 12, 'seed_tomato': 8, 'seed_wheat': 10,
    'seed_pumpkin': 0, 'seed_herb': 16, 'seed_hay': 20, 'seed_cotton': 12, 'seed_grape': 10, 'seed_apple': 12, 'seed_sugarcane': 10,
    'herb': 0, 'bandage': 10, 'hay': 40, 'wine': 0, 'raw_cotton': 0, 'cloth': 10,
    'flour': 0, 'sugar': 0, 'butter': 0, 'milk': 0,
    'scrap': 0, 'raw_water': 0, 'resonance_core': 0,
}
RESOURCE_NAMES = {
    'raw_potato': '土豆', 'raw_corn': '玉米', 'raw_soy': '大豆', 'raw_cabbage': '白菜', 'raw_tomato': '西红柿',
    'raw_wheat': '小麦', 'raw_pumpkin': '南瓜', 'raw_cotton': '棉花', 'raw_grape': '葡萄', 'raw_apple': '苹果', 'raw_sugarcane': '甘蔗',
    'food_meat': '肉蛋', 'food_meal': '熟食', 'food_feast': '佳肴', 'dish_pie': '苹果派', 'dish_power': '力量拌肉',
    'water': '净水', 'wood': '木材', 'metal': '金属',
    'medicine': '药品', 'ammo': '弹药', 'research': '研究点数',
    'crystal_core': '晶核', 'blueprint': '图纸',
    'seed_potato': '土豆种子', 'seed_corn': '玉米种子', 'seed_soy': '大豆种子', 'seed_cabbage': '白菜种子', 'seed_tomato': '西红柿种子',
    'seed_wheat': '小麦种子', 'seed_pumpkin': '南瓜种子', 'seed_herb': '药草种子', 'seed_hay': '干草种子', 'seed_cotton': '棉花种子',
    'seed_grape': '葡萄种子', 'seed_apple': '苹果种子', 'seed_sugarcane': '甘蔗种子',
    'herb': '药草', 'bandage': '绷带', 'hay': '干草', 'wine': '酒', 'cloth': '布',
    'flour': '面粉', 'sugar': '糖', 'butter': '黄油', 'milk': '牛奶', 'scrap': '废料', 'raw_water': '生水',
    'resonance_core': '共振核心',
    'textbook_intelligence': '智力教材', 'textbook_strength': '力量教材', 'textbook_agility': '敏捷教材',
    'textbook_education': '教育教材', 'textbook_willpower': '意志教材', 'textbook_appearance': '容貌教材',
    'textbook_luck': '幸运教材',
}
SEED_KEYS = ['seed_potato', 'seed_corn', 'seed_soy', 'seed_cabbage', 'seed_tomato', 'seed_wheat', 'seed_pumpkin', 'seed_herb',
             'seed_hay', 'seed_cotton', 'seed_grape', 'seed_apple', 'seed_sugarcane']

LEVEL_CONTRIBUTION_STEP = 50
MAX_SURVIVOR_LEVEL = 10
EQUIP_MAX_LEVEL = 3

def get_survivor_level(contribution):
    return min(MAX_SURVIVOR_LEVEL, 1 + contribution // LEVEL_CONTRIBUTION_STEP)

def age_energy_mult(age_years):
    """年纪大了没那么能干,体力上限打折;18-50 正常,51-65 打9折,66+打75折。"""
    if age_years > 65:
        return 0.75
    if age_years > 50:
        return 0.9
    return 1.0

def get_max_energy(survivor):
    base = MAX_ENERGY + 2 * (get_survivor_level(survivor['contribution']) - 1) + 2 * (survivor['stat_strength'] - STAT_BASE)
    return round(base * age_energy_mult(survivor['age_years']))

def get_level_mult(survivor):
    return 1 + 0.02 * (get_survivor_level(survivor['contribution']) - 1)

def weapon_cost(level):
    return {'metal': 15 * level, 'wood': 10 * level}

def gear_cost(level):
    return {'cloth': 15 * level, 'metal': 5 * level}

STATS = {
    'stat_intelligence': {'name': '智力', 'desc': '加成制作/研究/加工类产出'},
    'stat_strength':     {'name': '力量', 'desc': '提高体力上限,减少战斗受伤,加成种地/畜牧产出'},
    'stat_agility':      {'name': '敏捷', 'desc': '降低外勤受伤概率'},
    'stat_education':    {'name': '教育', 'desc': '加成科技研究和制药效率'},
    'stat_willpower':    {'name': '意志', 'desc': '减轻挨饿受的伤,降低所有行动的体力消耗'},
    'stat_appearance':   {'name': '容貌', 'desc': '加成商队/庆祝的效果'},
    'stat_luck':         {'name': '幸运', 'desc': '所有随机事件的概率往好的方向偏一点'},
}
STAT_BASE = 3
STAT_FREE_POINTS = 10
STAT_MAX = 20

def stat_mult(survivor, stat_key, per_point=0.03):
    """属性高于基准值 3 给正加成,低于给负加成,乘数型效果统一用这个。"""
    return 1 + per_point * (survivor[stat_key] - STAT_BASE)

def parse_stat_allocation(form):
    """注册/重生共用:读表单里的属性点分配,超过 STAT_FREE_POINTS 就返回 None。"""
    stat_values = {}
    allocated = 0
    for key in STATS:
        try:
            v = int(form.get(key, '0') or 0)
        except ValueError:
            v = 0
        v = max(0, v)
        stat_values[key] = v
        allocated += v
    if allocated > STAT_FREE_POINTS:
        return None, allocated
    return stat_values, allocated

def injury_chance_factor(survivor):
    """敏捷降低受伤概率,幸运也顺带降低一点,下限打 3 折封顶不会降到 0。"""
    factor = 1 - 0.05 * (survivor['stat_agility'] - STAT_BASE) - 0.03 * (survivor['stat_luck'] - STAT_BASE)
    return max(0.3, factor)

def strength_damage_reduction(survivor, dmg):
    return max(1, dmg - (survivor['stat_strength'] - STAT_BASE))

def int_discount(survivor):
    """智力高的人制作/加工东西更省料,封顶打 6 折。"""
    return max(0.6, 1 - 0.03 * (survivor['stat_intelligence'] - STAT_BASE))

def maybe_grant_stat_growth(survivor_id, stat_keys, chance=0.06):
    """战斗/外勤类行动小概率永久+1属性(封顶STAT_MAX),对应"通过战斗提升属性"的成长路径。"""
    if random.random() >= chance:
        return None
    stat_key = random.choice(stat_keys)
    row = q(f"SELECT {stat_key} v, name FROM survivors WHERE id=?", (survivor_id,), one=True)
    if not row or row['v'] >= STAT_MAX:
        return None
    run(f"UPDATE survivors SET {stat_key}=? WHERE id=?", (row['v'] + 1, survivor_id))
    log_action(survivor_id, row['name'], '历练', f"实战让{STATS[stat_key]['name']}+1")
    return STATS[stat_key]['name']

SPECIALIZATIONS = {
    'farmer':     {'name': '农夫',     'bonus_action': 'farm',     'mult': 1.2, 'desc': '种地/畜牧产出+20%,种子消耗-17%'},
    'engineer':   {'name': '工程师',   'bonus_action': 'build',    'mult': 1.2, 'desc': '织布产出+20%,建造/升级/维修材料-17%'},
    'sentry':     {'name': '哨兵',     'bonus_action': 'hunt',     'mult': 1.2, 'desc': '组队探索战斗伤害+20%,巡逻/组队探索弹药消耗-17%'},
    'medic':      {'name': '医生',     'bonus_action': 'heal',     'mult': 1.2, 'desc': '治疗效果+20%,药品消耗-17%'},
    'chef':       {'name': '厨师',     'bonus_action': 'cook',     'mult': 1.2, 'desc': '菜谱产出+20%,食材消耗-17%'},
    'scavenger':  {'name': '拾荒者',   'bonus_action': 'scavenge', 'mult': 1.2, 'desc': '采集收获+20%、受伤概率-40%'},
    'armorer':    {'name': '军械师',   'bonus_action': 'armory',   'mult': 1.2, 'desc': '研发进度+20%,武器维修材料-17%'},
    'processor':  {'name': '加工者',   'bonus_action': 'process',  'mult': 1.2, 'desc': '加工产出+20%,原料消耗-17%'},
    'scholar':    {'name': '学者',     'bonus_action': 'study',    'mult': 1.2, 'desc': '编写教材材料-17%'},
}

ENERGY_COSTS = {
    'plant': 15, 'harvest': 10, 'build': 20, 'upgrade': 20,
    'repair': 15, 'patrol': 20, 'scavenge': 25, 'heal': 15,
    'expedition': 40, 'craft': 20, 'cook': 15,
    'hunt': 30, 'craft_medicine': 15, 'purify': 15,
    'draft_blueprint': 25, 'repair_weapon': 15, 'weapon_rd': 20, 'celebrate': 10, 'weave': 20, 'process': 15,
    'demolish': 15, 'retrofit_weapon': 15, 'craft_textbook': 25, 'study': 10, 'play': 10, 'gate_invest': 20,
    'expedition_step': 12,
}

TEXTBOOKS = {
    'stat_intelligence': {'name': '智力教材', 'resource_key': 'textbook_intelligence', 'threshold': 8},
    'stat_strength':     {'name': '力量教材', 'resource_key': 'textbook_strength',     'threshold': 8},
    'stat_agility':      {'name': '敏捷教材', 'resource_key': 'textbook_agility',      'threshold': 8},
    'stat_education':    {'name': '教育教材', 'resource_key': 'textbook_education',    'threshold': 8},
    'stat_willpower':    {'name': '意志教材', 'resource_key': 'textbook_willpower',    'threshold': 8},
    'stat_appearance':   {'name': '容貌教材', 'resource_key': 'textbook_appearance',   'threshold': 8},
    'stat_luck':         {'name': '幸运教材', 'resource_key': 'textbook_luck',         'threshold': 8},
}
TEXTBOOK_COST = {'research': 25, 'wood': 15}

ILLNESSES = {
    'cold':    {'name': '感冒',   'daily_health_drain': 3, 'morale_penalty': 0, 'cure_cost': {'medicine': 4}},
    'stomach': {'name': '肠胃炎', 'daily_health_drain': 5, 'morale_penalty': 1, 'cure_cost': {'medicine': 6}},
    'fever':   {'name': '发热',   'daily_health_drain': 8, 'morale_penalty': 2, 'cure_cost': {'medicine': 9}},
}
ILLNESS_DAILY_CHANCE = 0.05  # 每天 tick 时,健康的幸存者有 5% 概率患上随机小病,需要去诊所治愈

def illness_chance_for_age(age_years):
    """年纪大了更容易生病,和 age_energy_mult 用同一套年龄分段。"""
    if age_years > 65:
        return ILLNESS_DAILY_CHANCE * 2.5
    if age_years > 50:
        return ILLNESS_DAILY_CHANCE * 1.6
    return ILLNESS_DAILY_CHANCE

# 快乐值/抑郁:照抄疾病系统的形状(起病看概率、消退看条件),不需要"治疗"动作,是自愈型
HAPPINESS_DAILY_DECAY = 3        # 每天自然衰减,逼着娱乐设施/礼物/庆祝持续有用,不是建一次就不用管
DEPRESSION_THRESHOLD = 30        # 快乐值低于这个数,每天有概率转入抑郁
DEPRESSION_DAILY_CHANCE = 0.10
DEPRESSION_RECOVERY_THRESHOLD = 50  # 快乐值回升到这个数以上,自动脱离抑郁
DEPRESSION_ENERGY_PENALTY = -25     # 传进 room_energy_regen_seconds 的负数 bonus,体力回复变慢

ROOM_TIERS = {
    0: {'name': '通铺',   'upgrade_cost': None,             'energy_regen_bonus': 0,  'morale_bonus': 0},
    1: {'name': '单人间', 'upgrade_cost': {'wallet': 150},  'energy_regen_bonus': 10, 'morale_bonus': 0},
    2: {'name': '舒适间', 'upgrade_cost': {'wallet': 400},  'energy_regen_bonus': 20, 'morale_bonus': 2},
    3: {'name': '套房',   'upgrade_cost': {'wallet': 900},  'energy_regen_bonus': 35, 'morale_bonus': 4},
}
ROOM_TIER_MAX = max(ROOM_TIERS)

RELATIONSHIP_TIERS = [(0, '陌生人'), (20, '熟人'), (50, '朋友'), (80, '暧昧'), (120, '可表白')]
PROPOSE_AFFINITY_THRESHOLD = 120
MOVE_IN_COST = 300  # 花提议人钱包,双人间(情侣同居)造价
SHARED_ROOM_ENERGY_BONUS = 15  # 百分比,和个人 room_tier 的加成叠加
SHARED_ROOM_MORALE_BONUS = 3   # 每对同居情侣给基地的被动士气加成
BREAKUP_AFFINITY_PENALTY = 30  # 分手扣的好感度
MAIL_GENEROSITY_AFFINITY = 3  # 通过信箱送钱包/装备/家具(非专门的"礼物"道具)给好感度的小额加成

def relationship_tier_name(affinity):
    name = RELATIONSHIP_TIERS[0][1]
    for threshold, label in RELATIONSHIP_TIERS:
        if affinity >= threshold:
            name = label
    return name

BIRTH_RIGHTS_COST = 500  # 花钱包购买生育权,需要房间等级达到套房(ROOM_TIER_MAX)
HAVE_CHILD_COST = 300    # 花发起人钱包生成一次出生邀请码

FURNITURE_TYPES = {
    # 谁都能做,工程师(build)有加成+材料折扣;做完先进自己背包,得去集市上架、别人买了才归买家所有。
    # effect='energy'/'morale' 的家具装进房间后叠加对应加成(和 room_tier/双人间叠加);'deco' 没有机制效果,纯装饰/纯用来卖钱。
    'bed_wood':      {'name': '木板床',     'cost': {'wood': 20, 'scrap': 5},              'effect': 'energy', 'amount': 5},
    'bed_soft':      {'name': '软垫床',     'cost': {'wood': 25, 'cloth': 15, 'scrap': 8}, 'effect': 'energy', 'amount': 10},
    'bed_double':    {'name': '双人床',     'cost': {'wood': 35, 'cloth': 20, 'scrap': 10},'effect': 'energy', 'amount': 14},
    'bunk_bed':      {'name': '上下铺',     'cost': {'wood': 30, 'metal': 10, 'scrap': 10},'effect': 'energy', 'amount': 9},
    'hammock':       {'name': '吊床',       'cost': {'cloth': 20, 'scrap': 6},             'effect': 'energy', 'amount': 7},
    'desk':          {'name': '书桌',       'cost': {'wood': 15, 'metal': 5, 'scrap': 5},  'effect': 'energy', 'amount': 4},
    'armchair':      {'name': '软椅',       'cost': {'wood': 15, 'cloth': 10, 'scrap': 5}, 'effect': 'energy', 'amount': 6},
    'stove_small':   {'name': '小火炉',     'cost': {'metal': 20, 'scrap': 10},            'effect': 'energy', 'amount': 8},
    'bathtub':       {'name': '浴缸',       'cost': {'metal': 30, 'scrap': 15},            'effect': 'energy', 'amount': 12},
    'chair':         {'name': '木椅',       'cost': {'wood': 10, 'scrap': 3},              'effect': 'deco',   'amount': 0},
    'bookshelf':     {'name': '书架',       'cost': {'wood': 20, 'metal': 5, 'scrap': 6},  'effect': 'deco',   'amount': 0},
    'wardrobe':      {'name': '衣柜',       'cost': {'wood': 25, 'metal': 8, 'scrap': 8},  'effect': 'deco',   'amount': 0},
    'mirror':        {'name': '穿衣镜',     'cost': {'metal': 10, 'scrap': 6},             'effect': 'deco',   'amount': 0},
    'clock':         {'name': '挂钟',       'cost': {'metal': 8, 'scrap': 5},              'effect': 'deco',   'amount': 0},
    'vase':          {'name': '花瓶',       'cost': {'metal': 5, 'scrap': 3},              'effect': 'deco',   'amount': 0},
    'photo_frame':   {'name': '相框',       'cost': {'wood': 5, 'scrap': 2},               'effect': 'deco',   'amount': 0},
    'trunk':         {'name': '储物箱',     'cost': {'wood': 15, 'metal': 10, 'scrap': 6}, 'effect': 'deco',   'amount': 0},
    'wall_shelf':    {'name': '置物架',     'cost': {'wood': 10, 'scrap': 4},              'effect': 'deco',   'amount': 0},
    'toy_box':       {'name': '玩具箱',     'cost': {'wood': 8, 'cloth': 5, 'scrap': 3},   'effect': 'deco',   'amount': 0},
    'candle_stand':  {'name': '烛台',       'cost': {'metal': 6, 'scrap': 3},              'effect': 'deco',   'amount': 0},
    'rug':           {'name': '地毯',       'cost': {'cloth': 15, 'scrap': 4},             'effect': 'morale', 'amount': 3},
    'curtain':       {'name': '窗帘',       'cost': {'cloth': 10, 'scrap': 3},             'effect': 'morale', 'amount': 2},
    'lamp_oil':      {'name': '油灯',       'cost': {'metal': 8, 'scrap': 5},              'effect': 'morale', 'amount': 2},
    'lamp_electric': {'name': '电灯',       'cost': {'metal': 15, 'scrap': 10},            'effect': 'morale', 'amount': 4},
    'painting':      {'name': '挂画',       'cost': {'cloth': 5, 'scrap': 4},              'effect': 'morale', 'amount': 2},
    'plant_potted':  {'name': '盆栽',       'cost': {'wood': 5, 'scrap': 3},               'effect': 'morale', 'amount': 2},
    'radio':         {'name': '老式收音机', 'cost': {'metal': 15, 'scrap': 12},            'effect': 'morale', 'amount': 5},
    'fireplace':     {'name': '壁炉',       'cost': {'metal': 25, 'wood': 15, 'scrap': 12},'effect': 'morale', 'amount': 6},
    'record_player': {'name': '唱片机',     'cost': {'metal': 18, 'scrap': 10},            'effect': 'morale', 'amount': 5},
    'wind_chime':    {'name': '风铃',       'cost': {'metal': 5, 'scrap': 3},              'effect': 'morale', 'amount': 1},
}
GIFT_TYPES = {
    # 谁都能做,加工者(process)有加成+材料折扣;做完先进自己背包,得去集市上架、别人买了才能通过信箱送人,
    # 领取到礼物类信箱附件时不进背包,直接把 affinity_bonus 加到送礼人和收礼人之间的好感度上,happiness_bonus 给收礼人的快乐值。
    'wildflower':   {'name': '野花',       'cost': {'scrap': 3},                        'affinity_bonus': 5,  'happiness_bonus': 3},
    'handkerchief': {'name': '手绢',       'cost': {'cloth': 8, 'scrap': 3},            'affinity_bonus': 8,  'happiness_bonus': 4},
    'love_letter':  {'name': '情书',       'cost': {'research': 5, 'scrap': 3},         'affinity_bonus': 10, 'happiness_bonus': 5},
    'carved_charm': {'name': '木雕护身符', 'cost': {'wood': 10, 'scrap': 5},            'affinity_bonus': 12, 'happiness_bonus': 6},
    'perfume':      {'name': '自制香水',   'cost': {'herb': 10, 'scrap': 5},            'affinity_bonus': 15, 'happiness_bonus': 8},
    'photo_locket': {'name': '相片盒坠',   'cost': {'metal': 8, 'cloth': 5, 'scrap': 5},'affinity_bonus': 18, 'happiness_bonus': 9},
    'ring':         {'name': '金属戒指',   'cost': {'metal': 15, 'scrap': 10},          'affinity_bonus': 25, 'happiness_bonus': 12},
}

def item_type_config(item_type):
    return FURNITURE_TYPES if item_type == 'furniture' else GIFT_TYPES

def item_display_name(item_type, item_key):
    cfg = item_type_config(item_type).get(item_key)
    return cfg['name'] if cfg else item_key

DEMOLISH_REFUND_RATIO = 0.5

def total_invested_cost(btype, level):
    bt = BUILDING_TYPES[btype]
    base = bt['cost']
    total = {}
    for k, v in base.items():
        total[k] = total.get(k, 0) + v
    for lvl in range(2, level + 1):
        for k, v in scaled_cost(base, lvl).items():
            total[k] = total.get(k, 0) + v
    return total

AMMO_COST_PATROL = 3
AMMO_COST_HUNT = 8
WEAPON_DURABILITY_PER_LEVEL = 20
BLUEPRINT_EXTRA_LEVELS = 2
WEAPON_RD_TREE = [
    {'progress': 100, 'name': '轻量化枪械', 'kind': 'max_level', 'desc': '武器等级上限+1'},
    {'progress': 250, 'name': '穿甲弹药',   'kind': 'damage',    'desc': '武器有效战斗力+10%', 'requires_tech': 'ballistics_lab'},
    {'progress': 450, 'name': '合金枪管',   'kind': 'max_level', 'desc': '武器等级上限再+1',   'requires_tech': 'unified_command'},
]
WEAPON_RD_MILESTONES = [node['progress'] for node in WEAPON_RD_TREE]  # 兼容旧的"已跨过的里程碑数"展示逻辑

def get_weapon_max_level():
    progress = float(get_meta('weapon_rd_progress', '0') or 0)
    extra = sum(1 for node in WEAPON_RD_TREE if node['kind'] == 'max_level' and progress >= node['progress'])
    if is_tech_unlocked('unified_command'):
        extra += 1
    return EQUIP_MAX_LEVEL + extra

def weapon_rd_damage_mult():
    progress = float(get_meta('weapon_rd_progress', '0') or 0)
    return 1.1 if any(n['kind'] == 'damage' and progress >= n['progress'] for n in WEAPON_RD_TREE) else 1.0

def next_weapon_rd_gate(progress):
    """研发进度往下一个还没跨过的里程碑推进时,如果那个里程碑要求的科技还没解锁,就卡在这里不让继续研发。"""
    for node in WEAPON_RD_TREE:
        if progress < node['progress']:
            req = node.get('requires_tech')
            if req and not is_tech_unlocked(req):
                return node
            return None
    return None

BUILDING_TYPES = {
    'wall':       {'name': '围墙',     'cost': {'wood': 30, 'metal': 10}, 'max_level': 5, 'base_hp': 60,
                   'defense_per_level': 10},
    'watchtower': {'name': '瞭望塔',   'cost': {'wood': 25, 'metal': 15}, 'max_level': 3, 'base_hp': 50,
                   'defense_per_level': 5, 'warn_per_level': 0.08},
    'farm_plot':  {'name': '露天农田', 'cost': {'wood': 15},              'max_level': 3, 'base_hp': 40,
                   'protected': False},
    'greenhouse': {'name': '温室',     'cost': {'wood': 45, 'metal': 25}, 'max_level': 3, 'base_hp': 60,
                   'protected': True},
    'well':       {'name': '净水站',   'cost': {'wood': 20, 'metal': 15}, 'max_level': 3, 'base_hp': 50,
                   'water_per_level': 20},
    'clinic':     {'name': '诊所',     'cost': {'wood': 30, 'metal': 20}, 'max_level': 3, 'base_hp': 50,
                   'heal_bonus_per_level': 8},
    'workshop':   {'name': '工坊',     'cost': {'wood': 25, 'metal': 30}, 'max_level': 3, 'base_hp': 50,
                   'ammo_per_level': 6},
    'warehouse':  {'name': '仓库',     'cost': {'wood': 35, 'metal': 15}, 'max_level': 3, 'base_hp': 60,
                   'cap_bonus_per_level': 150},
    'research_lab': {'name': '研究所', 'cost': {'wood': 30, 'metal': 20}, 'max_level': 3, 'base_hp': 50,
                   'research_per_level': 5},
    'trap':       {'name': '陷阱',     'cost': {'wood': 10, 'metal': 15}, 'max_level': 3, 'base_hp': 30,
                   'defense_per_level': 6, 'tech': 'traps'},
    'kitchen':    {'name': '厨房',     'cost': {'wood': 30, 'metal': 15}, 'max_level': 3, 'base_hp': 50},
    'barn':       {'name': '畜栏',     'cost': {'wood': 25, 'metal': 10}, 'max_level': 3, 'base_hp': 40},
    'rain_collector': {'name': '雨水收集器', 'cost': {'wood': 20, 'metal': 20}, 'max_level': 3, 'base_hp': 40,
                   'raw_water_per_level': 15, 'tech': 'rainwater_tech'},
    'rec_room':   {'name': '娱乐室',   'cost': {'wood': 35, 'metal': 20}, 'max_level': 3, 'base_hp': 50,
                   'tech': 'recreation_tech'},
}
FARM_TYPES = ('farm_plot', 'greenhouse')

CROPS = {
    'potato':  {'name': '土豆',   'grow_days': 2, 'yield_food': 35,  'seed_cost': 6,  'seed_key': 'seed_potato',  'output_key': 'raw_potato'},
    'corn':    {'name': '玉米',   'grow_days': 3, 'yield_food': 60,  'seed_cost': 10, 'seed_key': 'seed_corn',    'output_key': 'raw_corn'},
    'soy':     {'name': '大豆',   'grow_days': 4, 'yield_food': 90,  'seed_cost': 15, 'seed_key': 'seed_soy',     'output_key': 'raw_soy'},
    'cabbage': {'name': '白菜',   'grow_days': 1, 'yield_food': 22,  'seed_cost': 5,  'seed_key': 'seed_cabbage', 'output_key': 'raw_cabbage'},
    'tomato':  {'name': '西红柿', 'grow_days': 2, 'yield_food': 40,  'seed_cost': 8,  'seed_key': 'seed_tomato',  'output_key': 'raw_tomato'},
    'wheat':   {'name': '小麦',   'grow_days': 3, 'yield_food': 55,  'seed_cost': 10, 'seed_key': 'seed_wheat',   'output_key': 'raw_wheat'},
    'pumpkin': {'name': '南瓜',   'grow_days': 3, 'yield_food': 110, 'seed_cost': 18, 'seed_key': 'seed_pumpkin', 'output_key': 'raw_pumpkin', 'tech': 'advanced_farming'},
    'herb':    {'name': '药草',   'grow_days': 2, 'yield_food': 25,  'seed_cost': 8,  'seed_key': 'seed_herb',    'output_key': 'herb', 'edible': False},
    'hay':     {'name': '干草',   'grow_days': 1, 'yield_food': 40,  'seed_cost': 4,  'seed_key': 'seed_hay',     'output_key': 'hay', 'edible': False},
    'cotton':  {'name': '棉花',   'grow_days': 3, 'yield_food': 45,  'seed_cost': 12, 'seed_key': 'seed_cotton',  'output_key': 'raw_cotton', 'edible': False},
    'grape':   {'name': '葡萄',   'grow_days': 3, 'yield_food': 38,  'seed_cost': 10, 'seed_key': 'seed_grape',   'output_key': 'raw_grape'},
    'apple':   {'name': '苹果',   'grow_days': 4, 'yield_food': 45,  'seed_cost': 12, 'seed_key': 'seed_apple',   'output_key': 'raw_apple'},
    'sugarcane': {'name': '甘蔗', 'grow_days': 3, 'yield_food': 50,  'seed_cost': 10, 'seed_key': 'seed_sugarcane', 'output_key': 'raw_sugarcane', 'edible': False},
}
RAW_CROP_KEYS = [c['output_key'] for c in CROPS.values() if c.get('edible', True)]

# 特殊菜谱吃了有加成效果,各自独立成资源桶而不是并进 food_feast/food_meal,不然吃到谁做的菜就分不清了
FOOD_TIER_EFFECTS = {
    'dish_pie':   {'health': 10, 'morale': 3, 'happiness': 8},
    'dish_power': {'health': 3, 'morale': 2, 'stat': 'stat_strength', 'stat_amount': 1, 'happiness': 5},
    'food_feast': {'health': 3, 'morale': 2, 'happiness': 4},
    'food_meal':  {'morale': 1},
    'food_meat':  {'morale': 1},
}
FOOD_TIERS = ['dish_pie', 'dish_power', 'food_feast', 'food_meal', 'food_meat'] + RAW_CROP_KEYS  # 供餐时优先扣高档次,生鲜作物垫底

def spend_up_to_raw_crop(amount):
    """从各类生鲜作物里按固定顺序凑,不够就有多少扣多少,返回实际扣掉的量(丧尸潮抢粮/寒潮取暖/畜栏喂饲料用)。"""
    remaining = amount
    for k in RAW_CROP_KEYS:
        take = min(remaining, get_resource(k))
        if take > 0:
            add_resource(k, -take)
            remaining -= take
        if remaining <= 0:
            break
    return amount - remaining

ANIMALS = {
    'chicken': {'name': '鸡', 'grow_days': 1, 'yield_food': 18, 'feed_cost': 8, 'output_key': 'food_meat'},
    'duck':    {'name': '鸭', 'grow_days': 1, 'yield_food': 20, 'feed_cost': 9, 'output_key': 'food_meat'},
    'pig':     {'name': '猪', 'grow_days': 3, 'yield_food': 80, 'feed_cost': 28, 'output_key': 'food_meat'},
    'sheep':   {'name': '羊', 'grow_days': 3, 'yield_food': 60, 'feed_cost': 25, 'output_key': 'food_meat'},
    'cattle':  {'name': '牛', 'grow_days': 4, 'yield_food': 90, 'feed_cost': 35, 'output_key': 'milk'},
}

SEASONS = ['初春', '盛夏', '深秋', '严冬']
SEASON_DAYS = 10

TECHS = {
    # 一级:四个分支的根科技,谁都能先解锁
    'workshop_gear':    {'name': '制式装备图纸', 'desc': '解锁工坊打造武器/护甲',       'cost': {'research': 40, 'metal': 20}, 'requires': []},
    'traps':            {'name': '诡雷图纸',     'desc': '解锁陷阱建筑(低成本防御)',  'cost': {'research': 50, 'metal': 15}, 'requires': []},
    'expedition':       {'name': '远征路线',     'desc': '解锁组队探索(必须两人一起,回合制战斗,比采集风险产出更高)', 'cost': {'research': 70, 'wood': 30}, 'requires': []},
    'advanced_farming': {'name': '耐旱良种',     'desc': '解锁南瓜(高产作物)',         'cost': {'research': 45, 'wood': 25}, 'requires': []},
    'rainwater_tech':   {'name': '雨水收集技术', 'desc': '解锁雨水收集器建筑(被动产生水,需要加工者净化后才能喝)', 'cost': {'research': 50, 'wood': 20}, 'requires': []},
    'recreation_tech':  {'name': '娱乐设施技术', 'desc': '解锁娱乐室建筑(参与娱乐能回复快乐值)', 'cost': {'research': 50, 'metal': 15}, 'requires': []},
    # 二级:每个分支的深化,各自需要对应的一级科技
    'ballistics_lab':   {'name': '弹道实验室',   'desc': '武器有效战斗力+15%(减伤/输出计算里的武器加成)', 'cost': {'research': 80, 'metal': 40}, 'requires': ['workshop_gear']},
    'fortification':    {'name': '强化工事',     'desc': '围墙/陷阱/瞭望塔防御值总和+15%', 'cost': {'research': 70, 'wood': 40, 'metal': 20}, 'requires': ['traps']},
    'irrigation':        {'name': '灌溉系统',    'desc': '所有作物生长时间-20%',       'cost': {'research': 60, 'wood': 35}, 'requires': ['advanced_farming']},
    'supply_chain':      {'name': '物资链',      'desc': '基地物资上限+10%',           'cost': {'research': 70, 'wood': 30, 'metal': 20}, 'requires': ['expedition']},
    # 三级:集大成的压轴科技,四个二级分支都点完才能解锁
    'unified_command':   {'name': '统一指挥',    'desc': '武器等级上限再+1,基地全面进入体系化运作', 'cost': {'research': 150, 'metal': 60, 'wood': 40},
                          'requires': ['ballistics_lab', 'fortification', 'irrigation', 'supply_chain']},
}

MILESTONES = {
    10: '基地撑过了第一个 10 天,大家总算摸清了幸存的门道',
    30: '整整一个月过去了,避难所已经有了家的样子',
    60: '60 天,幸存者们的名字开始被附近流浪的人提起',
    100: '100 天——这片废土上活得最久的基地之一',
}

# 剧情节点:按天数触发,全基地共享同一个选择,谁先点谁的选择对全基地生效(一次性、不可撤销)
STORY_EVENTS = {
    15: {'title': '废墟侦察队的消息',
         'desc': '巡逻队带回消息:附近一处商场废墟似乎还没被搜刮干净,但那里也可能有丧尸盘踞。要不要派人深入调查?',
         'choices': [
             {'label': '派人深入调查', 'resources': {'wood': 40, 'metal': 30, 'medicine': 20}, 'risk_chance': 0.3, 'risk_damage': 15},
             {'label': '太危险,不去了', 'morale': 3},
         ]},
    40: {'title': '陌生的求救信号',
         'desc': '无线电里传来一段微弱的求救信号,像是附近还有别的幸存者。要不要回应?',
         'choices': [
             {'label': '回应信号,尝试接应', 'resources': {'research': 20}, 'morale': 5, 'risk_chance': 0.2, 'risk_damage': 10},
             {'label': '保持无线电静默', 'morale': 0},
         ]},
    70: {'title': '流浪商人的秘密交易',
         'desc': '一个神秘商人提出可以用大量弹药换取基地的部分物资储备,划算吗?',
         'choices': [
             {'label': '同意交易(弹药+60,消耗木材50+金属30)', 'resources': {'ammo': 60}, 'cost': {'wood': 50, 'metal': 30}},
             {'label': '拒绝,太可疑了', 'morale': 2},
         ]},
    100: {'title': '远方基地的求援信号',
          'desc': '一支自称"河岸营地"的幸存者队伍通过电台求援,说他们快撑不住了。要不要派人跨区支援?',
          'choices': [
              {'label': '派人跨区支援', 'resources': {'crystal_core': 15, 'research': 30}, 'morale': 8, 'risk_chance': 0.35, 'risk_damage': 20},
              {'label': '爱莫能助,先保住自己', 'morale': -3},
          ]},
    130: {'title': '地下避难所遗迹',
          'desc': '拾荒队在一处地下车库深处发现了未开封的应急物资库,但入口坍塌严重,清理需要冒险。',
          'choices': [
              {'label': '组织人手挖掘清理', 'resources': {'wood': 60, 'metal': 50, 'medicine': 30, 'ammo': 40}, 'risk_chance': 0.4, 'risk_damage': 25},
              {'label': '太危险,原样封死', 'morale': 2},
          ]},
    160: {'title': '严冬将至的备战会议',
          'desc': '眼看又一个严冬季节临近,基地该优先囤积过冬物资,还是趁早扩充军备迎接会更凶猛的丧尸潮?',
          'choices': [
              {'label': '囤积过冬物资', 'resources': {'raw_wheat': 80, 'wood': 60, 'water': 60}, 'morale': 4},
              {'label': '优先扩充军备', 'resources': {'ammo': 60, 'metal': 40}, 'morale': 2},
          ]},
}

def pending_story_events():
    return [(day, event) for day, event in STORY_EVENTS.items()
            if get_meta(f'story_pending_{day}', '0') == '1' and get_meta(f'story_resolved_{day}', '0') != '1']

# ── 归途装置(大剧情主线):没有天数上限,堆够进度随时能激活;装置激活前,每隔几天就来一波比一波猛的信号猛攻 ──
GATE_DEVICE_TARGET = 1000
GATE_DEVICE_INVEST_COST = 20   # 每次投入消耗的共振核心
GATE_DEVICE_INVEST_PROGRESS = 20  # 每次投入给装置进度加的量,和消耗的核心数1:1
GATE_SURGE_INTERVAL_DAYS = 3   # 每隔几天来一次猛攻,装置激活前一直循环、不设上限
GATE_SURGE_PROGRESS_PENALTY = 30  # 猛攻没扛住时装置进度倒退多少

def gate_surge_multiplier(surge_number):
    """第1/2/3次猛攻强度倍率固定,第4次起每次再+0.5,不设上限——拖得越久越猛。"""
    fixed = {1: 1.5, 2: 2.2, 3: 3.0}
    if surge_number in fixed:
        return fixed[surge_number]
    return 3.0 + 0.5 * (surge_number - 3)

def gate_device_progress():
    return int(get_meta('gate_device_progress', '0') or 0)

def gate_device_activated():
    return get_meta('gate_device_activated', '0') == '1'

def is_tech_unlocked(key):
    return get_meta(f'tech_{key}', '0') == '1'

def base_defense_breakdown():
    """围墙/陷阱/瞭望塔的当前防御值,强化工事科技解锁后三者总和+15%。"""
    wall_level = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='wall'", one=True)['s']
    trap_level = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='trap'", one=True)['s']
    tower_level = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='watchtower'", one=True)['s']
    tech_mult = 1.15 if is_tech_unlocked('fortification') else 1.0
    wall_defense = wall_level * BUILDING_TYPES['wall']['defense_per_level'] * tech_mult
    trap_defense = trap_level * BUILDING_TYPES['trap']['defense_per_level'] * tech_mult
    tower_defense = tower_level * BUILDING_TYPES['watchtower']['defense_per_level'] * tech_mult
    return wall_defense, trap_defense, tower_defense, tower_level

def available_building_types():
    return {k: v for k, v in BUILDING_TYPES.items() if 'tech' not in v or is_tech_unlocked(v['tech'])}

def available_crops():
    return {k: v for k, v in CROPS.items() if 'tech' not in v or is_tech_unlocked(v['tech'])}

# ── 登录态 ─────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in S:
            return redirect(url_for('login'))
        survivor = q("SELECT status, age_years, specialization FROM survivors WHERE user_id=?", (S['uid'],), one=True)
        if not survivor:
            S.clear()
            flash('登录状态已失效,请重新登录', 'error')
            return redirect(url_for('login'))
        if survivor['status'] in ('dead', 'permadead') and request.endpoint not in ('respawn', 'logout'):
            return redirect(url_for('respawn'))
        if survivor['age_years'] < AGE_ADULT and request.endpoint not in ('dashboard', 'logout', 'respawn'):
            flash('还没成年,先长大', 'error')
            return redirect(url_for('dashboard'))
        if (survivor['age_years'] >= AGE_ADULT and not survivor['specialization']
                and request.endpoint not in ('dashboard', 'logout', 'respawn', 'coming_of_age')):
            return redirect(url_for('coming_of_age'))
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

def current_survivor():
    return q("SELECT * FROM survivors WHERE user_id=?", (S.get('uid'),), one=True)

# ── 体力 / 状态 ─────────────────────────────────────────────────────────────────

def has_shared_room(survivor_id):
    return q("SELECT 1 FROM relationships WHERE (a_id=? OR b_id=?) AND shared_room=1",
              (survivor_id, survivor_id), one=True) is not None

def installed_furniture_bonus(survivor_id, effect):
    rows = q("SELECT item_key FROM survivor_items WHERE owner_id=? AND item_type='furniture' AND status='installed'", (survivor_id,))
    return sum(FURNITURE_TYPES[r['item_key']]['amount'] for r in rows
               if FURNITURE_TYPES.get(r['item_key'], {}).get('effect') == effect)

def room_energy_regen_seconds(room_tier, shared_room=False, furniture_bonus=0, depressed=False):
    bonus = ROOM_TIERS.get(room_tier, ROOM_TIERS[0])['energy_regen_bonus']
    if shared_room:
        bonus += SHARED_ROOM_ENERGY_BONUS
    bonus += furniture_bonus
    if depressed:
        bonus += DEPRESSION_ENERGY_PENALTY
    return max(20, round(ENERGY_REGEN_SECONDS / (1 + bonus / 100)))

def get_effective_energy(survivor_id):
    row = q("SELECT energy, energy_updated, contribution, stat_strength, room_tier, age_years, is_depressed FROM survivors WHERE id=?", (survivor_id,), one=True)
    if not row:
        return 0
    max_energy = get_max_energy(row)
    regen_seconds = room_energy_regen_seconds(row['room_tier'], has_shared_room(survivor_id),
                                               installed_furniture_bonus(survivor_id, 'energy'),
                                               depressed=bool(row['is_depressed']))
    base_ts = row['energy_updated'] or now_ts()
    elapsed = now_ts() - base_ts
    regen = elapsed // regen_seconds
    if regen <= 0:
        return min(row['energy'], max_energy)
    new_energy = min(max_energy, row['energy'] + regen)
    new_updated = base_ts + regen * regen_seconds
    run("UPDATE survivors SET energy=?, energy_updated=? WHERE id=?", (new_energy, new_updated, survivor_id))
    return new_energy

def get_effective_age(survivor_id):
    """和 get_effective_energy 同款懒 tick:锚定 age_updated_ts,按整倍数结算,到 AGE_MAX 触发老死。"""
    row = q("SELECT age_years, age_updated_ts, status FROM survivors WHERE id=?", (survivor_id,), one=True)
    if not row:
        return 0
    base_ts = row['age_updated_ts'] or now_ts()
    elapsed = now_ts() - base_ts
    grown = elapsed // AGE_YEAR_SECONDS
    if grown <= 0:
        return row['age_years']
    new_age = row['age_years'] + grown
    new_updated = base_ts + grown * AGE_YEAR_SECONDS
    run("UPDATE survivors SET age_years=?, age_updated_ts=? WHERE id=?", (new_age, new_updated, survivor_id))
    if new_age >= AGE_MAX and row['status'] not in ('dead', 'permadead'):
        apply_natural_death(survivor_id)
    return new_age

def try_spend_energy(survivor_id, action_key):
    base_cost = ENERGY_COSTS.get(action_key, 0)
    row = q("SELECT stat_willpower FROM survivors WHERE id=?", (survivor_id,), one=True)
    willpower_factor = max(0.7, 1 - 0.02 * (row['stat_willpower'] - STAT_BASE)) if row else 1.0
    cost = max(1, round(base_cost * willpower_factor)) if base_cost else 0
    current = get_effective_energy(survivor_id)
    if current < cost:
        return False
    run("UPDATE survivors SET energy=energy-? WHERE id=?", (cost, survivor_id))
    return True

def status_for_health(health):
    if health <= 0:
        return 'dead'
    if health < 20:
        return 'critical'
    if health < 50:
        return 'injured'
    return 'normal'

def add_happiness(survivor_id, delta):
    """快乐值0-100封顶,礼物/高档食物/庆祝/娱乐设施四个来源统一走这个。"""
    row = q("SELECT happiness FROM survivors WHERE id=?", (survivor_id,), one=True)
    if not row:
        return
    new_val = max(0, min(100, row['happiness'] + delta))
    run("UPDATE survivors SET happiness=? WHERE id=?", (new_val, survivor_id))
    return new_val

def apply_health_delta(survivor_id, delta):
    row = q("SELECT health, name, status FROM survivors WHERE id=?", (survivor_id,), one=True)
    if not row or row['status'] in ('dead', 'permadead'):
        return
    new_health = max(0, min(MAX_HEALTH, row['health'] + delta))
    new_status = status_for_health(new_health)
    run("UPDATE survivors SET health=?, status=? WHERE id=?", (new_health, new_status, survivor_id))
    if new_status == 'dead':
        log_event('death', f"{row['name']} 伤重不治,倒下了")

def apply_natural_death(survivor_id):
    """到 AGE_MAX 的老死,和战斗死亡走同一套 dead/respawn 流程,只是广播文案不同。"""
    row = q("SELECT name, status FROM survivors WHERE id=?", (survivor_id,), one=True)
    if not row or row['status'] in ('dead', 'permadead'):
        return
    run("UPDATE survivors SET health=0, status='dead' WHERE id=?", (survivor_id,))
    log_event('death', f"{row['name']} 年事已高,安详离世了")

def add_contribution(survivor_id, amount):
    run("UPDATE survivors SET contribution=contribution+?, wallet=wallet+? WHERE id=?", (amount, amount, survivor_id))

def log_action(survivor_id, survivor_name, action, detail):
    run("INSERT INTO action_log (survivor_id, survivor_name, action, detail, created_ts) VALUES (?,?,?,?,?)",
        (survivor_id, survivor_name, action, detail, now_ts()))

def log_event(kind, detail):
    row = q("SELECT day_count FROM base_state WHERE id=1", one=True)
    day = row['day_count'] if row else 1
    run("INSERT INTO events_log (day_count, kind, detail, created_ts) VALUES (?,?,?,?)", (day, kind, detail, now_ts()))

# ── 资源 helper ─────────────────────────────────────────────────────────────────

def get_resource(key):
    row = q("SELECT amount FROM resources WHERE key=?", (key,), one=True)
    return row['amount'] if row else 0

def resource_cap():
    wh = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='warehouse'", one=True)
    bonus = (wh['s'] or 0) * BUILDING_TYPES['warehouse']['cap_bonus_per_level']
    cap = BASE_RESOURCE_CAP + bonus
    if is_tech_unlocked('supply_chain'):
        cap = round(cap * 1.1)
    return cap

def add_resource(key, delta):
    cap = resource_cap()
    cur = get_resource(key)
    new_val = max(0, min(cap, cur + delta))
    run("INSERT INTO resources (key, amount) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET amount=excluded.amount", (key, new_val))
    return new_val

def can_afford(cost_dict):
    return all(get_resource(k) >= v for k, v in cost_dict.items())

def spend_resources(cost_dict):
    for k, v in cost_dict.items():
        add_resource(k, -v)

def scaled_cost(base_cost, factor):
    return {k: max(1, math.ceil(v * factor)) for k, v in base_cost.items()}

def specialization_mult(survivor, action_key):
    spec = SPECIALIZATIONS.get(survivor['specialization']) if survivor['specialization'] else None
    if spec and spec['bonus_action'] == action_key:
        return spec['mult']
    return 1.0

def profession_cost_discount(survivor, action_key):
    """本职业做本行动更省料(专属被动),不是本职业的人不受影响。"""
    return 1 / specialization_mult(survivor, action_key)

def effective_weapon_bonus(survivor):
    """武器耐久归零就不生效;刀不耗弹药但效果打7折,枪全额但要有弹药才能用;弹道实验室科技解锁后整体+15%。"""
    if survivor['weapon_level'] <= 0 or survivor['weapon_durability'] <= 0:
        return 0
    base = survivor['weapon_level'] * 0.7 if survivor['weapon_type'] == 'knife' else survivor['weapon_level']
    return base * (1.15 if is_tech_unlocked('ballistics_lab') else 1.0) * weapon_rd_damage_mult()

# ── 注册 / 登录 ─────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip() or username
        invite_code = request.form.get('invite_code', '').strip()
        invite = q("SELECT * FROM birth_invites WHERE code=? AND used=0", (invite_code,), one=True) if invite_code else None
        if not username or not password:
            flash('账号和密码不能为空', 'error')
            return redirect(url_for('register'))
        if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            flash('该账号已被注册', 'error')
            return redirect(url_for('register'))
        if invite:
            spec = ''
            stat_values = {k: 0 for k in STATS}
            age_years = 0
        else:
            spec = request.form.get('specialization', '')
            if spec not in SPECIALIZATIONS:
                flash('请选择一个专精', 'error')
                return redirect(url_for('register'))
            stat_values, allocated = parse_stat_allocation(request.form)
            if stat_values is None:
                flash(f'属性点最多只能分配 {STAT_FREE_POINTS} 点,你分配了 {allocated} 点', 'error')
                return redirect(url_for('register'))
            age_years = random.randint(18, 25)
        cur = run("INSERT INTO users (username, password_hash, role, created_ts) VALUES (?,?,?,?)",
                   (username, generate_password_hash(password, method='pbkdf2:sha256'), 'player', now_ts()))
        uid = cur.lastrowid
        cols = ', '.join(STATS.keys())
        placeholders = ', '.join(['?'] * len(STATS))
        values = [STAT_BASE + stat_values[k] for k in STATS]
        survivor_cur = run(f"INSERT INTO survivors (user_id, name, specialization, health, energy, energy_updated, "
            f"age_years, age_updated_ts, created_ts, {cols}) "
            f"VALUES (?,?,?,100,100,?,?,?,?,{placeholders})",
            (uid, name, spec, now_ts(), age_years, now_ts(), now_ts(), *values))
        if invite:
            run("UPDATE birth_invites SET used=1, child_survivor_id=? WHERE code=?", (survivor_cur.lastrowid, invite_code))
            log_event('birth', f"{name} 出生了")
            flash('注册成功,这是一个刚出生的孩子,得先长大成年才能正常行动', 'ok')
        else:
            flash('注册成功,欢迎来到避难所', 'ok')
        return redirect(url_for('login'))
    return render_template('register.html', specializations=SPECIALIZATIONS, stats=STATS,
                           stat_base=STAT_BASE, stat_free_points=STAT_FREE_POINTS)

MAX_RESPAWNS = 3

@app.route('/respawn', methods=['GET', 'POST'])
@login_required
def respawn():
    survivor = current_survivor()
    if survivor['status'] not in ('dead', 'permadead'):
        return redirect(url_for('dashboard'))
    if survivor['respawn_count'] >= MAX_RESPAWNS:
        if survivor['status'] != 'permadead':
            run("UPDATE survivors SET status='permadead' WHERE id=?", (survivor['id'],))
            remaining = q("SELECT COUNT(*) c FROM survivors WHERE status!='permadead'", one=True)['c']
            if remaining == 0:
                log_event('ending', f"{survivor['name']} 用完了最后一次重生机会——基地里再也没有能站起来的活人了,这片废土暂时安静了下来(全灭)")
        return render_template('respawn.html', survivor=survivor, out_of_lives=True,
                               max_respawns=MAX_RESPAWNS)
    if request.method == 'POST':
        spec = request.form.get('specialization', '')
        if spec not in SPECIALIZATIONS:
            flash('请选择一个专精', 'error')
            return redirect(url_for('respawn'))
        stat_values, allocated = parse_stat_allocation(request.form)
        if stat_values is None:
            flash(f'属性点最多只能分配 {STAT_FREE_POINTS} 点,你分配了 {allocated} 点', 'error')
            return redirect(url_for('respawn'))
        assignments = ', '.join(f"{k}=?" for k in STATS)
        values = [STAT_BASE + stat_values[k] for k in STATS]
        run(f"UPDATE survivors SET specialization=?, health=100, energy=100, energy_updated=?, status='normal', "
            f"contribution=0, wallet=0, weapon_level=0, gear_level=0, weapon_type='', weapon_durability=0, "
            f"weapon_max_durability=0, respawn_count=respawn_count+1, illness='', illness_started_ts=0, "
            f"age_years=?, age_updated_ts=?, "
            f"{assignments} WHERE id=?",
            (spec, now_ts(), random.randint(18, 25), now_ts(), *values, survivor['id']))
        log_event('respawn', f"{survivor['name']} 重新振作了起来,第 {survivor['respawn_count']+1} 次重生")
        flash('重生成功,一切数值都重置了,好好活下去', 'ok')
        return redirect(url_for('dashboard'))
    return render_template('respawn.html', survivor=survivor, out_of_lives=False,
                           specializations=SPECIALIZATIONS, stats=STATS,
                           stat_base=STAT_BASE, stat_free_points=STAT_FREE_POINTS,
                           max_respawns=MAX_RESPAWNS)

@app.route('/coming-of-age', methods=['GET', 'POST'])
@login_required
def coming_of_age():
    survivor = current_survivor()
    if survivor['age_years'] < AGE_ADULT or survivor['specialization']:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        spec = request.form.get('specialization', '')
        if spec not in SPECIALIZATIONS:
            flash('请选择一个专精', 'error')
            return redirect(url_for('coming_of_age'))
        stat_values, allocated = parse_stat_allocation(request.form)
        if stat_values is None:
            flash(f'属性点最多只能分配 {STAT_FREE_POINTS} 点,你分配了 {allocated} 点', 'error')
            return redirect(url_for('coming_of_age'))
        assignments = ', '.join(f"{k}=?" for k in STATS)
        values = [STAT_BASE + stat_values[k] for k in STATS]
        run(f"UPDATE survivors SET specialization=?, {assignments} WHERE id=?", (spec, *values, survivor['id']))
        log_event('coming_of_age', f"{survivor['name']} 成年了,选择成为{SPECIALIZATIONS[spec]['name']}")
        flash('成年了!欢迎正式加入基地建设', 'ok')
        return redirect(url_for('dashboard'))
    return render_template('coming_of_age.html', survivor=survivor, specializations=SPECIALIZATIONS, stats=STATS,
                           stat_base=STAT_BASE, stat_free_points=STAT_FREE_POINTS)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if username == ADMIN_USER and password == ADMIN_PASS:
            S.permanent = True
            S['role'] = 'admin'
            S['uname'] = username
            return redirect(url_for('admin_home'))
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if not user or not check_password_hash(user['password_hash'], password):
            flash('账号或密码错误', 'error')
            return redirect(url_for('login'))
        S.permanent = True
        S['uid'] = user['id']
        S['uname'] = user['username']
        S['role'] = 'player'
        run("UPDATE users SET last_login=? WHERE id=?", (now_ts(), user['id']))
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    S.clear()
    return redirect(url_for('login'))

# ── 求助板:系统自动检测需要协作的事项 ────────────────────────────────────────────

def compute_alerts(survivor=None):
    alerts = []
    if survivor is not None and survivor['wallet'] < FOOD_CLAIM_PRICE:
        alerts.append({'key': f"wallet:{survivor['id']}", 'claimable': False,
                       'text': f"你的钱包只剩{survivor['wallet']},不够明天领餐(需要{FOOD_CLAIM_PRICE}),赶紧去干点活攒贡献值", 'link': 'field_page'})
    for s in q("SELECT * FROM survivors WHERE status='critical'"):
        alerts.append({'key': f"critical:{s['id']}", 'claimable': True,
                       'text': f"{s['name']} 身负重伤,需要有人去诊所治疗", 'link': 'clinic_page'})
    day_now = q("SELECT day_count FROM base_state WHERE id=1", one=True)['day_count']
    for s in q("SELECT * FROM survivors WHERE infected=1 AND status NOT IN ('dead','permadead')"):
        days_left = max(0, INFECTION_DAYS_LIMIT - (day_now - s['infected_since_day']))
        alerts.append({'key': f"infected:{s['id']}", 'claimable': True,
                       'text': f"{s['name']} 被咬伤感染了,再拖{days_left}天不治疗就会变成丧尸,永远失去这个人,赶紧去诊所治", 'link': 'clinic_page'})
    for s in q("SELECT * FROM survivors WHERE illness!='' AND status NOT IN ('dead','permadead')"):
        alerts.append({'key': f"illness:{s['id']}", 'claimable': True,
                       'text': f"{s['name']} 生病了({ILLNESSES[s['illness']]['name']}),需要有人去诊所治", 'link': 'clinic_page'})
    for b in q("SELECT * FROM buildings WHERE type!='empty' AND max_hp>0"):
        if b['hp'] < b['max_hp'] * 0.5:
            alerts.append({'key': f"building:{b['slot_index']}", 'claimable': True,
                           'text': f"{BUILDING_TYPES[b['type']]['name']}#{b['slot_index']} 耐久过低,需要维修", 'link': 'build_page'})
    base = q("SELECT day_count FROM base_state WHERE id=1", one=True)
    day = base['day_count'] if base else 1
    wall_defense, trap_defense, tower_defense, _ = base_defense_breakdown()
    patrol_points = float(get_meta('patrol_points_today', '0') or 0)
    horde_reduction = float(get_meta('horde_reduction_today', '0') or 0)
    defense_total = wall_defense + trap_defense + tower_defense + patrol_points
    expected_strength = max(10, 40 + day * 3 - horde_reduction)
    if defense_total < expected_strength:
        alerts.append({'key': f"horde:{day}", 'claimable': True,
                       'text': f"今晚丧尸潮预计强度约{round(expected_strength)},当前防御值{round(defense_total)},还差{round(expected_strength-defense_total)}点,去巡逻/出击或加固围墙", 'link': 'field_page'})

    run("DELETE FROM alert_claims WHERE claimed_ts < ?", (now_ts() - ALERT_CLAIM_TIMEOUT_SECONDS,))

    claimable_keys = [a['key'] for a in alerts if a['claimable']]
    if claimable_keys:
        placeholders = ','.join('?' for _ in claimable_keys)
        db = get_db()
        db.execute(f"DELETE FROM alert_claims WHERE alert_key NOT IN ({placeholders}) AND "
                   f"(alert_key LIKE 'critical:%' OR alert_key LIKE 'illness:%' OR alert_key LIKE 'infected:%' OR alert_key LIKE 'building:%' OR alert_key LIKE 'horde:%')",
                   claimable_keys)
        db.commit()
    else:
        db = get_db()
        db.execute("DELETE FROM alert_claims WHERE alert_key LIKE 'critical:%' OR alert_key LIKE 'illness:%' OR alert_key LIKE 'infected:%' OR alert_key LIKE 'building:%' OR alert_key LIKE 'horde:%'")
        db.commit()
    claims = {c['alert_key']: c for c in q("SELECT * FROM alert_claims")}
    for a in alerts:
        claim = claims.get(a['key'])
        a['claimed_by'] = claim['claimed_by'] if claim else None
    return alerts

@app.route('/alert/claim', methods=['POST'])
@login_required
def alert_claim():
    survivor = current_survivor()
    alert_key = request.form.get('alert_key', '')
    existing = q("SELECT * FROM alert_claims WHERE alert_key=?", (alert_key,), one=True)
    if existing and existing['claimed_by'] == survivor['name']:
        run("DELETE FROM alert_claims WHERE alert_key=?", (alert_key,))
        flash('已取消认领', 'ok')
    elif existing:
        flash(f"已经被 {existing['claimed_by']} 认领了", 'error')
    else:
        run("INSERT INTO alert_claims (alert_key, claimed_by, claimed_ts) VALUES (?,?,?)",
            (alert_key, survivor['name'], now_ts()))
        flash('认领成功,大家会看到你在处理', 'ok')
    return redirect(request.referrer or url_for('dashboard'))

# ── 总览 ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    if S.get('uid'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    base = q("SELECT * FROM base_state WHERE id=1", one=True)
    resources = {r['key']: r['amount'] for r in q("SELECT * FROM resources")}
    cap = resource_cap()
    survivors = q("SELECT * FROM survivors ORDER BY contribution DESC")
    events = q("SELECT * FROM events_log ORDER BY id DESC LIMIT 8")
    actions = q("SELECT * FROM action_log ORDER BY id DESC LIMIT 8")
    patrol_points = float(get_meta('patrol_points_today', '0') or 0)
    level = get_survivor_level(survivor['contribution'])
    gate_progress = gate_device_progress()
    gate_activated = gate_device_activated()
    next_surge_day = ((base['day_count'] // GATE_SURGE_INTERVAL_DAYS) + 1) * GATE_SURGE_INTERVAL_DAYS
    return render_template('dashboard.html', survivor=survivor, base=base, resources=resources,
                           resource_names=RESOURCE_NAMES, cap=cap, survivors=survivors,
                           events=events, actions=actions, specializations=SPECIALIZATIONS,
                           patrol_points=round(patrol_points, 1), alerts=compute_alerts(survivor),
                           level=level, max_level=MAX_SURVIVOR_LEVEL, max_energy=get_max_energy(survivor),
                           level_step=LEVEL_CONTRIBUTION_STEP, food_claim_price=FOOD_CLAIM_PRICE,
                           get_survivor_level=get_survivor_level, stats=STATS,
                           room_tiers=ROOM_TIERS, illnesses=ILLNESSES,
                           story_events=pending_story_events(), age_adult=AGE_ADULT,
                           gate_progress=gate_progress, gate_target=GATE_DEVICE_TARGET,
                           gate_activated=gate_activated, gate_invest_cost=GATE_DEVICE_INVEST_COST,
                           gate_surge_interval=GATE_SURGE_INTERVAL_DAYS,
                           next_surge_day=next_surge_day if not gate_activated else None)

@app.route('/log')
@login_required
def broadcast_log():
    events = q("SELECT * FROM events_log ORDER BY id DESC LIMIT 60")
    actions = q("SELECT * FROM action_log ORDER BY id DESC LIMIT 60")
    return render_template('log.html', events=events, actions=actions)

# ── 农田 ─────────────────────────────────────────────────────────────────────

@app.route('/farm')
@login_required
def farm_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    plots = q("SELECT * FROM buildings WHERE type IN ('farm_plot','greenhouse') ORDER BY slot_index")
    barns = q("SELECT * FROM buildings WHERE type='barn' ORDER BY slot_index")
    return render_template('farm.html', survivor=survivor, plots=plots, crops=CROPS,
                           available_crops=available_crops(), building_types=BUILDING_TYPES, now=now_ts(),
                           max_energy=get_max_energy(survivor), barns=barns, animals=ANIMALS,
                           resource_names=RESOURCE_NAMES)

@app.route('/farm/plant/<int:slot_id>', methods=['POST'])
@login_required
def farm_plant(slot_id):
    survivor = current_survivor()
    crop_key = request.form.get('crop', '')
    plot = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not plot or plot['type'] not in FARM_TYPES:
        flash('这不是一块农田', 'error')
        return redirect(url_for('farm_page'))
    if plot['crop_type']:
        flash('这块地已经种了作物', 'error')
        return redirect(url_for('farm_page'))
    if crop_key not in available_crops():
        flash('没有这种作物', 'error')
        return redirect(url_for('farm_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('farm_page'))
    seed_key = CROPS[crop_key]['seed_key']
    seed_cost = max(1, math.ceil(CROPS[crop_key]['seed_cost'] * profession_cost_discount(survivor, 'farm')))
    if get_resource(seed_key) < seed_cost:
        flash(f"{RESOURCE_NAMES[seed_key]}不够了", 'error')
        return redirect(url_for('farm_page'))
    if not try_spend_energy(survivor['id'], 'plant'):
        flash('体力不足', 'error')
        return redirect(url_for('farm_page'))
    spend_resources({seed_key: seed_cost})
    grow_mult = 0.8 if is_tech_unlocked('irrigation') else 1.0
    ready_ts = now_ts() + round(CROPS[crop_key]['grow_days'] * DAY_SECONDS * grow_mult)
    run("UPDATE buildings SET crop_type=?, ready_ts=?, built_by=?, updated_ts=? WHERE slot_index=?",
        (crop_key, ready_ts, survivor['id'], now_ts(), slot_id))
    log_action(survivor['id'], survivor['name'], '种植', f"在{BUILDING_TYPES[plot['type']]['name']}#{slot_id}种下了{CROPS[crop_key]['name']}")
    flash(f"种下了{CROPS[crop_key]['name']}", 'ok')
    return redirect(url_for('farm_page'))

@app.route('/farm/harvest/<int:slot_id>', methods=['POST'])
@login_required
def farm_harvest(slot_id):
    survivor = current_survivor()
    plot = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not plot or plot['type'] not in FARM_TYPES or not plot['crop_type']:
        flash('这块地没有可收获的作物', 'error')
        return redirect(url_for('farm_page'))
    if plot['ready_ts'] > now_ts():
        flash('作物还没成熟', 'error')
        return redirect(url_for('farm_page'))
    if not try_spend_energy(survivor['id'], 'harvest'):
        flash('体力不足', 'error')
        return redirect(url_for('farm_page'))
    crop = CROPS[plot['crop_type']]
    plot_level_mult = 1 + 0.3 * max(0, plot['level'] - 1)
    mult = specialization_mult(survivor, 'farm') * get_level_mult(survivor) * stat_mult(survivor, 'stat_strength')
    yield_food = round(crop['yield_food'] * plot_level_mult * mult)
    output_key = crop['output_key']
    add_resource(output_key, yield_food)
    run("UPDATE buildings SET crop_type='', ready_ts=0, updated_ts=? WHERE slot_index=?", (now_ts(), slot_id))
    add_contribution(survivor['id'], 3)
    output_name = RESOURCE_NAMES[output_key]
    log_action(survivor['id'], survivor['name'], '收获', f"收获了{crop['name']},获得{yield_food}{output_name}")
    flash(f"收获{crop['name']},获得{yield_food}{output_name}", 'ok')
    return redirect(url_for('farm_page'))

@app.route('/farm/raise/<int:slot_id>', methods=['POST'])
@login_required
def farm_raise(slot_id):
    survivor = current_survivor()
    animal_key = request.form.get('animal', '')
    barn = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not barn or barn['type'] != 'barn':
        flash('这不是畜栏', 'error')
        return redirect(url_for('farm_page'))
    if barn['crop_type']:
        flash('这个畜栏已经在养了', 'error')
        return redirect(url_for('farm_page'))
    if animal_key not in ANIMALS:
        flash('没有这种动物', 'error')
        return redirect(url_for('farm_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('farm_page'))
    feed_cost = ANIMALS[animal_key]['feed_cost']
    if get_resource('hay') < feed_cost:
        flash('干草(饲料)不够了', 'error')
        return redirect(url_for('farm_page'))
    if not try_spend_energy(survivor['id'], 'plant'):
        flash('体力不足', 'error')
        return redirect(url_for('farm_page'))
    spend_resources({'hay': feed_cost})
    ready_ts = now_ts() + ANIMALS[animal_key]['grow_days'] * DAY_SECONDS
    run("UPDATE buildings SET crop_type=?, ready_ts=?, built_by=?, updated_ts=? WHERE slot_index=?",
        (animal_key, ready_ts, survivor['id'], now_ts(), slot_id))
    log_action(survivor['id'], survivor['name'], '养殖', f"在畜栏#{slot_id}养起了{ANIMALS[animal_key]['name']}")
    flash(f"养起了{ANIMALS[animal_key]['name']}", 'ok')
    return redirect(url_for('farm_page'))

@app.route('/farm/collect/<int:slot_id>', methods=['POST'])
@login_required
def farm_collect(slot_id):
    survivor = current_survivor()
    barn = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not barn or barn['type'] != 'barn' or not barn['crop_type']:
        flash('这个畜栏没有可收获的产出', 'error')
        return redirect(url_for('farm_page'))
    if barn['ready_ts'] > now_ts():
        flash('还没到收获的时候', 'error')
        return redirect(url_for('farm_page'))
    if not try_spend_energy(survivor['id'], 'harvest'):
        flash('体力不足', 'error')
        return redirect(url_for('farm_page'))
    animal = ANIMALS[barn['crop_type']]
    barn_level_mult = 1 + 0.3 * max(0, barn['level'] - 1)
    mult = specialization_mult(survivor, 'farm') * get_level_mult(survivor) * stat_mult(survivor, 'stat_strength')
    yield_food = round(animal['yield_food'] * barn_level_mult * mult)
    output_key = animal['output_key']
    add_resource(output_key, yield_food)
    run("UPDATE buildings SET crop_type='', ready_ts=0, updated_ts=? WHERE slot_index=?", (now_ts(), slot_id))
    add_contribution(survivor['id'], 3)
    output_name = RESOURCE_NAMES[output_key]
    log_action(survivor['id'], survivor['name'], '收获', f"从{animal['name']}身上收获了{yield_food}份{output_name}")
    flash(f"收获{animal['name']},获得{yield_food}份{output_name}", 'ok')
    return redirect(url_for('farm_page'))

# ── 建筑 ─────────────────────────────────────────────────────────────────────

@app.route('/build')
@login_required
def build_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    slots = q("SELECT * FROM buildings ORDER BY slot_index")
    return render_template('build.html', survivor=survivor, slots=slots, building_types=BUILDING_TYPES,
                           available_building_types=available_building_types(), max_energy=get_max_energy(survivor),
                           blueprint_extra=BLUEPRINT_EXTRA_LEVELS, blueprint_count=get_resource('blueprint'),
                           resource_names=RESOURCE_NAMES, cotton_count=get_resource('raw_cotton'),
                           weave_input=WEAVE_COTTON_INPUT, weave_output=WEAVE_CLOTH_OUTPUT,
                           furniture_types=FURNITURE_TYPES)

@app.route('/build/new/<int:slot_id>', methods=['POST'])
@login_required
def build_new(slot_id):
    survivor = current_survivor()
    btype = request.form.get('type', '')
    slot = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not slot or slot['type'] != 'empty':
        flash('这个位置已经有建筑了', 'error')
        return redirect(url_for('build_page'))
    if btype not in available_building_types():
        flash('没有这种建筑', 'error')
        return redirect(url_for('build_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('build_page'))
    cost = {k: max(1, round(v * profession_cost_discount(survivor, 'build'))) for k, v in BUILDING_TYPES[btype]['cost'].items()}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('build_page'))
    if not try_spend_energy(survivor['id'], 'build'):
        flash('体力不足', 'error')
        return redirect(url_for('build_page'))
    spend_resources(cost)
    hp = BUILDING_TYPES[btype]['base_hp']
    run("UPDATE buildings SET type=?, level=1, hp=?, max_hp=?, built_by=?, updated_ts=? WHERE slot_index=?",
        (btype, hp, hp, survivor['id'], now_ts(), slot_id))
    add_contribution(survivor['id'], 5)
    log_action(survivor['id'], survivor['name'], '建造', f"在#{slot_id}建起了{BUILDING_TYPES[btype]['name']}")
    flash(f"建起了{BUILDING_TYPES[btype]['name']}", 'ok')
    return redirect(url_for('build_page'))

@app.route('/build/upgrade/<int:slot_id>', methods=['POST'])
@login_required
def build_upgrade(slot_id):
    survivor = current_survivor()
    slot = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not slot or slot['type'] == 'empty':
        flash('这个位置没有建筑', 'error')
        return redirect(url_for('build_page'))
    bt = BUILDING_TYPES[slot['type']]
    extended_max = bt['max_level'] + BLUEPRINT_EXTRA_LEVELS
    if slot['level'] >= extended_max:
        flash('已经是最高等级了', 'error')
        return redirect(url_for('build_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('build_page'))
    next_level = slot['level'] + 1
    needs_blueprint = next_level > bt['max_level']
    if needs_blueprint and get_resource('blueprint') < 1:
        flash('没有图纸了,工程师需要先去绘制', 'error')
        return redirect(url_for('build_page'))
    cost = {k: max(1, round(v * profession_cost_discount(survivor, 'build'))) for k, v in scaled_cost(bt['cost'], next_level).items()}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('build_page'))
    if not try_spend_energy(survivor['id'], 'upgrade'):
        flash('体力不足', 'error')
        return redirect(url_for('build_page'))
    spend_resources(cost)
    if needs_blueprint:
        spend_resources({'blueprint': 1})
    new_max_hp = bt['base_hp'] * next_level
    run("UPDATE buildings SET level=?, hp=?, max_hp=?, updated_ts=? WHERE slot_index=?",
        (next_level, new_max_hp, new_max_hp, now_ts(), slot_id))
    add_contribution(survivor['id'], 5)
    log_action(survivor['id'], survivor['name'], '升级', f"把#{slot_id}的{bt['name']}升到了{next_level}级")
    flash(f"{bt['name']}升到了{next_level}级", 'ok')
    return redirect(url_for('build_page'))

@app.route('/build/draft-blueprint', methods=['POST'])
@login_required
def build_draft_blueprint():
    survivor = current_survivor()
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('build_page'))
    cost = {'wood': 40, 'metal': 30}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('build_page'))
    if not try_spend_energy(survivor['id'], 'draft_blueprint'):
        flash('体力不足', 'error')
        return redirect(url_for('build_page'))
    spend_resources(cost)
    add_resource('blueprint', 1)
    add_contribution(survivor['id'], 4)
    log_action(survivor['id'], survivor['name'], '绘图', "画出了一张图纸")
    flash('画出了一张图纸', 'ok')
    return redirect(url_for('build_page'))

WEAVE_COTTON_INPUT, WEAVE_CLOTH_OUTPUT = 20, 12

@app.route('/build/weave-cloth', methods=['POST'])
@login_required
def build_weave_cloth():
    survivor = current_survivor()
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('build_page'))
    if get_resource('raw_cotton') < WEAVE_COTTON_INPUT:
        flash('棉花不够了', 'error')
        return redirect(url_for('build_page'))
    if not try_spend_energy(survivor['id'], 'weave'):
        flash('体力不足', 'error')
        return redirect(url_for('build_page'))
    spend_resources({'raw_cotton': WEAVE_COTTON_INPUT})
    mult = specialization_mult(survivor, 'build') * get_level_mult(survivor)
    output = round(WEAVE_CLOTH_OUTPUT * mult)
    add_resource('cloth', output)
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '织布', f"用棉花织出了{output}份布")
    flash(f"织出了{output}份布", 'ok')
    return redirect(url_for('build_page'))

@app.route('/build/craft-furniture/<key>', methods=['POST'])
@login_required
def build_craft_furniture(key):
    survivor = current_survivor()
    if key not in FURNITURE_TYPES:
        flash('没有这种家具', 'error')
        return redirect(url_for('build_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('build_page'))
    furn = FURNITURE_TYPES[key]
    discount = profession_cost_discount(survivor, 'build')
    cost = {k: max(1, math.ceil(v * discount)) for k, v in furn['cost'].items()}
    if not can_afford(cost):
        flash('材料不够(废料只能靠采集/远征捡)', 'error')
        return redirect(url_for('build_page'))
    if not try_spend_energy(survivor['id'], 'build'):
        flash('体力不足', 'error')
        return redirect(url_for('build_page'))
    spend_resources(cost)
    run("INSERT INTO survivor_items (owner_id, item_type, item_key, status, created_ts) VALUES (?,?,?,'inventory',?)",
        (survivor['id'], 'furniture', key, now_ts()))
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '打造', f"做了一件{furn['name']}")
    flash(f"做了一件{furn['name']},去集市上架或者装进自己房间", 'ok')
    return redirect(url_for('build_page'))

@app.route('/build/repair/<int:slot_id>', methods=['POST'])
@login_required
def build_repair(slot_id):
    survivor = current_survivor()
    slot = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not slot or slot['type'] == 'empty':
        flash('这个位置没有建筑', 'error')
        return redirect(url_for('build_page'))
    missing = slot['max_hp'] - slot['hp']
    if missing <= 0:
        flash('这个建筑不需要维修', 'error')
        return redirect(url_for('build_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('build_page'))
    discount = profession_cost_discount(survivor, 'build')
    cost = {'wood': max(1, math.ceil(missing * 0.4 * discount)), 'metal': max(1, math.ceil(missing * 0.15 * discount))}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('build_page'))
    if not try_spend_energy(survivor['id'], 'repair'):
        flash('体力不足', 'error')
        return redirect(url_for('build_page'))
    spend_resources(cost)
    run("UPDATE buildings SET hp=max_hp, updated_ts=? WHERE slot_index=?", (now_ts(), slot_id))
    add_contribution(survivor['id'], 2)
    bt_name = BUILDING_TYPES[slot['type']]['name']
    log_action(survivor['id'], survivor['name'], '维修', f"修好了#{slot_id}的{bt_name}")
    flash(f"{bt_name}修好了", 'ok')
    return redirect(url_for('build_page'))

@app.route('/build/demolish/<int:slot_id>', methods=['POST'])
@login_required
def build_demolish(slot_id):
    survivor = current_survivor()
    slot = q("SELECT * FROM buildings WHERE slot_index=?", (slot_id,), one=True)
    if not slot or slot['type'] == 'empty':
        flash('这个位置没有建筑', 'error')
        return redirect(url_for('build_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('build_page'))
    if not try_spend_energy(survivor['id'], 'demolish'):
        flash('体力不足', 'error')
        return redirect(url_for('build_page'))
    bt = BUILDING_TYPES[slot['type']]
    invested = total_invested_cost(slot['type'], slot['level'])
    refund = {k: math.floor(v * DEMOLISH_REFUND_RATIO) for k, v in invested.items()}
    refund = {k: v for k, v in refund.items() if v > 0}
    for k, v in refund.items():
        add_resource(k, v)
    run("UPDATE buildings SET type='empty', level=0, hp=0, max_hp=0, crop_type='', ready_ts=0, built_by=0, updated_ts=? WHERE slot_index=?",
        (now_ts(), slot_id))
    refund_text = ', '.join(f"{RESOURCE_NAMES.get(k, k)}+{v}" for k, v in refund.items()) or '没有资源返还'
    log_action(survivor['id'], survivor['name'], '拆除', f"拆掉了#{slot_id}的{bt['name']},返还{refund_text}")
    flash(f"拆除了{bt['name']},返还了{refund_text}", 'ok')
    return redirect(url_for('build_page'))

# ── 外勤:巡逻 / 采集 ────────────────────────────────────────────────────────────

SCAVENGE_INJURY_CHANCE = 0.18
PATROL_BASE_POINTS = 10

# ── 组队探索:回合制,替代原来单人一次性掷骰的出击/远征 ──────────────────────────────

MONSTER_TYPES = {
    'walker':  {'name': '普通丧尸',   'hp': 50,  'attack': 8,
                'loot': {'wood': (10, 20), 'metal': (5, 15), 'crystal_core': (2, 5), 'raw_water': (10, 25), 'resonance_core': (3, 6)}},
    'runner':  {'name': '疾行者',     'hp': 40,  'attack': 12,
                'loot': {'ammo': (10, 20), 'medicine': (5, 10), 'crystal_core': (3, 6), 'raw_water': (8, 20), 'resonance_core': (2, 5)}},
    'brute':   {'name': '狂暴丧尸',   'hp': 90,  'attack': 16,
                'loot': {'metal': (20, 35), 'research': (10, 20), 'crystal_core': (5, 10), 'resonance_core': (6, 12)}},
    'horde':   {'name': '小型丧尸群', 'hp': 130, 'attack': 10,
                'loot': {'wood': (30, 50), 'metal': (30, 50), 'ammo': (20, 30), 'crystal_core': (8, 15), 'resonance_core': (10, 18)}},
    'carrier': {'name': '感染源',     'hp': 70,  'attack': 14, 'infect_chance': 0.15,
                'loot': {'medicine': (10, 20), 'crystal_core': (6, 12), 'resonance_core': (8, 14)}},
}
EXPEDITION_CRIT_CHANCE = 0.10       # 会心一击基础概率,幸运属性再加成
MONSTER_CRIT_CHANCE = 0.15          # 怪物暴击概率,固定不受玩家属性影响
EXPEDITION_ENERGY_COST_KEY = 'hunt'  # 沿用现有 hunt 的体力/弹药/专精折扣设置,不新造一套

INFECTION_CHANCE = 0.05             # 怪物打中普通目标时额外判定的感染概率,独立于伤害判定
INFECTION_DAYS_LIMIT = 2            # 感染后这么多天不治疗就直接变成丧尸(permadead,不给重生)
INFECTION_CURE_COST = {'medicine': 25, 'bandage': 15}

MAPS = {
    'suburbs':     {'name': '近郊废墟', 'tier': 1, 'progress_required': 0,   'monsters': ['walker'],
                     'resource_chance': 0.18, 'loot_table': {'wood': (10, 20), 'metal': (5, 15), 'blueprint': (0, 1)}},
    'supermarket': {'name': '废弃超市', 'tier': 2, 'progress_required': 60,  'monsters': ['walker', 'runner'],
                     'resource_chance': 0.20, 'loot_table': {'medicine': (8, 18), 'ammo': (10, 20), 'blueprint': (1, 2)}},
    'armory':      {'name': '旧军械库', 'tier': 3, 'progress_required': 140, 'monsters': ['runner', 'brute'],
                     'resource_chance': 0.22, 'loot_table': {'metal': (25, 45), 'crystal_core': (5, 10), 'blueprint': (1, 3)},
                     'weapon_rd_bonus': (5, 15)},
    'hospital':    {'name': '医院',     'tier': 4, 'progress_required': 260, 'monsters': ['brute', 'horde', 'carrier'],
                     'resource_chance': 0.25, 'loot_table': {'medicine': (15, 30), 'crystal_core': (8, 15), 'blueprint': (2, 4)},
                     'weapon_rd_bonus': (10, 25)},
}
MAP_ORDER = ['suburbs', 'supermarket', 'armory', 'hospital']
MAP_PROGRESS_PER_ATTEMPT = 2   # 不论输赢,每次交手都给当前地图的探索进度条+2

def available_monsters(map_key):
    keys = MAPS.get(map_key, {}).get('monsters', [])
    return {k: MONSTER_TYPES[k] for k in keys if k in MONSTER_TYPES}

def map_progress_row(map_key):
    return q("SELECT * FROM map_progress WHERE map_key=?", (map_key,), one=True)

def unlocked_maps():
    rows = {r['map_key']: r for r in q("SELECT * FROM map_progress")}
    return [k for k in MAP_ORDER if rows.get(k) and rows[k]['unlocked']]

def advance_map_progress(map_key):
    """每次交手给地图进度条加量,攒够就解锁地图顺序里的下一张,返回新解锁的地图 key(没有解锁则 None)。"""
    row = map_progress_row(map_key)
    if not row:
        run("INSERT INTO map_progress (map_key, progress, unlocked) VALUES (?,?,1)", (map_key, 0))
        row = map_progress_row(map_key)
    new_progress = row['progress'] + MAP_PROGRESS_PER_ATTEMPT
    run("UPDATE map_progress SET progress=? WHERE map_key=?", (new_progress, map_key))
    idx = MAP_ORDER.index(map_key) if map_key in MAP_ORDER else -1
    if idx < 0 or idx + 1 >= len(MAP_ORDER):
        return None
    next_key = MAP_ORDER[idx + 1]
    next_row = map_progress_row(next_key)
    if next_row and next_row['unlocked']:
        return None
    if new_progress >= MAPS[next_key]['progress_required']:
        if next_row:
            run("UPDATE map_progress SET unlocked=1 WHERE map_key=?", (next_key,))
        else:
            run("INSERT INTO map_progress (map_key, progress, unlocked) VALUES (?,0,1)", (next_key,))
        return next_key
    return None

def log_expedition(expedition_id, round_number, text):
    run("INSERT INTO expedition_log (expedition_id, round_number, text, created_ts) VALUES (?,?,?,?)",
        (expedition_id, round_number, text, now_ts()))

RESONANCE_CORE_SCAVENGE_CHANCE = 0.2  # 采集稀有档小概率捡到共振核心,不是常规产出

def _random_seed_loot():
    crop_key = random.choice(list(available_crops().keys()))
    crop = CROPS[crop_key]
    loot = {crop['seed_key']: random.randint(8, 18), 'medicine': random.randint(2, 5)}
    if crop.get('edible', True):
        loot[crop['output_key']] = random.randint(20, 40)
    if random.random() < RESONANCE_CORE_SCAVENGE_CHANCE:
        loot['resonance_core'] = random.randint(1, 3)
    return loot

SCAVENGE_LOOT_TABLE = [
    ('common', 0.45, lambda: {'wood': random.randint(8, 20), 'metal': random.randint(3, 10), 'raw_water': random.randint(5, 15)}),
    ('uncommon', 0.30, lambda: {'medicine': random.randint(3, 8), 'ammo': random.randint(4, 10), 'bandage': random.randint(2, 6), 'scrap': random.randint(3, 8)}),
    ('rare', 0.25, _random_seed_loot),
]

@app.route('/field')
@login_required
def field_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    current_exp = current_expedition_for(survivor['id'])
    others = q("SELECT * FROM survivors WHERE id!=? AND status NOT IN ('dead','permadead') ORDER BY name",
               (survivor['id'],))
    names = {s['id']: s['name'] for s in q("SELECT id, name FROM survivors")}
    incoming_invites = q("SELECT * FROM expeditions WHERE member_b_id=? AND status='inviting' ORDER BY id DESC",
                         (survivor['id'],))
    outgoing_invites = q("SELECT * FROM expeditions WHERE member_a_id=? AND status='inviting' ORDER BY id DESC",
                         (survivor['id'],))
    map_rows = {r['map_key']: r for r in q("SELECT * FROM map_progress")}
    map_states = []
    for idx, key in enumerate(MAP_ORDER):
        row = map_rows.get(key)
        unlocked = bool(row and row['unlocked'])
        # 探索进度攒在"当前能去的那张地图"的 map_progress 行上,不是攒在被解锁的这张地图自己身上,
        # 所以还没解锁的地图要去看前一张地图(玩家实际在打的那张)的进度,不能看自己(永远是0)。
        if not unlocked and idx > 0:
            prev_row = map_rows.get(MAP_ORDER[idx - 1])
            progress = prev_row['progress'] if prev_row else 0
        else:
            progress = row['progress'] if row else 0
        map_states.append({
            'key': key, 'name': MAPS[key]['name'],
            'unlocked': unlocked,
            'progress': progress,
            'progress_required': MAPS[key]['progress_required'],
        })
    exp_map_name = MAPS.get(current_exp['map_key'], {}).get('name', '') if current_exp else ''
    return render_template('field.html', survivor=survivor, patrol_cost=ENERGY_COSTS['patrol'],
                           scavenge_cost=ENERGY_COSTS['scavenge'],
                           ammo_patrol=AMMO_COST_PATROL, ammo_hunt=AMMO_COST_HUNT,
                           expedition_energy_cost=ENERGY_COSTS['hunt'],
                           expedition_unlocked=is_tech_unlocked('expedition'), max_energy=get_max_energy(survivor),
                           patrol_points=round(float(get_meta('patrol_points_today', '0') or 0), 1),
                           horde_reduction=round(float(get_meta('horde_reduction_today', '0') or 0), 1),
                           current_expedition=current_exp, others=others, names=names,
                           incoming_invites=incoming_invites, outgoing_invites=outgoing_invites,
                           map_states=map_states, exp_map_name=exp_map_name, maps=MAPS)

@app.route('/field/patrol', methods=['POST'])
@login_required
def field_patrol():
    survivor = current_survivor()
    if survivor['status'] == 'critical':
        flash('你身负重伤,不能去巡逻', 'error')
        return redirect(url_for('field_page'))
    ammo_cost = max(1, math.ceil(AMMO_COST_PATROL * profession_cost_discount(survivor, 'hunt')))
    if get_resource('ammo') < ammo_cost:
        flash('弹药不够了,巡逻需要弹药', 'error')
        return redirect(url_for('field_page'))
    if not try_spend_energy(survivor['id'], 'patrol'):
        flash('体力不足', 'error')
        return redirect(url_for('field_page'))
    spend_resources({'ammo': ammo_cost})
    weapon_bonus = effective_weapon_bonus(survivor) * 4
    if survivor['weapon_level'] > 0 and survivor['weapon_durability'] > 0:
        run("UPDATE survivors SET weapon_durability=MAX(0,weapon_durability-1) WHERE id=?", (survivor['id'],))
    points = round(PATROL_BASE_POINTS * get_level_mult(survivor) + weapon_bonus, 1)
    total = float(get_meta('patrol_points_today', '0') or 0) + points
    set_meta('patrol_points_today', total)
    add_contribution(survivor['id'], 2)
    log_action(survivor['id'], survivor['name'], '巡逻', f"巡逻了围墙,为今晚的防御贡献了{points}点")
    flash(f"巡逻结束,贡献了{points}点防御值", 'ok')
    growth = maybe_grant_stat_growth(survivor['id'], ['stat_strength', 'stat_agility'])
    if growth:
        flash(f"实战经验让你的{growth}提升了1点", 'ok')
    return redirect(url_for('field_page'))

@app.route('/field/scavenge', methods=['POST'])
@login_required
def field_scavenge():
    survivor = current_survivor()
    if survivor['status'] == 'critical':
        flash('你身负重伤,不能外出', 'error')
        return redirect(url_for('field_page'))
    if not try_spend_energy(survivor['id'], 'scavenge'):
        flash('体力不足', 'error')
        return redirect(url_for('field_page'))
    is_scavenger = survivor['specialization'] == 'scavenger'
    injury_chance = SCAVENGE_INJURY_CHANCE * (0.6 if is_scavenger else 1.0) * (1 - 0.15 * effective_weapon_bonus(survivor)) * injury_chance_factor(survivor)
    roll = random.random()
    if roll < injury_chance:
        dmg = strength_damage_reduction(survivor, max(3, random.randint(10, 25) - 3 * survivor['gear_level']))
        apply_health_delta(survivor['id'], -dmg)
        log_action(survivor['id'], survivor['name'], '采集', f"外出时遭遇了丧尸,受伤{dmg}点,空手而归")
        flash(f"遇到了丧尸!受伤{dmg}点,这次没能带回物资", 'error')
        return redirect(url_for('field_page'))
    tier_roll = min(1.0, random.random() + 0.02 * (survivor['stat_luck'] - STAT_BASE))
    acc = 0.0
    loot_fn = SCAVENGE_LOOT_TABLE[-1][2]
    tier_name = SCAVENGE_LOOT_TABLE[-1][0]
    for name, weight, fn in SCAVENGE_LOOT_TABLE:
        acc += weight
        if tier_roll <= acc:
            loot_fn, tier_name = fn, name
            break
    loot = loot_fn()
    loot_mult = (1.2 if is_scavenger else 1.0) * get_level_mult(survivor) * stat_mult(survivor, 'stat_luck')
    loot = {k: round(v * loot_mult) for k, v in loot.items()}
    for k, v in loot.items():
        add_resource(k, v)
    add_contribution(survivor['id'], 4)
    desc = '、'.join(f"{RESOURCE_NAMES.get(k,k)}+{v}" for k, v in loot.items())
    log_action(survivor['id'], survivor['name'], '采集', f"外出采集({tier_name}),带回了{desc}")
    flash(f"满载而归:{desc}", 'ok')
    return redirect(url_for('field_page'))

def current_expedition_for(survivor_id):
    """返回这个人正参与的探索(inviting/exploring/active 状态),没有则 None。"""
    return q("SELECT * FROM expeditions WHERE (member_a_id=? OR member_b_id=?) AND status IN ('inviting','exploring','active')",
              (survivor_id, survivor_id), one=True)

@app.route('/expedition/invite/<int:target_id>', methods=['POST'])
@login_required
def expedition_invite(target_id):
    survivor = current_survivor()
    target = q("SELECT * FROM survivors WHERE id=?", (target_id,), one=True)
    if not target or target['id'] == survivor['id']:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('field_page'))
    if target['status'] in ('dead', 'permadead'):
        flash(f"{target['name']} 已经倒下了,叫不动", 'error')
        return redirect(url_for('field_page'))
    if not is_tech_unlocked('expedition'):
        flash('还没有解锁远征路线', 'error')
        return redirect(url_for('field_page'))
    map_key = request.form.get('map_key', '')
    if map_key not in MAPS or map_key not in unlocked_maps():
        flash('选一张已解锁的地图', 'error')
        return redirect(url_for('field_page'))
    if current_expedition_for(survivor['id']):
        flash('你已经在一场探索里了', 'error')
        return redirect(url_for('field_page'))
    if current_expedition_for(target_id):
        flash(f"{target['name']} 已经在别的探索里了", 'error')
        return redirect(url_for('field_page'))
    run("INSERT INTO expeditions (member_a_id, member_b_id, map_key, status, created_ts, updated_ts) VALUES (?,?,?,'inviting',?,?)",
        (survivor['id'], target_id, map_key, now_ts(), now_ts()))
    log_action(survivor['id'], survivor['name'], '组队', f"邀请{target['name']}一起去{MAPS[map_key]['name']}探索")
    flash(f"已邀请{target['name']},等待对方回应", 'ok')
    return redirect(url_for('field_page'))

@app.route('/expedition/accept/<int:expedition_id>', methods=['POST'])
@login_required
def expedition_accept(expedition_id):
    survivor = current_survivor()
    exp = q("SELECT * FROM expeditions WHERE id=? AND member_b_id=? AND status='inviting'",
            (expedition_id, survivor['id']), one=True)
    if not exp:
        flash('没有这条邀请', 'error')
        return redirect(url_for('field_page'))
    member_a = q("SELECT * FROM survivors WHERE id=?", (exp['member_a_id'],), one=True)
    if not member_a or member_a['status'] in ('dead', 'permadead', 'critical'):
        flash('对方现在没法出发', 'error')
        return redirect(url_for('field_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,不能出门', 'error')
        return redirect(url_for('field_page'))
    # 用没打折的基础体力消耗做保守预检查,确认两人都够了再真正扣,避免扣了一半发现另一半不够
    if get_effective_energy(member_a['id']) < ENERGY_COSTS['hunt'] or get_effective_energy(survivor['id']) < ENERGY_COSTS['hunt']:
        flash('有人体力不够,没法两人一起出发', 'error')
        return redirect(url_for('field_page'))
    try_spend_energy(member_a['id'], 'hunt')
    try_spend_energy(survivor['id'], 'hunt')
    run("UPDATE expeditions SET status='exploring', updated_ts=? WHERE id=?", (now_ts(), expedition_id))
    log_expedition(expedition_id, 0, f"{member_a['name']}和{survivor['name']}一起抵达了{MAPS[exp['map_key']]['name']},队长可以按'继续探索'寻找目标了")
    log_action(survivor['id'], survivor['name'], '组队', f"接受了邀请,和{member_a['name']}一起出发")
    flash('出发了!', 'ok')
    return redirect(url_for('expedition_battle', expedition_id=expedition_id))

@app.route('/expedition/explore/<int:expedition_id>', methods=['POST'])
@login_required
def expedition_explore(expedition_id):
    survivor = current_survivor()
    exp = q("SELECT * FROM expeditions WHERE id=? AND status='exploring'", (expedition_id,), one=True)
    if not exp or exp['member_a_id'] != survivor['id']:
        flash('只有队长能带队继续探索', 'error')
        return redirect(url_for('field_page'))
    member_a = q("SELECT * FROM survivors WHERE id=?", (exp['member_a_id'],), one=True)
    member_b = q("SELECT * FROM survivors WHERE id=?", (exp['member_b_id'],), one=True)
    if member_a['status'] in ('dead', 'permadead', 'critical') or member_b['status'] in ('dead', 'permadead', 'critical'):
        flash('队伍里有人撑不住了,先返回基地', 'error')
        return redirect(url_for('expedition_battle', expedition_id=expedition_id))
    ammo_cost_a = max(1, math.ceil(AMMO_COST_HUNT * profession_cost_discount(member_a, 'hunt')))
    ammo_cost_b = max(1, math.ceil(AMMO_COST_HUNT * profession_cost_discount(member_b, 'hunt')))
    if get_resource('ammo') < ammo_cost_a + ammo_cost_b:
        flash('弹药不够两人继续探索了,先返回基地', 'error')
        return redirect(url_for('expedition_battle', expedition_id=expedition_id))
    if get_effective_energy(member_a['id']) < ENERGY_COSTS['expedition_step'] or get_effective_energy(member_b['id']) < ENERGY_COSTS['expedition_step']:
        flash('有人体力不够继续探索了,先返回基地', 'error')
        return redirect(url_for('expedition_battle', expedition_id=expedition_id))
    spend_resources({'ammo': ammo_cost_a + ammo_cost_b})
    try_spend_energy(member_a['id'], 'expedition_step')
    try_spend_energy(member_b['id'], 'expedition_step')
    pool = available_monsters(exp['map_key'])
    monster_key = random.choice(list(pool.keys()))
    monster = pool[monster_key]
    run("""UPDATE expeditions SET status='active', monster_key=?, monster_hp=?, monster_max_hp=?,
           round_number=1, action_a='', action_b='', updated_ts=? WHERE id=?""",
        (monster_key, monster['hp'], monster['hp'], now_ts(), expedition_id))
    log_expedition(expedition_id, 1, f"继续深入{MAPS[exp['map_key']]['name']},遭遇了{monster['name']}!")
    return redirect(url_for('expedition_battle', expedition_id=expedition_id))

@app.route('/expedition/return/<int:expedition_id>', methods=['POST'])
@login_required
def expedition_return(expedition_id):
    survivor = current_survivor()
    exp = q("SELECT * FROM expeditions WHERE id=? AND status='exploring'", (expedition_id,), one=True)
    if not exp or (exp['member_a_id'] != survivor['id'] and exp['member_b_id'] != survivor['id']):
        flash('没有这场探索', 'error')
        return redirect(url_for('field_page'))
    run("UPDATE expeditions SET status='returned', updated_ts=? WHERE id=?", (now_ts(), expedition_id))
    log_expedition(expedition_id, exp['round_number'], f"{survivor['name']}决定收队,两人满载而归")
    log_action(survivor['id'], survivor['name'], '探索', "带队返回了基地,结束了这趟探索")
    flash('已经返回基地', 'ok')
    return redirect(url_for('field_page'))

@app.route('/expedition/decline/<int:expedition_id>', methods=['POST'])
@login_required
def expedition_decline(expedition_id):
    survivor = current_survivor()
    exp = q("SELECT * FROM expeditions WHERE id=? AND member_b_id=? AND status='inviting'",
            (expedition_id, survivor['id']), one=True)
    if exp:
        run("UPDATE expeditions SET status='declined', updated_ts=? WHERE id=?", (now_ts(), expedition_id))
        flash('已拒绝', 'ok')
    return redirect(url_for('field_page'))

@app.route('/expedition/cancel/<int:expedition_id>', methods=['POST'])
@login_required
def expedition_cancel(expedition_id):
    survivor = current_survivor()
    exp = q("SELECT * FROM expeditions WHERE id=? AND member_a_id=? AND status='inviting'",
            (expedition_id, survivor['id']), one=True)
    if exp:
        run("UPDATE expeditions SET status='cancelled', updated_ts=? WHERE id=?", (now_ts(), expedition_id))
        flash('已取消邀请', 'ok')
    return redirect(url_for('field_page'))

@app.route('/expedition/<int:expedition_id>')
@login_required
def expedition_battle(expedition_id):
    survivor = current_survivor()
    exp = q("SELECT * FROM expeditions WHERE id=? AND (member_a_id=? OR member_b_id=?)",
            (expedition_id, survivor['id'], survivor['id']), one=True)
    if not exp:
        flash('没有这场探索', 'error')
        return redirect(url_for('field_page'))
    member_a = q("SELECT * FROM survivors WHERE id=?", (exp['member_a_id'],), one=True)
    member_b = q("SELECT * FROM survivors WHERE id=?", (exp['member_b_id'],), one=True)
    is_a = exp['member_a_id'] == survivor['id']
    my_action = exp['action_a'] if is_a else exp['action_b']
    logs = q("SELECT * FROM expedition_log WHERE expedition_id=? ORDER BY id DESC LIMIT 20", (expedition_id,))
    monster = MONSTER_TYPES.get(exp['monster_key'], {})
    map_info = MAPS.get(exp['map_key'], {})
    map_state = map_progress_row(exp['map_key'])
    next_map_name, next_map_required = None, None
    if exp['map_key'] in MAP_ORDER:
        idx = MAP_ORDER.index(exp['map_key'])
        if idx + 1 < len(MAP_ORDER):
            next_key = MAP_ORDER[idx + 1]
            next_map_name = MAPS[next_key]['name']
            next_map_required = MAPS[next_key]['progress_required']
    return render_template('expedition.html', exp=exp, member_a=member_a, member_b=member_b,
                           monster=monster, my_action=my_action, logs=logs, is_a=is_a,
                           map_info=map_info, map_state=map_state,
                           next_map_name=next_map_name, next_map_required=next_map_required)

def _expedition_crit_chance(survivor):
    return min(0.6, EXPEDITION_CRIT_CHANCE + 0.01 * (survivor['stat_luck'] - STAT_BASE))

def _resolve_expedition_round(exp):
    expedition_id = exp['id']
    member_a = q("SELECT * FROM survivors WHERE id=?", (exp['member_a_id'],), one=True)
    member_b = q("SELECT * FROM survivors WHERE id=?", (exp['member_b_id'],), one=True)
    members = [(member_a, exp['action_a']), (member_b, exp['action_b'])]
    monster = MONSTER_TYPES[exp['monster_key']]
    round_number = exp['round_number']

    total_damage = 0
    lines = []
    for member, action in members:
        if action != 'attack':
            continue
        base = (effective_weapon_bonus(member) * 3 + stat_mult(member, 'stat_strength') * 5) \
            * specialization_mult(member, 'hunt') * get_level_mult(member)
        crit = random.random() < _expedition_crit_chance(member)
        dmg = max(1, round(base * (2 if crit else 1)))
        total_damage += dmg
        if member['weapon_level'] > 0 and member['weapon_durability'] > 0:
            run("UPDATE survivors SET weapon_durability=MAX(0,weapon_durability-1) WHERE id=?", (member['id'],))
        lines.append(f"{member['name']} 发起攻击,{'会心一击!' if crit else ''}造成{dmg}点伤害")

    new_monster_hp = max(0, exp['monster_hp'] - total_damage)
    lines.append(f"{monster['name']} 剩余{new_monster_hp}/{exp['monster_max_hp']}点血量")

    attackable = [m for m, a in members if a != 'defend']
    if new_monster_hp > 0 and attackable:
        target = random.choice(attackable)
        crit = random.random() < MONSTER_CRIT_CHANCE
        raw_dmg = monster['attack'] * (2 if crit else 1)
        dmg = strength_damage_reduction(target, max(1, raw_dmg - 3 * target['gear_level']))
        apply_health_delta(target['id'], -dmg)
        lines.append(f"{monster['name']}{'暴击' if crit else ''}反击了{target['name']},造成{dmg}点伤害")
        if not target['infected'] and random.random() < monster.get('infect_chance', INFECTION_CHANCE):
            day = q("SELECT day_count FROM base_state WHERE id=1", one=True)['day_count']
            run("UPDATE survivors SET infected=1, infected_since_day=? WHERE id=?", (day, target['id']))
            lines.append(f"{target['name']}被咬伤了,伤口有点不对劲,可能感染了……")
    elif new_monster_hp > 0:
        lines.append(f"两人都选择了防御,{monster['name']}这回合没能得手")

    for text in lines:
        log_expedition(expedition_id, round_number, text)

    member_a = q("SELECT * FROM survivors WHERE id=?", (exp['member_a_id'],), one=True)
    member_b = q("SELECT * FROM survivors WHERE id=?", (exp['member_b_id'],), one=True)

    if new_monster_hp <= 0:
        loot_mult = (stat_mult(member_a, 'stat_luck') + stat_mult(member_b, 'stat_luck')) / 2
        loot = {k: max(1, round(random.randint(lo, hi) * loot_mult)) for k, (lo, hi) in monster['loot'].items()}
        for k, v in loot.items():
            add_resource(k, v)
        for member in (member_a, member_b):
            add_contribution(member['id'], 8)
            growth = maybe_grant_stat_growth(member['id'], ['stat_strength', 'stat_agility'])
            if growth:
                log_expedition(expedition_id, round_number, f"{member['name']}的实战经验让{growth}提升了1点")
        reduction = round(monster['attack'] * 1.5, 1)
        total_reduction = float(get_meta('horde_reduction_today', '0') or 0) + reduction
        set_meta('horde_reduction_today', total_reduction)
        desc = '、'.join(f"{RESOURCE_NAMES.get(k,k)}+{v}" for k, v in loot.items())
        log_expedition(expedition_id, round_number, f"击败了{monster['name']}!带回了{desc}")
        log_event('expedition', f"{member_a['name']}和{member_b['name']}组队击败了{monster['name']},今晚丧尸潮强度-{reduction}")

        map_key = exp['map_key']
        map_info = MAPS.get(map_key, {})
        newly_unlocked = advance_map_progress(map_key)
        if newly_unlocked:
            log_expedition(expedition_id, round_number, f"这一路的探索让队伍摸清了往{MAPS[newly_unlocked]['name']}去的路,新地图解锁了!")
            log_event('expedition', f"探索进度解锁了新地图:{MAPS[newly_unlocked]['name']}")
        if map_info and random.random() < map_info.get('resource_chance', 0):
            chest = {k: max(1, round(random.randint(lo, hi) * loot_mult)) for k, (lo, hi) in map_info.get('loot_table', {}).items()}
            for k, v in chest.items():
                add_resource(k, v)
            if 'weapon_rd_bonus' in map_info:
                lo, hi = map_info['weapon_rd_bonus']
                bonus = round(random.randint(lo, hi) * loot_mult, 1)
                before = float(get_meta('weapon_rd_progress', '0') or 0)
                set_meta('weapon_rd_progress', before + bonus)
                chest['__weapon_rd'] = bonus
            chest_desc = '、'.join(
                (f"军械研发进度+{v}" if k == '__weapon_rd' else f"{RESOURCE_NAMES.get(k,k)}+{v}")
                for k, v in chest.items())
            log_expedition(expedition_id, round_number, f"路上还发现了一个资源点,顺手带回了{chest_desc}")

        run("""UPDATE expeditions SET monster_key='', monster_hp=0, monster_max_hp=0, status='exploring',
               updated_ts=? WHERE id=?""", (now_ts(), expedition_id))
        return

    if member_a['status'] in ('dead', 'permadead', 'critical') or member_b['status'] in ('dead', 'permadead', 'critical'):
        log_expedition(expedition_id, round_number, "有人撑不住了,两人被迫撤退")
        advance_map_progress(exp['map_key'])
        run("UPDATE expeditions SET status='lost', updated_ts=? WHERE id=?", (now_ts(), expedition_id))
        return

    run("""UPDATE expeditions SET monster_hp=?, round_number=round_number+1, action_a='', action_b='',
           updated_ts=? WHERE id=?""", (new_monster_hp, now_ts(), expedition_id))

@app.route('/expedition/action/<int:expedition_id>', methods=['POST'])
@login_required
def expedition_action(expedition_id):
    survivor = current_survivor()
    action = request.form.get('action', '')
    if action not in ('attack', 'defend', 'flee'):
        flash('无效的动作', 'error')
        return redirect(url_for('expedition_battle', expedition_id=expedition_id))
    exp = q("SELECT * FROM expeditions WHERE id=? AND status='active'", (expedition_id,), one=True)
    if not exp or (exp['member_a_id'] != survivor['id'] and exp['member_b_id'] != survivor['id']):
        flash('没有这场探索', 'error')
        return redirect(url_for('field_page'))
    is_a = exp['member_a_id'] == survivor['id']
    if (is_a and exp['action_a']) or (not is_a and exp['action_b']):
        flash('你已经交过这回合的动作了', 'error')
        return redirect(url_for('expedition_battle', expedition_id=expedition_id))
    if action == 'flee':
        run("UPDATE expeditions SET status='fled', updated_ts=? WHERE id=?", (now_ts(), expedition_id))
        log_expedition(expedition_id, exp['round_number'], f"{survivor['name']}决定撤退,两人放弃了这次探索")
        log_action(survivor['id'], survivor['name'], '探索', "选择撤退,放弃了这次探索")
        flash('已经撤退', 'ok')
        return redirect(url_for('expedition_battle', expedition_id=expedition_id))
    if is_a:
        run("UPDATE expeditions SET action_a=?, updated_ts=? WHERE id=?", (action, now_ts(), expedition_id))
    else:
        run("UPDATE expeditions SET action_b=?, updated_ts=? WHERE id=?", (action, now_ts(), expedition_id))
    exp = q("SELECT * FROM expeditions WHERE id=?", (expedition_id,), one=True)
    if exp['action_a'] and exp['action_b']:
        _resolve_expedition_round(exp)
    return redirect(url_for('expedition_battle', expedition_id=expedition_id))

# ── 诊所 ─────────────────────────────────────────────────────────────────────

HEAL_MEDICINE_COST = 10
HEAL_BASE = 25

@app.route('/clinic')
@login_required
def clinic_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    clinics = q("SELECT * FROM buildings WHERE type='clinic'")
    others = q("SELECT * FROM survivors WHERE id!=? ORDER BY health ASC", (survivor['id'],))
    sick = q("SELECT * FROM survivors WHERE illness!='' AND status NOT IN ('dead','permadead') ORDER BY illness_started_ts ASC")
    infected_list = q("SELECT * FROM survivors WHERE infected=1 AND status NOT IN ('dead','permadead') ORDER BY infected_since_day ASC")
    day_now = q("SELECT day_count FROM base_state WHERE id=1", one=True)['day_count']
    return render_template('clinic.html', survivor=survivor, clinics=clinics, others=others, sick=sick,
                           medicine_cost=HEAL_MEDICINE_COST, max_energy=get_max_energy(survivor),
                           craft_medicine_herb=CRAFT_MEDICINE_HERB, craft_medicine_bandage=CRAFT_MEDICINE_BANDAGE,
                           craft_medicine_output=CRAFT_MEDICINE_OUTPUT, illnesses=ILLNESSES,
                           infected_list=infected_list, infection_days_limit=INFECTION_DAYS_LIMIT,
                           infection_cure_cost=INFECTION_CURE_COST, day_now=day_now)

@app.route('/clinic/heal/<int:target_id>', methods=['POST'])
@login_required
def clinic_heal(target_id):
    survivor = current_survivor()
    target = q("SELECT * FROM survivors WHERE id=?", (target_id,), one=True)
    if not target:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('clinic_page'))
    if target['status'] in ('dead', 'permadead'):
        flash(f"{target['name']} 已经倒下了,诊所治不了,只能等他自己重生", 'error')
        return redirect(url_for('clinic_page'))
    if target['health'] >= MAX_HEALTH:
        flash('对方状态良好,不需要治疗', 'error')
        return redirect(url_for('clinic_page'))
    clinic_level_sum = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='clinic'", one=True)['s']
    if clinic_level_sum <= 0:
        flash('基地还没有诊所', 'error')
        return redirect(url_for('clinic_page'))
    medicine_cost = max(1, math.ceil(HEAL_MEDICINE_COST * profession_cost_discount(survivor, 'heal')))
    if get_resource('medicine') < medicine_cost:
        flash('药品不够了', 'error')
        return redirect(url_for('clinic_page'))
    if not try_spend_energy(survivor['id'], 'heal'):
        flash('体力不足', 'error')
        return redirect(url_for('clinic_page'))
    spend_resources({'medicine': medicine_cost})
    mult = specialization_mult(survivor, 'heal') * get_level_mult(survivor)
    heal_amount = round((HEAL_BASE + clinic_level_sum * BUILDING_TYPES['clinic']['heal_bonus_per_level']) * mult)
    apply_health_delta(target_id, heal_amount)
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '治疗', f"为{target['name']}治疗,恢复了{heal_amount}点健康")
    flash(f"为{target['name']}治疗,恢复了{heal_amount}点健康", 'ok')
    return redirect(url_for('clinic_page'))

@app.route('/clinic/cure-illness/<int:target_id>', methods=['POST'])
@login_required
def clinic_cure_illness(target_id):
    survivor = current_survivor()
    target = q("SELECT * FROM survivors WHERE id=?", (target_id,), one=True)
    if not target:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('clinic_page'))
    if target['status'] in ('dead', 'permadead'):
        flash(f"{target['name']} 已经倒下了,只能等他自己重生", 'error')
        return redirect(url_for('clinic_page'))
    if not target['illness']:
        flash(f"{target['name']} 没有生病", 'error')
        return redirect(url_for('clinic_page'))
    clinic_level_sum = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='clinic'", one=True)['s']
    if clinic_level_sum <= 0:
        flash('基地还没有诊所', 'error')
        return redirect(url_for('clinic_page'))
    info = ILLNESSES[target['illness']]
    cost = {k: max(1, math.ceil(v * profession_cost_discount(survivor, 'heal'))) for k, v in info['cure_cost'].items()}
    if not can_afford(cost):
        flash('药品不够了', 'error')
        return redirect(url_for('clinic_page'))
    if not try_spend_energy(survivor['id'], 'heal'):
        flash('体力不足', 'error')
        return redirect(url_for('clinic_page'))
    spend_resources(cost)
    run("UPDATE survivors SET illness='', illness_started_ts=0 WHERE id=?", (target_id,))
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '治病', f"治好了{target['name']}的{info['name']}")
    flash(f"治好了{target['name']}的{info['name']}", 'ok')
    return redirect(url_for('clinic_page'))

@app.route('/clinic/cure-infection/<int:target_id>', methods=['POST'])
@login_required
def clinic_cure_infection(target_id):
    survivor = current_survivor()
    target = q("SELECT * FROM survivors WHERE id=?", (target_id,), one=True)
    if not target:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('clinic_page'))
    if target['status'] in ('dead', 'permadead'):
        flash(f"{target['name']} 已经倒下了,只能等他自己重生", 'error')
        return redirect(url_for('clinic_page'))
    if not target['infected']:
        flash(f"{target['name']} 没有感染", 'error')
        return redirect(url_for('clinic_page'))
    clinic_level_sum = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='clinic'", one=True)['s']
    if clinic_level_sum <= 0:
        flash('基地还没有诊所', 'error')
        return redirect(url_for('clinic_page'))
    cost = {k: max(1, math.ceil(v * profession_cost_discount(survivor, 'heal'))) for k, v in INFECTION_CURE_COST.items()}
    if not can_afford(cost):
        flash('药品不够了', 'error')
        return redirect(url_for('clinic_page'))
    if not try_spend_energy(survivor['id'], 'heal'):
        flash('体力不足', 'error')
        return redirect(url_for('clinic_page'))
    spend_resources(cost)
    run("UPDATE survivors SET infected=0, infected_since_day=0 WHERE id=?", (target_id,))
    add_contribution(survivor['id'], 5)
    log_action(survivor['id'], survivor['name'], '治疗感染', f"及时治好了{target['name']}的感染,把人从丧尸边缘拉了回来")
    flash(f"治好了{target['name']}的感染", 'ok')
    return redirect(url_for('clinic_page'))

CRAFT_MEDICINE_HERB, CRAFT_MEDICINE_BANDAGE, CRAFT_MEDICINE_OUTPUT = 8, 5, 10

@app.route('/clinic/craft-medicine', methods=['POST'])
@login_required
def clinic_craft_medicine():
    survivor = current_survivor()
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('clinic_page'))
    if get_resource('herb') < CRAFT_MEDICINE_HERB or get_resource('bandage') < CRAFT_MEDICINE_BANDAGE:
        flash('药草或绷带不够了(药草可以自己种,绷带要靠采集/远征捡)', 'error')
        return redirect(url_for('clinic_page'))
    if not try_spend_energy(survivor['id'], 'craft_medicine'):
        flash('体力不足', 'error')
        return redirect(url_for('clinic_page'))
    spend_resources({'herb': CRAFT_MEDICINE_HERB, 'bandage': CRAFT_MEDICINE_BANDAGE})
    mult = specialization_mult(survivor, 'heal') * get_level_mult(survivor) * stat_mult(survivor, 'stat_education')
    output = round(CRAFT_MEDICINE_OUTPUT * mult)
    add_resource('medicine', output)
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '制药', f"用药草和绷带制出了{output}份药品")
    flash(f"制出了{output}份药品", 'ok')
    return redirect(url_for('clinic_page'))

# ── 厨房:把生鲜作物做成更好的食物 ──────────────────────────────────────────────────

RECIPES = {
    'meal':        {'name': '家常便饭',     'any_raw_cost': 20, 'output_key': 'food_meal',  'output_qty': 12, 'action_key': 'cook', 'recommended': None, 'contribution': 3},
    'soup':        {'name': '番茄土豆浓汤', 'specific_cost': {'raw_tomato': 12, 'raw_potato': 12}, 'output_key': 'food_meal', 'output_qty': 14, 'action_key': 'cook', 'recommended': None, 'contribution': 3},
    'veg_soup':    {'name': '杂菜汤',       'specific_cost': {'raw_cabbage': 10, 'raw_corn': 10}, 'output_key': 'food_meal', 'output_qty': 13, 'action_key': 'cook', 'recommended': None, 'contribution': 3},
    'bread':       {'name': '烤面包',       'specific_cost': {'raw_wheat': 18}, 'output_key': 'food_meal', 'output_qty': 13, 'action_key': 'cook', 'recommended': None, 'contribution': 3},
    'fruit_salad': {'name': '水果沙拉',     'specific_cost': {'raw_apple': 10, 'raw_grape': 10}, 'output_key': 'food_meal', 'output_qty': 13, 'action_key': 'cook', 'recommended': None, 'contribution': 3},
    'feast':       {'name': '佳肴',         'any_raw_cost': 35, 'output_key': 'food_feast', 'output_qty': 15, 'action_key': 'cook', 'recommended': 'chef', 'contribution': 5},
    'stew':        {'name': '白菜炖肉',     'specific_cost': {'raw_cabbage': 15, 'food_meat': 10}, 'output_key': 'food_feast', 'output_qty': 18, 'action_key': 'cook', 'recommended': 'chef', 'contribution': 5},
    'braised':     {'name': '红烧肉炖土豆', 'specific_cost': {'food_meat': 15, 'raw_potato': 15}, 'output_key': 'food_feast', 'output_qty': 20, 'action_key': 'cook', 'recommended': 'chef', 'contribution': 5},
    'pie':         {'name': '苹果派',       'specific_cost': {'raw_apple': 15, 'flour': 10, 'sugar': 8, 'butter': 8}, 'output_key': 'dish_pie', 'output_qty': 16, 'action_key': 'cook', 'recommended': 'chef', 'contribution': 6},
    'power_meal':  {'name': '力量拌肉',     'specific_cost': {'food_meat': 15, 'raw_potato': 10}, 'output_key': 'dish_power', 'output_qty': 14, 'action_key': 'cook', 'recommended': 'chef', 'contribution': 6},
    'wine':        {'name': '酿酒',         'specific_cost': {'raw_wheat': 20, 'water': 15}, 'output_key': 'wine', 'output_qty': 10, 'action_key': 'process', 'recommended': 'processor', 'contribution': 5},
}

@app.route('/kitchen')
@login_required
def kitchen_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    has_kitchen = q("SELECT 1 FROM buildings WHERE type='kitchen'", one=True) is not None
    return render_template('kitchen.html', survivor=survivor, has_kitchen=has_kitchen,
                           recipes=RECIPES, resource_names=RESOURCE_NAMES, specializations=SPECIALIZATIONS,
                           purify_input=PURIFY_WOOD_INPUT, purify_output=PURIFY_WATER_OUTPUT,
                           celebrate_wine_cost=CELEBRATE_WINE_COST, celebrate_morale_bonus=CELEBRATE_MORALE_BONUS,
                           celebrate_happiness_bonus=CELEBRATE_HAPPINESS_BONUS,
                           max_energy=get_max_energy(survivor))

@app.route('/kitchen/cook/<recipe_key>', methods=['POST'])
@login_required
def kitchen_cook(recipe_key):
    survivor = current_survivor()
    if recipe_key not in RECIPES:
        flash('没有这个菜谱', 'error')
        return redirect(url_for('kitchen_page'))
    recipe = RECIPES[recipe_key]
    if not q("SELECT 1 FROM buildings WHERE type='kitchen'", one=True):
        flash('基地还没有厨房', 'error')
        return redirect(url_for('kitchen_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('kitchen_page'))
    discount = profession_cost_discount(survivor, recipe['action_key'])
    if 'any_raw_cost' in recipe:
        raw_cost = max(1, math.ceil(recipe['any_raw_cost'] * discount))
        if sum(get_resource(k) for k in RAW_CROP_KEYS) < raw_cost:
            flash('生鲜作物不够了', 'error')
            return redirect(url_for('kitchen_page'))
    else:
        specific_cost = {k: max(1, round(v * discount)) for k, v in recipe['specific_cost'].items()}
        if not can_afford(specific_cost):
            flash('食材不够了', 'error')
            return redirect(url_for('kitchen_page'))
    energy_key = recipe['action_key'] if recipe['action_key'] in ENERGY_COSTS else 'cook'
    if not try_spend_energy(survivor['id'], energy_key):
        flash('体力不足', 'error')
        return redirect(url_for('kitchen_page'))
    if 'any_raw_cost' in recipe:
        spend_up_to_raw_crop(raw_cost)
    else:
        spend_resources(specific_cost)
    mult = specialization_mult(survivor, recipe['action_key']) * get_level_mult(survivor) * stat_mult(survivor, 'stat_intelligence')
    output = round(recipe['output_qty'] * mult)
    add_resource(recipe['output_key'], output)
    add_contribution(survivor['id'], recipe['contribution'])
    log_action(survivor['id'], survivor['name'], '烹饪', f"做出了{output}份{recipe['name']}")
    flash(f"做出了{output}份{recipe['name']}", 'ok')
    return redirect(url_for('kitchen_page'))

PURIFY_WOOD_INPUT, PURIFY_WATER_OUTPUT = 15, 25

@app.route('/kitchen/purify', methods=['POST'])
@login_required
def kitchen_purify():
    survivor = current_survivor()
    if not q("SELECT 1 FROM buildings WHERE type='kitchen'", one=True):
        flash('基地还没有厨房', 'error')
        return redirect(url_for('kitchen_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('kitchen_page'))
    if get_resource('wood') < PURIFY_WOOD_INPUT:
        flash('木材不够了(净水要烧火煮沸)', 'error')
        return redirect(url_for('kitchen_page'))
    if not try_spend_energy(survivor['id'], 'purify'):
        flash('体力不足', 'error')
        return redirect(url_for('kitchen_page'))
    spend_resources({'wood': PURIFY_WOOD_INPUT})
    mult = specialization_mult(survivor, 'process') * get_level_mult(survivor)
    output = round(PURIFY_WATER_OUTPUT * mult)
    add_resource('water', output)
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '净水', f"烧火煮出了{output}份净水")
    flash(f"净化出了{output}份净水", 'ok')
    return redirect(url_for('kitchen_page'))

CELEBRATE_WINE_COST, CELEBRATE_MORALE_BONUS, CELEBRATE_HAPPINESS_BONUS = 5, 8, 10

@app.route('/kitchen/celebrate', methods=['POST'])
@login_required
def kitchen_celebrate():
    survivor = current_survivor()
    if get_resource('wine') < CELEBRATE_WINE_COST:
        flash('酒不够了', 'error')
        return redirect(url_for('kitchen_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('kitchen_page'))
    if not try_spend_energy(survivor['id'], 'celebrate'):
        flash('体力不足', 'error')
        return redirect(url_for('kitchen_page'))
    spend_resources({'wine': CELEBRATE_WINE_COST})
    bonus = round(CELEBRATE_MORALE_BONUS * stat_mult(survivor, 'stat_appearance'))
    base = q("SELECT morale FROM base_state WHERE id=1", one=True)
    new_morale = min(100, base['morale'] + bonus)
    run("UPDATE base_state SET morale=? WHERE id=1", (new_morale,))
    add_happiness(survivor['id'], CELEBRATE_HAPPINESS_BONUS)
    add_contribution(survivor['id'], 2)
    log_action(survivor['id'], survivor['name'], '庆祝', f"开了瓶酒跟大家庆祝,基地士气+{bonus},自己也开心了不少")
    flash(f"庆祝了一下,士气+{bonus},自己的快乐值也涨了", 'ok')
    return redirect(url_for('kitchen_page'))

# ── 娱乐:回复个人快乐值 ────────────────────────────────────────────────────────

PLAY_HAPPINESS_BONUS = 15

@app.route('/entertainment')
@login_required
def entertainment_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    rec_rooms = q("SELECT * FROM buildings WHERE type='rec_room'")
    played_today = daily_count(survivor['id'], 'play') >= 1
    return render_template('entertainment.html', survivor=survivor, rec_rooms=rec_rooms,
                           played_today=played_today, max_energy=get_max_energy(survivor),
                           happiness_bonus=PLAY_HAPPINESS_BONUS)

@app.route('/entertainment/play', methods=['POST'])
@login_required
def entertainment_play():
    survivor = current_survivor()
    if not q("SELECT 1 FROM buildings WHERE type='rec_room'", one=True):
        flash('基地还没有娱乐室', 'error')
        return redirect(url_for('entertainment_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('entertainment_page'))
    if daily_count(survivor['id'], 'play') >= 1:
        flash('今天已经玩过了,明天再来', 'error')
        return redirect(url_for('entertainment_page'))
    if not try_spend_energy(survivor['id'], 'play'):
        flash('体力不足', 'error')
        return redirect(url_for('entertainment_page'))
    add_happiness(survivor['id'], PLAY_HAPPINESS_BONUS)
    daily_inc(survivor['id'], 'play')
    add_contribution(survivor['id'], 2)
    log_action(survivor['id'], survivor['name'], '娱乐', f"在娱乐室放松了一下,快乐值+{PLAY_HAPPINESS_BONUS}")
    flash(f"放松了一下,快乐值+{PLAY_HAPPINESS_BONUS}", 'ok')
    return redirect(url_for('entertainment_page'))

# ── 加工:把原材料转化成半成品 ────────────────────────────────────────────────────

PROCESS_RECIPES = {
    'flour':  {'name': '磨面粉',   'specific_cost': {'raw_wheat': 20},     'output_key': 'flour',  'output_qty': 12},
    'sugar':  {'name': '榨糖',     'specific_cost': {'raw_sugarcane': 20}, 'output_key': 'sugar',  'output_qty': 12},
    'butter': {'name': '提炼黄油', 'specific_cost': {'milk': 15},          'output_key': 'butter', 'output_qty': 10},
    'purify_raw_water': {'name': '净化生水', 'specific_cost': {'raw_water': 20}, 'output_key': 'water', 'output_qty': 15},
}

@app.route('/process')
@login_required
def process_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    return render_template('process.html', survivor=survivor, recipes=PROCESS_RECIPES, resource_names=RESOURCE_NAMES,
                           max_energy=get_max_energy(survivor), gift_types=GIFT_TYPES)

@app.route('/process/do/<recipe_key>', methods=['POST'])
@login_required
def process_do(recipe_key):
    survivor = current_survivor()
    if recipe_key not in PROCESS_RECIPES:
        flash('没有这个加工项目', 'error')
        return redirect(url_for('process_page'))
    recipe = PROCESS_RECIPES[recipe_key]
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('process_page'))
    cost = {k: max(1, round(v * profession_cost_discount(survivor, 'process'))) for k, v in recipe['specific_cost'].items()}
    if not can_afford(cost):
        flash('原料不够了', 'error')
        return redirect(url_for('process_page'))
    if not try_spend_energy(survivor['id'], 'process'):
        flash('体力不足', 'error')
        return redirect(url_for('process_page'))
    spend_resources(cost)
    mult = specialization_mult(survivor, 'process') * get_level_mult(survivor) * stat_mult(survivor, 'stat_intelligence')
    output = round(recipe['output_qty'] * mult)
    add_resource(recipe['output_key'], output)
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '加工', f"加工出了{output}份{RESOURCE_NAMES[recipe['output_key']]}")
    flash(f"加工出了{output}份{RESOURCE_NAMES[recipe['output_key']]}", 'ok')
    return redirect(url_for('process_page'))

@app.route('/process/craft-gift/<key>', methods=['POST'])
@login_required
def process_craft_gift(key):
    survivor = current_survivor()
    if key not in GIFT_TYPES:
        flash('没有这种礼物', 'error')
        return redirect(url_for('process_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('process_page'))
    gift = GIFT_TYPES[key]
    cost = {k: max(1, round(v * profession_cost_discount(survivor, 'process'))) for k, v in gift['cost'].items()}
    if not can_afford(cost):
        flash('材料不够了', 'error')
        return redirect(url_for('process_page'))
    if not try_spend_energy(survivor['id'], 'process'):
        flash('体力不足', 'error')
        return redirect(url_for('process_page'))
    spend_resources(cost)
    run("INSERT INTO survivor_items (owner_id, item_type, item_key, status, created_ts) VALUES (?,?,?,'inventory',?)",
        (survivor['id'], 'gift', key, now_ts()))
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '制作', f"做了一份{gift['name']}")
    flash(f"做了一份{gift['name']},去集市上架,或者别人买了以后可以通过信箱送人", 'ok')
    return redirect(url_for('process_page'))

# ── 学者:编写/学习教材,属性成长的另一条路径 ─────────────────────────────────────

@app.route('/scholar')
@login_required
def scholar_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    resources = {r['key']: r['amount'] for r in q("SELECT * FROM resources")}
    return render_template('scholar.html', survivor=survivor, textbooks=TEXTBOOKS, stats=STATS,
                           textbook_cost=TEXTBOOK_COST, resources=resources, resource_names=RESOURCE_NAMES,
                           stat_max=STAT_MAX, max_energy=get_max_energy(survivor))

@app.route('/scholar/craft/<stat_key>', methods=['POST'])
@login_required
def scholar_craft(stat_key):
    survivor = current_survivor()
    if stat_key not in TEXTBOOKS:
        flash('没有这种教材', 'error')
        return redirect(url_for('scholar_page'))
    tb = TEXTBOOKS[stat_key]
    if survivor[stat_key] < tb['threshold']:
        flash(f"你的{STATS[stat_key]['name']}还不够{tb['threshold']},写不出这本教材", 'error')
        return redirect(url_for('scholar_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('scholar_page'))
    cost = {k: max(1, round(v * int_discount(survivor) / specialization_mult(survivor, 'study'))) for k, v in TEXTBOOK_COST.items()}
    if not can_afford(cost):
        flash('原料不够了', 'error')
        return redirect(url_for('scholar_page'))
    if not try_spend_energy(survivor['id'], 'craft_textbook'):
        flash('体力不足', 'error')
        return redirect(url_for('scholar_page'))
    spend_resources(cost)
    add_resource(tb['resource_key'], 1)
    add_contribution(survivor['id'], 4)
    log_action(survivor['id'], survivor['name'], '编写', f"编写了一本{tb['name']}")
    flash(f"编写了一本{tb['name']}", 'ok')
    return redirect(url_for('scholar_page'))

@app.route('/scholar/study/<stat_key>', methods=['POST'])
@login_required
def scholar_study(stat_key):
    survivor = current_survivor()
    if stat_key not in TEXTBOOKS:
        flash('没有这种教材', 'error')
        return redirect(url_for('scholar_page'))
    tb = TEXTBOOKS[stat_key]
    if get_resource(tb['resource_key']) < 1:
        flash('没有这本教材了,先去编写或者等别人写', 'error')
        return redirect(url_for('scholar_page'))
    if survivor[stat_key] >= STAT_MAX:
        flash(f"{STATS[stat_key]['name']}已经到上限了", 'error')
        return redirect(url_for('scholar_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('scholar_page'))
    if not try_spend_energy(survivor['id'], 'study'):
        flash('体力不足', 'error')
        return redirect(url_for('scholar_page'))
    spend_resources({tb['resource_key']: 1})
    run(f"UPDATE survivors SET {stat_key}=MIN({STAT_MAX},{stat_key}+1) WHERE id=?", (survivor['id'],))
    log_action(survivor['id'], survivor['name'], '学习', f"学习了{tb['name']},{STATS[stat_key]['name']}+1")
    flash(f"学习完成,{STATS[stat_key]['name']}+1", 'ok')
    return redirect(url_for('scholar_page'))

# ── 装备:工坊打造武器/护甲 ──────────────────────────────────────────────────────

@app.route('/gear')
@login_required
def gear_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    has_workshop = q("SELECT 1 FROM buildings WHERE type='workshop'", one=True) is not None
    unlocked = is_tech_unlocked('workshop_gear')
    weapon_max = get_weapon_max_level()
    next_weapon = min(weapon_max, survivor['weapon_level'] + 1)
    next_gear = min(EQUIP_MAX_LEVEL, survivor['gear_level'] + 1)
    rd_progress = float(get_meta('weapon_rd_progress', '0') or 0)
    rd_gate = next_weapon_rd_gate(rd_progress)
    return render_template('gear.html', survivor=survivor, has_workshop=has_workshop, unlocked=unlocked,
                           weapon_cost=weapon_cost(next_weapon) if survivor['weapon_level'] < weapon_max else None,
                           gear_cost=gear_cost(next_gear) if survivor['gear_level'] < EQUIP_MAX_LEVEL else None,
                           resource_names=RESOURCE_NAMES, max_level=EQUIP_MAX_LEVEL, weapon_max_level=weapon_max,
                           weapon_rd_progress=round(rd_progress, 1), weapon_rd_tree=WEAPON_RD_TREE,
                           rd_gate=rd_gate, techs=TECHS,
                           max_energy=get_max_energy(survivor))

def _craft_guard(survivor):
    if not is_tech_unlocked('workshop_gear'):
        flash('还没有解锁制式装备图纸', 'error')
        return False
    if not q("SELECT 1 FROM buildings WHERE type='workshop'", one=True):
        flash('基地还没有工坊', 'error')
        return False
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return False
    return True

@app.route('/gear/craft/weapon', methods=['POST'])
@login_required
def gear_craft_weapon():
    survivor = current_survivor()
    if not _craft_guard(survivor):
        return redirect(url_for('gear_page'))
    weapon_max = get_weapon_max_level()
    if survivor['weapon_level'] >= weapon_max:
        flash('武器已经是当前能打造的最高级了', 'error')
        return redirect(url_for('gear_page'))
    weapon_type = request.form.get('weapon_type', '')
    if survivor['weapon_level'] == 0:
        if weapon_type not in ('gun', 'knife'):
            flash('请选择武器类型(枪/刀)', 'error')
            return redirect(url_for('gear_page'))
    else:
        weapon_type = survivor['weapon_type']
    next_level = survivor['weapon_level'] + 1
    cost = {k: max(1, round(v * int_discount(survivor))) for k, v in weapon_cost(next_level).items()}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('gear_page'))
    if not try_spend_energy(survivor['id'], 'craft'):
        flash('体力不足', 'error')
        return redirect(url_for('gear_page'))
    spend_resources(cost)
    max_durability = WEAPON_DURABILITY_PER_LEVEL * next_level
    run("UPDATE survivors SET weapon_level=?, weapon_type=?, weapon_durability=?, weapon_max_durability=? WHERE id=?",
        (next_level, weapon_type, max_durability, max_durability, survivor['id']))
    add_contribution(survivor['id'], 3)
    type_name = '枪' if weapon_type == 'gun' else '刀'
    log_action(survivor['id'], survivor['name'], '打造', f"打造了{next_level}级{type_name}")
    flash(f"{type_name}升到了{next_level}级", 'ok')
    return redirect(url_for('gear_page'))

@app.route('/gear/retrofit-weapon', methods=['POST'])
@login_required
def gear_retrofit_weapon():
    survivor = current_survivor()
    if not _craft_guard(survivor):
        return redirect(url_for('gear_page'))
    if survivor['weapon_level'] <= 0:
        flash('你还没有武器,先打造一把', 'error')
        return redirect(url_for('gear_page'))
    new_type = request.form.get('weapon_type', '')
    if new_type not in ('gun', 'knife'):
        flash('请选择武器类型(枪/刀)', 'error')
        return redirect(url_for('gear_page'))
    if new_type == survivor['weapon_type']:
        flash('已经是这个类型了', 'error')
        return redirect(url_for('gear_page'))
    cost = {k: max(1, round(v * 0.5 * int_discount(survivor))) for k, v in weapon_cost(survivor['weapon_level']).items()}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('gear_page'))
    if not try_spend_energy(survivor['id'], 'retrofit_weapon'):
        flash('体力不足', 'error')
        return redirect(url_for('gear_page'))
    spend_resources(cost)
    run("UPDATE survivors SET weapon_type=?, weapon_durability=weapon_max_durability WHERE id=?",
        (new_type, survivor['id']))
    type_name = '枪' if new_type == 'gun' else '刀'
    log_action(survivor['id'], survivor['name'], '改型', f"把武器改造成了{type_name}")
    flash(f"武器改造成了{type_name},耐久已恢复满", 'ok')
    return redirect(url_for('gear_page'))

@app.route('/gear/craft/gear', methods=['POST'])
@login_required
def gear_craft_gear():
    survivor = current_survivor()
    if not _craft_guard(survivor):
        return redirect(url_for('gear_page'))
    if survivor['gear_level'] >= EQUIP_MAX_LEVEL:
        flash('护甲已经是最高级了', 'error')
        return redirect(url_for('gear_page'))
    next_level = survivor['gear_level'] + 1
    cost = {k: max(1, round(v * int_discount(survivor))) for k, v in gear_cost(next_level).items()}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('gear_page'))
    if not try_spend_energy(survivor['id'], 'craft'):
        flash('体力不足', 'error')
        return redirect(url_for('gear_page'))
    spend_resources(cost)
    run("UPDATE survivors SET gear_level=? WHERE id=?", (next_level, survivor['id']))
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '打造', f"打造了{next_level}级护甲")
    flash(f"护甲升到了{next_level}级", 'ok')
    return redirect(url_for('gear_page'))

@app.route('/gear/repair-weapon', methods=['POST'])
@login_required
def gear_repair_weapon():
    survivor = current_survivor()
    if survivor['weapon_level'] <= 0:
        flash('你还没有武器', 'error')
        return redirect(url_for('gear_page'))
    missing = survivor['weapon_max_durability'] - survivor['weapon_durability']
    if missing <= 0:
        flash('武器耐久是满的', 'error')
        return redirect(url_for('gear_page'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('gear_page'))
    mult = specialization_mult(survivor, 'armory') * get_level_mult(survivor)
    cost = {'metal': max(1, math.ceil(missing * 0.5 / mult))}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('gear_page'))
    if not try_spend_energy(survivor['id'], 'repair_weapon'):
        flash('体力不足', 'error')
        return redirect(url_for('gear_page'))
    spend_resources(cost)
    run("UPDATE survivors SET weapon_durability=weapon_max_durability WHERE id=?", (survivor['id'],))
    add_contribution(survivor['id'], 2)
    log_action(survivor['id'], survivor['name'], '维修', "把自己的武器修好了")
    flash('武器修好了', 'ok')
    return redirect(url_for('gear_page'))

@app.route('/gear/weapon-rd', methods=['POST'])
@login_required
def gear_weapon_rd():
    survivor = current_survivor()
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('gear_page'))
    progress_now = float(get_meta('weapon_rd_progress', '0') or 0)
    gate = next_weapon_rd_gate(progress_now)
    if gate:
        flash(f"研发遇到瓶颈:「{gate['name']}」需要先解锁「{TECHS[gate['requires_tech']]['name']}」科技才能继续研发", 'error')
        return redirect(url_for('gear_page'))
    cost = {'crystal_core': 5, 'metal': 20}
    if not can_afford(cost):
        flash('晶核或金属不够', 'error')
        return redirect(url_for('gear_page'))
    if not try_spend_energy(survivor['id'], 'weapon_rd'):
        flash('体力不足', 'error')
        return redirect(url_for('gear_page'))
    spend_resources(cost)
    mult = specialization_mult(survivor, 'armory') * get_level_mult(survivor)
    gain = round(15 * mult, 1)
    before = float(get_meta('weapon_rd_progress', '0') or 0)
    after = before + gain
    set_meta('weapon_rd_progress', after)
    add_contribution(survivor['id'], 4)
    crossed = [node for node in WEAPON_RD_TREE if before < node['progress'] <= after]
    log_action(survivor['id'], survivor['name'], '研发', f"军械研发进度+{gain}")
    if crossed:
        names = '、'.join(f"{node['name']}({node['desc']})" for node in crossed)
        log_event('weapon_rd', f"军械研发取得突破:{names}")
        flash(f"研发突破!解锁了{names}", 'ok')
    else:
        flash(f"军械研发进度+{gain}", 'ok')
    return redirect(url_for('gear_page'))

# ── 信箱:打包钱包/装备/家具/礼物寄给别人,每天发送次数有限 ──────────────────────────

MAIL_DAILY_LIMIT = 5

@app.route('/mail')
@login_required
def mail_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    others = q("SELECT * FROM survivors WHERE id!=? AND status NOT IN ('dead','permadead') ORDER BY name",
               (survivor['id'],))
    my_items = q("SELECT * FROM survivor_items WHERE owner_id=? AND status='inventory' ORDER BY id DESC", (survivor['id'],))
    inbox = q("SELECT * FROM mail WHERE to_id=? ORDER BY id DESC", (survivor['id'],))
    outbox = q("SELECT * FROM mail WHERE from_id=? ORDER BY id DESC", (survivor['id'],))
    names = {s['id']: s['name'] for s in q("SELECT id, name FROM survivors")}
    def _mail_item_rows(mail_id):
        return q("""SELECT mail_items.id, survivor_items.item_type, survivor_items.item_key
                    FROM mail_items JOIN survivor_items ON survivor_items.id = mail_items.survivor_item_id
                    WHERE mail_items.mail_id=?""", (mail_id,))
    inbox_items = {m['id']: _mail_item_rows(m['id']) for m in inbox}
    outbox_items = {m['id']: _mail_item_rows(m['id']) for m in outbox}
    sent_today = daily_count(survivor['id'], 'mail_sent')
    return render_template('mail.html', survivor=survivor, others=others, my_items=my_items,
                           inbox=inbox, outbox=outbox, names=names, inbox_items=inbox_items, outbox_items=outbox_items,
                           item_display_name=item_display_name, sent_today=sent_today, mail_daily_limit=MAIL_DAILY_LIMIT,
                           mail_generosity_affinity=MAIL_GENEROSITY_AFFINITY)

@app.route('/mail/send/<int:target_id>', methods=['POST'])
@login_required
def mail_send(target_id):
    survivor = current_survivor()
    target = q("SELECT * FROM survivors WHERE id=?", (target_id,), one=True)
    if not target or target['id'] == survivor['id']:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('mail_page'))
    if target['status'] in ('dead', 'permadead'):
        flash(f"{target['name']} 已经倒下了,寄不了", 'error')
        return redirect(url_for('mail_page'))
    if daily_count(survivor['id'], 'mail_sent') >= MAIL_DAILY_LIMIT:
        flash(f"今天已经寄了{MAIL_DAILY_LIMIT}封信了,明天再寄", 'error')
        return redirect(url_for('mail_page'))
    note = request.form.get('note', '').strip()[:200]
    try:
        wallet_amount = int(request.form.get('wallet_amount', '0') or 0)
    except ValueError:
        wallet_amount = 0
    wallet_amount = max(0, wallet_amount)
    gift_weapon = request.form.get('gift_weapon') == 'on'
    gift_gear = request.form.get('gift_gear') == 'on'
    item_ids = [int(i) for i in request.form.getlist('item_ids') if i.isdigit()]

    # 先把所有附件校验一遍,全部通过才统一扣除(避免校验到一半就先扣掉前面的附件)
    if wallet_amount > survivor['wallet']:
        flash('钱包余额不够', 'error')
        return redirect(url_for('mail_page'))
    if gift_weapon and survivor['weapon_level'] <= 0:
        flash('你还没有武器可以寄', 'error')
        return redirect(url_for('mail_page'))
    if gift_gear and survivor['gear_level'] <= 0:
        flash('你还没有护甲可以寄', 'error')
        return redirect(url_for('mail_page'))
    items = []
    for item_id in item_ids:
        item = q("SELECT * FROM survivor_items WHERE id=? AND owner_id=? AND status='inventory'", (item_id, survivor['id']), one=True)
        if not item:
            flash('有一件东西不在你的背包里(可能已经上架或寄出了)', 'error')
            return redirect(url_for('mail_page'))
        items.append(item)
    if wallet_amount <= 0 and not gift_weapon and not gift_gear and not items:
        flash('这封信是空的,至少要带点东西', 'error')
        return redirect(url_for('mail_page'))

    # 校验全部通过,开始扣除
    mail_weapon = (0, '', 0, 0)
    if gift_weapon:
        mail_weapon = (survivor['weapon_level'], survivor['weapon_type'], survivor['weapon_durability'], survivor['weapon_max_durability'])
        run("UPDATE survivors SET weapon_level=0, weapon_type='', weapon_durability=0, weapon_max_durability=0 WHERE id=?", (survivor['id'],))
    mail_gear = 0
    if gift_gear:
        mail_gear = survivor['gear_level']
        run("UPDATE survivors SET gear_level=0 WHERE id=?", (survivor['id'],))
    if wallet_amount > 0:
        run("UPDATE survivors SET wallet=wallet-? WHERE id=?", (wallet_amount, survivor['id']))
    for item in items:
        run("UPDATE survivor_items SET status='mailed' WHERE id=?", (item['id'],))

    cur = run("""INSERT INTO mail (from_id, to_id, note, wallet_amount, weapon_level, weapon_type, weapon_durability,
                 weapon_max_durability, gear_level, created_ts) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (survivor['id'], target_id, note, wallet_amount, *mail_weapon, mail_gear, now_ts()))
    mail_id = cur.lastrowid
    for item in items:
        run("INSERT INTO mail_items (mail_id, survivor_item_id) VALUES (?,?)", (mail_id, item['id']))
    daily_inc(survivor['id'], 'mail_sent')
    log_action(survivor['id'], survivor['name'], '寄信', f"给{target['name']}寄了一封信")
    flash(f"寄给{target['name']}了", 'ok')
    return redirect(url_for('mail_page'))

@app.route('/mail/claim/<int:mail_id>', methods=['POST'])
@login_required
def mail_claim(mail_id):
    survivor = current_survivor()
    m = q("SELECT * FROM mail WHERE id=? AND to_id=? AND claimed=0", (mail_id, survivor['id']), one=True)
    if not m:
        flash('没有这封信,或者已经领过了', 'error')
        return redirect(url_for('mail_page'))
    if m['weapon_level'] > 0 and survivor['weapon_level'] > 0:
        flash('你已经有武器了,先转让/处理掉才能领这份附件', 'error')
        return redirect(url_for('mail_page'))
    if m['gear_level'] > 0 and survivor['gear_level'] > 0:
        flash('你已经有护甲了,先处理掉才能领这份附件', 'error')
        return redirect(url_for('mail_page'))
    generous = False
    if m['wallet_amount'] > 0:
        run("UPDATE survivors SET wallet=wallet+? WHERE id=?", (m['wallet_amount'], survivor['id']))
        generous = True
    if m['weapon_level'] > 0:
        run("UPDATE survivors SET weapon_level=?, weapon_type=?, weapon_durability=?, weapon_max_durability=? WHERE id=?",
            (m['weapon_level'], m['weapon_type'], m['weapon_durability'], m['weapon_max_durability'], survivor['id']))
        generous = True
    if m['gear_level'] > 0:
        run("UPDATE survivors SET gear_level=? WHERE id=?", (m['gear_level'], survivor['id']))
        generous = True
    for mi in q("SELECT * FROM mail_items WHERE mail_id=?", (mail_id,)):
        item = q("SELECT * FROM survivor_items WHERE id=?", (mi['survivor_item_id'],), one=True)
        if not item:
            continue
        if item['item_type'] == 'gift':
            gift = GIFT_TYPES.get(item['item_key'], {})
            bonus = gift.get('affinity_bonus', 0)
            if bonus and m['from_id']:
                add_affinity(m['from_id'], survivor['id'], bonus)
            happiness_bonus = gift.get('happiness_bonus', 0)
            if happiness_bonus:
                add_happiness(survivor['id'], happiness_bonus)
            run("DELETE FROM survivor_items WHERE id=?", (item['id'],))
        else:
            run("UPDATE survivor_items SET owner_id=?, status='inventory' WHERE id=?", (survivor['id'], item['id']))
            generous = True
    if generous and m['from_id']:
        generosity_key = f"mail_generosity:{m['from_id']}"
        if daily_count(survivor['id'], generosity_key) < 1:
            add_affinity(m['from_id'], survivor['id'], MAIL_GENEROSITY_AFFINITY)
            daily_inc(survivor['id'], generosity_key)
    run("UPDATE mail SET claimed=1, is_read=1 WHERE id=?", (mail_id,))
    log_action(survivor['id'], survivor['name'], '领取', "领取了一封信的附件")
    flash('领取成功', 'ok')
    return redirect(url_for('mail_page'))

@app.route('/mail/read/<int:mail_id>', methods=['POST'])
@login_required
def mail_read(mail_id):
    survivor = current_survivor()
    run("UPDATE mail SET is_read=1 WHERE id=? AND to_id=?", (mail_id, survivor['id']))
    return redirect(url_for('mail_page'))

@app.route('/mail/delete/<int:mail_id>', methods=['POST'])
@login_required
def mail_delete(mail_id):
    survivor = current_survivor()
    run("DELETE FROM mail WHERE id=? AND to_id=?", (mail_id, survivor['id']))
    return redirect(url_for('mail_page'))

# ── 房间:个人住房分级,货币购买,提升体力回复速度 ──────────────────────────────────

def furniture_slots(room_tier):
    return room_tier + 2

@app.route('/room')
@login_required
def room_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    tier = survivor['room_tier']
    next_tier = tier + 1 if tier < ROOM_TIER_MAX else None
    inventory_furniture = q("SELECT * FROM survivor_items WHERE owner_id=? AND item_type='furniture' AND status='inventory' ORDER BY id",
                            (survivor['id'],))
    installed_furniture = q("SELECT * FROM survivor_items WHERE owner_id=? AND item_type='furniture' AND status='installed' ORDER BY id",
                            (survivor['id'],))
    slots = furniture_slots(tier)
    return render_template('room.html', survivor=survivor, room_tiers=ROOM_TIERS,
                           tier=tier, next_tier=next_tier, room_tier_max=ROOM_TIER_MAX,
                           birth_rights_cost=BIRTH_RIGHTS_COST, furniture_types=FURNITURE_TYPES,
                           inventory_furniture=inventory_furniture, installed_furniture=installed_furniture,
                           furniture_slots=slots)

@app.route('/room/install/<int:item_id>', methods=['POST'])
@login_required
def room_install(item_id):
    survivor = current_survivor()
    item = q("SELECT * FROM survivor_items WHERE id=? AND owner_id=? AND item_type='furniture'", (item_id, survivor['id']), one=True)
    if not item or item['status'] != 'inventory':
        flash('这件家具不在你的背包里', 'error')
        return redirect(url_for('room_page'))
    installed_count = q("SELECT COUNT(*) c FROM survivor_items WHERE owner_id=? AND item_type='furniture' AND status='installed'",
                        (survivor['id'],), one=True)['c']
    if installed_count >= furniture_slots(survivor['room_tier']):
        flash('房间放不下了,拆掉一件或者升级房间', 'error')
        return redirect(url_for('room_page'))
    run("UPDATE survivor_items SET status='installed' WHERE id=?", (item_id,))
    log_action(survivor['id'], survivor['name'], '装饰', f"把{FURNITURE_TYPES[item['item_key']]['name']}装进了房间")
    flash('装好了', 'ok')
    return redirect(url_for('room_page'))

@app.route('/room/uninstall/<int:item_id>', methods=['POST'])
@login_required
def room_uninstall(item_id):
    survivor = current_survivor()
    item = q("SELECT * FROM survivor_items WHERE id=? AND owner_id=? AND item_type='furniture'", (item_id, survivor['id']), one=True)
    if not item or item['status'] != 'installed':
        flash('这件家具没有装在房间里', 'error')
        return redirect(url_for('room_page'))
    run("UPDATE survivor_items SET status='inventory' WHERE id=?", (item_id,))
    flash('拆下来了', 'ok')
    return redirect(url_for('room_page'))

@app.route('/room/upgrade', methods=['POST'])
@login_required
def room_upgrade():
    survivor = current_survivor()
    if survivor['room_tier'] >= ROOM_TIER_MAX:
        flash('房间已经是最高等级了', 'error')
        return redirect(url_for('room_page'))
    next_tier = survivor['room_tier'] + 1
    cost = ROOM_TIERS[next_tier]['upgrade_cost']['wallet']
    if survivor['wallet'] < cost:
        flash(f"钱包不够,升级到{ROOM_TIERS[next_tier]['name']}需要{cost}点钱", 'error')
        return redirect(url_for('room_page'))
    run("UPDATE survivors SET wallet=wallet-?, room_tier=? WHERE id=?", (cost, next_tier, survivor['id']))
    add_contribution(survivor['id'], 2)
    log_action(survivor['id'], survivor['name'], '搬家', f"搬进了{ROOM_TIERS[next_tier]['name']}")
    flash(f"搬进了{ROOM_TIERS[next_tier]['name']}", 'ok')
    return redirect(url_for('room_page'))

@app.route('/room/buy-birth-rights', methods=['POST'])
@login_required
def room_buy_birth_rights():
    survivor = current_survivor()
    if survivor['birth_rights']:
        flash('已经买过生育权了', 'error')
        return redirect(url_for('room_page'))
    if survivor['room_tier'] < ROOM_TIER_MAX:
        flash(f"房间要升到{ROOM_TIERS[ROOM_TIER_MAX]['name']}才能买生育权", 'error')
        return redirect(url_for('room_page'))
    if survivor['wallet'] < BIRTH_RIGHTS_COST:
        flash(f"钱包不够,需要{BIRTH_RIGHTS_COST}点钱", 'error')
        return redirect(url_for('room_page'))
    run("UPDATE survivors SET wallet=wallet-?, birth_rights=1 WHERE id=?", (BIRTH_RIGHTS_COST, survivor['id']))
    log_action(survivor['id'], survivor['name'], '购买', "买下了生育权")
    flash('买下了生育权', 'ok')
    return redirect(url_for('room_page'))

# ── 集市:家具/礼物做完不能直接用,得先上架、别人买了才能用 ──────────────────────────────

@app.route('/market')
@login_required
def market_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    listings = q("""SELECT market_listings.id AS listing_id, market_listings.price, market_listings.seller_id,
                            survivor_items.id AS item_id, survivor_items.item_type, survivor_items.item_key
                     FROM market_listings JOIN survivor_items ON survivor_items.id = market_listings.item_id
                     ORDER BY market_listings.listed_ts DESC""")
    seller_names = {s['id']: s['name'] for s in q("SELECT id, name FROM survivors")}
    my_items = q("SELECT * FROM survivor_items WHERE owner_id=? AND status='inventory' ORDER BY id DESC", (survivor['id'],))
    return render_template('market.html', survivor=survivor, listings=listings, seller_names=seller_names,
                           my_items=my_items, item_display_name=item_display_name)

@app.route('/market/list/<int:item_id>', methods=['POST'])
@login_required
def market_list_item(item_id):
    survivor = current_survivor()
    item = q("SELECT * FROM survivor_items WHERE id=? AND owner_id=?", (item_id, survivor['id']), one=True)
    if not item or item['status'] != 'inventory':
        flash('这件东西不在你的背包里', 'error')
        return redirect(url_for('market_page'))
    try:
        price = int(request.form.get('price', '0') or 0)
    except ValueError:
        price = 0
    if price <= 0:
        flash('价格要大于0', 'error')
        return redirect(url_for('market_page'))
    run("UPDATE survivor_items SET status='listed' WHERE id=?", (item_id,))
    run("INSERT INTO market_listings (item_id, seller_id, price, listed_ts) VALUES (?,?,?,?)",
        (item_id, survivor['id'], price, now_ts()))
    log_action(survivor['id'], survivor['name'], '上架', f"把{item_display_name(item['item_type'], item['item_key'])}上架卖{price}钱")
    flash('已上架', 'ok')
    return redirect(url_for('market_page'))

@app.route('/market/unlist/<int:listing_id>', methods=['POST'])
@login_required
def market_unlist(listing_id):
    survivor = current_survivor()
    listing = q("SELECT * FROM market_listings WHERE id=? AND seller_id=?", (listing_id, survivor['id']), one=True)
    if not listing:
        flash('没有这条挂牌', 'error')
        return redirect(url_for('market_page'))
    run("UPDATE survivor_items SET status='inventory' WHERE id=?", (listing['item_id'],))
    run("DELETE FROM market_listings WHERE id=?", (listing_id,))
    flash('已下架', 'ok')
    return redirect(url_for('market_page'))

@app.route('/market/buy/<int:listing_id>', methods=['POST'])
@login_required
def market_buy(listing_id):
    survivor = current_survivor()
    listing = q("SELECT * FROM market_listings WHERE id=?", (listing_id,), one=True)
    if not listing:
        flash('这个东西已经被买走了', 'error')
        return redirect(url_for('market_page'))
    if listing['seller_id'] == survivor['id']:
        flash('不能买自己上架的东西', 'error')
        return redirect(url_for('market_page'))
    if survivor['wallet'] < listing['price']:
        flash('钱包不够', 'error')
        return redirect(url_for('market_page'))
    item = q("SELECT * FROM survivor_items WHERE id=?", (listing['item_id'],), one=True)
    run("UPDATE survivors SET wallet=wallet-? WHERE id=?", (listing['price'], survivor['id']))
    run("UPDATE survivors SET wallet=wallet+? WHERE id=?", (listing['price'], listing['seller_id']))
    run("UPDATE survivor_items SET owner_id=?, status='inventory' WHERE id=?", (survivor['id'], item['id']))
    run("DELETE FROM market_listings WHERE id=?", (listing_id,))
    seller = q("SELECT name FROM survivors WHERE id=?", (listing['seller_id'],), one=True)
    log_action(survivor['id'], survivor['name'], '购买',
               f"从{seller['name'] if seller else '某人'}那里买了{item_display_name(item['item_type'], item['item_key'])},花{listing['price']}钱")
    flash('购买成功', 'ok')
    return redirect(url_for('market_page'))

# ── 关系/互动:好感度、表白、同居 ──────────────────────────────────────────────────

def get_relationship(a_id, b_id):
    lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    return q("SELECT * FROM relationships WHERE a_id=? AND b_id=?", (lo, hi), one=True)

def add_affinity(a_id, b_id, delta):
    lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    row = q("SELECT affinity FROM relationships WHERE a_id=? AND b_id=?", (lo, hi), one=True)
    new_aff = max(0, (row['affinity'] if row else 0) + delta)
    run("""INSERT INTO relationships (a_id,b_id,affinity,updated_ts) VALUES (?,?,?,?)
        ON CONFLICT(a_id,b_id) DO UPDATE SET affinity=excluded.affinity, updated_ts=excluded.updated_ts""",
        (lo, hi, new_aff, now_ts()))
    return new_aff

@app.route('/relationship')
@login_required
def relationship_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    get_effective_age(survivor['id'])
    survivor = current_survivor()
    others = q("SELECT * FROM survivors WHERE id!=? AND status NOT IN ('dead','permadead') ORDER BY name", (survivor['id'],))
    rels = {o['id']: get_relationship(survivor['id'], o['id']) for o in others}
    return render_template('relationship.html', survivor=survivor, others=others, rels=rels,
                           relationship_tier_name=relationship_tier_name,
                           propose_threshold=PROPOSE_AFFINITY_THRESHOLD, move_in_cost=MOVE_IN_COST,
                           birth_rights_cost=BIRTH_RIGHTS_COST, have_child_cost=HAVE_CHILD_COST,
                           room_tier_max=ROOM_TIER_MAX, breakup_penalty=BREAKUP_AFFINITY_PENALTY)

@app.route('/relationship/interact/<int:target_id>', methods=['POST'])
@login_required
def relationship_interact(target_id):
    survivor = current_survivor()
    target = q("SELECT * FROM survivors WHERE id=?", (target_id,), one=True)
    if not target or target['id'] == survivor['id']:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('relationship_page'))
    if target['status'] in ('dead', 'permadead'):
        flash(f"{target['name']} 已经倒下了", 'error')
        return redirect(url_for('relationship_page'))
    key = f'interact:{target_id}'
    if daily_count(survivor['id'], key) >= 1:
        flash(f"今天已经和{target['name']}互动过了,明天再来", 'error')
        return redirect(url_for('relationship_page'))
    roll = random.random()
    if roll < 0.50:
        delta = random.randint(3, 6)
        add_affinity(survivor['id'], target_id, delta)
        msg, cat = f"和{target['name']}相处愉快,好感度+{delta}", 'ok'
    elif roll < 0.85:
        msg, cat = f"和{target['name']}相处平淡,什么都没发生", 'ok'
    else:
        delta = random.randint(2, 4)
        add_affinity(survivor['id'], target_id, -delta)
        msg, cat = f"和{target['name']}话不投机,好感度-{delta}", 'error'
    daily_inc(survivor['id'], key)
    log_action(survivor['id'], survivor['name'], '互动', msg)
    flash(msg, cat)
    return redirect(url_for('relationship_page'))

@app.route('/relationship/propose/<int:target_id>', methods=['POST'])
@login_required
def relationship_propose(target_id):
    survivor = current_survivor()
    target = q("SELECT * FROM survivors WHERE id=?", (target_id,), one=True)
    if not target or target['id'] == survivor['id']:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('relationship_page'))
    rel = get_relationship(survivor['id'], target_id)
    if rel and rel['is_couple']:
        flash(f"已经和{target['name']}是情侣了", 'error')
        return redirect(url_for('relationship_page'))
    affinity = rel['affinity'] if rel else 0
    if affinity < PROPOSE_AFFINITY_THRESHOLD:
        flash(f"好感度还不够{PROPOSE_AFFINITY_THRESHOLD},还不能表白", 'error')
        return redirect(url_for('relationship_page'))
    lo, hi = (survivor['id'], target_id) if survivor['id'] < target_id else (target_id, survivor['id'])
    run("""INSERT INTO relationships (a_id,b_id,affinity,proposed_by,updated_ts) VALUES (?,?,?,?,?)
        ON CONFLICT(a_id,b_id) DO UPDATE SET proposed_by=excluded.proposed_by, updated_ts=excluded.updated_ts""",
        (lo, hi, affinity, survivor['id'], now_ts()))
    log_action(survivor['id'], survivor['name'], '表白', f"向{target['name']}表白了")
    flash(f"向{target['name']}表白了,等待对方回应", 'ok')
    return redirect(url_for('relationship_page'))

@app.route('/relationship/accept/<int:target_id>', methods=['POST'])
@login_required
def relationship_accept(target_id):
    survivor = current_survivor()
    rel = get_relationship(survivor['id'], target_id)
    if not rel or rel['proposed_by'] != target_id:
        flash('没有这条表白', 'error')
        return redirect(url_for('relationship_page'))
    lo, hi = (survivor['id'], target_id) if survivor['id'] < target_id else (target_id, survivor['id'])
    run("UPDATE relationships SET is_couple=1, proposed_by=0, updated_ts=? WHERE a_id=? AND b_id=?", (now_ts(), lo, hi))
    target = q("SELECT name FROM survivors WHERE id=?", (target_id,), one=True)
    log_event('couple', f"{survivor['name']} 和 {target['name']} 成为了情侣")
    flash('接受了表白,你们成为情侣了', 'ok')
    return redirect(url_for('relationship_page'))

@app.route('/relationship/decline/<int:target_id>', methods=['POST'])
@login_required
def relationship_decline(target_id):
    survivor = current_survivor()
    lo, hi = (survivor['id'], target_id) if survivor['id'] < target_id else (target_id, survivor['id'])
    run("UPDATE relationships SET proposed_by=0 WHERE a_id=? AND b_id=?", (lo, hi))
    flash('已拒绝', 'ok')
    return redirect(url_for('relationship_page'))

@app.route('/relationship/move-in/<int:partner_id>', methods=['POST'])
@login_required
def relationship_move_in(partner_id):
    survivor = current_survivor()
    rel = get_relationship(survivor['id'], partner_id)
    if not rel or not rel['is_couple']:
        flash('还不是情侣', 'error')
        return redirect(url_for('relationship_page'))
    if rel['shared_room']:
        flash('已经同居了', 'error')
        return redirect(url_for('relationship_page'))
    if survivor['wallet'] < MOVE_IN_COST:
        flash(f"钱包不够,搬进双人间需要{MOVE_IN_COST}点钱", 'error')
        return redirect(url_for('relationship_page'))
    lo, hi = (survivor['id'], partner_id) if survivor['id'] < partner_id else (partner_id, survivor['id'])
    run("UPDATE survivors SET wallet=wallet-? WHERE id=?", (MOVE_IN_COST, survivor['id']))
    run("UPDATE relationships SET shared_room=1, updated_ts=? WHERE a_id=? AND b_id=?", (now_ts(), lo, hi))
    partner = q("SELECT name FROM survivors WHERE id=?", (partner_id,), one=True)
    log_event('couple', f"{survivor['name']} 和 {partner['name']} 搬进了双人间,住在了一起")
    flash(f"搬进了双人间,和{partner['name']}住在一起了", 'ok')
    return redirect(url_for('relationship_page'))

@app.route('/relationship/breakup/<int:partner_id>', methods=['POST'])
@login_required
def relationship_breakup(partner_id):
    survivor = current_survivor()
    rel = get_relationship(survivor['id'], partner_id)
    if not rel or not rel['is_couple']:
        flash('还不是情侣', 'error')
        return redirect(url_for('relationship_page'))
    lo, hi = (survivor['id'], partner_id) if survivor['id'] < partner_id else (partner_id, survivor['id'])
    new_affinity = max(0, rel['affinity'] - BREAKUP_AFFINITY_PENALTY)
    run("UPDATE relationships SET is_couple=0, shared_room=0, proposed_by=0, affinity=?, updated_ts=? WHERE a_id=? AND b_id=?",
        (new_affinity, now_ts(), lo, hi))
    partner = q("SELECT name FROM survivors WHERE id=?", (partner_id,), one=True)
    log_event('breakup', f"{survivor['name']} 和 {partner['name']} 分手了")
    flash(f"和{partner['name']}分手了", 'ok')
    return redirect(url_for('relationship_page'))

@app.route('/relationship/have-child/<int:partner_id>', methods=['POST'])
@login_required
def relationship_have_child(partner_id):
    survivor = current_survivor()
    partner = q("SELECT * FROM survivors WHERE id=?", (partner_id,), one=True)
    if not partner:
        flash('没有这个幸存者', 'error')
        return redirect(url_for('relationship_page'))
    rel = get_relationship(survivor['id'], partner_id)
    if not rel or not rel['is_couple']:
        flash('还不是情侣', 'error')
        return redirect(url_for('relationship_page'))
    if not survivor['birth_rights'] or not partner['birth_rights']:
        flash('双方都要先买生育权', 'error')
        return redirect(url_for('relationship_page'))
    if survivor['wallet'] < HAVE_CHILD_COST:
        flash(f"钱包不够,需要{HAVE_CHILD_COST}点钱", 'error')
        return redirect(url_for('relationship_page'))
    run("UPDATE survivors SET wallet=wallet-? WHERE id=?", (HAVE_CHILD_COST, survivor['id']))
    code = secrets.token_hex(4)
    run("INSERT INTO birth_invites (code, parent_a_id, parent_b_id, created_ts) VALUES (?,?,?,?)",
        (code, survivor['id'], partner_id, now_ts()))
    log_action(survivor['id'], survivor['name'], '生育', f"和{partner['name']}生了一个孩子,邀请码{code}")
    flash(f"生了一个孩子!邀请码:{code} —— 把这个码给新玩家去注册页填", 'ok')
    return redirect(url_for('relationship_page'))

# ── 科技树 ─────────────────────────────────────────────────────────────────────

@app.route('/tech')
@login_required
def tech_page():
    survivor = current_survivor()
    get_effective_energy(survivor['id'])
    unlocked = {k: is_tech_unlocked(k) for k in TECHS}
    prereqs_met = {k: all(unlocked[r] for r in v['requires']) for k, v in TECHS.items()}
    return render_template('tech.html', survivor=survivor, techs=TECHS,
                           unlocked=unlocked, prereqs_met=prereqs_met, resource_names=RESOURCE_NAMES,
                           research=get_resource('research'))

@app.route('/tech/unlock/<key>', methods=['POST'])
@login_required
def tech_unlock(key):
    survivor = current_survivor()
    if key not in TECHS:
        flash('没有这项科技', 'error')
        return redirect(url_for('tech_page'))
    if is_tech_unlocked(key):
        flash('已经解锁过了', 'error')
        return redirect(url_for('tech_page'))
    missing_prereq = [r for r in TECHS[key]['requires'] if not is_tech_unlocked(r)]
    if missing_prereq:
        names = '、'.join(TECHS[r]['name'] for r in missing_prereq)
        flash(f"还没解锁前置科技:{names}", 'error')
        return redirect(url_for('tech_page'))
    discount = max(0.6, 1 - 0.03 * (survivor['stat_education'] - STAT_BASE)) * profession_cost_discount(survivor, 'build')
    cost = {k: max(1, round(v * discount)) for k, v in TECHS[key]['cost'].items()}
    if not can_afford(cost):
        flash('资源不够', 'error')
        return redirect(url_for('tech_page'))
    spend_resources(cost)
    set_meta(f'tech_{key}', '1')
    add_contribution(survivor['id'], 10)
    log_action(survivor['id'], survivor['name'], '研究', f"带领大家解锁了「{TECHS[key]['name']}」")
    log_event('tech', f"基地解锁了新科技:「{TECHS[key]['name']}」")
    flash(f"解锁了「{TECHS[key]['name']}」", 'ok')
    return redirect(url_for('tech_page'))

def resolve_horde_damage(deficit, survivors):
    """丧尸潮/归途装置猛攻突破防线时的统一伤害结算(建筑受损+生鲜作物流失+部分人受伤),返回描述文字,给两处失败分支复用。"""
    damaged = []
    candidates = q("SELECT * FROM buildings WHERE type!='empty'")
    if candidates:
        hit_buildings = random.sample(candidates, min(2, len(candidates)))
        for b in hit_buildings:
            dmg = min(b['hp'], round(deficit * random.uniform(1.2, 2.2)))
            new_hp = b['hp'] - dmg
            if new_hp <= 0:
                new_level = max(0, b['level'] - 1)
                if new_level <= 0:
                    run("UPDATE buildings SET type='empty', level=0, hp=0, max_hp=0, crop_type='', ready_ts=0, updated_ts=? WHERE id=?", (now_ts(), b['id']))
                    damaged.append(f"{BUILDING_TYPES[b['type']]['name']}#{b['slot_index']}被摧毁")
                else:
                    new_max_hp = BUILDING_TYPES[b['type']]['base_hp'] * new_level
                    run("UPDATE buildings SET level=?, hp=?, max_hp=?, updated_ts=? WHERE id=?", (new_level, new_max_hp, new_max_hp, now_ts(), b['id']))
                    damaged.append(f"{BUILDING_TYPES[b['type']]['name']}#{b['slot_index']}降为{new_level}级")
            else:
                run("UPDATE buildings SET hp=?, updated_ts=? WHERE id=?", (new_hp, now_ts(), b['id']))
                damaged.append(f"{BUILDING_TYPES[b['type']]['name']}#{b['slot_index']}受损")
    loot_loss = spend_up_to_raw_crop(round(deficit * random.uniform(1.5, 3)))
    hit_count = max(1, round(deficit / 20))
    for s in random.sample(survivors, min(hit_count, len(survivors))):
        apply_health_delta(s['id'], -random.randint(10, 30))
    return f"{'; '.join(damaged) if damaged else '仓库被搜刮'},损失生鲜作物{loot_loss}"

# ── 每日 tick:资源产出/消耗 + 灾害结算 ──────────────────────────────────────────

def run_day_tick():
    base = q("SELECT * FROM base_state WHERE id=1", one=True)
    day = base['day_count']
    season = base['season']
    morale = base['morale']

    survivors = q("SELECT * FROM survivors")
    n = len(survivors) or 1

    # 生产
    well_level = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='well'", one=True)['s']
    workshop_level = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='workshop'", one=True)['s']
    lab_level = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='research_lab'", one=True)['s']
    rain_collector_level = q("SELECT COALESCE(SUM(level),0) s FROM buildings WHERE type='rain_collector'", one=True)['s']
    if well_level:
        add_resource('water', well_level * BUILDING_TYPES['well']['water_per_level'])
    if workshop_level:
        add_resource('ammo', workshop_level * BUILDING_TYPES['workshop']['ammo_per_level'])
    if lab_level:
        add_resource('research', lab_level * BUILDING_TYPES['research_lab']['research_per_level'])
    if rain_collector_level:
        add_resource('raw_water', rain_collector_level * BUILDING_TYPES['rain_collector']['raw_water_per_level'])

    # 消耗:净水走共享池;食物按人头单独结算——贡献值钱包不够,或者三档食物都没库存,都会挨饿
    water_needed = n * WATER_PER_SURVIVOR_PER_DAY
    water_short = max(0, water_needed - get_resource('water'))
    add_resource('water', -water_needed)
    if water_short:
        shortage_ratio = water_short / max(1, water_needed)
        morale = max(0, morale - round(10 * shortage_ratio))
        hit_count = max(1, round(n * shortage_ratio))
        for s in random.sample(survivors, min(hit_count, len(survivors))):
            apply_health_delta(s['id'], -random.randint(3, 8))

    hungry = []
    morale_gain = 0
    for s in survivors:
        if s['wallet'] < FOOD_CLAIM_PRICE:
            hungry.append(s)
            continue
        tier_fed = None
        for tier in FOOD_TIERS:
            if get_resource(tier) >= 1:
                add_resource(tier, -1)
                run("UPDATE survivors SET wallet=wallet-? WHERE id=?", (FOOD_CLAIM_PRICE, s['id']))
                tier_fed = tier
                break
        if tier_fed is None:
            hungry.append(s)
            continue
        effect = FOOD_TIER_EFFECTS.get(tier_fed, {})
        morale_gain += effect.get('morale', 0)
        if effect.get('health'):
            apply_health_delta(s['id'], effect['health'])
        if effect.get('happiness'):
            add_happiness(s['id'], effect['happiness'])
        if effect.get('stat'):
            run(f"UPDATE survivors SET {effect['stat']}=MIN(20,{effect['stat']}+?) WHERE id=?", (effect['stat_amount'], s['id']))
            log_event('buff', f"{s['name']}吃了{RESOURCE_NAMES.get(tier_fed, tier_fed)},{STATS[effect['stat']]['name']}+{effect['stat_amount']}")
    morale = min(100, morale + morale_gain)
    if hungry:
        morale = max(0, morale - min(20, len(hungry) * 3))
        for s in hungry:
            dmg = max(1, random.randint(5, 15) - (s['stat_willpower'] - STAT_BASE))
            apply_health_delta(s['id'], -dmg)
        names = '、'.join(s['name'] for s in hungry)
        log_event('hunger', f"今天{names}没能分到饭:{'贡献不够没换到' if any(s['wallet']<FOOD_CLAIM_PRICE for s in hungry) else '仓库里已经没吃的了'}")

    # 疾病:健康的人每天有小概率患上小病,患病期间每天扣血、拖累士气,得去诊所治愈才能停止
    sick_names = []
    for s in survivors:
        if s['status'] in ('dead', 'permadead'):
            continue
        if s['illness']:
            info = ILLNESSES.get(s['illness'])
            if info:
                apply_health_delta(s['id'], -info['daily_health_drain'])
                morale = max(0, morale - info['morale_penalty'])
        elif random.random() < illness_chance_for_age(s['age_years']):
            illness_key = random.choice(list(ILLNESSES.keys()))
            run("UPDATE survivors SET illness=?, illness_started_ts=? WHERE id=?", (illness_key, now_ts(), s['id']))
            sick_names.append(f"{s['name']}({ILLNESSES[illness_key]['name']})")
    if sick_names:
        log_event('illness', f"新添病号:{'、'.join(sick_names)},记得去诊所治")

    # 感染:组队探索被咬伤后小概率感染,拖过 INFECTION_DAYS_LIMIT 天不治疗直接变成丧尸,不给重生机会
    zombified = []
    for s in survivors:
        if s['status'] in ('dead', 'permadead') or not s['infected']:
            continue
        if day - s['infected_since_day'] >= INFECTION_DAYS_LIMIT:
            run("UPDATE survivors SET status='permadead', infected=0 WHERE id=?", (s['id'],))
            zombified.append(s['name'])
    if zombified:
        names = '、'.join(zombified)
        log_event('death', f"{names}没能扛过感染,变成了丧尸,永远地离开了大家")

    # 快乐值:每天自然衰减,过低有概率转入抑郁(拖慢体力回复),回升到位自动脱离,不需要专门的治疗动作
    newly_depressed = []
    recovered = []
    for s in survivors:
        if s['status'] in ('dead', 'permadead'):
            continue
        # 用当前实时值而非函数开头的快照,避免把同一次 tick 里供餐/庆祝等已经加过的快乐值覆盖掉
        current = q("SELECT happiness, is_depressed FROM survivors WHERE id=?", (s['id'],), one=True)
        new_happiness = max(0, current['happiness'] - HAPPINESS_DAILY_DECAY)
        run("UPDATE survivors SET happiness=? WHERE id=?", (new_happiness, s['id']))
        if not current['is_depressed'] and new_happiness < DEPRESSION_THRESHOLD and random.random() < DEPRESSION_DAILY_CHANCE:
            run("UPDATE survivors SET is_depressed=1 WHERE id=?", (s['id'],))
            newly_depressed.append(s['name'])
        elif current['is_depressed'] and new_happiness >= DEPRESSION_RECOVERY_THRESHOLD:
            run("UPDATE survivors SET is_depressed=0 WHERE id=?", (s['id'],))
            recovered.append(s['name'])
    if newly_depressed:
        log_event('depression', f"{'、'.join(newly_depressed)}情绪低落,陷入了抑郁,体力回复变慢了,该找点乐子了")
    if recovered:
        log_event('depression', f"{'、'.join(recovered)}心情好转,走出了抑郁")

    # 房间等级带来的被动士气加成(全员均摊)
    room_morale_bonus = sum(ROOM_TIERS.get(s['room_tier'], ROOM_TIERS[0])['morale_bonus'] for s in survivors)
    if room_morale_bonus:
        morale = min(100, morale + round(room_morale_bonus / n))

    # 情侣同居(双人间)带来的被动士气加成,每对独立计算,不摊薄
    shared_room_count = q("SELECT COUNT(*) c FROM relationships WHERE shared_room=1", one=True)['c']
    if shared_room_count:
        morale = min(100, morale + shared_room_count * SHARED_ROOM_MORALE_BONUS)

    # 已安装家具带来的被动士气加成(全员均摊,和房间等级的加成算法一致)
    furniture_morale_bonus = sum(installed_furniture_bonus(s['id'], 'morale') for s in survivors)
    if furniture_morale_bonus:
        morale = min(100, morale + round(furniture_morale_bonus / n))

    # 灾害/事件
    weights = {'calm': 30, 'zombie_horde': 25, 'environmental': 20, 'trader': 15, 'bonus_calm': 10}
    if season == '严冬':
        weights['environmental'] += 10
        weights['zombie_horde'] -= 5
    elif season == '盛夏':
        weights['zombie_horde'] += 10
        weights['environmental'] -= 5
    kinds = list(weights.keys())
    kind = random.choices(kinds, weights=[max(1, weights[k]) for k in kinds])[0]

    detail = ''
    if kind == 'zombie_horde':
        wall_defense, trap_defense, tower_defense, tower_level = base_defense_breakdown()
        warn_reduce = min(0.4, tower_level * BUILDING_TYPES['watchtower']['warn_per_level'])
        patrol_points = float(get_meta('patrol_points_today', '0') or 0)
        horde_reduction = float(get_meta('horde_reduction_today', '0') or 0)
        defense_total = wall_defense + trap_defense + tower_defense + patrol_points
        horde_strength = max(10, (40 + day * 3 + random.randint(-10, 15)) * (1 - warn_reduce) - horde_reduction)
        if defense_total >= horde_strength:
            morale = min(100, morale + 5)
            bonus = random.randint(5, 15)
            add_resource('ammo', bonus)
            detail = f"丧尸潮来袭(强度{round(horde_strength)}),防御值{round(defense_total)}成功击退,缴获弹药+{bonus}"
        else:
            deficit = horde_strength - defense_total
            morale = max(0, morale - 10)
            damage_desc = resolve_horde_damage(deficit, survivors)
            detail = f"丧尸潮突破了防线(缺口{round(deficit)}):{damage_desc}"
    elif kind == 'environmental':
        subtype = random.choice(['toxic_fog', 'radiation_storm', 'cold_snap'])
        if subtype in ('toxic_fog', 'radiation_storm'):
            name = '毒雾' if subtype == 'toxic_fog' else '辐射风暴'
            unprotected = q("SELECT * FROM buildings WHERE type='farm_plot' AND crop_type!=''")
            withered = []
            for p in unprotected:
                if random.random() < 0.6:
                    run("UPDATE buildings SET crop_type='', ready_ts=0, updated_ts=? WHERE id=?", (now_ts(), p['id']))
                    withered.append(f"#{p['slot_index']}")
            morale = max(0, morale - 5)
            for s in survivors:
                hit_chance = max(0.03, 0.15 - 0.03 * s['gear_level'])
                if random.random() < hit_chance:
                    apply_health_delta(s['id'], -5)
            detail = f"{name}笼罩了基地" + (f",露天农田{','.join(withered)}的作物枯萎了" if withered else ",幸好没有露天作物受损")
        else:
            extra = spend_up_to_raw_crop(n * 2)
            morale = max(0, morale - 3)
            detail = f"寒潮突袭,为了取暖多消耗了{extra}份生鲜作物"
    elif kind == 'trader':
        avg_appearance = sum(s['stat_appearance'] for s in survivors) / n
        trade_mult = 1 + 0.03 * (avg_appearance - STAT_BASE)
        gift = {'medicine': random.randint(5, 12), 'ammo': random.randint(5, 12), 'wood': random.randint(10, 20)}
        gift = {k: round(v * trade_mult) for k, v in gift.items()}
        for k, v in gift.items():
            add_resource(k, v)
        morale = min(100, morale + 3)
        desc = '、'.join(f"{RESOURCE_NAMES.get(k,k)}+{v}" for k, v in gift.items())
        detail = f"一支流浪商队造访了基地,留下了{desc}"
    elif kind == 'bonus_calm':
        bonus = random.randint(15, 30)
        bonus_key = random.choice(RAW_CROP_KEYS)
        add_resource(bonus_key, bonus)
        morale = min(100, morale + 5)
        detail = f"难得平静的一天,大家自发加了餐,{RESOURCE_NAMES[bonus_key]}+{bonus}"
    else:
        morale = min(100, morale + 2)
        detail = "平静的一天,没有异常"

    log_event(kind, detail)
    set_meta('patrol_points_today', 0)
    set_meta('horde_reduction_today', 0)

    new_day = day + 1
    new_season = SEASONS[((new_day - 1) // SEASON_DAYS) % len(SEASONS)]
    if new_day in MILESTONES:
        morale = min(100, morale + 10)
        log_event('milestone', MILESTONES[new_day])
    if new_day in STORY_EVENTS:
        set_meta(f'story_pending_{new_day}', '1')
        log_event('story', f"发生了一件大事:{STORY_EVENTS[new_day]['title']}——去总览页看看怎么选")

    # 归途装置:周期性信号猛攻,装置激活前一直循环、一波比一波猛,不设上限
    if new_day % GATE_SURGE_INTERVAL_DAYS == 0 and not gate_device_activated():
        surge_number = new_day // GATE_SURGE_INTERVAL_DAYS
        mult = gate_surge_multiplier(surge_number)
        wall_defense, trap_defense, tower_defense, tower_level = base_defense_breakdown()
        defense_total = wall_defense + trap_defense + tower_defense
        surge_strength = (40 + new_day * 3) * mult
        if defense_total >= surge_strength:
            morale = min(100, morale + 8)
            log_event('gate_surge', f"第{surge_number}波信号猛攻来袭(强度{round(surge_strength)}),防御值{round(defense_total)}扛住了")
        else:
            deficit = surge_strength - defense_total
            morale = max(0, morale - 15)
            damage_desc = resolve_horde_damage(deficit, survivors)
            cur_progress = gate_device_progress()
            progress_loss = min(cur_progress, GATE_SURGE_PROGRESS_PENALTY)
            if progress_loss:
                set_meta('gate_device_progress', str(cur_progress - progress_loss))
            log_event('gate_surge', f"第{surge_number}波信号猛攻突破了防线(缺口{round(deficit)}):{damage_desc},装置进度倒退{progress_loss}")

    run("UPDATE base_state SET day_count=?, season=?, morale=?, last_tick_ts=? WHERE id=1",
        (new_day, new_season, morale, now_ts()))

# ── 剧情节点:选项抢先生效 ─────────────────────────────────────────────────────

@app.route('/story/choose/<int:day>/<int:choice_idx>', methods=['POST'])
@login_required
def story_choose(day, choice_idx):
    survivor = current_survivor()
    event = STORY_EVENTS.get(day)
    if not event or choice_idx < 0 or choice_idx >= len(event['choices']):
        flash('没有这个剧情事件', 'error')
        return redirect(url_for('dashboard'))
    if get_meta(f'story_resolved_{day}', '0') == '1':
        flash('这件事已经有人处理过了', 'error')
        return redirect(url_for('dashboard'))
    choice = event['choices'][choice_idx]
    for k, v in choice.get('resources', {}).items():
        add_resource(k, v)
    for k, v in choice.get('cost', {}).items():
        add_resource(k, -v)
    if choice.get('morale'):
        base = q("SELECT morale FROM base_state WHERE id=1", one=True)
        run("UPDATE base_state SET morale=? WHERE id=1", (max(0, min(100, base['morale'] + choice['morale'])),))
    if choice.get('risk_chance') and random.random() < choice['risk_chance']:
        alive = q("SELECT id, name FROM survivors WHERE status NOT IN ('dead','permadead')")
        if alive:
            victim = random.choice(alive)
            dmg = choice.get('risk_damage', 10)
            apply_health_delta(victim['id'], -dmg)
            log_event('story', f"{victim['name']} 在这次行动中受伤了,损失{dmg}点健康")
    set_meta(f'story_resolved_{day}', '1')
    log_event('story', f"{survivor['name']} 代表基地选择了「{choice['label']}」,{event['title']}告一段落")
    flash(f"选择了「{choice['label']}」", 'ok')
    return redirect(url_for('dashboard'))

# ── 归途装置:投入进度 / 达标后抢先激活(谁先点谁替全基地生效,仿剧情节点模式) ──────

@app.route('/gate/invest', methods=['POST'])
@login_required
def gate_invest():
    survivor = current_survivor()
    if gate_device_activated():
        flash('装置已经激活了,不需要再投入了', 'error')
        return redirect(url_for('dashboard'))
    if gate_device_progress() >= GATE_DEVICE_TARGET:
        flash('材料已经攒够了,去激活装置吧', 'error')
        return redirect(url_for('dashboard'))
    if survivor['status'] == 'critical':
        flash('你身负重伤,需要先去诊所', 'error')
        return redirect(url_for('dashboard'))
    if get_resource('resonance_core') < GATE_DEVICE_INVEST_COST:
        flash(f"共振核心不够了(需要{GATE_DEVICE_INVEST_COST}),去组队探索或采集碰碰运气", 'error')
        return redirect(url_for('dashboard'))
    if not try_spend_energy(survivor['id'], 'gate_invest'):
        flash('体力不足', 'error')
        return redirect(url_for('dashboard'))
    spend_resources({'resonance_core': GATE_DEVICE_INVEST_COST})
    new_progress = min(GATE_DEVICE_TARGET, gate_device_progress() + GATE_DEVICE_INVEST_PROGRESS)
    set_meta('gate_device_progress', str(new_progress))
    add_contribution(survivor['id'], 3)
    log_action(survivor['id'], survivor['name'], '装置', f"往归途装置里投入了共振核心,进度推进到{new_progress}/{GATE_DEVICE_TARGET}")
    flash(f"投入成功,装置进度 {new_progress}/{GATE_DEVICE_TARGET}", 'ok')
    return redirect(url_for('dashboard'))

@app.route('/gate/activate', methods=['POST'])
@login_required
def gate_activate():
    survivor = current_survivor()
    if gate_device_activated():
        flash('装置已经激活过了', 'error')
        return redirect(url_for('dashboard'))
    if gate_device_progress() < GATE_DEVICE_TARGET:
        flash('材料还不够,继续投入吧', 'error')
        return redirect(url_for('dashboard'))
    set_meta('gate_device_activated', '1')
    day = q("SELECT day_count FROM base_state WHERE id=1", one=True)['day_count']
    log_event('gate_ending', f"{survivor['name']} 按下了归途装置的启动键——蓝光吞没了基地,大家总算能回家了(第{day}天,装置激活)")
    flash('装置激活成功!这是属于所有人的结局,恭喜大家撑到了这一天', 'ok')
    return redirect(url_for('dashboard'))

# ── 后台管理 ─────────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_home():
    base = q("SELECT * FROM base_state WHERE id=1", one=True)
    resources = {r['key']: r['amount'] for r in q("SELECT * FROM resources")}
    survivors = q("SELECT * FROM survivors ORDER BY id")
    buildings = q("SELECT * FROM buildings WHERE type!='empty' ORDER BY slot_index")
    events = q("SELECT * FROM events_log ORDER BY id DESC LIMIT 20")
    names = {s['id']: s['name'] for s in survivors}
    market_listings = q("""SELECT market_listings.id AS listing_id, market_listings.price, market_listings.seller_id,
                                   survivor_items.item_type, survivor_items.item_key
                            FROM market_listings JOIN survivor_items ON survivor_items.id = market_listings.item_id
                            ORDER BY market_listings.listed_ts DESC""")
    relationships = q("SELECT * FROM relationships ORDER BY affinity DESC")
    mail_stats = q("SELECT COUNT(*) total, COALESCE(SUM(claimed),0) claimed FROM mail", one=True)
    recent_mail = q("SELECT * FROM mail ORDER BY id DESC LIMIT 20")
    return render_template('admin.html', base=base, resources=resources, resource_names=RESOURCE_NAMES,
                           survivors=survivors, buildings=buildings, building_types=BUILDING_TYPES, events=events,
                           cap=resource_cap(), names=names, market_listings=market_listings,
                           relationships=relationships, mail_stats=mail_stats, recent_mail=recent_mail,
                           item_display_name=item_display_name, relationship_tier_name=relationship_tier_name)

@app.route('/admin/stats')
@admin_required
def admin_stats():
    """只读的内测统计页,把已经在打的日志(action_log/events_log)和当前表状态汇总成数值调优要看的东西,不改任何数据。"""
    survivors = q("SELECT * FROM survivors")
    n = len(survivors) or 1

    status_counts = {}
    for s in survivors:
        status_counts[s['status']] = status_counts.get(s['status'], 0) + 1

    age_buckets = [('未成年(<18)', 0), ('青年(18-50)', 0), ('中年(51-65)', 0), ('老年(66+)', 0)]
    age_buckets = dict(age_buckets)
    for s in survivors:
        a = s['age_years']
        if a < AGE_ADULT:
            age_buckets['未成年(<18)'] += 1
        elif a <= 50:
            age_buckets['青年(18-50)'] += 1
        elif a <= 65:
            age_buckets['中年(51-65)'] += 1
        else:
            age_buckets['老年(66+)'] += 1
    avg_age = round(sum(s['age_years'] for s in survivors) / n, 1) if survivors else 0
    pending_coming_of_age = sum(1 for s in survivors if s['age_years'] >= AGE_ADULT and not s['specialization'])

    respawn_dist = {}
    for s in survivors:
        respawn_dist[s['respawn_count']] = respawn_dist.get(s['respawn_count'], 0) + 1

    wallets = sorted(s['wallet'] for s in survivors)
    avg_wallet = round(sum(wallets) / n, 1) if wallets else 0
    median_wallet = wallets[len(wallets) // 2] if wallets else 0
    hungry_risk = sum(1 for w in wallets if w < FOOD_CLAIM_PRICE)

    room_dist = {}
    for s in survivors:
        room_dist[s['room_tier']] = room_dist.get(s['room_tier'], 0) + 1
    birth_rights_count = sum(1 for s in survivors if s['birth_rights'])
    couple_count = q("SELECT COUNT(*) c FROM relationships WHERE is_couple=1", one=True)['c']
    shared_room_count = q("SELECT COUNT(*) c FROM relationships WHERE shared_room=1", one=True)['c']

    stat_avgs = {key: round(sum(s[key] for s in survivors) / n, 2) if survivors else 0 for key in STATS}
    stat_total_avg = round(sum(sum(s[k] for k in STATS) for s in survivors) / n, 1) if survivors else 0
    stat_by_respawn = {}
    for s in survivors:
        stat_by_respawn.setdefault(s['respawn_count'], []).append(sum(s[k] for k in STATS))
    stat_by_respawn_avg = {rc: round(sum(v) / len(v), 1) for rc, v in sorted(stat_by_respawn.items())}

    action_counts = q("SELECT action, COUNT(*) c FROM action_log GROUP BY action ORDER BY c DESC")

    death_cause = {'战斗/饥饿/灾害': 0, '年老': 0}
    for e in q("SELECT detail FROM events_log WHERE kind='death'"):
        death_cause['年老' if '年事已高' in e['detail'] else '战斗/饥饿/灾害'] += 1

    story_status = [{'day': day, 'title': event['title'],
                     'resolved': get_meta(f'story_resolved_{day}', '0') == '1'}
                    for day, event in sorted(STORY_EVENTS.items())]

    weapon_rd_progress = float(get_meta('weapon_rd_progress', '0') or 0)
    unlocked_techs = [TECHS[k]['name'] for k in TECHS if is_tech_unlocked(k)]

    market_total_listed = q("SELECT COUNT(*) c FROM action_log WHERE action='上架'", one=True)['c']
    market_total_sold = q("SELECT COUNT(*) c FROM action_log WHERE action='购买'", one=True)['c']

    return render_template('admin_stats.html', n=len(survivors), status_counts=status_counts, age_buckets=age_buckets,
                           avg_age=avg_age, pending_coming_of_age=pending_coming_of_age, respawn_dist=respawn_dist,
                           max_respawns=MAX_RESPAWNS, avg_wallet=avg_wallet, median_wallet=median_wallet,
                           hungry_risk=hungry_risk, food_claim_price=FOOD_CLAIM_PRICE,
                           room_dist=room_dist, room_tiers=ROOM_TIERS, room_tier_max=ROOM_TIER_MAX,
                           birth_rights_count=birth_rights_count, couple_count=couple_count,
                           shared_room_count=shared_room_count, stats=STATS, stat_avgs=stat_avgs,
                           stat_total_avg=stat_total_avg, stat_base_total=STAT_BASE * len(STATS),
                           stat_by_respawn_avg=stat_by_respawn_avg, action_counts=action_counts,
                           death_cause=death_cause, story_status=story_status,
                           weapon_rd_progress=weapon_rd_progress, unlocked_techs=unlocked_techs,
                           market_total_listed=market_total_listed, market_total_sold=market_total_sold)

@app.route('/admin/tick', methods=['POST'])
@admin_required
def admin_tick():
    run_day_tick()
    flash('已手动推进一天', 'ok')
    return redirect(url_for('admin_home'))

@app.route('/admin/resource', methods=['POST'])
@admin_required
def admin_set_resource():
    key = request.form.get('key', '')
    amount = request.form.get('amount', '0')
    if key not in RESOURCE_NAMES:
        flash('没有这种资源', 'error')
        return redirect(url_for('admin_home'))
    try:
        amount = int(amount)
    except ValueError:
        flash('数值不对', 'error')
        return redirect(url_for('admin_home'))
    run("INSERT INTO resources (key, amount) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET amount=excluded.amount",
        (key, max(0, amount)))
    flash(f'{RESOURCE_NAMES[key]}已设为{amount}', 'ok')
    return redirect(url_for('admin_home'))

@app.route('/admin/reset', methods=['POST'])
@admin_required
def admin_reset():
    if request.form.get('confirm', '') != '重置':
        flash('请输入"重置"两个字以确认', 'error')
        return redirect(url_for('admin_home'))
    db = get_db()
    db.executescript("""
        DELETE FROM survivors; DELETE FROM users; DELETE FROM base_state;
        DELETE FROM resources; DELETE FROM buildings; DELETE FROM events_log;
        DELETE FROM action_log; DELETE FROM meta; DELETE FROM alert_claims;
        DELETE FROM relationships; DELETE FROM survivor_items; DELETE FROM market_listings;
        DELETE FROM mail; DELETE FROM mail_items; DELETE FROM daily_counters; DELETE FROM birth_invites;
        DELETE FROM expeditions; DELETE FROM expedition_log;
    """)
    db.commit()
    init_db()
    flash('游戏已重置', 'ok')
    return redirect(url_for('admin_home'))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, port=int(os.environ.get('PORT', 5008)))
