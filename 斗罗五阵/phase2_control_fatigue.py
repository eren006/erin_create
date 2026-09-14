"""Supplementary Phase 2 pass: control-fatigue histogram.

Only "control" type has control-kind skills in its kit (see
battle/templates.py), so control_resolved events only occur in battles
where at least one side is control-type. Reuses control-vs-<each type>
matchups from the same code/params/seed conventions as
run_phase2_suite.py -- this is a fresh, dedicated instrumentation pass,
not a reconstruction of the earlier aggregate run.

Distinguishes three things that are NOT the same:
  1. control hit          -- control_resolved, success=True
  2. hit but no action lost -- success=True and either the effect was
     silence/slow/disarm (target still acts, just modified), or it was
     an "interrupt" that landed on a target who had already acted this
     round (nothing left to cancel)
  3. genuinely lost an action -- a "stunned" event (full skip) OR an
     interrupt that actually canceled a pending action (weakened
     fallback executes instead of the real skill) -- reported as two
     distinct sub-categories, not merged, since one is a full skip and
     the other still does something (at reduced power).
"""
import random
import statistics
from collections import Counter, defaultdict

from battle.engine import new_battle
from battle.models import Action
from battle.resolver import resolve_round
import simulate as S

STAGES = (30, 60, 90)
TYPES = S.TYPES
N_PER_MATCHUP = 800  # control vs each of the 5 types, per seating


def run_one(stage, seed, opp_type, swap_seats):
    chargen_rng = random.Random(("fatigue-chargen", stage, seed, opp_type, swap_seats))
    cfg_ctrl, equip_ctrl, ult_ctrl = S.make_character("ctrl", "control", stage, chargen_rng)
    cfg_opp, equip_opp, ult_opp = S.make_character("opp", opp_type, stage, chargen_rng)
    configs = [cfg_opp, cfg_ctrl] if swap_seats else [cfg_ctrl, cfg_opp]
    state = new_battle(f"fatigue-{seed}", seed=seed, unit_configs=configs)
    ultimate_flags = {"ctrl": [False], "opp": [False]}
    side_ctrl = ("ctrl", equip_ctrl, ult_ctrl, S.POLICIES["burst"])
    side_opp = ("opp", equip_opp, ult_opp, S.POLICIES["burst"])
    action_rng = random.Random(("fatigue-actions", stage, seed, opp_type, swap_seats))
    provider = S.make_action_provider(side_ctrl, side_opp, action_rng, ultimate_flags)

    all_events = []
    rounds = 0
    fin_state = state
    while not fin_state.finished and fin_state.round <= S.MAX_ROUNDS:
        actions = provider(fin_state)
        fin_state, events, finished = resolve_round(fin_state, actions, seed=seed)
        all_events.extend(events)
        rounds += 1
        if finished:
            break
    if not fin_state.finished:
        alive = [u for u in fin_state.units.values() if u.alive]
        if len(alive) > 1:
            ratios = {u.id: u.hp / u.max_hp for u in alive}
            best = max(ratios.values())
            leaders = [uid for uid, r in ratios.items() if r == best]
            fin_state.winner = leaders[0] if len(leaders) == 1 else None
        fin_state.finished = True
    return all_events, rounds


def analyze_battle(events):
    """Return per-battle control-fatigue stats, unit-scoped by target id."""
    attempts_by_tier = Counter()
    hits_by_tier = Counter()
    lost_actions = defaultdict(int)     # target_id -> count of "stunned" full skips
    weakened_actions = defaultdict(int)  # target_id -> count of interrupts that landed pre-action
    hit_no_effect = 0
    immune_blocks = 0
    fatigue_resets = 0
    lost_action_rounds = defaultdict(set)  # target_id -> set of rounds where fully skipped

    interrupted_targets_this_round = defaultdict(set)  # round -> set of target_ids with will_be_interrupted

    for e in events:
        if e["type"] == "control_resolved":
            tier = e.get("target_fatigue_before", -1)
            attempts_by_tier[tier] += 1
            if tier >= 3:
                immune_blocks += 1
            if e["success"]:
                hits_by_tier[tier] += 1
        elif e["type"] == "will_be_interrupted":
            interrupted_targets_this_round[e["round"]].add(e["target"])
        elif e["type"] == "control_fatigue_reset":
            fatigue_resets += 1
        elif e["type"] == "stunned":
            lost_actions[e["source"]] += 1
            lost_action_rounds[e["source"]].add(e["round"])
        elif e["type"] == "interrupted":
            weakened_actions[e["source"]] += 1

    # "hit but no action lost": successful control_resolved not backed by
    # a will_be_interrupted (for interrupt-effect skills) and not a stun
    # (stun shows up as a separate "stunned" event on the target's own
    # turn, not as an extra control_resolved outcome).
    total_hits = sum(hits_by_tier.values())
    total_weakened = sum(weakened_actions.values())
    total_lost = sum(lost_actions.values())
    hit_no_effect = max(0, total_hits - total_weakened - total_lost)

    max_consecutive = {}
    for target, rounds_set in lost_action_rounds.items():
        if not rounds_set:
            continue
        rs = sorted(rounds_set)
        best = cur = 1
        for i in range(1, len(rs)):
            if rs[i] == rs[i - 1] + 1:
                cur += 1
                best = max(best, cur)
            else:
                cur = 1
        max_consecutive[target] = best

    return {
        "attempts_by_tier": attempts_by_tier, "hits_by_tier": hits_by_tier,
        "total_hits": total_hits, "hit_no_effect": hit_no_effect,
        "weakened_not_lost": total_weakened, "fully_lost": total_lost,
        "immune_blocks": immune_blocks, "fatigue_resets": fatigue_resets,
        "max_consecutive_lost": max(max_consecutive.values()) if max_consecutive else 0,
    }


def main():
    print("Control-fatigue supplementary histogram (dedicated re-simulation,")
    print("same code/params/seed conventions as run_phase2_suite.py)\n")
    for stage in STAGES:
        attempts_by_tier = Counter()
        hits_by_tier = Counter()
        total_hits = total_hit_no_effect = total_weakened = total_lost = 0
        immune_blocks = fatigue_resets = 0
        battles_with_1plus = battles_with_2plus = battles_with_3plus = 0
        n_battles = 0
        for opp_type in TYPES:
            for i in range(N_PER_MATCHUP):
                for swap in (False, True):
                    events, rounds = run_one(stage, i, opp_type, swap)
                    stats = analyze_battle(events)
                    n_battles += 1
                    for t, c in stats["attempts_by_tier"].items():
                        attempts_by_tier[t] += c
                    for t, c in stats["hits_by_tier"].items():
                        hits_by_tier[t] += c
                    total_hits += stats["total_hits"]
                    total_hit_no_effect += stats["hit_no_effect"]
                    total_weakened += stats["weakened_not_lost"]
                    total_lost += stats["fully_lost"]
                    immune_blocks += stats["immune_blocks"]
                    fatigue_resets += stats["fatigue_resets"]
                    if stats["max_consecutive_lost"] >= 1:
                        battles_with_1plus += 1
                    if stats["max_consecutive_lost"] >= 2:
                        battles_with_2plus += 1
                    if stats["max_consecutive_lost"] >= 3:
                        battles_with_3plus += 1

        print(f"=== Stage {stage} (n={n_battles} battles, control vs each of 5 types) ===")
        print("attempts by fatigue tier (0/1/2/3=immune):",
              {t: attempts_by_tier[t] for t in sorted(attempts_by_tier)})
        print("success rate by fatigue tier:")
        for t in sorted(attempts_by_tier):
            a = attempts_by_tier[t]
            h = hits_by_tier.get(t, 0)
            print(f"  tier {t}: {h}/{a} = {h/a:.1%}" if a else f"  tier {t}: n/a")
        print(f"\ncontrol hit total: {total_hits}")
        print(f"  hit but caused NO action loss (silence/slow/disarm, or interrupt landing "
              f"post-action): {total_hit_no_effect} ({total_hit_no_effect/total_hits:.1%} of hits)"
              if total_hits else "  n/a")
        print(f"  hit, weakened the action but did NOT fully skip it (interrupt pre-action): "
              f"{total_weakened} ({total_weakened/total_hits:.1%} of hits)" if total_hits else "  n/a")
        print(f"  hit, FULLY skipped the action (stun): {total_lost} "
              f"({total_lost/total_hits:.1%} of hits)" if total_hits else "  n/a")
        print(f"immune-tier blocks (attempts that could never land, tier>=3): {immune_blocks}")
        print(f"control_fatigue resets to 0 (after an immune round): {fatigue_resets}")
        print(f"battles where a unit fully lost >=1 consecutive action to control: "
              f"{battles_with_1plus}/{n_battles} ({battles_with_1plus/n_battles:.1%})")
        print(f"battles where a unit fully lost >=2 CONSECUTIVE actions: "
              f"{battles_with_2plus}/{n_battles} ({battles_with_2plus/n_battles:.1%})")
        print(f"battles where a unit fully lost >=3 CONSECUTIVE actions: "
              f"{battles_with_3plus}/{n_battles} ({battles_with_3plus/n_battles:.1%})")
        print()


if __name__ == "__main__":
    main()
