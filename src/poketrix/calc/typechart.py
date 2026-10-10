"""Type effectiveness per generation, read from the dex snapshot's type chart."""

from collections.abc import Iterable

from poketrix.dex import load_type_chart
from poketrix.schemas import Generation, PokemonType

# Canonical order (the enum's declaration order). Damage engines apply a dual-typed defender's
# two factors in this order, because each factor is floored separately.
TYPE_ORDER = {t: i for i, t in enumerate(PokemonType)}


def type_factor(gen: Generation | int, move_type: PokemonType, defender_type: PokemonType) -> float:
    """Multiplier of one attacking type against one defending type. `???` is always neutral."""
    return load_type_chart(Generation(gen)).get(move_type, {}).get(defender_type, 1.0)


def in_type_order(types: Iterable[PokemonType]) -> list[PokemonType]:
    return sorted(types, key=TYPE_ORDER.__getitem__)


def effectiveness(
    gen: Generation | int, move_type: PokemonType, defender_types: Iterable[PokemonType]
) -> float:
    """Combined multiplier against all of the defender's types (0, 0.25, 0.5, 1, 2 or 4)."""
    result = 1.0
    for defender_type in defender_types:
        result *= type_factor(gen, move_type, defender_type)
    return result
