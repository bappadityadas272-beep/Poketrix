"""Gen 4 (DPP) damage engine: the formula's skeleton and the order of its stages.

The order of operations and every floor follow `@smogon/calc` (mechanics/gen4), which the golden
fixtures in tests/fixtures/calc_golden_gen4.json are generated from. The rules of each stage live
in the sibling modules, so adding an ability or item never edits the formula here.
"""

from poketrix.schemas import (
    BattlePokemon,
    FieldState,
    FixedDamage,
    Generation,
    Move,
    MoveCategory,
)

from ..engine import (
    NO_CONDITIONS,
    DamageResult,
    Outcome,
    SideConditions,
    UnsupportedMoveError,
)
from . import chance, modifiers
from .context import Context, build_context
from .movetype import blocked_by_ability, move_type, type_factors
from .power import base_power, modified_power

_ROLLS = range(85, 101)  # the 16 random factors, in percent

# Damage-relevant abilities the engine does not model: it reports them instead of guessing.
_UNMODELLED_ATTACKER_ABILITIES = {
    "rivalry": "Rivalry depends on both Pokémon's gender, which is not tracked",
}


class Gen4Engine:
    gen = Generation.DPP

    def evaluate(
        self, attacker: BattlePokemon, defender: BattlePokemon, move: Move, field: FieldState,
        defender_conditions: SideConditions = NO_CONDITIONS,
        attacker_conditions: SideConditions = NO_CONDITIONS,
    ) -> Outcome:
        c = build_context(attacker, defender, move, field, attacker_conditions, defender_conditions)
        damage, reason = None, None
        if move.category is not MoveCategory.STATUS:
            try:
                damage = self._damage(c)
            except UnsupportedMoveError as error:
                reason = str(error)
        return Outcome(chance.hit_chance(c), damage, reason, c.defender.hp, c.defender.max_hp)

    def _damage(self, c: Context) -> DamageResult:
        move = c.move
        unmodelled = _UNMODELLED_ATTACKER_ABILITIES.get(c.attacker.ability)
        if unmodelled is not None:
            raise UnsupportedMoveError(unmodelled)

        attacking = move_type(c)
        factors = type_factors(c, attacking)
        multiplier = 1.0
        for factor in factors:
            multiplier *= factor
        if multiplier == 0 or blocked_by_ability(c, attacking, multiplier):
            return DamageResult((0,), None, 0.0, 0.0)
        if move.fixed_damage is not None:
            return DamageResult((self._fixed_damage(c),), None, multiplier, 0.0)

        power = base_power(c)
        if power == 0:  # the move fails: nothing to Fling, no berry for Natural Gift
            return DamageResult((0,), None, multiplier, 0.0)
        hits = chance.hit_distribution(c)
        if hits is not None and modifiers.resist_berry_applies(c, attacking, multiplier):
            raise UnsupportedMoveError(
                "a resist berry weakens only the first hit of a multi-hit move"
            )
        power = modified_power(power, c, attacking)

        level_factor = 2 * c.attacker.level // 5 + 2
        burned = modifiers.is_burned(c)
        roll_factors = [modifiers.stab(c, attacking), *factors]
        roll_factors += modifiers.after_type_factors(c, attacking, multiplier)
        roll_factors = [factor for factor in roll_factors if factor != 1.0]

        def rolls(crit: bool) -> tuple[int, ...]:
            base = level_factor * power * modifiers.attack(c, crit) // 50
            base //= modifiers.defense(c, crit)
            if burned:
                base //= 2
            base = modifiers.after_base_damage(base, c, attacking, crit)
            result = []
            for roll in _ROLLS:
                damage = base * roll // 100
                for factor in roll_factors:
                    damage = int(damage * factor)
                result.append(max(1, damage))
            return tuple(result)

        crit_rolls = rolls(True) if chance.can_crit(c) else None
        return DamageResult(rolls(False), crit_rolls, multiplier, chance.crit_chance(c), hits)

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
