"""Pure numeric formulas from 斗罗五阵录 v0.5 (section 07/05).

Every function here is a pure function: same inputs -> same output,
no randomness, no I/O. Randomness (dice rolls) lives in resolver.py,
which is handed a seeded random.Random so results stay reproducible.
"""
import math

# ---- damage / shield (07) ----------------------------------------------

def base_damage(power: int, atk: int) -> int:
    """基础伤害 = 技能威力 x ATK / 100"""
    return power * atk // 100


def defense_multiplier(defense: int) -> float:
    """防御倍率 = 100 / (100 + DEF)"""
    return 100.0 / (100.0 + defense)


def final_damage(power: int, atk: int, defense: int) -> int:
    """最终伤害 = floor(基础伤害 x 防御倍率)。无随机浮动，整数结算。"""
    return math.floor(base_damage(power, atk) * defense_multiplier(defense))


def shield_value(power: int, defense: int) -> int:
    """护盾值 = 技能威力 x DEF / 100"""
    return power * defense // 100


def decay_shield(shield: int) -> int:
    """护盾在下一回合开始时衰减 50%。"""
    return shield // 2


# ---- action speed (07) ---------------------------------------------------

def action_speed(spd: int, skill_speed_mod: int, status_mod: int = 0) -> int:
    """行动速度 = SPD + 技能速度修正 + 状态修正。

    技能速度修正只影响本次行动排序，不修改角色下回合的基础 SPD；
    真正持续多回合的加速/减速效果走 status_mod。
    """
    return spd + skill_speed_mod + status_mod


# ---- control (07) ---------------------------------------------------------

# 控制疲劳: 第0层100% / 第1层65% / 第2层35% / 第3层免疫一回合
CONTROL_FATIGUE_MULTIPLIER = {0: 1.0, 1: 0.65, 2: 0.35}
CONTROL_FATIGUE_IMMUNE_TIER = 3


def control_chance(base_chance: float, res: int, fatigue_tier: int) -> float:
    """控制成功率 = 基础命中率 x 100/(100+RES) x 控制疲劳修正。

    fatigue_tier >= CONTROL_FATIGUE_IMMUNE_TIER means immune (returns 0.0).
    """
    if fatigue_tier >= CONTROL_FATIGUE_IMMUNE_TIER:
        return 0.0
    res_multiplier = 100.0 / (100.0 + res)
    fatigue_multiplier = CONTROL_FATIGUE_MULTIPLIER.get(fatigue_tier, 0.0)
    return base_chance * res_multiplier * fatigue_multiplier


# ---- ring overload / backlash (05) ----------------------------------------

def can_bear_tier(power_level: int) -> int:
    """可承受阶级 = 1 + floor(魂力等级 / 20)"""
    return 1 + power_level // 20


def overload_value(ring_tier: int, power_level: int) -> int:
    """超载值 = max(0, 魂环阶级 - 可承受阶级)"""
    return max(0, ring_tier - can_bear_tier(power_level))


def backlash_chance(overload: int) -> float:
    """反噬概率 = min(60%, 超载值 x 18%)"""
    return min(0.60, overload * 0.18)


# ---- soul (魂力) resource (engineering proposal, adopted in v0.3) --------

SOUL_NATURAL_REGEN = 15
SOUL_BASIC_ATTACK_BONUS_REGEN = 10
