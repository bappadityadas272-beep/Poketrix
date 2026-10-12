"""Deterministic Math layer. Import from here, not from submodules."""

from poketrix.schemas import Generation

from .classic import Gen1Engine, Gen2Engine
from .engine import DamageEngine, DamageResult, Outcome, engine_for, register_engine
from .gen3 import Gen3Engine
from .gen4 import Gen4Engine
from .hidden_power import hidden_power
from .ko import ko_chances
from .order import acts_first_chance
from .report import build_report, evaluate_move, expected_hp_share
from .stats import apply_stage, apply_stage_classic, compute_stats
from .typechart import effectiveness

register_engine(Generation.RBY, Gen1Engine())
register_engine(Generation.GSC, Gen2Engine())
register_engine(Generation.ADV, Gen3Engine())
register_engine(Generation.DPP, Gen4Engine())

__all__ = [
    "DamageEngine",
    "DamageResult",
    "Outcome",
    "acts_first_chance",
    "apply_stage",
    "apply_stage_classic",
    "build_report",
    "compute_stats",
    "effectiveness",
    "engine_for",
    "evaluate_move",
    "expected_hp_share",
    "hidden_power",
    "ko_chances",
    "register_engine",
]
