"""The part of a damage calculation that Gens 3 and 4 share: what happens before the formula.

Immunities, fixed damage and multi-hit counts work the same way in both generations. The formula
itself (which stat is modified when, and in which order the multipliers are floored) differs, so
each generation's engine supplies it.
"""

from abc import abstractmethod
from collections.abc import Mapping, Sequence

from poketrix.schemas import FixedDamage, PokemonType

from ..base import BaseEngine
from ..context import Context
from ..engine import DamageResult, UnsupportedMoveError
from ..power_rules import Rule, resolve_power
from . import chance
from .movetype import blocked_by_ability, move_type, type_factors

ROLL_PERCENTS = range(85, 101)  # the 16 random factors


class ModernEngine(BaseEngine):
    power_rules: Mapping[str, Rule]

    def _hit_chance(self, c: Context) -> float:
        return chance.hit_chance(c)

    def _damage(self, c: Context) -> DamageResult:
        self._check_supported(c)
        attacking = move_type(c)
        c = self._with_category(c, attacking)
        factors = type_factors(c, attacking)
        multiplier = 1.0
        for factor in factors:
            multiplier *= factor
        if multiplier == 0 or blocked_by_ability(c, attacking, multiplier):
            return DamageResult((0,), None, 0.0, 0.0)
        if c.move.fixed_damage is not None:
            return DamageResult((self._fixed_damage(c),), None, multiplier, 0.0)

        power = resolve_power(c, self.power_rules)
        if power == 0:  # the move fails: nothing to Fling, no berry for Natural Gift
            return DamageResult((0,), None, multiplier, 0.0)
        hits = chance.hit_distribution(c)
        if hits is not None:
            self._check_multi_hit(c, attacking, multiplier)

        def rolls(crit: bool) -> tuple[int, ...]:
            return tuple(self._rolls(c, attacking, factors, multiplier, power, crit))

        crit_rolls = rolls(True) if chance.can_crit(c) else None
        return DamageResult(rolls(False), crit_rolls, multiplier, chance.crit_chance(c), hits)

    @abstractmethod
    def _rolls(
        self, c: Context, attacking: PokemonType, factors: Sequence[float], multiplier: float,
        power: int, crit: bool,
    ) -> Sequence[int]:
        """The 16 damage rolls of one hit, in ascending order."""

    def _check_supported(self, c: Context) -> None:
        """Raise UnsupportedMoveError for anything damage-relevant the engine does not model."""

    def _check_multi_hit(self, c: Context, attacking: PokemonType, multiplier: float) -> None:
        """Raise UnsupportedMoveError if the hits of one use would not share their rolls."""

    def _with_category(self, c: Context, attacking: PokemonType) -> Context:
        """Before Gen 4 a move's category follows its effective type."""
        return c

    @staticmethod
    def _fixed_damage(c: Context) -> int:
        kind = c.move.fixed_damage
        if isinstance(kind, int):
            return kind
        if kind is FixedDamage.LEVEL:
            return c.attacker.level
        if kind is FixedDamage.HALF_TARGET_HP:
            return max(1, c.defender.hp // 2)
        if kind is FixedDamage.TARGET_TO_USER_HP:
            return max(0, c.defender.hp - c.attacker.hp)
        if kind is FixedDamage.OHKO:
            fails = c.attacker.level < c.defender.level or c.defender.ability == "sturdy"
            return 0 if fails else c.defender.hp
        if kind is FixedDamage.REACTIVE:
            raise UnsupportedMoveError("damage depends on the damage the user takes first")
        raise UnsupportedMoveError(f"fixed-damage rule {kind.value!r} is not supported")
