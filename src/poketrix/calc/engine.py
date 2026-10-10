"""The contract every generation's damage engine implements, and the engine registry."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from poketrix.schemas import BattlePokemon, FieldState, Generation, Move, SideCondition

SideConditions = Mapping[SideCondition, int]


class UnsupportedMoveError(Exception):
    """The engine cannot produce a trustworthy number for this move; the reason is the message."""


@dataclass(frozen=True)
class DamageResult:
    """Raw engine output. A single roll means fixed damage or an immune matchup."""

    rolls: tuple[int, ...]
    crit_rolls: tuple[int, ...] | None  # None when a critical hit changes nothing
    type_multiplier: float
    crit_chance: float


class DamageEngine(Protocol):
    def damage(
        self, attacker: BattlePokemon, defender: BattlePokemon, move: Move,
        field: FieldState, defender_conditions: SideConditions,
    ) -> DamageResult:
        """Damage rolls of a damaging move. Raises UnsupportedMoveError if it cannot tell."""

    def hit_chance(self, attacker: BattlePokemon, defender: BattlePokemon, move: Move) -> float:
        """Probability that the move lands, from accuracy and accuracy/evasion stages."""


_ENGINES: dict[Generation, DamageEngine] = {}


def register_engine(gen: Generation, engine: DamageEngine) -> None:
    _ENGINES[gen] = engine


def engine_for(gen: Generation | int) -> DamageEngine:
    try:
        return _ENGINES[Generation(gen)]
    except KeyError:
        raise NotImplementedError(f"no damage engine for Gen {int(gen)} yet") from None
