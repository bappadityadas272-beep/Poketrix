"""Bayesian set uncloaker: which Random Battle set is the opponent's Pokémon running?

posterior(set) ∝ prior(set) x likelihood(evidence | set). The prior is how often the official
generator produces the set; the likelihood is 0 for a set the evidence contradicts.

Evidence can contradict every known set (the prior is older than the ladder, or the log is
unusual). The uncloaker then backs off in tiers instead of failing; see `Uncloaker.infer`.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from math import comb
from time import perf_counter

from poketrix.schemas import (
    PriorSet,
    SetEvidence,
    SetHypothesis,
    SetPosterior,
    SubsystemResult,
    SubsystemStatus,
    to_id,
)

from .prior import SetPrior

# Tier 3 builds movesets from the species' most frequent moves; these bound how many it tries.
_COMPLETION_POOL = 6
_SMOOTHING = 0.01  # keeps a move that is rare in the table from having probability 0


@dataclass(frozen=True)
class Candidate:
    """One hypothesis with its probabilities, before it becomes a schema object."""

    set_id: str
    moves: tuple[str, ...]
    item: str | None
    ability: str | None
    prior: float
    posterior: float


@dataclass(frozen=True)
class Inference:
    """Result of one update. `tier` says how the answer was reached (1 = plain Bayes)."""

    tier: int
    candidates: tuple[Candidate, ...]

    @property
    def status(self) -> SubsystemStatus:
        if self.tier == 1:
            return SubsystemStatus.OK
        return SubsystemStatus.FALLBACK if self.candidates else SubsystemStatus.ERROR


def _fits_moves(row: PriorSet, evidence: SetEvidence) -> bool:
    return set(evidence.revealed_moves) <= set(row.pokemon_set.moves)


def _fits_item_and_ability(row: PriorSet, evidence: SetEvidence) -> bool:
    item, ability = row.pokemon_set.item, row.pokemon_set.ability
    if evidence.item is not None and item != evidence.item:
        return False
    if evidence.ability is not None and ability != evidence.ability:
        return False
    return item not in evidence.ruled_out_items and ability not in evidence.ruled_out_abilities


def _reveal_likelihood(row: PriorSet, evidence: SetEvidence) -> float:
    """P(these moves are the ones shown | set): every move of a set is equally likely to be."""
    return 1 / comb(len(row.pokemon_set.moves), len(evidence.revealed_moves))


def _observed(evidence_value: str | None, own: str | None, ruled_out: frozenset[str]) -> str | None:
    """What a fallback hypothesis should claim: the revealed value, else the set's own."""
    if evidence_value is not None:
        return evidence_value
    return None if own in ruled_out else own


class Uncloaker:
    def __init__(self, prior: SetPrior) -> None:
        self._prior = prior

    def infer(self, species: str, evidence: SetEvidence) -> Inference:
        """Tier 1: Bayes over the known sets.
        Tier 2: no set fits everything, so only the revealed moves are trusted as a filter; the
                surviving sets take the item and ability that were actually seen.
        Tier 3: no known set holds the revealed moves; movesets are completed from the species'
                most frequent moves.
        Tier 4: nothing is known and nothing is revealed: no candidates.
        """
        rows = self._prior.sets_for(to_id(species))
        total = sum(row.count for row in rows)

        weights = [
            row.count * _reveal_likelihood(row, evidence)
            if _fits_moves(row, evidence) and _fits_item_and_ability(row, evidence) else 0.0
            for row in rows
        ]
        if sum(weights) > 0:
            mass = sum(weights)
            return Inference(1, tuple(
                Candidate(
                    row.set_id, tuple(row.pokemon_set.moves), row.pokemon_set.item,
                    row.pokemon_set.ability, row.count / total, weight / mass,
                )
                for row, weight in zip(rows, weights)
            ))

        by_moves = [row for row in rows if _fits_moves(row, evidence)]
        if by_moves:
            return Inference(2, self._with_observed_item_and_ability(by_moves, evidence))
        if rows or evidence.revealed_moves:
            return Inference(3, self._completed_movesets(rows, evidence))
        return Inference(4, ())

    @staticmethod
    def _with_observed_item_and_ability(
        rows: Sequence[PriorSet], evidence: SetEvidence
    ) -> tuple[Candidate, ...]:
        merged: dict[tuple, tuple[str, float]] = {}  # (moves, item, ability) -> (set id, weight)
        for row in rows:
            known = row.pokemon_set
            key = (
                tuple(known.moves),
                _observed(evidence.item, known.item, evidence.ruled_out_items),
                _observed(evidence.ability, known.ability, evidence.ruled_out_abilities),
            )
            set_id, weight = merged.get(key, (row.set_id, 0.0))
            merged[key] = (set_id, weight + row.count * _reveal_likelihood(row, evidence))
        mass = sum(weight for _, weight in merged.values())
        return tuple(
            Candidate(set_id, moves, item, ability, weight / mass, weight / mass)
            for (moves, item, ability), (set_id, weight) in merged.items()
        )

    @staticmethod
    def _completed_movesets(
        rows: Sequence[PriorSet], evidence: SetEvidence
    ) -> tuple[Candidate, ...]:
        revealed = tuple(evidence.revealed_moves)
        total = sum(row.count for row in rows)
        move_counts: Counter[str] = Counter()
        sizes: Counter[int] = Counter()
        items: Counter[str | None] = Counter()
        abilities: Counter[str | None] = Counter()
        for row in rows:
            known = row.pokemon_set
            sizes[len(known.moves)] += row.count
            items[_observed(evidence.item, known.item, evidence.ruled_out_items)] += row.count
            abilities[
                _observed(evidence.ability, known.ability, evidence.ruled_out_abilities)
            ] += row.count
            for move in known.moves:
                if move not in revealed:
                    move_counts[move] += row.count
        item = items.most_common(1)[0][0] if items else evidence.item
        ability = abilities.most_common(1)[0][0] if abilities else evidence.ability

        usual_size = sizes.most_common(1)[0][0] if sizes else len(revealed)
        open_slots = max(0, usual_size - len(revealed))
        pool = [move for move, _ in move_counts.most_common(_COMPLETION_POOL)]
        open_slots = min(open_slots, len(pool))
        completions: dict[tuple[str, ...], float] = {}
        for extra in combinations(pool, open_slots):
            weight = 1.0
            for move in extra:
                weight *= move_counts[move] / total + _SMOOTHING
            completions[revealed + extra] = weight
        completions = {moves: w for moves, w in completions.items() if moves}
        mass = sum(completions.values())
        return tuple(
            Candidate(f"fallback:{index}", moves, item, ability, weight / mass, weight / mass)
            for index, (moves, weight) in enumerate(completions.items(), start=1)
        )

    def uncloak(self, species: str, evidence: SetEvidence) -> SubsystemResult[SetPosterior]:
        """The posterior as an output contract. Never raises: a failure is an ERROR result."""
        started = perf_counter()

        def result(status: SubsystemStatus, **fields) -> SubsystemResult[SetPosterior]:
            elapsed = (perf_counter() - started) * 1000
            return SubsystemResult[SetPosterior](status=status, latency_ms=elapsed, **fields)

        try:
            inference = self.infer(species, evidence)
            if not inference.candidates:
                return result(
                    SubsystemStatus.ERROR,
                    error=f"no Random Battle sets known for {species!r} and no move revealed",
                )
            posterior = SetPosterior(
                species_id=species,
                evidence_moves=evidence.revealed_moves,
                evidence_item=evidence.item,
                evidence_ability=evidence.ability,
                hypotheses=[
                    SetHypothesis(
                        set_id=c.set_id, moves=list(c.moves), item=c.item, ability=c.ability,
                        prior=c.prior, posterior=c.posterior,
                    )
                    for c in inference.candidates
                ],
            )
            return result(inference.status, payload=posterior)
        # Rule 3: a subsystem reports its failure, it never takes the whole turn down.
        except Exception as error:  # noqa: BLE001
            return result(SubsystemStatus.ERROR, error=f"{type(error).__name__}: {error}")
