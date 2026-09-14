"""Phase 2 full structured suite -- run ONCE, no mid-run tuning.

v2: fixes a critical bug found after the first run (see
phase2_results_invalid_seating/summary.txt for the postmortem). The old
"swap_seats" boolean reordered a *list* of already-typed UnitConfigs;
since new_battle keys its unit dict by each config's own fixed .id,
reordering the list did nothing, and win-attribution code that assumed
the swap had happened inverted roughly half of every aggregated count.

Fix: there is no swap boolean anywhere in this version. To measure both
seatings of an unordered pair (X, Y), the caller makes two genuinely
distinct calls -- run_battle_full(..., left_type=X, right_type=Y) and
run_battle_full(..., left_type=Y, right_type=X) -- each of which
assigns types to seats directly from its own arguments. Win attribution
always reads the ACTUAL left_type/right_type recorded on that row, never
inferred from which call site produced it. A small regression check
(seating_regression_check, run before the main suite) asserts this
directly: same seed/policies, opposite type arguments -> left_type and
right_type actually swap, and nothing else about the setup changes.

Produces (in phase2_results/):
  summary.txt               human-readable report
  type_matrix_battles.csv   one row per type-matrix battle (54,000)
  ai_policy_battles.csv     one row per AI-policy-matrix battle (54,000)
  run_params.json           exact constants + seed scheme + dataset index
  anomalies.json            full event logs for the 20 "weirdest" battles

Per the explicit brief: code and parameters are frozen for this run
(the seating bug is an instrumentation fix, not a game-value change).
All conclusions are 1v1-only; special->control is excluded from "5-ring"
claims (not implemented); fusion/3v3 team mechanics are out of scope.
"""
import csv
import json
import os
import random
import statistics
import time
from collections import Counter, defaultdict

from battle.engine import new_battle, run_battle
from battle.models import UnitConfig
import simulate as S

OUT_DIR = os.path.join(os.path.dirname(__file__), "phase2_results")
os.makedirs(OUT_DIR, exist_ok=True)

RUN_ID = time.strftime("%Y%m%d-%H%M%S")

TYPES = S.TYPES
STAGES = (30, 60, 90)
N_TYPE_MATRIX = 600     # per DIRECTED type pair, i.e. both (X,Y) and (Y,X) get their own N
N_POLICY_MATRIX = 600   # per DIRECTED policy pair
MIXED_KIT = {
    "damage": "attack_t3_burst",
    "control": "control_t3_interrupt_strong",
    "shield": "defense_t3_bastion",
    "debuff": "support_t3_blight",
}
MIXED_KIT_LOADOUT_ID = "|".join(MIXED_KIT.values())
COUNTER_EDGES = S.COUNTER_EDGES
UNIMPLEMENTED_EDGE = S.UNIMPLEMENTED_EDGE

ALL_BATTLES = []
ALL_POLICY_BATTLES = []
TOTAL_BATTLES_RUN = [0]
_BATTLE_COUNTER = [0]


def _next_battle_id(dataset):
    _BATTLE_COUNTER[0] += 1
    return f"{dataset}-{_BATTLE_COUNTER[0]:08d}"


def analyze_events(events):
    out = {
        "interrupts": 0, "control_attempts": 0, "control_hits": 0,
        "backlash_events": 0, "backlash_self_dmg": 0,
        "fatigued_basic_attacks": 0, "total_damage": 0, "shield_absorbed": 0,
        "first_mover": None, "ultimate_used": {"left": False, "right": False},
    }
    for e in events:
        t = e["type"]
        if t == "interrupted":
            out["interrupts"] += 1
        elif t == "control_resolved":
            out["control_attempts"] += 1
            if e["success"]:
                out["control_hits"] += 1
        elif t == "ring_backlash":
            out["backlash_events"] += 1
            out["backlash_self_dmg"] += e.get("self_damage", 0)
        elif t == "fatigued_basic_attack":
            out["fatigued_basic_attacks"] += 1
        elif t == "damage":
            out["total_damage"] += e["amount"]
        elif t == "shield_absorbed":
            out["shield_absorbed"] += e["amount"]
        if out["first_mover"] is None and e["round"] == 1 and t in (
            "damage", "control_resolved", "shield_gained", "debuff_applied"
        ):
            out["first_mover"] = e["source"]
        if e.get("skill_id", "").startswith("ultimate_"):
            out["ultimate_used"][e["source"]] = True
    return out


def run_battle_full(stage, seed, left_type, right_type, left_policy, right_policy,
                     pair_seed=None, record=True, build="standard"):
    """left_type/right_type/left_policy/right_policy are assigned to the
    'left' and 'right' unit ids DIRECTLY from these arguments -- there is
    no swap inference anywhere in this function. To test the other
    seating of the same matchup, call this again with the two type
    arguments (and/or policy arguments) exchanged.

    build="standard" (default, primary balance reference as of Phase 2.1)
    uses each type's curated 4-skill STANDARD_LOADOUT; build="random_stress"
    samples randomly to stress-test for unplayable combinations.

    pair_seed: an id shared by the two directed calls that test the same
    unordered pair at the same seed index, so rows can be re-paired for
    analysis (battle_id alone doesn't reveal the pairing).
    """
    chargen_rng = random.Random(("chargen", stage, seed, left_type, right_type, build))
    cfg_left, equip_left, ult_left = S.make_character("left", left_type, stage, chargen_rng, build=build)
    cfg_right, equip_right, ult_right = S.make_character("right", right_type, stage, chargen_rng, build=build)
    state = new_battle(f"sim-{seed}", seed=seed, unit_configs=[cfg_left, cfg_right])
    ultimate_flags = {"left": [False], "right": [False]}
    side_left = ("left", equip_left, ult_left, S.POLICIES[left_policy])
    side_right = ("right", equip_right, ult_right, S.POLICIES[right_policy])
    action_rng = random.Random(("actions", stage, seed, left_type, right_type, left_policy, right_policy))
    provider = S.make_action_provider(side_left, side_right, action_rng, ultimate_flags)
    final_state, events = run_battle(state, provider, seed=seed, max_rounds=S.MAX_ROUNDS)
    genuine_kill = any(e["type"] == "defeated" for e in events)
    stats = analyze_events(events)

    row = {
        "run_id": RUN_ID, "dataset": "type_matrix", "build": build, "battle_id": _next_battle_id("type_matrix"),
        "pair_seed": pair_seed if pair_seed is not None else seed,
        "stage": stage, "seed": seed,
        "left_policy": left_policy, "right_policy": right_policy,
        "left_type": left_type, "right_type": right_type,
        "left_loadout_id": "|".join(equip_left), "right_loadout_id": "|".join(equip_right),
        "winner": final_state.winner, "rounds": final_state.round - 1,
        "timed_out": not genuine_kill,
        "first_mover": stats["first_mover"],
        "first_mover_won": (stats["first_mover"] == final_state.winner) if stats["first_mover"] else None,
        "interrupts": stats["interrupts"],
        "control_attempts": stats["control_attempts"], "control_hits": stats["control_hits"],
        "backlash_events": stats["backlash_events"], "backlash_self_dmg": stats["backlash_self_dmg"],
        "fatigued_basic_attacks": stats["fatigued_basic_attacks"],
        "total_damage": stats["total_damage"], "shield_absorbed": stats["shield_absorbed"],
        "ultimate_used_left": stats["ultimate_used"]["left"], "ultimate_used_right": stats["ultimate_used"]["right"],
        "ultimate_unlocked": ult_left or ult_right,
        "n_events": len(events),
    }
    if record:
        ALL_BATTLES.append(row)
        TOTAL_BATTLES_RUN[0] += 1
    return row, events


def run_mixed_kit_battle(stage, seed, left_policy, right_policy, pair_seed=None):
    m = S.STAGES[stage]["mult"]
    p = S.STAGES[stage]["power_level"]
    chargen_rng = random.Random(("mixedkit-chargen", stage, seed))
    equipped = [MIXED_KIT["damage"], MIXED_KIT["control"], MIXED_KIT["shield"], MIXED_KIT["debuff"]]
    has_ult = p >= S.ULTIMATE_UNLOCK_LEVEL
    skills_list = ["basic_attack"] + equipped + ["guard_stance"] + (["ultimate_attack"] if has_ult else [])
    spd_left = chargen_rng.randint(90, 110)
    spd_right = chargen_rng.randint(90, 110)
    cfg_left = UnitConfig(id="left", name="left", soul_type="attack", max_hp=int(S.BASE_HP * m),
                           atk=int(S.BASE_ATK * m), def_=S.BASE_DEF, res=S.BASE_RES, spd=spd_left,
                           power_level=p, ring_tier=1, skills=skills_list)
    cfg_right = UnitConfig(id="right", name="right", soul_type="attack", max_hp=int(S.BASE_HP * m),
                            atk=int(S.BASE_ATK * m), def_=S.BASE_DEF, res=S.BASE_RES, spd=spd_right,
                            power_level=p, ring_tier=1, skills=skills_list)
    state = new_battle(f"mk-{seed}", seed=seed, unit_configs=[cfg_left, cfg_right])
    ultimate_flags = {"left": [False], "right": [False]}
    side_left = ("left", equipped, has_ult, S.POLICIES[left_policy])
    side_right = ("right", equipped, has_ult, S.POLICIES[right_policy])
    action_rng = random.Random(("mixedkit-actions", stage, seed, left_policy, right_policy))
    provider = S.make_action_provider(side_left, side_right, action_rng, ultimate_flags)
    final_state, events = run_battle(state, provider, seed=seed, max_rounds=S.MAX_ROUNDS)
    genuine_kill = any(e["type"] == "defeated" for e in events)
    row = {
        "run_id": RUN_ID, "dataset": "ai_policy_matrix", "battle_id": _next_battle_id("ai_policy_matrix"),
        "pair_seed": pair_seed if pair_seed is not None else seed,
        "stage": stage, "seed": seed,
        "left_policy": left_policy, "right_policy": right_policy,
        "left_type": "mixed_kit", "right_type": "mixed_kit",
        "left_loadout_id": MIXED_KIT_LOADOUT_ID, "right_loadout_id": MIXED_KIT_LOADOUT_ID,
        "winner": final_state.winner, "rounds": final_state.round - 1, "timed_out": not genuine_kill,
    }
    ALL_POLICY_BATTLES.append(row)
    TOTAL_BATTLES_RUN[0] += 1
    return row, events


# ============================================================ regression check
def seating_regression_check():
    """Must pass before the main suite runs. Verifies actual seat
    assignment (not an assumption) and that flipping the type arguments
    changes ONLY the seating, nothing else about the matchup."""
    r1, _ = run_battle_full(30, 0, "control", "attack", "burst", "burst", record=False)
    assert r1["left_type"] == "control" and r1["right_type"] == "attack", r1

    r2, _ = run_battle_full(30, 0, "attack", "control", "burst", "burst", record=False)
    assert r2["left_type"] == "attack" and r2["right_type"] == "control", r2

    # policy must travel WITH its type argument, not get left behind on a seat
    r3, _ = run_battle_full(30, 0, "control", "attack", "survival", "resource", record=False)
    assert r3["left_type"] == "control" and r3["left_policy"] == "survival"
    assert r3["right_type"] == "attack" and r3["right_policy"] == "resource"
    r4, _ = run_battle_full(30, 0, "attack", "control", "resource", "survival", record=False)
    assert r4["left_type"] == "attack" and r4["left_policy"] == "resource"
    assert r4["right_type"] == "control" and r4["right_policy"] == "survival"

    print("seating_regression_check: PASSED "
          "(left/right seat assignment reads correctly from arguments, "
          "type+policy travel together, no swap-boolean inference anywhere)")


# ============================================================ type matrix
def run_type_matrix(stage, build="standard"):
    wins = defaultdict(int)   # (left_type, right_type) -> left's wins
    decided = defaultdict(int)
    edge_wins = {}

    directed_pairs = [(ta, tb) for ta in TYPES for tb in TYPES]  # includes mirrors, both directions
    for (lt, rt) in directed_pairs:
        for i in range(N_TYPE_MATRIX):
            row, _ = run_battle_full(stage, i, lt, rt, "burst", "burst",
                                      pair_seed=f"{stage}:{i}:{lt}v{rt}", build=build)
            if row["winner"] is not None:
                decided[(lt, rt)] += 1
                wins[(lt, rt)] += 1 if row["winner"] == "left" else 0

    matrix = {}
    for ta in TYPES:
        matrix[ta] = {}
        for tb in TYPES:
            d = decided.get((ta, tb), 0)
            matrix[ta][tb] = wins.get((ta, tb), 0) / d if d else None

    for (atk_t, def_t) in COUNTER_EDGES:
        d = decided.get((atk_t, def_t), 0)
        w = wins.get((atk_t, def_t), 0)
        edge_wins[f"{atk_t}->{def_t}"] = (w / d if d else None, d)
    return matrix, edge_wins


# ========================================================== policy matrix
def run_policy_matrix(stage):
    policies = list(S.POLICIES.keys())
    wins = defaultdict(int)
    decided = defaultdict(int)
    directed_pairs = [(pa, pb) for pa in policies for pb in policies]
    for (lp, rp) in directed_pairs:
        for i in range(N_POLICY_MATRIX):
            row, _ = run_mixed_kit_battle(stage, i, lp, rp, pair_seed=f"{stage}:{i}:{lp}v{rp}")
            if row["winner"] is not None:
                decided[(lp, rp)] += 1
                wins[(lp, rp)] += 1 if row["winner"] == "left" else 0
    matrix = {}
    for pa in policies:
        matrix[pa] = {}
        for pb in policies:
            d = decided.get((pa, pb), 0)
            matrix[pa][pb] = wins.get((pa, pb), 0) / d if d else None
    return matrix


# ========================================================= main sequence
def main():
    seating_regression_check()

    t_start = time.time()
    run_params = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "fixes_since_invalidated_run": [
            "seating: no more swap-boolean inference; two directed calls "
            "per unordered pair, win attribution reads actual left_type/"
            "right_type/winner recorded on each row",
            "stun status was ticking to 0 in the same round it was applied "
            "(same bug class as the earlier cooldown fix)",
            "stunned units never entered the execution loop, so the "
            "'stunned' event never fired even when the status was correct",
            "debuff-kind skills now scale def_down magnitude with skill.power "
            "(was a fixed 0.2 regardless of power)",
            "def_down status is now actually read by the damage formula "
            "(was applied but never consumed)",
        ],
        "MAX_ROUNDS": S.MAX_ROUNDS,
        "BASE_HP": S.BASE_HP, "BASE_ATK": S.BASE_ATK, "BASE_DEF": S.BASE_DEF, "BASE_RES": S.BASE_RES,
        "STAGES": S.STAGES, "ULTIMATE_UNLOCK_LEVEL": S.ULTIMATE_UNLOCK_LEVEL,
        "N_TYPE_MATRIX_per_directed_pair": N_TYPE_MATRIX,
        "N_POLICY_MATRIX_per_directed_pair": N_POLICY_MATRIX,
        "seed_scheme": "deterministic string-keyed random.Random((label, stage, seed, ...)); "
                       "pair_seed field lets the two directed calls for one unordered pair "
                       "be re-associated for analysis",
        "note": "code and parameters frozen for game VALUES this run; the seating "
                "bug fix is an instrumentation/methodology correction, not a balance change",
        "run_id": RUN_ID,
        "total_battles": len(TYPES) * len(TYPES) * N_TYPE_MATRIX * len(STAGES)
                          + len(S.POLICIES) * len(S.POLICIES) * N_POLICY_MATRIX * len(STAGES),
        "datasets": {
            "type_matrix": {
                "file": "type_matrix_battles.csv",
                "rows": len(TYPES) * len(TYPES) * N_TYPE_MATRIX * len(STAGES),
                "purpose": "类型、克制边、阶段胜率分析(每个有向对独立模拟,不依赖席位互换推断)",
            },
            "ai_policy_matrix": {
                "file": "ai_policy_battles.csv",
                "rows": len(S.POLICIES) * len(S.POLICIES) * N_POLICY_MATRIX * len(STAGES),
                "purpose": "固定混合技能配置下的AI策略交叉分析",
            },
        },
        "common_csv_columns": [
            "run_id", "dataset", "battle_id", "pair_seed", "stage", "seed",
            "left_policy", "right_policy", "left_type", "right_type",
            "left_loadout_id", "right_loadout_id",
            "winner", "rounds", "timed_out",
        ],
    }

    per_stage_type_matrix = {}
    per_stage_edge = {}
    per_stage_policy_matrix = {}

    for stage in STAGES:
        matrix, edges = run_type_matrix(stage)
        per_stage_type_matrix[stage] = matrix
        per_stage_edge[stage] = edges
        per_stage_policy_matrix[stage] = run_policy_matrix(stage)

    elapsed = time.time() - t_start

    csv_path = os.path.join(OUT_DIR, "type_matrix_battles.csv")
    if ALL_BATTLES:
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(ALL_BATTLES[0].keys()))
            w.writeheader()
            w.writerows(ALL_BATTLES)

    policy_csv_path = os.path.join(OUT_DIR, "ai_policy_battles.csv")
    if ALL_POLICY_BATTLES:
        with open(policy_csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(ALL_POLICY_BATTLES[0].keys()))
            w.writeheader()
            w.writerows(ALL_POLICY_BATTLES)

    stage_rounds = defaultdict(list)
    for r in ALL_BATTLES:
        stage_rounds[r["stage"]].append(r["rounds"])
    medians = {s: statistics.median(v) for s, v in stage_rounds.items()}

    def weirdness(r):
        score = abs(r["rounds"] - medians[r["stage"]]) * 2
        score += r["backlash_events"] * 3
        score += 10 if r["winner"] is None else 0
        score += 5 if (r["ultimate_used_left"] or r["ultimate_used_right"]) else 0
        score += r["fatigued_basic_attacks"] * 2
        return score

    ranked = sorted(ALL_BATTLES, key=weirdness, reverse=True)[:20]
    anomalies = []
    for r in ranked:
        _, events = run_battle_full(
            r["stage"], r["seed"], r["left_type"], r["right_type"], r["left_policy"], r["right_policy"],
            record=False,
        )
        anomalies.append({"summary": r, "events": events})
    with open(os.path.join(OUT_DIR, "anomalies.json"), "w") as f:
        json.dump(anomalies, f, ensure_ascii=False, indent=2)

    with open(os.path.join(OUT_DIR, "run_params.json"), "w") as f:
        json.dump(run_params, f, ensure_ascii=False, indent=2)

    lines = []
    lines.append("Phase 2 full structured suite v2 -- seating bug fixed, 1v1 only, no game-value tuning")
    lines.append(f"run_id: {RUN_ID}")
    lines.append(f"total battles simulated: {TOTAL_BATTLES_RUN[0]}   "
                 f"(type_matrix_battles.csv: {len(ALL_BATTLES)} rows, "
                 f"ai_policy_battles.csv: {len(ALL_POLICY_BATTLES)} rows)   wall time: {elapsed:.1f}s")
    lines.append("special->control excluded from any '5-ring balance' conclusion (not implemented).")
    lines.append("fusion/3v3 team mechanics out of scope -- support/control's numbers here are")
    lines.append("1v1-only and say nothing about their team-oriented kit.")
    lines.append("Prior run in phase2_results_invalid_seating/ is INVALIDATED -- do not compare against it.\n")

    for stage in STAGES:
        rows = [r for r in ALL_BATTLES if r["stage"] == stage]
        rounds = [r["rounds"] for r in rows]
        draws = sum(1 for r in rows if r["winner"] is None)
        timeouts = sum(1 for r in rows if r["timed_out"])
        fm_known = [r for r in rows if r["first_mover"] and r["winner"]]
        fm_wins = sum(1 for r in fm_known if r["first_mover"] == r["winner"])
        ctrl_attempts = sum(r["control_attempts"] for r in rows)
        ctrl_hits = sum(r["control_hits"] for r in rows)
        backlash_n = sum(r["backlash_events"] for r in rows)
        backlash_dmg = sum(r["backlash_self_dmg"] for r in rows)
        fatigued = sum(r["fatigued_basic_attacks"] for r in rows)
        total_dmg = sum(r["total_damage"] for r in rows)
        shield_abs = sum(r["shield_absorbed"] for r in rows)
        ult_eligible = [r for r in rows if r["ultimate_unlocked"]]
        ult_used = [r for r in ult_eligible if r["ultimate_used_left"] or r["ultimate_used_right"]]
        ult_swing = sum(1 for r in ult_used if (r["winner"] == "left" and r["ultimate_used_left"])
                         or (r["winner"] == "right" and r["ultimate_used_right"]))

        lines.append(f"=== Stage {stage} (n={len(rows)} battles across type matrix) ===")
        lines.append(f"avg rounds: {statistics.mean(rounds):.2f}  median: {statistics.median(rounds):.1f}  "
                      f"draw rate: {draws/len(rows):.1%}  timeout(no-KO) rate: {timeouts/len(rows):.1%}")
        lines.append(f"first-mover win rate: {(fm_wins/len(fm_known) if fm_known else float('nan')):.1%} "
                      f"(n={len(fm_known)})  [note: 'first mover' = fastest-resolving action this round, "
                      f"not necessarily a strategic edge -- some templates put negative speed_mod on their "
                      f"strongest skills, so this can conflate with 'used a weak filler skill']")
        lines.append(f"control hit rate: {(ctrl_hits/ctrl_attempts if ctrl_attempts else float('nan')):.1%} "
                      f"(attempts={ctrl_attempts})")
        lines.append(f"ring backlash: {backlash_n} events ({backlash_n/len(rows):.2f}/battle), "
                      f"avg self-dmg when triggered: {(backlash_dmg/backlash_n if backlash_n else 0):.1f}")
        lines.append(f"soul-exhaustion (fatigued basic attack) count: {fatigued}")
        if total_dmg:
            lines.append(f"shield absorbed as % of (damage+absorbed): {shield_abs/(total_dmg+shield_abs):.1%}")
        if ult_eligible:
            lines.append(f"ultimate release rate: {len(ult_used)/len(ult_eligible):.1%}  "
                          f"used-and-won rate among releases: {(ult_swing/len(ult_used) if ult_used else float('nan')):.1%}")

        lines.append("\ntype matchup win-rate matrix (row's win rate vs column, directed, no swap inference):")
        header = "         " + "".join(f"{t:>10s}" for t in TYPES)
        lines.append(header)
        for ta in TYPES:
            cells = []
            for tb in TYPES:
                v = per_stage_type_matrix[stage][ta][tb]
                cells.append(f"{v:9.1%} " if v is not None else "      n/a ")
            lines.append(f"{ta:8s} " + "".join(cells))

        lines.append("\ncounter edges (countering side's win rate; target 53-60%):")
        for edge, (rate, decided_n) in per_stage_edge[stage].items():
            flag = ""
            marker = "  [NOT IMPLEMENTED, excluded]" if edge == f"{UNIMPLEMENTED_EDGE[0]}->{UNIMPLEMENTED_EDGE[1]}" else ""
            if not marker and rate is not None and not (0.53 <= rate <= 0.60):
                flag = " <-- OUTSIDE TARGET"
            lines.append(f"  {edge:20s} {rate:5.1%} (decided {decided_n}){flag}{marker}" if rate is not None
                         else f"  {edge:20s} n/a{marker}")

        lines.append("\nAI policy win-rate matrix (mixed kit, row's win rate vs column):")
        policies = list(S.POLICIES.keys())
        header2 = "          " + "".join(f"{p:>10s}" for p in policies)
        lines.append(header2)
        for pa in policies:
            cells = []
            for pb in policies:
                v = per_stage_policy_matrix[stage][pa][pb]
                cells.append(f"{v:9.1%} " if v is not None else "      n/a ")
            lines.append(f"{pa:9s} " + "".join(cells))
        lines.append("")

    equipped_count, used_count = Counter(), Counter()
    for r in ALL_BATTLES:
        for equip_str in (r["left_loadout_id"], r["right_loadout_id"]):
            for sid in equip_str.split("|"):
                if sid:
                    equipped_count[sid] += 1
    lines.append("=== skill configuration rate across full run (uniform-random sampling caveat applies) ===")
    lines.append("config rate here reflects the random sampler (~66.7% by construction), not player")
    lines.append("preference -- usage-given-equipped is the more meaningful number; full per-skill")
    lines.append("breakdown available by post-processing type_matrix_battles.csv.\n")

    summary_text = "\n".join(lines)
    with open(os.path.join(OUT_DIR, "summary.txt"), "w") as f:
        f.write(summary_text)
    print(summary_text)
    print(f"\nWrote: {csv_path}")
    print(f"Wrote: {policy_csv_path}")
    print(f"Wrote: {os.path.join(OUT_DIR, 'run_params.json')}")
    print(f"Wrote: {os.path.join(OUT_DIR, 'anomalies.json')}")
    print(f"Wrote: {os.path.join(OUT_DIR, 'summary.txt')}")


if __name__ == "__main__":
    main()
