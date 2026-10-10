"""Gen 3 Attack, Defense and damage modifiers, in the oracle's order (`@smogon/calc` gen3).

Unlike Gen 4, items and abilities change the Attack or Defense stat itself, before the stat
stage is applied, and the type-boosting items give 10%.
"""

from poketrix.schemas import BoostStat, PokemonType, SideCondition, Stat, Status, Weather

from ..context import Context
from ..stats import apply_stage

_SOUL_DEW_USERS = frozenset({"latios", "latias"})
_PINCH_ABILITY_TYPE = {
    "overgrow": PokemonType.GRASS,
    "blaze": PokemonType.FIRE,
    "torrent": PokemonType.WATER,
    "swarm": PokemonType.BUG,
}
_WEATHER_POWER = {  # (weather, move type) -> (numerator, denominator)
    (Weather.SUN, PokemonType.FIRE): (3, 2),
    (Weather.RAIN, PokemonType.WATER): (3, 2),
    (Weather.SUN, PokemonType.WATER): (1, 2),
    (Weather.RAIN, PokemonType.FIRE): (1, 2),
}
_SOLAR_BEAM_WEAKENERS = frozenset({Weather.RAIN, Weather.SANDSTORM, Weather.HAIL})


def modified_power(power: int, c: Context, attacking: PokemonType) -> int:
    attacker = c.attacker
    pinch = _PINCH_ABILITY_TYPE.get(attacker.ability) is attacking
    if pinch and attacker.hp * 3 <= attacker.max_hp:
        power = int(power * 1.5)
    return power


def _item_boosted_attack(value: int, c: Context, attacking: PokemonType) -> int:
    item = c.attacker.item
    if item is None:
        return value
    physical, species = c.physical, c.attacker.species_id
    boosts_struggle = c.move.id == "struggle" and item.boosts_type is PokemonType.NORMAL
    if item.id != "seaincense" and (item.boosts_type is attacking or boosts_struggle):
        return int(value * 1.1)
    if item.id == "seaincense" and attacking is PokemonType.WATER:
        return int(value * 1.05)
    if (physical and item.id == "choiceband") or (
        not physical and item.id == "souldew" and species in _SOUL_DEW_USERS
    ):
        return int(value * 1.5)
    if (
        (not physical and item.id == "deepseatooth" and species == "clamperl")
        or (not physical and item.id == "lightball" and species == "pikachu")
        or (physical and item.id == "thickclub" and species in ("cubone", "marowak"))
    ):
        return value * 2
    return value


def attack(c: Context, attacking: PokemonType, crit: bool) -> int:
    attacker, physical = c.attacker, c.physical
    stat = Stat.ATK if physical else Stat.SPA
    value = attacker.stats[stat]
    if physical and attacker.ability in ("hugepower", "purepower"):
        value *= 2
    value = _item_boosted_attack(value, c, attacking)
    if c.defender.ability == "thickfat" and attacking in (PokemonType.FIRE, PokemonType.ICE):
        value //= 2
    guts = attacker.ability == "guts" and attacker.status is not None
    if physical and (attacker.ability == "hustle" or guts):
        value = int(value * 1.5)
    stage = attacker.stage(BoostStat(stat.value))
    if stage > 0 or (stage < 0 and not crit):  # a critical hit ignores the attacker's drops
        value = apply_stage(value, stage)
    return value


def defense(c: Context, crit: bool) -> int:
    defender, physical = c.defender, c.physical
    stat = Stat.DEF if physical else Stat.SPD
    value = defender.stats[stat]
    item, species = defender.item_id, defender.species_id
    if not physical and item == "souldew" and species in _SOUL_DEW_USERS:
        value = int(value * 1.5)
    elif (not physical and item == "deepseascale" and species == "clamperl") or (
        physical and item == "metalpowder" and species == "ditto"
    ):
        value *= 2
    if physical and defender.ability == "marvelscale" and defender.status is not None:
        value = int(value * 1.5)
    if c.move.id in ("explosion", "selfdestruct"):
        value //= 2
    stage = defender.stage(BoostStat(stat.value))
    if stage < 0 or (stage > 0 and not crit):  # a critical hit ignores the defender's boosts
        value = apply_stage(value, stage)
    return max(1, value)


def after_base_damage(base: int, c: Context, attacking: PokemonType, crit: bool) -> int:
    """Burn, screens, weather, Flash Fire, the +2, critical hit, doubling effects and STAB."""
    attacker, physical = c.attacker, c.physical
    if physical and attacker.status is Status.BURN and attacker.ability != "guts":
        base //= 2
    screen = SideCondition.REFLECT if physical else SideCondition.LIGHT_SCREEN
    if not crit and screen in c.defender_conditions and c.move.id != "brickbreak":
        base //= 2
    numerator, denominator = _WEATHER_POWER.get((c.weather, attacking), (1, 1))
    if c.move.id == "solarbeam" and c.weather in _SOLAR_BEAM_WEAKENERS:
        denominator = 2
    base = base * numerator // denominator
    flash_fire = attacker.ability == "flashfire" and attacker.has_volatile("flashfire")
    if flash_fire and attacking is PokemonType.FIRE:
        base = int(base * 1.5)
    base = (max(1, base) if physical else base) + 2
    if crit:
        base *= 2
    if c.move.id == "weatherball" and c.weather is not Weather.NONE:
        base *= 2
    if attacker.has_volatile("charge") and attacking is PokemonType.ELECTRIC:
        base *= 2
    if attacking in attacker.types:  # STAB
        base = int(base * 1.5)
    return base
