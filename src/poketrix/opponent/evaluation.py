"""How well the opponent models predict real decisions on the held-out battles.

Three predictors are compared on the test split, per generation and pooled: each generation's
base rates (from the training split), heuristic-0 and the learned model.

- Log-loss covers every row. A `stay` row (a move was chosen, the log hides which) costs
  −log(P(attack) + P(utility)).
- Brier score, accuracy and the 10-bin reliability table of the top choice cover the rows
  whose choice is visible, where all three classes can be checked.
- The switch reliability table covers every row: a switch is visible whenever it happens.
- The log-loss improvement gets a 95% interval from a bootstrap over battles, not rows,
  since decisions within one battle are not independent.

Needs the `ml` dependencies.  Print the tables with:  python -m poketrix.opponent.evaluation
"""

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy

from .dataset import DATASET_FILE, STAYED, Row, load
from .features import ACTIONS, FEATURES, DecisionView
from .models import Heuristic, XgbModel, model_paths, softmax

LABELS = {**{action: index for index, action in enumerate(ACTIONS)}, STAYED: len(ACTIONS)}
ATTACK, UTILITY, SWITCH = (ACTIONS.index(action) for action in ("attack", "utility", "switch"))
VISIBLE = len(ACTIONS)  # labels below this are visible choices
CLIP = 1e-6  # a probability of 0 for what happened costs −log(CLIP), not infinity
BINS = 10
BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED = 2_000, 20261502
POOLED = 0


@dataclass(frozen=True)
class Table:
    """Rows as arrays: features, label (`LABELS`), generation and battle."""

    x: numpy.ndarray
    y: numpy.ndarray
    gen: numpy.ndarray
    battle: numpy.ndarray

    def where(self, mask: numpy.ndarray) -> "Table":
        return Table(self.x[mask], self.y[mask], self.gen[mask], self.battle[mask])


def table(rows: Sequence[Row]) -> Table:
    return Table(
        numpy.array([row.features for row in rows], dtype=numpy.float64),
        numpy.array([LABELS[row.action] for row in rows]),
        numpy.array([row.gen for row in rows]),
        numpy.array([row.battle for row in rows]),
    )


def splits(path: Path = DATASET_FILE) -> dict[str, Table]:
    rows = list(load(path))
    return {name: table([row for row in rows if row.split == name])
            for name in ("train", "valid", "test")}


# --------------------------------------------------------------------------- the arithmetic


def stay_shares(train: Table) -> dict[int, float]:
    """Per generation: the attack share among visible moves. A `stay` row is that much
    attack, and the rest utility, when the model learns from it."""
    shares = {}
    for gen in numpy.unique(train.gen):
        y = train.y[train.gen == gen]
        attacks, utilities = (y == ATTACK).sum(), (y == UTILITY).sum()
        shares[int(gen)] = float(attacks / (attacks + utilities))
    return shares


def row_losses(p: numpy.ndarray, y: numpy.ndarray) -> numpy.ndarray:
    """−log of the probability given to what happened, row by row."""
    stayed = y == LABELS[STAYED]
    chosen = numpy.where(stayed, 0, y)
    likelihood = numpy.where(stayed, p[:, ATTACK] + p[:, UTILITY],
                             p[numpy.arange(len(y)), chosen])
    return -numpy.log(numpy.clip(likelihood, CLIP, 1.0))


def brier(p: numpy.ndarray, y: numpy.ndarray) -> float:
    return float(((p - numpy.eye(len(ACTIONS))[y]) ** 2).sum(axis=1).mean())


def reliability(confidence: numpy.ndarray, hit: numpy.ndarray) -> tuple[list[tuple], float]:
    """10 equal-width bins of predicted probability: (low, high, rows, mean predicted,
    observed share) each, and the expected calibration error."""
    bins = numpy.minimum((confidence * BINS).astype(int), BINS - 1)
    table_rows, error = [], 0.0
    for b in range(BINS):
        inside = bins == b
        if inside.any():
            predicted, observed = confidence[inside].mean(), hit[inside].mean()
            table_rows.append((b / BINS, (b + 1) / BINS, int(inside.sum()), predicted, observed))
            error += inside.sum() / len(confidence) * abs(predicted - observed)
    return table_rows, float(error)


def improvement_interval(gain: numpy.ndarray, battle: numpy.ndarray) -> tuple[float, float, float]:
    """Mean per-row gain and its 95% bootstrap interval, resampling whole battles."""
    ids, index = numpy.unique(battle, return_inverse=True)
    sums = numpy.bincount(index, weights=gain)
    counts = numpy.bincount(index)
    chooser = numpy.random.default_rng(BOOTSTRAP_SEED)
    picks = chooser.integers(0, len(ids), size=(BOOTSTRAP_RESAMPLES, len(ids)))
    means = numpy.sort(sums[picks].sum(axis=1) / counts[picks].sum(axis=1))
    return (float(gain.mean()), float(means[int(0.025 * BOOTSTRAP_RESAMPLES)]),
            float(means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]))


# --------------------------------------------------------------------------- the predictors


Predictor = Callable[[Table], numpy.ndarray]  # rows in, one probability per action out


def base_rates(train: Table) -> Predictor:
    shares = stay_shares(train)
    rates = {}
    for gen, share in shares.items():
        y = train.y[train.gen == gen]
        counts = numpy.array([(y == label).sum() for label in range(len(ACTIONS))], dtype=float)
        stayed = (y == LABELS[STAYED]).sum()
        counts[ATTACK] += share * stayed
        counts[UTILITY] += (1 - share) * stayed
        rates[gen] = counts / counts.sum()
    return lambda rows: numpy.array([rates[int(gen)] for gen in rows.gen])


def heuristic(rows: Table) -> numpy.ndarray:
    model = Heuristic()
    return numpy.array([
        [getattr(prediction, f"p_{action}") for action in ACTIONS]
        for prediction in (model.predict(DecisionView(*vector)) for vector in rows.x)
    ])


def learned(model: XgbModel, temperature: float) -> Predictor:
    def predict(rows: Table) -> numpy.ndarray:
        return numpy.array([softmax(m, temperature) for m in model.margins(rows.x)])
    return predict


def without_rating(predictor: Predictor) -> Predictor:
    """The predictor where no rating is known: unrated games and the simulator's bots."""
    column = FEATURES.index("rating")

    def predict(rows: Table) -> numpy.ndarray:
        x = rows.x.copy()
        x[:, column] = numpy.nan
        return predictor(Table(x, rows.y, rows.gen, rows.battle))
    return predict


# --------------------------------------------------------------------------- the report


def scores(p: numpy.ndarray, rows: Table) -> dict[str, float]:
    visible = rows.y < VISIBLE
    pv, yv = p[visible], rows.y[visible]
    switched = (rows.y == SWITCH).astype(float)
    return {
        "rows": len(rows.y), "log_loss": float(row_losses(p, rows.y).mean()),
        "brier": brier(pv, yv), "accuracy": float((pv.argmax(axis=1) == yv).mean()),
        "ece": reliability(pv.max(axis=1), (pv.argmax(axis=1) == yv).astype(float))[1],
        "switch_ece": reliability(p[:, SWITCH], switched)[1],
    }


def measure(predictors: dict[str, Predictor], test: Table, baselines: Sequence[str],
            model: str) -> dict:
    """Every score per generation and pooled, and the model's gain over each baseline."""
    p = {name: predict(test) for name, predict in predictors.items()}
    losses = {name: row_losses(probabilities, test.y) for name, probabilities in p.items()}
    report: dict = {"scores": {}, "gains": {}, "clipped": {}}
    for gen in [*sorted(int(g) for g in numpy.unique(test.gen)), POOLED]:
        mask = numpy.ones(len(test.y), bool) if gen == POOLED else test.gen == gen
        rows = test.where(mask)
        report["scores"][gen] = {name: scores(probs[mask], rows) for name, probs in p.items()}
        report["gains"][gen] = {
            base: improvement_interval(losses[base][mask] - losses[model][mask], rows.battle)
            for base in baselines
        }
    report["clipped"] = {name: int((loss >= -numpy.log(CLIP) - 1e-9).sum())
                         for name, loss in losses.items()}
    visible = test.y < VISIBLE
    pm = p[model][visible]
    report["reliability"] = reliability(pm.max(axis=1),
                                        (pm.argmax(axis=1) == test.y[visible]).astype(float))[0]
    report["switch_reliability"] = reliability(p[model][:, SWITCH],
                                               (test.y == SWITCH).astype(float))[0]
    return report


def print_report(report: dict, model: str) -> None:
    print("| Gen | Predictor | Rows | Log-loss | Brier | Accuracy | ECE (top choice) "
          "| ECE (switch) |")
    print("|---|---|---|---|---|---|---|---|")
    for gen, by_name in report["scores"].items():
        for name, s in by_name.items():
            print(f"| {gen or 'all'} | {name} | {s['rows']} | {s['log_loss']:.4f} "
                  f"| {s['brier']:.4f} | {s['accuracy']:.1%} | {s['ece']:.4f} "
                  f"| {s['switch_ece']:.4f} |")
    print(f"\nLog-loss improvement of {model} (battle bootstrap, 95%)\n")
    print("| Gen | Over | Improvement | 95% interval |")
    print("|---|---|---|---|")
    for gen, by_base in report["gains"].items():
        for base, (gain, low, high) in by_base.items():
            print(f"| {gen or 'all'} | {base} | {gain:+.4f} | {low:+.4f} to {high:+.4f} |")
    for title, key in (("top choice, visible choices", "reliability"),
                       ("P(switch), every row", "switch_reliability")):
        print(f"\nReliability of {model}, {title} (pooled test split)\n")
        print("| Bin | Rows | Mean predicted | Observed |")
        print("|---|---|---|---|")
        for low, high, n, predicted, observed in report[key]:
            print(f"| {low:.1f}–{high:.1f} | {n} | {predicted:.3f} | {observed:.3f} |")
    print(f"\nRows given a probability under {CLIP} for what happened: {report['clipped']}")


def evaluate(model: XgbModel, temperature: float, data: dict[str, Table]) -> dict:
    predictors = {
        "base rates": base_rates(data["train"]), "heuristic-0": heuristic,
        model.version: learned(model, temperature),
        f"{model.version}, no rating": without_rating(learned(model, temperature)),
    }
    return measure(predictors, data["test"], ("base rates", "heuristic-0"), model.version)


def main() -> None:
    version = sys.argv[1] if sys.argv[1:] else "xgb-1"
    manifest = json.loads(model_paths(version)[1].read_text(encoding="utf-8"))
    model = XgbModel(version)
    report = evaluate(model, manifest["temperature"], splits())
    sys.stdout.reconfigure(encoding="utf-8")
    print_report(report, version)


if __name__ == "__main__":
    main()
