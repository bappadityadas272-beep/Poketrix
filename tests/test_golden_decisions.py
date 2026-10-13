"""Golden decisions: recorded games replayed without the simulator. Every choice of both
players must come out exactly as recorded, so any change to the parser, the engines, the
uncloaker or the policy that alters a decision is caught here. Re-record on purpose only:
`python -m poketrix.arena record`, and note it in the progress tracker."""

import pytest

from poketrix.arena.golden import GENS, SIDES, load, players, replay

RECORDING = load()
GAMES = [(game, side) for game in RECORDING["games"] for side in SIDES]


def test_the_recording_covers_two_games_of_every_generation():
    assert sorted(game["gen"] for game in RECORDING["games"]) == sorted([*GENS, *GENS])
    assert all(len(game["sides"][side]["choices"]) > 5 for game, side in GAMES)


@pytest.mark.slow
@pytest.mark.parametrize(("game", "side"), GAMES,
                         ids=[f"gen{g['gen']}-{g['index']}-{s}" for g, s in GAMES])
def test_every_recorded_decision_is_made_again(game, side):
    player = players(RECORDING["settings"])[side]
    for number, (recorded, made) in enumerate(replay(game, side, player)):
        assert made == recorded, f"decision {number} of {SIDES[side]}"
