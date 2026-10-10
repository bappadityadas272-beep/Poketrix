"""Gen 4 (DPP) damage engine: the formula's skeleton and the order of its stages.

The order of operations and every floor follow `@smogon/calc` (mechanics/gen4), which the golden
fixtures in tests/fixtures/calc_golden_gen4.json are generated from. The rules of each stage live
in the sibling modules, so adding an ability or item never edits the formula here.
"""

from collections.abc import Sequence

from poketrix.schemas import Generation, PokemonType

from ..context import Context
from ..engine import UnsupportedMoveError
from ..modern.engine import ROLL_PERCENTS, ModernEngine
from . import modifiers
from .power import POWER_RULES, modified_power

# Damage-relevant abilities the engine does not model: it reports them instead of guessing.
_UNMODELLED_ATTACKER_ABILITIES = {
    "rivalry": "Rivalry depends on both Pokémon's gender, which is not tracked",
}


class Gen4Engine(ModernEngine):
    gen = Generation.DPP
    power_rules = POWER_RULES

    def _check_supported(self, c: Context) -> None:
        unmodelled = _UNMODELLED_ATTACKER_ABILITIES.get(c.attacker.ability)
        if unmodelled is not None:
            raise UnsupportedMoveError(unmodelled)

    def _check_multi_hit(self, c: Context, attacking: PokemonType, multiplier: float) -> None:
        if modifiers.resist_berry_applies(c, attacking, multiplier):
            raise UnsupportedMoveError(
                "a resist berry weakens only the first hit of a multi-hit move"
            )

    def _rolls(
        self, c: Context, attacking: PokemonType, factors: Sequence[float], multiplier: float,
        power: int, crit: bool,
    ) -> Sequence[int]:
        power = modified_power(power, c, attacking)
        base = (2 * c.attacker.level // 5 + 2) * power * modifiers.attack(c, crit) // 50
        base //= modifiers.defense(c, crit)
        if modifiers.is_burned(c):
            base //= 2
        base = modifiers.after_base_damage(base, c, attacking, crit)
        roll_factors = [modifiers.stab(c, attacking), *factors]
        roll_factors += modifiers.after_type_factors(c, attacking, multiplier)
        roll_factors = [factor for factor in roll_factors if factor != 1.0]
        result = []
        for percent in ROLL_PERCENTS:
            damage = base * percent // 100
            for factor in roll_factors:
                damage = int(damage * factor)
            result.append(max(1, damage))
        return result
