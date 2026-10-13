"""Win rates and health figures from the games `python -m poketrix.arena run` recorded.

Only whole pairs are scored. A quarantined pair (one in which a game raised) is counted,
never scored.
"""

import json
import random
from collections import Counter
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path

from poketrix.advisor.latency import percentile
from poketrix.showdown.corpus import wilson_interval

POOLED = 0  # the "generation" under which all four are counted together
# E3.2 (ruling 13-A6): against random we may trail max-damage by at most this much, pooled
# over the generations, and by at most the wider margin in any single generation.
NON_INFERIORITY_MARGIN = 0.02
GENERATION_MARGIN = 0.05
QUARANTINE_LIMIT = 0.005  # E3.3: share of a generation's pairs that may be quarantined
BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED = 10_000, 20261402


def difference_interval(wins_a: int, games_a: int, wins_b: int, games_b: int) -> tuple[float, float]:
    """95% interval of (rate A − rate B) for two independent proportions (Newcombe's method,
    built from each rate's Wilson interval)."""
    rate_a, rate_b = wins_a / games_a, wins_b / games_b
    low_a, high_a = wilson_interval(wins_a, games_a)
    low_b, high_b = wilson_interval(wins_b, games_b)
    difference = rate_a - rate_b
    return (
        difference - sqrt((rate_a - low_a) ** 2 + (high_b - rate_b) ** 2),
        difference + sqrt((high_a - rate_a) ** 2 + (rate_b - low_b) ** 2),
    )


@dataclass
class Tally:
    """Player 1's results over a set of whole pairs."""

    games: int = 0
    wins: int = 0
    ties: int = 0
    turns: int = 0
    pair_scores: list[float] = field(default_factory=list)  # 0, 0.5 or 1 per pair
    quarantined: int = 0  # pairs
    decisions: int = 0
    statuses: Counter = field(default_factory=Counter)
    latency_ms: list[float] = field(default_factory=list)
    illegal: int = 0  # both sides: a rejected choice is a bug whoever made it
    trap_reasks: int = 0
    voluntary_switches: int = 0
    thrown_away: list[str] = field(default_factory=list)
    self_ko: int = 0
    won: dict[tuple, bool] = field(default_factory=dict)  # (gen, index, swap) -> player 1 won

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.wins, self.games)

    @property
    def pairs(self) -> Counter:
        names = {0.0: "0-2", 0.5: "split", 1.0: "2-0"}
        return Counter(names[score] for score in self.pair_scores)

    @property
    def quarantine_share(self) -> float:
        return self.quarantined / max(1, self.quarantined + len(self.pair_scores))

    def pair_interval(self) -> tuple[float, float, float]:
        """(mean pair score, low, high): a bootstrap over pairs, which is the unit that is
        actually independent. The same seed always gives the same interval."""
        scores = self.pair_scores
        if not scores:
            return 0.0, 0.0, 1.0
        chooser = random.Random(BOOTSTRAP_SEED)
        means = sorted(
            sum(chooser.choices(scores, k=len(scores))) / len(scores)
            for _ in range(BOOTSTRAP_RESAMPLES)
        )
        return (sum(scores) / len(scores), means[int(0.025 * BOOTSTRAP_RESAMPLES)],
                means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1])

    def share(self, status: str) -> float:
        return self.statuses[status] / self.decisions if self.decisions else 0.0

    def add_pair(self, games: list[dict]) -> None:
        self.pair_scores.append(sum(game["winner"] == "p1" for game in games) / 2)
        for game in games:
            self.games += 1
            self.wins += game["winner"] == "p1"
            self.won[(game["gen"], game["index"], game["swap"])] = game["winner"] == "p1"
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
    pairs: dict[tuple, dict] = {}  # (match, settings, gen, index) -> {swap: game} or None
    for path in paths:
        for text in path.read_text(encoding="utf-8").splitlines():
            game = json.loads(text)
            settings = json.dumps(game["settings"], sort_keys=True)
            key = (game["match"], settings, game["gen"], game["index"])
            if game.get("quarantined"):
                pairs[key] = None
            elif pairs.get(key, {}) is not None:
                pairs.setdefault(key, {})[game["swap"]] = game
    found: dict[tuple[str, str], dict[int, Tally]] = {}
    for (match, settings, gen, _), games in sorted(pairs.items()):
        by_gen = found.setdefault((match, settings), {})
        for key in (gen, POOLED):
            tally = by_gen.setdefault(key, Tally())
            if games is None:
                tally.quarantined += 1
            elif len(games) == 2:
                tally.add_pair([games[False], games[True]])
    return found


def verdict(policy_max: dict[int, Tally], policy_random: dict[int, Tally],
            max_random: dict[int, Tally]) -> list[tuple[str, bool, str]]:
    """The E3 pass marks, as amended by 13-A3 and 13-A6: (mark, passed, the numbers)."""
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
    for gen, margin in [(POOLED, NON_INFERIORITY_MARGIN), *((g, GENERATION_MARGIN) for g in gens)]:
        ours, theirs = policy_random[gen], max_random[gen]
        low, high = difference_interval(ours.wins, ours.games, theirs.wins, theirs.games)
        where = "pooled" if gen == POOLED else f"Gen {gen}"
        marks.append((
            (f"2{'a' if gen == POOLED else 'b'}. Against random, {where}: not more than "
            f"{margin:.0%} behind max-damage"),
            low > -margin,
            (f"ours {ours.win_rate:.1%}, max-damage {theirs.win_rate:.1%}, "
            f"difference {ours.win_rate - theirs.win_rate:+.1%} ({low:+.1%} to {high:+.1%})"),
        ))
    health = [policy_max[POOLED], policy_random[POOLED]]
    decisions = sum(t.decisions for t in health)
    illegal = sum(t.illegal for t in health) + max_random[POOLED].illegal
    errors = sum(t.statuses["error"] for t in health)
    timeouts = sum(t.statuses["timeout"] for t in health)
    p95 = percentile([ms for t in health for ms in t.latency_ms], 0.95)
    worst = max(
        ((match[gen].quarantine_share, gen, match[gen].quarantined)
         for match in (policy_max, policy_random, max_random) for gen in gens),
    )
    marks += [
        ("3a. No illegal choice", illegal == 0, f"{illegal} rejected"),
        ("3b. No decision ended in `error`", errors == 0, f"{errors} of {decisions}"),
        ("3c. `timeout` in under 1% of decisions", timeouts < 0.01 * decisions,
         f"{timeouts} of {decisions}"),
        ("3d. p95 latency under 250 ms", p95 < 250, f"{p95:.0f} ms"),
        (f"3e. At most {QUARANTINE_LIMIT:.1%} of a generation's pairs quarantined",
         worst[0] <= QUARANTINE_LIMIT,
         f"worst is Gen {worst[1]} with {worst[2]} pairs ({worst[0]:.2%})"),
    ]
    return marks


def paired_difference(ours: Tally, theirs: Tally) -> tuple[int, int, int, float, float, float]:
    """The same games played by two players against the same opponent, compared game by game:
    (games in common, only ours won, only theirs won, difference, low, high).

    Supplementary to the verdict: the same teams and seed make the two results correlated, so
    this interval (Wald, for a difference of paired proportions) shows the real precision.
    """
    common = sorted(set(ours.won) & set(theirs.won))
    only_ours = sum(ours.won[key] and not theirs.won[key] for key in common)
    only_theirs = sum(theirs.won[key] and not ours.won[key] for key in common)
    n = max(1, len(common))
    difference = (only_ours - only_theirs) / n
    spread = 1.96 * sqrt(max(0.0, only_ours + only_theirs - (only_ours - only_theirs) ** 2 / n)) / n
    return len(common), only_ours, only_theirs, difference, difference - spread, difference + spread


def print_report(paths: list[Path]) -> None:
    found = load(paths)
    for (match, settings), by_gen in found.items():
        print(f"\n{match}  {settings}\n")
        print("| Gen | Games | Wins | Win rate | 95% interval (games) | Pair score (bootstrap 95%) "
              "| Pairs 2-0 / split / 0-2 | Quarantined pairs | Ties | Avg turns | Fallback "
              "| Timeout | Error | Illegal | Trap re-asks | Voluntary switches "
              "| Thrown-away KOs | Self-KO advised | p50 ms | p95 ms |")
        print("|" + "---|" * 20)
        for gen in [*sorted(g for g in by_gen if g != POOLED), POOLED]:
            t = by_gen[gen]
            low, high = t.interval
            score, score_low, score_high = t.pair_interval()
            switches = t.voluntary_switches / t.decisions if t.decisions else 0.0
            pairs = t.pairs
            print(
                f"| {gen or 'all'} | {t.games} | {t.wins} | {t.win_rate:.1%} "
                f"| {low:.1%} to {high:.1%} "
                f"| {score:.1%} ({score_low:.1%} to {score_high:.1%}) "
                f"| {pairs['2-0']} / {pairs['split']} / {pairs['0-2']} | {t.quarantined} "
                f"| {t.ties} | {t.turns / max(1, t.games):.1f} | {t.share('fallback'):.2%} "
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
        print("\nSupplementary, not part of the verdict: the against-random games compared "
              "game by game (same teams, same seed)\n")
        print("| Gen | Games in common | Only the policy won | Only max-damage won "
              "| Paired difference | 95% interval |")
        print("|---|---|---|---|---|---|")
        ours, theirs = by_match["policy-random"][0], by_match["maxdamage-random"][0]
        for gen in [*sorted(g for g in ours if g != POOLED), POOLED]:
            n, a, b, difference, low, high = paired_difference(ours[gen], theirs[gen])
            print(f"| {gen or 'all'} | {n} | {a} | {b} | {difference:+.1%} "
                  f"| {low:+.1%} to {high:+.1%} |")
