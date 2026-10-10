"""Gen 1 (RBY) and Gen 2 (GSC) damage engines.

The two generations share one formula: stats are capped to a byte, the 39 random factors run
from 217/255 to 255/255, and there are no abilities. `ClassicEngine` holds that formula and the
steps where the generations differ are methods each subclass fills in. The order of operations
and every floor follow `@smogon/calc` (mechanics/gen12), which the golden fixtures
tests/fixtures/calc_golden_gen{1,2}.json are generated from.
"""

from abc import abstractmethod
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import ClassVar

from poketrix.schemas import (
    BoostStat,
    FixedDamage,
    Generation,
    Move,
    MoveCategory,
    PokemonType,
    SideCondition,
    Stat,
    Status,
    Weather,
    category_for_type,
)

from ..base import BaseEngine
from ..context import Context
from ..engine import DamageResult, UnsupportedMoveError
from ..power_rules import (
    Rule,
    derived_hidden_power,
    derives_hidden_power,
    maximum_happiness,
    resolve_power,
    stronger_at_low_hp,
)
from ..stats import apply_stage_classic
from ..typechart import type_factor
from . import chance

_ROLL_NUMERATORS = range(217, 256)  # the 39 random factors, out of 255
_HALVES_DEFENSE = frozenset({"explosion", "selfdestruct"})


class ClassicEngine(BaseEngine):
    power_rules: ClassVar[Mapping[str, Rule]] = MappingProxyType({})

    # ------------------------------------------------------------------ what differs per gen

    @abstractmethod
    def _crit_chance(self, c: Context) -> float: ...

    @abstractmethod
    def _defender_types(self, c: Context) -> Sequence[PokemonType]:
        """The defender's types in the order their factors are applied."""

    @abstractmethod
    def _crit_uses_raw_stats(self, c: Context, attack_stat: Stat, defense_stat: Stat) -> bool:
        """Whether a critical hit ignores stat stages, burn and screens in this matchup."""

    @abstractmethod
    def _apply_effectiveness(self, base: int, factors: Sequence[float]) -> int: ...

    @abstractmethod
    def _roll(self, base: int, numerator: int) -> int: ...

    crit_doubles_level: bool  # Gen 1; Gen 2 doubles the damage instead
    fixed_damage_ignores_immunity: bool
    hits_share_roll: bool  # Gen 1: a multi-hit move repeats its first hit

    def _ohko_fails(self, c: Context) -> bool:
        return c.attacker.level < c.defender.level

    # ------------------------------------------------------------------ the shared calculation

    def _damage(self, c: Context) -> DamageResult:
        move = c.move
        attacking = self._move_type(c)
        factors = [self._factor(c, attacking, t) for t in self._defender_types(c)]
        multiplier = 1.0
        for factor in factors:
            multiplier *= factor
        if self.fixed_damage_ignores_immunity and self._is_flat_or_halving(move):
            multiplier = 1.0  # the type chart plays no part at all
        if multiplier == 0:
            return DamageResult((0,), None, 0.0, 0.0)
        if move.fixed_damage is not None:
            return DamageResult((self._fixed_damage(c),), None, multiplier, 0.0)

        power = resolve_power(c, self.power_rules)
        if derives_hidden_power(c):
            physical = category_for_type(attacking) is MoveCategory.PHYSICAL
        else:
            physical = c.physical
        crit_chance = self._crit_chance(c)
        rolls = self._rolls(c, attacking, factors, power, physical, crit=False)
        crit_rolls = None
        if crit_chance > 0:
            crit_rolls = self._rolls(c, attacking, factors, power, physical, crit=True)
        hits = chance.hit_distribution(c)
        shared = self.hits_share_roll and hits is not None
        return DamageResult(
            rolls, crit_rolls, multiplier, crit_chance, hits, hits_share_roll=shared
        )

    @staticmethod
    def _is_flat_or_halving(move: Move) -> bool:
        """Seismic Toss, Sonic Boom, Super Fang: in Gen 1 they hit through type immunity."""
        kind = move.fixed_damage
        return isinstance(kind, int) or kind in (FixedDamage.LEVEL, FixedDamage.HALF_TARGET_HP)

    def _move_type(self, c: Context) -> PokemonType:
        if c.move.ignores_type_chart:
            return PokemonType.TYPELESS
        if derives_hidden_power(c):
            return derived_hidden_power(c)[0]
        return c.move.type

    def _factor(self, c: Context, attacking: PokemonType, defending: PokemonType) -> float:
        if (
            c.defender.has_volatile("foresight") and defending is PokemonType.GHOST
            and attacking in (PokemonType.NORMAL, PokemonType.FIGHTING)
        ):
            return 1.0
        return type_factor(self.gen, attacking, defending)

    def _fixed_damage(self, c: Context) -> int:
        kind = c.move.fixed_damage
        if isinstance(kind, int):
            return kind
        if kind is FixedDamage.LEVEL:
            return c.attacker.level
        if kind is FixedDamage.HALF_TARGET_HP:
            return max(1, c.defender.hp // 2)
        if kind is FixedDamage.OHKO:
            return 0 if self._ohko_fails(c) else c.defender.hp
        if kind is FixedDamage.REACTIVE:
            raise UnsupportedMoveError("damage depends on the damage the user takes first")
        raise UnsupportedMoveError(f"fixed-damage rule {kind.value!r} is not supported")

    def _rolls(
        self, c: Context, attacking: PokemonType, factors: Sequence[float], power: int,
        physical: bool, crit: bool,
    ) -> tuple[int, ...]:
        attacker, defender, move = c.attacker, c.defender, c.move
        attack_stat, defense_stat = (Stat.ATK, Stat.DEF) if physical else (Stat.SPA, Stat.SPD)
        attack, defense = attacker.stats[attack_stat], defender.stats[defense_stat]
        level = attacker.level
        raw = crit and self._crit_uses_raw_stats(c, attack_stat, defense_stat)
        if raw:
            if self.crit_doubles_level:
                level *= 2
        else:
            attack = apply_stage_classic(attack, attacker.stage(BoostStat(attack_stat.value)))
            defense = apply_stage_classic(defense, defender.stage(BoostStat(defense_stat.value)))
            if physical and attacker.status is Status.BURN:
                attack //= 2
        if move.id in _HALVES_DEFENSE:
            defense //= 2
        screen = SideCondition.REFLECT if physical else SideCondition.LIGHT_SCREEN
        if not raw and screen in c.defender_conditions:
            defense *= 2
        attack = self._item_attack(c, attack, physical)
        if attack > 255 or defense > 255:  # stats are bytes: both are quartered, then wrap
            attack, defense = attack // 4 % 256, defense // 4 % 256
        defense = self._item_defense(c, defense)

        base = (2 * level // 5 + 2) * max(1, attack) * power // max(1, defense) // 50
        if crit and not self.crit_doubles_level:
            base *= 2
        base = self._item_damage(c, base, attacking)
        base = min(997, base) + 2
        base = self._weather(c, base, attacking)
        if attacking in attacker.types:  # STAB
            base = int(base * 1.5)
        base = self._apply_effectiveness(base, factors)
        if move.id in ("flail", "reversal"):  # no random factor
            return (base,)
        return tuple(self._roll(base, numerator) for numerator in _ROLL_NUMERATORS)

    # Held items and weather arrive in Gen 2; the defaults are Gen 1's "nothing happens".

    def _item_attack(self, c: Context, attack: int, physical: bool) -> int:
        return attack

    def _item_defense(self, c: Context, defense: int) -> int:
        return defense

    def _item_damage(self, c: Context, base: int, attacking: PokemonType) -> int:
        return base

    def _weather(self, c: Context, base: int, attacking: PokemonType) -> int:
        return base


class Gen1Engine(ClassicEngine):
    gen = Generation.RBY
    crit_doubles_level = True
    fixed_damage_ignores_immunity = True  # Seismic Toss hits Ghosts, Night Shade hits Normals
    hits_share_roll = True

    def _hit_chance(self, c: Context) -> float:
        return chance.gen1_hit_chance(c)

    def _crit_chance(self, c: Context) -> float:
        return chance.gen1_crit_chance(c)

    def _ohko_fails(self, c: Context) -> bool:
        return chance.gen1_ohko_fails(c)

    def _defender_types(self, c: Context) -> Sequence[PokemonType]:
        return c.defender.types  # in the species' own order: each factor is floored in turn

    def _crit_uses_raw_stats(self, c: Context, attack_stat: Stat, defense_stat: Stat) -> bool:
        return True

    def _apply_effectiveness(self, base: int, factors: Sequence[float]) -> int:
        for factor in factors:
            base = int(base * factor)
        return base

    def _roll(self, base: int, numerator: int) -> int:
        return 1 if base == 1 else base * numerator // 255


_GEN2_WEATHER_POWER = {  # (weather, move type) -> (numerator, denominator)
    (Weather.SUN, PokemonType.FIRE): (3, 2),
    (Weather.RAIN, PokemonType.WATER): (3, 2),
    (Weather.SUN, PokemonType.WATER): (1, 2),
    (Weather.RAIN, PokemonType.FIRE): (1, 2),
}
_gen2_low_hp = stronger_at_low_hp(48, ((1, 200), (4, 150), (9, 100), (16, 80), (32, 40)))


class Gen2Engine(ClassicEngine):
    gen = Generation.GSC
    crit_doubles_level = False
    fixed_damage_ignores_immunity = False
    hits_share_roll = False
    power_rules = MappingProxyType({
        "return": maximum_happiness,
        "frustration": maximum_happiness,
        "flail": _gen2_low_hp,
        "reversal": _gen2_low_hp,
    })

    def _hit_chance(self, c: Context) -> float:
        return chance.gen2_hit_chance(c)

    def _crit_chance(self, c: Context) -> float:
        return chance.gen2_crit_chance(c)

    def _defender_types(self, c: Context) -> Sequence[PokemonType]:
        return c.defender.types

    def _crit_uses_raw_stats(self, c: Context, attack_stat: Stat, defense_stat: Stat) -> bool:
        # Stages are ignored only when they do not favour the attacker.
        attack_stage = c.attacker.stage(BoostStat(attack_stat.value))
        return attack_stage <= c.defender.stage(BoostStat(defense_stat.value))

    def _apply_effectiveness(self, base: int, factors: Sequence[float]) -> int:
        multiplier = 1.0
        for factor in factors:
            multiplier *= factor
        return int(base * multiplier)

    def _roll(self, base: int, numerator: int) -> int:
        return max(1, base * numerator // 255)

    def _item_attack(self, c: Context, attack: int, physical: bool) -> int:
        item, species = c.attacker.item_id, c.attacker.species_id
        light_ball = item == "lightball" and species == "pikachu" and not physical
        thick_club = item == "thickclub" and species in ("cubone", "marowak") and physical
        return attack * 2 if light_ball or thick_club else attack

    def _item_defense(self, c: Context, defense: int) -> int:
        if c.defender.item_id == "metalpowder" and c.defender.species_id == "ditto":
            return int(defense * 1.5)
        return defense

    def _item_damage(self, c: Context, base: int, attacking: PokemonType) -> int:
        item = c.attacker.item
        if item is None:
            return base
        # A Gen 2 bug: Dragon Scale, not Dragon Fang, boosts Dragon moves.
        quirks = {"dragonfang": None, "dragonscale": PokemonType.DRAGON}
        boosted = quirks.get(item.id, item.boosts_type)
        struggle = c.move.id == "struggle" and boosted is PokemonType.NORMAL
        return int(base * 1.1) if boosted is attacking or struggle else base

    def _weather(self, c: Context, base: int, attacking: PokemonType) -> int:
        numerator, denominator = _GEN2_WEATHER_POWER.get((c.weather, attacking), (1, 1))
        if c.move.id == "solarbeam" and c.weather is Weather.RAIN:
            denominator = 2
        return base * numerator // denominator
