"""Gens 3-4: probabilities around a hit: accuracy, critical-hit rate and multi-hit counts.

The damage oracle takes these as inputs, so the rules here follow the Showdown simulator's code
instead (data/mods/gen4 and gen3: scripts.ts, abilities.ts, items.ts; sim/battle-actions.ts).
The two generations share every rule; only Lax Incense's strength differs.
Accuracy is kept as a real number; the simulator's integer rounding can differ by up to one
percentage point.
"""

from collections.abc import Mapping
from types import MappingProxyType

from poketrix.schemas import BoostStat, FixedDamage, Generation, Weather

from ..context import Context, Side
from .speed import moves_first

_CRIT_CHANCE = (1 / 16, 1 / 8, 1 / 4, 1 / 3, 1 / 2)  # by crit stage, 1-based
_CRIT_ITEMS = frozenset({"scopelens", "razorclaw"})
_SIGNATURE_CRIT_ITEMS = {("luckypunch", "chansey"), ("stick", "farfetchd")}
_BLOCKS_CRITS = frozenset({"battlearmor", "shellarmor"})
_EVASION_IGNORERS = frozenset({"foresight", "odorsleuth", "miracleeye"})  # volatiles
_EVASIVE_IN_WEATHER = {"sandveil": Weather.SANDSTORM, "snowcloak": Weather.HAIL}
_EVASION_ITEM_MULTIPLIER = {
    Generation.DPP: {"brightpowder": 0.9, "laxincense": 0.9},
    Generation.ADV: {"brightpowder": 0.9, "laxincense": 0.95},
}
_TWO_TO_FIVE_HITS = MappingProxyType({2: 3 / 8, 3: 3 / 8, 4: 1 / 8, 5: 1 / 8})


def can_crit(c: Context) -> bool:
    return c.defender.ability not in _BLOCKS_CRITS


def crit_chance(c: Context) -> float:
    if not can_crit(c):
        return 0.0
    attacker = c.attacker
    stage = c.move.crit_ratio
    stage += attacker.ability == "superluck"
    stage += attacker.item_id in _CRIT_ITEMS
    stage += 2 * ((attacker.item_id, attacker.species_id) in _SIGNATURE_CRIT_ITEMS)
    stage += 2 * attacker.has_volatile("focusenergy")
    return _CRIT_CHANCE[min(stage, len(_CRIT_CHANCE)) - 1]


def hit_distribution(c: Context) -> Mapping[int, float] | None:
    """Hits per use -> probability, or None for an ordinary single-hit move."""
    if c.move.multihit is None:
        return None
    low, high = c.move.multihit
    if low == high:
        return {low: 1.0}
    if c.attacker.ability == "skilllink":
        return {high: 1.0}
    return _TWO_TO_FIVE_HITS


def _stage(side: Side, stat: BoostStat, ignored: bool) -> int:
    if ignored:
        return 0
    stage = side.stage(stat) * (2 if side.ability == "simple" else 1)
    return max(-6, min(6, stage))


def _stage_multiplier(stage: int) -> float:
    return (3 + stage) / 3 if stage >= 0 else 3 / (3 - stage)


def hit_chance(c: Context) -> float:
    attacker, defender, move = c.attacker, c.defender, c.move
    no_guard = "noguard" in (attacker.ability, defender.ability)
    if move.fixed_damage is FixedDamage.OHKO:  # ignores every accuracy modifier
        if attacker.level < defender.level:
            return 0.0
        return 1.0 if no_guard else min(1.0, (30 + attacker.level - defender.level) / 100)
    if move.accuracy is None or no_guard:
        return 1.0

    accuracy_stage = _stage(attacker, BoostStat.ACCURACY, ignored=defender.ability == "unaware")
    evasion_stage = _stage(defender, BoostStat.EVASION, ignored=attacker.ability == "unaware")
    if evasion_stage > 0 and not _EVASION_IGNORERS.isdisjoint(defender.pokemon.volatiles):
        evasion_stage = 0
    accuracy = move.accuracy * _stage_multiplier(accuracy_stage) / _stage_multiplier(evasion_stage)

    if attacker.ability == "compoundeyes":
        accuracy *= 1.3
    if attacker.ability == "hustle" and c.physical:
        accuracy *= 0.8
    if attacker.item_id == "widelens":
        accuracy *= 1.1
    if attacker.item_id == "zoomlens" and not moves_first(c):
        accuracy *= 1.2
    if _EVASIVE_IN_WEATHER.get(defender.ability) is c.weather and c.weather is not Weather.NONE:
        accuracy *= 0.8
    if defender.ability == "tangledfeet" and defender.has_volatile("confusion"):
        accuracy *= 0.5
    accuracy *= _EVASION_ITEM_MULTIPLIER[c.gen].get(defender.item_id, 1.0)
    if c.gravity:
        accuracy *= 5 / 3
    return min(1.0, accuracy / 100)
