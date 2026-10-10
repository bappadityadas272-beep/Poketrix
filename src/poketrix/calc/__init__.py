"""Deterministic Math layer. Import from here, not from submodules."""

from poketrix.schemas import Generation

from .engine import DamageEngine, DamageResult, Outcome, engine_for, register_engine
from .gen4 import Gen4Engine
from .hidden_power import hidden_power
from .ko import ko_chances
from .report import build_report, evaluate_move
from .stats import apply_stage, compute_stats
from .typechart import effectiveness

register_engine(Generation.DPP, Gen4Engine())

__all__ = [
    "DamageEngine",
    "DamageResult",
    "Outcome",
    "apply_stage",
    "build_report",
    "compute_stats",
    "effectiveness",
    "engine_for",
    "evaluate_move",
    "hidden_power",
    "ko_chances",
    "register_engine",
]
