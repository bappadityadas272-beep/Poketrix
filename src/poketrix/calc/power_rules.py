"""Building blocks for per-move base power rules, shared by every generation's engine.

Each engine owns a table `move id -> Rule`; the helpers here are the rules that recur.
"""

from collections.abc import Callable, Mapping, Sequence

from poketrix.schemas import PokemonType, Status

from .context import Context
from .engine import UnsupportedMoveError
from .hidden_power import hidden_power

Rule = Callable[[Context], int]

FACADE_STATUSES = frozenset({Status.PARALYSIS, Status.POISON, Status.TOXIC, Status.BURN})

# Moves no engine can evaluate from the information it is given.
UNSUPPORTED = {
    "beatup": "damage depends on the whole team",
    "triplekick": "each of its three hits has its own power and accuracy check",
    "magnitude": "its seven possible powers do not fit one roll list",
    "present": "its random power (or healing) does not fit one roll list",
    "trumpcard": "power depends on remaining PP, which is not tracked",
    "spitup": "power depends on Stockpile count, which is not tracked",
    "hiddenpower": "untyped Hidden Power: give the set IVs/DVs or use a typed Hidden Power",
}


def maximum_happiness(c: Context) -> int:
    """Return at maximum happiness (and Frustration at minimum), as the oracle assumes."""
    return 102


def scaled_by_user_hp(c: Context) -> int:
    """Eruption, Water Spout."""
    return max(1, c.move.base_power * c.attacker.hp // c.attacker.max_hp)


def stronger_at_low_hp(scale: int, steps: Sequence[tuple[int, int]]) -> Rule:
    """Flail, Reversal: `steps` are (highest HP fraction in `scale`ths, power) pairs."""

    def rule(c: Context) -> int:
        fraction = scale * c.attacker.hp // c.attacker.max_hp
        for limit, power in steps:
            if fraction <= limit:
                return power
        return 20

    return rule


def by_target_weight(c: Context) -> int:
    """Low Kick, Grass Knot."""
    weight = c.defender.pokemon.species.weight_kg
    for minimum, power in ((200, 120), (100, 100), (50, 80), (25, 60), (10, 40)):
        if weight >= minimum:
            return power
    return 20


def doubled_if(condition: Callable[[Context], bool]) -> Rule:
    return lambda c: c.move.base_power * (2 if condition(c) else 1)


def derives_hidden_power(c: Context) -> bool:
    """Listed IVs/DVs decide Hidden Power; without them a typed Hidden Power is taken as given."""
    return c.move.id.startswith("hiddenpower") and bool(c.attacker.pokemon.known_set.spread.ivs)


def derived_hidden_power(c: Context) -> tuple[PokemonType, int]:
    return hidden_power(c.gen, c.attacker.pokemon.known_set.spread.ivs)


def resolve_power(c: Context, rules: Mapping[str, Rule]) -> int:
    """The move's power before modifiers. 0 means the move fails (Fling with nothing to throw)."""
    move = c.move
    if derives_hidden_power(c):
        return derived_hidden_power(c)[1]
    if move.id in UNSUPPORTED:
        raise UnsupportedMoveError(UNSUPPORTED[move.id])
    rule = rules.get(move.id)
    if rule is not None:
        return rule(c)
    if move.base_power == 0:
        raise UnsupportedMoveError("variable-power move without a rule")
    return move.base_power
