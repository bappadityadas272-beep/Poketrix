"""One battle room as the overlay follows it: lines in, in arrival order; advice out.

A room reads its battle with its own `BattleReader`. A player's own battle gives a snapshot
per decision, carrying the request; a battle watched or replayed gives one per turn, and is
advised from p1's side (`advisor.spectator`).

Fair play, enforced here: a live battle that is rated (the protocol's `|rated|` line) gets no
advice at all. Replays are exempt; they are over.
"""

from dataclasses import dataclass, field
from enum import Enum
from threading import Lock

from poketrix.advisor import TurnAdvisor
from poketrix.advisor.spectator import seen_as
from poketrix.advisor.tendency import tendency_line
from poketrix.opponent import OpponentModel
from poketrix.schemas import PlayerSlot
from poketrix.showdown import BattleReader, TurnSnapshot
from poketrix.uncloak import load_prior

from .panel import panel

RATED_MESSAGE = "Poketrix is off in rated battles"
DEMO_SIDE = PlayerSlot.P1  # a watched battle or a replay is advised from p1's side


class Source(str, Enum):
    LIVE = "live"
    REPLAY = "replay"


@dataclass
class Room:
    source: Source
    reader: BattleReader = field(default_factory=BattleReader)
    rated: bool = False
    snapshots: list[TurnSnapshot] = field(default_factory=list)
    advice: dict[int, dict] = field(default_factory=dict)  # snapshot position -> panel
    lock: Lock = field(default_factory=Lock)

    @property
    def off(self) -> bool:
        return self.rated and self.source is Source.LIVE


class Rooms:
    """Every room the overlay has been sent, kept in memory only."""

    def __init__(self, advisor: TurnAdvisor, tendency_model: OpponentModel) -> None:
        self._advisor = advisor
        self._tendency_model = tendency_model
        self._rooms: dict[str, Room] = {}
        self._lock = Lock()

    def feed(self, room_id: str, lines: list[str], source: Source) -> Room:
        """Read lines in order. The newest decision of a live battle is advised at once, so
        that the advice is ready when the panel asks."""
        with self._lock:
            room = self._rooms.setdefault(room_id, Room(source))
        with room.lock:
            for line in lines:
                if line.startswith("|rated|"):
                    room.rated = True
                found = room.reader.feed(line)
                if found is not None:
                    room.snapshots.append(found)
            if room.source is Source.LIVE and not room.off and room.snapshots:
                self._advise(room, len(room.snapshots) - 1)
        return room

    def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def advice(self, room: Room, turn: int | None = None) -> dict:
        """The panel for a turn (a replay), or for the newest decision."""
        if room.off:
            return {"status": "rated", "message": RATED_MESSAGE}
        with room.lock:
            positions = [i for i, s in enumerate(room.snapshots)
                         if turn is None or (s.turn == turn and s.decision_index == 0)]
            if not positions:
                return {"status": "waiting", "message": "No decision to advise on yet."}
            return self._advise(room, positions[-1])

    def _advise(self, room: Room, position: int) -> dict:
        if position not in room.advice:
            room.advice[position] = self._panel(room.snapshots[position])
        return room.advice[position]

    def _panel(self, snapshot: TurnSnapshot) -> dict:
        mode = "player"
        if snapshot.state.me.request is None:
            mode = f"spectator, advising {DEMO_SIDE.value}"
            snapshot = seen_as(snapshot, DEMO_SIDE, load_prior(snapshot.state.generation),
                               switches=True)
            if snapshot is None:
                return {"status": "waiting", "message": "No set can be named for p1's Pokémon."}
        report = self._advisor.advise(snapshot)
        return panel(snapshot, report, tendency_line(snapshot, report, self._tendency_model),
                     mode)
