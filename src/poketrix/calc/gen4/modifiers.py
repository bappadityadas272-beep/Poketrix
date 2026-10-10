"""Attack, Defense and damage modifiers from abilities, items, status and the field.

Each function is one stage of the formula. The order inside a stage, and which rules exclude
each other (`elif`), are the oracle's; changing them changes results by a point of damage.
"""

from poketrix.schemas import BoostStat, PokemonType, SideCondition, Stat, Status, Weather

from ..context import Context
from ..stats import apply_stage

_SOUL_DEW_USERS = frozenset({"latios", "latias"})
_HALVES_DEFENSE = frozenset({"explosion", "selfdestruct"})
_WEATHER_POWER = {  # (weather, move type) -> (numerator, denominator)
    (Weather.SUN, PokemonType.FIRE): (3, 2),
    (Weather.RAIN, PokemonType.WATER): (3, 2),
    (Weather.SUN, PokemonType.WATER): (1, 2),
    (Weather.RAIN, PokemonType.FIRE): (1, 2),
}
_SOLAR_BEAM_WEAKENERS = frozenset({Weather.RAIN, Weather.SANDSTORM, Weather.HAIL})


def _simple_stage(stat: int, stage: int) -> int:
    """Simple doubles the holder's stat stages."""
    return apply_stage(stat, max(-6, min(6, stage * 2)))


def attack(c: Context, crit: bool) -> int:
    attacker, physical = c.attacker, c.physical
    stat = Stat.ATK if physical else Stat.SPA
    value = attacker.stats[stat]
    stage = attacker.stage(BoostStat(stat.value))
    if c.defender.ability == "unaware":
        pass
    elif attacker.ability == "simple":
        value = _simple_stage(value, stage)
    elif stage > 0 or (stage < 0 and not crit):  # a critical hit ignores the attacker's drops
        value = apply_stage(value, stage)

    ability = attacker.ability
    sun_ability = "flowergift" if physical else "solarpower"
    sun_boosted = c.weather is Weather.SUN and ability == sun_ability
    guts = ability == "guts" and attacker.status is not None
    if physical and ability in ("hugepower", "purepower"):
        value *= 2
    elif sun_boosted or (physical and (ability == "hustle" or guts)):
        value = int(value * 1.5)
    elif physical and ability == "slowstart" and attacker.has_volatile("slowstart"):
        value //= 2

    item, species = attacker.item_id, attacker.species_id
    if item == ("choiceband" if physical else "choicespecs") or (
        not physical and item == "souldew" and species in _SOUL_DEW_USERS
    ):
        value = int(value * 1.5)
    elif (
        (item == "lightball" and species == "pikachu")
        or (item == "thickclub" and species in ("cubone", "marowak") and physical)
        or (item == "deepseatooth" and species == "clamperl" and not physical)
    ):
        value *= 2
    return value


def defense(c: Context, crit: bool) -> int:
    defender, physical = c.defender, c.physical
    stat = Stat.DEF if physical else Stat.SPD
    value = defender.stats[stat]
    stage = defender.stage(BoostStat(stat.value))
    if c.attacker.ability == "unaware":
        pass
    elif defender.ability == "simple":
        value = _simple_stage(value, stage)
    elif stage < 0 or (stage > 0 and not crit):  # a critical hit ignores the defender's boosts
        value = apply_stage(value, stage)

    marvel_scale = defender.ability == "marvelscale" and defender.status is not None and physical
    flower_gift = defender.ability == "flowergift" and c.weather is Weather.SUN and not physical
    if marvel_scale or flower_gift:
        value = int(value * 1.5)

    item, species = defender.item_id, defender.species_id
    if item == "souldew" and species in _SOUL_DEW_USERS and not physical:
        value = int(value * 1.5)
    elif (item == "deepseascale" and species == "clamperl" and not physical) or (
        item == "metalpowder" and species == "ditto" and physical
    ):
        value *= 2

    if c.weather is Weather.SANDSTORM and PokemonType.ROCK in defender.types and not physical:
        value = int(value * 1.5)
    if c.move.id in _HALVES_DEFENSE:
        value //= 2
    return max(1, value)


def is_burned(c: Context) -> bool:
    return c.physical and c.attacker.status is Status.BURN and c.attacker.ability != "guts"


def after_base_damage(base: int, c: Context, attacking: PokemonType, crit: bool) -> int:
    """Screens, weather, Flash Fire, the +2, the critical-hit multiplier and Life Orb."""
    screen = SideCondition.REFLECT if c.physical else SideCondition.LIGHT_SCREEN
    if not crit and screen in c.defender_conditions and c.move.id != "brickbreak":
        base //= 2
    numerator, denominator = _WEATHER_POWER.get((c.weather, attacking), (1, 1))
    if c.move.id == "solarbeam" and c.weather in _SOLAR_BEAM_WEAKENERS:
        denominator = 2
    base = base * numerator // denominator
    flash_fire = c.attacker.ability == "flashfire" and c.attacker.has_volatile("flashfire")
    if flash_fire and attacking is PokemonType.FIRE:
        base = int(base * 1.5)
    base += 2
    if crit:
        base *= 3 if c.attacker.ability == "sniper" else 2
    if c.attacker.item_id == "lifeorb":
        base = int(base * 1.3)
    return base


def stab(c: Context, attacking: PokemonType) -> float:
    if attacking not in c.attacker.types:
        return 1.0
    return 2.0 if c.attacker.ability == "adaptability" else 1.5


def resist_berry_applies(c: Context, attacking: PokemonType, multiplier: float) -> bool:
    item = c.defender.item
    if item is None or item.resists_type is not attacking:
        return False
    return multiplier > 1 or attacking is PokemonType.NORMAL  # Chilan Berry needs no weakness


def after_type_factors(c: Context, attacking: PokemonType, multiplier: float) -> list[float]:
    """Multipliers applied after STAB and type effectiveness, each floored in turn."""
    factors = []
    if c.defender.ability in ("filter", "solidrock") and multiplier > 1:
        factors.append(0.75)
    if c.attacker.item_id == "expertbelt" and multiplier > 1:
        factors.append(1.2)
    # Metronome (item) is treated as a first use: no boost.
    if c.attacker.ability == "tintedlens" and multiplier < 1:
        factors.append(2.0)
    if resist_berry_applies(c, attacking, multiplier):
        factors.append(0.5)
    return factors
