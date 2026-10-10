"""Hidden Power's real type and power, derived from IVs (Gens 3-4) or DVs (Gen 2)."""

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
    """(type, base power) for the given IVs or DVs; a missing value counts as the maximum."""
    rules = rules_for(gen)
    if not rules.has_items:
        raise ValueError("Hidden Power does not exist in Gen 1")
    if not rules.has_natures:
        dvs = (ivs.get(s, rules.iv_max) for s in (Stat.ATK, Stat.DEF, Stat.SPE, Stat.SPA))
        return _from_dvs(*dvs)
    type_bits = power_bits = 0
    for bit, stat in enumerate(_BIT_ORDER):
        iv = ivs.get(stat, rules.iv_max)
        type_bits += (iv & 1) << bit
        power_bits += ((iv >> 1) & 1) << bit
    return _TYPES[type_bits * 15 // 63], power_bits * 40 // 63 + 30


def _from_dvs(attack: int, defense: int, speed: int, special: int) -> tuple[PokemonType, int]:
    """Gen 2: type from the low bits of the Attack and Defense DVs, power 31-70."""
    top_bits = (special >> 3) + 2 * (speed >> 3) + 4 * (defense >> 3) + 8 * (attack >> 3)
    return _TYPES[4 * (attack % 4) + defense % 4], (5 * top_bits + special % 4) // 2 + 31
