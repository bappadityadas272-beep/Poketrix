"""Opponent-action models: a `DecisionView` in, the chance of attack, utility and switch out.

`Heuristic` is heuristic-0, a rule of thumb that needs nothing installed. `XgbModel` is the
learned model (Phase 7); it needs NumPy (from the optional `ml` dependencies) and its saved
files, and says so with `ModelUnavailable` when they are missing, so that the turn engine can
fall back.
"""

import json
import math
from bisect import bisect_right
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Isotonic:
    """A non-decreasing map from a predicted probability to an observed one, linear between
    its points and flat beyond them."""

    x: tuple[float, ...]
    y: tuple[float, ...]

    def __call__(self, value: float) -> float:
        at = bisect_right(self.x, value)
        if at == 0:
            return self.y[0]
        if at == len(self.x):
            return self.y[-1]
        x0, x1, y0, y1 = self.x[at - 1], self.x[at], self.y[at - 1], self.y[at]
        return y0 + (y1 - y0) * (value - x0) / (x1 - x0)


def calibrated(switch: Isotonic, attack_share: Isotonic, odds) -> list[float]:
    """Odds in `ACTIONS` order, remapped: P(switch) by its own map, and the rest split between
    attack and utility by the map of the attack share."""
    p_attack, p_utility, p_switch = (float(odds[ACTIONS.index(a)]) for a in ACTIONS)
    leaves = switch(p_switch)
    attack = (1 - leaves) * attack_share(p_attack / max(p_attack + p_utility, 1e-12))
    by_action = {"attack": attack, "utility": 1 - leaves - attack, "switch": leaves}
    return [by_action[action] for action in ACTIONS]


class XgbModel:
    """Gradient-boosted trees over the feature vector, calibrated by one temperature.

    When the manifest holds display maps (ruling 15-R, `calibration.py`), `predict` returns
    the trees' plain odds passed through them instead: that is what is shown to a player.
    `switch_cap` is then the P(switch) above which the shown number is "70%+", or None.

    The trees are read from XGBoost's saved JSON and walked here, all at once with NumPy:
    the same margins as XGBoost's own prediction (a test compares them), at a fraction of its
    per-call cost. Running it needs NumPy only; training it needs XGBoost.
    """

    def __init__(self, version: str = "xgb-1", directory: Path = MODEL_DIR) -> None:
        self.version = version
        self._temperature = 1.0
        self._maps: tuple[Isotonic, Isotonic] | None = None
        self.switch_cap: float | None = None
        self._problem = self._load(*model_paths(version, directory))

    def _load(self, model_file: Path, manifest_file: Path) -> str | None:
        """Read the saved model. Returns why it cannot be used, or None when it can."""
        try:
            import numpy
        except ImportError:
            return 'numpy is not installed: pip install -e ".[ml]"'
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            saved = json.loads(model_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return f"{self.version} could not be read: {error}"
        if tuple(manifest["features"]) != FEATURES or tuple(manifest["actions"]) != ACTIONS:
            return f"{self.version} was trained on other features: train it again"
        self._temperature = manifest["temperature"]
        display = manifest.get("display_calibration")
        if display is not None:
            maps = display["maps"]
            self._maps = tuple(Isotonic(tuple(maps[name]["x"]), tuple(maps[name]["y"]))
                               for name in ("switch", "attack_share"))
            self.switch_cap = display["switch_cap"]
        self._levels = manifest["params"]["max_depth"]
        self._read_trees(numpy, saved["learner"])
        return None

    def _read_trees(self, numpy, learner: dict) -> None:
        """One flat array per node property. A leaf leads back to itself, so every row can
        take the same number of steps down every tree."""
        booster = learner["gradient_booster"]["model"]
        trees = booster["trees"]
        width = max(len(tree["left_children"]) for tree in trees)
        size = len(trees) * width
        self._feature = numpy.zeros(size, numpy.int64)
        self._threshold = numpy.zeros(size, numpy.float32)  # a leaf's value, at a leaf
        self._missing_left = numpy.zeros(size, bool)
        self._child = numpy.zeros((size, 2), numpy.int64)  # [right, left]
        for number, tree in enumerate(trees):
            offset = number * width
            for node, left in enumerate(tree["left_children"]):
                at = offset + node
                self._threshold[at] = tree["split_conditions"][node]
                if left == -1:
                    self._child[at] = (at, at)
                else:
                    self._child[at] = (offset + tree["right_children"][node], offset + left)
                    self._feature[at] = tree["split_indices"][node]
                    self._missing_left[at] = tree["default_left"][node]
        self._roots = numpy.arange(len(trees)) * width
        self._tree_class = numpy.array(booster["tree_info"])
        self._base = numpy.array(json.loads(learner["learner_model_param"]["base_score"]))

    def margins(self, rows):
        """The trees' raw scores, one row per decision and one column per action."""
        import numpy

        if self._problem is not None:
            raise ModelUnavailable(self._problem)
        x = numpy.asarray(rows, dtype=numpy.float32)
        missing = numpy.isnan(x)
        row = numpy.arange(len(x))[:, None]
        node = numpy.broadcast_to(self._roots, (len(x), len(self._roots)))
        for _ in range(self._levels):
            feature = self._feature[node]
            left = (x[row, feature] < self._threshold[node]) | (
                missing[row, feature] & self._missing_left[node])
            node = self._child[node, left.astype(numpy.int64)]
        leaves = self._threshold[node]
        return numpy.stack([leaves[:, self._tree_class == action].sum(axis=1)
                            for action in range(len(ACTIONS))], axis=1) + self._base

    def predict(self, view: DecisionView) -> ActionPrediction:
        margins = self.margins([view.vector()])[0]
        if self._maps is None:
            odds = softmax(margins, self._temperature)
        else:
            odds = calibrated(*self._maps, softmax(margins, 1.0))
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
