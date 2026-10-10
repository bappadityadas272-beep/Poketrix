"""Turns engine output into the Math layer's output contracts."""

from collections.abc import Sequence
from time import perf_counter

from poketrix.schemas import (
    BattlePokemon,
    DamageRange,
    FieldState,
    MathReport,
    Move,
    MoveEvaluation,
    SubsystemResult,
    SubsystemStatus,
)

from .engine import NO_CONDITIONS, SideConditions, engine_for
from .ko import ko_chances

_NO_FIELD = FieldState()


def evaluate_move(
    attacker: BattlePokemon, defender: BattlePokemon, move: Move,
    field: FieldState = _NO_FIELD,
    defender_conditions: SideConditions = NO_CONDITIONS,
    attacker_conditions: SideConditions = NO_CONDITIONS,
) -> MoveEvaluation:
    """Damage rolls and exact KO odds of one move. `defender_conditions` holds the screens."""
    gen = attacker.generation
    if defender.generation != gen or move.generation != gen:
        raise ValueError("attacker, defender and move must be from the same generation")
    outcome = engine_for(gen).evaluate(
        attacker, defender, move, field, defender_conditions, attacker_conditions
    )
    result = outcome.damage
    if result is None:
        return MoveEvaluation(
            move_id=move.id, accuracy=outcome.hit_chance,
            unsupported_reason=outcome.unsupported_reason,
        )
    damage = DamageRange(
        generation=gen, move_id=move.id,
        attacker_species=attacker.species.id, defender_species=defender.species.id,
        rolls=list(result.rolls),
        crit_rolls=None if result.crit_rolls is None else list(result.crit_rolls),
        defender_max_hp=outcome.defender_max_hp, type_multiplier=result.type_multiplier,
        hit_distribution=None if result.hit_distribution is None else dict(result.hit_distribution),
    )
    ko = []
    if outcome.defender_hp:
        ko = ko_chances(
            result.rolls, result.crit_rolls, result.crit_chance, outcome.hit_chance,
            outcome.defender_hp, hit_distribution=result.hit_distribution,
        )
    return MoveEvaluation(move_id=move.id, damage=damage, ko=ko, accuracy=outcome.hit_chance)


def build_report(
    ours: BattlePokemon, theirs: BattlePokemon,
    our_moves: Sequence[Move], their_moves: Sequence[Move] = (),
    field: FieldState = _NO_FIELD,
    our_conditions: SideConditions = NO_CONDITIONS,
    their_conditions: SideConditions = NO_CONDITIONS,
) -> SubsystemResult[MathReport]:
    """One active matchup: our moves into them, and their (likely) moves into us."""
    started = perf_counter()
    try:
        report = MathReport(
            our_moves=[
                evaluate_move(ours, theirs, m, field, their_conditions, our_conditions)
                for m in our_moves
            ],
            threats=[
                evaluate_move(theirs, ours, m, field, our_conditions, their_conditions)
                for m in their_moves
            ],
        )
    # Rule 3: a subsystem reports its failure, it never takes the whole turn down.
    except Exception as error:  # noqa: BLE001
        return SubsystemResult[MathReport](
            status=SubsystemStatus.ERROR, latency_ms=(perf_counter() - started) * 1000,
            error=f"{type(error).__name__}: {error}",
        )
    return SubsystemResult[MathReport](
        status=SubsystemStatus.OK, latency_ms=(perf_counter() - started) * 1000, payload=report
    )
