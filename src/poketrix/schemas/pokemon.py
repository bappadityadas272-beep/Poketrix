"""Static dex data (Species, Move) and per-battle Pokémon state.

Split of responsibility:
- these schemas guarantee *structure* and *generation legality*
  (e.g. no held item in Gen 1, no Dark type in Gen 1, DVs capped at 15 in Gens 1-2);
- the dex layer (later task) guarantees *content* (that "stoneedge" really exists, its real power).
"""

import re
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from typing_extensions import Self

from .enums import (
    BoostStat,
    FixedDamage,
    Generation,
    MoveCategory,
    MoveFlag,
    PokemonType,
    Stat,
    Status,
)
from .generation import category_for_type, rules_for

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def to_id(name: str) -> str:
    """Showdown id normalisation: 'Stone Edge' -> 'stoneedge', "Farfetch'd" -> 'farfetchd'."""
    return _NON_ALNUM.sub("", str(name).lower())


ShowdownId = Annotated[
    str,
    BeforeValidator(lambda v: to_id(v) if isinstance(v, str) else v),
    StringConstraints(min_length=1, pattern=r"^[a-z0-9]+$"),
]


class Strict(BaseModel):
    """Base for every Poketrix schema: no unknown fields, no silent coercion surprises."""

    model_config = ConfigDict(extra="forbid", frozen=False, validate_assignment=True)


# --------------------------------------------------------------------------- static dex data


class BaseStats(Strict):
    hp: int = Field(ge=1, le=255)
    atk: int = Field(ge=1, le=255)
    def_: int = Field(ge=1, le=255, alias="def")
    spa: int = Field(ge=1, le=255)
    spd: int = Field(ge=1, le=255)
    spe: int = Field(ge=1, le=255)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Species(Strict):
    """A species *as it exists in one generation* (stats and types changed across gens)."""

    id: ShowdownId
    name: str
    generation: Generation
    dex_number: int = Field(ge=1)
    types: tuple[PokemonType] | tuple[PokemonType, PokemonType]
    base_stats: BaseStats
    weight_kg: float = Field(gt=0)
    possible_abilities: list[ShowdownId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _gen_legal(self) -> Self:
        r = rules_for(self.generation)
        if self.dex_number > r.max_dex:
            raise ValueError(f"dex #{self.dex_number} does not exist in Gen {self.generation}")
        bad = [t.value for t in self.types if t not in r.pokemon_types]
        if bad:
            raise ValueError(f"type(s) {bad} not available to Pokémon in Gen {self.generation}")
        if len(set(self.types)) != len(self.types):
            raise ValueError("duplicate types")
        if r.unified_special and self.base_stats.spa != self.base_stats.spd:
            raise ValueError("Gen 1 has a single Special stat: base spa must equal spd")
        if self.possible_abilities and not r.has_abilities:
            raise ValueError(f"abilities do not exist in Gen {self.generation}")
        return self


class Move(Strict):
    id: ShowdownId
    name: str
    generation: Generation
    type: PokemonType
    category: MoveCategory
    base_power: int = Field(ge=0, le=255)  # 0 for status / fixed-damage moves
    accuracy: int | None = Field(default=None, ge=1, le=100)  # None = never misses
    pp: int = Field(ge=1, le=64)
    priority: int = Field(default=0, ge=-7, le=5)
    # Set when the move bypasses the damage formula; an int is a flat amount (Sonic Boom = 20).
    fixed_damage: Annotated[int, Field(ge=1)] | FixedDamage | None = None
    # Typeless damage: no type effectiveness and no STAB (Struggle from Gen 2, Gen 1 Bide).
    ignores_type_chart: bool = False
    crit_ratio: int = Field(default=1, ge=1, le=6)  # Showdown's critRatio; 1 = normal
    multihit: tuple[int, int] | None = None  # (min, max) hits per use
    flags: frozenset[MoveFlag] = frozenset()

    @model_validator(mode="after")
    def _gen_legal(self) -> Self:
        r = rules_for(self.generation)
        if self.fixed_damage is not None and (
            self.base_power != 0 or self.category is MoveCategory.STATUS
        ):
            raise ValueError("a fixed-damage move is a damaging move with base power 0")
        if self.multihit is not None and not 1 <= self.multihit[0] <= self.multihit[1] <= 5:
            raise ValueError("multihit must be (min, max) with 1 <= min <= max <= 5")
        if self.type not in r.move_types:
            raise ValueError(f"move type {self.type.value} not available in Gen {self.generation}")
        if (
            not r.physical_special_split
            and self.category is not MoveCategory.STATUS
            and self.category is not category_for_type(self.type)
        ):
            raise ValueError(
                f"before Gen 4 a {self.type.value}-type damaging move must be "
                f"{category_for_type(self.type).value}"
            )
        return self


class Item(Strict):
    """A held item *as it exists in one generation*, with the data the Math layer keys on."""

    id: ShowdownId
    name: str
    generation: Generation
    boosts_type: PokemonType | None = None  # powers up moves of this type (Charcoal, plates)
    plate_type: PokemonType | None = None  # Judgment's type while held
    resists_type: PokemonType | None = None  # berry that halves one hit of this type
    fling_power: int | None = Field(default=None, ge=1, le=255)
    natural_gift_type: PokemonType | None = None
    natural_gift_power: int | None = Field(default=None, ge=1, le=255)

    @model_validator(mode="after")
    def _gen_legal(self) -> Self:
        r = rules_for(self.generation)
        if not r.has_items:
            raise ValueError(f"held items do not exist in Gen {self.generation}")
        types = (self.boosts_type, self.plate_type, self.resists_type, self.natural_gift_type)
        bad = [t.value for t in types if t is not None and t not in r.pokemon_types]
        if bad:
            raise ValueError(f"type(s) {bad} not available in Gen {self.generation}")
        if (self.natural_gift_type is None) != (self.natural_gift_power is None):
            raise ValueError("Natural Gift type and power go together")
        return self


class Nature(Strict):
    """A nature raises one stat by 10% and lowers another; neutral natures do neither."""

    id: ShowdownId
    plus: Stat | None = None
    minus: Stat | None = None

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if (self.plus is None) != (self.minus is None):
            raise ValueError("a nature raises and lowers a stat, or neither")
        if Stat.HP in (self.plus, self.minus):
            raise ValueError("natures never affect HP")
        return self


# --------------------------------------------------------------------------- sets & spreads


class StatSpread(Strict):
    """IVs + EVs. In Gens 1-2 these hold DVs (0-15) and Stat Exp (0-65535)."""

    ivs: dict[Stat, int] = Field(default_factory=dict)  # missing stat = max (Showdown default)
    evs: dict[Stat, int] = Field(default_factory=dict)  # missing stat = 0 (Gen 3+) / max (Gen 1-2)

    def validate_for(self, gen: Generation) -> None:
        r = rules_for(gen)
        for stat, v in self.ivs.items():
            if not 0 <= v <= r.iv_max:
                raise ValueError(f"{stat.value} IV/DV {v} outside 0..{r.iv_max} for Gen {gen}")
        for stat, v in self.evs.items():
            if not 0 <= v <= r.ev_max_per_stat:
                raise ValueError(
                    f"{stat.value} EV/StatExp {v} outside 0..{r.ev_max_per_stat} for Gen {gen}"
                )
        if r.ev_max_total is not None and sum(self.evs.values()) > r.ev_max_total:
            raise ValueError(f"EV total {sum(self.evs.values())} exceeds {r.ev_max_total}")
        if gen <= Generation.GSC:
            # One Special DV and one Special Stat Exp are shared by SpA and SpD in Gens 1-2.
            for name, d in (("DV", self.ivs), ("Stat Exp", self.evs)):
                if d.get(Stat.SPA, None) != d.get(Stat.SPD, None):
                    raise ValueError(f"Gen {gen}: Special {name} must be identical for spa/spd")
            if Stat.HP in self.ivs:
                expected = gen1_2_hp_dv(self.ivs, r.iv_max)
                if self.ivs[Stat.HP] != expected:
                    raise ValueError(f"Gen {gen}: HP DV is derived; expected {expected}")


def gen1_2_hp_dv(ivs: dict[Stat, int], default: int = 15) -> int:
    """HP DV = low bits of Atk, Def, Spe, Spc DVs."""
    atk, df, spe, spc = (ivs.get(s, default) for s in (Stat.ATK, Stat.DEF, Stat.SPE, Stat.SPA))
    return (atk & 1) * 8 + (df & 1) * 4 + (spe & 1) * 2 + (spc & 1)


class PokemonSet(Strict):
    """A fully specified set (your own Pokémon, or one hypothesis about an opponent's)."""

    species: Species
    level: int = Field(default=100, ge=1, le=100)
    moves: list[ShowdownId] = Field(min_length=1, max_length=4)
    item: ShowdownId | None = None
    ability: ShowdownId | None = None
    nature: ShowdownId | None = None
    spread: StatSpread = Field(default_factory=StatSpread)

    @property
    def generation(self) -> Generation:
        return self.species.generation

    @model_validator(mode="after")
    def _gen_legal(self) -> Self:
        gen = self.generation
        r = rules_for(gen)
        if len(set(self.moves)) != len(self.moves):
            raise ValueError("duplicate moves in set")
        if self.item is not None and not r.has_items:
            raise ValueError(f"held items do not exist in Gen {gen}")
        if self.ability is not None and not r.has_abilities:
            raise ValueError(f"abilities do not exist in Gen {gen}")
        abilities = self.species.possible_abilities
        if self.ability is not None and abilities and self.ability not in abilities:
            raise ValueError(f"{self.species.name} cannot have ability {self.ability}")
        if self.nature is not None and not r.has_natures:
            raise ValueError(f"natures do not exist in Gen {gen}")
        self.spread.validate_for(gen)
        return self


# --------------------------------------------------------------------------- in-battle state


class BattlePokemon(Strict):
    """One team slot as seen *during* a battle.

    For our own side `known_set` is filled in. For the opponent only what has been revealed is
    known; the Bayesian layer produces a posterior over the rest (see outputs.SetPosterior).
    """

    species: Species
    level: int = Field(default=100, ge=1, le=100)
    hp_fraction: float = Field(ge=0.0, le=1.0)  # what Showdown shows for both sides
    hp_current: int | None = Field(default=None, ge=0)  # exact, own side only
    hp_max: int | None = Field(default=None, ge=1)
    status: Status | None = None
    boosts: dict[BoostStat, int] = Field(default_factory=dict)
    volatiles: set[ShowdownId] = Field(default_factory=set)  # confusion, substitute, leechseed…
    revealed_moves: list[ShowdownId] = Field(default_factory=list, max_length=4)
    revealed_item: ShowdownId | None = None
    item_consumed: bool = False  # e.g. Leftovers knocked off, berry eaten
    revealed_ability: ShowdownId | None = None
    known_set: PokemonSet | None = None

    @property
    def fainted(self) -> bool:
        return self.hp_fraction == 0.0

    @property
    def generation(self) -> Generation:
        return self.species.generation

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        gen = self.generation
        r = rules_for(gen)
        for stat, stage in self.boosts.items():
            if not -6 <= stage <= 6:
                raise ValueError(f"boost {stat.value}={stage} outside -6..6")
        if r.unified_special and self.boosts.get(BoostStat.SPA, 0) != self.boosts.get(
            BoostStat.SPD, 0
        ):
            raise ValueError("Gen 1: Special boosts must be equal for spa/spd")
        if (self.revealed_item or self.item_consumed) and not r.has_items:
            raise ValueError(f"held items do not exist in Gen {gen}")
        if self.revealed_ability and not r.has_abilities:
            raise ValueError(f"abilities do not exist in Gen {gen}")
        if len(set(self.revealed_moves)) != len(self.revealed_moves):
            raise ValueError("duplicate revealed moves")
        if (self.hp_current is None) != (self.hp_max is None):
            raise ValueError("hp_current and hp_max must be given together")
        if self.hp_current is not None and self.hp_max is not None:
            if self.hp_current > self.hp_max:
                raise ValueError("hp_current > hp_max")
            if abs(self.hp_current / self.hp_max - self.hp_fraction) > 0.01:
                raise ValueError("hp_fraction disagrees with hp_current/hp_max")
        if self.fainted and self.status is not None:
            raise ValueError("a fainted Pokémon has no status")
        if self.known_set is not None:
            ks = self.known_set
            if ks.species.id != self.species.id or ks.generation != gen:
                raise ValueError("known_set is for a different species or generation")
            if ks.level != self.level:
                raise ValueError("known_set level differs from battle level")
            missing = set(self.revealed_moves) - set(ks.moves)
            if missing:
                raise ValueError(f"revealed moves {sorted(missing)} are not in known_set")
        return self
