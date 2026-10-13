"""Who acts first when both Pokémon use a move: priority, then Speed, Trick Room reversing it.

Each generation's Speed rule is its engine's own (`modern.speed`, `classic.chance`); this module
only compares the two results. Both Pokémon need a `known_set`.
"""

from collections.abc import Callable

from poketrix.schemas import BattlePokemon, FieldState, Generation, Move

from .classic.chance import classic_speed
from .context import Context, Side, build_context
from .engine import NO_CONDITIONS, SideConditions
from .modern.speed import effective_speed

_SPEED: dict[Generation, Callable[[Side, Context], int]] = {
    Generation.RBY: lambda side, c: classic_speed(side),
    Generation.GSC: lambda side, c: classic_speed(side),
    Generation.ADV: effective_speed,
    Generation.DPP: effective_speed,
}


def acts_first_chance(
    ours: BattlePokemon, theirs: BattlePokemon, our_move: Move, their_priority: int = 0,
    field: FieldState | None = None,
    our_conditions: SideConditions = NO_CONDITIONS,
    their_conditions: SideConditions = NO_CONDITIONS,
) -> float:
    """Chance that `ours` acts before `theirs`: 1, 0, or 0.5 for a Speed tie."""
    if our_move.priority != their_priority:
        return 1.0 if our_move.priority > their_priority else 0.0
    c = build_context(ours, theirs, our_move, field or FieldState(), our_conditions,
                      their_conditions)
    speed = _SPEED[c.gen]
    mine, other = speed(c.attacker, c), speed(c.defender, c)
    if mine == other:
        return 0.5
    return 1.0 if (mine < other) == c.trick_room else 0.0
