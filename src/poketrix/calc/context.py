"""Everything a damage engine looks at, resolved once per calculation (all generations)."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache

from poketrix.dex import Dex
from poketrix.schemas import (
    BattlePokemon,
    BoostStat,
    FieldState,
    Generation,
    Item,
    Move,
    MoveCategory,
    PokemonType,
    SideCondition,
    Stat,
    Status,
    Weather,
)

from .engine import SideConditions
from .stats import battle_stats, current_hp

_dex = cache(Dex)

# Defender abilities that Mold Breaker (Gen 4) switches off (the oracle's list).
MOLD_BREAKER_IGNORES = frozenset({
    "battlearmor", "clearbody", "damp", "dryskin", "filter", "flashfire", "flowergift",
    "heatproof", "hypercutter", "immunity", "innerfocus", "insomnia", "keeneye", "leafguard",
    "levitate", "lightningrod", "limber", "magmaarmor", "marvelscale", "motordrive", "oblivious",
    "owntempo", "sandveil", "shellarmor", "shielddust", "simple", "snowcloak", "solidrock",
    "soundproof", "stickyhold", "stormdrain", "sturdy", "suctioncups", "tangledfeet", "thickfat",
    "unaware", "vitalspirit", "voltabsorb", "waterabsorb", "waterveil", "whitesmoke",
    "wonderguard",
})
_WEATHER_NEGATORS = frozenset({"airlock", "cloudnine"})
# Klutz switches off the holder's item, except these, which still slow it down.
SPEED_HALVING_ITEMS = frozenset({
    "ironball", "machobrace", "poweranklet", "powerband", "powerbelt", "powerbracer",
    "powerlens", "powerweight",
})


@dataclass(frozen=True)
class Side:
    pokemon: BattlePokemon
    stats: Mapping[Stat, int]
    hp: int
    own_ability: str | None  # as held
    ability: str | None  # in effect for this calculation (None under Mold Breaker)
    held_item: Item | None  # as held
    item: Item | None  # in effect (None under Klutz)

    @property
    def max_hp(self) -> int:
        return self.stats[Stat.HP]

    @property
    def level(self) -> int:
        return self.pokemon.level

    @property
    def species_id(self) -> str:
        return self.pokemon.species.id

    @property
    def types(self) -> tuple[PokemonType, ...]:
        return self.pokemon.species.types

    @property
    def status(self) -> Status | None:
        return self.pokemon.status

    @property
    def item_id(self) -> str | None:
        return None if self.item is None else self.item.id

    def stage(self, stat: BoostStat) -> int:
        return self.pokemon.boosts.get(stat, 0)

    def has_volatile(self, volatile: str) -> bool:
        return volatile in self.pokemon.volatiles


@dataclass(frozen=True)
class Context:
    gen: Generation
    attacker: Side
    defender: Side
    move: Move
    physical: bool  # a field, not derived: before Gen 4 it follows the move's effective type
    field: FieldState
    weather: Weather  # NONE when Air Lock or Cloud Nine is on the field
    attacker_conditions: SideConditions
    defender_conditions: SideConditions

    @property
    def gravity(self) -> bool:
        return self.field.gravity_turns_left > 0

    @property
    def trick_room(self) -> bool:
        return self.field.trick_room_turns_left > 0

    def tailwind(self, side: Side) -> bool:
        conditions = self.attacker_conditions if side is self.attacker else self.defender_conditions
        return SideCondition.TAILWIND in conditions


def _own_ability(pokemon: BattlePokemon) -> str | None:
    if pokemon.known_set is not None and pokemon.known_set.ability is not None:
        return pokemon.known_set.ability
    return pokemon.revealed_ability


def _held_item(pokemon: BattlePokemon) -> Item | None:
    if pokemon.item_consumed:
        return None
    item_id = pokemon.revealed_item
    if pokemon.known_set is not None and pokemon.known_set.item is not None:
        item_id = pokemon.known_set.item
    return None if item_id is None else _dex(pokemon.generation).item(item_id)


def _side(pokemon: BattlePokemon, ability_ignored: bool) -> Side:
    stats = battle_stats(pokemon)
    own_ability = _own_ability(pokemon)
    held_item = _held_item(pokemon)
    return Side(
        pokemon=pokemon, stats=stats, hp=current_hp(pokemon, stats[Stat.HP]),
        own_ability=own_ability, ability=None if ability_ignored else own_ability,
        held_item=held_item, item=None if own_ability == "klutz" else held_item,
    )


def build_context(
    attacker: BattlePokemon, defender: BattlePokemon, move: Move, field: FieldState,
    attacker_conditions: SideConditions, defender_conditions: SideConditions,
) -> Context:
    attacker_ability, defender_ability = _own_ability(attacker), _own_ability(defender)
    mold_breaker = attacker_ability == "moldbreaker" and defender_ability in MOLD_BREAKER_IGNORES
    negated = not _WEATHER_NEGATORS.isdisjoint((attacker_ability, defender_ability))
    return Context(
        gen=attacker.generation, physical=move.category is MoveCategory.PHYSICAL,
        attacker=_side(attacker, ability_ignored=False),
        defender=_side(defender, ability_ignored=mold_breaker),
        move=move, field=field, weather=Weather.NONE if negated else field.weather,
        attacker_conditions=attacker_conditions, defender_conditions=defender_conditions,
    )
