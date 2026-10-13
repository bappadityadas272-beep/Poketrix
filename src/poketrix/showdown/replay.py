"""Whole battle logs: protocol text in, one validated snapshot per turn out."""

from pydantic import BaseModel, ConfigDict, Field

from poketrix.schemas import GameState, PlayerSlot, SetEvidence
from poketrix.schemas.pokemon import ShowdownId

from .events import Event, RequestEvent, TurnEvent
from .protocol import parse_line
from .tracker import BattleTracker


class PokemonEvidence(BaseModel):
    """The uncloaker's input for one revealed Pokémon."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    player: PlayerSlot
    team_index: int = Field(ge=0)  # position in that side's `team` in the snapshot's state
    species_id: ShowdownId  # the forme it was sent out as: its key in the set prior
    evidence: SetEvidence


class TurnSnapshot(BaseModel):
    """The battle as it stands when a turn begins (or, for the last one, when it ended).

    A player's own log gives one snapshot per decision instead: each carries the request in
    `state.me.request`, and a replacement chosen during a turn has a snapshot of its own.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn: int = Field(ge=1)
    # Position within the turn: 0 is the turn's main choice, 1 and up are replacements chosen
    # during it (and the closing snapshot). `(turn, decision_index)` identifies a snapshot.
    decision_index: int = Field(default=0, ge=0)
    final: bool = False
    state: GameState
    evidence: tuple[PokemonEvidence, ...]
    events: tuple[Event, ...]  # what happened since the previous snapshot


class BattleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format_id: str
    snapshots: tuple[TurnSnapshot, ...]
    winner: str | None
    ended: bool  # False for a log that stops before `|win|` or `|tie|`
    player: PlayerSlot | None  # whose requests the log carries; None for a spectator log
    request_disagreements: dict[str, int]  # where a request contradicted the log; empty if sound
    unknown_message_types: dict[str, int]
    rule_counts: dict[str, int]  # how often each evidence rule fired
    anomalies: tuple[str, ...]  # evidence the rules did not expect; empty for a clean log


def _snapshot(tracker: BattleTracker, perspective: PlayerSlot | None, events: list[Event],
              decision_index: int, final: bool = False) -> TurnSnapshot:
    evidence = tuple(
        PokemonEvidence(
            player=slot, team_index=index, species_id=tracker.set_species_id(slot, index),
            evidence=found,
        )
        for (slot, index), found in tracker.evidence().items()
    )
    return TurnSnapshot(
        turn=tracker.turn, decision_index=decision_index, final=final,
        state=tracker.state(perspective), evidence=evidence,
        events=tuple(events),
    )


class BattleReader:
    """Reads a battle line by line, as it happens, and hands out each snapshot when it is due.

    A live client feeds lines in the order they arrive; `parse_battle` feeds a whole log.
    """

    def __init__(self, perspective: PlayerSlot | None = None) -> None:
        self.tracker = BattleTracker()
        self._perspective = perspective
        self._pending: list[Event] = []
        self._turn_began = False  # a turn line was read and its snapshot is still to be taken
        self._last: tuple[int, int] | None = None  # (turn, decision_index) of the last snapshot

    def _take(self, final: bool = False) -> TurnSnapshot:
        tracker = self.tracker
        same_turn = self._last is not None and self._last[0] == tracker.turn
        index = self._last[1] + 1 if same_turn else 0
        snapshot = _snapshot(tracker, self._perspective, self._pending, index, final)
        self._last = (tracker.turn, index)
        self._pending, self._turn_began = [], False
        return snapshot

    def feed(self, line: str) -> TurnSnapshot | None:
        """Read one protocol line. Returns the snapshot it completes, if any: a turn's start
        (a spectator's log) or a decision (a player's own log, at the request)."""
        event = parse_line(line)
        if event is None:
            return None
        asks = isinstance(event, RequestEvent) and not event.wait
        due = None
        if self._turn_began and not asks:  # no request follows the turn line: a spectator's log
            due = self._take()
        self.tracker.apply(event)
        self._pending.append(event)
        if isinstance(event, TurnEvent):
            self._turn_began = True
        elif asks and self.tracker.turn:
            due = self._take()
        return due

    def close(self) -> TurnSnapshot | None:
        """The closing snapshot of a log that has ended, if anything happened since the last."""
        if self.tracker.turn and (self._pending or self._turn_began):
            return self._take(final=not self._turn_began)
        return None


def parse_battle(
    text: str, perspective: PlayerSlot | None = None, strict: bool = False
) -> BattleRecord:
    """Parse a spectator log (a saved replay) or a player's own log, which also has requests.

    The perspective defaults to the player whose requests the log carries, else to p1.
    `strict` makes an unknown message type an error.
    """
    reader = BattleReader(perspective)
    found = [reader.feed(line) for line in text.splitlines()]
    tracker = reader.tracker
    if strict and tracker.unknown:
        raise ValueError(f"unknown message types: {dict(tracker.unknown)}")
    found.append(reader.close())
    return BattleRecord(
        format_id=tracker.format_id,
        snapshots=tuple(snapshot for snapshot in found if snapshot is not None),
        winner=tracker.winner,
        ended=tracker.ended, player=tracker.player,
        request_disagreements=dict(tracker.disagreements),
        unknown_message_types=dict(tracker.unknown),
        rule_counts={rule: count for rule, count in tracker.rules.items() if count},
        anomalies=tuple(tracker.anomalies),
    )
