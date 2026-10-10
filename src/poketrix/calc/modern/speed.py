"""Gens 3-4: effective Speed and turn order (Gyro Ball, Payback, Zoom Lens). Follows the oracle."""

from poketrix.schemas import BoostStat, Stat, Status, Weather

from ..context import SPEED_HALVING_ITEMS, Context, Side
from ..stats import apply_stage

_DOUBLE, _ONE_AND_A_HALF, _HALF = 8192, 6144, 2048  # modifiers in 4096ths
_WEATHER_SPEED_ABILITY = {"chlorophyll": Weather.SUN, "swiftswim": Weather.RAIN}


def effective_speed(side: Side, c: Context) -> int:
    speed = apply_stage(side.stats[Stat.SPE], side.stage(BoostStat.SPE))
    modifiers = []
    if c.tailwind(side):
        modifiers.append(_DOUBLE)
    # Speed uses the ability as held: Mold Breaker only matters once the move connects.
    ability = side.own_ability
    unburdened = ability == "unburden" and side.has_volatile("unburden")
    weather_boost = _WEATHER_SPEED_ABILITY.get(ability)
    if unburdened or (weather_boost is not None and weather_boost is c.weather):
        modifiers.append(_DOUBLE)
    elif ability == "quickfeet" and side.status is not None:
        modifiers.append(_ONE_AND_A_HALF)
    elif ability == "slowstart" and side.has_volatile("slowstart"):
        modifiers.append(_HALF)
    held = None if side.held_item is None else side.held_item.id
    if not unburdened:
        if side.item_id == "choicescarf":
            modifiers.append(_ONE_AND_A_HALF)
        elif held in SPEED_HALVING_ITEMS:  # these work even under Klutz
            modifiers.append(_HALF)
        elif side.item_id == "quickpowder" and side.species_id == "ditto":
            modifiers.append(_DOUBLE)
    chained = 4096
    for modifier in modifiers:
        chained = (chained * modifier + 2048) >> 12
    whole, remainder = divmod(speed * chained, 4096)
    speed = whole + (remainder > 2048)  # rounds half down
    if side.status is Status.PARALYSIS and ability != "quickfeet":
        speed = speed * 25 // 100
    return min(10000, speed)


def moves_first(c: Context) -> bool:
    """Whether the attacker acts before the defender when both use a move of equal priority.

    An estimate by Speed alone: the opponent's priority moves and switches are not known here.
    A Speed tie counts as moving second, as in the oracle.
    """
    attacker, defender = effective_speed(c.attacker, c), effective_speed(c.defender, c)
    return attacker < defender if c.trick_room else attacker > defender
