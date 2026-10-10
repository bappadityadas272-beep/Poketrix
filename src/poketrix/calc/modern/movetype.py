"""Gens 3-4: the move's effective type, its effectiveness, and the abilities that negate it.

Rules for things a generation lacks (Gravity, Scrappy, Iron Ball in Gen 3) never trigger there,
because the dex of that generation has no such ability, item or field state.
"""

from poketrix.schemas import MoveFlag, PokemonType, Weather

from ..context import Context
from ..power_rules import derived_hidden_power, derives_hidden_power
from ..typechart import in_type_order, type_factor

_ABSORBS = {  # defender ability -> move type it makes do nothing
    "flashfire": PokemonType.FIRE,
    "waterabsorb": PokemonType.WATER,
    "dryskin": PokemonType.WATER,
    "voltabsorb": PokemonType.ELECTRIC,
    "motordrive": PokemonType.ELECTRIC,
    "levitate": PokemonType.GROUND,
}
_GHOST_REVEALERS = frozenset({"foresight", "odorsleuth"})  # volatiles on the defender
_WEATHER_BALL_TYPE = {
    Weather.SUN: PokemonType.FIRE,
    Weather.RAIN: PokemonType.WATER,
    Weather.SANDSTORM: PokemonType.ROCK,
    Weather.HAIL: PokemonType.ICE,
}


def move_type(c: Context) -> PokemonType:
    move, item = c.move, c.attacker.item
    if c.attacker.ability == "normalize" and move.id != "struggle":
        return PokemonType.NORMAL
    if move.ignores_type_chart:
        return PokemonType.TYPELESS
    if move.id == "weatherball":
        return _WEATHER_BALL_TYPE.get(c.weather, move.type)
    if move.id == "judgment" and item is not None and item.plate_type is not None:
        return item.plate_type
    if move.id == "naturalgift" and item is not None and item.natural_gift_type is not None:
        return item.natural_gift_type
    if derives_hidden_power(c):
        return derived_hidden_power(c)[0]
    return move.type


def type_factors(c: Context, attacking: PokemonType) -> list[float]:
    """One factor per defender type, in canonical type order (each is floored separately)."""
    foreseen = not _GHOST_REVEALERS.isdisjoint(c.defender.pokemon.volatiles)
    ghost_revealed = c.attacker.ability == "scrappy" or foreseen
    factors = []
    for defending in in_type_order(c.defender.types):
        factor = type_factor(c.gen, attacking, defending)
        if (
            ghost_revealed and defending is PokemonType.GHOST
            and attacking in (PokemonType.NORMAL, PokemonType.FIGHTING)
        ) or (c.gravity and defending is PokemonType.FLYING and attacking is PokemonType.GROUND):
            factor = 1.0
        factors.append(factor)
    # Iron Ball grounds its holder: a Ground move's immunity becomes neutral.
    if attacking is PokemonType.GROUND and c.defender.item_id == "ironball" and 0.0 in factors:
        factors[factors.index(0.0)] = 1.0
    return factors


def blocked_by_ability(c: Context, attacking: PokemonType, multiplier: float) -> bool:
    ability = c.defender.ability
    if ability == "wonderguard":
        # Typeless damage and (a Gen 4 glitch) Fire Fang get through Wonder Guard.
        typeless = attacking is PokemonType.TYPELESS
        return multiplier <= 1 and not typeless and c.move.id != "firefang"
    if ability == "soundproof":
        return MoveFlag.SOUND in c.move.flags
    if ability == "levitate" and (c.gravity or c.defender.item_id == "ironball"):
        return False
    return _ABSORBS.get(ability) is attacking
