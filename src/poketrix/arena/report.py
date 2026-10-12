"""Win rates and health figures from the games `python -m poketrix.arena run` recorded."""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from poketrix.advisor.latency import percentile
from poketrix.showdown.corpus import wilson_interval

POOLED = 0  # the "generation" under which all four are counted together


@dataclass
class Tally:
    """Player 1's results over a set of games."""

    games: int = 0
    wins: int = 0
    ties: int = 0
    turns: int = 0
    pairs: Counter = field(default_factory=Counter)  # "2-0", "split", "0-2"
    decisions: int = 0
    statuses: Counter = field(default_factory=Counter)
    latency_ms: list[float] = field(default_factory=list)
    illegal: int = 0  # both sides: a rejected choice is a bug whoever made it
    trap_reasks: int = 0
    voluntary_switches: int = 0
    thrown_away: list[str] = field(default_factory=list)
    self_ko: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.wins, self.games)

    def share(self, status: str) -> float:
        return self.statuses[status] / self.decisions if self.decisions else 0.0

    def add(self, game: dict) -> None:
        self.games += 1
        self.wins += game["winner"] == "p1"
        self.ties += game["winner"] is None
        self.turns += game["turns"]
        for side in ("p1", "p2"):
            self.illegal += game.get(side, {}).get("illegal", 0)
        mine = game["p1"]
        self.decisions += mine["decisions"]
        self.statuses.update(mine["statuses"])
        self.latency_ms += mine["latency_ms"]
        self.trap_reasks += mine["trap_reasks"]
        self.voluntary_switches += mine["voluntary_switches"]
        self.thrown_away += [case for case in mine["thrown_away"] if "self-KO" not in case]
        self.self_ko += len(mine["self_ko"])


def load(paths: list[Path]) -> dict[tuple[str, str], dict[int, Tally]]:
    """Tallies by (match, settings) and generation; generation 0 pools all four."""
    games: dict[tuple, dict] = {}
    for path in paths:
        for text in path.read_text(encoding="utf-8").splitlines():
            game = json.loads(text)
            settings = json.dumps(game["settings"], sort_keys=True)
            games[(game["match"], settings, game["gen"], game["index"], game["swap"])] = game
    found: dict[tuple[str, str], dict[int, Tally]] = {}
    won: dict[tuple, int] = Counter()
    played: dict[tuple, int] = Counter()
    for (match, settings, gen, index, _), game in sorted(games.items()):
        by_gen = found.setdefault((match, settings), {})
        for key in (gen, POOLED):
            by_gen.setdefault(key, Tally()).add(game)
        won[(match, settings, gen, index)] += game["winner"] == "p1"
        played[(match, settings, gen, index)] += 1
    for (match, settings, gen, index), count in played.items():
        if count == 2:
            outcome = ("0-2", "split", "2-0")[won[(match, settings, gen, index)]]
            for key in (gen, POOLED):
                found[(match, settings)][key].pairs[outcome] += 1
    return found


def verdict(policy_max: dict[int, Tally], policy_random: dict[int, Tally],
            max_random: dict[int, Tally]) -> list[tuple[str, bool, str]]:
    """The E3 pass marks: (mark, passed, the numbers it was judged on)."""
    pooled = policy_max[POOLED]
    gens = sorted(gen for gen in policy_max if gen != POOLED)
    lowest = min(gens, key=lambda gen: policy_max[gen].win_rate)
    marks = [
        ("1a. Against max-damage, pooled: the interval's lower bound is above 50%",
         pooled.interval[0] > 0.5,
         f"{pooled.wins}/{pooled.games} = {pooled.win_rate:.1%}, lower bound {pooled.interval[0]:.1%}"),
        ("1b. Against max-damage: no generation below 45%",
         policy_max[lowest].win_rate >= 0.45,
         f"lowest is Gen {lowest} at {policy_max[lowest].win_rate:.1%}"),
    ]
    for gen in gens:
        ours, theirs = policy_random[gen], max_random[gen]
        marks.append((
            f"2. Against random, Gen {gen}: our lower bound is at or above max-damage's rate",
            ours.interval[0] >= theirs.win_rate,
            (f"ours {ours.win_rate:.1%} (lower bound {ours.interval[0]:.1%}), "
            f"max-damage {theirs.win_rate:.1%}"),
        ))
    health = [policy_max[POOLED], policy_random[POOLED]]
    decisions = sum(t.decisions for t in health)
    illegal = sum(t.illegal for t in health) + max_random[POOLED].illegal
    errors = sum(t.statuses["error"] for t in health)
    timeouts = sum(t.statuses["timeout"] for t in health)
    p95 = percentile([ms for t in health for ms in t.latency_ms], 0.95)
    marks += [
        ("3a. No illegal choice", illegal == 0, f"{illegal} rejected"),
        ("3b. No decision ended in `error`", errors == 0, f"{errors} of {decisions}"),
        ("3c. `timeout` in under 1% of decisions", timeouts < 0.01 * decisions,
         f"{timeouts} of {decisions}"),
        ("3d. p95 latency under 250 ms", p95 < 250, f"{p95:.0f} ms"),
    ]
    return marks


def print_report(paths: list[Path]) -> None:
    found = load(paths)
    for (match, settings), by_gen in found.items():
        print(f"\n{match}  {settings}\n")
        print("| Gen | Games | Wins | Win rate | 95% interval | Pairs 2-0 / split / 0-2 | Ties "
              "| Avg turns | Fallback | Timeout | Error | Illegal | Trap re-asks "
              "| Voluntary switches | Thrown-away KOs | Self-KO advised | p50 ms | p95 ms |")
        print("|" + "---|" * 18)
        for gen in [*sorted(g for g in by_gen if g != POOLED), POOLED]:
            t = by_gen[gen]
            low, high = t.interval
            switches = t.voluntary_switches / t.decisions if t.decisions else 0.0
            print(
                f"| {gen or 'all'} | {t.games} | {t.wins} | {t.win_rate:.1%} "
                f"| {low:.1%} to {high:.1%} "
                f"| {t.pairs['2-0']} / {t.pairs['split']} / {t.pairs['0-2']} | {t.ties} "
                f"| {t.turns / max(1, t.games):.1f} | {t.share('fallback'):.2%} "
                f"| {t.share('timeout'):.2%} | {t.share('error'):.2%} | {t.illegal} "
                f"| {t.trap_reasks} | {switches:.1%} | {len(t.thrown_away)} | {t.self_ko} "
                f"| {percentile(t.latency_ms, 0.5):.1f} | {percentile(t.latency_ms, 0.95):.1f} |"
            )
        for case in by_gen[POOLED].thrown_away[:10]:
            print(f"  thrown away: {case}")
    by_match = {}
    for (match, _), by_gen in found.items():
        by_match.setdefault(match, []).append(by_gen)
    if all(len(by_match.get(m, [])) == 1 for m in
           ("policy-maxdamage", "policy-random", "maxdamage-random")):
        print("\nE3 verdict\n")
        marks = verdict(by_match["policy-maxdamage"][0], by_match["policy-random"][0],
                        by_match["maxdamage-random"][0])
        for mark, passed, numbers in marks:
            print(f"- {'PASS' if passed else 'FAIL'}  {mark}: {numbers}")
        print(f"\n{'E3 PASSES' if all(p for _, p, _ in marks) else 'E3 FAILS'}")
