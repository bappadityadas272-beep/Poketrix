"""Whole battle logs: protocol text in, one validated snapshot per turn out."""

from pydantic import BaseModel, ConfigDict, Field

from poketrix.schemas import GameState, PlayerSlot, SetEvidence
from poketrix.schemas.pokemon import ShowdownId

from .events import Event, TurnEvent
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
    """The battle as it stands when a turn begins (or, for the last one, when it ended)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn: int = Field(ge=1)
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
    unknown_message_types: dict[str, int]
    rule_counts: dict[str, int]  # how often each evidence rule fired
    anomalies: tuple[str, ...]  # evidence the rules did not expect; empty for a clean log


def _snapshot(tracker: BattleTracker, perspective: PlayerSlot, events: list[Event],
              final: bool = False) -> TurnSnapshot:
    evidence = tuple(
        PokemonEvidence(
            player=slot, team_index=index, species_id=tracker.set_species_id(slot, index),
            evidence=found,
        )
        for (slot, index), found in tracker.evidence().items()
    )
    return TurnSnapshot(
        turn=tracker.turn, final=final, state=tracker.state(perspective), evidence=evidence,
        events=tuple(events),
    )


def parse_battle(
    text: str, perspective: PlayerSlot = PlayerSlot.P1, strict: bool = False
) -> BattleRecord:
    """Parse a spectator log (a saved replay). `strict` makes an unknown message type an error."""
    tracker = BattleTracker()
    snapshots: list[TurnSnapshot] = []
    pending: list[Event] = []
    for line in text.splitlines():
        event = parse_line(line)
        if event is None:
            continue
        tracker.apply(event)
        pending.append(event)
        if isinstance(event, TurnEvent):
            snapshots.append(_snapshot(tracker, perspective, pending))
            pending = []
    if strict and tracker.unknown:
        raise ValueError(f"unknown message types: {dict(tracker.unknown)}")
    if tracker.turn and pending:
        snapshots.append(_snapshot(tracker, perspective, pending, final=True))
    return BattleRecord(
        format_id=tracker.format_id, snapshots=tuple(snapshots), winner=tracker.winner,
        ended=tracker.ended, unknown_message_types=dict(tracker.unknown),
        rule_counts={rule: count for rule, count in tracker.rules.items() if count},
        anomalies=tuple(tracker.anomalies),
    )
