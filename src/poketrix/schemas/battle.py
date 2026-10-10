"""GameState: the single contract every ingestion source (Showdown parser now, vision later)
must produce, and every subsystem consumes."""

from pydantic import Field, model_validator
from typing_extensions import Self

from .enums import Generation, PlayerSlot, SideCondition, Weather
from .generation import rules_for
from .pokemon import BattlePokemon, ShowdownId, Strict

HAZARDS = frozenset({SideCondition.SPIKES, SideCondition.TOXIC_SPIKES, SideCondition.STEALTH_ROCK})


class FieldState(Strict):
    weather: Weather = Weather.NONE
    weather_turns_left: int | None = Field(default=None, ge=0, le=8)
    trick_room_turns_left: int = Field(default=0, ge=0, le=5)  # Gen 4
    gravity_turns_left: int = Field(default=0, ge=0, le=5)  # Gen 4


class ActionRequest(Strict):
    """What *we* are legally allowed to do this turn (from Showdown's |request| message).

    This is what the synthesis guardrail checks the LLM's recommendation against.
    """

    available_moves: list[ShowdownId] = Field(default_factory=list, max_length=4)
    available_switches: list[int] = Field(default_factory=list)  # team indices
    force_switch: bool = False  # our active fainted / was phazed

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if self.force_switch and self.available_moves:
            raise ValueError("a forced switch allows no moves")
        if not self.available_moves and not self.available_switches:
            raise ValueError("request offers no legal action")
        return self


class SideState(Strict):
    player: PlayerSlot
    name: str | None = None
    team: list[BattlePokemon] = Field(min_length=1, max_length=6)  # opponent: revealed so far
    team_size: int = Field(default=6, ge=1, le=6)  # total, including unrevealed
    active_index: int | None = Field(default=None, ge=0)
    conditions: dict[SideCondition, int] = Field(default_factory=dict)  # condition -> layers/turns
    request: ActionRequest | None = None  # only set on our own side

    @property
    def active(self) -> BattlePokemon | None:
        return None if self.active_index is None else self.team[self.active_index]

    @property
    def alive_count(self) -> int:
        unrevealed = self.team_size - len(self.team)
        return sum(not p.fainted for p in self.team) + unrevealed

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(self.team) > self.team_size:
            raise ValueError("more Pokémon listed than team_size")
        if self.active_index is not None and self.active_index >= len(self.team):
            raise ValueError("active_index out of range")
        if self.request is not None:
            for i in self.request.available_switches:
                if not 0 <= i < len(self.team):
                    raise ValueError(f"switch target {i} out of range")
                if i == self.active_index:
                    raise ValueError("cannot switch to the active Pokémon")
                if self.team[i].fainted:
                    raise ValueError(f"switch target {i} is fainted")
            if self.request.available_moves and self.active is not None:
                ks = self.active.known_set
                if ks is not None:
                    bad = set(self.request.available_moves) - set(ks.moves)
                    if bad:
                        raise ValueError(f"request offers moves {sorted(bad)} not in known set")
        return self


class GameState(Strict):
    generation: Generation
    format_id: ShowdownId  # e.g. "gen4randombattle"
    battle_id: str | None = None
    turn: int = Field(ge=0)
    perspective: PlayerSlot  # which side is "us"
    sides: dict[PlayerSlot, SideState]
    field: FieldState = Field(default_factory=FieldState)

    @property
    def me(self) -> SideState:
        return self.sides[self.perspective]

    @property
    def opponent(self) -> SideState:
        other = PlayerSlot.P2 if self.perspective is PlayerSlot.P1 else PlayerSlot.P1
        return self.sides[other]

    @model_validator(mode="after")
    def _gen_legal(self) -> Self:
        gen = self.generation
        r = rules_for(gen)
        if not self.format_id.startswith(f"gen{int(gen)}"):
            raise ValueError(f"format {self.format_id!r} does not match Gen {int(gen)}")
        if set(self.sides) != {PlayerSlot.P1, PlayerSlot.P2}:
            raise ValueError("both p1 and p2 sides are required")
        for slot, side in self.sides.items():
            if side.player is not slot:
                raise ValueError(f"side keyed {slot.value} claims to be {side.player.value}")
            for mon in side.team:
                if mon.generation != gen:
                    raise ValueError(
                        f"{mon.species.name} is Gen {int(mon.generation)} data in a Gen {int(gen)} battle"
                    )
            for cond, layers in side.conditions.items():
                max_layers = r.side_condition_max_layers.get(cond)
                if max_layers is None:
                    raise ValueError(f"{cond.value} does not exist in Gen {int(gen)}")
                # hazards store layers; everything else stores turns left (screens ≤ 8)
                upper = max_layers if cond in HAZARDS else 8
                if not 1 <= layers <= upper:
                    raise ValueError(f"{cond.value}={layers} outside 1..{upper} in Gen {int(gen)}")
        if self.field.weather not in r.weathers:
            raise ValueError(f"weather {self.field.weather.value} does not exist in Gen {int(gen)}")
        if gen < Generation.DPP and (self.field.trick_room_turns_left or self.field.gravity_turns_left):
            raise ValueError("Trick Room / Gravity only exist from Gen 4")
        if self.opponent.request is not None:
            raise ValueError("we cannot know the opponent's request")
        return self
