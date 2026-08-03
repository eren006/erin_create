"""禁林冒险：PvE版的决斗。

复用决斗那一套规则（回合制、HP、冷却、四系克制、护盾、封锁），区别是对手换成怪物，
而且怪物**自己出招**——每种怪有自己的出招偏好，打多了能摸出规律，用克制关系针对它。

核心抉择：打赢一层之后可以「继续深入」（更好的战利品）或者「撤退」（落袋为安）。
中途被打败，这一趟没结算的战利品全部清空——见好就收还是再赌一把，是这个玩法的骨架。

荧光闪烁：学会之后降低每层的遇险概率（进场时被偷袭掉血）。
"""

import json
import random

from plugins.hp_core import moon
from plugins.hp_core import spells as spell_catalog
from plugins.hp_core import storage as core_storage

from . import forest_catalog, storage

storage.init_db()

PLAYER_HP = 100
STAMINA_COST = 12
DAILY_LIMIT = 2
MIN_GRADE = 2
MONSTER_BASE_DAMAGE = {"attack": 16, "blast": 20, "control": 12, "defence": 4}
MONSTER_SHIELD = 14
AMBUSH_CHANCE = 0.30
AMBUSH_CHANCE_WITH_LUMOS = 0.12  # 学会荧光闪烁之后，看得清路，遇险概率大幅下降
AMBUSH_DAMAGE = (8, 16)
LUMOS_KEY = "lumos"


class ForestError(Exception):
    pass


def _usable_spells(uid: str) -> list[tuple]:
    return spell_catalog.combat_spells_of(core_storage.list_learned_spells(uid))


def _require_explorer(uid: str):
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise ForestError("你还没有分院，先发「/入学 你的名字」完成入学测试。")
    if player["grade"] < MIN_GRADE:
        raise ForestError(f"禁林要{MIN_GRADE}年级才敢进，你现在是{player['grade']}年级。")
    if not _usable_spells(uid):
        raise ForestError("你还没学会任何能用来打架的咒语，空着手进禁林是送死。先去上课。")
    return player


def _monster_max_depth_for_grade(grade: int) -> int:
    """年级不够就下不去更深的层——到了门槛层会被劝退。"""
    deepest = 0
    for key, name, min_d, max_d, hp, weights, req_grade, teaches, desc in forest_catalog.MONSTERS:
        if grade >= req_grade:
            deepest = max(deepest, max_d)
    return deepest


def _spawn_monster(run_id: int, depth: int) -> dict:
    day = core_storage.get_current_day() or 1
    monster = forest_catalog.monster_for_depth(depth, moon.is_full_moon(day))
    key, name, min_d, max_d, hp, weights, req_grade, teaches, desc = monster
    # 同一档怪在更深的层会更硬
    scaled_hp = hp + (depth - min_d) * 15
    storage.clear_forest_cooldowns(run_id)
    storage.update_run(
        run_id,
        depth=depth,
        monster_key=key,
        monster_hp=scaled_hp,
        monster_max_hp=scaled_hp,
        monster_shield=0,
        monster_last_category="",
        my_last_spell="",
        locked_me="",
        my_shield=0,
        round=1,
        phase="combat",
    )
    return {"name": name, "hp": scaled_hp, "desc": desc}


def _ambush(uid: str, run) -> int:
    """进层时的遇险判定。学会荧光闪烁能大幅降低概率。"""
    chance = AMBUSH_CHANCE_WITH_LUMOS if core_storage.has_spell(uid, LUMOS_KEY) else AMBUSH_CHANCE
    if random.random() >= chance:
        return 0
    damage = random.randint(*AMBUSH_DAMAGE)
    new_hp = max(1, run["my_hp"] - damage)  # 偷袭不会直接打死，最少留1点
    storage.update_run(run["id"], my_hp=new_hp)
    return run["my_hp"] - new_hp


# ======================== 进入 / 状态 ========================


def enter(uid: str) -> dict:
    player = _require_explorer(uid)
    if storage.get_active_run(uid):
        raise ForestError("你已经在禁林里了，用「/禁林状态」看看现在什么情况。")
    if storage.get_active_session(uid):
        raise ForestError("你正在决斗中，打完再进禁林。")

    day = core_storage.get_current_day() or 1
    runs_today = storage.get_forest_daily(uid, day)
    if runs_today >= DAILY_LIMIT:
        raise ForestError(f"你今天已经进过{DAILY_LIMIT}次禁林了，再去就要被费尔奇抓住了。明天再来。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise ForestError(
            f"禁林不是这个状态能进的地方。当前体力{player['stamina']}/{core_storage.STAMINA_MAX}，"
            f"进禁林要{STAMINA_COST}点。约{wait_min}分钟后恢复一轮。"
        )

    core_storage.spend_stamina(uid, STAMINA_COST)
    storage.increment_forest_daily(uid, day)
    run_id = storage.create_run(uid, my_hp=PLAYER_HP, depth=1)
    monster = _spawn_monster(run_id, 1)
    from plugins.hp_school import potions
    protection_potion = potions.consume_effect(uid, "forest_protection")
    if protection_potion:
        storage.update_run(run_id, my_shield=20, protection_potion=1)
    run = storage.get_run(run_id)
    ambush_damage = _ambush(uid, run)

    return {
        "depth": 1,
        "monster": monster["name"],
        "monster_desc": monster["desc"],
        "monster_hp": monster["hp"],
        "my_hp": storage.get_run(run_id)["my_hp"],
        "ambush_damage": ambush_damage,
        "has_lumos": core_storage.has_spell(uid, LUMOS_KEY),
        "runs_today": runs_today + 1,
        "daily_limit": DAILY_LIMIT,
        "protection_potion": protection_potion,
    }


def get_state(uid: str) -> dict:
    run = storage.get_active_run(uid)
    if not run:
        raise ForestError("你现在不在禁林里。用「/进入禁林」开始一趟。")
    monster = forest_catalog.MONSTERS_BY_KEY[run["monster_key"]]
    cooldowns = storage.get_forest_cooldowns(run["id"])
    locked = run["locked_me"]

    available, unavailable = [], []
    for spell in _usable_spells(uid):
        key, name, latin, subject, min_grade, category, desc = spell
        stats = spell_catalog.COMBAT[key]
        reason = None
        if stats.get("once") and run["ace_used"]:
            reason = "本场已用过"
        elif cooldowns.get(key, 0) > run["round"]:
            reason = f"冷却至第{cooldowns[key]}回合"
        elif locked and (locked == "any" or locked == category):
            reason = "被封锁"
        entry = {"name": name, "category": category, "damage": stats.get("damage", 0), "reason": reason}
        (unavailable if reason else available).append(entry)

    materials = json.loads(run["pending_materials"])
    return {
        "phase": run["phase"],
        "depth": run["depth"],
        "max_depth": forest_catalog.MAX_DEPTH,
        "monster": monster[1],
        "monster_hp": run["monster_hp"],
        "monster_max_hp": run["monster_max_hp"],
        "monster_shield": run["monster_shield"],
        "monster_last_category": run["monster_last_category"],
        "my_hp": run["my_hp"],
        "my_shield": run["my_shield"],
        "round": run["round"],
        "locked": locked,
        "available": available,
        "unavailable": unavailable,
        "pending_galleons": run["pending_galleons"],
        "pending_exp": run["pending_exp"],
        "pending_materials": [forest_catalog.MATERIALS_BY_KEY[m][1] for m in materials],
    }


# ======================== 战斗 ========================


def _monster_pick(monster) -> str:
    weights = monster[5]
    return random.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _monster_turn(uid: str, run, monster) -> dict:
    """怪物自己出招：按偏好权重随机选一系，克制关系照样生效。"""
    category = _monster_pick(monster)
    my_last = run["my_last_spell"]
    my_last_category = ""
    if my_last:
        spell = spell_catalog.SPELLS_BY_KEY.get(my_last)
        my_last_category = spell[5] if spell else ""
    countered = my_last_category and spell_catalog.COUNTERS.get(category) == my_last_category
    multiplier = spell_catalog.COUNTER_DAMAGE_BONUS if countered else 1.0

    updates = {"monster_last_category": category}
    damage = 0
    blocked = 0
    shield_gain = 0
    lock = ""

    if category == "defence":
        shield_gain = int(MONSTER_SHIELD * multiplier)
        updates["monster_shield"] = run["monster_shield"] + shield_gain
    else:
        damage = int(MONSTER_BASE_DAMAGE[category] * multiplier)
        depth_bonus = (run["depth"] - 1) * 2  # 越深打得越疼
        damage += depth_bonus
        if run["monster_key"] == "werewolf" and run["wolfsbane_potion"]:
            damage = (damage + 1) // 2
        my_shield = run["my_shield"]
        if my_shield:
            blocked = min(my_shield, damage)
            damage -= blocked
            updates["my_shield"] = my_shield - blocked
        # 封锁不连续生效：上一回合刚被锁过就不再锁，避免玩家被连环控住起不来
        if category == "control" and not run["locked_me"]:
            lock = random.choice(["attack", "blast", "control"])
            updates["locked_me"] = lock

    new_my_hp = max(0, run["my_hp"] - damage)
    updates["my_hp"] = new_my_hp
    storage.update_run(run["id"], **updates)

    return {
        "category": category,
        "damage": damage,
        "blocked": blocked,
        "shield_gain": shield_gain,
        "countered": countered,
        "lock": lock,
        "my_hp": new_my_hp,
    }


def _grant_layer_loot(uid: str, run) -> dict:
    """打赢一层的战利品——先记在"待结算"里，撤退才真正到手。"""
    depth = run["depth"]
    galleons = forest_catalog.GALLEON_PER_DEPTH * depth + random.randint(0, 8)
    exp = forest_catalog.EXP_PER_DEPTH * depth
    pool = forest_catalog.materials_for_depth(depth)
    materials = json.loads(run["pending_materials"])
    dropped = []
    if pool and random.random() < 0.75:
        mat = random.choice(pool)
        materials.append(mat[0])
        dropped.append(mat[1])
    lucky_material = ""
    conn = core_storage.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if pool:
            lucky_cur = conn.execute(
                "UPDATE potion_effects SET charges=charges-1 "
                "WHERE uid=? AND effect_key='felix_felicis' AND charges>0", (uid,),
            )
            if lucky_cur.rowcount:
                conn.execute(
                    "DELETE FROM potion_effects WHERE uid=? AND effect_key='felix_felicis' AND charges<=0",
                    (uid,),
                )
                lucky = pool[-1]  # 目录按最低深度递增，取当前深度能见到的最稀有材料。
                materials.append(lucky[0])
                dropped.append(lucky[1])
                lucky_material = lucky[1]
        conn.execute(
            "UPDATE forest_runs SET pending_galleons=?,pending_exp=?,pending_materials=?,"
            "phase='cleared',updated_at=? WHERE id=?",
            (run["pending_galleons"] + galleons, run["pending_exp"] + exp,
             json.dumps(materials), core_storage.now(), run["id"]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"galleons": galleons, "exp": exp, "materials": dropped,
            "lucky_material": lucky_material}


def cast(uid: str, spell_input: str) -> dict:
    run = storage.get_active_run(uid)
    if not run:
        raise ForestError("你现在不在禁林里。")
    if run["phase"] != "combat":
        raise ForestError("这一层已经清完了，用「/继续深入」或者「/撤退」。")

    spell = spell_catalog.find(spell_input.strip())
    if not spell:
        raise ForestError("没有这个咒语。")
    key, name, latin, subject, min_grade, category, desc = spell
    if not core_storage.has_spell(uid, key):
        raise ForestError(f"你还没学会「{name}」。")
    if category not in spell_catalog.COMBAT_CATEGORIES:
        raise ForestError(f"「{name}」不是战斗咒语，这时候派不上用场。")

    stats = spell_catalog.COMBAT[key]
    if stats.get("once") and run["ace_used"]:
        raise ForestError(f"「{name}」这一趟只能用一次，你已经用过了。")
    cooldowns = storage.get_forest_cooldowns(run["id"])
    if cooldowns.get(key, 0) > run["round"]:
        raise ForestError(f"「{name}」还在冷却，第{cooldowns[key]}回合才能再用。")
    locked = run["locked_me"]
    if locked and (locked == "any" or locked == category):
        raise ForestError(f"你被缠住了，这一回合用不了{'任何咒语' if locked == 'any' else name}。")

    monster = forest_catalog.MONSTERS_BY_KEY[run["monster_key"]]

    # ── 我方结算 ──
    countered = (
        category != "ace"
        and run["monster_last_category"]
        and spell_catalog.COUNTERS.get(category) == run["monster_last_category"]
    )
    multiplier = spell_catalog.COUNTER_DAMAGE_BONUS if countered else 1.0
    damage = int(stats.get("damage", 0) * multiplier)
    shield_gain = int(stats.get("shield", 0) * multiplier)

    # 摄魂怪只怕守护神：别的咒语对它几乎没用
    resisted = False
    if run["monster_key"] == forest_catalog.DEMENTOR_KEY and key not in forest_catalog.PATRONUS_KEYS:
        damage = int(damage * forest_catalog.DEMENTOR_RESIST)
        resisted = True

    updates = {"my_last_spell": key, "locked_me": ""}
    blocked = 0
    if damage:
        monster_shield = run["monster_shield"]
        if monster_shield and not stats.get("pierce"):
            blocked = min(monster_shield, damage)
            damage -= blocked
            updates["monster_shield"] = monster_shield - blocked
        elif monster_shield and stats.get("pierce"):
            updates["monster_shield"] = 0
    new_monster_hp = max(0, run["monster_hp"] - damage)
    updates["monster_hp"] = new_monster_hp
    if shield_gain:
        updates["my_shield"] = run["my_shield"] + shield_gain
    if stats.get("once"):
        updates["ace_used"] = 1

    storage.set_forest_cooldown(run["id"], key, run["round"] + stats.get("cooldown", 1))
    storage.update_run(run["id"], **updates)
    run = storage.get_run(run["id"])

    my_action = {
        "spell": name,
        "latin": latin,
        "damage": damage,
        "blocked": blocked,
        "shield_gain": shield_gain,
        "countered": countered,
        "resisted": resisted,
        "monster": monster[1],
        "monster_hp": new_monster_hp,
    }

    # ── 怪物倒下？ ──
    if new_monster_hp <= 0:
        learned = None
        if not storage.has_defeated(uid, monster[0]):
            storage.mark_defeated(uid, monster[0])
            teaches = monster[7]
            if teaches and not core_storage.has_spell(uid, teaches):
                core_storage.learn_spell(uid, teaches)
                tspell = spell_catalog.SPELLS_BY_KEY[teaches]
                learned = {"name": tspell[1], "latin": tspell[2], "desc": tspell[6]}
        loot = _grant_layer_loot(uid, run)
        player = core_storage.get_player(uid)
        can_go_deeper = (
            run["depth"] < forest_catalog.MAX_DEPTH
            and _monster_max_depth_for_grade(player["grade"]) > run["depth"]
        )
        return {
            **my_action,
            "monster_down": True,
            "learned_spell": learned,
            "loot": loot,
            "depth": run["depth"],
            "can_go_deeper": can_go_deeper,
            "next_blocked_by_grade": run["depth"] < forest_catalog.MAX_DEPTH and not can_go_deeper,
        }

    # ── 怪物反击 ──
    monster_action = _monster_turn(uid, run, monster)
    run = storage.get_run(run["id"])

    if monster_action["my_hp"] <= 0:
        lost = {
            "galleons": run["pending_galleons"],
            "exp": run["pending_exp"],
            "materials": [forest_catalog.MATERIALS_BY_KEY[m][1] for m in json.loads(run["pending_materials"])],
        }
        storage.update_run(run["id"], status="finished", phase="defeated")
        return {**my_action, "monster_action": monster_action, "defeated": True, "lost": lost, "depth": run["depth"]}

    storage.update_run(run["id"], round=run["round"] + 1)
    return {
        **my_action,
        "monster_action": monster_action,
        "round": run["round"] + 1,
        "my_hp": monster_action["my_hp"],
    }


def skip(uid: str) -> dict:
    """什么都不做，直接挨怪物一下。咒语全在冷却时的保底选项。"""
    run = storage.get_active_run(uid)
    if not run:
        raise ForestError("你现在不在禁林里。")
    if run["phase"] != "combat":
        raise ForestError("这一层已经清完了，用「/继续深入」或者「/撤退」。")

    monster = forest_catalog.MONSTERS_BY_KEY[run["monster_key"]]
    storage.update_run(run["id"], my_last_spell="", locked_me="")
    run = storage.get_run(run["id"])
    monster_action = _monster_turn(uid, run, monster)
    run = storage.get_run(run["id"])

    if monster_action["my_hp"] <= 0:
        lost = {
            "galleons": run["pending_galleons"],
            "exp": run["pending_exp"],
            "materials": [forest_catalog.MATERIALS_BY_KEY[m][1] for m in json.loads(run["pending_materials"])],
        }
        storage.update_run(run["id"], status="finished", phase="defeated")
        return {"skipped": True, "monster_action": monster_action, "defeated": True, "lost": lost, "depth": run["depth"]}

    storage.update_run(run["id"], round=run["round"] + 1)
    return {"skipped": True, "monster_action": monster_action, "round": run["round"] + 1}


# ======================== 深入 / 撤退 ========================


def go_deeper(uid: str) -> dict:
    run = storage.get_active_run(uid)
    if not run:
        raise ForestError("你现在不在禁林里。")
    if run["phase"] != "cleared":
        raise ForestError("先把眼前这只解决掉再说。")
    if run["depth"] >= forest_catalog.MAX_DEPTH:
        raise ForestError("这已经是禁林最深处了，没有更深的地方可去。撤退吧。")

    player = core_storage.get_player(uid)
    next_depth = run["depth"] + 1
    day = core_storage.get_current_day() or 1
    next_monster = forest_catalog.monster_for_depth(next_depth, moon.is_full_moon(day))
    if player["grade"] < next_monster[6]:
        raise ForestError(
            f"再往里走就是{next_monster[1]}的地盘了，{next_monster[6]}年级以下进去就是送死。"
            "见好就收，用「/撤退」把东西带回去。"
        )

    monster = _spawn_monster(run["id"], next_depth)
    wolfsbane_potion = False
    if next_monster[0] == "werewolf" and not run["wolfsbane_potion"]:
        from plugins.hp_school import potions
        wolfsbane_potion = potions.consume_effect(uid, "wolfsbane")
        if wolfsbane_potion:
            storage.update_run(run["id"], wolfsbane_potion=1)
    run = storage.get_run(run["id"])
    ambush_damage = _ambush(uid, run)
    run = storage.get_run(run["id"])

    return {
        "depth": next_depth,
        "monster": monster["name"],
        "monster_desc": monster["desc"],
        "monster_hp": monster["hp"],
        "my_hp": run["my_hp"],
        "ambush_damage": ambush_damage,
        "wolfsbane_potion": wolfsbane_potion,
    }


def use_healing_potion(uid: str, item_key: str, potion_name: str) -> dict:
    """在禁林战斗中原子扣除药剂并恢复HP，每趟只能使用一次。"""
    conn = core_storage.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute(
            "SELECT * FROM forest_runs WHERE uid=? AND status='active'", (uid,)
        ).fetchone()
        if not run or run["phase"] != "combat":
            conn.rollback()
            raise ForestError("愈合药剂只能在禁林战斗途中使用。")
        if run["healing_potion"]:
            conn.rollback()
            raise ForestError("这一趟已经喝过一瓶愈合药剂了。")
        if run["my_hp"] >= PLAYER_HP:
            conn.rollback()
            raise ForestError("你现在没有受伤，先别浪费愈合药剂。")
        removed = conn.execute(
            "UPDATE inventory SET quantity=quantity-1 WHERE uid=? AND item_key=? AND quantity>0",
            (uid, item_key),
        )
        if removed.rowcount == 0:
            conn.rollback()
            raise ForestError(f"背包里没有「{potion_name}」。")
        healed = min(25, PLAYER_HP - run["my_hp"])
        conn.execute(
            "UPDATE forest_runs SET my_hp=my_hp+?,healing_potion=1,updated_at=? WHERE id=?",
            (healed, core_storage.now(), run["id"]),
        )
        conn.commit()
        return {"name": potion_name, "effect": f"恢复{healed}HP", "healed": healed,
                "hp": run["my_hp"] + healed}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def retreat(uid: str) -> dict:
    run = storage.get_active_run(uid)
    if not run:
        raise ForestError("你现在不在禁林里。")

    galleons = run["pending_galleons"]
    exp = run["pending_exp"]
    materials = json.loads(run["pending_materials"])

    core_storage.add_galleons(uid, galleons)
    # 学科经验对半分给保护神奇动物学和黑魔法防御术
    half = exp // 2
    core_storage.add_subject_exp(uid, "care_of_magical_creatures", half)
    core_storage.add_subject_exp(uid, "defence", exp - half)

    from plugins.hp_school import storage as school_storage

    material_names = []
    for mat_key in materials:
        school_storage.add_item(uid, mat_key, 1)
        material_names.append(forest_catalog.MATERIALS_BY_KEY[mat_key][1])

    storage.update_run(run["id"], status="finished", phase="retreated")
    return {
        "depth": run["depth"],
        "cleared_depth": run["depth"] if run["phase"] == "cleared" else run["depth"] - 1,
        "galleons": galleons,
        "exp": exp,
        "materials": material_names,
        "my_hp": run["my_hp"],
    }


def moon_state() -> dict:
    day = core_storage.get_current_day() or 1
    return {
        "day": day,
        "phase": moon.phase_name(day),
        "is_full_moon": moon.is_full_moon(day),
        "days_to_full": moon.days_to_full_moon(day),
    }


def bestiary(uid: str) -> list[dict]:
    defeated = storage.list_defeated(uid)
    player = core_storage.get_player(uid)
    grade = player["grade"] if player else 1
    day = core_storage.get_current_day() or 1
    tonight_full = moon.is_full_moon(day)
    result = []
    for key, name, min_d, max_d, hp, weights, req_grade, teaches, desc in forest_catalog.MONSTERS:
        pref = "、".join(
            f"{cat}{int(w * 100)}%"
            for cat, w in sorted(weights.items(), key=lambda x: -x[1])
            if w >= 0.2
        )
        if key == forest_catalog.WEREWOLF_KEY:
            timing = "只在满月夜出现"
            tonight = tonight_full
        elif key == forest_catalog.WEREWOLF_STANDIN_KEY:
            timing = "满月夜之外出现"
            tonight = not tonight_full
        else:
            timing = ""
            tonight = True
        result.append(
            {
                "name": name,
                "depth": f"{min_d}-{max_d}层" if min_d != max_d else f"{min_d}层",
                "defeated": key in defeated,
                "locked": grade < req_grade,
                "req_grade": req_grade,
                "preference": pref if key in defeated else "？（打赢一次才会记下来）",
                "teaches": spell_catalog.SPELLS_BY_KEY[teaches][1] if teaches else "",
                "timing": timing,
                "tonight": tonight,
            }
        )
    return result
