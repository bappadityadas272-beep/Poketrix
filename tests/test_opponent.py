"""The opponent model (Phase 7): what a row is labelled, that its features use nothing from
after the decision, the split, and how the turn engine uses a model or falls back."""

import math
from collections import Counter

import pytest
from test_advisor import advise, ours, position

from poketrix.advisor import TurnAdvisor
from poketrix.dex import Dex
from poketrix.opponent import FEATURES, DecisionView, Heuristic, ModelUnavailable, XgbModel
from poketrix.opponent.dataset import SPLITS, STAYED, actions, split, view_of
from poketrix.schemas import PlayerSlot, SubsystemStatus
from poketrix.showdown import parse_battle, parse_line
from poketrix.showdown.validation import load_battles
from poketrix.uncloak import load_prior

P1, P2 = PlayerSlot.P1, PlayerSlot.P2
GENS = (1, 2, 3, 4)


def _events(*lines: str):
    return [parse_line(line) for line in lines]


# --------------------------------------------------------------------------- labels


def test_the_first_event_of_each_side_is_its_choice():
    turn = _events(
        "|switch|p2a: Skarmory|Skarmory, L79, F|100/100",
        "|move|p1a: Starmie|Thunder Wave|p2a: Skarmory",
        "|move|p2a: Skarmory|Spikes|p1a: Starmie",  # not its choice: it switched first
    )
    assert actions(turn, Dex(4)) == {P2: "switch", P1: "utility"}
    assert actions(_events("|move|p1a: Starmie|Surf|p2a: Skarmory"), Dex(4)) == {P1: "attack"}


def test_a_hidden_move_is_a_stay_and_no_choice_gives_no_row():
    stayed = _events(
        "|move|p1a: Starmie|Surf|p2a: Heatran", "|-damage|p2a: Heatran|0 fnt",
        "|faint|p2a: Heatran", "|switch|p2a: Skarmory|Skarmory, L79, F|100/100",
    )
    assert actions(stayed, Dex(4)) == {P1: "attack", P2: STAYED}  # it fainted before acting
    asleep = _events("|cant|p1a: Starmie|slp", "|move|p2a: Heatran|Fire Blast|p1a: Starmie")
    assert actions(asleep, Dex(4)) == {P1: STAYED, P2: "attack"}
    no_choice = _events(
        "|cant|p1a: Snorlax|recharge",
        "|drag|p2a: Heatran|Heatran, L76, M|100/100",
    )
    assert actions(no_choice, Dex(4)) == {}


def test_a_locked_move_going_on_is_not_a_choice():
    tagged = _events("|move|p1a: Salamence|Outrage|p2a: Heatran|[from] lockedmove")
    assert actions(tagged, Dex(4)) == {}
    called = _events("|move|p1a: Snorlax|Body Slam|p2a: Heatran|[from] move: Sleep Talk")
    assert actions(called, Dex(4)) == {}
    # Gen 2 writes no tag: the same Rollout again from a Pokémon that stayed in is going on.
    before = _events("|move|p1a: Golem|Rollout|p2a: Skarmory")
    again = _events("|move|p1a: Golem|Rollout|p2a: Skarmory")
    assert actions(again, Dex(2), before) == {}
    came_back = _events(*[f"|{line}" for line in (
        "move|p1a: Golem|Rollout|p2a: Skarmory", "switch|p1a: Snorlax|Snorlax, L74|100/100",
    )])
    assert actions(again, Dex(2), came_back) == {P1: "attack"}


# --------------------------------------------------------------------------- no future information


def _same(first: DecisionView, second: DecisionView) -> bool:
    return all(a == b or (math.isnan(a) and math.isnan(b))
               for a, b in zip(first.vector(), second.vector(), strict=True))


@pytest.mark.slow
@pytest.mark.parametrize("gen", GENS)
def test_features_come_only_from_lines_before_the_decision(gen):
    """Cut the log right after the turn line: every feature must come out the same."""
    prior = load_prior(gen)
    log = load_battles(gen)[0]["spectator"]
    lines = log.splitlines()
    full = parse_battle(log).snapshots
    checked = 0
    for snapshot in full[1:-1:4]:
        cut = lines.index(f"|turn|{snapshot.turn}") + 1
        truncated = parse_battle("\n".join(lines[:cut])).snapshots[-1]
        assert truncated.turn == snapshot.turn
        for decider in (P1, P2):
            whole, cut_view = view_of(snapshot, decider, prior), view_of(truncated, decider, prior)
            assert (whole is None) == (cut_view is None)
            if whole is not None:
                assert _same(whole, cut_view), f"turn {snapshot.turn}, {decider.value}"
                checked += 1
    assert checked >= 4


# --------------------------------------------------------------------------- the split


def test_the_split_keeps_battles_whole_in_the_agreed_shares():
    battles = [(gen, f"gen{gen}-{number}") for gen in GENS for number in range(200)]
    assigned = split(battles)
    assert assigned == split(list(reversed(battles)))  # the order read does not matter
    assert split(battles, seed=1) != assigned
    for gen in GENS:
        shares = Counter(name for battle, name in assigned.items() if battle.startswith(f"gen{gen}-"))
        assert {name: count / 200 for name, count in shares.items()} == SPLITS


# --------------------------------------------------------------------------- the turn engine


class _Missing:
    version = "missing"

    def predict(self, view):
        raise ModelUnavailable("not here")


def test_heuristic_0_is_the_default_and_a_missing_model_falls_back_to_it():
    snapshot = position([ours("garchomp"), ours("skarmory")], "magnezone")
    default = advise(snapshot)
    assert default.opponent.status is SubsystemStatus.OK
    assert default.opponent.payload.model_version == Heuristic.version
    missing = advise(snapshot, opponent_model=_Missing())
    assert missing.opponent.status is SubsystemStatus.FALLBACK
    assert missing.opponent.error == "not here"
    assert missing.opponent.payload == default.opponent.payload
    assert missing.recommendation == default.recommendation


def test_a_model_without_its_files_says_so(tmp_path):
    model = XgbModel(directory=tmp_path)
    view = DecisionView(*[0.0] * len(FEATURES))
    with pytest.raises(ModelUnavailable):
        model.predict(view)


def test_the_saved_model_matches_the_features_and_predicts():
    pytest.importorskip("numpy")
    snapshot = position([ours("garchomp"), ours("skarmory")], "magnezone")
    report = TurnAdvisor(opponent_model=XgbModel()).advise(snapshot)
    assert report.opponent.status is SubsystemStatus.OK
    assert report.opponent.payload.model_version == "xgb-1"
    assert report.numbers["opponent.p_attack"] == report.opponent.payload.p_attack


def test_the_trees_give_xgboost_s_own_margins():
    xgboost = pytest.importorskip("xgboost")
    numpy = pytest.importorskip("numpy")
    from poketrix.opponent.models import model_paths

    rows = numpy.random.default_rng(1).uniform(0, 1, (300, len(FEATURES)))
    rows[:, FEATURES.index("generation")] = numpy.repeat([1, 2, 3, 4], 75)
    rows[::7, FEATURES.index("moves_first")] = numpy.nan  # missing values take their branch
    booster = xgboost.Booster(model_file=model_paths("xgb-1")[0])
    expected = booster.inplace_predict(rows, predict_type="margin")
    assert XgbModel().margins(rows) == pytest.approx(expected, abs=1e-4)


@pytest.mark.timing
def test_one_prediction_takes_under_two_milliseconds():
    pytest.importorskip("numpy")
    from time import perf_counter

    model = XgbModel()
    view = DecisionView(*[0.5] * len(FEATURES))
    model.predict(view)
    times = []
    for _ in range(500):
        started = perf_counter()
        model.predict(view)
        times.append(perf_counter() - started)
    assert sorted(times)[int(0.95 * len(times))] < 0.002


# --------------------------------------------------------------------------- the metrics


def test_a_stay_costs_what_attack_and_utility_were_given():
    numpy = pytest.importorskip("numpy")
    from poketrix.opponent.evaluation import LABELS, improvement_interval, reliability, row_losses

    p = numpy.array([[0.5, 0.2, 0.3], [0.5, 0.2, 0.3]])
    y = numpy.array([LABELS["switch"], LABELS[STAYED]])
    assert row_losses(p, y) == pytest.approx([-math.log(0.3), -math.log(0.7)])
    _, error = reliability(numpy.array([0.25, 0.25, 0.75, 0.75]), numpy.array([0, 1, 1, 1.0]))
    assert error == pytest.approx(0.5 * 0.25 + 0.5 * 0.25)
    gain, low, high = improvement_interval(numpy.full(6, 0.1), numpy.array(list("aabbcc")))
    assert (gain, low, high) == pytest.approx((0.1, 0.1, 0.1))


# --------------------------------------------------------------------------- ruling 15-R


def test_the_tendency_line_reads_the_model_and_caps_the_switch_odds():
    from poketrix.advisor.tendency import UNAVAILABLE, describe
    from poketrix.schemas import ActionPrediction

    odds = ActionPrediction(p_attack=0.5, p_utility=0.05, p_switch=0.45, model_version="xgb-1")
    assert describe(odds) == "Opponent tendency: switch 45% · attack 50% · utility 5%"
    leaving = ActionPrediction(p_attack=0.1, p_utility=0.05, p_switch=0.85, model_version="xgb-1")
    assert describe(leaving, switch_cap=0.7) == ("Opponent tendency: switch 70%+ · attack 10% "
                                                 "· utility 5%")
    assert describe(None) == UNAVAILABLE


def test_the_tendency_comes_from_the_turn_and_leaves_the_advice_alone():
    pytest.importorskip("numpy")
    from poketrix.advisor.tendency import tendency, tendency_line

    snapshot = position([ours("garchomp"), ours("skarmory")], "magnezone")
    report = advise(snapshot)
    assert report.opponent.payload.model_version == Heuristic.version  # the policy's model
    model = XgbModel()
    shown = tendency(snapshot, report, model)
    assert shown.model_version == "xgb-1"
    assert shown == model.predict(_view_of_turn(snapshot, report))
    assert tendency_line(snapshot, report, _Missing()).startswith("Opponent tendency: not available")


def _view_of_turn(snapshot, report):
    from poketrix.advisor import stages
    from poketrix.advisor.situation import Situation

    situation = Situation(snapshot, load_prior(4), Dex(4))
    ours_index, theirs = situation.me.active_index, situation.them.active_index
    return stages.opponent_view(
        situation, report.uncloak.payload.posteriors[theirs],
        report.threats.payload.by_target[ours_index],
        report.offence.payload.by_attacker[ours_index], report.order.payload.first[ours_index],
    )


def test_the_isotonic_fit_never_decreases_and_keeps_the_mean():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("xgboost")
    from poketrix.opponent.calibration import fit_isotonic
    from poketrix.opponent.models import calibrated

    x = numpy.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    hit = numpy.array([0, 1, 0, 0, 1, 1.0])
    fitted = fit_isotonic(x, hit)
    assert list(fitted.y) == sorted(fitted.y) and fitted.y == pytest.approx((0, 1 / 3, 1))
    assert [fitted(v) for v in (0.0, 1.0)] == [0.0, 1.0]  # flat beyond its points
    odds = calibrated(fitted, fitted, [0.6, 0.1, 0.3])
    assert sum(odds) == pytest.approx(1.0) and min(odds) >= 0


def test_analyze_prints_the_opponent_tendency(tmp_path, capsys):
    from poketrix.__main__ import main

    log = tmp_path / "battle.log"
    log.write_text(load_battles(4)[0]["player"], encoding="utf-8")
    main(["analyze", str(log), "--turn", "2"])
    assert "Opponent tendency: " in capsys.readouterr().out
