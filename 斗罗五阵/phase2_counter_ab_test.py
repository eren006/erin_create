"""Fixed-configuration counter-edge A/B causal test.

v2: fixed the same seating bug as run_phase2_suite.py -- no swap
boolean anywhere. To measure both seatings of an edge, this makes two
genuinely distinct calls with the type/policy arguments exchanged, and
reads win attribution from the actual left_type/right_type/winner
recorded on each result, never inferred.

Isolates the counter-mechanic bonus's own effect from loadout-sampling
noise via resolver.COUNTER_MECHANICS_ENABLED, a controlled switch that
changes nothing else about the battle.

For each of the 4 implemented edges, two fixed configs (reduced from
the requested three -- "反制配置" is not run this pass, flagged as a
follow-up, not silently dropped):

  standard : both sides on fixed loadouts, both burst AI
  mechanism: same fixed loadouts; the countering side's AI is weighted
             toward the skill that actually exercises the mechanic, and
             (where relevant) the countered side's AI is weighted
             toward the skill that creates the mechanic's precondition
"""
import random
import statistics

from battle import resolver
from battle.engine import new_battle
from battle.models import UnitConfig
from battle.resolver import resolve_round
import simulate as S

STAGE = 30
N = 800  # per DIRECTED seating (both directions run, each own N)

FIXED_LOADOUTS = {
    # Phase 2.1: control/support now include their designated "stable
    # damage" skill (see templates.CORE_DAMAGE_SKILL) -- previously both
    # had zero damage-capable skills in these fixed configs, so the
    # countering side in control->attack and support->defense could
    # never win regardless of the counter mechanic being tested.
    "control": ["control_t1_interrupt", "control_t3_interrupt_strong", "control_t6_rupture", "control_t4_stun"],
    "attack": ["attack_t3_burst", "attack_t2_heavy", "attack_t4_overpower", "attack_t1_quick"],
    "support": ["support_t2_ward", "support_t3_blight", "support_t6_judgment", "support_t5_ruin"],
    "defense": ["defense_t2_wall", "defense_t3_bastion", "defense_t2_counter", "defense_t5_retaliate"],
    "special": ["special_t2_mirage", "special_t3_snare", "special_t1_needle", "special_t4_eclipse"],
}

# (attacker_type, defender_type) -> (countering-side preferred skills, countered-side preferred skills)
EDGE_CONFIGS = {
    ("control", "attack"): (
        ["control_t1_interrupt", "control_t3_interrupt_strong"],
        ["attack_t3_burst", "attack_t4_overpower"],
    ),
    ("attack", "support"): (
        ["attack_t3_burst"],
        ["support_t2_ward"],  # MUST cast the shield for "+20% vs shielded" to ever matter
    ),
    ("support", "defense"): (
        ["support_t3_blight"],
        ["defense_t2_wall"],  # MUST raise a shield for support to have something to dispel
    ),
    ("defense", "special"): (
        None,  # defense benefits passively, no active mechanic action of its own
        ["special_t2_mirage", "special_t3_snare"],
    ),
}


def policy_prefer(preferred_ids, fallback_policy):
    def policy(unit, opp, usable):
        ids, weights = fallback_policy(unit, opp, usable)
        weights = list(weights)
        for i, sid in enumerate(ids):
            if sid in preferred_ids:
                weights[i] *= 6.0
        return ids, weights
    return policy


def make_fixed_unit(unit_id, soul_type, stage):
    p = S.STAGES[stage]
    skills = ["basic_attack"] + FIXED_LOADOUTS[soul_type] + ["guard_stance"]
    return UnitConfig(
        id=unit_id, name=unit_id, soul_type=soul_type,
        max_hp=int(S.BASE_HP * p["mult"]), atk=int(S.BASE_ATK * p["mult"]),
        def_=S.BASE_DEF, res=S.BASE_RES, spd=100,
        power_level=p["power_level"], ring_tier=1, skills=skills,
    ), FIXED_LOADOUTS[soul_type]


def run_one_directed(left_type, right_type, left_policy, right_policy, seed, mechanics_on):
    """left_type/right_type/left_policy/right_policy assigned DIRECTLY,
    no swap inference. resolver.COUNTER_MECHANICS_ENABLED must already
    be set by the caller."""
    cfg_left, equip_left = make_fixed_unit("left", left_type, STAGE)
    cfg_right, equip_right = make_fixed_unit("right", right_type, STAGE)
    state = new_battle(f"ab-{seed}", seed=seed, unit_configs=[cfg_left, cfg_right])
    ultimate_flags = {"left": [False], "right": [False]}
    side_left = ("left", equip_left, False, left_policy)
    side_right = ("right", equip_right, False, right_policy)
    action_rng = random.Random(("ab-actions", left_type, right_type, seed, mechanics_on))
    provider = S.make_action_provider(side_left, side_right, action_rng, ultimate_flags)

    fin_state = state
    all_events = []
    while not fin_state.finished and fin_state.round <= S.MAX_ROUNDS:
        actions = provider(fin_state)
        fin_state, events, finished = resolve_round(fin_state, actions, seed=seed)
        all_events.extend(events)
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
    return fin_state, all_events


def count_opportunity_trigger(atk_type, def_type, left_type, events):
    """left_type tells us which physical seat is playing the countering
    (atk_type) role in THIS directed call, read from actual assignment."
    """
    left_is_countering = (left_type == atk_type)
    opp = trig = 0
    countering_seat = "left" if left_is_countering else "right"
    countered_seat = "right" if left_is_countering else "left"
    for e in events:
        if (atk_type, def_type) == ("control", "attack"):
            if e["type"] == "control_resolved" and e["source"] == countering_seat:
                opp += 1
                if e["success"]:
                    trig += 1
        elif (atk_type, def_type) == ("attack", "support"):
            if e["type"] == "damage" and e["source"] == countering_seat:
                opp += 1
            if e["type"] == "counter_bonus":
                trig += 1
        elif (atk_type, def_type) == ("support", "defense"):
            if e["type"] == "debuff_applied" and e["source"] == countering_seat:
                opp += 1
            if e["type"] == "dispelled":
                trig += 1
        elif (atk_type, def_type) == ("defense", "special"):
            if e["type"] == "debuff_applied" and e["source"] == countered_seat:
                opp += 1
                if e.get("duration") == 1:
                    trig += 1
    return opp, trig


def run_edge_condition(atk_type, def_type, config_name, mechanics_on, n=N):
    left_pref, right_pref = EDGE_CONFIGS[(atk_type, def_type)]
    countering_policy = policy_prefer(left_pref, S.policy_burst) if (config_name == "mechanism" and left_pref) else S.policy_burst
    countered_policy = policy_prefer(right_pref, S.policy_burst) if (config_name == "mechanism" and right_pref) else S.policy_burst

    resolver.COUNTER_MECHANICS_ENABLED = mechanics_on
    try:
        wins_countering = 0
        decided = 0
        rounds = []
        opportunities = triggers = 0
        # two directed seatings, each with its own N, exactly like the
        # main suite -- no swap boolean, no inferred attribution
        for (lt, rt, lp, rp) in ((atk_type, def_type, countering_policy, countered_policy),
                                  (def_type, atk_type, countered_policy, countering_policy)):
            for i in range(n):
                fin_state, events = run_one_directed(lt, rt, lp, rp, seed=i, mechanics_on=mechanics_on)
                if fin_state.winner is not None:
                    decided += 1
                    winner_type = lt if fin_state.winner == "left" else rt
                    if winner_type == atk_type:
                        wins_countering += 1
                rounds.append(fin_state.round - 1)
                opp, trig = count_opportunity_trigger(atk_type, def_type, lt, events)
                opportunities += opp
                triggers += trig
        return {
            "win_rate": wins_countering / decided if decided else float("nan"),
            "decided": decided, "avg_rounds": statistics.mean(rounds),
            "opportunities": opportunities, "triggers": triggers,
        }
    finally:
        resolver.COUNTER_MECHANICS_ENABLED = True


def seating_regression_check():
    resolver.COUNTER_MECHANICS_ENABLED = True
    s1, _ = run_one_directed("control", "attack", S.policy_burst, S.policy_burst, seed=0, mechanics_on=True)
    assert s1.units["left"].soul_type == "control" and s1.units["right"].soul_type == "attack"
    s2, _ = run_one_directed("attack", "control", S.policy_burst, S.policy_burst, seed=0, mechanics_on=True)
    assert s2.units["left"].soul_type == "attack" and s2.units["right"].soul_type == "control"

    # A/B must differ ONLY in the flag: same seed, same types -> identical
    # setup, and the flag must actually move a real number (verified
    # directly here, not just trusted)
    _, ev_on = run_one_directed("control", "attack", S.policy_burst, S.policy_burst, seed=5, mechanics_on=True)
    _, ev_off = run_one_directed("control", "attack", S.policy_burst, S.policy_burst, seed=5, mechanics_on=False)
    chances_on = [e["final_chance"] for e in ev_on if e["type"] == "control_resolved"]
    chances_off = [e["final_chance"] for e in ev_off if e["type"] == "control_resolved"]
    assert chances_on and chances_off and chances_on[0] != chances_off[0], (
        "COUNTER_MECHANICS_ENABLED flag did not change control_resolved chance -- wiring broken"
    )
    print("seating_regression_check: PASSED "
          "(seat assignment correct both directions, A/B flag verified to change real behavior)")


def main():
    seating_regression_check()
    print("\nFixed-configuration counter-edge A/B test (stage", STAGE, ", N=", N, "per directed seating)")
    print("Reduced to 2 of the requested 3 configs (standard, mechanism) -- '反制配置' not run this pass.\n")
    for (atk_type, def_type) in EDGE_CONFIGS:
        print(f"=== {atk_type} -> {def_type} ===")
        for config_name in ("standard", "mechanism"):
            a = run_edge_condition(atk_type, def_type, config_name, mechanics_on=True)
            b = run_edge_condition(atk_type, def_type, config_name, mechanics_on=False)
            delta = a["win_rate"] - b["win_rate"]
            round_delta = a["avg_rounds"] - b["avg_rounds"]
            verdict = ""
            if abs(delta) < 0.01:
                verdict = " <-- mechanism has ~no measurable presence here"
            elif abs(delta) > 0.10:
                verdict = " <-- mechanism may be too strong"
            trigger_rate = a["triggers"] / a["opportunities"] if a["opportunities"] else float("nan")
            print(f"  [{config_name}] A(on)={a['win_rate']:.1%} (n={a['decided']}) "
                  f"B(off)={b['win_rate']:.1%} (n={b['decided']}) delta={delta:+.1%}  "
                  f"opportunities(A)={a['opportunities']} triggers(A)={a['triggers']} "
                  f"trigger_rate={trigger_rate:.1%}  "
                  f"avg_rounds A={a['avg_rounds']:.2f} B={b['avg_rounds']:.2f} (delta {round_delta:+.2f}){verdict}")
        print()


if __name__ == "__main__":
    main()
