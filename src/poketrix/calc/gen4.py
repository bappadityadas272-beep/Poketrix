"""Gen 4 (DPP) damage engine, stage 03a: the core formula without held items and without
abilities, except the abilities that make a move do nothing (Levitate, Flash Fire, ...).

The order of operations and every floor follow `@smogon/calc` (mechanics/gen4), which the golden
fixtures in tests/fixtures/calc_golden_gen4.json are generated from.
"""

from collections.abc import Callable
from dataclasses import dataclass

from poketrix.schemas import (
    BattlePokemon,
    BoostStat,
    FieldState,
    FixedDamage,
    Generation,
    Move,
    MoveCategory,
    PokemonType,
    SideCondition,
    Stat,
    Status,
    Weather,
)

from .engine import DamageResult, SideConditions, UnsupportedMoveError
from .hidden_power import hidden_power
from .stats import apply_stage, battle_stats, current_hp
from .typechart import in_type_order, type_factor

_ROLLS = range(85, 101)  # the 16 random factors, in percent
_CRIT_CHANCE = {1: 1 / 16, 2: 1 / 8, 3: 1 / 4, 4: 1 / 3, 5: 1 / 2}  # by Move.crit_ratio

# Defender abilities that absorb a whole move type.
_ABSORBS = {
    "flashfire": PokemonType.FIRE,
    "waterabsorb": PokemonType.WATER,
    "dryskin": PokemonType.WATER,
    "voltabsorb": PokemonType.ELECTRIC,
    "motordrive": PokemonType.ELECTRIC,
    "levitate": PokemonType.GROUND,
}
_MOLD_BREAKER_IGNORES = frozenset(_ABSORBS) | {"wonderguard", "sturdy"}
_WEATHER_NEGATORS = frozenset({"airlock", "cloudnine"})
_GHOST_REVEALERS = frozenset({"foresight", "odorsleuth"})  # volatiles
_HALVES_DEFENSE = frozenset({"explosion", "selfdestruct"})
_WEATHER_BALL_TYPE = {
    Weather.SUN: PokemonType.FIRE,
    Weather.RAIN: PokemonType.WATER,
    Weather.SANDSTORM: PokemonType.ROCK,
    Weather.HAIL: PokemonType.ICE,
}
_WEATHER_POWER = {  # (weather, move type) -> (numerator, denominator)
    (Weather.SUN, PokemonType.FIRE): (3, 2),
    (Weather.RAIN, PokemonType.WATER): (3, 2),
    (Weather.SUN, PokemonType.WATER): (1, 2),
    (Weather.RAIN, PokemonType.FIRE): (1, 2),
}
_SOLAR_BEAM_WEAKENERS = frozenset({Weather.RAIN, Weather.SANDSTORM, Weather.HAIL})

_ORACLE_DISAGREES = "the oracle and the Showdown simulator disagree on its power (open question)"
_UNSUPPORTED = {
    "payback": "power depends on turn order, which needs item-aware Speed (Task 03b)",
    "gyroball": _ORACLE_DISAGREES,
    "punishment": _ORACLE_DISAGREES,
    "beatup": "damage depends on the whole team",
    "hiddenpower": "untyped Hidden Power: give the set IVs or use a typed Hidden Power",
}


@dataclass(frozen=True)
class _Context:
    """What a variable-power rule may look at."""

    attacker: BattlePokemon
    defender: BattlePokemon
    attacker_hp: int
    attacker_max_hp: int
    defender_hp: int
    defender_max_hp: int
    weather: Weather


def _scaled_by_user_hp(move: Move, c: _Context) -> int:
    return max(1, move.base_power * c.attacker_hp // c.attacker_max_hp)


def _stronger_at_low_hp(move: Move, c: _Context) -> int:
    p = 64 * c.attacker_hp // c.attacker_max_hp
    for limit, power in ((1, 200), (5, 150), (12, 100), (21, 80), (42, 40)):
        if p <= limit:
            return power
    return 20


def _scaled_by_target_hp(move: Move, c: _Context) -> int:
    return c.defender_hp * 120 // c.defender_max_hp + 1


def _doubled_if(condition: Callable[[_Context], bool]) -> Callable[[Move, _Context], int]:
    return lambda move, c: move.base_power * (2 if condition(c) else 1)


_FACADE_STATUSES = frozenset({Status.PARALYSIS, Status.POISON, Status.TOXIC, Status.BURN})

_POWER_RULES: dict[str, Callable[[Move, _Context], int]] = {
    "return": lambda move, c: 102,  # maximum happiness, as the oracle assumes
    "frustration": lambda move, c: 102,  # minimum happiness
    "eruption": _scaled_by_user_hp,
    "waterspout": _scaled_by_user_hp,
    "flail": _stronger_at_low_hp,
    "reversal": _stronger_at_low_hp,
    "crushgrip": _scaled_by_target_hp,
    "wringout": _scaled_by_target_hp,
    "brine": _doubled_if(lambda c: c.defender_hp * 2 <= c.defender_max_hp),
    "facade": _doubled_if(lambda c: c.attacker.status in _FACADE_STATUSES),
    "wakeupslap": _doubled_if(lambda c: c.defender.status is Status.SLEEP),
    "weatherball": _doubled_if(lambda c: c.weather is not Weather.NONE),
}


def _ability(pokemon: BattlePokemon) -> str | None:
    if pokemon.known_set is not None and pokemon.known_set.ability is not None:
        return pokemon.known_set.ability
    return pokemon.revealed_ability


class Gen4Engine:
    gen = Generation.DPP

    def hit_chance(self, attacker: BattlePokemon, defender: BattlePokemon, move: Move) -> float:
        if move.fixed_damage is FixedDamage.OHKO:
            if attacker.level < defender.level:
                return 0.0
            return min(1.0, (30 + attacker.level - defender.level) / 100)
        if move.accuracy is None:
            return 1.0
        accuracy_stage = attacker.boosts.get(BoostStat.ACCURACY, 0)
        evasion_stage = defender.boosts.get(BoostStat.EVASION, 0)
        stage = max(-6, min(6, accuracy_stage - evasion_stage))
        multiplier = (3 + stage) / 3 if stage >= 0 else 3 / (3 - stage)
        return min(1.0, move.accuracy / 100 * multiplier)

    def damage(
        self, attacker: BattlePokemon, defender: BattlePokemon, move: Move,
        field: FieldState, defender_conditions: SideConditions,
    ) -> DamageResult:
        if move.category is MoveCategory.STATUS:
            raise ValueError(f"{move.name} is a status move and deals no damage")
        attacker_stats, defender_stats = battle_stats(attacker), battle_stats(defender)
        attacker_ability, defender_ability = _ability(attacker), _ability(defender)
        weather = field.weather
        if _WEATHER_NEGATORS & {attacker_ability, defender_ability}:
            weather = Weather.NONE
        if attacker_ability == "moldbreaker" and defender_ability in _MOLD_BREAKER_IGNORES:
            defender_ability = None
        context = _Context(
            attacker, defender,
            current_hp(attacker, attacker_stats[Stat.HP]), attacker_stats[Stat.HP],
            current_hp(defender, defender_stats[Stat.HP]), defender_stats[Stat.HP],
            weather,
        )
        gravity = field.gravity_turns_left > 0

        move_type = self._move_type(move, attacker, weather)
        ghost_revealed = (
            attacker_ability == "scrappy" or not _GHOST_REVEALERS.isdisjoint(defender.volatiles)
        )
        factors = [
            self._factor(move_type, defender_type, ghost_revealed, gravity)
            for defender_type in in_type_order(defender.species.types)
        ]
        multiplier = 1.0
        for factor in factors:
            multiplier *= factor
        blocked = self._blocked_by_ability(move, move_type, multiplier, defender_ability, gravity)
        if multiplier == 0 or blocked:
            return DamageResult((0,), None, 0.0, 0.0)

        if move.fixed_damage is not None:
            amount = self._fixed_damage(move, context, defender_ability)
            return DamageResult((amount,), None, multiplier, 0.0)

        power = self._power(move, context)
        physical = move.category is MoveCategory.PHYSICAL
        attack_stat, defense_stat = (Stat.ATK, Stat.DEF) if physical else (Stat.SPA, Stat.SPD)
        attack = attacker_stats[attack_stat]
        attack_stage = attacker.boosts.get(BoostStat(attack_stat.value), 0)
        defense = defender_stats[defense_stat]
        defense_stage = defender.boosts.get(BoostStat(defense_stat.value), 0)
        level_factor = 2 * attacker.level // 5 + 2
        burned = physical and attacker.status is Status.BURN
        screen = SideCondition.REFLECT if physical else SideCondition.LIGHT_SCREEN
        screened = screen in defender_conditions and move.id != "brickbreak"
        weather_num, weather_den = _WEATHER_POWER.get((weather, move_type), (1, 1))
        if move.id == "solarbeam" and weather in _SOLAR_BEAM_WEAKENERS:
            weather_den = 2
        sand_boost = (
            weather is Weather.SANDSTORM and not physical
            and PokemonType.ROCK in defender.species.types
        )
        stab = move_type in attacker.species.types

        def rolls(crit: bool) -> tuple[int, ...]:
            # A critical hit ignores the attacker's drops, the defender's boosts and screens.
            a = attack
            if attack_stage > 0 or (attack_stage < 0 and not crit):
                a = apply_stage(a, attack_stage)
            d = defense
            if defense_stage < 0 or (defense_stage > 0 and not crit):
                d = apply_stage(d, defense_stage)
            if sand_boost:
                d = d * 3 // 2
            if move.id in _HALVES_DEFENSE:
                d //= 2
            base = level_factor * power * a // 50 // max(1, d)
            if burned:
                base //= 2
            if screened and not crit:
                base //= 2
            base = base * weather_num // weather_den + 2
            if crit:
                base *= 2
            result = []
            for roll in _ROLLS:
                damage = base * roll // 100
                if stab:
                    damage = damage * 3 // 2
                for factor in factors:
                    damage = int(damage * factor)
                result.append(max(1, damage))
            return tuple(result)

        return DamageResult(rolls(False), rolls(True), multiplier, _CRIT_CHANCE[move.crit_ratio])

    def _move_type(self, move: Move, attacker: BattlePokemon, weather: Weather) -> PokemonType:
        if move.ignores_type_chart:
            return PokemonType.TYPELESS
        if move.id == "weatherball":
            return _WEATHER_BALL_TYPE.get(weather, move.type)
        if self._derives_hidden_power(move, attacker):
            return hidden_power(self.gen, attacker.known_set.spread.ivs)[0]
        return move.type

    @staticmethod
    def _derives_hidden_power(move: Move, attacker: BattlePokemon) -> bool:
        """Listed IVs decide Hidden Power; without them a typed Hidden Power is taken as given."""
        return move.id.startswith("hiddenpower") and bool(attacker.known_set.spread.ivs)

    def _factor(
        self, move_type: PokemonType, defender_type: PokemonType, ghost_revealed: bool,
        gravity: bool,
    ) -> float:
        if (
            ghost_revealed and defender_type is PokemonType.GHOST
            and move_type in (PokemonType.NORMAL, PokemonType.FIGHTING)
        ):
            return 1.0
        if gravity and defender_type is PokemonType.FLYING and move_type is PokemonType.GROUND:
            return 1.0
        return type_factor(self.gen, move_type, defender_type)

    @staticmethod
    def _blocked_by_ability(
        move: Move, move_type: PokemonType, multiplier: float, defender_ability: str | None,
        gravity: bool,
    ) -> bool:
        if defender_ability == "wonderguard":
            # Typeless damage and (a Gen 4 glitch) Fire Fang get through Wonder Guard.
            typeless = move_type is PokemonType.TYPELESS
            return multiplier <= 1 and not typeless and move.id != "firefang"
        if defender_ability == "levitate" and gravity:
            return False
        return _ABSORBS.get(defender_ability) is move_type

    @staticmethod
    def _fixed_damage(move: Move, c: _Context, defender_ability: str | None) -> int:
        kind = move.fixed_damage
        if isinstance(kind, int):
            return kind
        if kind is FixedDamage.LEVEL:
            return c.attacker.level
        if kind is FixedDamage.HALF_TARGET_HP:
            return max(1, c.defender_hp // 2)
        if kind is FixedDamage.TARGET_TO_USER_HP:
            return max(0, c.defender_hp - c.attacker_hp)
        if kind is FixedDamage.OHKO:
            fails = c.attacker.level < c.defender.level or defender_ability == "sturdy"
            return 0 if fails else c.defender_hp
        if kind is FixedDamage.REACTIVE:
            raise UnsupportedMoveError("damage depends on the damage the user takes first")
        raise UnsupportedMoveError(f"fixed-damage rule {kind.value!r} is not supported yet")

    def _power(self, move: Move, c: _Context) -> int:
        if self._derives_hidden_power(move, c.attacker):
            return hidden_power(self.gen, c.attacker.known_set.spread.ivs)[1]
        if move.id in _UNSUPPORTED:
            raise UnsupportedMoveError(_UNSUPPORTED[move.id])
        if move.multihit is not None:
            raise UnsupportedMoveError("multi-hit moves are supported from Task 03b")
        rule = _POWER_RULES.get(move.id)
        if rule is not None:
            return rule(move, c)
        if move.base_power == 0:
            raise UnsupportedMoveError("variable-power move without a rule yet (Task 03b)")
        return move.base_power
