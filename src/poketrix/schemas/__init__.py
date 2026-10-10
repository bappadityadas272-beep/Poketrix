"""Poketrix shared contracts. Import from here, not from submodules."""

from .battle import HAZARDS, ActionRequest, FieldState, GameState, SideState
from .enums import (
    ActionKind,
    BoostStat,
    Generation,
    MoveCategory,
    PlayerSlot,
    PokemonType,
    SideCondition,
    Stat,
    Status,
    SubsystemStatus,
    Weather,
)
from .generation import GEN_RULES, GenRules, category_for_type, rules_for
from .outputs import (
    ActionPrediction,
    DamageRange,
    KOChance,
    MathReport,
    MoveEvaluation,
    Recommendation,
    SetHypothesis,
    SetPosterior,
    SubsystemResult,
)
from .pokemon import (
    BaseStats,
    BattlePokemon,
    Move,
    PokemonSet,
    Species,
    StatSpread,
    gen1_2_hp_dv,
    to_id,
)

__all__ = [name for name in dir() if not name.startswith("_")]
