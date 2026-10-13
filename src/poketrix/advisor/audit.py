"""Sanity signals on what the engine advises, counted over many decisions.

- thrown-away knock-outs: a voluntary switch advised although a move that knocks out at least
  90% of the time, and acts first at least 90% of the time, was legal. Should be zero.
- voluntary switch rate: no target; a policy that switches a third of the time is suspect.
- self-KO moves advised (Explosion, Self-Destruct): should be rare and for a reason.

Print them for a directory of battles with:  python -m poketrix.advisor.audit [directory]
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

from poketrix.schemas import ActionKind, Generation, TurnReport
from poketrix.showdown import TurnSnapshot, parse_battle
from poketrix.showdown.validation import FIXTURE_DIR, load_battles

from .pipeline import TurnAdvisor
from .policy import SELF_FAINT

SURE = 0.9


@dataclass
class Guardrails:
    decisions: int = 0
    voluntary_switches: int = 0
    thrown_away: list[str] = field(default_factory=list)  # each case, with its numbers
    self_ko: list[str] = field(default_factory=list)

    def add(self, snapshot: TurnSnapshot, report: TurnReport, label: str = "") -> None:
        state, advice = snapshot.state, report.recommendation
        self.decisions += 1
        where = f"{label} turn {snapshot.turn}".strip()
        index = state.me.active_index
        if advice.move_id in SELF_FAINT:
            ko = report.numbers.get(f"our.{index}.{advice.move_id}.ko", 0.0)
            self.self_ko.append(
                f"{where}: {advice.move_id}, knock-out {ko:.0%}, "
                f"{state.me.alive_count} of ours and {state.opponent.alive_count} of theirs left"
            )
        if advice.action is not ActionKind.SWITCH or state.me.request.force_switch:
            return
        self.voluntary_switches += 1
        for move_id in state.me.request.available_moves:
            ko = report.numbers.get(f"our.{index}.{move_id}.ko", 0.0)
            first = report.numbers.get(f"our.{index}.{move_id}.first", 0.0)
            if ko >= SURE and first >= SURE:
                self.thrown_away.append(
                    f"{where}: switched although {move_id} knocks out {ko:.0%} and acts first "
                    f"{first:.0%}" + (" (a self-KO move)" if move_id in SELF_FAINT else "")
                )

    def merge(self, other: "Guardrails") -> None:
        self.decisions += other.decisions
        self.voluntary_switches += other.voluntary_switches
        self.thrown_away += other.thrown_away
        self.self_ko += other.self_ko


def audit(gen: Generation | int, directory: Path = FIXTURE_DIR,
          advisor: TurnAdvisor | None = None) -> Guardrails:
    """The guardrails over every decision of the player logs of one generation."""
    advisor, found = advisor or TurnAdvisor(), Guardrails()
    for number, battle in enumerate(load_battles(gen, directory)):
        if "player" not in battle:
            continue
        for snapshot in parse_battle(battle["player"]).snapshots:
            if snapshot.state.me.request is not None:
                found.add(snapshot, advisor.advise(snapshot), f"gen{int(gen)} #{number}")
    return found


def main() -> None:
    directory = Path(sys.argv[1]) if sys.argv[1:] else FIXTURE_DIR
    total = Guardrails()
    print("| Gen | Decisions | Voluntary switches | Thrown-away knock-outs | Self-KO advised |")
    print("|-----|-----------|--------------------|------------------------|-----------------|")
    for gen in Generation:
        found = audit(gen, directory)
        total.merge(found)
        print(f"| {int(gen)} | {found.decisions} | {found.voluntary_switches} "
              f"| {len(found.thrown_away)} | {len(found.self_ko)} |")
    share = total.voluntary_switches / max(1, total.decisions)
    print(f"| all | {total.decisions} | {total.voluntary_switches} ({share:.0%}) "
          f"| {len(total.thrown_away)} | {len(total.self_ko)} |")
    for line in total.thrown_away + total.self_ko:
        print(f"  {line}")


if __name__ == "__main__":
    main()
