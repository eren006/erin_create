"""Single-round resolution: resolve_round(battle_state, actions, seed).

Pure function contract (v0.5 section 11): same battle_state + actions +
seed always produces the same next_state + events. No Flask, no DB, no
wall-clock reads. Randomness comes only from a random.Random seeded
deterministically from (seed, round) or (seed, unit_id) for the fixed
tie-break sequence.

Phase 1 scope: 1v1 only. No fusion skills (needs a team of 2+), no
equipment, no faction war -- see 斗罗五阵录 v0.5 section 12.
"""
import copy
import random
from typing import Dict, List, Tuple

from . import formulas
from .effects import counter_relationship, overload_tier_effect
from .models import Action, BattleState, Skill, StatusEffect, UnitState
from .skills import get_skill

REFUND_RATIO_ON_INTERRUPT = 0.5
WEAKEN_RATIO_ON_INTERRUPT = 0.5  # interrupted skill executes at half power
FATIGUED_BASIC_ATTACK_RATIO = 0.5  # insufficient-soul fallback

# Phase 2.1 "minimum win path" mechanics (v0.7 review + Phase 2 sim data):
# control/support/defense had no way to convert their utility into a kill
# -- these give each a real finishing tool with ONE integer counter each,
# not per-type conditional branching. See doc changelog for the diagnosis
# (identical base stats across types by construction rule out "attribute"
# as attack's edge; the type matrix showed it's pure skill-kit composition).
ADVANTAGE_STACK_CAP = 3
ADVANTAGE_BONUS_PER_STACK = 0.15  # dmg bonus per stack, consumed on next damage hit
EXPOSED_DURATION = 2       # rounds a control "exposed" debuff lasts
EXPOSED_BONUS = 0.20       # +dmg taken while exposed (control's follow-up window)
SPECIAL_MARK_BONUS = 0.15  # special's own dmg skills hit harder vs an already-marked target

# Controlled-experiment switch for Phase 2's counter-edge A/B test (does
# NOT change any numeric constant -- toggles whether the four
# implemented counter-mechanic bonuses below apply at all, with every
# other rule identical, so "mechanism on" vs "mechanism off" battles can
# be compared with the same seeds/stats/skills/AI). Leave True for any
# real game logic; only test harnesses should ever set this False.
COUNTER_MECHANICS_ENABLED = True

# known gap (documented, not guessed): "特殊克控制" (special negating a
# control unit's own counter bonus via hidden-type play) is not
# implemented yet -- it depends on info-play/UI concepts (scouting,
# hidden skill reveal) that aren't fully specified as engine-level rules
# in the design doc. counter_relationship() still reports it correctly;
# there is simply no mechanic bonus function wired up for that pair.


def _effective_type(unit: UnitState, skill: Skill) -> str:
    """Basic attacks borrow the caster's own soul type."""
    return unit.soul_type if skill.is_basic_attack else skill.type


def _tie_break_key(seed: int, unit_id: str) -> float:
    """Deterministic 'fixed random sequence' generated once per battle,
    independent of round number, per v0.5 section 07."""
    return random.Random(f"tie:{seed}:{unit_id}").random()


def _counter_speed_bonus(attacker_type: str, defender_type: str) -> int:
    if not COUNTER_MECHANICS_ENABLED:
        return 0
    if attacker_type == "control" and defender_type == "attack":
        return 15
    return 0


def _counter_control_chance_bonus(attacker_type: str, defender_type: str) -> float:
    if not COUNTER_MECHANICS_ENABLED:
        return 0.0
    if attacker_type == "control" and defender_type == "attack":
        return 0.15
    return 0.0


def _counter_damage_multiplier(attacker_type: str, defender_type: str, target_shielded: bool) -> float:
    if not COUNTER_MECHANICS_ENABLED:
        return 1.0
    if attacker_type == "attack" and defender_type == "support" and target_shielded:
        return 1.20
    return 1.0


def _counter_debuff_dispels_buff(attacker_type: str, defender_type: str) -> bool:
    if not COUNTER_MECHANICS_ENABLED:
        return False
    return attacker_type == "support" and defender_type == "defense"


def _counter_debuff_duration_penalty(attacker_type: str, defender_type: str) -> int:
    """防御克特殊: incoming DoT/debuff from a special-type attacker onto a
    defense-type target is shortened by 1 round (min 1)."""
    if not COUNTER_MECHANICS_ENABLED:
        return 0
    if attacker_type == "special" and defender_type == "defense":
        return 1
    return 0


def resolve_round(
    battle_state: BattleState,
    actions: Dict[str, Action],
    seed: int,
) -> Tuple[BattleState, List[dict], bool]:
    """Resolve one round. Returns (next_state, events, battle_finished).

    `actions` maps unit_id -> Action for every living unit that has one
    (a unit with no action simply does nothing this round).
    """
    state = copy.deepcopy(battle_state)
    rng = random.Random(f"{seed}:{state.round}")
    events: List[dict] = []
    seq = [0]

    def emit(event_type: str, **fields) -> None:
        seq[0] += 1
        events.append({"seq": seq[0], "round": state.round, "type": event_type, **fields})

    units = state.units

    # ---- decay shields at the start of the round --------------------
    for u in units.values():
        if u.shield:
            u.shield = formulas.decay_shield(u.shield)

    # Cooldowns that existed BEFORE this round's actions resolve tick
    # down at the end of this round; a cooldown freshly set by an action
    # taken THIS round only starts ticking at the end of the NEXT round,
    # so "cooldown: N" means N full rounds of downtime after use.
    pre_round_cooldowns = {uid: set(u.cooldowns.keys()) for uid, u in units.items()}
    # Same fix as cooldowns: a status (stun/silence/slow/disarm) applied
    # THIS round must not tick down at this round's own end -- found via
    # Phase 2's control-fatigue pass, which showed zero "stunned" events
    # ever firing (every freshly-applied 1-round status was expiring
    # before the next round's pre-round status check could see it).
    pre_round_status_ids = {uid: {id(s) for s in u.statuses} for uid, u in units.items()}

    # ---- resolve statuses that block/alter the chosen action --------
    resolved_skill: Dict[str, Skill] = {}
    for unit_id, action in actions.items():
        unit = units[unit_id]
        if not unit.alive:
            continue
        skill = get_skill(action.skill_id)
        if unit.has_status("stun"):
            # Emitted here directly: a stunned unit is excluded from
            # `order` below (it has no action to sequence), so the main
            # per-unit loop -- and _execute's skill=None branch -- would
            # otherwise never run for it and this event would never fire.
            emit("stunned", source=unit.id)
            resolved_skill[unit_id] = None  # stunned: forfeits the round
            continue
        if unit.has_status("silence") and not skill.is_basic_attack:
            skill = get_skill("basic_attack")
        if unit.has_status("disarm") and skill.type == "attack" and not skill.is_basic_attack:
            skill = get_skill("basic_attack")
        resolved_skill[unit_id] = skill

    # ---- compute this round's action speed and ordering --------------
    order: List[str] = []
    action_speed_of: Dict[str, int] = {}
    for unit_id, action in actions.items():
        unit = units[unit_id]
        skill = resolved_skill.get(unit_id)
        if not unit.alive or skill is None:
            continue
        target = units.get(action.target_id)
        speed_bonus = 0
        if target is not None and skill.kind != "basic":
            atype = _effective_type(unit, skill)
            speed_bonus = _counter_speed_bonus(atype, target.soul_type)
        status_mod = int(unit.status_magnitude("spd_mod"))
        action_speed_of[unit_id] = formulas.action_speed(unit.spd, skill.speed_mod + speed_bonus, status_mod)
        order.append(unit_id)

    order.sort(
        key=lambda uid: (
            -action_speed_of[uid],
            -resolved_skill[uid].priority,
            -units[uid].spd,
            -_tie_break_key(seed, uid),
            uid,
        )
    )

    interrupted: Dict[str, bool] = {}
    was_controlled_this_round: Dict[str, bool] = {}

    for unit_id in order:
        unit = units[unit_id]
        if not unit.alive:
            continue
        action = actions[unit_id]
        skill = resolved_skill[unit_id]
        target = units.get(action.target_id)

        if interrupted.get(unit_id):
            _execute(
                units, unit, skill, target, rng, emit,
                weaken=True, refund=True, consume_resources=False, allow_overload=False,
                was_controlled_this_round=was_controlled_this_round,
            )
            continue

        # cooldown / soul checks (defensive net; real selection UI should
        # already prevent illegal choices)
        on_cooldown = (not skill.is_basic_attack) and unit.cooldowns.get(skill.id, 0) > 0
        if on_cooldown:
            skill = get_skill("basic_attack")
            _execute(
                units, unit, skill, target, rng, emit,
                weaken=False, refund=False, consume_resources=True, allow_overload=False,
                was_controlled_this_round=was_controlled_this_round,
            )
            continue

        if not skill.is_basic_attack and unit.soul < skill.soul_cost:
            emit("fatigued_basic_attack", source=unit.id, reason="insufficient_soul")
            _execute(
                units, unit, get_skill("basic_attack"), target, rng, emit,
                weaken=True, refund=False, consume_resources=False, allow_overload=False,
                was_controlled_this_round=was_controlled_this_round,
            )
            continue

        _execute(
            units, unit, skill, target, rng, emit,
            weaken=False, refund=False, consume_resources=True, allow_overload=True,
            was_controlled_this_round=was_controlled_this_round,
            interrupted_map=interrupted,
            order=order,
            unit_id=unit_id,
        )

    # ---- end-of-round upkeep -------------------------------------------
    for unit_id, action in actions.items():
        unit = units[unit_id]
        if not unit.alive:
            continue
        skill = resolved_skill.get(unit_id)
        used_basic = skill is None or skill.is_basic_attack
        regen = formulas.SOUL_NATURAL_REGEN + (formulas.SOUL_BASIC_ATTACK_BONUS_REGEN if used_basic else 0)
        unit.soul = min(unit.max_soul, unit.soul + regen)

    for unit in units.values():
        if not unit.alive:
            continue
        for skill_id in list(unit.cooldowns.keys()):
            if skill_id not in pre_round_cooldowns.get(unit.id, set()):
                continue  # freshly set this round; starts ticking next round
            unit.cooldowns[skill_id] = max(0, unit.cooldowns[skill_id] - 1)
            if unit.cooldowns[skill_id] == 0:
                del unit.cooldowns[skill_id]
        pre_existing_ids = pre_round_status_ids.get(unit.id, set())
        for status in unit.statuses:
            if id(status) in pre_existing_ids:
                status.rounds_left -= 1
            # else: freshly applied this round, starts ticking next round
        unit.statuses = [s for s in unit.statuses if s.rounds_left > 0]

        if unit.control_fatigue >= formulas.CONTROL_FATIGUE_IMMUNE_TIER:
            unit.control_fatigue = 0
            emit("control_fatigue_reset", target=unit.id)
        elif not was_controlled_this_round.get(unit.id):
            unit.control_fatigue = max(0, unit.control_fatigue - 1)

    finished = any(not u.alive for u in units.values())
    winner = None
    if finished:
        survivors = [u.id for u in units.values() if u.alive]
        winner = survivors[0] if len(survivors) == 1 else None

    state.finished = finished
    state.winner = winner
    state.round += 1
    return state, events, finished


def _execute(
    units: Dict[str, UnitState],
    unit: UnitState,
    skill: Skill,
    target,
    rng: random.Random,
    emit,
    *,
    weaken: bool,
    refund: bool,
    consume_resources: bool,
    allow_overload: bool,
    was_controlled_this_round: Dict[str, bool],
    interrupted_map: Dict[str, bool] = None,
    order: List[str] = None,
    unit_id: str = None,
) -> None:
    if consume_resources and not skill.is_basic_attack:
        unit.soul -= skill.soul_cost
        if refund:
            unit.soul = min(unit.max_soul, unit.soul + int(skill.soul_cost * REFUND_RATIO_ON_INTERRUPT))
        if skill.cooldown:
            unit.cooldowns[skill.id] = skill.cooldown

    power = skill.power
    if weaken:
        power = int(power * WEAKEN_RATIO_ON_INTERRUPT)
        emit("interrupted", source=unit.id, skill_id=skill.id)
    elif skill.is_basic_attack and not consume_resources:
        power = int(power * FATIGUED_BASIC_ATTACK_RATIO)

    overload_note = None
    damage_penalty = 0.0
    if allow_overload and not skill.is_basic_attack:
        overload = formulas.overload_value(skill.ring_tier, unit.power_level)
        if overload > 0 and rng.random() < formulas.backlash_chance(overload):
            tier = overload_tier_effect(overload)
            self_dmg = int(unit.max_hp * tier["self_damage_pct"])
            if self_dmg:
                unit.hp = max(0, unit.hp - self_dmg)
            damage_penalty = tier["damage_penalty_pct"]
            if tier["lose_control"] and target is not None:
                alive_others = [u for u in units.values() if u.alive and u.id != unit.id]
                if alive_others:
                    target = rng.choice(alive_others)
            emit(
                "ring_backlash",
                source=unit.id,
                overload=overload,
                self_damage=self_dmg,
                damage_penalty_pct=damage_penalty,
                redirected=tier["lose_control"],
            )
            overload_note = tier
            if unit.hp <= 0:
                unit.alive = False

    if not unit.alive or target is None or not target.alive:
        return

    atype = _effective_type(unit, skill)
    dtype = target.soul_type
    rel = counter_relationship(atype, dtype)

    if skill.kind in ("basic", "damage"):
        effective_def = int(target.def_ * (1 - target.status_magnitude("def_down")))
        dmg = formulas.final_damage(power, unit.atk, max(0, effective_def))
        if damage_penalty:
            dmg = int(dmg * (1 - damage_penalty))
        if rel == "counters":
            mult = _counter_damage_multiplier(atype, dtype, target.shield > 0)
            if mult != 1.0:
                dmg = int(dmg * mult)
                emit("counter_bonus", source=unit.id, target=target.id, kind="damage_bonus")
        exposed_mag = target.status_magnitude("exposed")
        if exposed_mag:
            dmg = int(dmg * (1 + exposed_mag))
            emit("exposed_bonus", source=unit.id, target=target.id, bonus_pct=exposed_mag)
        if atype == "special" and target.has_status("def_down"):
            dmg = int(dmg * (1 + SPECIAL_MARK_BONUS))
            emit("mark_bonus", source=unit.id, target=target.id, bonus_pct=SPECIAL_MARK_BONUS)
        if unit.advantage_stacks > 0:
            dmg = int(dmg * (1 + ADVANTAGE_BONUS_PER_STACK * unit.advantage_stacks))
            emit("advantage_consumed", source=unit.id, stacks=unit.advantage_stacks)
            unit.advantage_stacks = 0
        remaining = dmg
        if target.shield > 0:
            absorbed = min(target.shield, remaining)
            target.shield -= absorbed
            remaining -= absorbed
            target.advantage_stacks = min(ADVANTAGE_STACK_CAP, target.advantage_stacks + 1)
            emit("shield_absorbed", target=target.id, amount=absorbed)
        target.hp = max(0, target.hp - remaining)
        emit(
            "damage",
            source=unit.id, target=target.id, skill_id=skill.id,
            amount=dmg, target_hp_after=target.hp,
        )
        if target.hp <= 0:
            target.alive = False
            emit("defeated", target=target.id)

        # hybrid secondary effects (Phase 2.1 skill-package restructure):
        # a damage skill can ALSO grant the caster a stack, a shield, or
        # attempt a light control effect on the target -- these give
        # control/support/defense multiple skills that both progress the
        # fight and build toward their own conversion mechanic, instead
        # of exactly one damage skill bolted onto pure utility.
        if skill.grants_stack:
            unit.advantage_stacks = min(ADVANTAGE_STACK_CAP, unit.advantage_stacks + 1)
        if skill.attached_shield_power:
            gained = formulas.shield_value(skill.attached_shield_power, unit.def_)
            unit.shield += gained
            emit("shield_gained", source=unit.id, amount=gained, shield_total=unit.shield)
        if skill.secondary_control_effect and target.alive:
            sec_chance = formulas.control_chance(
                skill.secondary_control_chance, target.res, target.control_fatigue
            )
            sec_success = rng.random() < sec_chance
            emit(
                "secondary_control_resolved", source=unit.id, target=target.id,
                effect=skill.secondary_control_effect, chance=sec_chance, success=sec_success,
            )
            if sec_success:
                target.control_fatigue = min(
                    formulas.CONTROL_FATIGUE_IMMUNE_TIER, target.control_fatigue + 1
                )
                was_controlled_this_round[target.id] = True
                target.statuses.append(
                    StatusEffect(kind=skill.secondary_control_effect, rounds_left=skill.secondary_control_duration)
                )

    elif skill.kind == "shield":
        shield_amt = formulas.shield_value(power, unit.def_)
        unit.shield += shield_amt
        unit.advantage_stacks = min(ADVANTAGE_STACK_CAP, unit.advantage_stacks + 1)
        emit("shield_gained", source=unit.id, amount=shield_amt, shield_total=unit.shield)

    elif skill.kind == "debuff":
        # magnitude scales with skill.power (was a fixed 0.2 regardless
        # of power -- every support skill was mechanically identical
        # regardless of its designed strength; found via Phase 2 sim).
        magnitude = min(0.5, power / 300.0)
        duration = 2
        if rel == "counters":
            # caster's type counters target's type: offensive bonus (支持克防御's dispel)
            if _counter_debuff_dispels_buff(atype, dtype) and target.shield > 0:
                target.shield = 0
                emit("dispelled", source=unit.id, target=target.id, removed="shield")
        if rel == "countered":
            # target's type counters caster's type: DEFENSIVE resistance
            # (防御克特殊) -- this benefits the target, so it must key off
            # the opposite relationship direction from the offensive
            # bonuses above. Found via Phase 2's counter-edge A/B test:
            # triggers(A) was 0 for defense->special because this branch
            # was previously also gated behind rel=="counters", which
            # from the caster's (special's) own viewpoint is never true
            # here -- special is COUNTERED BY defense, not countering it.
            duration = max(1, duration - _counter_debuff_duration_penalty(atype, dtype))
        target.statuses.append(StatusEffect(kind="def_down", rounds_left=duration, magnitude=magnitude))
        unit.advantage_stacks = min(ADVANTAGE_STACK_CAP, unit.advantage_stacks + 1)
        emit("debuff_applied", source=unit.id, target=target.id, skill_id=skill.id, duration=duration, magnitude=magnitude)

    elif skill.kind == "control":
        chance = skill.base_control_chance
        if rel == "counters":
            chance += _counter_control_chance_bonus(atype, dtype)
        chance = formulas.control_chance(chance, target.res, target.control_fatigue)
        success = rng.random() < chance
        emit(
            "control_resolved",
            source=unit.id, target=target.id, skill_id=skill.id,
            base_chance=skill.base_control_chance, final_chance=chance, success=success,
            target_fatigue_before=target.control_fatigue,
        )
        if success:
            target.control_fatigue = min(
                formulas.CONTROL_FATIGUE_IMMUNE_TIER, target.control_fatigue + 1
            )
            was_controlled_this_round[target.id] = True
            if skill.control_effect == "interrupt":
                if order and unit_id and interrupted_map is not None:
                    if target.id in order and order.index(target.id) > order.index(unit_id):
                        interrupted_map[target.id] = True
                        emit("will_be_interrupted", target=target.id)
                        target.statuses.append(
                            StatusEffect(kind="exposed", rounds_left=EXPOSED_DURATION, magnitude=EXPOSED_BONUS)
                        )
            else:
                target.statuses.append(
                    StatusEffect(kind=skill.control_effect, rounds_left=skill.control_duration)
                )
                if skill.control_effect == "stun":
                    target.statuses.append(
                        StatusEffect(kind="exposed", rounds_left=EXPOSED_DURATION, magnitude=EXPOSED_BONUS)
                    )

    elif skill.kind == "heal":
        # self-targeted only (1v1 has no ally to heal); reuses the base
        # damage formula's shape with no defense mitigation since it's
        # not an attack. Support's defining "win by outlasting into a
        # big hit" tool.
        heal_amt = formulas.base_damage(power, unit.atk)
        unit.hp = min(unit.max_hp, unit.hp + heal_amt)
        if skill.grants_stack:
            unit.advantage_stacks = min(ADVANTAGE_STACK_CAP, unit.advantage_stacks + 1)
        emit("heal_gained", source=unit.id, amount=heal_amt, hp_after=unit.hp)

    elif skill.kind == "focus":
        # pure resource management: restore soul to self, no combat effect.
        restored = power
        unit.soul = min(unit.max_soul, unit.soul + restored)
        emit("focus_used", source=unit.id, amount=restored, soul_after=unit.soul)
