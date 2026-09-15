"""Phase 3A multi-unit round resolution: resolve_team_round(state, actions, seed).

Separate module from resolver.py (1v1) on purpose -- see EncounterState's
docstring in models.py. Pure function contract, same as the 1v1 resolver:
same state + actions + seed -> same next_state + events, no wall-clock
reads, no Flask/DB. Randomness only from a random.Random seeded from
(seed, round).

Deliberately simplified vs. the 1v1 engine for this first vertical slice
(scope per the Phase 3A/B/C/D brief -- not an oversight):
  - no ring overload/backlash
  - a landed "interrupt" fully cancels the target's pending action this
    round (no partial-weaken-and-refund) -- simpler, and matches "打断
    关键技能才计控制贡献" directly
  - no advantage_stacks/exposed (those are 1v1-only for now)
These can be ported in later once the team primitives themselves (team_id,
group targeting, protect, objective, charge) are validated.

Identity/allegiance/display are three separate things, on purpose (the
seating bug was exactly this kind of conflation): `unit.id` is the
permanent unit_id, `unit.team_id` is allegiance for THIS encounter (ally/
enemy resolution reads ONLY this), `unit.faction_id` is metadata with NO
mechanical effect. There is no "seat" concept here at all -- display
position belongs to a future UI layer.
"""
import random
from typing import Dict, List, Optional, Tuple

from . import formulas
from .models import Action, EncounterState, Skill, StatusEffect, UnitState
from .skills import get_skill

CONTROL_FATIGUE_IMMUNE_TIER = formulas.CONTROL_FATIGUE_IMMUNE_TIER


def is_enemy(a: UnitState, b: UnitState) -> bool:
    return a.team_id != b.team_id


def is_ally(a: UnitState, b: UnitState) -> bool:
    return a.team_id == b.team_id and a.id != b.id


def _tie_break_key(seed: int, unit_id: str) -> float:
    return random.Random(f"team-tie:{seed}:{unit_id}").random()


def _effective_type(unit: UnitState, skill: Skill) -> str:
    return unit.soul_type if skill.is_basic_attack else skill.type


def resolve_targets(caster: UnitState, skill: Skill, chosen_target_id: Optional[str],
                     units: Dict[str, UnitState]) -> List[UnitState]:
    """Resolve the actual legal target list for a skill's target_mode.
    Only alive units are ever returned. Dead/missing chosen targets for
    single-target modes resolve to an empty list (the caller treats this
    as 'no legal target', not an error) -- covers the case where the
    original target died earlier in the same round."""
    mode = skill.target_mode
    if mode == "self":
        return [caster] if caster.alive else []
    if mode == "single_enemy":
        t = units.get(chosen_target_id) if chosen_target_id else None
        return [t] if t and t.alive and is_enemy(caster, t) else []
    if mode == "single_ally":
        if chosen_target_id == caster.id:
            return [caster] if caster.alive else []
        t = units.get(chosen_target_id) if chosen_target_id else None
        return [t] if t and t.alive and is_ally(caster, t) else []
    if mode == "all_enemies":
        return [u for u in units.values() if u.alive and is_enemy(caster, u)]
    if mode == "all_allies":
        return [u for u in units.values() if u.alive and (is_ally(caster, u) or u.id == caster.id)]
    if mode == "objective":
        # Deliberately NOT filtered by ally/enemy: a boss attacking the
        # objective and a player repairing it are both legitimate, and
        # this vertical slice has exactly one objective per encounter.
        # If a future encounter needs multiple objectives per side, this
        # needs a real side-aware lookup instead of "the one objective".
        objs = [u for u in units.values() if u.alive and u.is_objective]
        return objs[:1]
    return []


def resolve_team_round(
    state: EncounterState,
    actions: Dict[str, Action],
    seed: int,
) -> Tuple[EncounterState, List[dict]]:
    import copy
    state = copy.deepcopy(state)
    rng = random.Random(f"team:{seed}:{state.round}")
    events: List[dict] = []
    seq = [0]

    def emit(event_type: str, **fields) -> None:
        seq[0] += 1
        events.append({"seq": seq[0], "round": state.round, "type": event_type, **fields})

    units = state.units
    fighters = {uid: u for uid, u in units.items() if not u.is_objective}

    # ---- start-of-round upkeep: shield decay, cooldown/status snapshot --
    for u in units.values():
        if u.shield:
            u.shield = formulas.decay_shield(u.shield)
        u.pending_protector_id = None  # both re-decided fresh each round;
        u.active_protector_id = None   # protection never carries over
    pre_round_cooldowns = {uid: set(u.cooldowns.keys()) for uid, u in fighters.items()}
    pre_round_status_ids = {uid: {id(s) for s in u.statuses} for uid, u in units.items()}

    # ---- resolve statuses that block/alter the chosen action ----------
    resolved_skill: Dict[str, Optional[Skill]] = {}
    resolved_target: Dict[str, Optional[str]] = {}
    for uid, unit in fighters.items():
        if not unit.alive:
            continue
        if unit.charging_skill:
            resolved_skill[uid] = "__charging__"  # sentinel, handled separately below
            continue
        action = actions.get(uid)
        if action is None:
            continue
        skill = get_skill(action.skill_id)
        if unit.has_status("stun"):
            emit("stunned", source=uid)
            resolved_skill[uid] = None
            continue
        if unit.has_status("silence") and not skill.is_basic_attack:
            skill = get_skill("basic_attack")
        if unit.has_status("disarm") and skill.type == "attack" and not skill.is_basic_attack:
            skill = get_skill("basic_attack")
        resolved_skill[uid] = skill
        resolved_target[uid] = action.target_id

    # ---- ordering: everyone with a resolved (non-None) action/charge ---
    order: List[str] = []
    action_speed_of: Dict[str, int] = {}
    for uid, unit in fighters.items():
        skill = resolved_skill.get(uid)
        if not unit.alive or skill is None:
            continue
        if skill == "__charging__":
            action_speed_of[uid] = formulas.action_speed(unit.spd, 0, int(unit.status_magnitude("spd_mod")))
        else:
            atype = _effective_type(unit, skill)
            speed_bonus = 0
            if skill.target_mode in ("single_enemy", "objective", "all_enemies"):
                targets_preview = resolve_targets(unit, skill, resolved_target.get(uid), units)
                if targets_preview and skill.kind != "basic":
                    speed_bonus = 15 if atype == "control" and targets_preview[0].soul_type == "attack" else 0
            status_mod = int(unit.status_magnitude("spd_mod"))
            action_speed_of[uid] = formulas.action_speed(unit.spd, skill.speed_mod + speed_bonus, status_mod)
        order.append(uid)

    order.sort(key=lambda uid: (
        -action_speed_of[uid], -fighters[uid].spd, -_tie_break_key(seed, uid), uid,
    ))

    # ---- protect pre-registration: bookkeeping ONLY, no mechanical -----
    # effect yet. Determines which protector "wins" when several declare
    # protecting the same ally (skill priority -> actual action speed ->
    # base SPD -> fixed random tie-break -> unit_id), so that when a
    # protector's OWN action later resolves at its speed-determined slot,
    # it already knows whether it's the one that gets to activate.
    candidates_by_target: Dict[str, List[str]] = {}
    for uid in order:
        skill = resolved_skill.get(uid)
        if skill is None or skill == "__charging__" or skill.kind != "protect":
            continue
        target_id = resolved_target.get(uid)
        if target_id and target_id in fighters:
            candidates_by_target.setdefault(target_id, []).append(uid)
    for target_id, protector_ids in candidates_by_target.items():
        winner = min(protector_ids, key=lambda pid: (
            -get_skill(actions[pid].skill_id).priority,
            -action_speed_of.get(pid, -10**9),
            -fighters[pid].spd,
            -_tie_break_key(seed, pid),
            pid,
        ))
        fighters[target_id].pending_protector_id = winner
        emit("protect_registered", protector=winner, target=target_id,
             contested=len(protector_ids) > 1)

    interrupted: Dict[str, bool] = {}
    was_controlled_this_round: Dict[str, bool] = {}

    for uid in order:
        unit = fighters[uid]
        if not unit.alive:
            continue
        skill = resolved_skill[uid]

        if skill == "__charging__":
            if was_controlled_this_round.get(uid):
                unit.charging_skill = None
                unit.charge_rounds_left = 0
                emit("charge_interrupted", source=uid)
                continue
            unit.charge_rounds_left -= 1
            if unit.charge_rounds_left > 0:
                emit("charging_continues", source=uid, rounds_left=unit.charge_rounds_left)
                continue
            charged_skill = get_skill(unit.charging_skill)
            unit.charging_skill = None
            emit("charge_resolved", source=uid, skill_id=charged_skill.id)
            _apply_skill(units, unit, charged_skill, None, rng, emit,
                         was_controlled_this_round, order, uid, interrupted)
            continue

        if interrupted.get(uid):
            emit("interrupted", source=uid, skill_id=skill.id)
            continue

        on_cooldown = (not skill.is_basic_attack) and unit.cooldowns.get(skill.id, 0) > 0
        insufficient_soul = (not skill.is_basic_attack) and unit.soul < skill.soul_cost
        if on_cooldown or insufficient_soul:
            skill = get_skill("basic_attack")
            if insufficient_soul and not on_cooldown:
                emit("fatigued_basic_attack", source=uid, reason="insufficient_soul")

        target_id = resolved_target.get(uid)

        if skill.charge_rounds > 0:
            # Starting a wind-up consumes this turn but deals no effect
            # yet -- soul cost is paid up front, cooldown starts only
            # when the charge actually resolves (see the "__charging__"
            # branch above), so an interrupted charge doesn't also waste
            # a cooldown on top of the soul already spent.
            if not skill.is_basic_attack:
                unit.soul -= skill.soul_cost
            unit.charging_skill = skill.id
            unit.charge_rounds_left = skill.charge_rounds
            emit("charge_started", source=unit.id, skill_id=skill.id, rounds=skill.charge_rounds)
            continue

        if not skill.is_basic_attack:
            unit.soul -= skill.soul_cost
            if skill.cooldown:
                unit.cooldowns[skill.id] = skill.cooldown

        _apply_skill(units, unit, skill, target_id, rng, emit,
                     was_controlled_this_round, order, uid, interrupted)

    # ---- end-of-round upkeep ------------------------------------------
    for uid, unit in fighters.items():
        if not unit.alive:
            continue
        skill = resolved_skill.get(uid)
        used_basic = skill is None or skill == "__charging__" or getattr(skill, "is_basic_attack", False)
        regen = formulas.SOUL_NATURAL_REGEN + (formulas.SOUL_BASIC_ATTACK_BONUS_REGEN if used_basic else 0)
        unit.soul = min(unit.max_soul, unit.soul + regen)

    for unit in units.values():
        if unit.is_objective and unit.hp <= 0:
            continue
        if not unit.alive:
            continue
        cds = pre_round_cooldowns.get(unit.id, set())
        for skill_id in list(unit.cooldowns.keys()):
            if skill_id not in cds:
                continue
            unit.cooldowns[skill_id] = max(0, unit.cooldowns[skill_id] - 1)
            if unit.cooldowns[skill_id] == 0:
                del unit.cooldowns[skill_id]
        pre_ids = pre_round_status_ids.get(unit.id, set())
        for status in unit.statuses:
            if id(status) in pre_ids:
                status.rounds_left -= 1
        unit.statuses = [s for s in unit.statuses if s.rounds_left > 0]
        if unit.control_fatigue >= CONTROL_FATIGUE_IMMUNE_TIER:
            unit.control_fatigue = 0
            emit("control_fatigue_reset", target=unit.id)
        elif not was_controlled_this_round.get(unit.id):
            unit.control_fatigue = max(0, unit.control_fatigue - 1)

    objectives_alive = [u for u in units.values() if u.is_objective]
    objective_destroyed = any(o.hp <= 0 for o in objectives_alive)
    players_alive = [u for u in fighters.values() if u.team_id == "players" and u.alive]
    npcs_alive = [u for u in fighters.values() if u.team_id != "players" and u.alive]

    finished = False
    outcome = None
    if objective_destroyed:
        finished, outcome = True, "failure"
    elif not npcs_alive:
        finished, outcome = True, "success"
    elif not players_alive:
        finished, outcome = True, "failure"

    state.finished = finished
    state.outcome = outcome
    state.round += 1
    return state, events


def _deal_damage_to(target: UnitState, dmg: int, source: UnitState, skill: Skill, emit) -> None:
    """Apply dmg to target's shield-then-hp, and emit the resulting
    events. Shared by the direct hit and the redirected-to-protector
    portion so both go through the exact same mitigation pipeline."""
    remaining = dmg
    if target.shield > 0:
        absorbed = min(target.shield, remaining)
        target.shield -= absorbed
        remaining -= absorbed
        emit("shield_absorbed", target=target.id, amount=absorbed, source=source.id)
    target.hp = max(0, target.hp - remaining)
    emit("damage", source=source.id, target=target.id, skill_id=skill.id,
         amount=dmg, target_hp_after=target.hp, is_objective=target.is_objective)
    if target.hp <= 0:
        target.alive = False
        emit("defeated", target=target.id)


def _protect_fallback_shield(unit: UnitState, skill: Skill, emit, reason: str) -> None:
    """A protect skill that can't activate (target died before this
    protector's turn, or another protector won the priority contest for
    the same ally) does NOT silently waste the whole action, and does
    NOT auto-retarget to a different ally -- the system silently
    choosing a new target for the player would override their actual
    intent. It falls back to a weakened self-shield instead."""
    amt = formulas.shield_value(skill.power // 2, unit.def_)
    unit.shield += amt
    emit("protect_fallback_shield", source=unit.id, amount=amt, shield_total=unit.shield, reason=reason)


def _apply_skill(units, unit, skill, target_id, rng, emit,
                  was_controlled_this_round, order, unit_id, interrupted_map) -> None:
    if skill.kind == "protect":
        declared_target = units.get(target_id)
        if declared_target is None or not declared_target.alive:
            _protect_fallback_shield(unit, skill, emit, reason="target_invalid")
            return
        if declared_target.pending_protector_id != unit_id:
            _protect_fallback_shield(unit, skill, emit, reason="lost_priority")
            return
        declared_target.active_protector_id = unit_id
        emit("protect_activated", source=unit.id, target=declared_target.id)
        return

    targets = resolve_targets(unit, skill, target_id, units)
    if not targets and skill.target_mode not in ("all_enemies", "all_allies"):
        emit("no_legal_target", source=unit.id, skill_id=skill.id)
        return

    atype = _effective_type(unit, skill)
    power = skill.power

    if skill.kind in ("basic", "damage"):
        # Each target in an AoE is judged for protection independently
        # (per-target, not once for the whole skill). Redirect is single-
        # level only -- the portion sent to the protector is applied
        # directly, it never itself checks for a protector-of-the-
        # protector (no A-protects-B, C-protects-A chains).
        for target in targets:
            effective_def = int(target.def_ * (1 - target.status_magnitude("def_down")))
            dmg = formulas.final_damage(power, unit.atk, max(0, effective_def))

            protector = None
            if target.active_protector_id and target.active_protector_id in units:
                cand = units[target.active_protector_id]
                if cand.alive and cand.id != target.id:
                    protector = cand

            if protector is not None:
                redirected_amount = dmg // 2
                remaining_on_target = dmg - redirected_amount
                emit("damage_redirected", original_target=target.id, protector=protector.id,
                     original_damage=dmg, redirected_damage=redirected_amount,
                     remaining_damage=remaining_on_target, redirect_depth=1)
                _deal_damage_to(target, remaining_on_target, unit, skill, emit)
                _deal_damage_to(protector, redirected_amount, unit, skill, emit)
            else:
                _deal_damage_to(target, dmg, unit, skill, emit)

    elif skill.kind == "shield":
        for target in targets:
            amt = formulas.shield_value(power, unit.def_)
            target.shield += amt
            emit("shield_gained", source=unit.id, target=target.id, amount=amt, shield_total=target.shield)

    elif skill.kind == "heal":
        for target in targets:
            if target.is_objective:
                emit("heal_rejected", source=unit.id, target=target.id, reason="is_objective")
                continue
            heal_amt = formulas.base_damage(power, unit.atk)
            before = target.hp
            target.hp = min(target.max_hp, target.hp + heal_amt)
            actual = target.hp - before
            emit("heal_gained", source=unit.id, target=target.id, amount=heal_amt,
                 effective_amount=actual, hp_after=target.hp)

    elif skill.kind == "repair":
        for target in targets:
            if not target.is_objective:
                continue
            amt = formulas.base_damage(power, unit.atk)
            before = target.hp
            target.hp = min(target.max_hp, target.hp + amt)
            emit("repaired", source=unit.id, target=target.id, amount=amt,
                 effective_amount=target.hp - before, hp_after=target.hp)

    elif skill.kind == "debuff":
        for target in targets:
            magnitude = min(0.5, power / 300.0)
            target.statuses.append(StatusEffect(kind="def_down", rounds_left=2, magnitude=magnitude))
            emit("debuff_applied", source=unit.id, target=target.id, skill_id=skill.id, magnitude=magnitude)
            if skill.dispel_shield and target.shield > 0:
                target.shield = 0
                emit("dispelled", source=unit.id, target=target.id, removed="shield")

    elif skill.kind == "cleanse":
        for target in targets:
            had = target.has_status("def_down")
            target.statuses = [s for s in target.statuses if s.kind != "def_down"]
            if had:
                emit("purified", source=unit.id, target=target.id, removed="def_down")
            else:
                emit("purify_wasted", source=unit.id, target=target.id)

    elif skill.kind == "focus":
        unit.soul = min(unit.max_soul, unit.soul + power)
        emit("focus_used", source=unit.id, amount=power, soul_after=unit.soul)

    elif skill.kind == "control":
        # NOTE: counter-relationship bonuses (control's +15 speed/+15%
        # chance vs attack-type, etc.) are 1v1-only for this first team
        # slice -- deferred along with exposed/advantage_stacks, see the
        # module docstring. counter_relationship() itself is unused here
        # on purpose, not a leftover.
        for target in targets:
            chance = skill.base_control_chance
            chance = formulas.control_chance(chance, target.res, target.control_fatigue)
            success = rng.random() < chance
            emit("control_resolved", source=unit.id, target=target.id, skill_id=skill.id,
                 base_chance=skill.base_control_chance, final_chance=chance, success=success,
                 target_fatigue_before=target.control_fatigue)
            if not success:
                continue
            target.control_fatigue = min(CONTROL_FATIGUE_IMMUNE_TIER, target.control_fatigue + 1)
            was_controlled_this_round[target.id] = True
            if skill.control_effect == "interrupt":
                if target.id in order and order.index(target.id) > order.index(unit_id):
                    interrupted_map[target.id] = True
                    emit("will_be_interrupted", target=target.id)
            else:
                target.statuses.append(StatusEffect(kind=skill.control_effect, rounds_left=skill.control_duration))
