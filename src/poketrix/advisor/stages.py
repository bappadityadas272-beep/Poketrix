"""Stages 1 to 5 of the turn engine: each joins layers that already exist and adds no rule
of its own. A stage returns what it finished, how complete that is, and why not if it is not;
it records every number it produced in `numbers` under a stable key.
"""

from collections.abc import Mapping

from poketrix.calc import acts_first_chance, evaluate_move, expected_hp_share
from poketrix.calc.stats import battle_stats, current_hp
from poketrix.dex import UnknownDexEntryError
from poketrix.schemas import (
    ActionPrediction,
    BattlePokemon,
    MoveCategory,
    MoveOutlook,
    OffenceSheet,
    OpponentSets,
    OrderSheet,
    SetPosterior,
    Stat,
    SubsystemStatus,
    ThreatSheet,
)
from poketrix.uncloak import Uncloaker, threat_report

from .situation import Deadline, Situation

OK, FALLBACK, TIMEOUT = SubsystemStatus.OK, SubsystemStatus.FALLBACK, SubsystemStatus.TIMEOUT
Numbers = dict[str, float]
# heuristic-0: placeholders until the Phase 7 predictor replaces them.
HEURISTIC_VERSION = "heuristic-0"
_SWITCH_BASE, _SWITCH_PER_KO, _SWITCH_MIN, _SWITCH_MAX = 0.10, 0.40, 0.05, 0.60


def _out_of_time(done: int, total: int) -> tuple[SubsystemStatus, str | None]:
    if done == total:
        return OK, None
    return TIMEOUT, f"out of time after {done} of {total}"


def read_opponent(situation: Situation, deadline: Deadline, numbers: Numbers):
    """Stage 1: a posterior for each of their Pokémon still alive, the active one first."""
    uncloaker = Uncloaker(situation.prior)
    team = situation.them.team
    alive = [index for index, mon in enumerate(team) if not mon.fainted]
    alive.sort(key=lambda index: index != situation.them.active_index)
    sets = OpponentSets()
    failed = []
    for done, index in enumerate(alive):
        if deadline.expired():
            return sets, *_out_of_time(done, len(alive))
        species_id, evidence = situation.evidence(index)
        result = uncloaker.uncloak(species_id, evidence)
        if result.payload is None:
            failed.append(f"{species_id}: {result.error}")
        else:
            sets.posteriors[index] = result.payload
            if result.status is not OK:
                failed.append(f"{species_id}: evidence fits no known set, fallback sets used")
    return (sets, FALLBACK, "; ".join(failed)) if failed else (sets, OK, None)


def read_threats(
    situation: Situation, posterior: SetPosterior, deadline: Deadline, numbers: Numbers
):
    """Stage 2: their active Pokémon against each of ours that may face it next."""
    sheet = ThreatSheet()
    targets = situation.attackers
    failed = []
    for done, index in enumerate(targets):
        if deadline.expired():
            return sheet, *_out_of_time(done, len(targets))
        result = threat_report(
            situation.me.team[index], situation.theirs, posterior, situation.prior,
            situation.state.field, situation.me.conditions, situation.them.conditions,
        )
        if result.payload is None:
            failed.append(f"our Pokémon {index}: {result.error}")
            continue
        sheet.by_target[index] = report = result.payload
        numbers[f"their.{index}.p_ko"] = report.p_ko_best_move
        numbers[f"their.{index}.share"] = report.expected_best_share
    return (sheet, FALLBACK, "; ".join(failed)) if failed else (sheet, OK, None)


def _moves_of(situation: Situation, index: int) -> list[str]:
    if index == situation.me.active_index:
        return list(situation.request.available_moves)
    return list(situation.me.team[index].known_set.moves)


def _outlook(
    situation: Situation, attacker: BattlePokemon, move_id: str,
    their_sets: list[tuple[float, BattlePokemon]],
) -> MoveOutlook:
    try:
        move = situation.dex.move(move_id)
    except UnknownDexEntryError:  # `recharge`, `fight`: a forced choice, not a move
        return MoveOutlook(move_id=move_id, unsupported_reason="not a move the calculator knows")
    if move.category is MoveCategory.STATUS:
        return MoveOutlook(move_id=move_id)
    share = knock_out = 0.0
    for weight, defender in their_sets:
        evaluation = evaluate_move(
            attacker, defender, move, situation.state.field,
            situation.them.conditions, situation.me.conditions,
        )
        if evaluation.unsupported_reason is not None:  # R5: unknown, never zero
            return MoveOutlook(move_id=move_id, unsupported_reason=evaluation.unsupported_reason)
        remaining = current_hp(defender, battle_stats(defender)[Stat.HP])
        share += weight * (expected_hp_share(evaluation, remaining) or 0.0)
        knock_out += weight * (evaluation.ko[0].probability if evaluation.ko else 0.0)
    return MoveOutlook(
        move_id=move_id, expected_share=min(1.0, share), ko_probability=min(1.0, knock_out)
    )


def move_outlooks(
    situation: Situation, index: int, their_sets: list[tuple[float, BattlePokemon]]
) -> list[MoveOutlook]:
    """What each move of our Pokémon `index` does to their active Pokémon."""
    attacker = situation.me.team[index]
    return [
        _outlook(situation, attacker, move_id, their_sets)
        for move_id in _moves_of(situation, index)
    ]


def read_offence(
    situation: Situation, posterior: SetPosterior, deadline: Deadline, numbers: Numbers
):
    """Stage 3: what each move of ours does to their active Pokémon, our active one first."""
    their_sets = situation.their_sets(posterior)
    sheet = OffenceSheet()
    attackers = situation.attackers
    for done, index in enumerate(attackers):
        if deadline.expired():
            return sheet, *_out_of_time(done, len(attackers))
        sheet.by_attacker[index] = outlooks = move_outlooks(situation, index, their_sets)
        for outlook in outlooks:
            if outlook.expected_share is not None:
                numbers[f"our.{index}.{outlook.move_id}.share"] = outlook.expected_share
                numbers[f"our.{index}.{outlook.move_id}.ko"] = outlook.ko_probability
    return sheet, OK, None


def read_order(
    situation: Situation, posterior: SetPosterior, deadline: Deadline, numbers: Numbers
):
    """Stage 4: the chance that we act first, per move. Their move is taken to have no
    priority: which one they choose is not known here."""
    their_sets = situation.their_sets(posterior)
    sheet = OrderSheet()
    attackers = situation.attackers
    for done, index in enumerate(attackers):
        if deadline.expired():
            return sheet, *_out_of_time(done, len(attackers))
        attacker = situation.me.team[index]
        by_priority: dict[int, float] = {}
        sheet.first[index] = first = {}
        for move_id in _moves_of(situation, index):
            try:
                move = situation.dex.move(move_id)
            except UnknownDexEntryError:
                continue
            if move.priority not in by_priority:
                by_priority[move.priority] = sum(
                    weight * acts_first_chance(
                        attacker, defender, move, 0, situation.state.field,
                        situation.me.conditions, situation.them.conditions,
                    )
                    for weight, defender in their_sets
                )
            first[move_id] = numbers[f"our.{index}.{move_id}.first"] = min(
                1.0, by_priority[move.priority]
            )
    return sheet, OK, None


def predict_opponent(
    situation: Situation, posterior: SetPosterior, outlooks: list[MoveOutlook],
    numbers: Numbers,
):
    """Stage 5: attack, switch or utility. A rule of thumb: the likelier we are to knock their
    Pokémon out, the likelier it leaves, if it has somewhere to go."""
    best_ko = max((outlook.ko_probability or 0.0 for outlook in outlooks), default=0.0)
    p_switch = 0.0
    if situation.them.alive_count > 1:
        p_switch = min(_SWITCH_MAX, max(_SWITCH_MIN, _SWITCH_BASE + _SWITCH_PER_KO * best_ko))
    prediction = ActionPrediction(
        p_switch=p_switch, model_version=HEURISTIC_VERSION,
        **_attack_or_utility(1 - p_switch, _damaging_share(situation, posterior)),
    )
    numbers["opponent.p_switch"] = prediction.p_switch
    numbers["opponent.p_attack"] = prediction.p_attack
    return prediction, OK, None


def _attack_or_utility(staying: float, damaging: float) -> Mapping[str, float]:
    return {"p_attack": staying * damaging, "p_utility": staying * (1 - damaging)}


def _damaging_share(situation: Situation, posterior: SetPosterior) -> float:
    """How much of their likely moveset is damaging moves."""
    share = 0.0
    for hypothesis in posterior.hypotheses:
        damaging = sum(
            situation.dex.move(move).category is not MoveCategory.STATUS
            for move in hypothesis.moves
        )
        share += hypothesis.posterior * damaging / len(hypothesis.moves)
    return min(1.0, share)
