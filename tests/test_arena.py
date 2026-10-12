"""The game harness: turning a decision into the simulator's words, the baseline player, and
the report's arithmetic. Whole games need Node and the simulator, so they run on demand:
`python -m poketrix.arena run ...`."""

import json

import pytest
from test_advisor import ours, position

from poketrix.arena.play import MaxDamagePlayer, PolicyPlayer, to_choice
from poketrix.arena.report import POOLED, load, verdict
from poketrix.schemas import ActionKind, OptionScore


def test_a_decision_is_sent_as_a_position_in_the_request():
    snapshot = position([ours("jolteon"), ours("skarmory"), ours("swampert")], "magnezone")
    request = snapshot.state.me.request
    assert "hiddenpowerice" in request.available_moves  # the request itself says `hiddenpower`
    hidden_power = OptionScore(action=ActionKind.MOVE, move_id="hiddenpowerice")
    slot = snapshot.state.me.active.known_set.moves.index("hiddenpowerice") + 1
    assert to_choice(snapshot, hidden_power, None) == f"move {slot}"
    switch = OptionScore(action=ActionKind.SWITCH, switch_index=2)
    assert to_choice(snapshot, switch, "Swampert") == "switch 3"
    with pytest.raises(ValueError, match="not offered"):
        to_choice(snapshot, OptionScore(action=ActionKind.MOVE, move_id="surf"), None)


def test_the_max_damage_player_hits_hardest_and_never_leaves_by_choice():
    player = MaxDamagePlayer()
    doomed = position([ours("gyarados", has_move="stoneedge", hp=0.45), ours("swampert")],
                      "jolteon")
    choice = player.choose(doomed).option
    assert choice.action is ActionKind.MOVE  # the policy switches here; the baseline stays
    assert PolicyPlayer().choose(doomed).option.action is ActionKind.SWITCH
    assert player.choose(position([ours("garchomp")], "magnezone")).option.move_id == "earthquake"
    forced = position([ours("gyarados", condition="0 fnt"), ours("skarmory"), ours("swampert")],
                      "jolteon", forceSwitch=[True])
    assert player.choose(forced).option.switch_index == 1  # the first it may send in


def _game(match, gen, index, swap, winner, **p1):
    side = {"decisions": 20, "statuses": {"ok": 20}, "latency_ms": [10.0] * 20, "illegal": 0,
            "trap_reasks": 0, "voluntary_switches": 2, "thrown_away": [], "self_ko": []}
    return {"match": match, "settings": {"gamma": 0.5}, "gen": gen, "index": index,
            "swap": swap, "winner": winner, "turns": 30, "p1": side | p1}


def _results(tmp_path, wins_against_max: int, max_wins_against_random: int = 15):
    """20 pairs per generation for each match; player 1 wins the first `n` games."""
    games = []
    for match, wins in (("policy-maxdamage", wins_against_max), ("policy-random", 40),
                        ("maxdamage-random", max_wins_against_random)):
        for gen in (1, 2, 3, 4):
            for number in range(40):
                winner = "p1" if number < wins else "p2"
                games.append(_game(match, gen, number // 2, bool(number % 2), winner))
    path = tmp_path / "games.jsonl"
    path.write_text("\n".join(json.dumps(game) for game in games), encoding="utf-8")
    return {match: by_gen for (match, _), by_gen in load([path]).items()}


def test_the_report_counts_games_pairs_and_the_pooled_total(tmp_path):
    found = _results(tmp_path, wins_against_max=30)
    gen4, pooled = found["policy-maxdamage"][4], found["policy-maxdamage"][POOLED]
    assert (gen4.games, gen4.wins, pooled.games, pooled.wins) == (40, 30, 160, 120)
    assert gen4.pairs == {"2-0": 15, "0-2": 5}  # games 2n and 2n+1 are one pair
    assert pooled.win_rate == 0.75 and pooled.interval[0] == pytest.approx(0.678, abs=0.002)
    assert (pooled.decisions, pooled.share("fallback")) == (3200, 0.0)


def test_the_verdict_applies_every_pass_mark(tmp_path):
    def judged(**changes):
        found = _results(tmp_path, **changes)
        return {mark[:2]: passed for mark, passed, _ in verdict(
            found["policy-maxdamage"], found["policy-random"], found["maxdamage-random"]
        )}

    assert all(judged(wins_against_max=30).values())
    close = judged(wins_against_max=22)  # 55% of 160: the lower bound is under 50%
    assert not close["1a"] and close["1b"]
    assert not judged(wins_against_max=17)["1b"]  # 42.5% in a generation
    # Against random we must do at least as well as max-damage does: 40 of 40 against 40.
    assert not judged(wins_against_max=30, max_wins_against_random=40)["2."]


def test_a_rejected_choice_or_an_error_fails_the_health_marks(tmp_path):
    found = _results(tmp_path, wins_against_max=30)
    broken = _game("policy-maxdamage", 1, 99, False, "p1", illegal=1,
                   statuses={"ok": 19, "error": 1}, latency_ms=[300.0] * 20)
    found["policy-maxdamage"][POOLED].add(broken)
    marks = {mark[:2]: passed for mark, passed, _ in verdict(
        found["policy-maxdamage"], found["policy-random"], found["maxdamage-random"]
    )}
    assert not marks["3a"] and not marks["3b"] and marks["3c"] and marks["3d"]
