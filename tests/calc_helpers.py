"""Builders shared by the calculator tests."""

from poketrix.calc import compute_stats
from poketrix.dex import Dex
from poketrix.schemas import BattlePokemon, PokemonSet, Stat, StatSpread

DEX4 = Dex(4)


def battler(
    species, *, level=100, nature=None, ability=None, ivs=None, evs=None, boosts=None,
    status=None, hp=None, volatiles=(), moves=("tackle",), gen_dex=DEX4,
) -> BattlePokemon:
    """A BattlePokemon with a full known set; `hp` is the current HP (default: full)."""
    sp = gen_dex.species(species)
    known_set = PokemonSet(
        species=sp, level=level, moves=list(moves), nature=nature,
        ability=ability or sp.possible_abilities[0],
        spread=StatSpread(ivs=ivs or {}, evs=evs or {}),
    )
    max_hp = compute_stats(known_set)[Stat.HP]
    current = max_hp if hp is None else hp
    return BattlePokemon(
        species=sp, level=level, hp_fraction=current / max_hp, hp_current=current, hp_max=max_hp,
        status=status, boosts=boosts or {}, volatiles=set(volatiles), known_set=known_set,
    )
