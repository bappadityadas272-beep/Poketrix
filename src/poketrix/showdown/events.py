"""Typed events: one per Showdown protocol line that the tracker acts on.

Events are immutable and hold exactly what the line says, with names turned into ids. They are
the replayable record of a battle: applying the same events again gives the same states.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from poketrix.schemas import BoostStat, PlayerSlot, Status, Weather


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PokemonRef(_Frozen):
    """`p1a: Nickname` (on the field) or `p1: Nickname` (on the bench)."""

    player: PlayerSlot
    name: str
    active: bool


class Effect(_Frozen):
    """What a `[from]` tag or an effect argument names: `item: Leftovers`, `move: Trick`, `psn`."""

    kind: Literal["move", "item", "ability"] | None
    id: str


class Hp(_Frozen):
    """`63/100 par`, `243/301`, or `0 fnt`. Spectators see a percentage: `maximum` is then 100."""

    current: int
    maximum: int | None  # not given once the Pokémon has fainted
    status: Status | None = None
    fainted: bool = False

    @property
    def fraction(self) -> float:
        return 0.0 if self.fainted or not self.maximum else self.current / self.maximum


class Event(_Frozen):
    """Base of every event. `source` and `of` are the line's `[from]` and `[of]` tags."""

    source: Effect | None = None
    of: PokemonRef | None = None


class SetupEvent(Event):
    key: Literal["player", "teamsize", "gen", "tier", "gametype", "start"]
    player: PlayerSlot | None = None
    value: str = ""


class TurnEvent(Event):
    number: int


class UpkeepEvent(Event):
    """End-of-turn effects have been applied."""


class EndEvent(Event):
    winner: str | None  # None for a tie


class MoveEvent(Event):
    pokemon: PokemonRef
    move_id: str
    target: PokemonRef | None = None


class SwitchEvent(Event):
    pokemon: PokemonRef
    species_name: str
    level: int
    hp: Hp
    forced: bool  # dragged out by the opponent


class FormeEvent(Event):
    pokemon: PokemonRef
    species_name: str


class CantEvent(Event):
    pokemon: PokemonRef
    reason: str


class FaintEvent(Event):
    pokemon: PokemonRef


class HpEvent(Event):
    change: Literal["damage", "heal", "sethp"]
    pokemon: PokemonRef
    hp: Hp


class StatusEvent(Event):
    pokemon: PokemonRef
    status: Status
    cured: bool


class CureTeamEvent(Event):
    pokemon: PokemonRef


class BoostEvent(Event):
    op: Literal[
        "boost", "unboost", "set", "clear", "clearpositive", "clearnegative", "clearall",
        "swap", "copy",
    ]
    pokemon: PokemonRef | None = None  # None for "clearall" (Haze)
    stat: BoostStat | None = None
    amount: int = 0
    other: PokemonRef | None = None
    stats: tuple[BoostStat, ...] = ()  # the stats a swap covers; empty = all


class WeatherEvent(Event):
    weather: Weather
    upkeep: bool  # the weather continues; it did not just start


class FieldEvent(Event):
    started: bool
    condition_id: str


class SideEvent(Event):
    started: bool
    player: PlayerSlot
    condition_id: str


class VolatileEvent(Event):
    """`-start` / `-end` / `-activate`: an effect on one Pokémon begins, ends or triggers."""

    phase: Literal["start", "end", "activate"]
    pokemon: PokemonRef
    effect: Effect
    detail: str | None = None  # e.g. the move copied by Mimic


class ItemEvent(Event):
    pokemon: PokemonRef
    item_id: str
    lost: bool  # `-enditem`: eaten, used up, knocked off or taken


class AbilityEvent(Event):
    pokemon: PokemonRef
    ability_id: str | None  # None: the ability was suppressed (`-endability`)


class TransformEvent(Event):
    pokemon: PokemonRef
    target: PokemonRef


class TagEvent(Event):
    """A line we otherwise ignore (`-immune`, `-fail`, ...) that carries an item or ability tag."""

    kind: str
    pokemon: PokemonRef | None = None


class UnknownEvent(Event):
    """A message type the parser does not know. Counted, never an error."""

    kind: str
