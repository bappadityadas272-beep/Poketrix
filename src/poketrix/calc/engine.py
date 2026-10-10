"""The contract every generation's damage engine implements, and the engine registry."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from poketrix.schemas import BattlePokemon, FieldState, Generation, Move, SideCondition

SideConditions = Mapping[SideCondition, int]
NO_CONDITIONS: SideConditions = MappingProxyType({})


class UnsupportedMoveError(Exception):
    """Raised inside an engine when it cannot produce a trustworthy number; the reason is the
    message, which the engine reports as `Outcome.unsupported_reason`."""


@dataclass(frozen=True)
class DamageResult:
    """Raw engine output. A single roll means fixed damage, an immune matchup or a failed move."""

    rolls: tuple[int, ...]  # one hit
    crit_rolls: tuple[int, ...] | None  # None when a critical hit is impossible or changes nothing
    type_multiplier: float
    crit_chance: float
    hit_distribution: Mapping[int, float] | None = None  # multi-hit moves: hits per use -> odds
    hits_share_roll: bool = False  # Gen 1: every hit of a use repeats the first hit's damage


@dataclass(frozen=True)
class Outcome:
    """Everything an engine knows about one move in one matchup."""

    hit_chance: float
    damage: DamageResult | None  # None for a status move or an unsupported one
    unsupported_reason: str | None  # set when a damaging move cannot be evaluated
    defender_hp: int
    defender_max_hp: int


class DamageEngine(Protocol):
    def evaluate(
        self, attacker: BattlePokemon, defender: BattlePokemon, move: Move, field: FieldState,
        defender_conditions: SideConditions = NO_CONDITIONS,
        attacker_conditions: SideConditions = NO_CONDITIONS,
    ) -> Outcome:
        """Hit chance and damage rolls of one move. Never guesses: see Outcome."""


_ENGINES: dict[Generation, DamageEngine] = {}


def register_engine(gen: Generation, engine: DamageEngine) -> None:
    _ENGINES[gen] = engine


def engine_for(gen: Generation | int) -> DamageEngine:
    try:
        return _ENGINES[Generation(gen)]
    except KeyError:
        raise NotImplementedError(f"no damage engine for Gen {int(gen)} yet") from None
