"""Trains `xgb-1`, the learned opponent model, and saves it with its manifest.

Everything is chosen on the validation split: the depth and learning rate (a grid of four),
the number of trees (early stopping on validation log-loss) and the calibration temperature.
The test split is read once, at the end, for the metrics written into the manifest.

Needs the `ml` dependencies.  Run:  python -m poketrix.opponent.training
"""

import json
import math
import sys
from datetime import date
from time import perf_counter

import numpy
import xgboost

from .dataset import SPLIT_SEED, STAYED
from .evaluation import ATTACK, LABELS, UTILITY, Table, evaluate, print_report, row_losses, splits
from .evaluation import stay_shares as shares_of
from .features import ACTIONS, FEATURES, DecisionView
from .models import XgbModel, model_paths, softmax

VERSION = "xgb-1"
GRID = [(depth, rate) for depth in (3, 5) for rate in (0.05, 0.1)]
MAX_ROUNDS, PATIENCE = 3_000, 50
FIXED = {"objective": "multi:softprob", "num_class": len(ACTIONS), "eval_metric": "mlogloss",
         "tree_method": "hist", "seed": SPLIT_SEED, "nthread": 4}


def matrix(rows: Table, shares: dict[int, float]) -> xgboost.DMatrix:
    """A stay row becomes two: attack and utility, weighted by its generation's shares."""
    stayed = rows.y == LABELS[STAYED]
    share = numpy.array([shares[int(gen)] for gen in rows.gen[stayed]])
    x = numpy.concatenate([rows.x[~stayed], rows.x[stayed], rows.x[stayed]])
    y = numpy.concatenate([rows.y[~stayed], numpy.full(stayed.sum(), ATTACK),
                           numpy.full(stayed.sum(), UTILITY)])
    weight = numpy.concatenate([numpy.ones((~stayed).sum()), share, 1 - share])
    return xgboost.DMatrix(x, label=y, weight=weight, feature_names=list(FEATURES))


def probabilities(booster: xgboost.Booster, rows: Table, temperature: float) -> numpy.ndarray:
    margins = booster.inplace_predict(rows.x, predict_type="margin")
    return numpy.array([softmax(m, temperature) for m in margins])


def fit_temperature(booster: xgboost.Booster, valid: Table) -> float:
    """The temperature that minimises validation log-loss (golden-section search on its log)."""
    margins = booster.inplace_predict(valid.x, predict_type="margin")

    def loss(log_t: float) -> float:
        scaled = margins / math.exp(log_t)
        scaled -= scaled.max(axis=1, keepdims=True)
        p = numpy.exp(scaled)
        return float(row_losses(p / p.sum(axis=1, keepdims=True), valid.y).mean())

    low, high, ratio = math.log(0.25), math.log(4.0), (math.sqrt(5) - 1) / 2
    for _ in range(60):
        a, b = high - ratio * (high - low), low + ratio * (high - low)
        low, high = (low, b) if loss(a) < loss(b) else (a, high)
    return math.exp((low + high) / 2)


def search(train: xgboost.DMatrix, valid_matrix: xgboost.DMatrix, valid: Table) -> list[dict]:
    tried = []
    for depth, rate in GRID:
        booster = xgboost.train(
            FIXED | {"max_depth": depth, "eta": rate}, train, MAX_ROUNDS,
            evals=[(valid_matrix, "valid")], early_stopping_rounds=PATIENCE, verbose_eval=False,
        )
        trees = booster.best_iteration + 1
        booster = booster[:trees]
        loss = float(row_losses(probabilities(booster, valid, 1.0), valid.y).mean())
        tried.append({"max_depth": depth, "eta": rate, "trees": trees,
                      "valid_log_loss": loss, "booster": booster})
        print(f"  depth {depth}, rate {rate}: {tried[-1]['trees']} trees, "
              f"validation log-loss {loss:.4f}", flush=True)
    return tried


def latency_ms(model: XgbModel, rows: Table, count: int = 2_000) -> float:
    """Median time of one prediction from a view, as the turn engine makes it."""
    views = [DecisionView(*vector) for vector in rows.x[:count]]
    model.predict(views[0])
    times = []
    for view in views:
        started = perf_counter()
        model.predict(view)
        times.append((perf_counter() - started) * 1000)
    return sorted(times)[len(times) // 2]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    data = splits()
    shares = shares_of(data["train"])
    train, valid = matrix(data["train"], shares), matrix(data["valid"], shares)
    print(f"Search on {len(data['valid'].y)} validation decisions:")
    tried = search(train, valid, data["valid"])
    best = min(tried, key=lambda entry: entry["valid_log_loss"])
    booster = best.pop("booster")
    temperature = fit_temperature(booster, data["valid"])
    calibrated = float(row_losses(probabilities(booster, data["valid"], temperature),
                                  data["valid"].y).mean())
    print(f"Chosen: depth {best['max_depth']}, rate {best['eta']}; temperature "
          f"{temperature:.3f} (validation log-loss {best['valid_log_loss']:.4f} -> {calibrated:.4f})")

    model_file, manifest_file = model_paths(VERSION)
    model_file.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(model_file)
    manifest = {
        "version": VERSION, "trained": date.today().isoformat(),
        "xgboost": xgboost.__version__, "features": list(FEATURES), "actions": list(ACTIONS),
        "temperature": temperature, "split_seed": SPLIT_SEED,
        "stay_attack_share": {str(gen): share for gen, share in shares.items()},
        "params": FIXED | {key: best[key] for key in ("max_depth", "eta", "trees")},
        "search": [{key: value for key, value in entry.items() if key != "booster"}
                   for entry in tried],
        "valid_log_loss_calibrated": calibrated,
        "data": {name: {"decisions": len(rows.y),
                        "battles": sorted(set(rows.battle.tolist()))}
                 for name, rows in data.items()},
    }
    manifest_file.write_text(json.dumps(manifest, indent=1), encoding="utf-8", newline="\n")

    model = XgbModel(VERSION)
    report = evaluate(model, temperature, data)
    manifest["test"] = {
        "scores": {str(gen): by_name for gen, by_name in report["scores"].items()},
        "gains": {str(gen): by_base for gen, by_base in report["gains"].items()},
        "reliability": report["reliability"],
    }
    manifest["latency_ms_median"] = latency_ms(model, data["test"])
    importance = booster.get_score(importance_type="gain")
    manifest["importance_gain"] = dict(sorted(importance.items(), key=lambda kv: -kv[1]))
    manifest_file.write_text(json.dumps(manifest, indent=1), encoding="utf-8", newline="\n")
    print(f"Saved {model_file} and {manifest_file}\n")
    print_report(report, VERSION)
    print(f"\nOne prediction: {manifest['latency_ms_median']:.3f} ms (median)")
    print("\nFeatures by gain:")
    for name, gain in list(manifest["importance_gain"].items())[:10]:
        print(f"  {name}: {gain:.1f}")


if __name__ == "__main__":
    main()
