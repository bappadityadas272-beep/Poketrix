"""Golden decisions: whole games recorded once, replayed in plain Python ever after.

A recording holds what each side received from the simulator and what it then chose. Replaying
it feeds the same lines through the reader and the players and compares every choice, so the
whole path from protocol line to decision is under test without Node or the simulator. That
makes it the proof that a refactor changed no behaviour.

Re-record only when the policy is changed on purpose, and say so in the progress tracker:

    python -m poketrix.arena record
"""

import gzip
import json
from pathlib import Path

from poketrix.advisor import PolicySettings
from poketrix.schemas import OptionScore
from poketrix.showdown import BattleReader

from .play import Bridge, MaxDamagePlayer, Player, PolicyPlayer, read_chunk

GOLDEN_FILE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "golden_decisions.json.gz"
GENS = (1, 2, 3, 4)
FIRST_INDEX = 910_000  # outside the tuning (1,000,000+) and evaluation (2,000,000+) ranges
GAMES_PER_GEN = 2
SIDES = {"p1": "policy", "p2": "maxdamage"}


def players(settings: dict) -> dict[str, Player]:
    makers = {"policy": lambda: PolicyPlayer(PolicySettings(**settings)),
              "maxdamage": MaxDamagePlayer}
    return {side: makers[kind]() for side, kind in SIDES.items()}


def record(path: Path = GOLDEN_FILE, settings: PolicySettings | None = None) -> int:
    """Play the golden games in the simulator and save them. Returns the decisions recorded."""
    used = vars(settings or PolicySettings())
    bridge = Bridge()
    games, decisions = [], 0
    for gen in GENS:
        for index in range(FIRST_INDEX, FIRST_INDEX + GAMES_PER_GEN):
            result = bridge.play(gen, index, False, players(used))
            games.append({
                "gen": gen, "index": index, "winner": result.winner,
                "sides": {
                    side: {"chunks": bridge.log[side],
                           "choices": [c.model_dump(mode="json", exclude_none=True)
                                       for c in tally.choices]}
                    for side, tally in result.sides.items()
                },
            })
            decisions += sum(len(tally.choices) for tally in result.sides.values())
    recording = {"simulator": bridge.simulator, "settings": used, "players": SIDES,
                 "games": games}
    bridge.close()
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as file:
        json.dump(recording, file)
    return decisions


def load(path: Path = GOLDEN_FILE) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as file:
        return json.load(file)


def replay(game: dict, side: str, player: Player) -> list[tuple[OptionScore, OptionScore]]:
    """Every decision of one side of a recorded game as (recorded, made now)."""
    reader = BattleReader()
    recorded = [OptionScore(**choice) for choice in game["sides"][side]["choices"]]
    made = [
        player.choose(asked).option.model_copy(update={"score": None})
        for chunk in game["sides"][side]["chunks"]
        for asked in read_chunk(reader, chunk) if not isinstance(asked, str)
    ]
    if len(made) != len(recorded):
        raise AssertionError(f"{len(made)} decisions now, {len(recorded)} recorded")
    return list(zip(recorded, made, strict=True))
