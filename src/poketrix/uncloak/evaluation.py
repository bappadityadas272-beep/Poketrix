"""Measures the uncloaker on teams it has not seen.

For every held-out set and every k = 0..4, each way of revealing k of its moves is scored
(exactly, by enumeration, weighted by how often the generator produced the set):

- does the true set keep a non-zero posterior on the main path (tier 1)?
- is it the top guess, or among the top three?
- log-loss of the posterior on the true set, against "uniform over the sets that fit";
- Brier score and calibration error of P(move) for the moves not yet revealed.

Print the table with:  python -m poketrix.uncloak.evaluation
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from poketrix.schemas import Generation, PriorSet, SetEvidence

from .prior import SetPrior, load_prior, read_set_table
from .uncloaker import Candidate, Uncloaker

# tests/fixtures/ in the repo: the held-out tables written by scripts/randbats/build_randbats.mjs
HOLDOUT_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
REVEALED_COUNTS = range(5)
STALE_SHARE = 0.05  # share of sets removed for the out-of-date-prior test
_BINS = 10


@dataclass
class Metrics:
    """Weighted totals for one number of revealed moves; the properties are the reported rates."""

    revealed: int
    weight: float = 0.0
    kept: float = 0.0  # tier 1 and the true set has posterior > 0
    top1: float = 0.0
    top3: float = 0.0
    log_loss_sum: float = 0.0
    uniform_log_loss_sum: float = 0.0
    tiers: dict[int, float] = field(default_factory=dict)
    move_weight: float = 0.0
    brier_sum: float = 0.0
    bins: list[list[float]] = field(default_factory=lambda: [[0.0, 0.0, 0.0] for _ in range(_BINS)])

    @property
    def true_set_kept(self) -> float:
        return self.kept / self.weight

    @property
    def top1_accuracy(self) -> float:
        return self.top1 / self.weight

    @property
    def top3_accuracy(self) -> float:
        return self.top3 / self.weight

    @property
    def set_log_loss(self) -> float:
        return self.log_loss_sum / self.kept if self.kept else math.inf

    @property
    def uniform_log_loss(self) -> float:
        return self.uniform_log_loss_sum / self.kept if self.kept else math.inf

    @property
    def move_brier(self) -> float:
        return self.brier_sum / self.move_weight if self.move_weight else 0.0

    @property
    def move_calibration_error(self) -> float:
        """Expected calibration error: mean |predicted - observed| over 10 probability bins."""
        if not self.move_weight:
            return 0.0
        gaps = (abs(predicted - observed) for _, predicted, observed in self.bins)
        return sum(gaps) / self.move_weight

    def tier_share(self, tier: int) -> float:
        return self.tiers.get(tier, 0.0) / self.weight


def _is_truth(candidate: Candidate, truth: PriorSet) -> bool:
    known = truth.pokemon_set
    return (
        set(candidate.moves) == set(known.moves)
        and candidate.item == known.item and candidate.ability == known.ability
    )


def _score(
    metrics: Metrics, uncloaker: Uncloaker, truth: PriorSet, revealed: tuple[str, ...],
    weight: float, item_and_ability_shown: bool,
) -> None:
    known = truth.pokemon_set
    evidence = SetEvidence(revealed_moves=list(revealed))
    if item_and_ability_shown:
        evidence = SetEvidence(
            revealed_moves=list(revealed), item=known.item, ability=known.ability
        )
    inference = uncloaker.infer(known.species.id, evidence)
    metrics.weight += weight
    metrics.tiers[inference.tier] = metrics.tiers.get(inference.tier, 0.0) + weight

    ranked = sorted(inference.candidates, key=lambda c: c.posterior, reverse=True)
    rank = next((i for i, c in enumerate(ranked) if _is_truth(c, truth)), None)
    if inference.tier == 1 and rank is not None and ranked[rank].posterior > 0:
        fitting = sum(c.posterior > 0 for c in ranked)
        metrics.kept += weight
        metrics.top1 += weight * (rank == 0)
        metrics.top3 += weight * (rank < 3)
        metrics.log_loss_sum += weight * -math.log(ranked[rank].posterior)
        metrics.uniform_log_loss_sum += weight * math.log(fitting)

    # P(move) for every unrevealed move that is either predicted or actually present.
    predicted: dict[str, float] = dict.fromkeys(known.moves, 0.0)
    for candidate in ranked:
        for move in candidate.moves:
            predicted[move] = predicted.get(move, 0.0) + candidate.posterior
    for move, probability in predicted.items():
        if move in revealed:
            continue
        probability = min(1.0, probability)
        present = float(move in known.moves)
        metrics.move_weight += weight
        metrics.brier_sum += weight * (probability - present) ** 2
        bucket = metrics.bins[min(_BINS - 1, int(probability * _BINS))]
        bucket[0] += weight
        bucket[1] += weight * probability
        bucket[2] += weight * present


def evaluate(
    prior: SetPrior, holdout: Sequence[PriorSet], item_and_ability_shown: bool = False
) -> list[Metrics]:
    """Score `prior` on held-out sets; one `Metrics` per number of revealed moves.

    With `item_and_ability_shown` the true item and ability are part of the evidence as well.
    """
    uncloaker = Uncloaker(prior)
    results = [Metrics(revealed=k) for k in REVEALED_COUNTS]
    for truth in holdout:
        moves = tuple(truth.pokemon_set.moves)
        for metrics in results:
            if metrics.revealed > len(moves):
                continue
            reveals = list(combinations(moves, metrics.revealed))
            for revealed in reveals:
                weight = truth.count / len(reveals)
                _score(metrics, uncloaker, truth, revealed, weight, item_and_ability_shown)
    return results


def load_holdout(gen: Generation | int, directory: Path = HOLDOUT_DIR) -> list[PriorSet]:
    gen = Generation(gen)
    return read_set_table(directory / f"randbats_holdout_gen{int(gen)}.json", gen)


def thinned(prior: SetPrior, share: float, seed: int) -> SetPrior:
    """`prior` with a random share of its sets removed: a stand-in for an out-of-date table."""
    ids = sorted(row.set_id for row in prior.all_sets())
    return prior.without(random.Random(seed).sample(ids, round(len(ids) * share)))


def _table(title: str, rows: list[tuple[int, list[Metrics]]]) -> str:
    lines = [
        f"**{title}**",
        "",
        (
            "| Gen | k | True set kept | Top-1 | Top-3 | Set log-loss | Uniform log-loss "
            "| Move Brier | Move calibration error | Tier 2 | Tier 3 |"
        ),
        (
            "|-----|---|---------------|-------|-------|--------------|------------------"
            "|------------|------------------------|--------|--------|"
        ),
    ]
    for gen, results in rows:
        for m in results:
            lines.append(
                f"| {gen} | {m.revealed} | {m.true_set_kept:.4%} | {m.top1_accuracy:.3f} "
                f"| {m.top3_accuracy:.3f} | {m.set_log_loss:.3f} | {m.uniform_log_loss:.3f} "
                f"| {m.move_brier:.4f} | {m.move_calibration_error:.4f} "
                f"| {m.tier_share(2):.2%} | {m.tier_share(3):.2%} |"
            )
    return "\n".join(lines)


def main() -> None:
    full, shown, shifted, shifted_shown = [], [], [], []
    for gen in Generation:
        prior, holdout = load_prior(gen), load_holdout(gen)
        stale = thinned(prior, share=STALE_SHARE, seed=int(gen))
        full.append((int(gen), evaluate(prior, holdout)))
        shown.append((int(gen), evaluate(prior, holdout, item_and_ability_shown=True)))
        shifted.append((int(gen), evaluate(stale, holdout)))
        shifted_shown.append((int(gen), evaluate(stale, holdout, item_and_ability_shown=True)))
    tables = (
        ("Full prior, moves revealed", full),
        ("Full prior, moves plus item and ability revealed", shown),
        ("Prior with a random 5% of sets removed, moves revealed", shifted),
        ("Prior with a random 5% of sets removed, moves plus item and ability revealed",
         shifted_shown),
    )
    print("\n\n".join(_table(title, rows) for title, rows in tables))


if __name__ == "__main__":
    main()
