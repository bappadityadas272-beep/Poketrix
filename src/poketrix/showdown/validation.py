"""Checks the parser's evidence against simulated battles whose true teams are known.

The fixtures (tests/fixtures/battles_gen{N}.json, written by scripts/randbats/build_battles.mjs)
hold the spectator log of each battle next to both real teams. For every revealed Pokémon:

- every move the parser calls revealed must be in the true set;
- the item and ability it reports as original must be the true ones;
- nothing it rules out may be true.

Print a summary with:  python -m poketrix.showdown.validation [directory]
"""

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from poketrix.schemas import Generation, moves_fit

from .replay import BattleRecord, parse_battle

# tests/fixtures/ in the repo
FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


@dataclass
class Report:
    """Totals over a set of battles. `violations` must stay empty."""

    battles: int = 0
    turns: int = 0
    pokemon: int = 0
    revealed_moves: int = 0
    items_identified: int = 0
    abilities_identified: int = 0
    ruled_out: Counter = field(default_factory=Counter)  # item or ability id -> how often
    violations: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    unknown_message_types: Counter = field(default_factory=Counter)


def load_battles(gen: Generation | int, directory: Path = FIXTURE_DIR) -> list[dict]:
    path = directory / f"battles_gen{int(gen)}.json"
    return json.loads(path.read_text(encoding="utf-8"))["battles"]


def check_battle(record: BattleRecord, teams: dict, report: Report, label: str = "") -> None:
    """Compare the final evidence of one parsed battle with the true teams."""
    report.battles += 1
    report.turns += record.snapshots[-1].turn
    report.anomalies += [f"{label} {text}" for text in record.anomalies]
    report.unknown_message_types.update(record.unknown_message_types)
    last = record.snapshots[-1]
    for found in last.evidence:
        side = last.state.sides[found.player]
        nickname_species = side.team[found.team_index].species.name
        truth = _true_set(teams[found.player.value], found.species_id, nickname_species)
        where = f"{label} {found.player.value} {found.species_id}"
        if truth is None:
            report.violations.append(f"{where}: not in the true team")
            continue
        evidence = found.evidence
        report.pokemon += 1
        report.revealed_moves += len(evidence.revealed_moves)
        for move in evidence.revealed_moves:
            if not moves_fit([move], truth["moves"]):
                report.violations.append(f"{where}: {move} is not in the true set {truth['moves']}")
        if evidence.item is not None:
            report.items_identified += 1
            if evidence.item != truth["item"]:
                report.violations.append(f"{where}: item {evidence.item}, truly {truth['item']}")
        if evidence.ability is not None:
            report.abilities_identified += 1
            if evidence.ability != truth["ability"]:
                report.violations.append(
                    f"{where}: ability {evidence.ability}, truly {truth['ability']}"
                )
        report.ruled_out.update(evidence.ruled_out_items)
        report.ruled_out.update(evidence.ruled_out_abilities)
        if truth["item"] in evidence.ruled_out_items:
            report.violations.append(f"{where}: ruled out its true item {truth['item']}")
        if truth["ability"] in evidence.ruled_out_abilities:
            report.violations.append(f"{where}: ruled out its true ability {truth['ability']}")


def _true_set(team: list[dict], species_id: str, species_name: str) -> dict | None:
    def key(text: str) -> str:
        return "".join(c for c in text.lower() if c.isalnum())

    for member in team:
        if species_id in (key(member["species"]), key(member["name"])):
            return member
    # A cosmetic forme (an Unown letter) is in the log under its own name.
    return next((m for m in team if key(m["species"]).startswith(species_id)), None)


def validate(gen: Generation | int, directory: Path = FIXTURE_DIR) -> Report:
    report = Report()
    for index, battle in enumerate(load_battles(gen, directory)):
        record = parse_battle(battle["spectator"], strict=True)
        check_battle(record, battle["teams"], report, label=f"gen{int(gen)} #{index}")
    return report


def main() -> None:
    directory = Path(sys.argv[1]) if sys.argv[1:] else FIXTURE_DIR
    print("| Gen | Battles | Turns | Pokémon seen | Moves revealed | Items identified "
          "| Abilities identified | Ruled out | Violations | Anomalies |")
    print("|-----|---------|-------|--------------|----------------|------------------"
          "|----------------------|-----------|------------|-----------|")
    for gen in Generation:
        r = validate(gen, directory)
        print(f"| {int(gen)} | {r.battles} | {r.turns} | {r.pokemon} | {r.revealed_moves} "
              f"| {r.items_identified} | {r.abilities_identified} | {sum(r.ruled_out.values())} "
              f"| {len(r.violations)} | {len(r.anomalies)} |")
        for line in (r.violations + r.anomalies)[:20]:
            print(f"  ! {line}")


if __name__ == "__main__":
    main()
