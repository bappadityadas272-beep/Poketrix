"""Turns engine output into the Math layer's output contracts."""

from collections.abc import Sequence
from time import perf_counter
from types import MappingProxyType

from poketrix.schemas import (
    BattlePokemon,
    DamageRange,
    FieldState,
    MathReport,
    Move,
    MoveCategory,
    MoveEvaluation,
    Stat,
    SubsystemResult,
    SubsystemStatus,
)

from .engine import SideConditions, UnsupportedMoveError, engine_for
from .ko import ko_chances
from .stats import battle_stats, current_hp

_NO_FIELD = FieldState()
_NO_CONDITIONS: SideConditions = MappingProxyType({})


def evaluate_move(
    attacker: BattlePokemon, defender: BattlePokemon, move: Move,
    field: FieldState = _NO_FIELD, defender_conditions: SideConditions = _NO_CONDITIONS,
) -> MoveEvaluation:
    """Damage rolls and exact KO odds of one move. `defender_conditions` holds the screens."""
    gen = attacker.generation
    if defender.generation != gen or move.generation != gen:
        raise ValueError("attacker, defender and move must be from the same generation")
    engine = engine_for(gen)
    accuracy = engine.hit_chance(attacker, defender, move)
    if move.category is MoveCategory.STATUS:
        return MoveEvaluation(move_id=move.id, accuracy=accuracy)
    try:
        result = engine.damage(attacker, defender, move, field, defender_conditions)
    except UnsupportedMoveError as reason:
        return MoveEvaluation(move_id=move.id, accuracy=accuracy, unsupported_reason=str(reason))

    max_hp = battle_stats(defender)[Stat.HP]
    damage = DamageRange(
        generation=gen, move_id=move.id,
        attacker_species=attacker.species.id, defender_species=defender.species.id,
        rolls=list(result.rolls),
        crit_rolls=None if result.crit_rolls is None else list(result.crit_rolls),
        defender_max_hp=max_hp, type_multiplier=result.type_multiplier,
    )
    hp = current_hp(defender, max_hp)
    ko = ko_chances(result.rolls, result.crit_rolls, result.crit_chance, accuracy, hp) if hp else []
    return MoveEvaluation(move_id=move.id, damage=damage, ko=ko, accuracy=accuracy)


def build_report(
    ours: BattlePokemon, theirs: BattlePokemon,
    our_moves: Sequence[Move], their_moves: Sequence[Move] = (),
    field: FieldState = _NO_FIELD,
    our_conditions: SideConditions = _NO_CONDITIONS,
    their_conditions: SideConditions = _NO_CONDITIONS,
) -> SubsystemResult[MathReport]:
    """One active matchup: our moves into them, and their (likely) moves into us."""
    started = perf_counter()
    try:
        report = MathReport(
            our_moves=[evaluate_move(ours, theirs, m, field, their_conditions) for m in our_moves],
            threats=[evaluate_move(theirs, ours, m, field, our_conditions) for m in their_moves],
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
