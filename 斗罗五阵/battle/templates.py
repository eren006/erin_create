"""Phase-2 simulation templates: 5 martial-soul types x 6 mechanic
templates each = 30. These are NOT the 140 final named skills from the
beast x mutation x absorption content pool (doc v0.7 section 05) --
they're generic mechanic shapes, used to find balance problems in the
underlying formulas before any content is written on top of them.

Each template's `ring_tier` (1-5) stands in for "which age-tier ring
this skill draws on" -- templates 1-2 per type are early/low-tier,
5-6 are late/high-tier, so a character equipping a template above what
their power_level can bear is the simulated equivalent of "越级吸收".
"""
from .models import Skill

TEMPLATES = {
    # ---- control: interrupt/silence/stun/slow/disarm, tiers 1-5 -------
    "control_t1_interrupt": Skill(
        id="control_t1_interrupt", name="[控制#1]牵制", type="control", kind="control",
        power=0, soul_cost=20, speed_mod=15, cooldown=2, ring_tier=1,
        control_effect="interrupt", base_control_chance=0.65,
    ),
    "control_t2_slow": Skill(
        id="control_t2_slow", name="[控制#2]缠绊", type="control", kind="control",
        power=0, soul_cost=22, speed_mod=10, cooldown=2, ring_tier=2,
        control_effect="slow", base_control_chance=0.75, control_duration=2,
    ),
    "control_t3_silence": Skill(
        id="control_t3_silence", name="[控制#3]封语", type="control", kind="control",
        power=0, soul_cost=28, speed_mod=15, cooldown=3, ring_tier=3,
        control_effect="silence", base_control_chance=0.60, control_duration=1,
    ),
    "control_t3_interrupt_strong": Skill(
        id="control_t3_interrupt_strong", name="[控制#4]强击破", type="control", kind="control",
        power=0, soul_cost=30, speed_mod=20, cooldown=3, ring_tier=3,
        control_effect="interrupt", base_control_chance=0.70,
    ),
    "control_t4_stun": Skill(
        id="control_t4_stun", name="[控制#5]震慑", type="control", kind="control",
        power=0, soul_cost=35, speed_mod=15, cooldown=3, ring_tier=4,
        control_effect="stun", base_control_chance=0.55, control_duration=1,
    ),
    "control_t5_disarm": Skill(
        id="control_t5_disarm", name="[控制#6]锁武", type="control", kind="control",
        power=0, soul_cost=40, speed_mod=10, cooldown=4, ring_tier=5,
        control_effect="disarm", base_control_chance=0.60, control_duration=2,
    ),
    # Phase 2.1: control had ZERO damage-capable skills in its entire
    # pool -- no follow-up meant successful control could never convert
    # into a kill regardless of any other mechanic. This is control's
    # designated "stable damage" skill (see CORE_DAMAGE_SKILL below);
    # its own kit is what capitalizes on the "exposed" window control's
    # hard-control effects create (see resolver.py EXPOSED_BONUS).
    "control_t6_rupture": Skill(
        id="control_t6_rupture", name="[控制#7]破绽突刺", type="control", kind="damage",
        power=125, soul_cost=28, speed_mod=5, cooldown=1, ring_tier=3,
    ),
    # Phase 2.1 restructure: control's real win path is 2 damage+control
    # hybrids (progress the fight AND set up "exposed") + a finisher that
    # capitalizes on exposed (generic bonus, see resolver.py) + a
    # self-protect + a resource skill. One damage skill alone (t6_rupture
    # above) wasn't enough throughput against attack's 4 damage options.
    "control_h1_pin": Skill(
        id="control_h1_pin", name="[控制混合#1]牵制打击", type="control", kind="damage",
        power=100, soul_cost=22, speed_mod=10, cooldown=1, ring_tier=1,
        secondary_control_effect="slow", secondary_control_chance=0.55, secondary_control_duration=2,
    ),
    "control_h2_breakthrough": Skill(
        id="control_h2_breakthrough", name="[控制混合#2]破招刺", type="control", kind="damage",
        power=115, soul_cost=28, speed_mod=10, cooldown=2, ring_tier=2,
        secondary_control_effect="silence", secondary_control_chance=0.50, secondary_control_duration=1,
    ),
    "control_finisher": Skill(
        id="control_finisher", name="[控制#终结]破绽追击", type="control", kind="damage",
        power=115, soul_cost=26, speed_mod=5, cooldown=1, ring_tier=3,
    ),
    "control_selfprotect": Skill(
        id="control_selfprotect", name="[控制#自保]疾影残像", type="control", kind="shield",
        power=90, soul_cost=20, speed_mod=20, cooldown=2, ring_tier=2,
    ),
    "control_focus": Skill(
        id="control_focus", name="[控制#资源]凝神", type="control", kind="focus",
        power=25, soul_cost=0, speed_mod=15, cooldown=1, ring_tier=1,
    ),

    # ---- attack: 4 progressing damage skills + self-protect + resource -
    # (was 6 pure-damage skills -- see doc changelog: no other type has
    # anywhere near this much guaranteed-damage throughput per rotation)
    "attack_t1_light": Skill(
        id="attack_t1_light", name="[攻击#1]轻击", type="attack", kind="damage",
        power=100, soul_cost=18, speed_mod=10, cooldown=0, ring_tier=1,
    ),
    "attack_guard": Skill(
        id="attack_guard", name="[攻击#自保]格挡步", type="attack", kind="shield",
        power=85, soul_cost=18, speed_mod=20, cooldown=2, ring_tier=1,
    ),
    "attack_t2_heavy": Skill(
        id="attack_t2_heavy", name="[攻击#3]重击", type="attack", kind="damage",
        power=140, soul_cost=30, speed_mod=-10, cooldown=1, ring_tier=2,
    ),
    "attack_t3_burst": Skill(
        id="attack_t3_burst", name="[攻击#4]爆发斩", type="attack", kind="damage",
        power=165, soul_cost=40, speed_mod=-15, cooldown=2, ring_tier=3,
    ),
    "attack_t4_overpower": Skill(
        id="attack_t4_overpower", name="[攻击#5]破军", type="attack", kind="damage",
        power=190, soul_cost=50, speed_mod=-20, cooldown=2, ring_tier=4,
    ),
    "attack_focus": Skill(
        id="attack_focus", name="[攻击#资源]蓄力凝气", type="attack", kind="focus",
        power=25, soul_cost=0, speed_mod=15, cooldown=1, ring_tier=1,
    ),

    # ---- support: 2 damage+buff hybrids + finisher + heal + resource ---
    "support_h1_glowstrike": Skill(
        id="support_h1_glowstrike", name="[辅助混合#1]魂光击", type="support", kind="damage",
        power=90, soul_cost=20, speed_mod=5, cooldown=1, ring_tier=1, grants_stack=True,
    ),
    "support_h2_radiance": Skill(
        id="support_h2_radiance", name="[辅助混合#2]光耀斩", type="support", kind="damage",
        power=100, soul_cost=26, speed_mod=0, cooldown=2, ring_tier=2, grants_stack=True,
    ),
    "support_finisher": Skill(
        id="support_finisher", name="[辅助#终结]辉光引爆", type="support", kind="damage",
        power=105, soul_cost=28, speed_mod=0, cooldown=1, ring_tier=3,
    ),
    "support_heal": Skill(
        id="support_heal", name="[辅助#治疗]回灵术", type="support", kind="heal",
        power=90, soul_cost=24, speed_mod=10, cooldown=2, ring_tier=2, grants_stack=True,
    ),
    "support_t2_ward": Skill(
        id="support_t2_ward", name="[辅助#强化]庇护", type="support", kind="shield",
        power=90, soul_cost=25, speed_mod=10, cooldown=2, ring_tier=2,
    ),
    "support_focus": Skill(
        id="support_focus", name="[辅助#资源]净心", type="support", kind="focus",
        power=25, soul_cost=0, speed_mod=15, cooldown=1, ring_tier=1,
    ),
    # kept for the random-stress-test pool (not in the standard build):
    "support_t1_weaken": Skill(
        id="support_t1_weaken", name="[辅助#1]弱化", type="support", kind="debuff",
        power=50, soul_cost=20, speed_mod=5, cooldown=2, ring_tier=1,
    ),
    "support_t2_curse": Skill(
        id="support_t2_curse", name="[辅助#2]诅咒", type="support", kind="debuff",
        power=65, soul_cost=25, speed_mod=5, cooldown=2, ring_tier=2,
    ),
    "support_t3_blight": Skill(
        id="support_t3_blight", name="[辅助#4]枯萎", type="support", kind="debuff",
        power=80, soul_cost=30, speed_mod=0, cooldown=3, ring_tier=3,
    ),
    "support_t4_sap": Skill(
        id="support_t4_sap", name="[辅助#5]夺魂", type="support", kind="debuff",
        power=95, soul_cost=35, speed_mod=0, cooldown=3, ring_tier=4,
    ),
    "support_t5_ruin": Skill(
        id="support_t5_ruin", name="[辅助#6]崩解诅咒", type="support", kind="debuff",
        power=115, soul_cost=45, speed_mod=-5, cooldown=3, ring_tier=5,
    ),
    "support_t6_judgment": Skill(
        id="support_t6_judgment", name="[辅助#7]裁决之光", type="support", kind="damage",
        power=110, soul_cost=26, speed_mod=0, cooldown=1, ring_tier=3,
    ),

    # ---- defense: mostly shields, a couple of retaliatory hits --------
    "defense_t1_guard": Skill(
        id="defense_t1_guard", name="[防御#1]守卫", type="defense", kind="shield",
        power=90, soul_cost=20, speed_mod=25, cooldown=1, ring_tier=1,
    ),
    "defense_t2_wall": Skill(
        id="defense_t2_wall", name="[防御#2]铁壁", type="defense", kind="shield",
        power=120, soul_cost=28, speed_mod=30, cooldown=2, ring_tier=2,
    ),
    "defense_t2_counter": Skill(
        id="defense_t2_counter", name="[防御#3]反击刺", type="defense", kind="damage",
        power=90, soul_cost=22, speed_mod=20, cooldown=1, ring_tier=2,
    ),
    "defense_t3_bastion": Skill(
        id="defense_t3_bastion", name="[防御#4]壁垒", type="defense", kind="shield",
        power=150, soul_cost=35, speed_mod=30, cooldown=2, ring_tier=3,
    ),
    "defense_t4_bulwark": Skill(
        id="defense_t4_bulwark", name="[防御#5]金刚护体", type="defense", kind="shield",
        power=180, soul_cost=45, speed_mod=30, cooldown=3, ring_tier=4,
    ),
    "defense_t5_retaliate": Skill(
        id="defense_t5_retaliate", name="[防御#6]天罚反震", type="defense", kind="damage",
        power=150, soul_cost=45, speed_mod=15, cooldown=3, ring_tier=5,
    ),
    # Phase 2.1: defense already had 2 pure-damage skills, but its win
    # path should be "tank hits -> build 守势 (advantage_stacks from
    # shield absorption) -> bigger counter", so give it damage skills
    # that ALSO grant a shield on the way in, not just a shield OR a hit.
    "defense_h1_shieldbash": Skill(
        id="defense_h1_shieldbash", name="[防御混合#1]盾击", type="defense", kind="damage",
        power=95, soul_cost=22, speed_mod=15, cooldown=1, ring_tier=1, attached_shield_power=60,
    ),
    "defense_h2_bulwarkstrike": Skill(
        id="defense_h2_bulwarkstrike", name="[防御混合#2]壁垒斩", type="defense", kind="damage",
        power=105, soul_cost=28, speed_mod=15, cooldown=2, ring_tier=2, attached_shield_power=50,
    ),
    "defense_finisher": Skill(
        id="defense_finisher", name="[防御#终结]山崩反震", type="defense", kind="damage",
        power=115, soul_cost=28, speed_mod=10, cooldown=1, ring_tier=3,
    ),
    "defense_focus": Skill(
        id="defense_focus", name="[防御#资源]调息", type="defense", kind="focus",
        power=25, soul_cost=0, speed_mod=20, cooldown=1, ring_tier=1,
    ),

    # ---- special: mixed damage/debuff, hidden-flavour, tiers 1-5 ------
    "special_t1_needle": Skill(
        id="special_t1_needle", name="[特殊#1]毒针", type="special", kind="damage",
        power=85, soul_cost=22, speed_mod=5, cooldown=1, ring_tier=1,
    ),
    "special_t2_mirage": Skill(
        id="special_t2_mirage", name="[特殊#2]幻影步", type="special", kind="debuff",
        power=55, soul_cost=25, speed_mod=10, cooldown=2, ring_tier=2,
    ),
    "special_t3_venom": Skill(
        id="special_t3_venom", name="[特殊#3]腐蚀之毒", type="special", kind="damage",
        power=120, soul_cost=32, speed_mod=0, cooldown=2, ring_tier=3,
    ),
    "special_t3_snare": Skill(
        id="special_t3_snare", name="[特殊#4]暗影陷阱", type="special", kind="debuff",
        power=85, soul_cost=30, speed_mod=0, cooldown=2, ring_tier=3,
    ),
    "special_t4_eclipse": Skill(
        id="special_t4_eclipse", name="[特殊#5]蚀月", type="special", kind="damage",
        power=160, soul_cost=42, speed_mod=-5, cooldown=3, ring_tier=4,
    ),
    "special_t5_oblivion": Skill(
        id="special_t5_oblivion", name="[特殊#6]忘忧蛊", type="special", kind="debuff",
        power=140, soul_cost=50, speed_mod=-5, cooldown=3, ring_tier=5,
    ),
    # Phase 2.1: special had 3 damage + 3 mark/debuff already (a real win
    # path existed) but zero self-protect or resource skill.
    "special_selfprotect": Skill(
        id="special_selfprotect", name="[特殊#自保]虚影屏障", type="special", kind="shield",
        power=90, soul_cost=22, speed_mod=15, cooldown=2, ring_tier=2,
    ),
    "special_focus": Skill(
        id="special_focus", name="[特殊#资源]潜行蓄能", type="special", kind="focus",
        power=25, soul_cost=0, speed_mod=15, cooldown=1, ring_tier=1,
    ),
}

TEMPLATES_BY_TYPE = {
    t: [tid for tid, s in TEMPLATES.items() if s.type == t]
    for t in ("control", "attack", "support", "defense", "special")
}

# Phase 2.1: each type's designated "stable damage" skill (v0.7 review's
# minimum-loadout recommendation). Character generation guarantees this
# is always equipped, not left to random 4-of-N sampling -- control and
# support only got ONE damage-capable template each, so a random draw
# could otherwise still leave a character with zero damage output.
CORE_DAMAGE_SKILL = {
    "control": "control_h1_pin",
    "attack": "attack_t2_heavy",
    "support": "support_h1_glowstrike",
    "defense": "defense_h1_shieldbash",
    "special": "special_t1_needle",
}

# Phase 2.1: "standard build" -- the curated 4-skill loadout a real
# player would actually pick (2 skills that progress the fight, 1 core
# skill defining the type's identity, 1 self-protect/resource skill).
# This is now the PRIMARY balance reference; plain random-4-of-pool
# sampling (still available via TEMPLATES_BY_TYPE) is a secondary
# stress test for "does some combination leave a character unable to
# deal damage at all", not the main balance signal.
STANDARD_LOADOUT = {
    "control": ["control_h1_pin", "control_finisher", "control_t3_interrupt_strong", "control_selfprotect"],
    "attack": ["attack_t1_light", "attack_t2_heavy", "attack_t3_burst", "attack_t4_overpower"],
    "support": ["support_h1_glowstrike", "support_finisher", "support_heal", "support_focus"],
    "defense": ["defense_h1_shieldbash", "defense_finisher", "defense_t3_bastion", "defense_focus"],
    "special": ["special_t1_needle", "special_t4_eclipse", "special_t3_snare", "special_selfprotect"],
}

# Ultimate (武魂真身) templates -- unlocked at the 7th ring, at most one
# use per battle, one per type so every soul type has an endgame option.
ULTIMATES = {
    "ultimate_control": Skill(
        id="ultimate_control", name="[真身]天崩地陷", type="control", kind="control",
        power=0, soul_cost=70, speed_mod=25, cooldown=0, ring_tier=5,
        control_effect="stun", base_control_chance=0.75, control_duration=1,
    ),
    "ultimate_attack": Skill(
        id="ultimate_attack", name="[真身]九幽绝杀", type="attack", kind="damage",
        power=320, soul_cost=75, speed_mod=-10, cooldown=0, ring_tier=5,
    ),
    "ultimate_support": Skill(
        id="ultimate_support", name="[真身]万灵枯荣", type="support", kind="debuff",
        power=180, soul_cost=70, speed_mod=0, cooldown=0, ring_tier=5,
    ),
    "ultimate_defense": Skill(
        id="ultimate_defense", name="[真身]不灭金身", type="defense", kind="shield",
        power=280, soul_cost=70, speed_mod=30, cooldown=0, ring_tier=5,
    ),
    "ultimate_special": Skill(
        id="ultimate_special", name="[真身]终末蚀", type="special", kind="damage",
        power=260, soul_cost=75, speed_mod=0, cooldown=0, ring_tier=5,
    ),
}

# Universal actions available to every character regardless of type,
# occupying the shared "通用动作" slot (doc v0.7 section 07).
UNIVERSAL = {
    "guard_stance": Skill(
        id="guard_stance", name="护体架势", type="defense", kind="shield",
        power=60, soul_cost=10, speed_mod=25, cooldown=0, ring_tier=1,
    ),
}
