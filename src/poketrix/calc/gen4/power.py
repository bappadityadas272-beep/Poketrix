"""Gen 4 base power: per-move rules, then the ability and item modifiers in the oracle's order.

Every modifier is floored as soon as it is applied, with the same floating-point operation the
oracle uses, so results match it bit for bit.
"""

from poketrix.schemas import MoveFlag, PokemonType, Status, Weather

from ..context import Context
from ..modern.speed import effective_speed, moves_first
from ..power_rules import (
    FACADE_STATUSES,
    Rule,
    by_target_weight,
    doubled_if,
    maximum_happiness,
    scaled_by_user_hp,
    stronger_at_low_hp,
)

# ----------------------------------------------------------------------------- per-move rules


def _scaled_by_target_hp(c: Context) -> int:
    return c.defender.hp * 120 // c.defender.max_hp + 1


def _gyro_ball(c: Context) -> int:
    # Showdown simulator rule (data/moves.ts): the oracle omits the "+ 1".
    user_speed = effective_speed(c.attacker, c)
    if user_speed == 0:
        return 1
    return min(150, 25 * effective_speed(c.defender, c) // user_speed + 1)


def _punishment(c: Context) -> int:
    # Showdown simulator rule (sim/pokemon.ts positiveBoosts): every positive stage counts,
    # accuracy and evasion included. The oracle counts only the five battle stats.
    positive = sum(stage for stage in c.defender.pokemon.boosts.values() if stage > 0)
    return min(200, 60 + 20 * positive)


def _fling(c: Context) -> int:
    item = c.attacker.item
    return 0 if item is None or item.fling_power is None else item.fling_power


def _natural_gift(c: Context) -> int:
    item = c.attacker.item
    return 0 if item is None or item.natural_gift_power is None else item.natural_gift_power


_low_hp = stronger_at_low_hp(64, ((1, 200), (5, 150), (12, 100), (21, 80), (42, 40)))

POWER_RULES: dict[str, Rule] = {
    "return": maximum_happiness,
    "frustration": maximum_happiness,
    "eruption": scaled_by_user_hp,
    "waterspout": scaled_by_user_hp,
    "flail": _low_hp,
    "reversal": _low_hp,
    "crushgrip": _scaled_by_target_hp,
    "wringout": _scaled_by_target_hp,
    "lowkick": by_target_weight,
    "grassknot": by_target_weight,
    "gyroball": _gyro_ball,
    "punishment": _punishment,
    "fling": _fling,
    "naturalgift": _natural_gift,
    "brine": doubled_if(lambda c: c.defender.hp * 2 <= c.defender.max_hp),
    "facade": doubled_if(lambda c: c.attacker.status in FACADE_STATUSES),
    "wakeupslap": doubled_if(lambda c: c.defender.status is Status.SLEEP),
    "weatherball": doubled_if(lambda c: c.weather is not Weather.NONE),
    "payback": doubled_if(lambda c: not moves_first(c)),
}


# ----------------------------------------------------------------------------- modifiers

_PINCH_ABILITY_TYPE = {
    "overgrow": PokemonType.GRASS,
    "blaze": PokemonType.FIRE,
    "torrent": PokemonType.WATER,
    "swarm": PokemonType.BUG,
}
_SIGNATURE_ORB_TYPES = {  # (item, species) -> boosted types
    ("adamantorb", "dialga"): (PokemonType.STEEL, PokemonType.DRAGON),
    ("lustrousorb", "palkia"): (PokemonType.WATER, PokemonType.DRAGON),
    ("griseousorb", "giratinaorigin"): (PokemonType.GHOST, PokemonType.DRAGON),
}


def _item_boosts_type(c: Context, attacking: PokemonType) -> bool:
    item = c.attacker.item
    if item is None:
        return False
    if item.boosts_type is attacking:
        return True
    if attacking in _SIGNATURE_ORB_TYPES.get((item.id, c.attacker.species_id), ()):
        return True
    return c.move.id == "struggle" and item.boosts_type is PokemonType.NORMAL


def modified_power(power: int, c: Context, attacking: PokemonType) -> int:
    attacker, defender, move = c.attacker, c.defender, c.move
    if attacker.has_volatile("charge") and attacking is PokemonType.ELECTRIC:
        power *= 2
    if attacker.ability == "technician" and power <= 60:
        power = int(power * 1.5)

    band = "muscleband" if c.physical else "wiseglasses"
    if attacker.item_id == band:
        power = int(power * 1.1)
    elif _item_boosts_type(c, attacking):
        power = int(power * 1.2)

    reckless = attacker.ability == "reckless" and MoveFlag.RECOIL in move.flags
    iron_fist = attacker.ability == "ironfist" and MoveFlag.PUNCH in move.flags
    if reckless or iron_fist:
        power = int(power * 1.2)
    elif (
        _PINCH_ABILITY_TYPE.get(attacker.ability) is attacking
        and attacker.hp * 3 <= attacker.max_hp
    ):
        power = int(power * 1.5)

    fire = attacking is PokemonType.FIRE
    if (defender.ability == "heatproof" and fire) or (
        defender.ability == "thickfat" and (fire or attacking is PokemonType.ICE)
    ):
        power = int(power * 0.5)
    elif defender.ability == "dryskin" and fire:
        power = int(power * 1.25)
    return power
