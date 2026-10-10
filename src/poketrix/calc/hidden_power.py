"""Hidden Power's real type and power, derived from IVs (Gens 3-4)."""

from collections.abc import Mapping

from poketrix.schemas import Generation, PokemonType, Stat, rules_for

_TYPES = (
    PokemonType.FIGHTING, PokemonType.FLYING, PokemonType.POISON, PokemonType.GROUND,
    PokemonType.ROCK, PokemonType.BUG, PokemonType.GHOST, PokemonType.STEEL,
    PokemonType.FIRE, PokemonType.WATER, PokemonType.GRASS, PokemonType.ELECTRIC,
    PokemonType.PSYCHIC, PokemonType.ICE, PokemonType.DRAGON, PokemonType.DARK,
)
# Bit order used by the games: note Speed comes before the special stats.
_BIT_ORDER = (Stat.HP, Stat.ATK, Stat.DEF, Stat.SPE, Stat.SPA, Stat.SPD)


def hidden_power(gen: Generation | int, ivs: Mapping[Stat, int]) -> tuple[PokemonType, int]:
    """(type, base power 30-70) for the given IVs; a missing IV counts as 31."""
    rules = rules_for(gen)
    if not rules.has_natures:
        raise NotImplementedError(f"Gen {int(gen)} Hidden Power (from DVs) arrives with Task 03c")
    type_bits = power_bits = 0
    for bit, stat in enumerate(_BIT_ORDER):
        iv = ivs.get(stat, rules.iv_max)
        type_bits += (iv & 1) << bit
        power_bits += ((iv >> 1) & 1) << bit
    return _TYPES[type_bits * 15 // 63], power_bits * 40 // 63 + 30
