"""Core data structures for the battle engine.

Phase 1 scope: 1v1 only. No Flask, no persistence, no equipment, no
faction war, no fusion skills (fusion needs a team of 2+ and is out of
scope until Phase 3). See 斗罗五阵录 v0.5 for the full design.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Five martial-soul types, in counter-wheel order:
# control -> attack -> support -> defense -> special -> control (cycle)
TYPES = ("control", "attack", "support", "defense", "special")

SKILL_KINDS = ("basic", "damage", "control", "shield", "debuff", "heal", "focus", "cleanse", "protect", "repair")
CONTROL_EFFECTS = ("interrupt", "silence", "stun", "slow", "disarm")
TARGET_MODES = ("single_enemy", "single_ally", "all_enemies", "all_allies", "objective", "self")


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    type: str  # one of TYPES; the martial-soul type this skill belongs to
    kind: str  # one of SKILL_KINDS
    power: int  # skill power, used by damage/shield formulas
    soul_cost: int
    speed_mod: int  # added to SPD for this action's ordering only
    cooldown: int  # rounds before it can be used again (0 = no cooldown)
    ring_tier: int = 1  # 魂环阶级(1-5) this skill draws on, for overload checks.
    # A character holds up to 9 rings (see doc v0.7 section 05); each ring
    # -- not the character as a whole -- has its own age-tier, so overload
    # is a property of the SKILL being cast, not a single scalar on the
    # unit. "越级吸收" simply means the generated skill carries a higher
    # ring_tier than the character can comfortably bear yet.
    priority: int = 0  # tie-break priority when action speed is equal
    control_effect: Optional[str] = None  # for kind == "control"
    base_control_chance: float = 0.0  # for kind == "control"
    control_duration: int = 1  # rounds the control effect lasts
    is_basic_attack: bool = False

    # Phase 2.1 skill-package restructure: a "damage" kind skill can also
    # carry ONE secondary effect, making it a genuine hybrid rather than
    # needing a whole new kind per combination. Each type's win path now
    # runs through 2-3 skills that both progress the fight AND build
    # toward its own conversion mechanic, instead of 1 damage skill
    # bolted onto 3+ purely non-damage utility skills.
    secondary_control_effect: Optional[str] = None  # e.g. "slow"/"silence" on a damage skill
    secondary_control_chance: float = 0.0
    secondary_control_duration: int = 1
    grants_stack: bool = False  # this action also grants the caster 1 advantage_stack
    attached_shield_power: int = 0  # this action also grants the caster a shield (defense hybrids)

    # Phase 3A (team_resolver.py only -- the 1v1 resolver.py never reads
    # these, so this is additive and doesn't change any 1v1 behavior):
    target_mode: str = "single_enemy"  # who a skill can legally target
    charge_rounds: int = 0  # >0: a telegraphed multi-round wind-up (e.g. boss
    # "蓄力崩山") that a hard control landing on the caster cancels outright
    dispel_shield: bool = False  # a debuff/cleanse skill that can strip an
    # enemy's shield directly, not gated behind the 1v1 counter-relationship
    # pairing (PvE needs a reliable dispel tool for any type, not just
    # "support countering defense")

    def __post_init__(self) -> None:
        assert self.type in TYPES, f"unknown type {self.type!r}"
        assert self.kind in SKILL_KINDS, f"unknown kind {self.kind!r}"
        assert self.target_mode in TARGET_MODES, f"unknown target_mode {self.target_mode!r}"
        if self.kind == "control":
            assert self.control_effect in CONTROL_EFFECTS
        if self.secondary_control_effect is not None:
            assert self.secondary_control_effect in CONTROL_EFFECTS


@dataclass
class UnitConfig:
    """Static-ish starting configuration for a unit in a battle."""
    id: str
    name: str
    soul_type: str  # the unit's own five-classification type
    max_hp: int
    atk: int
    def_: int
    res: int
    spd: int
    power_level: int  # 魂力等级 (1-99), used for ring-overload calc
    ring_tier: int  # display-only "highest ring" summary; overload checks
    # use the acting Skill's own ring_tier instead (see Skill.ring_tier)
    max_soul: int = 100
    soul: Optional[int] = None  # defaults to max_soul if not given
    skills: List[str] = field(default_factory=list)  # skill ids available

    # Phase 3A: identity/allegiance/display are three separate concepts,
    # on purpose -- the Phase 2 seating bug was exactly this kind of
    # conflation (reusing one field to imply two things). `id` is the
    # permanent unit_id; `team_id` is who this unit fights for THIS
    # encounter (ally/enemy resolution reads ONLY this, never list order
    # or dict position); `faction_id` is which of the five real-world
    # factions this unit represents, for later scoring/attribution, and
    # has NO effect on battle mechanics. Seat/display position belongs to
    # a future UI layer and is never modeled here at all.
    team_id: str = ""
    faction_id: Optional[str] = None
    is_objective: bool = False  # an environment target (阵眼), not a fighter:
    # cannot gain soul, cannot act, not in speed ordering, "heal"-kind
    # skills reject it as a target (only "repair"-kind restores it),
    # failure/downgrade triggers at 0 durability instead of "defeated"

    def __post_init__(self) -> None:
        assert self.soul_type in TYPES
        if self.soul is None:
            self.soul = self.max_soul


@dataclass
class StatusEffect:
    kind: str  # "silence" | "stun" | "slow" | "disarm" | "def_down" | "spd_down"
    rounds_left: int
    magnitude: float = 0.0  # e.g. def_down percentage


@dataclass
class UnitState:
    id: str
    name: str
    soul_type: str
    max_hp: int
    hp: int
    atk: int
    def_: int
    res: int
    spd: int
    power_level: int
    ring_tier: int
    max_soul: int
    soul: int
    skills: List[str]
    shield: int = 0
    pending_shield_decay: bool = False
    cooldowns: Dict[str, int] = field(default_factory=dict)
    statuses: List[StatusEffect] = field(default_factory=list)
    control_fatigue: int = 0
    advantage_stacks: int = 0  # Phase 2.1: generic "进攻窗口" counter -- gained by
    # casting a shield/debuff skill or by a shield absorbing incoming damage,
    # consumed by the next damage-kind skill for a flat bonus. One integer,
    # no per-type branching; see resolver.py ADVANTAGE_STACK_CAP/BONUS_PER_STACK.
    alive: bool = True

    # Phase 3A team/objective/protect/charge state (team_resolver.py only)
    team_id: str = ""
    faction_id: Optional[str] = None
    is_objective: bool = False
    # Phase 3A protect: pre-registration and activation are deliberately
    # two different fields, not two phases of the same field, so a
    # protect skill can never take effect before its own initiative slot
    # (that would silently reintroduce "defense always goes first" as a
    # special case, bypassing the unified speed formula). pending_* is
    # bookkeeping computed once before the round's ordering loop runs
    # (who declared protecting whom, and who won if several did); it has
    # NO mechanical effect. active_protector_id is set only when that
    # protector's OWN action actually resolves at its speed-determined
    # slot -- only THEN does damage start redirecting.
    pending_protector_id: Optional[str] = None
    active_protector_id: Optional[str] = None
    charging_skill: Optional[str] = None
    charge_rounds_left: int = 0
    pending_target_mode: Optional[str] = None  # the charging skill's own
    # target_mode, snapshotted at charge-start so the resolver knows how
    # to resolve targets when the charge finally goes off

    @classmethod
    def from_config(cls, cfg: UnitConfig) -> "UnitState":
        return cls(
            id=cfg.id,
            name=cfg.name,
            soul_type=cfg.soul_type,
            max_hp=cfg.max_hp,
            hp=cfg.max_hp,
            atk=cfg.atk,
            def_=cfg.def_,
            res=cfg.res,
            spd=cfg.spd,
            power_level=cfg.power_level,
            ring_tier=cfg.ring_tier,
            max_soul=cfg.max_soul,
            soul=cfg.soul if cfg.soul is not None else cfg.max_soul,
            skills=list(cfg.skills),
            team_id=cfg.team_id,
            faction_id=cfg.faction_id,
            is_objective=cfg.is_objective,
        )

    def has_status(self, kind: str) -> bool:
        return any(s.kind == kind for s in self.statuses)

    def status_magnitude(self, kind: str) -> float:
        return sum(s.magnitude for s in self.statuses if s.kind == kind)


@dataclass
class Action:
    unit_id: str
    skill_id: str
    target_id: Optional[str] = None  # ignored for target_mode in
    # (all_enemies, all_allies, objective, self) -- resolver computes the
    # actual target list from the skill's own target_mode in that case


@dataclass
class BattleState:
    battle_id: str
    seed: int
    round: int
    units: Dict[str, UnitState]
    finished: bool = False
    winner: Optional[str] = None


@dataclass
class EncounterState:
    """Phase 3A multi-unit battle state (team_resolver.py). Separate from
    BattleState (1v1, resolver.py) rather than generalizing it in place --
    the 1v1 resolver's control-flow already has 16 passing tests pinned
    to its exact 2-unit assumptions; a parallel module avoids touching
    that surface while this gets built and tested independently."""
    battle_id: str
    seed: int
    round: int
    units: Dict[str, UnitState]
    finished: bool = False
    outcome: Optional[str] = None  # "success" | "failure" | None (ongoing)
