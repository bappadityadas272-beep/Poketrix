"""How long a decision takes, per stage, over the decisions of simulated battles.

Print the table with:  python -m poketrix.advisor.latency [battle directory] [decisions per gen]

The directory holds battles with player logs (tests/fixtures by default; the 500-battle
corpus is built with `node build_battles.mjs 500 DIR 500`). Decisions are sampled with a fixed
seed, so two runs time the same ones.
"""

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from poketrix.schemas import Generation, TurnReport
from poketrix.showdown import parse_battle
from poketrix.showdown.validation import FIXTURE_DIR, load_battles

from .pipeline import STAGE_BUDGET_MS, TurnAdvisor

SAMPLE_SEED = 20261301
STAGES = tuple(STAGE_BUDGET_MS)


@dataclass
class Latency:
    decisions: int = 0
    total_ms: list[float] = field(default_factory=list)
    stage_ms: dict[str, list[float]] = field(default_factory=lambda: {s: [] for s in STAGES})
    statuses: dict[str, int] = field(default_factory=dict)

    def add(self, report: TurnReport) -> None:
        self.decisions += 1
        self.total_ms.append(report.latency_ms)
        for stage in STAGES:
            self.stage_ms[stage].append(getattr(report, stage).latency_ms)
        status = report.status.value
        self.statuses[status] = self.statuses.get(status, 0) + 1


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else 0.0


def measure(gen: Generation | int, directory: Path = FIXTURE_DIR, sample: int | None = None,
            advisor: TurnAdvisor | None = None) -> Latency:
    advisor = advisor or TurnAdvisor()
    chooser = random.Random(SAMPLE_SEED)
    battles = [battle for battle in load_battles(gen, directory) if "player" in battle]
    chooser.shuffle(battles)
    decisions = []
    for battle in battles:
        if sample is not None and len(decisions) >= 2 * sample:
            break  # enough battles read to draw the sample from
        decisions += [
            snapshot for snapshot in parse_battle(battle["player"]).snapshots
            if snapshot.state.me.request is not None
        ]
    if sample is not None and sample < len(decisions):
        decisions = chooser.sample(decisions, sample)
    if decisions:
        advisor.advise(decisions[0])  # load the prior and the dex before timing
    latency = Latency()
    for snapshot in decisions:
        latency.add(advisor.advise(snapshot))
    return latency


def main() -> None:
    directory = Path(sys.argv[1]) if sys.argv[1:] else FIXTURE_DIR
    sample = int(sys.argv[2]) if sys.argv[2:] else None
    columns = " | ".join(f"{stage} p50 / p95" for stage in STAGES)
    print(f"| Gen | Decisions | Total p50 | Total p95 | Max | {columns} | Not `ok` |")
    print("|-----|-----------|-----------|-----------|-----|" + "---|" * (len(STAGES) + 1))
    for gen in Generation:
        found = measure(gen, directory, sample)
        stages = " | ".join(
            f"{percentile(found.stage_ms[s], 0.5):.1f} / {percentile(found.stage_ms[s], 0.95):.1f}"
            for s in STAGES
        )
        other = {k: v for k, v in found.statuses.items() if k != "ok"}
        print(f"| {int(gen)} | {found.decisions} | {percentile(found.total_ms, 0.5):.1f} "
              f"| {percentile(found.total_ms, 0.95):.1f} | {max(found.total_ms, default=0):.1f} "
              f"| {stages} | {other or 0} |")


if __name__ == "__main__":
    main()
