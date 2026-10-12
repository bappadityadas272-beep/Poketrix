"""Checks the parser's evidence against simulated battles whose true teams are known.

The fixtures (tests/fixtures/battles_gen{N}.json, written by scripts/randbats/build_battles.mjs)
hold the spectator log of each battle next to both real teams. For every revealed Pokémon:

- every move the parser calls revealed must be in the true set;
- the item and ability it reports as original must be the true ones;
- nothing it rules out may be true.

Battles that also hold player 1's own log (`player`) check player mode the same way: our six
sets must be the true ones, every request must agree with what the log had shown, and the
opponent must look exactly as it does to a spectator.

Print a summary with:  python -m poketrix.showdown.validation [directory]
"""

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from poketrix.dex import Dex, UnknownDexEntryError
from poketrix.schemas import FORCED_MOVES, Generation, PlayerSlot, Species, moves_fit

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
    rules: Counter = field(default_factory=Counter)  # evidence rule -> times it fired


@dataclass
class PlayerReport:
    """Totals over the battles that hold a player's own log. `violations` must stay empty."""

    battles: int = 0
    decisions: int = 0
    forced_switches: int = 0
    own_pokemon: int = 0
    # Offered moves that are not in the active Pokémon's set, by reason.
    outside_the_set: Counter = field(default_factory=Counter)
    disagreements: Counter = field(default_factory=Counter)  # request against log, by kind
    violations: list[str] = field(default_factory=list)


def load_battles(gen: Generation | int, directory: Path = FIXTURE_DIR) -> list[dict]:
    path = directory / f"battles_gen{int(gen)}.json"
    return json.loads(path.read_text(encoding="utf-8"))["battles"]


def check_battle(record: BattleRecord, teams: dict, report: Report, label: str = "") -> None:
    """Compare the final evidence of one parsed battle with the true teams."""
    report.battles += 1
    report.turns += record.snapshots[-1].turn
    report.anomalies += [f"{label} {text}" for text in record.anomalies]
    report.unknown_message_types.update(record.unknown_message_types)
    report.rules.update(record.rule_counts)
    last = record.snapshots[-1]
    for found in last.evidence:
        side = last.state.sides[found.player]
        nickname_species = side.team[found.team_index].species.name
        truth = true_set(teams[found.player.value], found.species_id, nickname_species)
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


def check_player_battle(battle: dict, report: PlayerReport, label: str = "") -> None:
    """Player mode against the truth: our sets, the requests, and the spectator's view."""
    record = parse_battle(battle["player"], strict=True)
    public = parse_battle(battle["spectator"], perspective=record.player, strict=True)
    me = record.player
    report.battles += 1
    report.disagreements.update(record.request_disagreements)
    report.violations += [f"{label} {text}" for text in record.anomalies]
    if me is None:
        report.violations.append(f"{label}: no request found in the player's log")
        return
    them = PlayerSlot.P2 if me is PlayerSlot.P1 else PlayerSlot.P1

    truths = battle["teams"][me.value]
    team = record.snapshots[0].state.me.team
    dex = Dex(record.snapshots[0].state.generation)
    if len(team) != len(truths):
        report.violations.append(f"{label}: {len(team)} of our Pokémon, truly {len(truths)}")
    for mon, truth in zip(team, truths, strict=False):
        report.own_pokemon += 1
        own = mon.known_set
        found = (own.level, sorted(own.moves), own.item, own.ability)
        true = (truth["level"], sorted(truth["moves"]), truth["item"], truth["ability"])
        if found != true or not _is_species(dex, own.species, truth["species"]):
            report.violations.append(
                f"{label}: our set {own.species.name} {found}, truly {truth['species']} {true}"
            )

    turn_starts = {}
    for snapshot in record.snapshots:
        request = snapshot.state.me.request
        if request is None:
            if not snapshot.final:
                report.violations.append(f"{label} turn {snapshot.turn}: a decision with no request")
            continue
        report.decisions += 1
        report.forced_switches += request.force_switch
        active = snapshot.state.me.active
        for move in request.available_moves:
            if move in FORCED_MOVES:
                report.outside_the_set[move] += 1
            elif not moves_fit([move], active.known_set.moves):
                reason = "transform" if "transform" in active.volatiles else "mimic"
                report.outside_the_set[f"while under {reason}"] += 1
        if not request.force_switch:
            turn_starts.setdefault(snapshot.turn, snapshot)

    for seen in public.snapshots:
        ours = turn_starts.get(seen.turn)
        if seen.final or ours is None:
            continue
        where = f"{label} turn {seen.turn}"
        if ours.state.sides[them] != seen.state.sides[them] or ours.state.field != seen.state.field:
            report.violations.append(f"{where}: the opponent differs from the spectator's view")
        theirs = [found for found in ours.evidence if found.player is them]
        if theirs != [found for found in seen.evidence if found.player is them]:
            report.violations.append(f"{where}: evidence differs from the spectator's view")
        # Our own side, as the public saw it: the same Pokémon in play, at the same health.
        mine, shown = ours.state.me.active, seen.state.sides[me].active
        if (mine.species.id, mine.status) != (shown.species.id, shown.status) or abs(
            mine.hp_fraction - shown.hp_fraction
        ) > 0.01:
            report.violations.append(f"{where}: our active differs from the spectator's view")


def _is_species(dex: Dex, species: Species, true_name: str) -> bool:
    try:
        return dex.species(true_name).id == species.id
    except UnknownDexEntryError:  # a cosmetic forme (an Unown letter) is its base species
        return true_name.startswith(f"{species.name}-")


def validate_player(gen: Generation | int, directory: Path = FIXTURE_DIR) -> PlayerReport:
    report = PlayerReport()
    for index, battle in enumerate(load_battles(gen, directory)):
        if "player" in battle:
            check_player_battle(battle, report, label=f"gen{int(gen)} #{index}")
    return report


def true_set(team: list[dict], species_id: str, species_name: str) -> dict | None:
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
    rules: Counter = Counter()
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
        rules.update(r.rules)
    print("\n| Evidence rule | Times fired |\n|---|---|")
    for rule, count in sorted(rules.items(), key=lambda item: item[1]):
        print(f"| {rule} | {count} |")
    print("\n| Gen | Player logs | Our Pokémon | Decisions | Forced switches "
          "| Offered moves outside the set | Request disagreements | Violations |")
    print("|-----|-------------|-------------|-----------|-----------------"
          "|-------------------------------|-----------------------|------------|")
    for gen in Generation:
        p = validate_player(gen, directory)
        print(f"| {int(gen)} | {p.battles} | {p.own_pokemon} | {p.decisions} "
              f"| {p.forced_switches} | {dict(p.outside_the_set) or 0} "
              f"| {dict(p.disagreements) or 0} | {len(p.violations)} |")
        for line in p.violations[:20]:
            print(f"  ! {line}")


if __name__ == "__main__":
    main()
