"""Per-generation rules: the single place that knows what exists in which gen.

Every validator asks `rules_for(gen)` instead of hard-coding generation checks, so adding
Gen 5+ later is a matter of adding one `GenRules` entry (plus new enum members).
"""

from dataclasses import dataclass
from types import MappingProxyType

from .enums import Generation, MoveCategory, PokemonType, SideCondition, Weather

_GEN1_TYPES = frozenset(PokemonType) - {
    PokemonType.DARK,
    PokemonType.STEEL,
    PokemonType.TYPELESS,
}
_GEN2_TYPES = frozenset(PokemonType) - {PokemonType.TYPELESS}

# Gens 1-3: physical/special is decided by the move's type, not per move.
PHYSICAL_TYPES_PRE_SPLIT = frozenset(
    {
        PokemonType.NORMAL,
        PokemonType.FIGHTING,
        PokemonType.FLYING,
        PokemonType.POISON,
        PokemonType.GROUND,
        PokemonType.ROCK,
        PokemonType.BUG,
        PokemonType.GHOST,
        PokemonType.STEEL,
        PokemonType.TYPELESS,
    }
)


@dataclass(frozen=True)
class GenRules:
    gen: Generation
    max_dex: int
    pokemon_types: frozenset[PokemonType]
    move_types: frozenset[PokemonType]
    has_items: bool
    has_abilities: bool
    has_natures: bool
    unified_special: bool  # Gen 1: one Special stat (SpA == SpD)
    physical_special_split: bool  # Gen 4+: category is per move
    iv_max: int  # DVs 0-15 in Gens 1-2, IVs 0-31 from Gen 3
    ev_max_per_stat: int  # Stat Exp 65535 in Gens 1-2, EVs 255 from Gen 3
    ev_max_total: int | None  # no total cap on Stat Exp
    damage_roll_count: int  # 217..255 -> 39 rolls (Gens 1-2); 85..100 -> 16 rolls (Gen 3+)
    weathers: frozenset[Weather]
    side_condition_max_layers: MappingProxyType  # SideCondition -> max layers (1 = on/off)


def _layers(d: dict[SideCondition, int]) -> MappingProxyType:
    return MappingProxyType(d)


_BASE_SC = {SideCondition.REFLECT: 1, SideCondition.LIGHT_SCREEN: 1, SideCondition.MIST: 1}
_GEN2_SC = _BASE_SC | {SideCondition.SAFEGUARD: 1, SideCondition.SPIKES: 1}
_GEN3_SC = _GEN2_SC | {SideCondition.SPIKES: 3}
_GEN4_SC = _GEN3_SC | {
    SideCondition.STEALTH_ROCK: 1,
    SideCondition.TOXIC_SPIKES: 2,
    SideCondition.TAILWIND: 1,
    SideCondition.LUCKY_CHANT: 1,
}

_W_GEN2 = frozenset({Weather.NONE, Weather.RAIN, Weather.SUN, Weather.SANDSTORM})

GEN_RULES: dict[Generation, GenRules] = {
    Generation.RBY: GenRules(
        gen=Generation.RBY, max_dex=151,
        pokemon_types=_GEN1_TYPES, move_types=_GEN1_TYPES,
        has_items=False, has_abilities=False, has_natures=False,
        unified_special=True, physical_special_split=False,
        iv_max=15, ev_max_per_stat=65535, ev_max_total=None, damage_roll_count=39,
        weathers=frozenset({Weather.NONE}), side_condition_max_layers=_layers(_BASE_SC),
    ),
    Generation.GSC: GenRules(
        gen=Generation.GSC, max_dex=251,
        pokemon_types=_GEN2_TYPES, move_types=frozenset(PokemonType),
        has_items=True, has_abilities=False, has_natures=False,
        unified_special=False, physical_special_split=False,
        iv_max=15, ev_max_per_stat=65535, ev_max_total=None, damage_roll_count=39,
        weathers=_W_GEN2, side_condition_max_layers=_layers(_GEN2_SC),
    ),
    Generation.ADV: GenRules(
        gen=Generation.ADV, max_dex=386,
        pokemon_types=_GEN2_TYPES, move_types=frozenset(PokemonType),
        has_items=True, has_abilities=True, has_natures=True,
        unified_special=False, physical_special_split=False,
        iv_max=31, ev_max_per_stat=255, ev_max_total=510, damage_roll_count=16,
        weathers=_W_GEN2 | {Weather.HAIL}, side_condition_max_layers=_layers(_GEN3_SC),
    ),
    Generation.DPP: GenRules(
        gen=Generation.DPP, max_dex=493,
        pokemon_types=_GEN2_TYPES, move_types=frozenset(PokemonType),
        has_items=True, has_abilities=True, has_natures=True,
        unified_special=False, physical_special_split=True,
        iv_max=31, ev_max_per_stat=255, ev_max_total=510, damage_roll_count=16,
        weathers=_W_GEN2 | {Weather.HAIL}, side_condition_max_layers=_layers(_GEN4_SC),
    ),
}


def rules_for(gen: Generation | int) -> GenRules:
    return GEN_RULES[Generation(gen)]


def category_for_type(move_type: PokemonType) -> MoveCategory:
    """Damage category of a non-status move in Gens 1-3."""
    if move_type in PHYSICAL_TYPES_PRE_SPLIT:
        return MoveCategory.PHYSICAL
    return MoveCategory.SPECIAL
