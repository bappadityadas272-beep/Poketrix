"""The game harness: turning a decision into the simulator's words, the baseline player, and
the report's arithmetic. Whole games need Node and the simulator, so they run on demand:
`python -m poketrix.arena run ...`."""

import json

import pytest
from test_advisor import ours, position

from poketrix.arena.play import MaxDamagePlayer, PolicyPlayer, to_choice
from poketrix.arena.report import POOLED, difference_interval, load, verdict
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


def _results(tmp_path, wins_against_max: int, max_wins_against_random: int = 190,
             wins_against_random: int = 190, pairs: int = 100, extra=()):
    """`pairs` pairs per generation for each match; player 1 wins the first `n` games."""
    games = list(extra)
    for match, wins in (("policy-maxdamage", wins_against_max),
                        ("policy-random", wins_against_random),
                        ("maxdamage-random", max_wins_against_random)):
        for gen in (1, 2, 3, 4):
            for number in range(2 * pairs):
                winner = "p1" if number < wins else "p2"
                games.append(_game(match, gen, number // 2, bool(number % 2), winner))
    path = tmp_path / "games.jsonl"
    path.write_text("\n".join(json.dumps(game) for game in games), encoding="utf-8")
    return {match: by_gen for (match, _), by_gen in load([path]).items()}


def _marks(found):
    return {mark[:2]: passed for mark, passed, _ in verdict(
        found["policy-maxdamage"], found["policy-random"], found["maxdamage-random"]
    )}


def test_the_report_counts_games_pairs_and_the_pooled_total(tmp_path):
    found = _results(tmp_path, wins_against_max=151)
    gen4, pooled = found["policy-maxdamage"][4], found["policy-maxdamage"][POOLED]
    assert (gen4.games, gen4.wins, pooled.games, pooled.wins) == (200, 151, 800, 604)
    assert gen4.pairs == {"2-0": 75, "split": 1, "0-2": 24}  # games 2n and 2n+1 are one pair
    assert pooled.win_rate == 0.755 and pooled.interval[0] == pytest.approx(0.724, abs=0.002)
    assert (pooled.decisions, pooled.share("fallback")) == (16_000, 0.0)


def test_the_pair_view_is_a_bootstrap_over_pairs(tmp_path):
    """13-A5: the pair is the independent unit, so its interval is the honest one."""
    tally = _results(tmp_path, wins_against_max=151)["policy-maxdamage"][4]
    score, low, high = tally.pair_interval()
    assert score == pytest.approx(0.755) and low < score < high
    assert (low, high) == tally.pair_interval()[1:]  # a fixed seed: the same every time
    # Pairs that are all won or all lost vary more than 200 independent games would.
    assert high - low > tally.interval[1] - tally.interval[0]


def test_the_difference_of_two_win_rates_has_newcombes_interval():
    low, high = difference_interval(56, 70, 48, 80)  # Newcombe's own worked example
    assert (low, high) == (pytest.approx(0.0524, abs=5e-4), pytest.approx(0.3339, abs=5e-4))
    low, high = difference_interval(950, 1000, 950, 1000)
    assert low == pytest.approx(-high) and -0.02 < low < 0  # equal rates: centred on zero


def test_the_verdict_applies_every_pass_mark(tmp_path):
    def marks(wins_against_max):
        return _marks(_results(tmp_path, wins_against_max, wins_against_random=199))

    assert all(marks(150).values())
    close = marks(106)  # 53%: the lower bound is under 50%
    assert not close["1a"] and close["1b"]
    assert not marks(85)["1b"]  # 42.5% in a generation


def test_against_random_the_mark_is_non_inferiority_not_a_ceiling(tmp_path):
    """13-A1: we may not trail max-damage by a clear margin, but need not beat a 95% rate."""
    def mark(ours, theirs, pairs):
        found = _results(tmp_path, 150, max_wins_against_random=theirs,
                         wins_against_random=ours, pairs=pairs)
        return _marks(found)["2."]

    assert mark(ours=950, theirs=950, pairs=500)  # level with it at 95%: enough, just
    assert mark(ours=970, theirs=950, pairs=500)
    assert not mark(ours=900, theirs=950, pairs=500)  # five points behind
    # The interval is about two points wide each way at 1,000 games, so the mark cannot tell
    # "one point behind" from "more than two", and at lower rates not even "level":
    assert not mark(ours=940, theirs=950, pairs=500)
    assert not mark(ours=900, theirs=900, pairs=500)
    assert not mark(ours=190, theirs=190, pairs=100)


def test_a_rejected_choice_or_an_error_fails_the_health_marks(tmp_path):
    broken = [_game("policy-maxdamage", 1, 999, swap, "p1", illegal=1,
                    statuses={"ok": 19, "error": 1}) for swap in (False, True)]
    marks = _marks(_results(tmp_path, wins_against_max=150, extra=broken))
    assert not marks["3a"] and not marks["3b"] and marks["3c"] and marks["3d"] and marks["3e"]


def test_a_quarantined_pair_is_counted_and_never_scored(tmp_path):
    """13-A3: a pair in which a game raised leaves the scoring whole, and is reported."""
    lost = {"match": "policy-maxdamage", "settings": {"gamma": 0.5}, "gen": 2, "index": 7,
            "quarantined": True}
    found = _results(tmp_path, wins_against_max=150, extra=[lost])
    gen2 = found["policy-maxdamage"][2]
    assert (gen2.quarantined, gen2.games, len(gen2.pair_scores)) == (1, 198, 99)
    assert gen2.quarantine_share == pytest.approx(0.01)
    assert not _marks(found)["3e"]  # 1 of 100 pairs is over the 0.5% limit
    half = [_game("policy-maxdamage", 3, 5000, False, "p1")]  # the second game never came
    assert _results(tmp_path, 150, extra=half)["policy-maxdamage"][3].games == 200
