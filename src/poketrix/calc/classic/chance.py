"""Gens 1-2: accuracy, critical-hit rate and multi-hit counts.

The damage oracle takes these as inputs, so the rules follow the Showdown simulator instead
(data/mods/gen1/scripts.ts, data/mods/gen2/scripts.ts and items.ts). Both generations work on a
0-255 scale compared against a random byte.
"""

from collections.abc import Mapping
from types import MappingProxyType

from poketrix.schemas import BoostStat, FixedDamage, Stat, Status

from ..context import Context, Side
from ..stats import apply_stage_classic

_TWO_TO_FIVE_HITS = MappingProxyType({2: 3 / 8, 3: 3 / 8, 4: 1 / 8, 5: 1 / 8})


def hit_distribution(c: Context) -> Mapping[int, float] | None:
    """Hits per use -> probability, or None for an ordinary single-hit move."""
    if c.move.multihit is None:
        return None
    low, high = c.move.multihit
    return {low: 1.0} if low == high else _TWO_TO_FIVE_HITS


def _byte_scale(accuracy: int) -> int:
    return accuracy * 255 // 100


# ----------------------------------------------------------------------------- Gen 1

_GEN1_STAGE_PERCENT = (25, 28, 33, 40, 50, 66, 100, 150, 200, 250, 300, 350, 400)  # stages -6..+6


def _gen1_speed(side: Side) -> int:
    speed = apply_stage_classic(side.stats[Stat.SPE], side.stage(BoostStat.SPE))
    return max(1, speed // 4) if side.status is Status.PARALYSIS else speed


def gen1_ohko_fails(c: Context) -> bool:
    """A one-hit KO move cannot hit a faster target."""
    return _gen1_speed(c.defender) > _gen1_speed(c.attacker)


def gen1_hit_chance(c: Context) -> float:
    move = c.move
    if move.fixed_damage is FixedDamage.OHKO and gen1_ohko_fails(c):
        return 0.0
    if move.accuracy is None:
        return 1.0
    accuracy = _byte_scale(move.accuracy)
    accuracy = int(accuracy * (_GEN1_STAGE_PERCENT[c.attacker.stage(BoostStat.ACCURACY) + 6] / 100))
    accuracy = int(accuracy * (_GEN1_STAGE_PERCENT[6 - c.defender.stage(BoostStat.EVASION)] / 100))
    # Compared against a random byte, so even a 100% accurate move misses 1 time in 256.
    return max(1, min(255, accuracy)) / 256


def gen1_crit_chance(c: Context) -> float:
    """Based on the user's base Speed; high-crit moves multiply it by 8."""
    rate = c.attacker.pokemon.species.base_stats.spe // 2
    if c.attacker.has_volatile("focusenergy"):
        rate //= 2  # the Gen 1 Focus Energy bug: it lowers the rate
    else:
        rate = max(1, min(255, rate * 2))
    if c.move.crit_ratio == 1:
        rate //= 2
    else:
        rate = max(1, min(255, rate * 4))
    return rate / 256


# ----------------------------------------------------------------------------- Gen 2

_GEN2_BOOST = (1, 1.33, 1.66, 2, 2.33, 2.66, 3)
_GEN2_DROP = (1, 0.75, 0.6, 0.5, 0.43, 0.36, 0.33)
_GEN2_CRIT_RATE = (17, 32, 64, 85, 128)  # by crit stage, 1-based, out of 256
_SIGNATURE_CRIT_ITEMS = {("luckypunch", "chansey"), ("stick", "farfetchd")}
_NEVER_CRITS = frozenset({"flail", "reversal"})
_EVASION_IGNORERS = frozenset({"foresight"})  # volatiles on the defender


def gen2_hit_chance(c: Context) -> float:
    attacker, defender, move = c.attacker, c.defender, c.move
    ohko = move.fixed_damage is FixedDamage.OHKO
    if ohko and attacker.level < defender.level:
        return 0.0
    if move.accuracy is None:
        return 1.0
    accuracy = _byte_scale(move.accuracy)
    if ohko:
        accuracy = min(255, accuracy + 2 * (attacker.level - defender.level))
    stage = attacker.stage(BoostStat.ACCURACY)
    accuracy *= _GEN2_BOOST[stage] if stage > 0 else _GEN2_DROP[-stage]
    evasion = defender.stage(BoostStat.EVASION)
    if evasion > 0 and _EVASION_IGNORERS.isdisjoint(defender.pokemon.volatiles):
        accuracy *= _GEN2_DROP[evasion]
    elif evasion < 0:
        accuracy *= _GEN2_BOOST[-evasion]
    accuracy = max(1, min(255, int(accuracy)))
    if defender.item_id == "brightpowder":
        accuracy = max(0, accuracy - 20)
    return 1.0 if accuracy == 255 else accuracy / 256


def gen2_crit_chance(c: Context) -> float:
    attacker = c.attacker
    if c.move.id in _NEVER_CRITS:
        return 0.0
    stage = c.move.crit_ratio + (attacker.item_id == "scopelens")
    stage += attacker.has_volatile("focusenergy")
    if (attacker.item_id, attacker.species_id) in _SIGNATURE_CRIT_ITEMS:
        stage = 3
    return _GEN2_CRIT_RATE[min(stage, len(_GEN2_CRIT_RATE)) - 1] / 256
