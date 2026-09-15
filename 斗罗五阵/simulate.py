"""Phase 2 shared building blocks: character generation, the 30 mechanic
templates' loadout sampling, and the five AI policies.

This module is a LIBRARY now, imported as `import simulate as S` by
run_phase2_suite.py and phase2_counter_ab_test.py -- it has no `main()`
and running it directly does nothing. It used to also own the
battle-running/aggregation layer (run_one_battle and friends); that
layer had a seating bug (see phase2_results_invalid_seating/summary.txt)
and was removed rather than patched in place -- the two scripts above
are the corrected replacements.
"""
import random
import statistics
import sys
from collections import Counter

from battle.engine import new_battle, run_battle
from battle.models import Action, UnitConfig
from battle.templates import TEMPLATES_BY_TYPE, CORE_DAMAGE_SKILL, STANDARD_LOADOUT
from battle.skills import get_skill
from battle.effects import counter_relationship

TYPES = ("control", "attack", "support", "defense", "special")
COUNTER_EDGES = [(TYPES[i], TYPES[(i + 1) % 5]) for i in range(5)]
# special -> control is a real edge in the wheel but its mechanic bonus
# (hidden-type negating the control side's read) is NOT implemented yet
# (see resolver.py's documented gap) -- never fold it into "5-ring"
# conclusions, report it separately and clearly marked as such.
UNIMPLEMENTED_EDGE = ("special", "control")

# v0.7 review: scale HP/ATK together by the stage multiplier so the
# defense formula's mitigation (100/(100+DEF)) doesn't shift -- freezing
# DEF/RES/SPD/SOUL is what actually keeps dmg/HP ratio *exactly* stage
# invariant under our formula. Scaling DEF by the same multiplier too
# (as literally proposed) does NOT hold the ratio constant here: with
# defense_mult = 100/(100+DEF), scaling ATK, HP and DEF all by k gives
# per-hit damage proportional to k/(100+70k), which is strictly
# increasing in k -- fights get relatively SHORTER at higher stages,
# the opposite of the stated goal. Kept the requested 1.00/1.80/3.00
# magnitudes, applied only to HP/ATK.
STAGES = {
    30: {"power_level": 30, "mult": 1.00},
    60: {"power_level": 60, "mult": 1.80},
    90: {"power_level": 90, "mult": 3.00},
}
BASE_HP, BASE_ATK, BASE_DEF, BASE_RES = 650, 110, 70, 15
# BASE_HP dropped from 1000: at 1000, even attack-vs-attack (the most
# damage-dense matchup) timed out ~90% of the time at 15 rounds. At 650
# it lands at ~9.9 avg rounds / 3.8% timeout, inside the 6-9 target band.
# Pure-utility mirror matches (control/support/defense vs themselves)
# still time out almost always regardless of this value -- expected,
# not a bug: those kits are ~all control/shield-kind with near-zero
# direct damage, so a solo pure-utility character has nothing to
# convert into a kill. That's a property of testing a team-oriented
# type alone, not evidence to buff their damage (see the 1v1-only
# disclaimer printed at the top of every run).
ULTIMATE_UNLOCK_LEVEL = 70
MAX_ROUNDS = 15


def make_character(unit_id, soul_type, stage, rng, spd=100, build="standard"):
    """build="standard" uses the curated 4-skill STANDARD_LOADOUT (the
    primary balance reference as of Phase 2.1 -- what a real player would
    actually equip). build="random_stress" samples 4-of-pool at random
    (still guaranteeing the core damage skill) to stress-test whether
    some combination leaves a character unable to deal damage at all;
    it is NOT the main balance signal any more."""
    p = STAGES[stage]
    m = p["mult"]
    if build == "standard":
        equipped = list(STANDARD_LOADOUT[soul_type])
    else:
        core = CORE_DAMAGE_SKILL[soul_type]
        rest_pool = [t for t in TEMPLATES_BY_TYPE[soul_type] if t != core]
        equipped = [core] + rng.sample(rest_pool, 3)
    has_ultimate = p["power_level"] >= ULTIMATE_UNLOCK_LEVEL
    skills = ["basic_attack"] + equipped + ["guard_stance"]
    if has_ultimate:
        skills.append(f"ultimate_{soul_type}")
    cfg = UnitConfig(
        id=unit_id, name=unit_id, soul_type=soul_type,
        max_hp=int(BASE_HP * m), atk=int(BASE_ATK * m), def_=BASE_DEF, res=BASE_RES,
        spd=spd, power_level=p["power_level"], ring_tier=1, skills=skills,
    )
    return cfg, equipped, has_ultimate


# ---- AI policies ---------------------------------------------------------
# Reduced from the reviewer's suggested 5 to 3 for this pass (random-legal,
# burst, control-priority, survival-priority) given time -- burst/control/
# survival is enough to check for one dominant strategy; resource-priority
# and a plain random-legal baseline are natural follow-ups, not done here.

def policy_burst(unit, opp, usable):
    weights = []
    for sid in usable:
        s = get_skill(sid)
        w = 0.6 if s.is_basic_attack else (1.0 + s.power / 50.0 if s.kind == "damage" else 0.8)
        weights.append(w)
    return usable, weights


def policy_control(unit, opp, usable):
    weights = []
    for sid in usable:
        s = get_skill(sid)
        if s.kind == "control":
            w = 3.0
        elif s.is_basic_attack:
            w = 0.6
        elif s.kind == "damage":
            w = 1.0 + s.power / 60.0
        else:
            w = 0.8
        weights.append(w)
    return usable, weights


def policy_survival(unit, opp, usable):
    weights = []
    low_hp = unit.hp < unit.max_hp * 0.5
    for sid in usable:
        s = get_skill(sid)
        if s.kind == "shield":
            w = 2.5 if low_hp else 0.9
        elif s.is_basic_attack:
            w = 0.8
        elif s.kind == "damage":
            w = 1.0 + s.power / 70.0
        else:
            w = 0.7
        weights.append(w)
    return usable, weights


def policy_random(unit, opp, usable):
    return usable, [1.0] * len(usable)


def policy_resource(unit, opp, usable):
    weights = []
    for sid in usable:
        s = get_skill(sid)
        if sid.startswith("ultimate_"):
            w = 3.0 if opp.hp < opp.max_hp * 0.3 else 0.25
        elif s.is_basic_attack:
            w = 1.4
        else:
            cost_factor = max(0.2, 1.0 - s.soul_cost / 80.0)
            base = 1.0 + (s.power / 80.0 if s.kind == "damage" else 0.5)
            w = base * cost_factor
        weights.append(w)
    return usable, weights


POLICIES = {
    "random": policy_random,
    "burst": policy_burst,
    "control": policy_control,
    "survival": policy_survival,
    "resource": policy_resource,
}


def _usable(unit, equipped, has_ultimate, ultimate_used):
    ids = ["basic_attack"]
    for sid in equipped:
        s = get_skill(sid)
        if unit.cooldowns.get(sid, 0) == 0 and unit.soul >= s.soul_cost:
            ids.append(sid)
    guard = get_skill("guard_stance")
    if unit.cooldowns.get("guard_stance", 0) == 0 and unit.soul >= guard.soul_cost:
        ids.append("guard_stance")
    if has_ultimate and not ultimate_used[0]:
        uid = f"ultimate_{unit.soul_type}"
        u = get_skill(uid)
        if unit.soul >= u.soul_cost:
            ids.append(uid)
    return ids


def make_action_provider(side_a, side_b, rng, ultimate_flags):
    # side_* = (unit_id, equipped, has_ultimate, policy_fn)
    def provider(state):
        actions = {}
        for uid, equipped, has_ult, policy in (side_a, side_b):
            unit = state.units[uid]
            if not unit.alive:
                continue
            opp_id = side_b[0] if uid == side_a[0] else side_a[0]
            opp = state.units[opp_id]
            ids = _usable(unit, equipped, has_ult, ultimate_flags[uid])
            ids, weights = policy(unit, opp, ids)
            chosen = rng.choices(ids, weights=weights, k=1)[0]
            if chosen.startswith("ultimate_"):
                ultimate_flags[uid][0] = True
            actions[uid] = Action(unit_id=uid, skill_id=chosen, target_id=opp_id)
        return actions
    return provider


# ---------------------------------------------------------------------
# DEPRECATED / REMOVED: run_one_battle, _basic_metrics,
# _skill_config_and_usage, run_counter_edges, run_mirror_batches,
# run_ai_cross_test, and this module's own main() used to live here.
# They all built on a `swap_seats` boolean that reordered a *list* of
# already-typed UnitConfigs -- since new_battle keys its unit dict by
# each config's own fixed .id, that reorder was a complete no-op, and
# the win-attribution code that assumed the swap had happened inverted
# roughly half of every aggregated result. See
# phase2_results_invalid_seating/summary.txt for the postmortem.
#
# Removed rather than fixed in place: run_phase2_suite.py and
# phase2_counter_ab_test.py are the corrected, current replacements --
# they use directed calls (both (X,Y) and (Y,X) run explicitly with
# their own arguments) and read win attribution from the actual
# left_type/right_type/winner recorded on each result, never inferred
# from a swap flag. Do not resurrect the pattern that was here.
#
# The helpers ABOVE this comment (make_character, the five policy_*
# functions, POLICIES, make_action_provider, _usable, STAGES, BASE_*,
# MAX_ROUNDS, TYPES, COUNTER_EDGES) are still correct and are imported
# by both replacement scripts (`import simulate as S`) -- only the
# battle-running/aggregation layer above was affected.
# ---------------------------------------------------------------------
