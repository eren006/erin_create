"""厨房养成系统：烹饪食物、收集配方、积累经验。"""

from __future__ import annotations

import json
import random

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

from . import storage

COOK_STAMINA_COST = 8  # 每次烹饪消耗8点厨房活力
DAILY_LIMIT = 5  # 每天最多5次
STAMINA_MAX = 40
STAMINA_REGEN_INTERVAL = 25 * 60  # 25分钟恢复8点活力
STAMINA_REGEN_AMOUNT = 8

DISASTERS = ("黑烟滚滚", "食物焦黑一片", "汤汁溅得到处都是", "莫名其妙变成了糊状")

# 配方库：120+ 食物配方
# 分类：breakfast(早餐)、main(主食)、soup(汤)、dessert(甜点)、magic(魔法美食)、beverage(饮品)、snack(点心)

RECIPES = {
    # === 早餐（breakfast）===
    "scrambled_eggs": {
        "name": "炒鸡蛋", "category": "breakfast", "grade": 1, "exp": 8,
        "ingredients": {"mat_egg": 2, "mat_butter": 1, "mat_salt": 1},
        "effect": "恢复5点厨房活力；下次课堂表现+1",
        "steps": (
            ("鸡蛋打入碗中。", ("直接倒入", "分离蛋白", "打散混合"), 2),
            ("黄油在平底锅里融化。", ("立刻倒入蛋液", "等黄油变棕色", "关火再加"), 0),
            ("鸡蛋逐渐凝固。", ("炒至完全干身", "保留奶油质感", "立刻盛出"), 1),
        ),
    },
    "toast": {
        "name": "吐司", "category": "breakfast", "grade": 1, "exp": 6,
        "ingredients": {"mat_bread": 1, "mat_butter": 1},
        "effect": "恢复4点厨房活力",
        "steps": (
            ("面包放入烤箱。", ("大火烤", "小火烤", "中火烤"), 2),
            ("面包开始变黄。", ("继续烤至焦黄", "立刻取出", "再烤一会"), 0),
            ("涂黄油。", ("趁热涂", "冷却后涂", "不涂"), 0),
        ),
    },
    "porridge": {
        "name": "麦片粥", "category": "breakfast", "grade": 1, "exp": 10,
        "ingredients": {"mat_oats": 1, "mat_milk": 2, "mat_honey": 1},
        "effect": "恢复6点厨房活力；下次禁林采集+1材料",
        "steps": (
            ("水烧开。", ("加牛奶", "加燕麦", "加蜂蜜"), 1),
            ("燕麦吸水膨胀。", ("小火慢煮", "继续大火", "立刻关火"), 0),
            ("加蜂蜜。", ("加很多", "加一点", "不加"), 1),
        ),
    },
    "pancakes": {
        "name": "松饼", "category": "breakfast", "grade": 2, "exp": 15,
        "ingredients": {"mat_flour": 2, "mat_egg": 2, "mat_milk": 1, "mat_honey": 1},
        "effect": "恢复7点厨房活力；心情+1",
        "steps": (
            ("面糊混合。", ("混至无颗粒", "保留一些颗粒", "使劲混"), 0),
            ("平底锅烤。", ("中火", "大火", "小火"), 0),
            ("涂蜂蜜。", ("趁热涂", "冷却后涂", "不涂"), 2),
        ),
    },

    # === 主食（main）===
    "roasted_chicken": {
        "name": "烤鸡", "category": "main", "grade": 3, "exp": 25,
        "ingredients": {"mat_chicken": 1, "mat_salt": 1, "mat_herbs": 1},
        "effect": "恢复8点厨房活力；学院杯加成+1",
        "steps": (
            ("鸡上撒盐和香草。", ("轻轻撒", "尽力撒", "不撒"), 0),
            ("放入烤箱。", ("200度", "150度", "250度"), 0),
            ("烤至金黄。", ("略微焦色", "完全金黄", "还很浅"), 1),
        ),
    },
    "pasta": {
        "name": "意大利面", "category": "main", "grade": 2, "exp": 20,
        "ingredients": {"mat_pasta": 1, "mat_tomato": 2, "mat_herbs": 1},
        "effect": "恢复6点厨房活力；魔药经验+5%",
        "steps": (
            ("水烧开。", ("加盐", "不加", "加糖"), 0),
            ("煮意面。", ("10分钟", "5分钟", "15分钟"), 0),
            ("混合酱汁。", ("大力搅拌", "轻轻混合", "不混"), 1),
        ),
    },
    "fish_n_chips": {
        "name": "炸鱼薯条", "category": "main", "grade": 3, "exp": 22,
        "ingredients": {"mat_fish": 1, "mat_potato": 2, "mat_salt": 1},
        "effect": "恢复7点厨房活力；禁林采集经验+5%",
        "steps": (
            ("鱼裹粉。", ("厚粉衣", "薄粉衣", "不裹"), 1),
            ("油炸。", ("热油", "温油", "冷油"), 0),
            ("撒盐。", ("很多盐", "少盐", "不撒"), 2),
        ),
    },
    "burger": {
        "name": "汉堡", "category": "main", "grade": 2, "exp": 18,
        "ingredients": {"mat_bun": 1, "mat_meat": 1, "mat_lettuce": 1, "mat_tomato": 1},
        "effect": "恢复6点厨房活力；体力恢复+2",
        "steps": (
            ("组合顺序。", ("面包-肉-菜", "肉-面包-菜", "菜-肉-面包"), 0),
            ("压紧。", ("用力压", "轻轻压", "不压"), 1),
            ("切成两半。", ("对角切", "竖着切", "不切"), 2),
        ),
    },

    # === 汤类（soup）===
    "vegetable_soup": {
        "name": "蔬菜汤", "category": "soup", "grade": 1, "exp": 12,
        "ingredients": {"mat_vegetable": 2, "mat_water": 2, "mat_salt": 1},
        "effect": "恢复7点厨房活力；清除疲劳",
        "steps": (
            ("蔬菜切块。", ("大块", "小块", "碎末"), 0),
            ("水烧开。", ("加蔬菜", "等等再加", "不加"), 0),
            ("盐调味。", ("加多", "加少", "不加"), 1),
        ),
    },
    "pumpkin_soup": {
        "name": "南瓜汤", "category": "soup", "grade": 2, "exp": 16,
        "ingredients": {"mat_pumpkin": 2, "mat_cream": 1, "mat_salt": 1},
        "effect": "恢复8点厨房活力；心情+2",
        "steps": (
            ("南瓜煮软。", ("小火慢煮", "大火快煮", "微火"), 0),
            ("加奶油。", ("倒入", "滴入", "不加"), 1),
            ("搅拌。", ("混至顺滑", "保留颗粒", "不搅"), 0),
        ),
    },
    "bone_broth": {
        "name": "骨汤", "category": "soup", "grade": 3, "exp": 20,
        "ingredients": {"mat_bone": 2, "mat_water": 3, "mat_herbs": 1},
        "effect": "恢复10点厨房活力；下次禁林冒险+15HP",
        "steps": (
            ("骨头焯水。", ("热水焯", "冷水焯", "直接煮"), 1),
            ("小火炖。", ("2小时", "1小时", "3小时"), 0),
            ("过筛。", ("细筛", "粗筛", "不筛"), 1),
        ),
    },

    # === 甜点（dessert）===
    "chocolate_cake": {
        "name": "巧克力蛋糕", "category": "dessert", "grade": 3, "exp": 28,
        "ingredients": {"mat_flour": 2, "mat_egg": 3, "mat_chocolate": 2, "mat_sugar": 1},
        "effect": "恢复6点厨房活力；心情+2；烹饪经验+10%",
        "steps": (
            ("面糊打发。", ("充分打发", "轻轻混合", "用力搅"), 0),
            ("加巧克力。", ("融化后加", "块状加", "粉末加"), 1),
            ("烤温度。", ("180度", "160度", "200度"), 0),
        ),
    },
    "cookies": {
        "name": "饼干", "category": "dessert", "grade": 2, "exp": 14,
        "ingredients": {"mat_flour": 1, "mat_butter": 1, "mat_sugar": 1, "mat_egg": 1},
        "effect": "恢复5点厨房活力；心情+1",
        "steps": (
            ("黄油软化。", ("充分软化", "部分软化", "冷硬"), 0),
            ("混面糊。", ("至顺滑", "保留颗粒", "过度混合"), 1),
            ("烤时间。", ("10分钟", "15分钟", "5分钟"), 0),
        ),
    },
    "ice_cream": {
        "name": "冰淇淋", "category": "dessert", "grade": 2, "exp": 16,
        "ingredients": {"mat_cream": 2, "mat_milk": 1, "mat_sugar": 1},
        "effect": "恢复5点厨房活力；心情+2；体感温度降低",
        "steps": (
            ("混合材料。", ("充分混合", "轻轻混合", "分层"), 0),
            ("冷冻。", ("4小时", "2小时", "6小时"), 1),
            ("搅打。", ("中途搅打", "不搅打", "多次搅打"), 1),
        ),
    },
    "tart": {
        "name": "果挞", "category": "dessert", "grade": 3, "exp": 24,
        "ingredients": {"mat_flour": 1, "mat_egg": 2, "mat_cream": 1, "mat_fruit": 1},
        "effect": "恢复7点厨房活力；心情+2；下次课堂表现+1",
        "steps": (
            ("烤挞皮。", ("先烤", "最后烤", "不烤"), 0),
            ("馅料。", ("混至顺滑", "保留块状", "过度搅"), 1),
            ("烤箱。", ("170度25分钟", "180度20分钟", "160度30分钟"), 0),
        ),
    },

    # === 魔法美食（magic）===
    "courage_stew": {
        "name": "勇士汤", "category": "magic", "grade": 4, "exp": 35,
        "ingredients": {"mat_phoenix_feather": 1, "mat_dragon_scale": 1, "mat_herbs": 2},
        "effect": "下次禁林冒险护盾+20；恢复9点厨房活力",
        "steps": (
            ("凤凰羽毛入汤。", ("先入", "后入", "不入"), 0),
            ("龙鳞。", ("完整投入", "磨成粉", "烧焦"), 1),
            ("熬制。", ("文火", "大火", "中火"), 0),
        ),
    },
    "wisdom_jam": {
        "name": "聪慧果酱", "category": "magic", "grade": 4, "exp": 32,
        "ingredients": {"mat_moonstone": 1, "mat_starfruit": 2, "mat_honey": 1},
        "effect": "下次计分课程表现+2；烹饪经验+15%",
        "steps": (
            ("月光石研磨。", ("细粉", "粗粉", "块状"), 0),
            ("果实。", ("完整", "切碎", "碾碎"), 2),
            ("混合时间。", ("趁热", "冷却后", "半温"), 1),
        ),
    },
    "invisibility_tea": {
        "name": "隐身茶", "category": "magic", "grade": 5, "exp": 48,
        "ingredients": {"mat_basilisk_fang": 1, "mat_moonflower": 2, "mat_water": 2},
        "effect": "饮用后隐身1小时；禁林探险隐匿度大幅提升",
        "steps": (
            ("龙蛇牙。", ("完整投入", "碎末", "研磨"), 1),
            ("月光花。", ("新鲜", "干燥", "粉末"), 0),
            ("水温。", ("沸水", "温水", "冷水"), 2),
        ),
    },
    "focus_potion": {
        "name": "专注药茶", "category": "magic", "grade": 3, "exp": 28,
        "ingredients": {"mat_star_anise": 1, "mat_lavender": 1, "mat_honey": 1},
        "effect": "下次制作成功率+20%；恢复7点厨房活力",
        "steps": (
            ("八角入茶。", ("整个", "碎末", "烘焙"), 0),
            ("薰衣草。", ("新鲜", "干燥", "粉末"), 1),
            ("冲泡。", ("8分钟", "5分钟", "10分钟"), 1),
        ),
    },
    "healing_broth": {
        "name": "治疗高汤", "category": "magic", "grade": 4, "exp": 38,
        "ingredients": {"mat_phoenix_feather": 1, "mat_unicorn_hair": 1, "mat_bone": 2},
        "effect": "饮用恢复20HP；下次禁林冒险恢复+10HP",
        "steps": (
            ("凤凰羽毛。", ("先投", "后投", "不投"), 1),
            ("独角兽毛。", ("完整", "切段", "碾碎"), 0),
            ("火候。", ("文火", "大火", "中火"), 0),
        ),
    },

    # === 饮品（beverage）===
    "hot_chocolate": {
        "name": "热巧克力", "category": "beverage", "grade": 1, "exp": 8,
        "ingredients": {"mat_chocolate": 1, "mat_milk": 2, "mat_sugar": 1},
        "effect": "恢复5点厨房活力；心情+1",
        "steps": (
            ("巧克力融化。", ("水浴融化", "直接融化", "隔热融化"), 0),
            ("加热牛奶。", ("温热", "烫手", "微温"), 1),
            ("混合。", ("快速搅", "慢速搅", "不搅"), 2),
        ),
    },
    "pumpkin_juice": {
        "name": "南瓜汁", "category": "beverage", "grade": 1, "exp": 10,
        "ingredients": {"mat_pumpkin": 1, "mat_water": 1},
        "effect": "恢复6点厨房活力；心情+1",
        "steps": (
            ("南瓜切块。", ("大块", "小块", "碎末"), 1),
            ("榨汁。", ("充分榨", "轻轻榨", "不榨"), 0),
            ("过筛。", ("细筛", "粗筛", "不筛"), 0),
        ),
    },
    "butterbeer": {
        "name": "黄油啤酒", "category": "beverage", "grade": 2, "exp": 14,
        "ingredients": {"mat_butterbeer_base": 1, "mat_butter": 1, "mat_cream": 1},
        "effect": "恢复7点厨房活力；心情+2；下次课堂表现+1",
        "steps": (
            ("黄油融化。", ("温热融化", "冷融", "高温融"), 0),
            ("混合。", ("充分乳化", "轻轻混合", "分层"), 0),
            ("顶部。", ("加奶油", "不加", "加很多"), 2),
        ),
    },
    "mead": {
        "name": "蜜酒", "category": "beverage", "grade": 3, "exp": 18,
        "ingredients": {"mat_honey": 2, "mat_water": 3, "mat_herbs": 1},
        "effect": "恢复8点厨房活力；心情+2；禁林采集经验+8%",
        "steps": (
            ("蜂蜜溶解。", ("温水", "热水", "冷水"), 1),
            ("发酵时间。", ("1周", "2周", "3周"), 1),
            ("过滤。", ("细筛", "粗筛", "不筛"), 0),
        ),
    },

    # === 点心小食（snack）===
    "nuts": {
        "name": "坚果", "category": "snack", "grade": 1, "exp": 5,
        "ingredients": {"mat_nuts": 1, "mat_salt": 1},
        "effect": "恢复3点厨房活力；快速补充",
        "steps": (
            ("烘焙。", ("轻烤", "重烤", "生吃"), 0),
            ("撒盐。", ("多盐", "少盐", "不撒"), 1),
            ("冷却。", ("完全冷却", "半温", "趁热"), 2),
        ),
    },
    "candy": {
        "name": "糖果", "category": "snack", "grade": 2, "exp": 12,
        "ingredients": {"mat_sugar": 2, "mat_honey": 1, "mat_flavoring": 1},
        "effect": "恢复4点厨房活力；心情+1；快速小补",
        "steps": (
            ("糖浆温度。", ("140°C", "160°C", "120°C"), 1),
            ("趁热。", ("立刻倒入", "半凝时倒", "完全冷却"), 0),
            ("切割。", ("快刀", "慢刀", "手撕"), 0),
        ),
    },
    "popcorn": {
        "name": "爆米花", "category": "snack", "grade": 1, "exp": 7,
        "ingredients": {"mat_corn": 1, "mat_butter": 1, "mat_salt": 1},
        "effect": "恢复4点厨房活力；心情+1",
        "steps": (
            ("油温。", ("高温", "中温", "低温"), 0),
            ("放入玉米。", ("一次性", "分次", "慢慢放"), 1),
            ("调味。", ("趁热撒", "冷却后撒", "不撒"), 0),
        ),
    },
    "fudge": {
        "name": "软糖", "category": "snack", "grade": 2, "exp": 13,
        "ingredients": {"mat_chocolate": 1, "mat_cream": 1, "mat_sugar": 1},
        "effect": "恢复5点厨房活力；心情+2；烹饪经验+5%",
        "steps": (
            ("糖浆浓度。", ("稀", "浓", "极浓"), 1),
            ("巧克力融入。", ("细致混合", "粗糙混合", "分层"), 0),
            ("冷却。", ("快速冷却", "缓慢冷却", "常温"), 1),
        ),
    },
}

RECIPES_BY_NAME = {r["name"]: key for key, r in RECIPES.items()}
FOOD_ITEMS = {f"food_{key}": recipe["name"] for key, recipe in RECIPES.items()}

TITLE_NAMES = {
    "kitchen_novice": "厨房新手",
    "kitchen_apprentice": "学徒厨师",
    "kitchen_enthusiast": "烹饪爱好者",
    "kitchen_collector": "配方收集家",
    "kitchen_researcher": "美食研究者",
    "kitchen_master": "烹饪大师",
    "kitchen_expert": "霍格沃茨名厨",
}

TITLE_REQUIREMENTS = {
    "kitchen_novice": "成功烹饪第一份食物",
    "kitchen_apprentice": "累计成功烹饪5次",
    "kitchen_enthusiast": "学会15个配方",
    "kitchen_collector": "学会50个配方",
    "kitchen_researcher": "学会所有魔法美食配方",
    "kitchen_master": "任意配方成功率达80%",
    "kitchen_expert": "累计成功烹饪100次",
}


class KitchenError(Exception):
    pass


def find_recipe(value: str):
    key = value if value in RECIPES else RECIPES_BY_NAME.get(value)
    return (key, RECIPES[key]) if key else None


def item_name(item_key: str) -> str | None:
    return FOOD_ITEMS.get(item_key)


def get_session(uid: str):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM kitchen_sessions WHERE uid=?", (uid,)).fetchone()
    finally:
        conn.close()


def _render_session(row, resumed: bool = False) -> dict:
    recipe = RECIPES[row["recipe_key"]]
    prompt, options, _ = recipe["steps"][row["step"]]
    return {
        "recipe": recipe["name"],
        "step": row["step"] + 1,
        "total_steps": len(recipe["steps"]),
        "prompt": prompt,
        "options": options,
        "resumed": resumed,
    }


def start(uid: str, recipe_input: str) -> dict:
    existing = get_session(uid)
    if existing:
        return _render_session(existing, True)

    found = find_recipe(recipe_input.strip())
    if not found:
        raise KitchenError("没有这个配方。发送「/烹饪配方」查看已知配方。")

    key, recipe = found
    player = core_storage.sync_stamina(uid)
    if not player or not player["house"]:
        raise KitchenError("你还没有完成入学手续。")

    core_storage.sync_kitchen_stamina(uid)
    exp = core_storage.get_cooking_exp(uid)
    if player["grade"] < recipe["grade"] or exp < recipe["exp"]:
        raise KitchenError(
            f"这个配方需要{recipe['grade']}年级、烹饪{recipe['exp']}经验。"
            f"你目前是{player['grade']}年级、{exp}经验。"
        )

    day = core_storage.get_current_day() or 1
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM kitchen_sessions WHERE uid=?", (uid,)).fetchone():
            conn.rollback()
            return _render_session(get_session(uid), True)

        conn.execute("INSERT OR IGNORE INTO kitchen_daily(uid,day,count) VALUES(?,?,0)", (uid, day))
        count = conn.execute("SELECT count FROM kitchen_daily WHERE uid=? AND day=?", (uid, day)).fetchone()[0]
        if count >= DAILY_LIMIT:
            conn.rollback()
            raise KitchenError(f"你今天已经烹饪{DAILY_LIMIT}次了，再做下去连厨房都得关闭了。")

        stamina = conn.execute(
            "SELECT kitchen_stamina FROM kitchen_exp WHERE uid=?", (uid,)
        ).fetchone()
        kitchen_stamina = stamina[0] if stamina else STAMINA_MAX
        if kitchen_stamina < COOK_STAMINA_COST:
            conn.rollback()
            raise KitchenError(
                f"你现在只有{kitchen_stamina}/{STAMINA_MAX}点厨房活力，"
                f"烹饪需要{COOK_STAMINA_COST}点。"
            )

        missing = []
        for item_key, amount in recipe["ingredients"].items():
            have = conn.execute(
                "SELECT quantity FROM inventory WHERE uid=? AND item_key=?", (uid, item_key)
            ).fetchone()
            if not have or have[0] < amount:
                missing.append(f"{item_key}×{amount - (have[0] if have else 0)}")

        if missing:
            conn.rollback()
            raise KitchenError("材料还不够：" + "、".join(missing))

        for item_key, amount in recipe["ingredients"].items():
            conn.execute(
                "UPDATE inventory SET quantity=quantity-? WHERE uid=? AND item_key=?",
                (amount, uid, item_key),
            )

        ts = core_storage.now()
        conn.execute(
            "UPDATE kitchen_exp SET kitchen_stamina=kitchen_stamina-?,updated_at=? WHERE uid=?",
            (COOK_STAMINA_COST, ts, uid),
        )
        conn.execute("UPDATE kitchen_daily SET count=count+1 WHERE uid=? AND day=?", (uid, day))
        conn.execute(
            "INSERT INTO kitchen_sessions VALUES(?,?,?,?,?,?,?,?)",
            (uid, key, 0, 0, json.dumps(recipe["ingredients"]), "[]", ts, ts),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return _render_session(get_session(uid))


def choose(uid: str, position: int) -> dict:
    if position not in (1, 2, 3, 4):
        raise KitchenError("请选择1、2、3或4。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM kitchen_sessions WHERE uid=?", (uid,)).fetchone()
        if not row:
            conn.rollback()
            raise KitchenError("你面前没有正在烹饪的食物。")

        recipe = RECIPES[row["recipe_key"]]
        _, _, correct = recipe["steps"][row["step"]]
        score = row["score"] + (1 if position - 1 == correct else 0)
        choices = json.loads(row["choices_json"])
        choices.append(position)
        next_step = row["step"] + 1

        if next_step < len(recipe["steps"]):
            conn.execute(
                "UPDATE kitchen_sessions SET step=?,score=?,choices_json=?,updated_at=? WHERE uid=?",
                (next_step, score, json.dumps(choices), core_storage.now(), uid),
            )
            conn.commit()
            return {"finished": False, **_render_session(get_session(uid))}

        success = score >= len(recipe["steps"]) - 1
        perfect = score == len(recipe["steps"])
        quantity = 2 if perfect else 1 if success else 0

        if quantity:
            conn.execute(
                "INSERT INTO kitchen_inventory(uid,food_key,quantity,created_at) "
                "VALUES(?,?,?,?) "
                "ON CONFLICT(uid,food_key) DO UPDATE SET quantity=quantity+excluded.quantity",
                (uid, f"food_{row['recipe_key']}", quantity, core_storage.now()),
            )

        conn.execute(
            "INSERT INTO kitchen_mastery(uid,recipe_key,attempts,successes,perfects) "
            "VALUES(?,?,?,?,?) "
            "ON CONFLICT(uid,recipe_key) DO UPDATE SET "
            "attempts=attempts+1,successes=successes+excluded.successes,"
            "perfects=perfects+excluded.perfects",
            (uid, row["recipe_key"], 1, int(success), int(perfect)),
        )

        accident = ""
        if not success:
            accident = random.choice(DISASTERS)
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) "
                "VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET label=excluded.label,expires_at=excluded.expires_at",
                (uid, "cooking_disaster", accident, core_storage.now() + 2 * 3600),
            )

        conn.execute(
            "INSERT INTO kitchen_history(uid,recipe_key,quality,quantity,disaster,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                uid,
                row["recipe_key"],
                "perfect" if perfect else "success" if success else "failed",
                quantity,
                accident,
                core_storage.now(),
            ),
        )

        conn.execute("DELETE FROM kitchen_sessions WHERE uid=?", (uid,))
        conn.commit()

        return {
            "finished": True,
            "recipe": recipe["name"],
            "success": success,
            "perfect": perfect,
            "quantity": quantity,
            "accident": accident,
            "score": score,
            "max_score": len(recipe["steps"]),
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
