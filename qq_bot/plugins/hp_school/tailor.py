"""马金夫人长袍店：上缝纫课攒等级、学图纸、做衣服、上架卖钱或者自己穿。

纯网页玩法，不接QQ机器人指令——这里每个动作网页表单一次提交就能完成，
不需要像厨房烹饪那样分步引导，没必要在QQ里重复一遍。

图纸照奇迹暖暖那一套分四个部位：上装/下装/裙装/饰品——长袍这种连体的
算裙装，斗篷大衣这种罩在外面的算上装，裤子/半身裙算下装，小件的算饰品。

缝纫等级不占用"今日作业/成绩"那一套，纯粹是解锁高级图纸的进度条，
0-10级，10次课封顶，跟学科经验完全无关。

摆摊卖出用的是懒结算：不开定时任务，每次玩家打开裁缝铺页面（或做任何
操作）时，按上次检查到现在经过的整点小时数补算摇号，思路跟宠物心情
衰减、体力自然回复是同一套写法。

穿上不消耗库存（可以反复穿、之后还能拿去卖），但每天限次，避免刷屏；
播报文案按图纸要求等级分层，越难做的衣服穿出来动静越大。
"""

from __future__ import annotations

import random
import sqlite3

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

from . import shop_catalog
from . import storage as school_storage

LESSON_STAMINA_COST = 30
MAX_LEVEL = 10

SALE_CHECK_INTERVAL = 3600  # 每小时结算一次
SALE_CHANCE = 0.3
SALE_DAILY_LIMIT = 5  # 摊位一天最多卖出5件，卖满了当天剩下的摇号直接跳过，衣服留在摊位上等明天

WEAR_DAILY_LIMIT = 3

SLOT_ORDER = ("dress", "top", "bottom", "accessory")
SLOT_NAMES = {"dress": "👗 裙装", "top": "👚 上装", "bottom": "👖 下装", "accessory": "💍 饰品"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tailor_progress (
    uid TEXT PRIMARY KEY,
    level INTEGER NOT NULL DEFAULT 0,
    total_crafted INTEGER NOT NULL DEFAULT 0,
    total_earned INTEGER NOT NULL DEFAULT 0,
    fashion_points INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tailor_learned_patterns (
    uid TEXT NOT NULL,
    pattern_key TEXT NOT NULL,
    learned_at INTEGER NOT NULL,
    PRIMARY KEY (uid, pattern_key)
);

CREATE TABLE IF NOT EXISTS tailor_crafted_keys (
    uid TEXT NOT NULL,
    pattern_key TEXT NOT NULL,
    crafted_at INTEGER NOT NULL,
    PRIMARY KEY (uid, pattern_key)
);

CREATE TABLE IF NOT EXISTS tailor_inventory (
    uid TEXT NOT NULL,
    clothing_key TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, clothing_key)
);

CREATE TABLE IF NOT EXISTS tailor_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    clothing_key TEXT NOT NULL,
    listed_at INTEGER NOT NULL,
    next_check_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tailor_wear_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS tailor_sale_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);
"""

# key: {名字, 部位, 所需缝纫等级, 材料需求, 解锁方式(level/shop/forest), 学习图纸价格(仅shop), 售出加隆区间}
# 材料成本都压在售价区间下限之下，保证每次卖出都稳赚——见各条目成本换算。
PATTERNS: dict[str, dict] = {
    # ── 裙装：长袍/礼服这类连体款 ──
    "cotton_robe": {
        "name": "棉布学徒袍", "slot": "dress", "level": 1, "unlock": "level",
        "ingredients": {"fabric_cotton": 3}, "sell_range": (30, 38),
    },
    "linen_daydress": {
        "name": "亚麻晨光裙", "slot": "dress", "level": 1, "unlock": "level",
        "ingredients": {"fabric_linen": 3}, "sell_range": (30, 40),
    },
    "chiffon_dawn_gown": {
        "name": "晨曦纱裙", "slot": "dress", "level": 3, "unlock": "level",
        "ingredients": {"fabric_chiffon": 3}, "sell_range": (36, 46),
    },
    "satin_glaze_dress": {
        "name": "琉璃缎面礼裙", "slot": "dress", "level": 4, "unlock": "shop", "shop_price": 40,
        "ingredients": {"fabric_satin": 2}, "sell_range": (38, 48),
    },
    "lace_thorned_rose_gown": {
        "name": "荆棘玫瑰蕾丝礼服", "slot": "dress", "level": 5, "unlock": "forest",
        "ingredients": {"fabric_lace": 3}, "sell_range": (42, 52),
    },
    "shifting_silk_illusion_gown": {
        "name": "幻形丝绸魅影长裙", "slot": "dress", "level": 9, "unlock": "forest",
        "ingredients": {"fabric_shifting_silk": 1}, "sell_range": (48, 58),
    },
    "grand_couture_gala_gown": {
        "name": "盛典华服", "slot": "dress", "level": 10, "unlock": "level",
        "ingredients": {"fabric_satin": 2, "fabric_pearl_button": 2}, "sell_range": (52, 60),
    },
    "wool_school_robe": {
        "name": "羊毛校服袍", "slot": "dress", "level": 2, "unlock": "level",
        "ingredients": {"fabric_wool": 3}, "sell_range": (32, 42),
    },
    "silk_moonlit_robe": {
        "name": "月华丝绸长袍", "slot": "dress", "level": 4, "unlock": "level",
        "ingredients": {"fabric_silk": 2}, "sell_range": (40, 50),
    },
    "velvet_ballgown": {
        "name": "天鹅绒晚礼裙", "slot": "dress", "level": 6, "unlock": "shop", "shop_price": 50,
        "ingredients": {"fabric_velvet": 2, "fabric_lace": 1}, "sell_range": (44, 54),
    },
    "silver_thread_frost_gown": {
        "name": "冰霜银线长裙", "slot": "dress", "level": 8, "unlock": "forest",
        "ingredients": {"fabric_silver_thread": 2}, "sell_range": (46, 56),
    },
    # ── 上装：斗篷/大衣这类罩在外面的 ──
    "hemp_traveler_cloak": {
        "name": "麻布旅人斗篷", "slot": "top", "level": 1, "unlock": "level",
        "ingredients": {"fabric_hemp": 4}, "sell_range": (30, 40),
    },
    "corduroy_traveler_coat": {
        "name": "灯芯绒旅人外套", "slot": "top", "level": 3, "unlock": "level",
        "ingredients": {"fabric_corduroy": 3}, "sell_range": (36, 46),
    },
    "velvet_dusk_cape": {
        "name": "暮色天鹅绒披风", "slot": "top", "level": 5, "unlock": "level",
        "ingredients": {"fabric_velvet": 2}, "sell_range": (40, 50),
    },
    "leather_huntsman_coat": {
        "name": "猎人皮革大衣", "slot": "top", "level": 6, "unlock": "level",
        "ingredients": {"fabric_leather": 3}, "sell_range": (44, 54),
    },
    "enchanted_thread_starlight_cloak": {
        "name": "星光魔法斗篷", "slot": "top", "level": 7, "unlock": "level",
        "ingredients": {"fabric_enchanted_thread": 2}, "sell_range": (46, 56),
    },
    "mink_frost_coat": {
        "name": "霜色貂皮大衣", "slot": "top", "level": 8, "unlock": "shop", "shop_price": 60,
        "ingredients": {"fabric_mink_fur": 2}, "sell_range": (46, 56),
    },
    "dragon_hide_armor_cloak": {
        "name": "龙鳞纹甲斗篷", "slot": "top", "level": 10, "unlock": "forest",
        "ingredients": {"fabric_dragon_hide": 1, "fabric_leather": 1}, "sell_range": (50, 60),
    },
    "waxed_rain_coat": {
        "name": "防水雨行外套", "slot": "top", "level": 4, "unlock": "shop", "shop_price": 35,
        "ingredients": {"fabric_waxed_cloth": 2}, "sell_range": (38, 48),
    },
    "warm_fleece_parka": {
        "name": "保暖绒毛大衣", "slot": "top", "level": 5, "unlock": "level",
        "ingredients": {"fabric_warm_fleece": 3}, "sell_range": (40, 50),
    },
    "pearl_button_blazer": {
        "name": "珍珠纽扣西装外套", "slot": "top", "level": 9, "unlock": "level",
        "ingredients": {"fabric_pearl_button": 2, "fabric_satin": 1}, "sell_range": (48, 58),
    },
    # ── 下装：裤子/半身裙 ──
    "linen_trousers": {
        "name": "亚麻长裤", "slot": "bottom", "level": 1, "unlock": "level",
        "ingredients": {"fabric_linen": 3}, "sell_range": (30, 40),
    },
    "wool_pleated_skirt": {
        "name": "羊毛百褶裙", "slot": "bottom", "level": 2, "unlock": "level",
        "ingredients": {"fabric_wool": 3}, "sell_range": (34, 44),
    },
    "satin_ribbon_skirt": {
        "name": "缎面丝带裙", "slot": "bottom", "level": 4, "unlock": "shop", "shop_price": 40,
        "ingredients": {"fabric_satin": 2}, "sell_range": (38, 48),
    },
    "stain_resist_cargo_trousers": {
        "name": "抗污旅者长裤", "slot": "bottom", "level": 7, "unlock": "level",
        "ingredients": {"fabric_stain_resist": 2}, "sell_range": (42, 52),
    },
    "gold_thread_court_skirt": {
        "name": "金线宫廷裙", "slot": "bottom", "level": 9, "unlock": "level",
        "ingredients": {"fabric_gold_thread": 2}, "sell_range": (46, 56),
    },
    "cotton_shorts": {
        "name": "棉布短裤", "slot": "bottom", "level": 1, "unlock": "level",
        "ingredients": {"fabric_cotton": 2}, "sell_range": (30, 36),
    },
    "corduroy_pants": {
        "name": "灯芯绒长裤", "slot": "bottom", "level": 3, "unlock": "level",
        "ingredients": {"fabric_corduroy": 3}, "sell_range": (36, 46),
    },
    "lace_trim_skirt": {
        "name": "蕾丝边半身裙", "slot": "bottom", "level": 5, "unlock": "shop", "shop_price": 35,
        "ingredients": {"fabric_lace": 2}, "sell_range": (40, 50),
    },
    "leather_riding_pants": {
        "name": "皮革骑装裤", "slot": "bottom", "level": 8, "unlock": "level",
        "ingredients": {"fabric_leather": 3}, "sell_range": (44, 54),
    },
    # ── 饰品：小件 ──
    "hemp_woven_bag": {
        "name": "麻布编织包", "slot": "accessory", "level": 2, "unlock": "shop", "shop_price": 25,
        "ingredients": {"fabric_hemp": 3}, "sell_range": (30, 40),
    },
    "feather_hair_clip": {
        "name": "羽毛发饰", "slot": "accessory", "level": 6, "unlock": "shop", "shop_price": 30,
        "ingredients": {"fabric_feather_trim": 2}, "sell_range": (38, 48),
    },
    "enchanted_thread_brooch": {
        "name": "魔法丝线胸针", "slot": "accessory", "level": 7, "unlock": "level",
        "ingredients": {"fabric_enchanted_thread": 1}, "sell_range": (42, 52),
    },
    "spider_silk_gloves": {
        "name": "蛛丝手套", "slot": "accessory", "level": 8, "unlock": "forest",
        "ingredients": {"fabric_spider_silk": 1}, "sell_range": (46, 56),
    },
    "phoenix_thread_pendant": {
        "name": "凤凰余烬项坠", "slot": "accessory", "level": 10, "unlock": "forest",
        "ingredients": {"fabric_phoenix_thread": 1}, "sell_range": (50, 60),
    },
    "unicorn_thread_tiara": {
        "name": "独角兽银辉发冠", "slot": "accessory", "level": 10, "unlock": "shop", "shop_price": 70,
        "ingredients": {"fabric_unicorn_thread": 1, "fabric_silver_thread": 1}, "sell_range": (50, 60),
    },
    "silk_bowtie": {
        "name": "丝绸领结", "slot": "accessory", "level": 1, "unlock": "level",
        "ingredients": {"fabric_silk": 1}, "sell_range": (30, 38),
    },
    "wool_scarf": {
        "name": "羊毛围巾", "slot": "accessory", "level": 3, "unlock": "shop", "shop_price": 20,
        "ingredients": {"fabric_wool": 2}, "sell_range": (34, 44),
    },
    "gold_thread_cufflinks": {
        "name": "金线袖扣", "slot": "accessory", "level": 5, "unlock": "level",
        "ingredients": {"fabric_gold_thread": 1}, "sell_range": (38, 48),
    },
    "dragon_hide_belt": {
        "name": "龙皮革腰带", "slot": "accessory", "level": 9, "unlock": "forest",
        "ingredients": {"fabric_dragon_hide": 1}, "sell_range": (48, 58),
    },
}

FOREST_PATTERN_KEYS = tuple(key for key, p in PATTERNS.items() if p["unlock"] == "forest")

# 按图纸要求等级分层的穿着播报文案，越难做的衣服动静越大
WEAR_LINES_BY_TIER = {
    1: "{name}穿上了{clothing}，看起来清爽干净。",
    2: "{name}穿上了{clothing}，收拾得整整齐齐。",
    3: "{name}穿着{clothing}走过，引来几声低低的讨论。",
    4: "{name}穿着{clothing}路过，回头率不低。",
    5: "{name}穿上{clothing}走进大厅，不少人多看了两眼。",
    6: "{name}穿着{clothing}出现，身边很快围上来几个人问在哪儿做的。",
    7: "{name}时尚地穿上了{clothing}，瞬间成为了这一层楼的焦点！",
    8: "{name}穿着{clothing}走进礼堂，交谈声都低了半拍。",
    9: "{name}穿着{clothing}亮相，礼堂安静了一瞬——随后爆发出低声惊叹。",
    10: "{name}穿上传说级的{clothing}走进人群，今晚学院里没有人能不谈论这件衣服。",
}

# 首次做出某款式（不是重复做）的播报文案，同样按图纸等级分层
UNLOCK_LINES_BY_TIER = {
    1: "{name}第一次成功做出了「{clothing}」，手艺还挺像样。",
    2: "{name}又琢磨出一件新花样——「{clothing}」。",
    3: "{name}捣鼓出了「{clothing}」，裁缝手艺又精进了一分。",
    4: "{name}设计出「{clothing}」，已经小有几分心得。",
    5: "{name}做出了「{clothing}」，开始有点大师风范了。",
    6: "{name}又解锁一件新款——「{clothing}」，衣橱越来越像样了。",
    7: "{name}做出了「{clothing}」，手艺已经不输马金夫人本人了！",
    8: "{name}攻克了「{clothing}」的裁剪难题，让人刮目相看。",
    9: "{name}做出了「{clothing}」，这份巧思已经传遍了裁缝圈。",
    10: "{name}竟然做出了传说级的「{clothing}」，时尚值直接封顶！",
}


class TailorError(Exception):
    pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # 旧存档迁移：CREATE TABLE IF NOT EXISTS 不会给已存在的表加新列，要单独补。
        try:
            conn.execute("ALTER TABLE tailor_progress ADD COLUMN fashion_points INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


init_db()


def _require_enrolled(uid: str):
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise TailorError("你还没有分院，先发「/入学」完成入学测试。")
    return player


def _progress_row(uid: str) -> sqlite3.Row:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tailor_progress WHERE uid=?", (uid,)).fetchone()
        if row:
            return row
        conn.execute(
            "INSERT INTO tailor_progress (uid, updated_at) VALUES (?, ?)",
            (uid, core_storage.now()),
        )
        conn.commit()
        return conn.execute("SELECT * FROM tailor_progress WHERE uid=?", (uid,)).fetchone()
    finally:
        conn.close()


def _learned_keys(uid: str) -> set[str]:
    conn = get_conn()
    try:
        return {
            row["pattern_key"]
            for row in conn.execute(
                "SELECT pattern_key FROM tailor_learned_patterns WHERE uid=?", (uid,)
            ).fetchall()
        }
    finally:
        conn.close()


def _is_available(pattern: dict, level: int, learned: set[str], pattern_key: str) -> bool:
    if pattern["unlock"] == "level":
        return level >= pattern["level"]
    return pattern_key in learned


# ======================== 缝纫课 ========================


def take_lesson(uid: str) -> dict:
    _require_enrolled(uid)
    row = _progress_row(uid)
    if row["level"] >= MAX_LEVEL:
        raise TailorError("你的缝纫技术已经满级了，不用再上课了。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < LESSON_STAMINA_COST:
        raise TailorError(
            f"体力不够，上缝纫课需要{LESSON_STAMINA_COST}点，你现在只有{player['stamina']}点。"
        )
    core_storage.spend_stamina(uid, LESSON_STAMINA_COST)

    new_level = row["level"] + 1
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE tailor_progress SET level=?, updated_at=? WHERE uid=?",
            (new_level, core_storage.now(), uid),
        )
        conn.commit()
    finally:
        conn.close()
    return {"level": new_level, "maxed": new_level >= MAX_LEVEL}


# ======================== 图纸 ========================


def buy_pattern(uid: str, pattern_key: str) -> dict:
    _require_enrolled(uid)
    pattern = PATTERNS.get(pattern_key)
    if not pattern or pattern["unlock"] != "shop":
        raise TailorError("这张图纸没法在这里购买。")

    row = _progress_row(uid)
    if row["level"] < pattern["level"]:
        raise TailorError(f"缝纫技术还不够，「{pattern['name']}」需要{pattern['level']}级。")
    if pattern_key in _learned_keys(uid):
        raise TailorError(f"你已经学过「{pattern['name']}」了。")

    price = pattern["shop_price"]
    if not core_storage.try_spend_galleons(uid, price):
        player = core_storage.get_player(uid)
        raise TailorError(f"加隆不够。当前{player['galleons']}，这张图纸要{price}加隆。")

    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tailor_learned_patterns (uid, pattern_key, learned_at) VALUES (?, ?, ?)",
            (uid, pattern_key, core_storage.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"name": pattern["name"], "price": price}


def learn_pattern_from_forest(uid: str) -> str | None:
    """禁林掉落图纸——forest.py 小概率调用。挑一张还没学会的forest款式，学会后返回名字。"""
    learned = _learned_keys(uid)
    candidates = [key for key in FOREST_PATTERN_KEYS if key not in learned]
    if not candidates:
        return None
    pattern_key = random.choice(candidates)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tailor_learned_patterns (uid, pattern_key, learned_at) VALUES (?, ?, ?)",
            (uid, pattern_key, core_storage.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return PATTERNS[pattern_key]["name"]


def available_patterns(uid: str) -> list[dict]:
    """给页面渲染用：每张图纸的解锁状态、材料是否齐全。"""
    row = _progress_row(uid)
    level = row["level"]
    learned = _learned_keys(uid)
    have = {r["item_key"]: r["quantity"] for r in school_storage.get_inventory(uid)}

    result = []
    for key, pattern in PATTERNS.items():
        unlocked = _is_available(pattern, level, learned, key)
        ingredients = [
            {
                "name": shop_catalog.find(item_key)[1] if shop_catalog.find(item_key) else item_key,
                "need": amount,
                "have": have.get(item_key, 0),
            }
            for item_key, amount in pattern["ingredients"].items()
        ]
        result.append(
            {
                "key": key,
                "name": pattern["name"],
                "slot": pattern["slot"],
                "level": pattern["level"],
                "unlock": pattern["unlock"],
                "shop_price": pattern.get("shop_price"),
                "ingredients": ingredients,
                "can_afford": all(i["have"] >= i["need"] for i in ingredients),
                "unlocked": unlocked,
                "sell_range": pattern["sell_range"],
            }
        )
    result.sort(key=lambda r: (not r["unlocked"], r["level"]))
    return result


def patterns_by_slot(uid: str) -> list[dict]:
    """给模板分组用：按上装/下装/裙装/饰品四个部位分组，组内按等级排序。"""
    patterns = available_patterns(uid)
    grouped: dict[str, list[dict]] = {slot: [] for slot in SLOT_ORDER}
    for p in patterns:
        grouped.setdefault(p["slot"], []).append(p)
    return [
        {"slot": slot, "slot_name": SLOT_NAMES[slot], "patterns": grouped[slot]}
        for slot in SLOT_ORDER
        if grouped[slot]
    ]


# ======================== 做衣服 ========================


def craft(uid: str, pattern_key: str) -> dict:
    _require_enrolled(uid)
    pattern = PATTERNS.get(pattern_key)
    if not pattern:
        raise TailorError("没有这张图纸。")

    row = _progress_row(uid)
    if not _is_available(pattern, row["level"], _learned_keys(uid), pattern_key):
        raise TailorError(f"「{pattern['name']}」还没解锁。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        missing = []
        for item_key, amount in pattern["ingredients"].items():
            have = conn.execute(
                "SELECT quantity FROM inventory WHERE uid=? AND item_key=?", (uid, item_key)
            ).fetchone()
            have_qty = have["quantity"] if have else 0
            if have_qty < amount:
                item = shop_catalog.find(item_key)
                name = item[1] if item else item_key
                missing.append(f"{name}×{amount - have_qty}")
        if missing:
            conn.rollback()
            raise TailorError("材料还不够：" + "、".join(missing))

        for item_key, amount in pattern["ingredients"].items():
            conn.execute(
                "UPDATE inventory SET quantity=quantity-? WHERE uid=? AND item_key=?",
                (amount, uid, item_key),
            )
        conn.execute(
            "INSERT INTO tailor_inventory (uid, clothing_key, quantity) VALUES (?, ?, 1) "
            "ON CONFLICT(uid, clothing_key) DO UPDATE SET quantity=quantity+1",
            (uid, pattern_key),
        )

        is_new_design = conn.execute(
            "INSERT OR IGNORE INTO tailor_crafted_keys (uid, pattern_key, crafted_at) VALUES (?, ?, ?)",
            (uid, pattern_key, core_storage.now()),
        ).rowcount > 0
        fashion_gain = pattern["level"] if is_new_design else 0

        conn.execute(
            "UPDATE tailor_progress SET total_crafted=total_crafted+1, "
            "fashion_points=fashion_points+?, updated_at=? WHERE uid=?",
            (fashion_gain, core_storage.now(), uid),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result = {"name": pattern["name"], "sell_range": pattern["sell_range"], "is_new_design": is_new_design}
    if is_new_design:
        tier = min(10, max(1, pattern["level"]))
        display_name = core_storage.get_full_name(uid)
        result["fashion_gain"] = fashion_gain
        result["notify_text"] = UNLOCK_LINES_BY_TIER[tier].format(name=display_name, clothing=pattern["name"])
    return result


def my_wardrobe(uid: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT clothing_key, quantity FROM tailor_inventory WHERE uid=? AND quantity>0", (uid,)
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "key": r["clothing_key"],
            "name": PATTERNS[r["clothing_key"]]["name"],
            "slot_name": SLOT_NAMES[PATTERNS[r["clothing_key"]]["slot"]],
            "quantity": r["quantity"],
        }
        for r in rows
        if r["clothing_key"] in PATTERNS
    ]


# ======================== 自己穿 ========================


def wear(uid: str, clothing_key: str) -> dict:
    pattern = PATTERNS.get(clothing_key)
    if not pattern:
        raise TailorError("没有这件衣服。")

    conn = get_conn()
    try:
        owned = conn.execute(
            "SELECT quantity FROM tailor_inventory WHERE uid=? AND clothing_key=?", (uid, clothing_key)
        ).fetchone()
    finally:
        conn.close()
    if not owned or owned["quantity"] <= 0:
        raise TailorError(f"衣橱里没有「{pattern['name']}」。")

    day = core_storage.get_current_day() or 1
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO tailor_wear_daily (uid, day, count) VALUES (?, ?, 0)", (uid, day))
        used = conn.execute(
            "SELECT count FROM tailor_wear_daily WHERE uid=? AND day=?", (uid, day)
        ).fetchone()["count"]
        if used >= WEAR_DAILY_LIMIT:
            conn.rollback()
            raise TailorError(f"今天已经穿出去秀过{WEAR_DAILY_LIMIT}次了，明天再来。")
        conn.execute(
            "UPDATE tailor_wear_daily SET count=count+1 WHERE uid=? AND day=?", (uid, day)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    name = core_storage.get_full_name(uid)
    tier = min(10, max(1, pattern["level"]))
    notify_text = WEAR_LINES_BY_TIER[tier].format(name=name, clothing=pattern["name"])
    return {"name": pattern["name"], "notify_text": notify_text}


# ======================== 摆摊 ========================


def list_for_sale(uid: str, clothing_key: str) -> dict:
    if clothing_key not in PATTERNS:
        raise TailorError("没有这件衣服。")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        removed = conn.execute(
            "UPDATE tailor_inventory SET quantity=quantity-1 WHERE uid=? AND clothing_key=? AND quantity>0",
            (uid, clothing_key),
        )
        if removed.rowcount == 0:
            conn.rollback()
            raise TailorError(f"衣橱里没有「{PATTERNS[clothing_key]['name']}」了。")
        now = core_storage.now()
        conn.execute(
            "INSERT INTO tailor_listings (uid, clothing_key, listed_at, next_check_at) VALUES (?, ?, ?, ?)",
            (uid, clothing_key, now, now + SALE_CHECK_INTERVAL),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"name": PATTERNS[clothing_key]["name"]}


def _process_listings(uid: str) -> tuple[list[dict], int]:
    """懒结算：按经过的整点小时数补算摇号。卖掉一件就从列表里摘掉、记进账；
    没卖掉的把next_check_at往后滚一轮，等下次再摇。今天卖满 SALE_DAILY_LIMIT 件之后，
    剩下的摇号直接当作没卖出——衣服留在摊位上，等明天再继续摇。
    返回（这次结算卖出的事件列表，今天累计卖出件数）。"""
    day = core_storage.get_current_day() or 1
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO tailor_sale_daily (uid, day, count) VALUES (?, ?, 0)", (uid, day))
        sold_today = conn.execute(
            "SELECT count FROM tailor_sale_daily WHERE uid=? AND day=?", (uid, day)
        ).fetchone()["count"]

        rows = conn.execute("SELECT * FROM tailor_listings WHERE uid=?", (uid,)).fetchall()
        now = core_storage.now()
        sold_events = []
        for row in rows:
            next_check = row["next_check_at"]
            sold = False
            amount = 0
            while now >= next_check:
                if sold_today < SALE_DAILY_LIMIT and random.random() < SALE_CHANCE:
                    pattern = PATTERNS.get(row["clothing_key"])
                    lo, hi = pattern["sell_range"] if pattern else (30, 60)
                    amount = random.randint(lo, hi)
                    sold = True
                    break
                next_check += SALE_CHECK_INTERVAL
            if sold:
                sold_today += 1
                conn.execute("DELETE FROM tailor_listings WHERE id=?", (row["id"],))
                conn.execute(
                    "UPDATE players SET galleons=galleons+?, updated_at=? WHERE uid=?",
                    (amount, now, uid),
                )
                conn.execute(
                    "UPDATE tailor_progress SET total_earned=total_earned+?, updated_at=? WHERE uid=?",
                    (amount, now, uid),
                )
                name = PATTERNS[row["clothing_key"]]["name"] if row["clothing_key"] in PATTERNS else row["clothing_key"]
                sold_events.append({"name": name, "amount": amount})
            elif next_check != row["next_check_at"]:
                conn.execute(
                    "UPDATE tailor_listings SET next_check_at=? WHERE id=?", (next_check, row["id"])
                )
        conn.execute(
            "UPDATE tailor_sale_daily SET count=? WHERE uid=? AND day=?", (sold_today, uid, day)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return sold_events, sold_today


def my_listings(uid: str) -> dict:
    sold_events, sold_today = _process_listings(uid)
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM tailor_listings WHERE uid=? ORDER BY listed_at", (uid,)).fetchall()
    finally:
        conn.close()
    now = core_storage.now()
    listings = [
        {
            "name": PATTERNS[r["clothing_key"]]["name"] if r["clothing_key"] in PATTERNS else r["clothing_key"],
            "listed_at": r["listed_at"],
            "next_check_in": max(0, r["next_check_at"] - now),
        }
        for r in rows
    ]
    return {
        "listings": listings,
        "sold_events": sold_events,
        "sold_today": sold_today,
        "sale_daily_limit": SALE_DAILY_LIMIT,
    }


# ======================== 状态 / 排行榜 ========================


def status(uid: str) -> dict:
    row = _progress_row(uid)
    return {
        "level": row["level"],
        "maxed": row["level"] >= MAX_LEVEL,
        "total_crafted": row["total_crafted"],
        "total_earned": row["total_earned"],
        "fashion_points": row["fashion_points"],
    }


def leaderboard(limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tailor_progress WHERE total_earned > 0 ORDER BY total_earned DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "name": core_storage.get_full_name(r["uid"]),
            "level": r["level"],
            "total_crafted": r["total_crafted"],
            "total_earned": r["total_earned"],
        }
        for r in rows
    ]


def fashion_leaderboard(limit: int = 20) -> list[dict]:
    """时尚达人榜：按解锁新款式攒下的时尚值排名，跟上面按卖出所得排的裁缝排行榜是两回事。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tailor_progress WHERE fashion_points > 0 ORDER BY fashion_points DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "name": core_storage.get_full_name(r["uid"]),
            "level": r["level"],
            "fashion_points": r["fashion_points"],
        }
        for r in rows
    ]
