"""可中断恢复的魔药熬制，以及成品药剂的实际效果。"""

from __future__ import annotations

import json
import random

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

from . import storage

BREW_STAMINA_COST = 4
DAILY_LIMIT = 2
TRADE_DAILY_LIMIT = 3
CORE_RECIPE_KEYS = ("energizing", "focus", "healing", "protection", "wolfsbane")

# key: 名称、年级、魔药经验、材料、三个步骤（提示、选项、正确下标）、说明
RECIPES = {
    "energizing": {
        "name": "提神剂", "grade": 2, "exp": 16,
        "ingredients": {"mat_knotgrass": 1, "mat_leech": 1},
        "effect": "恢复7点体力；不能降低课堂疲劳。",
        "steps": (
            ("水蛭开始蜷缩，结节草仍浮在表面。", ("直接碾碎投入", "先切碎结节草，再压出水蛭汁液", "整份倒进坩埚"), 1),
            ("药液冒出密集的小泡，颜色正由褐色转绿。", ("改用小火慢煨", "继续大火催沸", "立刻熄火"), 0),
            ("液面稳定下来，只剩一道细细的银线。", ("顺时针搅拌三圈", "逆时针搅拌三圈", "不再搅拌，马上装瓶"), 1),
        ),
    },
    "focus": {
        "name": "振奋药剂", "grade": 2, "exp": 32,
        "ingredients": {"mat_knotgrass": 2, "mat_flobberworm": 1},
        "effect": "下一次计分课堂的课堂表现额外+1。",
        "steps": (
            ("黏液挂在银勺上，迟迟不肯落下。", ("先加热银勺", "用力甩进坩埚", "兑水稀释"), 0),
            ("药液逐渐清亮，却闻起来过分甜腻。", ("加入两份切碎的结节草", "只加入一份", "继续熬到气味消失"), 0),
            ("坩埚边缘浮起一圈金色薄沫。", ("撇去薄沫再装瓶", "连薄沫一起装瓶", "加入冷水压下薄沫"), 0),
        ),
    },
    "healing": {
        "name": "愈合药剂", "grade": 3, "exp": 56,
        "ingredients": {"mat_leech": 1, "mat_flobberworm": 1, "mat_lacewing": 1},
        "effect": "禁林战斗中恢复25HP；每趟限用1瓶。",
        "steps": (
            ("草蛉翅膀遇热便会失去药性。", ("先投入草蛉", "离火后再投入草蛉", "与水蛭一起研碎"), 1),
            ("深红药液开始黏住搅拌棒。", ("加入毛虫黏液稳定药性", "加大火力", "停止搅拌等待分层"), 0),
            ("药液从深红变成温和的石榴色。", ("趁热装瓶", "冷却到完全透明再装瓶", "再煮十分钟"), 0),
        ),
    },
    "protection": {
        "name": "防护药剂", "grade": 4, "exp": 88,
        "ingredients": {"mat_flobberworm": 2, "mat_boomslang": 1},
        "effect": "下一趟禁林开始时获得20点护盾。",
        "steps": (
            ("树蛇皮在坩埚上方缓慢卷曲。", ("整片投入", "剪成七段依次投入", "烧成灰再投入"), 1),
            ("银灰色药液突然向坩埚中心收缩。", ("顺时针快速搅拌", "逆时针缓慢搅拌", "停止加热并静置"), 1),
            ("药液表面结出一层极薄的硬壳。", ("敲碎硬壳一同装瓶", "从硬壳下抽取药液", "重新煮沸硬壳"), 1),
        ),
    },
    "wolfsbane": {
        "name": "狼毒药剂", "grade": 5, "exp": 120,
        "ingredients": {"mat_knotgrass": 1, "mat_unicorn_hair": 1, "mat_bicorn_horn": 1},
        "effect": "下一次遭遇狼人时，本趟受到的伤害降低50%。",
        "steps": (
            ("双角兽角粉落下时，药液剧烈排斥独角兽毛。", ("同时投入两者", "先以结节草稳定药液", "增加角粉压制反应"), 1),
            ("药液呈现月光般的苍白色。", ("保持文火，不让颜色变深", "大火煮至银色", "加入冷水"), 0),
            ("最后一缕蒸汽形成了短暂的狼首轮廓。", ("立即密封装瓶", "继续搅拌直到轮廓消失", "打开窗户散去蒸汽"), 0),
        ),
    },
    "polyjuice": {
        "name": "复方汤剂", "grade": 6, "exp": 135,
        "ingredients": {"mat_lacewing": 2, "mat_boomslang": 1, "mat_bicorn_horn": 1},
        "effect": "暂时变成另一名学生的模样；只改变剧情状态，不改变账号身份与权限。",
        "steps": (
            ("熬了足够久的草蛉已经近乎透明。", ("直接倒掉浸液", "连同浸液缓慢加入", "重新用大火煮沸"), 1),
            ("树蛇皮与双角兽角粉让药液变得浓稠。", ("顺时针搅拌直到发黑", "逆时针搅拌至表面平滑", "停止搅拌等待结块"), 1),
            ("基础药液完成，只差目标身上的一小部分。", ("现在加入并立刻饮用", "装瓶，使用时再加入", "提前加入后存放一夜"), 1),
        ),
    },
    "felix": {
        "name": "福灵剂", "grade": 6, "exp": 150,
        "ingredients": {"mat_unicorn_hair": 1, "mat_acromantula_venom": 1, "mat_dementor_frost": 1},
        "effect": "下一次击败禁林生物时，额外获得当前深度可见的最稀有材料；每学年最多熬制一次。",
        "steps": (
            ("摄魂怪寒霜一靠近毒液，坩埚周围便结出白霜。", ("立刻混合", "以独角兽毛隔开两者缓慢融合", "先把寒霜融成水"), 1),
            ("金色液滴开始跃出液面，又自行落回坩埚。", ("追着液滴快速搅拌", "保持文火，完全不碰坩埚", "加入冷水压住液滴"), 1),
            ("药液像融化的黄金一样平静下来。", ("用锡制瓶塞密封", "用水晶瓶装好并避光密封", "敞口放到完全冷却"), 1),
        ),
    },
}
RECIPES_BY_NAME = {r["name"]: key for key, r in RECIPES.items()}

POTION_ITEMS = {f"potion_{key}": recipe["name"] for key, recipe in RECIPES.items()}
ACCIDENTS = ("头发不停变色", "说话时冒出紫色泡泡", "身上散发着烤卷心菜味", "耳朵里不断冒烟")
TITLE_NAMES = {
    "potion_apprentice": "坩埚学徒",
    "potion_collector": "配方收藏家",
    "potion_perfectionist": "坩埚守望者",
    "potion_master": "魔药优等生",
}
TITLE_REQUIREMENTS = {
    "potion_apprentice": "成功熬制第一瓶魔药",
    "potion_collector": "五张基础配方都至少成功一次",
    "potion_perfectionist": "累计完美熬制3次",
    "potion_master": "任意配方达到精通",
}


class PotionError(Exception):
    pass


def find_recipe(value: str):
    key = value if value in RECIPES else RECIPES_BY_NAME.get(value)
    return (key, RECIPES[key]) if key else None


def item_name(item_key: str) -> str | None:
    return POTION_ITEMS.get(item_key)


def _material_name(key: str) -> str:
    from plugins.hp_events import forest_catalog
    material = forest_catalog.MATERIALS_BY_KEY.get(key)
    return material[1] if material else key


def mastery_level(row) -> str:
    if not row or not row["attempts"]:
        return "未尝试"
    if row["successes"] >= 8 and row["perfects"] >= 3:
        return "精通"
    if row["successes"] >= 5:
        return "熟练"
    if row["successes"] >= 3:
        return "熟悉"
    return "生疏"


def list_recipes(uid: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise PotionError("你还没有分院，先完成入学手续。")
    exp = core_storage.get_subject_exp(uid, "potions")
    rows = []
    conn = get_conn()
    try:
        mastery = {r["recipe_key"]: dict(r) for r in conn.execute(
            "SELECT * FROM potion_mastery WHERE uid=?", (uid,)
        ).fetchall()}
        yearly = {
            r["recipe_key"]: r["count"] for r in conn.execute(
                "SELECT recipe_key,count FROM potion_yearly WHERE uid=? AND school_year=?",
                (uid, player["grade"]),
            ).fetchall()
        }
    finally:
        conn.close()
    for key, recipe in RECIPES.items():
        unlocked = player["grade"] >= recipe["grade"] and exp >= recipe["exp"]
        record = mastery.get(key)
        rows.append({"key": key, **recipe, "unlocked": unlocked, "mastery": record,
                     "mastery_level": mastery_level(record), "yearly_used": yearly.get(key, 0)})
    return {"rows": rows, "grade": player["grade"], "exp": exp}


def _render_session(row, resumed: bool = False) -> dict:
    recipe = RECIPES[row["recipe_key"]]
    prompt, options, _ = recipe["steps"][row["step"]]
    return {"recipe": recipe["name"], "step": row["step"] + 1, "total_steps": 3,
            "prompt": prompt, "options": options, "resumed": resumed}


def get_session(uid: str):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM potion_sessions WHERE uid=?", (uid,)).fetchone()
    finally:
        conn.close()


def start(uid: str, recipe_input: str) -> dict:
    existing = get_session(uid)
    if existing:
        return _render_session(existing, True)
    found = find_recipe(recipe_input.strip())
    if not found:
        raise PotionError("没有这张配方。发送「/魔药配方」查看已知配方。")
    key, recipe = found
    player = core_storage.sync_stamina(uid)
    if not player or not player["house"]:
        raise PotionError("你还没有完成入学手续。")
    exp = core_storage.get_subject_exp(uid, "potions")
    if player["grade"] < recipe["grade"] or exp < recipe["exp"]:
        raise PotionError(f"这张配方需要{recipe['grade']}年级、魔药学{recipe['exp']}经验。你目前是{player['grade']}年级、{exp}经验。")
    day = core_storage.get_current_day() or 1
    material_names = {item_key: _material_name(item_key) for item_key in recipe["ingredients"]}
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM potion_sessions WHERE uid=?", (uid,)).fetchone():
            conn.rollback()
            return _render_session(get_session(uid), True)
        conn.execute("INSERT OR IGNORE INTO potion_daily(uid,day,count) VALUES(?,?,0)", (uid, day))
        count = conn.execute("SELECT count FROM potion_daily WHERE uid=? AND day=?", (uid, day)).fetchone()[0]
        if count >= DAILY_LIMIT:
            conn.rollback()
            raise PotionError(f"你今天已经守过{DAILY_LIMIT}次坩埚了，再熬下去连气味都分不清。")
        stamina = conn.execute("SELECT stamina FROM players WHERE uid=?", (uid,)).fetchone()[0]
        if stamina < BREW_STAMINA_COST:
            conn.rollback()
            raise PotionError(f"你现在只有{stamina}/{core_storage.STAMINA_MAX}体力，熬制需要{BREW_STAMINA_COST}点。")
        missing = []
        for item_key, amount in recipe["ingredients"].items():
            have = conn.execute("SELECT quantity FROM inventory WHERE uid=? AND item_key=?", (uid, item_key)).fetchone()
            if not have or have[0] < amount:
                missing.append(f"{material_names[item_key]}×{amount - (have[0] if have else 0)}")
        if missing:
            conn.rollback()
            raise PotionError("材料还不够：" + "、".join(missing) + "。禁林撤退后才能把材料带回背包。")
        if key == "felix":
            yearly = conn.execute(
                "SELECT count FROM potion_yearly WHERE uid=? AND school_year=? AND recipe_key='felix'",
                (uid, player["grade"]),
            ).fetchone()
            if yearly and yearly["count"] >= 1:
                conn.rollback()
                raise PotionError("福灵剂极难熬制，你这个学年已经开过一次坩埚了。无论成败都要等下一学年。")
            conn.execute(
                "INSERT INTO potion_yearly(uid,school_year,recipe_key,count) VALUES(?,?,'felix',1) "
                "ON CONFLICT(uid,school_year,recipe_key) DO UPDATE SET count=count+1",
                (uid, player["grade"]),
            )
        for item_key, amount in recipe["ingredients"].items():
            conn.execute("UPDATE inventory SET quantity=quantity-? WHERE uid=? AND item_key=?", (amount, uid, item_key))
        ts = core_storage.now()
        conn.execute("UPDATE players SET stamina=stamina-?,updated_at=? WHERE uid=?", (BREW_STAMINA_COST, ts, uid))
        conn.execute("UPDATE potion_daily SET count=count+1 WHERE uid=? AND day=?", (uid, day))
        conn.execute("INSERT INTO potion_sessions VALUES(?,?,?,?,?,?,?,?)",
                     (uid, key, 0, 0, json.dumps(recipe["ingredients"]), "[]", ts, ts))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return _render_session(get_session(uid))


def choose(uid: str, position: int) -> dict:
    if position not in (1, 2, 3):
        raise PotionError("请选择1、2或3。")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM potion_sessions WHERE uid=?", (uid,)).fetchone()
        if not row:
            conn.rollback()
            raise PotionError("你面前没有正在熬制的坩埚。")
        recipe = RECIPES[row["recipe_key"]]
        _, _, correct = recipe["steps"][row["step"]]
        score = row["score"] + (1 if position - 1 == correct else 0)
        choices = json.loads(row["choices_json"])
        choices.append(position)
        next_step = row["step"] + 1
        if next_step < 3:
            conn.execute("UPDATE potion_sessions SET step=?,score=?,choices_json=?,updated_at=? WHERE uid=?",
                         (next_step, score, json.dumps(choices), core_storage.now(), uid))
            conn.commit()
            return {"finished": False, **_render_session(get_session(uid))}

        success = score >= 2
        perfect = score == 3
        quantity = (1 if success else 0) if row["recipe_key"] == "felix" else (2 if perfect else 1 if success else 0)
        if quantity:
            conn.execute(
                "INSERT INTO inventory(uid,item_key,quantity) VALUES(?,?,?) "
                "ON CONFLICT(uid,item_key) DO UPDATE SET quantity=quantity+excluded.quantity",
                (uid, f"potion_{row['recipe_key']}", quantity),
            )
        conn.execute(
            "INSERT INTO potion_mastery(uid,recipe_key,attempts,successes,perfects) VALUES(?,?,?,?,?) "
            "ON CONFLICT(uid,recipe_key) DO UPDATE SET attempts=attempts+1,successes=successes+excluded.successes,perfects=perfects+excluded.perfects",
            (uid, row["recipe_key"], 1, int(success), int(perfect)),
        )
        accident = ""
        if not success:
            accident = random.choice(ACCIDENTS)
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET label=excluded.label,expires_at=excluded.expires_at",
                (uid, "potion_accident", accident, core_storage.now() + 2 * 3600),
            )
        conn.execute(
            "INSERT INTO potion_history(uid,recipe_key,quality,quantity,accident,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (uid, row["recipe_key"], "perfect" if perfect else "success" if success else "failed",
             quantity, accident, core_storage.now()),
        )
        totals = conn.execute(
            "SELECT COALESCE(SUM(successes),0),COALESCE(SUM(perfects),0),"
            "SUM(CASE WHEN successes>0 THEN 1 ELSE 0 END),"
            "SUM(CASE WHEN successes>=8 AND perfects>=3 THEN 1 ELSE 0 END) "
            "FROM potion_mastery WHERE uid=?", (uid,),
        ).fetchone()
        successful_keys = {
            r["recipe_key"] for r in conn.execute(
                "SELECT recipe_key FROM potion_mastery WHERE uid=? AND successes>0", (uid,)
            ).fetchall()
        }
        earned = []
        checks = {
            "potion_apprentice": totals[0] >= 1,
            "potion_collector": all(key in successful_keys for key in CORE_RECIPE_KEYS),
            "potion_perfectionist": totals[1] >= 3,
            "potion_master": totals[3] >= 1,
        }
        for title_key, achieved in checks.items():
            if achieved:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO titles(uid,title_key,unlocked_at) VALUES(?,?,?)",
                    (uid, title_key, core_storage.now()),
                )
                if cur.rowcount:
                    earned.append(TITLE_NAMES[title_key])
        conn.execute("DELETE FROM potion_sessions WHERE uid=?", (uid,))
        conn.commit()
        return {"finished": True, "recipe": recipe["name"], "score": score,
                "quality": "完美" if perfect else "合格" if success else "失败",
                "quantity": quantity, "accident": accident, "earned_titles": earned}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def abandon(uid: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM potion_sessions WHERE uid=?", (uid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _consume_inventory(conn, uid: str, item_key: str) -> None:
    cur = conn.execute("UPDATE inventory SET quantity=quantity-1 WHERE uid=? AND item_key=? AND quantity>0", (uid, item_key))
    if cur.rowcount == 0:
        raise PotionError(f"背包里没有「{POTION_ITEMS[item_key]}」。")


def use(uid: str, potion_input: str, target_uid: str | None = None) -> dict:
    found = find_recipe(potion_input.strip())
    if not found:
        raise PotionError("没有这种药剂。")
    key, recipe = found
    item_key = f"potion_{key}"
    if key == "healing":
        from plugins.hp_events import forest
        try:
            return forest.use_healing_potion(uid, item_key, recipe["name"])
        except forest.ForestError as exc:
            raise PotionError(str(exc)) from exc
    target = None
    if key == "polyjuice":
        if not target_uid:
            raise PotionError("复方汤剂需要一名变身对象。用法：/使用魔药 复方汤剂 对方名字")
        if target_uid == uid:
            raise PotionError("你本来就是自己，不需要复方汤剂。")
        target = core_storage.get_player(target_uid)
        if not target or not target["house"]:
            raise PotionError("对方还没有完成入学手续，无法取得有效的变身样本。")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _consume_inventory(conn, uid, item_key)
        result = {"name": recipe["name"], "effect": recipe["effect"]}
        if key == "energizing":
            row = conn.execute("SELECT stamina FROM players WHERE uid=?", (uid,)).fetchone()
            if not row:
                raise PotionError("没有找到你的入学记录。")
            restored = min(7, core_storage.STAMINA_MAX - row["stamina"])
            if restored <= 0:
                raise PotionError("你的体力已经是满的，不需要喝提神剂。")
            conn.execute("UPDATE players SET stamina=stamina+?,updated_at=? WHERE uid=?", (restored, core_storage.now(), uid))
            result.update(restored=restored, stamina=row["stamina"] + restored)
        elif key == "polyjuice":
            full_name = f"{target['name']}·{target['surname']}" if target["surname"] else target["name"]
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET label=excluded.label,expires_at=excluded.expires_at",
                (uid, "polyjuice", f"暂时顶着{full_name}的模样", core_storage.now() + 2 * 3600),
            )
            result.update(target_name=full_name, hours=2)
        else:
            effect_key = {
                "focus": "focus_lesson", "protection": "forest_protection",
                "wolfsbane": "wolfsbane", "felix": "felix_felicis",
            }[key]
            conn.execute(
                "INSERT INTO potion_effects(uid,effect_key,charges) VALUES(?,?,1) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET charges=1", (uid, effect_key),
            )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def gift(uid: str, target_uid: str, potion_input: str, quantity: int = 1) -> dict:
    if uid == target_uid:
        raise PotionError("不能把药剂送给自己。")
    if quantity < 1 or quantity > 5:
        raise PotionError("单次赠送数量必须在1到5瓶之间。")
    sender = core_storage.get_player(uid)
    target = core_storage.get_player(target_uid)
    if not sender or not sender["house"]:
        raise PotionError("你还没有完成入学手续。")
    if not target or not target["house"]:
        raise PotionError("对方还没有完成入学手续。")
    found = find_recipe(potion_input.strip())
    if not found:
        raise PotionError("没有这种药剂。")
    key, recipe = found
    item_key = f"potion_{key}"
    day = core_storage.get_current_day() or 1
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO potion_trade_daily(uid,day,count) VALUES(?,?,0)", (uid, day))
        daily = conn.execute("SELECT count FROM potion_trade_daily WHERE uid=? AND day=?", (uid, day)).fetchone()[0]
        if daily >= TRADE_DAILY_LIMIT:
            conn.rollback()
            raise PotionError(f"你今天已经送过{TRADE_DAILY_LIMIT}次药剂了，猫头鹰也需要休息。")
        removed = conn.execute(
            "UPDATE inventory SET quantity=quantity-? WHERE uid=? AND item_key=? AND quantity>=?",
            (quantity, uid, item_key, quantity),
        )
        if removed.rowcount == 0:
            conn.rollback()
            have = storage.get_item_quantity(uid, item_key)
            raise PotionError(f"你只有{have}瓶「{recipe['name']}」，送不了{quantity}瓶。")
        conn.execute(
            "INSERT INTO inventory(uid,item_key,quantity) VALUES(?,?,?) "
            "ON CONFLICT(uid,item_key) DO UPDATE SET quantity=quantity+excluded.quantity",
            (target_uid, item_key, quantity),
        )
        conn.execute("UPDATE potion_trade_daily SET count=count+1 WHERE uid=? AND day=?", (uid, day))
        conn.execute(
            "INSERT INTO potion_trades(sender_uid,receiver_uid,potion_key,quantity,created_at) VALUES(?,?,?,?,?)",
            (uid, target_uid, key, quantity, core_storage.now()),
        )
        conn.commit()
        target_name = f"{target['name']}·{target['surname']}" if target["surname"] else target["name"]
        return {"name": recipe["name"], "quantity": quantity, "target_name": target_name,
                "today_count": daily + 1, "daily_limit": TRADE_DAILY_LIMIT}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consume_effect(uid: str, effect_key: str) -> bool:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("UPDATE potion_effects SET charges=charges-1 WHERE uid=? AND effect_key=? AND charges>0", (uid, effect_key))
        if cur.rowcount:
            conn.execute("DELETE FROM potion_effects WHERE uid=? AND effect_key=? AND charges<=0", (uid, effect_key))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consume_focus_bonus(uid: str, subject_key: str) -> int:
    """原子消耗课堂药效并发放1点经验，避免重复按钮重复加成。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("UPDATE potion_effects SET charges=charges-1 WHERE uid=? AND effect_key='focus_lesson' AND charges>0", (uid,))
        if not cur.rowcount:
            conn.rollback()
            return 0
        conn.execute("DELETE FROM potion_effects WHERE uid=? AND effect_key='focus_lesson' AND charges<=0", (uid,))
        conn.execute(
            "INSERT INTO subject_exp(uid,subject,exp) VALUES(?,?,1) "
            "ON CONFLICT(uid,subject) DO UPDATE SET exp=exp+1", (uid, subject_key),
        )
        conn.commit()
        return 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def title_state(uid: str) -> list[dict]:
    conn = get_conn()
    try:
        unlocked = {
            row["title_key"] for row in conn.execute(
                "SELECT title_key FROM titles WHERE uid=?", (uid,)
            ).fetchall()
        }
        player = conn.execute("SELECT active_title FROM players WHERE uid=?", (uid,)).fetchone()
        active = player["active_title"] if player else ""
        return [
            {"key": key, "name": name, "requirement": TITLE_REQUIREMENTS[key],
             "unlocked": key in unlocked, "active": active == name}
            for key, name in TITLE_NAMES.items()
        ]
    finally:
        conn.close()


def wear_title(uid: str, title_input: str) -> str:
    key = next((key for key, name in TITLE_NAMES.items() if title_input in (key, name)), None)
    if not key:
        raise PotionError("没有这个魔药称号。发送「/魔药称号」查看。")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM titles WHERE uid=? AND title_key=?", (uid, key)).fetchone():
            conn.rollback()
            raise PotionError(f"你还没有解锁「{TITLE_NAMES[key]}」。")
        conn.execute("UPDATE players SET active_title=?,updated_at=? WHERE uid=?",
                     (TITLE_NAMES[key], core_storage.now(), uid))
        conn.commit()
        return TITLE_NAMES[key]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
