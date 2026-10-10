"""Threat report: what the opponent's possible moves would do to our Pokémon.

Joins the two layers without adding to either: every set hypothesis with a non-zero posterior
becomes a full set for the opponent, the existing damage calculator evaluates its moves against
our Pokémon, and the results are averaged with the posterior as weights.
"""

from dataclasses import dataclass
from time import perf_counter

from poketrix.calc import evaluate_move
from poketrix.calc.engine import NO_CONDITIONS, SideConditions
from poketrix.dex import Dex
from poketrix.schemas import (
    BattlePokemon,
    FieldState,
    MoveEvaluation,
    MoveThreat,
    PokemonSet,
    SetHypothesis,
    SetPosterior,
    StatSpread,
    SubsystemResult,
    SubsystemStatus,
    ThreatReport,
)

from .prior import SetPrior

_NO_FIELD = FieldState()


def _hypothesis_set(
    theirs: BattlePokemon, hypothesis: SetHypothesis, prior: SetPrior
) -> PokemonSet:
    """The opponent's full set under one hypothesis.

    Moves, item and ability are the hypothesis's own (a fallback tier may have replaced the
    table's). The spread comes from the table set the hypothesis names, or failing that from the
    species' most common set; the level is the one the battle shows.
    """
    known = prior.sets_for(theirs.species.id)
    spread = known[0].pokemon_set.spread if known else StatSpread()
    if not hypothesis.set_id.startswith("fallback:"):
        spread = prior.pokemon_set(hypothesis.set_id).spread
    return PokemonSet(
        species=theirs.species, level=theirs.level, moves=hypothesis.moves,
        item=hypothesis.item, ability=hypothesis.ability, spread=spread,
    )


def _ko_this_turn(evaluation: MoveEvaluation) -> float:
    """Chance that one use knocks our Pokémon out; 0 for a status or unsupported move."""
    return evaluation.ko[0].probability if evaluation.ko else 0.0


@dataclass
class _MoveTally:
    """Posterior-weighted totals for one move across the hypotheses that carry it."""

    weight: float = 0.0
    expected: float = 0.0
    worst: float = 0.0
    worst_crit: float = 0.0
    ko: float = 0.0
    has_damage: bool = False
    unsupported_reason: str | None = None

    def add(self, weight: float, evaluation: MoveEvaluation) -> None:
        self.weight += weight
        if evaluation.unsupported_reason is not None:
            self.unsupported_reason = evaluation.unsupported_reason
        damage = evaluation.damage
        if damage is None:
            return
        hits = damage.hit_distribution or {1: 1.0}
        mean_hits = sum(count * odds for count, odds in hits.items())
        mean_roll = sum(damage.rolls) / len(damage.rolls)
        self.has_damage = True
        self.expected += weight * 100 * mean_hits * mean_roll / damage.defender_max_hp
        self.worst = max(self.worst, damage.max_pct)
        # Where a critical hit is impossible or changes nothing, the two worst cases coincide.
        top_crit = damage.crit_rolls[-1] if damage.crit_rolls else damage.rolls[-1]
        self.worst_crit = max(self.worst_crit, 100 * max(hits) * top_crit / damage.defender_max_hp)
        self.ko += weight * _ko_this_turn(evaluation)

    def threat(self, move_id: str) -> MoveThreat:
        probability = min(1.0, self.weight)
        if self.unsupported_reason is not None:
            return MoveThreat(
                move_id=move_id, probability=probability,
                unsupported_reason=self.unsupported_reason,
            )
        if not self.has_damage:  # a status move
            return MoveThreat(move_id=move_id, probability=probability)
        expected = self.expected / self.weight
        worst = max(self.worst, expected)
        return MoveThreat(
            move_id=move_id, probability=probability,
            expected_pct=expected, worst_case_pct=worst,
            worst_crit_pct=max(self.worst_crit, worst),
            ko_probability=min(1.0, self.ko / self.weight),
        )


def _report(
    ours: BattlePokemon, theirs: BattlePokemon, posterior: SetPosterior, prior: SetPrior,
    field: FieldState, our_conditions: SideConditions, their_conditions: SideConditions,
) -> ThreatReport:
    dex = Dex(ours.generation)
    tallies: dict[str, _MoveTally] = {}
    # A move's damage depends on the attacker's item, ability and spread, not on its other
    # moves, and many hypotheses share those: evaluate each combination once.
    evaluated: dict[tuple, MoveEvaluation] = {}
    p_ko_best_move = 0.0
    for hypothesis in posterior.hypotheses:
        if hypothesis.posterior <= 0:
            continue
        known = _hypothesis_set(theirs, hypothesis, prior)
        attacker = theirs.model_copy(update={"known_set": known})
        stats_key = (known.item, known.ability, known.spread.model_dump_json())
        for move_id in hypothesis.moves:
            key = (move_id, *stats_key)
            if key not in evaluated:
                evaluated[key] = evaluate_move(
                    attacker, ours, dex.move(move_id), field, our_conditions, their_conditions
                )
            tallies.setdefault(move_id, _MoveTally()).add(hypothesis.posterior, evaluated[key])
        # Under this hypothesis the opponent's best move for a knockout is one specific move.
        best = max(_ko_this_turn(evaluated[(move_id, *stats_key)]) for move_id in hypothesis.moves)
        p_ko_best_move += hypothesis.posterior * best
    threats = [tally.threat(move_id) for move_id, tally in tallies.items()]
    threats.sort(key=lambda threat: (-threat.probability, threat.move_id))
    return ThreatReport(
        attacker_species=theirs.species.id, defender_species=ours.species.id, threats=threats,
        p_ko_best_move=min(1.0, p_ko_best_move),
        ko_lower_bound=any(threat.unsupported_reason is not None for threat in threats),
    )


def threat_report(
    ours: BattlePokemon, theirs: BattlePokemon, posterior: SetPosterior, prior: SetPrior,
    field: FieldState = _NO_FIELD,
    our_conditions: SideConditions = NO_CONDITIONS,
    their_conditions: SideConditions = NO_CONDITIONS,
) -> SubsystemResult[ThreatReport]:
    """Every move the opponent may carry, with its probability and its damage to `ours`.

    `ours` needs a `known_set`; `theirs` is the opponent as the battle shows it. Never raises:
    a failure is an ERROR result.
    """
    started = perf_counter()

    def result(status: SubsystemStatus, **fields) -> SubsystemResult[ThreatReport]:
        elapsed = (perf_counter() - started) * 1000
        return SubsystemResult[ThreatReport](status=status, latency_ms=elapsed, **fields)

    try:
        report = _report(ours, theirs, posterior, prior, field, our_conditions, their_conditions)
    # Rule 3: a subsystem reports its failure, it never takes the whole turn down.
    except Exception as error:  # noqa: BLE001
        return result(SubsystemStatus.ERROR, error=f"{type(error).__name__}: {error}")
    return result(SubsystemStatus.OK, payload=report)
