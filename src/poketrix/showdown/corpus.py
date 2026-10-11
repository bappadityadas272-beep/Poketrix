"""Measurements over whole corpora: does the parser survive real replays, and how often does
what a battle reveals contradict every set the prior knows (its staleness)?

Real replays are downloaded by scripts/download_replays.py into data/raw/replays/ (git-ignored).
Only ladder games count towards staleness: tournament and challenge games may run under custom
rules (extra moves, other levels), which says nothing about the prior. Simulated battles, whose
true teams are known, give the floor: there a contradiction is either a set the prior never
sampled, or a bug in the evidence rules.

Print both with:  python -m poketrix.showdown.corpus [replay directory] [battle directory]
"""

import json
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path

from poketrix.schemas import Generation, SetEvidence, moves_fit
from poketrix.uncloak import SetPrior, Uncloaker, load_prior

from .replay import BattleRecord, parse_battle
from .tracker import UnsupportedBattleError
from .validation import FIXTURE_DIR, load_battles, true_set

REPLAY_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "replays"
_LADDER_GAME = "|rated|"  # the whole line; a tournament game adds a message after it

SPECIES_UNKNOWN = "species not in the prior"
MOVE_UNKNOWN = "a move the species never has in the prior"
ITEM_UNKNOWN = "an item the species never holds in the prior"
ABILITY_UNKNOWN = "an ability the species never has in the prior"
UNSEEN_COMBINATION = "known moves, item and ability in a combination the prior lacks"


def wilson_interval(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% confidence interval of a proportion (Wilson score)."""
    if total == 0:
        return 0.0, 1.0
    share = hits / total
    centre = share + z * z / (2 * total)
    spread = z * sqrt(share * (1 - share) / total + z * z / (4 * total * total))
    scale = 1 + z * z / total
    return max(0.0, (centre - spread) / scale), min(1.0, (centre + spread) / scale)


def contradiction(prior: SetPrior, species_id: str, evidence: SetEvidence) -> str | None:
    """Why no known set of the species fits the evidence; `None` when one does."""
    rows = [row.pokemon_set for row in prior.sets_for(species_id)]
    if not rows:
        return SPECIES_UNKNOWN
    if Uncloaker(prior).infer(species_id, evidence).tier == 1:
        return None
    if not moves_fit(evidence.revealed_moves, {move for row in rows for move in row.moves}):
        return MOVE_UNKNOWN
    if evidence.item is not None and evidence.item not in {row.item for row in rows}:
        return ITEM_UNKNOWN
    if evidence.ability is not None and evidence.ability not in {row.ability for row in rows}:
        return ABILITY_UNKNOWN
    return UNSEEN_COMBINATION


@dataclass
class Staleness:
    """How many revealed Pokémon contradict every known set, and why."""

    pokemon: int = 0
    reasons: Counter = field(default_factory=Counter)
    examples: Counter = field(default_factory=Counter)  # "species: what was seen" -> count

    @property
    def contradicted(self) -> int:
        return sum(self.reasons.values())

    def add(self, record: BattleRecord, prior: SetPrior) -> None:
        for found in record.snapshots[-1].evidence:
            self.pokemon += 1
            reason = contradiction(prior, found.species_id, found.evidence)
            if reason is not None:
                self.reasons[reason] += 1
                seen = found.evidence
                self.examples[
                    f"{found.species_id}: {sorted(seen.revealed_moves)} {seen.item} {seen.ability}"
                ] += 1


@dataclass
class Robustness:
    """What the parser made of a set of real replays. `failures` must stay empty."""

    replays: int = 0
    ladder_games: int = 0
    turns: int = 0
    unfinished: int = 0  # logs that stop before a winner is named
    unsupported: Counter = field(default_factory=Counter)  # out of scope, by reason
    failures: list[str] = field(default_factory=list)  # replays that raised
    unknown_message_types: Counter = field(default_factory=Counter)
    # By kind, the Pokémon's name removed; ladder games and the rest apart.
    anomalies: Counter = field(default_factory=Counter)
    anomalies_elsewhere: Counter = field(default_factory=Counter)
    staleness: Staleness = field(default_factory=Staleness)  # ladder games
    staleness_elsewhere: Staleness = field(default_factory=Staleness)  # tournaments, challenges


def load_replays(gen: Generation | int, directory: Path = REPLAY_DIR) -> Iterator[tuple[str, str]]:
    """(replay id, log) for every downloaded replay of a generation."""
    for path in sorted((directory / f"gen{int(gen)}").glob("*.json")):
        replay = json.loads(path.read_text(encoding="utf-8"))
        yield replay["id"], replay["log"]


def measure_replays(gen: Generation | int, directory: Path = REPLAY_DIR) -> Robustness:
    """Parse every replay leniently: nothing may raise, and everything odd is counted."""
    report, prior = Robustness(), load_prior(gen)
    for replay_id, log in load_replays(gen, directory):
        report.replays += 1
        ladder = _LADDER_GAME in log.splitlines()
        report.ladder_games += ladder
        try:
            record = parse_battle(log)
        except UnsupportedBattleError as error:
            report.unsupported[str(error)] += 1
            continue
        except Exception as error:  # noqa: BLE001 - the point is to find whatever raises
            report.failures.append(f"{replay_id}: {type(error).__name__}: {error}"[:300])
            continue
        if not record.snapshots:
            report.unfinished += 1  # the players left before the first turn
            continue
        report.turns += record.snapshots[-1].turn
        report.unfinished += not record.ended
        report.unknown_message_types.update(record.unknown_message_types)
        kinds = [text.split(": ", 1)[1] for text in record.anomalies]
        (report.anomalies if ladder else report.anomalies_elsewhere).update(kinds)
        (report.staleness if ladder else report.staleness_elsewhere).add(record, prior)
    return report


@dataclass
class Floor:
    """Staleness where the truth is known: every contradiction is explained or is a bug."""

    staleness: Staleness = field(default_factory=Staleness)
    true_set_unknown: int = 0  # the generator produced a set the prior never sampled
    bugs: list[str] = field(default_factory=list)  # the true set is known, yet was ruled out


def measure_floor(gen: Generation | int, directory: Path = FIXTURE_DIR) -> Floor:
    floor, prior = Floor(), load_prior(gen)
    for index, battle in enumerate(load_battles(gen, directory)):
        record = parse_battle(battle["spectator"], strict=True)
        floor.staleness.add(record, prior)
        last = record.snapshots[-1]
        for found in last.evidence:
            if contradiction(prior, found.species_id, found.evidence) is None:
                continue
            name = last.state.sides[found.player].team[found.team_index].species.name
            truth = true_set(battle["teams"][found.player.value], found.species_id, name)
            known = any(
                (sorted(row.pokemon_set.moves), row.pokemon_set.item, row.pokemon_set.ability)
                == (sorted(truth["moves"]), truth["item"], truth["ability"])
                for row in prior.sets_for(found.species_id)
            )
            if known:
                floor.bugs.append(f"gen{int(gen)} #{index} {found.species_id}: {found.evidence}")
            else:
                floor.true_set_unknown += 1
    return floor


def _rate(hits: int, total: int) -> str:
    low, high = wilson_interval(hits, total)
    share = hits / total if total else 0.0
    return f"{hits} / {total} = {share:.2%} ({low:.2%} to {high:.2%})"


def main() -> None:
    replay_dir = Path(sys.argv[1]) if sys.argv[1:] else REPLAY_DIR
    battle_dir = Path(sys.argv[2]) if sys.argv[2:] else FIXTURE_DIR
    reasons = (SPECIES_UNKNOWN, MOVE_UNKNOWN, ITEM_UNKNOWN, ABILITY_UNKNOWN, UNSEEN_COMBINATION)

    print("Simulated battles (the floor)\n")
    print("| Gen | Contradicted (95% interval) | True set not in the prior | Bugs |")
    print("|-----|-----------------------------|---------------------------|------|")
    for gen in Generation:
        floor = measure_floor(gen, battle_dir)
        stale = floor.staleness
        print(f"| {int(gen)} | {_rate(stale.contradicted, stale.pokemon)} "
              f"| {floor.true_set_unknown} | {len(floor.bugs)} |")
        for line in floor.bugs[:10]:
            print(f"  ! {line}")

    reports = {gen: measure_replays(gen, replay_dir) for gen in Generation}
    print("\nReal replays: robustness\n")
    print("| Gen | Replays | Ladder games | Raised | Out of scope | Unfinished | Turns "
          "| Unknown message types | Anomalies, ladder | Anomalies, other games |")
    print("|-----|---------|--------------|--------|--------------|------------|-------"
          "|-----------------------|-------------------|------------------------|")
    for gen, report in reports.items():
        print(f"| {int(gen)} | {report.replays} | {report.ladder_games} | {len(report.failures)} "
              f"| {dict(report.unsupported) or 0} | {report.unfinished} | {report.turns} "
              f"| {dict(report.unknown_message_types) or 0} | {sum(report.anomalies.values())} "
              f"| {sum(report.anomalies_elsewhere.values())} |")

    print("\nReal replays: staleness of the prior\n")
    print("| Gen | Games | Contradicted (95% interval) | " + " | ".join(reasons) + " |")
    print("|-----|-------|-----------------------------|" + "---|" * len(reasons))
    for gen, report in reports.items():
        for games, stale in (("ladder", report.staleness), ("other", report.staleness_elsewhere)):
            print(f"| {int(gen)} | {games} | {_rate(stale.contradicted, stale.pokemon)} | "
                  + " | ".join(str(stale.reasons[reason]) for reason in reasons) + " |")

    for gen, report in reports.items():
        print(f"\nGen {int(gen)}")
        for line in report.failures[:10]:
            print(f"  raised: {line}")
        for kind, count in (report.anomalies + report.anomalies_elsewhere).most_common(10):
            print(f"  anomaly x{count} ({report.anomalies[kind]} on the ladder): {kind}")
        species = Counter()
        for seen, count in report.staleness.examples.items():
            species[seen.split(":")[0]] += count
        if species:
            print(f"  contradicted on the ladder, by species: {dict(species.most_common())}")
        for seen, count in report.staleness.examples.most_common(15):
            print(f"  contradicted on the ladder x{count}: {seen}")


if __name__ == "__main__":
    main()
