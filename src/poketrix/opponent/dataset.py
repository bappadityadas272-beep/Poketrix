"""The training data of the opponent model: one row per voluntary decision in real ladder games.

A replay is a spectator's log, so both players' decisions count. For each one the row holds
what the *other* player could see when it was made, computed by the turn engine's own stages
(the same code that builds the view during a game), and what was then chosen.

A spectator's log gives neither player a known set, while the engine needs one for the
Pokémon facing the decider. That Pokémon is given its most likely set under the evidence so
far, as if its owner were watching: during a game the owner knows the real one.

A decider that fainted before acting, or could not move (asleep, frozen, fully paralysed,
flinched, infatuated), stayed in: it chose a move, but the log does not say which. Such a row
is labelled `stay`, so that leaving these turns out does not inflate the switch rate (ruled by
the user, 2026-10-15). The model is trained on it as attack and utility in the shares its
generation shows when the move is visible, and scored on it by P(attack) + P(utility).

Rows are left out when the log does not show a free choice: the decider continued a locked or
two-turn move, recharged, loafed (Truant), was dragged out, or the engine could compute nothing
for the position (a transformed Pokémon, no known set).

Build it with:  python -m poketrix.opponent.dataset [replay directory] [output file]
"""

import json
import random
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from poketrix.advisor import Deadline, stages
from poketrix.advisor.situation import Situation
from poketrix.dex import Dex, UnknownDexEntryError
from poketrix.schemas import ActionRequest, Generation, MoveCategory, PlayerSlot
from poketrix.showdown import TurnSnapshot, UnsupportedBattleError, parse_battle
from poketrix.showdown import events as ev
from poketrix.showdown.corpus import REPLAY_DIR, is_ladder_game, load_replays
from poketrix.uncloak import SetPrior, Uncloaker, hypothesis_set, load_prior

from .features import ACTIONS, DecisionView

DATASET_FILE = REPLAY_DIR.parent / "opponent" / "decisions.jsonl"  # git-ignored, like the replays
SPLIT_SEED = 20261501
SPLITS = {"train": 0.70, "valid": 0.15, "test": 0.15}
_OTHER = {PlayerSlot.P1: PlayerSlot.P2, PlayerSlot.P2: PlayerSlot.P1}
_NO_DEADLINE = Deadline(float("inf"))
_HIDDEN = "the choice was not shown"  # `actions` marks a side whose turn gives no row
STAYED = "stay"  # it chose a move, which the log does not show
_KEPT_FROM_MOVING = frozenset({"slp", "frz", "par", "flinch", "Attract"})  # `cant` reasons
# Moves that go on for more than one turn, leaving their user no choice meanwhile.
_LOCKING = frozenset({
    "rollout", "iceball", "outrage", "thrash", "petaldance", "uproar", "bide", "solarbeam",
    "skyattack", "skullbash", "razorwind", "fly", "dig", "dive", "bounce", "shadowforce",
})


@dataclass(frozen=True)
class Row:
    battle: str
    gen: int
    turn: int
    player: str
    action: str  # one of `features.ACTIONS`, or `STAYED`
    features: tuple[float, ...]
    split: str = ""


# --------------------------------------------------------------------------- labels


def actions(events: Sequence[ev.Event], dex: Dex,
            before: Sequence[ev.Event] = ()) -> dict[PlayerSlot, str]:
    """What each side freely chose in the turn these events tell: its first event decides.
    `before` is the previous turn, which shows the moves that were still going on."""
    going_on = _locking_moves(before)
    seen: dict[PlayerSlot, str] = {}
    for event in events:
        if isinstance(event, ev.MoveEvent):
            player = event.pokemon.player
            locked = going_on.get(player) == (event.pokemon.name, event.move_id)
            seen.setdefault(player, _HIDDEN if locked else _move_action(event, dex))
        elif isinstance(event, ev.SwitchEvent):
            seen.setdefault(event.pokemon.player, _HIDDEN if event.forced else "switch")
        elif isinstance(event, ev.FaintEvent):
            seen.setdefault(event.pokemon.player, STAYED)
        elif isinstance(event, ev.CantEvent):
            stayed = event.reason in _KEPT_FROM_MOVING
            seen.setdefault(event.pokemon.player, STAYED if stayed else _HIDDEN)
    return {player: action for player, action in seen.items() if action != _HIDDEN}


def _locking_moves(events: Sequence[ev.Event]) -> dict[PlayerSlot, tuple[str, str]]:
    """The locking move each side's Pokémon used last in a turn, if it then stayed in: the
    same move next turn is its continuation. Gen 2 logs do not tag one, so a move chosen
    again right after its lock ended is taken for one too: when in doubt, no row."""
    last: dict[PlayerSlot, tuple[str, str]] = {}
    for event in events:
        if isinstance(event, ev.MoveEvent):
            last[event.pokemon.player] = (event.pokemon.name, event.move_id)
        elif isinstance(event, ev.SwitchEvent):
            last.pop(event.pokemon.player, None)
    return {player: used for player, used in last.items() if used[1] in _LOCKING}


def _move_action(event: ev.MoveEvent, dex: Dex) -> str:
    if event.source is not None:  # a locked move going on, or a move called by another
        return _HIDDEN
    try:
        status = dex.move(event.move_id).category is MoveCategory.STATUS
    except UnknownDexEntryError:
        return _HIDDEN
    return "utility" if status else "attack"


# --------------------------------------------------------------------------- features


def observed(snapshot: TurnSnapshot, observer: PlayerSlot, prior: SetPrior) -> Situation | None:
    """The turn as `observer` would meet it in a game: its active Pokémon has a set (the most
    likely one) and a request offers that set's moves. None when no set can be named."""
    side = snapshot.state.sides[observer]
    found = next((f for f in snapshot.evidence
                  if f.player is observer and f.team_index == side.active_index), None)
    if found is None or side.active.fainted:
        return None
    posterior = Uncloaker(prior).uncloak(found.species_id, found.evidence).payload
    if posterior is None:
        return None
    likeliest = max(posterior.hypotheses, key=lambda hypothesis: hypothesis.posterior)
    known = hypothesis_set(side.active, likeliest, prior)
    team = list(side.team)
    team[side.active_index] = side.active.model_copy(update={"known_set": known})
    request = ActionRequest(available_moves=known.moves)
    state = snapshot.state.model_copy(update={
        "perspective": observer,
        "sides": snapshot.state.sides
        | {observer: side.model_copy(update={"team": team, "request": request})},
    })
    return Situation(snapshot.model_copy(update={"state": state}), prior, Dex(prior.gen))


def view_of(snapshot: TurnSnapshot, decider: PlayerSlot, prior: SetPrior) -> DecisionView | None:
    """`decider`'s decision at this snapshot, as its opponent sees it. None in the positions
    where the turn engine predicts nothing either."""
    situation = observed(snapshot, _OTHER[decider], prior)
    if situation is None or situation.transformed or situation.theirs.fainted:
        return None
    index = situation.them.active_index
    posterior = Uncloaker(prior).uncloak(*situation.evidence(index)).payload
    if posterior is None:
        return None
    numbers: dict[str, float] = {}
    work = (situation, posterior, _NO_DEADLINE, numbers)
    active = situation.me.active_index
    return stages.opponent_view(
        situation, posterior,
        stages.read_threats(*work)[0].by_target.get(active),
        stages.read_offence(*work)[0].by_attacker.get(active, []),
        stages.read_order(*work)[0].first.get(active, {}),
    )


def rows_of(battle: str, log: str) -> list[Row]:
    """Every labelled decision of one replay. Raises what the parser raises."""
    record = parse_battle(log)
    if not record.snapshots:
        return []
    gen = record.snapshots[0].state.generation
    prior, dex = load_prior(gen), Dex(gen)
    rows = []
    for snapshot, following in zip(record.snapshots, record.snapshots[1:], strict=False):
        for player, action in actions(following.events, dex, snapshot.events).items():
            view = view_of(snapshot, player, prior)
            if view is not None:
                rows.append(Row(battle, int(gen), snapshot.turn, player.value, action,
                                view.vector()))
    return rows


# --------------------------------------------------------------------------- the whole corpus


def split(battles: Iterable[tuple[int, str]], seed: int = SPLIT_SEED) -> dict[str, str]:
    """Battle id -> train, valid or test: whole battles, in the same shares in every
    generation. The same battles and seed always give the same split."""
    by_gen: dict[int, list[str]] = {}
    for gen, battle in battles:
        by_gen.setdefault(gen, []).append(battle)
    assigned = {}
    for gen, ids in sorted(by_gen.items()):
        ids = sorted(set(ids))
        random.Random(seed + gen).shuffle(ids)
        train = round(SPLITS["train"] * len(ids))
        valid = train + round(SPLITS["valid"] * len(ids))
        for position, battle in enumerate(ids):
            name = "train" if position < train else "valid" if position < valid else "test"
            assigned[battle] = name
    return assigned


def _rows_or_reason(replay: tuple[str, str]) -> list[Row] | str:
    battle, log = replay
    if not is_ladder_game(log):
        return "not a ladder game"
    try:
        return rows_of(battle, log) or "no labelled decision"
    except UnsupportedBattleError as error:
        return f"out of scope: {error}"
    except Exception as error:  # noqa: BLE001 - a replay the parser refuses is left out, counted
        return f"raised {type(error).__name__}"


def build(directory: Path = REPLAY_DIR) -> tuple[list[Row], Counter]:
    """All rows, each with its split, and why each left-out replay was left out."""
    replays = [replay for gen in Generation for replay in load_replays(gen, directory)]
    rows: list[Row] = []
    left_out: Counter = Counter()
    with ProcessPoolExecutor() as workers:
        for found in workers.map(_rows_or_reason, replays, chunksize=8):
            if isinstance(found, str):
                left_out[found] += 1
            else:
                rows += found
    assigned = split({(row.gen, row.battle) for row in rows})
    return [replace(row, split=assigned[row.battle]) for row in rows], left_out


def save(rows: Iterable[Row], path: Path = DATASET_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(vars(row)) + "\n")


def load(path: Path = DATASET_FILE) -> Iterator[Row]:
    with path.open(encoding="utf-8") as file:
        for line in file:
            fields = json.loads(line)
            yield Row(**fields | {"features": tuple(fields["features"])})


def main() -> None:
    directory = Path(sys.argv[1]) if sys.argv[1:] else REPLAY_DIR
    path = Path(sys.argv[2]) if sys.argv[2:] else DATASET_FILE
    rows, left_out = build(directory)
    save(rows, path)
    print(f"{len(rows)} decisions written to {path}\n")
    print("| Gen | Split | Battles | Decisions | " + " | ".join((*ACTIONS, STAYED)) + " |")
    print("|-----|-------|---------|-----------|" + "---|" * (len(ACTIONS) + 1))
    for gen in sorted({row.gen for row in rows}):
        for name in SPLITS:
            part = [row for row in rows if row.gen == gen and row.split == name]
            chosen = Counter(row.action for row in part)
            shares = " | ".join(f"{chosen[action] / max(1, len(part)):.1%}"
                                for action in (*ACTIONS, STAYED))
            print(f"| {gen} | {name} | {len({row.battle for row in part})} | {len(part)} "
                  f"| {shares} |")
    print("\nReplays left out:", dict(left_out) or "none")


if __name__ == "__main__":
    main()
