"""Exact n-hit KO odds from one hit's damage rolls.

Every use independently misses or lands; a landed use deals one hit, or for a multi-hit move a
random number of hits. Every hit independently is normal (one of the rolls, equally likely) or
critical (one of the crit rolls, equally likely). Assumes nothing else changes HP in between:
no healing, residual damage, hazards or switching.
"""

from bisect import bisect_left
from collections import Counter
from collections.abc import Mapping, Sequence
from fractions import Fraction
from functools import cache
from math import comb, lcm

from poketrix.schemas import KOChance

MAX_HITS = 4

_Hits = tuple[int, int]  # (normal hits, critical hits)


class _DamageSums:
    """P(total damage >= threshold) for any mix of normal and critical hits.

    A mix is split into two halves; the answer is a sum over one half's totals of the other
    half's tail. So the full distribution of a mix is never built, only those of its halves.
    """

    def __init__(self, rolls: Sequence[int], crit_rolls: Sequence[int] | None) -> None:
        self._rolls = (rolls, crit_rolls)
        self._low = (min(rolls), min(crit_rolls) if crit_rolls else 0)
        self._high = (max(rolls), max(crit_rolls) if crit_rolls else 0)
        self._ways: dict[_Hits, dict[int, int]] = {}  # mix -> total damage -> number of ways
        self._tails: dict[_Hits, tuple[list[int], list[int]]] = {}

    @staticmethod
    def _halves(mix: _Hits) -> tuple[_Hits, _Hits]:
        normal, crit = mix
        first_normal = min(normal, (normal + crit) // 2)
        first_crit = (normal + crit) // 2 - first_normal
        return (first_normal, first_crit), (normal - first_normal, crit - first_crit)

    def _distribution(self, mix: _Hits) -> dict[int, int]:
        if mix not in self._ways:
            if sum(mix) == 1:
                self._ways[mix] = Counter(self._rolls[mix[1]])
            else:
                first, second = (self._distribution(half) for half in self._halves(mix))
                combined: dict[int, int] = {}
                for a, ways_a in first.items():
                    for b, ways_b in second.items():
                        combined[a + b] = combined.get(a + b, 0) + ways_a * ways_b
                self._ways[mix] = combined
        return self._ways[mix]

    def _tail(self, mix: _Hits) -> tuple[list[int], list[int]]:
        """Sorted totals and, for each, the number of ways to reach it or more."""
        if mix not in self._tails:
            distribution = self._distribution(mix)
            totals = sorted(distribution)
            at_least = [0] * (len(totals) + 1)
            for i in range(len(totals) - 1, -1, -1):
                at_least[i] = at_least[i + 1] + distribution[totals[i]]
            self._tails[mix] = (totals, at_least)
        return self._tails[mix]

    def at_least(self, mix: _Hits, threshold: int) -> float:
        normal, crit = mix
        # Most matchups are decided by the bounds, without building any distribution.
        if threshold <= normal * self._low[0] + crit * self._low[1]:
            return 1.0
        if threshold > normal * self._high[0] + crit * self._high[1]:
            return 0.0
        outcomes = len(self._rolls[0]) ** normal * (len(self._rolls[1]) ** crit if crit else 1)
        if normal + crit == 1:
            totals, at_least = self._tail(mix)
            return at_least[bisect_left(totals, threshold)] / outcomes
        first, second = self._halves(mix)
        totals, at_least = self._tail(second)
        ways = 0
        for total, count in self._distribution(first).items():
            ways += count * at_least[bisect_left(totals, threshold - total)]
        return ways / outcomes


def _binomial(n: int, k: int, p: float) -> float:
    return comb(n, k) * p**k * (1 - p) ** (n - k)


def _whole_use_rolls(rolls: Sequence[int], hit_distribution: Mapping[int, float]) -> list[int]:
    """Equally likely damage totals of one use whose hits all repeat the same roll."""
    odds = {hits: Fraction(p).limit_denominator(256) for hits, p in hit_distribution.items()}
    scale = lcm(*(f.denominator for f in odds.values()))
    return [
        hits * roll for hits, f in odds.items() for _ in range(int(f * scale)) for roll in rolls
    ]


def ko_chances(
    rolls: Sequence[int], crit_rolls: Sequence[int] | None, crit_chance: float,
    hit_chance: float, hp: int, max_hits: int = MAX_HITS,
    hit_distribution: Mapping[int, float] | None = None, hits_share_roll: bool = False,
) -> list[KOChance]:
    """P(the defender, at `hp`, is knocked out within n uses) for n = 1..max_hits.

    `hit_distribution` (hits per landed use -> probability) is given for multi-hit moves. With
    `hits_share_roll` every hit of a use repeats the first hit's roll and crit (Gen 1), which
    makes the whole use behave like one hit with a longer roll list.
    """
    if hits_share_roll and hit_distribution is not None:
        rolls = _whole_use_rolls(rolls, hit_distribution)
        crit_rolls = None if crit_rolls is None else _whole_use_rolls(crit_rolls, hit_distribution)
        hit_distribution = None
    per_use = {1: 1.0} if hit_distribution is None else hit_distribution
    if crit_rolls is None:
        crit_chance = 0.0
    sums = _DamageSums(rolls, crit_rolls if crit_chance > 0 else None)

    @cache
    def after_hits(hits: int) -> float:
        """P(total >= hp) once this many hits have landed, over every normal/critical split."""
        total = 0.0
        for crits in range(hits + 1):
            p_crits = _binomial(hits, crits, crit_chance)
            if p_crits:
                total += p_crits * sums.at_least((hits - crits, crits), hp)
        return total

    result = []
    hit_totals = {0: 1.0}  # total hits after k landed uses -> probability
    after_uses = [0.0]  # index k: P(KO) given exactly k uses landed
    for uses in range(1, max_hits + 1):
        longer: dict[int, float] = {}
        for total, p in hit_totals.items():
            for hits, q in per_use.items():
                longer[total + hits] = longer.get(total + hits, 0.0) + p * q
        hit_totals = longer
        after_uses.append(sum(p * after_hits(total) for total, p in hit_totals.items()))
        probability = sum(
            _binomial(uses, landed_uses, hit_chance) * after_uses[landed_uses]
            for landed_uses in range(1, uses + 1)
        )
        result.append(
            KOChance(hits=uses, probability=min(1.0, max(0.0, probability)), method="exact")
        )
    return result
