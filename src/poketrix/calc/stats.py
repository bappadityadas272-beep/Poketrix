"""Stat formulas: a set's actual stats, stat stages, and in-battle HP."""

from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType

from poketrix.dex import load_natures
from poketrix.schemas import BattlePokemon, PokemonSet, Stat, rules_for

_STATS = tuple(Stat)
_DEFAULT_IV = 31
_DEFAULT_EV = 0


def compute_stats(pokemon_set: PokemonSet) -> Mapping[Stat, int]:
    """Actual stats of a set at its level, before stat stages. Cached; treat as read-only."""
    gen = pokemon_set.generation
    if not rules_for(gen).has_natures:
        raise NotImplementedError(f"Gen {int(gen)} stats (DVs / Stat Exp) arrive with Task 03c")
    base = pokemon_set.species.base_stats
    spread = pokemon_set.spread
    return _modern_stats(
        (base.hp, base.atk, base.def_, base.spa, base.spd, base.spe),
        pokemon_set.level,
        tuple(spread.ivs.get(s, _DEFAULT_IV) for s in _STATS),
        tuple(spread.evs.get(s, _DEFAULT_EV) for s in _STATS),
        pokemon_set.nature,
    )


@lru_cache(maxsize=4096)
def _modern_stats(
    base: tuple[int, ...], level: int, ivs: tuple[int, ...], evs: tuple[int, ...],
    nature_id: str | None,
) -> Mapping[Stat, int]:
    """Gens 3-4: IVs, EVs and natures."""
    plus, minus = _nature_effect(nature_id)
    stats: dict[Stat, int] = {}
    for stat, b, iv, ev in zip(_STATS, base, ivs, evs):
        core = (2 * b + iv + ev // 4) * level // 100
        if stat is Stat.HP:
            stats[stat] = 1 if b == 1 else core + level + 10  # base 1 = Shedinja
            continue
        percent = 100 + 10 * (stat is plus) - 10 * (stat is minus)
        stats[stat] = (core + 5) * percent // 100
    return MappingProxyType(stats)


def _nature_effect(nature_id: str | None) -> tuple[Stat | None, Stat | None]:
    if nature_id is None:
        return None, None
    try:
        nature = load_natures()[nature_id]
    except KeyError:
        raise ValueError(f"unknown nature {nature_id!r}") from None
    return nature.plus, nature.minus


def apply_stage(stat: int, stage: int) -> int:
    """Gens 3-4 stat stage: x(2+n)/2 for a boost, x2/(2-n) for a drop, floored."""
    if stage >= 0:
        return stat * (2 + stage) // 2
    return stat * 2 // (2 - stage)


def battle_stats(pokemon: BattlePokemon) -> Mapping[Stat, int]:
    if pokemon.known_set is None:
        raise ValueError(
            f"{pokemon.species.name} has no known_set: the calculator needs a full set "
            "(for an opponent, a set hypothesis)"
        )
    return compute_stats(pokemon.known_set)


def current_hp(pokemon: BattlePokemon, max_hp: int) -> int:
    """Exact HP when known, otherwise the displayed fraction of max HP (at least 1 if alive)."""
    if pokemon.hp_current is not None:
        return pokemon.hp_current
    if pokemon.fainted:
        return 0
    return max(1, int(pokemon.hp_fraction * max_hp + 0.5))
