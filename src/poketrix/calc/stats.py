"""Stat formulas: a set's actual stats, stat stages, and in-battle HP."""

from collections.abc import Mapping
from functools import lru_cache
from math import ceil, sqrt
from types import MappingProxyType

from poketrix.dex import load_natures
from poketrix.schemas import BattlePokemon, PokemonSet, Stat, gen1_2_hp_dv, rules_for

_STATS = tuple(Stat)
_DEFAULT_IV = 31
_DEFAULT_EV = 0


def compute_stats(pokemon_set: PokemonSet) -> Mapping[Stat, int]:
    """Actual stats of a set at its level, before stat stages. Cached; treat as read-only."""
    rules = rules_for(pokemon_set.generation)
    stats = pokemon_set.species.base_stats
    base = (stats.hp, stats.atk, stats.def_, stats.spa, stats.spd, stats.spe)
    spread = pokemon_set.spread
    if not rules.has_natures:
        dvs = {s: spread.ivs.get(s, rules.iv_max) for s in _STATS}
        dvs[Stat.HP] = gen1_2_hp_dv(dvs, rules.iv_max)  # the HP DV is derived from the others
        return _classic_stats(
            base, pokemon_set.level, tuple(dvs[s] for s in _STATS),
            tuple(spread.evs.get(s, rules.ev_max_per_stat) for s in _STATS),
        )
    return _modern_stats(
        base,
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


@lru_cache(maxsize=4096)
def _classic_stats(
    base: tuple[int, ...], level: int, dvs: tuple[int, ...], stat_exp: tuple[int, ...],
) -> Mapping[Stat, int]:
    """Gens 1-2: DVs (0-15) and Stat Exp (0-65535); a missing value counts as the maximum."""
    stats: dict[Stat, int] = {}
    for stat, b, dv, exp in zip(_STATS, base, dvs, stat_exp):
        exp_bonus = min(255, ceil(sqrt(exp))) // 4
        core = ((b + dv) * 2 + exp_bonus) * level // 100
        stats[stat] = core + level + 10 if stat is Stat.HP else core + 5
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


_CLASSIC_BOOST = (1, 1.5, 2, 2.5, 3, 3.5, 4)
_CLASSIC_DROP_PERCENT = (100, 66, 50, 40, 33, 28, 25)


def apply_stage_classic(stat: int, stage: int) -> int:
    """Gens 1-2 stat stage, kept between 1 and 999."""
    if stage >= 0:
        stat = int(stat * _CLASSIC_BOOST[stage])
    else:
        stat = stat * _CLASSIC_DROP_PERCENT[-stage] // 100
    return min(999, max(1, stat))


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
