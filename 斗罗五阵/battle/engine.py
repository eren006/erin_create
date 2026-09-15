"""Battle-level loop on top of resolver.resolve_round.

resolve_round is the real architectural boundary (v0.5 section 11): pure,
stateless, one round at a time. run_battle is a convenience wrapper for
testing and for the Phase-2 auto-simulator -- a real multiplayer server
would call resolve_round directly once per submitted round instead.
"""
from typing import Callable, Dict, List, Tuple

from .models import Action, BattleState, UnitConfig, UnitState
from .resolver import resolve_round

# action_provider(state) -> {unit_id: Action}
ActionProvider = Callable[[BattleState], Dict[str, Action]]


def new_battle(battle_id: str, seed: int, unit_configs: List[UnitConfig]) -> BattleState:
    units = {cfg.id: UnitState.from_config(cfg) for cfg in unit_configs}
    return BattleState(battle_id=battle_id, seed=seed, round=1, units=units)


def run_battle(
    state: BattleState,
    action_provider: ActionProvider,
    seed: int,
    max_rounds: int = 15,
) -> Tuple[BattleState, List[dict]]:
    """Run rounds until finished or max_rounds is hit.

    v0.7 review: 1v1 needs a real answer for "neither side dies" (two
    defensive/utility loadouts can otherwise stall forever) rather than
    silently returning finished=False. At the round cap, decide by
    remaining HP%; an exact tie is a genuine draw (winner=None).
    """
    all_events: List[dict] = []
    while not state.finished and state.round <= max_rounds:
        actions = action_provider(state)
        state, events, finished = resolve_round(state, actions, seed)
        all_events.extend(events)
        if finished:
            break
    if not state.finished:
        alive = [u for u in state.units.values() if u.alive]
        state.finished = True
        if len(alive) <= 1:
            state.winner = alive[0].id if alive else None
        else:
            ratios = {u.id: u.hp / u.max_hp for u in alive}
            best = max(ratios.values())
            leaders = [uid for uid, r in ratios.items() if r == best]
            state.winner = leaders[0] if len(leaders) == 1 else None
    return state, all_events
