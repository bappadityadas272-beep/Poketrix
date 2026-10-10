"""Gen 3 (ADV) damage engine.

The order of operations and every floor follow `@smogon/calc` (mechanics/gen3), which the golden
fixtures in tests/fixtures/calc_golden_gen3.json are generated from.
"""

from collections.abc import Sequence
from dataclasses import replace

from poketrix.schemas import Generation, MoveCategory, PokemonType, category_for_type

from ..context import Context
from ..modern.engine import ROLL_PERCENTS, ModernEngine
from ..power_rules import (
    FACADE_STATUSES,
    Rule,
    by_target_weight,
    derives_hidden_power,
    doubled_if,
    maximum_happiness,
    scaled_by_user_hp,
    stronger_at_low_hp,
)
from . import modifiers

_low_hp = stronger_at_low_hp(48, ((1, 200), (4, 150), (9, 100), (16, 80), (32, 40)))

POWER_RULES: dict[str, Rule] = {
    "return": maximum_happiness,
    "frustration": maximum_happiness,
    "eruption": scaled_by_user_hp,
    "waterspout": scaled_by_user_hp,
    "flail": _low_hp,
    "reversal": _low_hp,
    "lowkick": by_target_weight,
    "facade": doubled_if(lambda c: c.attacker.status in FACADE_STATUSES),
}


class Gen3Engine(ModernEngine):
    gen = Generation.ADV
    power_rules = POWER_RULES

    def _with_category(self, c: Context, attacking: PokemonType) -> Context:
        # The snapshot's category is right for every move whose type is fixed. Two moves change
        # type in battle: Weather Ball (the oracle makes it special unless it turns Rock) and a
        # Hidden Power derived from IVs.
        if c.move.id == "weatherball":
            return replace(c, physical=attacking is PokemonType.ROCK)
        if derives_hidden_power(c):
            return replace(c, physical=category_for_type(attacking) is MoveCategory.PHYSICAL)
        return c

    def _rolls(
        self, c: Context, attacking: PokemonType, factors: Sequence[float], multiplier: float,
        power: int, crit: bool,
    ) -> Sequence[int]:
        power = modifiers.modified_power(power, c, attacking)
        base = (2 * c.attacker.level // 5 + 2) * modifiers.attack(c, attacking, crit) * power
        base = base // modifiers.defense(c, crit) // 50
        base = modifiers.after_base_damage(base, c, attacking, crit)
        for factor in factors:
            base = int(base * factor)
        return [max(1, base * percent // 100) for percent in ROLL_PERCENTS]
