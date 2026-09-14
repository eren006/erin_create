"""Type-counter wheel and ring-overload tier tables (v0.5 sections 03/05).

Counter relationships give MECHANIC bonuses only -- there is no blanket
damage multiplier (v0.3 had one; v0.4 removed it as double-dipping with
the mechanic bonuses, see doc changelog).

Ring cycle: control -> attack -> support -> defense -> special -> control
"control counters attack", "attack counters support", etc.
"""
from typing import Optional

from .models import TYPES

_ORDER = TYPES  # ("control", "attack", "support", "defense", "special")


def counter_relationship(attacker_type: str, defender_type: str) -> str:
    """Return 'counters' | 'countered' | 'neutral' from attacker's POV."""
    if attacker_type == defender_type:
        return "neutral"
    i = _ORDER.index(attacker_type)
    next_type = _ORDER[(i + 1) % len(_ORDER)]
    prev_type = _ORDER[(i - 1) % len(_ORDER)]
    if defender_type == next_type:
        return "counters"
    if defender_type == prev_type:
        return "countered"
    return "neutral"


# Ring overload backlash tiers (05): effect description is informational;
# resolver.py implements the actual numeric application.
OVERLOAD_TIERS = {
    0: {"chance": 0.0, "self_damage_pct": 0.0, "damage_penalty_pct": 0.0, "lose_control": False},
    1: {"chance": 0.18, "self_damage_pct": 0.05, "damage_penalty_pct": 0.0, "lose_control": False},
    2: {"chance": 0.36, "self_damage_pct": 0.08, "damage_penalty_pct": 0.20, "lose_control": False},
}
# overload >= 3 uses this tier (capped at 60% chance per formulas.backlash_chance)
OVERLOAD_TIER_3PLUS = {"self_damage_pct": 0.0, "damage_penalty_pct": 0.0, "lose_control": True}


def overload_tier_effect(overload: int) -> dict:
    if overload <= 0:
        return OVERLOAD_TIERS[0]
    if overload in OVERLOAD_TIERS:
        return OVERLOAD_TIERS[overload]
    return OVERLOAD_TIER_3PLUS


# Fusion-relevant pairing (needed later in Phase 3, kept here since it's
# defined by the same adjacency table as the counter wheel). Not used by
# the 1v1 engine (fusion needs a team of 2+), listed for reference only.
FUSION_PAIRS = {
    frozenset({"control", "attack"}): "合击/破招",
    frozenset({"attack", "support"}): "强化爆发",
    frozenset({"support", "defense"}): "群体守护",
    frozenset({"defense", "special"}): "反制领域",
    frozenset({"special", "control"}): "封锁/欺诈",
}


def is_adjacent_pair(type_a: str, type_b: str) -> Optional[str]:
    """Return the fusion pairing name if type_a/type_b are ring-adjacent."""
    return FUSION_PAIRS.get(frozenset({type_a, type_b}))
