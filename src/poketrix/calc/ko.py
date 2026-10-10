"""Exact n-hit KO odds from one hit's damage rolls.

Every hit independently misses, lands normally (one of the rolls, equally likely) or lands as a
critical hit (one of the crit rolls, equally likely). Assumes nothing else changes HP between
hits: no healing, residual damage, hazards or switching.
"""

from bisect import bisect_left
from collections import Counter
from collections.abc import Sequence
from functools import cache
from math import comb

from poketrix.schemas import KOChance

MAX_HITS = 4


class _RollSums:
    """Distribution of the sum of i independent draws from one roll list, built on demand."""

    def __init__(self, rolls: Sequence[int]) -> None:
        self._single = Counter(rolls)
        self._count = len(rolls)
        self.low, self.high = min(rolls), max(rolls)
        self._sums: list[dict[int, int]] = [{0: 1}]  # index i: sum -> number of ways
        self._tails: dict[int, tuple[list[int], list[int]]] = {}

    def ways(self, draws: int) -> dict[int, int]:
        while len(self._sums) <= draws:
            longer: dict[int, int] = {}
            for total, ways in self._sums[-1].items():
                for roll, copies in self._single.items():
                    longer[total + roll] = longer.get(total + roll, 0) + ways * copies
            self._sums.append(longer)
        return self._sums[draws]

    def at_least(self, draws: int, threshold: int) -> float:
        """P(sum of `draws` rolls >= threshold)."""
        if threshold <= draws * self.low:
            return 1.0
        if threshold > draws * self.high:
            return 0.0
        if draws not in self._tails:
            totals = sorted(self.ways(draws))
            suffix = [0] * (len(totals) + 1)
            for i in range(len(totals) - 1, -1, -1):
                suffix[i] = suffix[i + 1] + self._sums[draws][totals[i]]
            self._tails[draws] = (totals, suffix)
        totals, suffix = self._tails[draws]
        return suffix[bisect_left(totals, threshold)] / self._count**draws


def _binomial(n: int, k: int, p: float) -> float:
    return comb(n, k) * p**k * (1 - p) ** (n - k)


def ko_chances(
    rolls: Sequence[int], crit_rolls: Sequence[int] | None, crit_chance: float,
    hit_chance: float, hp: int, max_hits: int = MAX_HITS,
) -> list[KOChance]:
    """P(the defender, at `hp`, is knocked out within n uses) for n = 1..max_hits."""
    normal = _RollSums(rolls)
    crit = _RollSums(crit_rolls) if crit_rolls is not None and crit_chance > 0 else None
    if crit is None:
        crit_chance = 0.0

    @cache
    def landed(normal_hits: int, crit_hits: int) -> float:
        """P(total >= hp) for this many normal and critical hits landing."""
        if crit_hits == 0:
            return normal.at_least(normal_hits, hp)
        if normal_hits == 0:
            return crit.at_least(crit_hits, hp)
        # Most matchups are decided by the bounds, without building any distribution.
        if normal_hits * normal.low + crit_hits * crit.low >= hp:
            return 1.0
        if normal_hits * normal.high + crit_hits * crit.high < hp:
            return 0.0
        ways = normal.ways(normal_hits)
        hit = sum(n * crit.at_least(crit_hits, hp - total) for total, n in ways.items())
        return hit / len(rolls) ** normal_hits

    result = []
    for uses in range(1, max_hits + 1):
        probability = 0.0
        for hits in range(1, uses + 1):
            p_hits = _binomial(uses, hits, hit_chance)
            if p_hits == 0:
                continue
            for crits in range(hits + 1):
                p_crits = _binomial(hits, crits, crit_chance)
                if p_crits:
                    probability += p_hits * p_crits * landed(hits - crits, crits)
        result.append(
            KOChance(hits=uses, probability=min(1.0, max(0.0, probability)), method="exact")
        )
    return result
