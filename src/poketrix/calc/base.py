"""What every generation's engine does the same way: build the context once, then report the
hit chance together with either the damage or the reason it cannot be computed."""

from abc import ABC, abstractmethod

from poketrix.schemas import BattlePokemon, FieldState, Generation, Move, MoveCategory

from .context import Context, build_context
from .engine import NO_CONDITIONS, DamageResult, Outcome, SideConditions, UnsupportedMoveError


class BaseEngine(ABC):
    gen: Generation

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
        return Outcome(self._hit_chance(c), damage, reason, c.defender.hp, c.defender.max_hp)

    @abstractmethod
    def _damage(self, c: Context) -> DamageResult:
        """Rolls of a damaging move. Raises UnsupportedMoveError rather than guess."""

    @abstractmethod
    def _hit_chance(self, c: Context) -> float: ...
