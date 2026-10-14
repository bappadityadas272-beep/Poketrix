"""Display calibration of xgb-1 (ruling 15-R): isotonic maps, fitted by cross-fitting.

The temperature fitted in training leaves the tail of P(switch) overconfident (on the test
split, about 0.85 predicted against 0.40 observed). Two isotonic maps fix the shown odds:
one for P(switch), learned on every row (a switch is always visible), and one for the attack
share of the rest, learned on the rows whose move is visible. Their composition always sums to 1.

Only train and validation battles are used; the test split is not read. They are cut into 5
folds by battle. Each fold is predicted by trees trained on the other four, with xgb-1's own
settings, which gives honest out-of-fold predictions; the maps are fitted on those. The
reliability of the maps is measured the same way: fitted on four folds' predictions,
checked on the fifth. If any switch bin from 0.7 up is off by more than `TAIL_TOLERANCE`, however
few rows it holds, shown switch odds stay capped at "70%+".

Needs the `ml` dependencies.  Run:  python -m poketrix.opponent.calibration
"""

import json
import random
import sys

import numpy
import xgboost

from .evaluation import ATTACK, SWITCH, UTILITY, VISIBLE, Table, reliability, splits, stay_shares
from .models import Isotonic, calibrated, model_paths, softmax
from .training import FIXED, VERSION, matrix

FOLDS, FOLD_SEED = 5, 20261503
SWITCH_CAP = 0.70
TAIL_TOLERANCE = 0.10


def fit_isotonic(x: numpy.ndarray, hit: numpy.ndarray) -> Isotonic:
    """Pool adjacent violators: the best non-decreasing fit of `hit` against `x`."""
    order = numpy.argsort(x, kind="stable")
    blocks: list[list[float]] = []  # [sum of x, sum of hits, rows]
    for xi, hi in zip(x[order], hit[order], strict=True):
        blocks.append([xi, hi, 1.0])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] >= blocks[-1][1] / blocks[-1][2]:
            last = blocks.pop()
            blocks[-1] = [a + b for a, b in zip(blocks[-1], last, strict=True)]
    return Isotonic(tuple(b[0] / b[2] for b in blocks), tuple(b[1] / b[2] for b in blocks))


def fit_maps(p: numpy.ndarray, y: numpy.ndarray) -> dict[str, Isotonic]:
    staying = (y == ATTACK) | (y == UTILITY)
    share = p[:, ATTACK] / numpy.maximum(p[:, ATTACK] + p[:, UTILITY], 1e-12)
    return {"switch": fit_isotonic(p[:, SWITCH], (y == SWITCH).astype(float)),
            "attack_share": fit_isotonic(share[staying], (y[staying] == ATTACK).astype(float))}


def apply_maps(maps: dict[str, Isotonic], p: numpy.ndarray) -> numpy.ndarray:
    return numpy.array([calibrated(maps["switch"], maps["attack_share"], row) for row in p])


def folds(battles: numpy.ndarray) -> numpy.ndarray:
    ids = sorted(set(battles.tolist()))
    random.Random(FOLD_SEED).shuffle(ids)
    fold_of = {battle: number % FOLDS for number, battle in enumerate(ids)}
    return numpy.array([fold_of[battle] for battle in battles])


def out_of_fold(rows: Table, fold: numpy.ndarray, params: dict, trees: int) -> numpy.ndarray:
    shares = stay_shares(rows)
    found = numpy.zeros((len(rows.y), 3))
    for k in range(FOLDS):
        booster = xgboost.train(params, matrix(rows.where(fold != k), shares), trees)
        margins = booster.inplace_predict(rows.x[fold == k], predict_type="margin")
        found[fold == k] = [softmax(m, 1.0) for m in margins]
    return found


def tables(p: numpy.ndarray, y: numpy.ndarray) -> dict:
    visible = y < VISIBLE
    pv = p[visible]
    return {"switch": reliability(p[:, SWITCH], (y == SWITCH).astype(float)),
            "top": reliability(pv.max(axis=1), (pv.argmax(axis=1) == y[visible]).astype(float))}


def tail_holds(switch_table: list[tuple]) -> bool:
    return all(abs(predicted - observed) <= TAIL_TOLERANCE
               for low, _, _, predicted, observed in switch_table if low >= SWITCH_CAP - 1e-9)


def _print(title: str, found: dict) -> None:
    for name, label in (("switch", "P(switch), every row"), ("top", "top choice, visible rows")):
        rows, error = found[name]
        print(f"\n{title}: {label} (ECE {error:.4f})\n")
        print("| Bin | Rows | Mean predicted | Observed |")
        print("|---|---|---|---|")
        for low, high, n, predicted, observed in rows:
            print(f"| {low:.1f}–{high:.1f} | {n} | {predicted:.3f} | {observed:.3f} |")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    data = splits()
    rows = Table(*(numpy.concatenate([getattr(data["train"], f), getattr(data["valid"], f)])
                   for f in ("x", "y", "gen", "battle")))
    manifest_file = model_paths(VERSION)[1]
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    params = FIXED | {key: manifest["params"][key] for key in ("max_depth", "eta")}
    fold = folds(rows.battle)
    print(f"Cross-fitting on {len(rows.y)} decisions from {len(set(rows.battle))} battles "
          f"(train + validation), {FOLDS} folds by battle")
    raw = out_of_fold(rows, fold, params, manifest["params"]["trees"])
    checked = numpy.zeros_like(raw)
    for k in range(FOLDS):
        maps = fit_maps(raw[fold != k], rows.y[fold != k])
        checked[fold == k] = apply_maps(maps, raw[fold == k])
    before, after = tables(raw, rows.y), tables(checked, rows.y)
    _print("Out of fold, before the maps", before)
    _print("Out of fold, with the maps (fitted on the other four folds)", after)
    holds = tail_holds(after["switch"][0])
    final = fit_maps(raw, rows.y)
    manifest["display_calibration"] = {
        "method": "isotonic, cross-fitted on train + valid (5 folds by battle, seed "
                  f"{FOLD_SEED}); the test split was not read",
        "maps": {name: {"x": list(m.x), "y": list(m.y)} for name, m in final.items()},
        "switch_cap": None if holds else SWITCH_CAP,
        "cross_fitted": {"before": before, "after": after},
    }
    manifest_file.write_text(json.dumps(manifest, indent=1), encoding="utf-8", newline="\n")
    verdict = "yes, no cap" if holds else f"no: switch odds over {SWITCH_CAP:.0%} shown as 70%+"
    print(f"\nSwitch bins from {SWITCH_CAP} up within ±{TAIL_TOLERANCE}: {verdict}")
    print(f"Maps written to {manifest_file}")


if __name__ == "__main__":
    main()
