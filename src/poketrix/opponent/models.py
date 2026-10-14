"""Opponent-action models: a `DecisionView` in, the chance of attack, utility and switch out.

`Heuristic` is heuristic-0, a rule of thumb that needs nothing installed. `XgbModel` is the
learned model (Phase 7); it needs the optional `ml` dependencies and its saved files, and says
so with `ModelUnavailable` when they are missing, so that the turn engine can fall back.
"""

import json
import math
from pathlib import Path
from typing import Protocol

from poketrix.schemas import ActionPrediction

from .features import ACTIONS, FEATURES, DecisionView

MODEL_DIR = Path(__file__).resolve().parents[3] / "data" / "models"
_SWITCH_BASE, _SWITCH_PER_KO, _SWITCH_MIN, _SWITCH_MAX = 0.10, 0.40, 0.05, 0.60


class ModelUnavailable(RuntimeError):
    """The model cannot predict here: a dependency or its saved files are missing."""


class OpponentModel(Protocol):
    version: str

    def predict(self, view: DecisionView) -> ActionPrediction: ...


class Heuristic:
    """The likelier the target is to knock its Pokémon out, the likelier it leaves, if it has
    somewhere to go; staying, it attacks as often as its likely moves are damaging ones."""

    version = "heuristic-0"

    def predict(self, view: DecisionView) -> ActionPrediction:
        p_switch = 0.0
        if view.alive > 1:
            p_switch = min(_SWITCH_MAX, max(
                _SWITCH_MIN, _SWITCH_BASE + _SWITCH_PER_KO * view.target_best_ko
            ))
        staying = 1 - p_switch
        return ActionPrediction(
            p_attack=staying * view.damaging_share,
            p_utility=staying * (1 - view.damaging_share),
            p_switch=p_switch, model_version=self.version,
        )


def model_paths(version: str, directory: Path = MODEL_DIR) -> tuple[Path, Path]:
    """Where a learned model lives: XGBoost's own JSON, and the manifest beside it."""
    return (directory / f"opponent-{version}.json",
            directory / f"opponent-{version}.manifest.json")


class XgbModel:
    """Gradient-boosted trees over the feature vector, calibrated by one temperature."""

    def __init__(self, version: str = "xgb-1", directory: Path = MODEL_DIR) -> None:
        self.version = version
        self._booster = None
        self._temperature = 1.0
        self._problem = self._load(*model_paths(version, directory))

    def _load(self, model_file: Path, manifest_file: Path) -> str | None:
        """Read the saved model. Returns why it cannot be used, or None when it can."""
        try:
            import xgboost
        except ImportError:
            return 'xgboost is not installed: pip install -e ".[ml]"'
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            booster = xgboost.Booster(model_file=model_file)
        except (OSError, ValueError, xgboost.core.XGBoostError) as error:
            return f"{self.version} could not be read: {error}"
        if tuple(manifest["features"]) != FEATURES or tuple(manifest["actions"]) != ACTIONS:
            return f"{self.version} was trained on other features: train it again"
        booster.set_param({"nthread": 1})  # one row at a time: threads only add overhead
        self._booster, self._temperature = booster, manifest["temperature"]
        return None

    def margins(self, rows):
        """The trees' raw scores, one row per decision and one column per action."""
        import numpy

        if self._problem is not None:
            raise ModelUnavailable(self._problem)
        matrix = numpy.asarray(rows, dtype=numpy.float32)
        return self._booster.inplace_predict(matrix, predict_type="margin")

    def predict(self, view: DecisionView) -> ActionPrediction:
        odds = softmax(self.margins([view.vector()])[0], self._temperature)
        return ActionPrediction(
            **{f"p_{action}": share for action, share in zip(ACTIONS, odds, strict=True)},
            model_version=self.version,
        )


def softmax(margins, temperature: float) -> list[float]:
    """Raw scores to probabilities; a temperature above 1 makes them less confident."""
    scaled = [float(margin) / temperature for margin in margins]
    top = max(scaled)
    weights = [math.exp(value - top) for value in scaled]
    total = sum(weights)
    return [weight / total for weight in weights]


MODELS: dict[str, type[OpponentModel]] = {Heuristic.version: Heuristic, "xgb-1": XgbModel}
