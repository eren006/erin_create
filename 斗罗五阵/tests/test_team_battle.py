import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from battle.models import Action, EncounterState, UnitConfig, UnitState
from battle.team_resolver import resolve_team_round
from battle.skills import get_skill


def make_player(uid, soul_type="attack", **overrides):
    defaults = dict(
        id=uid, name=uid, soul_type=soul_type, team_id="players",
        max_hp=1000, atk=110, def_=70, res=15, spd=100,
        power_level=30, ring_tier=1, skills=["basic_attack"],
    )
    defaults.update(overrides)
    return UnitConfig(**defaults)


def make_npc(uid, soul_type="attack", **overrides):
    defaults = dict(
        id=uid, name=uid, soul_type=soul_type, team_id="npc",
        max_hp=2000, atk=110, def_=70, res=15, spd=100,
        power_level=30, ring_tier=1, skills=["basic_attack"],
    )
    defaults.update(overrides)
    return UnitConfig(**defaults)


def make_objective(uid, durability=1000):
    return UnitConfig(
        id=uid, name=uid, soul_type="defense", team_id="players", is_objective=True,
        max_hp=durability, atk=0, def_=0, res=0, spd=0,
        power_level=1, ring_tier=1, skills=[],
    )


def encounter(*configs, seed=1):
    units = {c.id: UnitState.from_config(c) for c in configs}
    return EncounterState(battle_id="t", seed=seed, round=1, units=units)


class OrderingAndTargetingTests(unittest.TestCase):
    def test_three_unit_action_order_is_stable_and_deterministic(self):
        state = encounter(
            make_player("p1", spd=100), make_player("p2", spd=100), make_player("p3", spd=100),
            make_npc("boss", spd=100),
        )
        actions = {
            "p1": Action("p1", "basic_attack", "boss"),
            "p2": Action("p2", "basic_attack", "boss"),
            "p3": Action("p3", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "p1"),
        }
        s1, e1 = resolve_team_round(encounter(
            make_player("p1", spd=100), make_player("p2", spd=100), make_player("p3", spd=100),
            make_npc("boss", spd=100),
        ), actions, seed=7)
        s2, e2 = resolve_team_round(encounter(
            make_player("p1", spd=100), make_player("p2", spd=100), make_player("p3", spd=100),
            make_npc("boss", spd=100),
        ), actions, seed=7)
        order1 = [e["source"] for e in e1 if e["type"] == "damage"]
        order2 = [e["source"] for e in e2 if e["type"] == "damage"]
        self.assertEqual(order1, order2)
        self.assertEqual(len(order1), 4)

    def test_group_skill_only_hits_legal_targets(self):
        state = encounter(
            make_player("p1"), make_player("p2"),
            make_npc("boss1"), make_npc("boss2"),
        )
        state.units["p1"].skills.append("attack_t3_burst")
        # give p1 a group skill by borrowing an all_enemies-tagged skill id
        from battle.models import Skill
        import battle.skills as skills_mod
        skills_mod.SKILLS["test_aoe"] = Skill(
            id="test_aoe", name="test aoe", type="attack", kind="damage",
            power=100, soul_cost=0, speed_mod=0, cooldown=0, target_mode="all_enemies",
        )
        skills_mod._REGISTRY = None  # bust the lazy-merge cache
        actions = {
            "p1": Action("p1", "test_aoe", None),
            "p2": Action("p2", "basic_attack", "boss1"),
            "boss1": Action("boss1", "basic_attack", "p1"),
            "boss2": Action("boss2", "basic_attack", "p1"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        dmg_from_p1 = {e["target"] for e in events if e["type"] == "damage" and e["source"] == "p1"}
        self.assertEqual(dmg_from_p1, {"boss1", "boss2"})  # never hits p2 (ally)

    def test_dead_unit_does_not_act(self):
        state = encounter(
            make_player("p1", atk=500), make_npc("boss", max_hp=50, spd=50),
        )
        actions = {
            "p1": Action("p1", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "p1"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        boss_acted = any(e["type"] == "damage" and e["source"] == "boss" for e in events)
        self.assertFalse(boss_acted)
        self.assertTrue(any(e["type"] == "defeated" and e["target"] == "boss" for e in events))


class ProtectTests(unittest.TestCase):
    def _setup(self, protector_spd, attacker_spd, protected_spd=100):
        return encounter(
            make_player("guard", spd=protector_spd, soul_type="defense",
                        skills=["basic_attack", "test_protect"]),
            make_player("carry", spd=protected_spd),
            make_npc("boss", spd=attacker_spd, atk=300),
        )

    @classmethod
    def setUpClass(cls):
        from battle.models import Skill
        import battle.skills as skills_mod
        skills_mod.SKILLS["test_protect"] = Skill(
            id="test_protect", name="test protect", type="defense", kind="protect",
            power=100, soul_cost=0, speed_mod=30, cooldown=0, target_mode="single_ally",
        )
        skills_mod._REGISTRY = None

    def test_hit_before_protector_acts_is_not_redirected(self):
        # attacker much faster than the protector -> damage lands before
        # protection ever activates this round
        state = self._setup(protector_spd=10, attacker_spd=200)
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        self.assertFalse(any(e["type"] == "damage_redirected" for e in events))
        hit = next(e for e in events if e["type"] == "damage" and e["target"] == "carry")
        self.assertEqual(hit["source"], "boss")

    def test_hit_after_protector_activates_is_redirected(self):
        # protector's speed_mod (+30) plus a high base spd puts it before
        # the (slower) attacker this round
        state = self._setup(protector_spd=100, attacker_spd=50)
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        activated = [e for e in events if e["type"] == "protect_activated"]
        self.assertTrue(activated, "protector should have activated before boss acts")
        redirect = next(e for e in events if e["type"] == "damage_redirected")
        self.assertEqual(redirect["original_target"], "carry")
        self.assertEqual(redirect["protector"], "guard")
        self.assertEqual(redirect["redirect_depth"], 1)
        self.assertEqual(redirect["redirected_damage"] + redirect["remaining_damage"],
                          redirect["original_damage"])

    def test_speed_mod_actually_moves_activation_timing(self):
        # same base spd as the attacker; only the skill's own +30 speed_mod
        # should be able to put the protector ahead
        state = self._setup(protector_spd=100, attacker_spd=100)
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        order_of_events = [e["type"] for e in events]
        activate_idx = next(i for i, e in enumerate(events) if e["type"] == "protect_activated")
        boss_dmg_idx = next(i for i, e in enumerate(events)
                             if e["type"] == "damage" and e["source"] == "boss")
        self.assertLess(activate_idx, boss_dmg_idx)

    def test_protector_dead_before_activation_fails_protection(self):
        state = self._setup(protector_spd=10, attacker_spd=200)
        state.units["guard"].hp = 1
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "guard"),  # kill the guard first
        }
        _, events = resolve_team_round(state, actions, seed=1)
        self.assertFalse(any(e["type"] == "protect_activated" for e in events))
        self.assertFalse(any(e["type"] == "damage_redirected" for e in events))

    def test_protector_dead_after_activation_stops_future_redirects(self):
        # protector activates, then dies to a first hit; a second hit the
        # same round on the protected ally must NOT redirect to a corpse
        state = encounter(
            make_player("guard", spd=200, soul_type="defense", max_hp=1,
                        skills=["basic_attack", "test_protect"]),
            make_player("carry", spd=100),
            make_npc("boss1", spd=150, atk=300),
            make_npc("boss2", spd=50, atk=300),
        )
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss1"),
            "boss1": Action("boss1", "basic_attack", "carry"),
            "boss2": Action("boss2", "basic_attack", "carry"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        redirects = [e for e in events if e["type"] == "damage_redirected"]
        self.assertEqual(len(redirects), 1)  # only the first hit redirected

    def test_target_invalid_falls_back_to_self_shield_not_wasted_or_retargeted(self):
        state = self._setup(protector_spd=10, attacker_spd=200)
        state.units["carry"].hp = 1
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),  # kills carry before guard's slot
        }
        _, events = resolve_team_round(state, actions, seed=1)
        fallback = [e for e in events if e["type"] == "protect_fallback_shield" and e["source"] == "guard"]
        self.assertTrue(fallback)
        self.assertEqual(fallback[0]["reason"], "target_invalid")

    def test_multiple_protectors_same_target_only_one_wins(self):
        state = encounter(
            make_player("guard1", spd=150, soul_type="defense", skills=["basic_attack", "test_protect"]),
            make_player("guard2", spd=120, soul_type="defense", skills=["basic_attack", "test_protect"]),
            make_player("carry", spd=50),
            make_npc("boss", spd=10, atk=300),
        )
        actions = {
            "guard1": Action("guard1", "test_protect", "carry"),
            "guard2": Action("guard2", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        activated = [e for e in events if e["type"] == "protect_activated"]
        self.assertEqual(len(activated), 1)
        self.assertEqual(activated[0]["source"], "guard1")  # higher speed_mod-boosted speed wins
        fallback = [e for e in events if e["type"] == "protect_fallback_shield" and e["source"] == "guard2"]
        self.assertTrue(fallback)
        self.assertEqual(fallback[0]["reason"], "lost_priority")

    def test_redirected_damage_does_not_chain(self):
        # guard protects carry; nobody protects guard -- redirected damage
        # to guard must apply directly, not look for a protector-of-guard
        state = self._setup(protector_spd=100, attacker_spd=50)
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        redirects = [e for e in events if e["type"] == "damage_redirected"]
        self.assertEqual(len(redirects), 1)
        self.assertEqual(redirects[0]["redirect_depth"], 1)

    def test_group_attack_checks_protection_per_target(self):
        from battle.models import Skill
        import battle.skills as skills_mod
        skills_mod.SKILLS["test_aoe2"] = Skill(
            id="test_aoe2", name="aoe2", type="attack", kind="damage",
            power=100, soul_cost=0, speed_mod=0, cooldown=0, target_mode="all_enemies",
        )
        skills_mod._REGISTRY = None
        state = encounter(
            make_player("guard", spd=100, soul_type="defense", skills=["basic_attack", "test_protect"]),
            make_player("carry1", spd=90),
            make_player("carry2", spd=80),
            make_npc("boss", spd=50, skills=["test_aoe2"], atk=200),
        )
        actions = {
            "guard": Action("guard", "test_protect", "carry1"),
            "carry1": Action("carry1", "basic_attack", "boss"),
            "carry2": Action("carry2", "basic_attack", "boss"),
            "boss": Action("boss", "test_aoe2", None),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        redirects = [e for e in events if e["type"] == "damage_redirected"]
        self.assertEqual(len(redirects), 1)
        self.assertEqual(redirects[0]["original_target"], "carry1")
        direct_hit_on_carry2 = [e for e in events if e["type"] == "damage" and e["target"] == "carry2"]
        self.assertTrue(direct_hit_on_carry2)

    def test_swapping_dict_insertion_order_does_not_change_attribution(self):
        cfgs = [
            make_player("guard", spd=100, soul_type="defense", skills=["basic_attack", "test_protect"]),
            make_player("carry", spd=50),
            make_npc("boss", spd=10, atk=300),
        ]
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),
        }
        s1, e1 = resolve_team_round(encounter(*cfgs, seed=3), actions, seed=3)
        s2, e2 = resolve_team_round(encounter(*reversed(cfgs), seed=3), actions, seed=3)
        r1 = next(e for e in e1 if e["type"] == "damage_redirected")
        r2 = next(e for e in e2 if e["type"] == "damage_redirected")
        self.assertEqual(r1["protector"], r2["protector"])
        self.assertEqual(r1["original_target"], r2["original_target"])

    def test_same_seed_same_actions_deterministic_replay(self):
        cfgs = lambda: [
            make_player("guard", spd=100, soul_type="defense", skills=["basic_attack", "test_protect"]),
            make_player("carry", spd=50),
            make_npc("boss", spd=10, atk=300),
        ]
        actions = {
            "guard": Action("guard", "test_protect", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "carry"),
        }
        s1, e1 = resolve_team_round(encounter(*cfgs(), seed=9), dict(actions), seed=9)
        s2, e2 = resolve_team_round(encounter(*cfgs(), seed=9), dict(actions), seed=9)
        self.assertEqual(e1, e2)
        self.assertEqual(s1.units["carry"].hp, s2.units["carry"].hp)
        self.assertEqual(s1.units["guard"].hp, s2.units["guard"].hp)


class ScoringSupportTests(unittest.TestCase):
    """Effective-value filters that scoring.py will lean on -- these
    verify the ENGINE emits the right raw facts, not the scorer itself
    (Phase 3C is a separate module that reads these events)."""

    def test_overheal_not_reported_as_effective(self):
        from battle.models import Skill
        import battle.skills as skills_mod
        skills_mod.SKILLS["test_heal"] = Skill(
            id="test_heal", name="test heal", type="support", kind="heal",
            power=500, soul_cost=0, speed_mod=0, cooldown=0, target_mode="single_ally",
        )
        skills_mod._REGISTRY = None
        state = encounter(
            make_player("healer", soul_type="support", skills=["basic_attack", "test_heal"]),
            make_player("carry", max_hp=1000),
            make_npc("boss"),
        )
        state.units["carry"].hp = 990  # nearly full, heal will overheal
        actions = {
            "healer": Action("healer", "test_heal", "carry"),
            "carry": Action("carry", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "healer"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        heal_ev = next(e for e in events if e["type"] == "heal_gained")
        self.assertLess(heal_ev["effective_amount"], heal_ev["amount"])
        self.assertEqual(heal_ev["effective_amount"], 10)

    def test_empty_shield_not_a_real_protection_event(self):
        # a shield with 0 absorption never emits shield_absorbed at all --
        # scoring reads shield_absorbed events, so a wasted/unused shield
        # simply produces none, which is the correct "no credit" signal
        state = encounter(
            make_player("tank", soul_type="defense", skills=["basic_attack"]),
            make_npc("boss"),
        )
        actions = {
            "tank": Action("tank", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "tank"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        self.assertFalse(any(e["type"] == "shield_absorbed" for e in events))

    def test_control_only_counts_when_it_actually_lands(self):
        from battle.models import Skill
        import battle.skills as skills_mod
        skills_mod.SKILLS["test_stun"] = Skill(
            id="test_stun", name="test stun", type="control", kind="control",
            power=0, soul_cost=0, speed_mod=0, cooldown=0, target_mode="single_enemy",
            control_effect="stun", base_control_chance=0.0,  # guaranteed miss
        )
        skills_mod._REGISTRY = None
        state = encounter(
            make_player("ctrl", soul_type="control", skills=["basic_attack", "test_stun"]),
            make_npc("boss"),
        )
        actions = {
            "ctrl": Action("ctrl", "test_stun", "boss"),
            "boss": Action("boss", "basic_attack", "ctrl"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        control_ev = next(e for e in events if e["type"] == "control_resolved")
        self.assertFalse(control_ev["success"])
        self.assertFalse(any(e["type"] == "stunned" for e in events))


class ObjectiveTests(unittest.TestCase):
    def test_objective_destroyed_triggers_failure(self):
        state = encounter(
            make_player("p1"), make_npc("boss", atk=2000),
            make_objective("gate", durability=100),
        )
        actions = {
            "p1": Action("p1", "basic_attack", "boss"),
            "boss": Action("boss", "basic_attack", "gate"),
        }
        _, events = resolve_team_round(state, actions, seed=1)
        state2, _ = resolve_team_round(encounter(
            make_player("p1"), make_npc("boss", atk=2000), make_objective("gate", durability=100),
        ), actions, seed=1)
        self.assertTrue(state2.finished)
        self.assertEqual(state2.outcome, "failure")

    def test_objective_rejects_heal_kind(self):
        from battle.models import Skill
        import battle.skills as skills_mod
        skills_mod.SKILLS["test_heal2"] = Skill(
            id="test_heal2", name="test heal2", type="support", kind="heal",
            power=100, soul_cost=0, speed_mod=0, cooldown=0, target_mode="single_ally",
        )
        skills_mod._REGISTRY = None
        state = encounter(
            make_player("healer", soul_type="support", skills=["basic_attack", "test_heal2"]),
            make_npc("boss"),
            make_objective("gate", durability=100),
        )
        state.units["gate"].hp = 50
        actions = {
            "healer": Action("healer", "test_heal2", "gate"),
            "boss": Action("boss", "basic_attack", "healer"),
        }
        next_state, events = resolve_team_round(state, actions, seed=1)
        self.assertTrue(any(e["type"] == "heal_rejected" for e in events))
        self.assertEqual(next_state.units["gate"].hp, 50)

    def test_objective_repaired_by_repair_kind(self):
        from battle.models import Skill
        import battle.skills as skills_mod
        skills_mod.SKILLS["test_repair"] = Skill(
            id="test_repair", name="test repair", type="support", kind="repair",
            power=200, soul_cost=0, speed_mod=0, cooldown=0, target_mode="objective",
        )
        skills_mod._REGISTRY = None
        state = encounter(
            make_player("fixer", soul_type="support", skills=["basic_attack", "test_repair"]),
            make_npc("boss"),
            make_objective("gate", durability=100),
        )
        state.units["gate"].hp = 50
        actions = {
            "fixer": Action("fixer", "test_repair", None),
            "boss": Action("boss", "basic_attack", "fixer"),
        }
        next_state, events = resolve_team_round(state, actions, seed=1)
        self.assertTrue(any(e["type"] == "repaired" for e in events))
        self.assertGreater(next_state.units["gate"].hp, 50)


if __name__ == "__main__":
    unittest.main()
