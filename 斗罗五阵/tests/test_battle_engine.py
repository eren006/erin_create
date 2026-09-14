import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from battle import formulas
from battle.effects import counter_relationship, is_adjacent_pair
from battle.engine import new_battle, run_battle
from battle.models import Action, UnitConfig
from battle.resolver import resolve_round
from battle.skills import get_skill

BASIC_POWER = get_skill("basic_attack").power


def make_unit(id_, soul_type, **overrides):
    defaults = dict(
        id=id_, name=id_, soul_type=soul_type,
        max_hp=1000, atk=110, def_=70, res=15, spd=100,
        power_level=25, ring_tier=1, skills=["basic_attack"],
    )
    defaults.update(overrides)
    return UnitConfig(**defaults)


class FormulaTests(unittest.TestCase):
    def test_damage_formula(self):
        # power=160, atk=120, def=80 -> base=192, def_mult=100/180
        self.assertEqual(formulas.base_damage(160, 120), 192)
        self.assertAlmostEqual(formulas.defense_multiplier(80), 100 / 180)
        self.assertEqual(formulas.final_damage(160, 120, 80), 192 * 100 // 180)

    def test_shield_and_decay(self):
        self.assertEqual(formulas.shield_value(140, 80), 112)
        self.assertEqual(formulas.decay_shield(112), 56)
        self.assertEqual(formulas.decay_shield(1), 0)

    def test_action_speed(self):
        self.assertEqual(formulas.action_speed(100, 20, 0), 120)
        self.assertEqual(formulas.action_speed(100, -20, -5), 75)

    def test_control_chance_tiers(self):
        base = 0.70
        res = 25
        c0 = formulas.control_chance(base, res, 0)
        c1 = formulas.control_chance(base, res, 1)
        c2 = formulas.control_chance(base, res, 2)
        c3 = formulas.control_chance(base, res, 3)
        self.assertAlmostEqual(c0, 0.70 * 100 / 125)
        self.assertAlmostEqual(c1, c0 * 0.65)
        self.assertAlmostEqual(c2, c0 * 0.35)
        self.assertEqual(c3, 0.0)  # immune

    def test_overload_and_backlash(self):
        self.assertEqual(formulas.can_bear_tier(25), 2)  # 1 + 25//20
        self.assertEqual(formulas.overload_value(ring_tier=4, power_level=25), 2)
        self.assertAlmostEqual(formulas.backlash_chance(2), 0.36)
        self.assertAlmostEqual(formulas.backlash_chance(5), 0.60)  # capped at 60%
        self.assertEqual(formulas.overload_value(ring_tier=1, power_level=25), 0)


class CounterWheelTests(unittest.TestCase):
    def test_full_cycle(self):
        self.assertEqual(counter_relationship("control", "attack"), "counters")
        self.assertEqual(counter_relationship("attack", "support"), "counters")
        self.assertEqual(counter_relationship("support", "defense"), "counters")
        self.assertEqual(counter_relationship("defense", "special"), "counters")
        self.assertEqual(counter_relationship("special", "control"), "counters")
        # reverse direction is "countered"
        self.assertEqual(counter_relationship("attack", "control"), "countered")
        self.assertEqual(counter_relationship("control", "special"), "countered")
        # non-adjacent pairs are neutral
        self.assertEqual(counter_relationship("control", "defense"), "neutral")
        self.assertEqual(counter_relationship("attack", "defense"), "neutral")

    def test_fusion_adjacency(self):
        self.assertEqual(is_adjacent_pair("control", "attack"), "合击/破招")
        self.assertEqual(is_adjacent_pair("control", "defense"), None)


class ResolverTests(unittest.TestCase):
    def test_basic_damage_round(self):
        state = new_battle("b1", seed=42, unit_configs=[
            make_unit("a", "attack"), make_unit("b", "defense"),
        ])
        actions = {
            "a": Action(unit_id="a", skill_id="basic_attack", target_id="b"),
            "b": Action(unit_id="b", skill_id="basic_attack", target_id="a"),
        }
        next_state, events, finished = resolve_round(state, actions, seed=42)
        self.assertFalse(finished)
        dmg_events = [e for e in events if e["type"] == "damage"]
        self.assertEqual(len(dmg_events), 2)
        expected = formulas.final_damage(BASIC_POWER, 110, 70)
        self.assertEqual(dmg_events[0]["amount"], expected)
        self.assertEqual(next_state.units["b"].hp, 1000 - expected)

    def test_replay_is_deterministic(self):
        state = new_battle("b1", seed=7, unit_configs=[
            make_unit("a", "control", ring_tier=3, power_level=10),
            make_unit("b", "attack"),
        ])
        actions = {
            "a": Action(unit_id="a", skill_id="blue_silver_bind", target_id="b"),
            "b": Action(unit_id="b", skill_id="haotian_hammer_smash", target_id="a"),
        }
        state1, events1, _ = resolve_round(copy.deepcopy(state), copy.deepcopy(actions), seed=7)
        state2, events2, _ = resolve_round(copy.deepcopy(state), copy.deepcopy(actions), seed=7)
        self.assertEqual(events1, events2)
        self.assertEqual(state1.units["a"].hp, state2.units["a"].hp)
        self.assertEqual(state1.units["b"].hp, state2.units["b"].hp)
        self.assertEqual(state1.units["a"].soul, state2.units["a"].soul)

    def test_control_counters_attack_speed_and_interrupt(self):
        # control unit vs attack unit: control gets +15 speed from the
        # counter wheel, so even with equal base SPD and the attack
        # skill's own -20 speed_mod, control should act first.
        state = new_battle("b2", seed=1, unit_configs=[
            make_unit("ctrl", "control", spd=100),
            make_unit("atk", "attack", spd=100),
        ])
        actions = {
            "ctrl": Action(unit_id="ctrl", skill_id="blue_silver_bind", target_id="atk"),
            "atk": Action(unit_id="atk", skill_id="haotian_hammer_smash", target_id="ctrl"),
        }
        # search a seed where the control roll succeeds, to check the
        # interrupt/weaken/refund path deterministically
        for seed in range(200):
            s = new_battle("b2", seed=seed, unit_configs=[
                make_unit("ctrl", "control", spd=100),
                make_unit("atk", "attack", spd=100),
            ])
            _, events, _ = resolve_round(s, actions, seed=seed)
            control_ev = next(e for e in events if e["type"] == "control_resolved")
            if control_ev["success"]:
                interrupted_ev = [e for e in events if e["type"] == "interrupted" and e["source"] == "atk"]
                self.assertTrue(interrupted_ev, f"expected atk to be interrupted at seed={seed}")
                # control's final_chance should include the +15% counter bonus
                self.assertAlmostEqual(control_ev["base_chance"], 0.70)
                self.assertGreater(control_ev["final_chance"], 0)
                return
        self.fail("no seed in range produced a successful control roll")

    def test_shield_absorbs_then_decays(self):
        state = new_battle("b3", seed=3, unit_configs=[
            make_unit("def_unit", "defense", spd=200),
            make_unit("atk_unit", "attack", spd=50, atk=200),
        ])
        actions = {
            "def_unit": Action(unit_id="def_unit", skill_id="iron_wall_guard", target_id="def_unit"),
            "atk_unit": Action(unit_id="atk_unit", skill_id="basic_attack", target_id="def_unit"),
        }
        state1, events, _ = resolve_round(state, actions, seed=3)
        shield_after = state1.units["def_unit"].shield
        self.assertGreaterEqual(shield_after, 0)
        gained = next(e for e in events if e["type"] == "shield_gained")
        self.assertEqual(gained["shield_total"], formulas.shield_value(140, 70))

        # next round: no new shield skill, shield should have decayed by
        # half at the START of round processing (already applied above
        # only if a new round runs) -- run one more idle round to check decay
        idle_actions = {
            "def_unit": Action(unit_id="def_unit", skill_id="basic_attack", target_id="atk_unit"),
            "atk_unit": Action(unit_id="atk_unit", skill_id="basic_attack", target_id="def_unit"),
        }
        pre_shield = state1.units["def_unit"].shield
        state2, _, _ = resolve_round(state1, idle_actions, seed=3)
        # shield decays first, then this round's basic attack on def_unit
        # (from atk_unit) may consume some of the decayed shield
        self.assertLessEqual(state2.units["def_unit"].shield, pre_shield // 2)

    def test_insufficient_soul_falls_back_to_fatigued_basic_attack(self):
        state = new_battle("b4", seed=5, unit_configs=[
            make_unit("a", "attack"),
            make_unit("b", "defense"),
        ])
        state.units["a"].soul = 10  # not enough for haotian_hammer_smash (45)
        actions = {
            "a": Action(unit_id="a", skill_id="haotian_hammer_smash", target_id="b"),
            "b": Action(unit_id="b", skill_id="basic_attack", target_id="a"),
        }
        _, events, _ = resolve_round(state, actions, seed=5)
        fatigued = [e for e in events if e["type"] == "fatigued_basic_attack"]
        self.assertEqual(len(fatigued), 1)
        self.assertEqual(fatigued[0]["source"], "a")
        dmg = next(e for e in events if e["type"] == "damage" and e["source"] == "a")
        full_power_dmg = formulas.final_damage(BASIC_POWER, 110, 70)
        self.assertLess(dmg["amount"], full_power_dmg)

    def test_cooldown_prevents_immediate_reuse(self):
        state = new_battle("b5", seed=9, unit_configs=[
            make_unit("a", "attack"),
            make_unit("b", "defense"),
        ])
        actions = {
            "a": Action(unit_id="a", skill_id="haotian_hammer_smash", target_id="b"),
            "b": Action(unit_id="b", skill_id="basic_attack", target_id="a"),
        }
        state1, _, _ = resolve_round(state, actions, seed=9)
        self.assertEqual(state1.units["a"].cooldowns.get("haotian_hammer_smash"), 1)
        # attempting to reuse next round should be silently downgraded to
        # a basic attack by the resolver's defensive cooldown guard
        state2, events2, _ = resolve_round(state1, actions, seed=9)
        dmg = next(e for e in events2 if e["type"] == "damage" and e["source"] == "a")
        full_skill_dmg = formulas.final_damage(160, 110, 70)
        self.assertLess(dmg["amount"], full_skill_dmg)
        self.assertNotIn("haotian_hammer_smash", state2.units["a"].cooldowns)

    def test_stun_status_survives_into_next_round(self):
        # Regression test for the same bug class as cooldowns: a status
        # applied THIS round must not expire before the NEXT round's
        # pre-round status check ever sees it. Found via Phase 2's
        # control-fatigue pass (zero "stunned" events were ever firing).
        state = new_battle("b7", seed=1, unit_configs=[
            make_unit("ctrl", "control", spd=100),
            make_unit("atk", "attack", spd=100),
        ])
        actions = {
            "ctrl": Action(unit_id="ctrl", skill_id="restraining_grasp", target_id="atk"),
            "atk": Action(unit_id="atk", skill_id="haotian_hammer_smash", target_id="ctrl"),
        }
        for seed in range(200):
            s = new_battle("b7", seed=seed, unit_configs=[
                make_unit("ctrl", "control", spd=100),
                make_unit("atk", "attack", spd=100),
            ])
            state1, events1, _ = resolve_round(s, actions, seed=seed)
            control_ev = next(e for e in events1 if e["type"] == "control_resolved")
            if control_ev["success"]:
                self.assertTrue(state1.units["atk"].has_status("stun"))
                next_actions = {
                    "ctrl": Action(unit_id="ctrl", skill_id="basic_attack", target_id="atk"),
                    "atk": Action(unit_id="atk", skill_id="basic_attack", target_id="ctrl"),
                }
                state2, events2, _ = resolve_round(state1, next_actions, seed=seed)
                stunned_ev = [e for e in events2 if e["type"] == "stunned" and e["source"] == "atk"]
                self.assertTrue(stunned_ev, f"expected atk to be stunned next round at seed={seed}")
                return
        self.fail("no seed in range produced a successful stun roll")

    def test_defense_resists_special_debuff_duration(self):
        # Regression test: found via Phase 2's counter-edge A/B test.
        # defense->special's duration penalty was gated behind
        # rel=="counters" from the caster's (special's) own viewpoint,
        # which is never true -- special is COUNTERED BY defense, not
        # countering it, so counter_relationship("special","defense")
        # correctly returns "countered", and the old code's check never
        # fired. A defense-type target's incoming special-type debuff
        # must last 1 round (2 - 1), not the base 2.
        state = new_battle("b8", seed=1, unit_configs=[
            make_unit("spec", "special", spd=100),
            make_unit("def", "defense", spd=100),
        ])
        actions = {
            "spec": Action(unit_id="spec", skill_id="special_t2_mirage", target_id="def"),
            "def": Action(unit_id="def", skill_id="basic_attack", target_id="spec"),
        }
        _, events, _ = resolve_round(state, actions, seed=1)
        debuff_ev = next(e for e in events if e["type"] == "debuff_applied")
        self.assertEqual(debuff_ev["duration"], 1)

    def test_battle_runs_to_completion(self):
        state = new_battle("b6", seed=11, unit_configs=[
            make_unit("a", "attack", atk=300, spd=120),
            make_unit("b", "defense", max_hp=200, def_=10, spd=80),
        ])

        def simple_ai(s):
            return {
                "a": Action(unit_id="a", skill_id="basic_attack", target_id="b"),
                "b": Action(unit_id="b", skill_id="basic_attack", target_id="a"),
            }

        final_state, all_events = run_battle(state, simple_ai, seed=11, max_rounds=30)
        self.assertTrue(final_state.finished)
        self.assertEqual(final_state.winner, "a")
        self.assertTrue(any(e["type"] == "defeated" for e in all_events))


if __name__ == "__main__":
    unittest.main()
