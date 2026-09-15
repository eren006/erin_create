"""A small starter skill library, enough to exercise every Phase-1
mechanic (basic attack, damage, control/interrupt, shield, debuff).

This is NOT the full 20-30 skill content set from the design doc (that's
later content work) -- just enough fixtures to build and test the engine.
"""
from .models import Skill

BASIC_ATTACK = Skill(
    id="basic_attack",
    name="普通攻击",
    type="attack",  # only used if the caster has no other type context
    kind="basic",
    # Phase 2 sim: at power=40, basic attack did ~2.6% of a stage-30
    # HP pool per hit -- far too weak as filler between cooldowns, so
    # even best-case attack-vs-attack mirror matches timed out ~90% of
    # the time at 15 rounds. Raised to match the weakest attack template
    # (matches formulas.py's own precedent of treating basic attack as
    # a real, if modest, damage source rather than a near-no-op).
    power=100,
    soul_cost=0,
    speed_mod=0,
    cooldown=0,
    is_basic_attack=True,
)

SKILLS = {
    "basic_attack": BASIC_ATTACK,
    "blue_silver_bind": Skill(
        id="blue_silver_bind",
        name="蓝银缠绕",
        type="control",
        kind="control",
        power=0,
        soul_cost=25,
        speed_mod=20,
        cooldown=2,
        control_effect="interrupt",
        base_control_chance=0.70,
    ),
    "restraining_grasp": Skill(
        id="restraining_grasp",
        name="束缚之握",
        type="control",
        kind="control",
        power=0,
        soul_cost=30,
        speed_mod=15,
        cooldown=3,
        control_effect="stun",
        base_control_chance=0.55,
        control_duration=1,
    ),
    "haotian_hammer_smash": Skill(
        id="haotian_hammer_smash",
        name="昊天锤裂地",
        type="attack",
        kind="damage",
        power=160,
        soul_cost=45,
        speed_mod=-20,
        cooldown=1,
    ),
    "iron_wall_guard": Skill(
        id="iron_wall_guard",
        name="铁壁守护",
        type="defense",
        kind="shield",
        power=140,
        soul_cost=30,
        speed_mod=30,
        cooldown=2,
    ),
    "withering_curse": Skill(
        id="withering_curse",
        name="枯萎诅咒",
        type="support",
        kind="debuff",
        power=70,
        soul_cost=25,
        speed_mod=0,
        cooldown=2,
    ),
    "shadow_needle": Skill(
        id="shadow_needle",
        name="暗影毒针",
        type="special",
        kind="damage",
        power=90,
        soul_cost=35,
        speed_mod=0,
        cooldown=2,
    ),
}


def _all_skills():
    # Merged lazily to avoid a circular import at module load time
    # (templates.py doesn't import skills.py, so this is safe, just
    # deferred for clarity about why it's not a plain module-level dict).
    from .templates import TEMPLATES, ULTIMATES, UNIVERSAL
    merged = dict(SKILLS)
    merged.update(TEMPLATES)
    merged.update(ULTIMATES)
    merged.update(UNIVERSAL)
    return merged


_REGISTRY = None


def get_skill(skill_id: str) -> Skill:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _all_skills()
    return _REGISTRY[skill_id]
