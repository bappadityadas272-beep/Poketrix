"""Runs paired simulator games and reports win rates.

    python -m poketrix.arena run policy-maxdamage --first 2000000 --pairs 500 --out eval.jsonl
        [--opponent xgb-1]     the opponent model the policy plays with (default heuristic-0)
    python -m poketrix.arena report eval.jsonl [more.jsonl ...]
    python -m poketrix.arena record          re-record the golden games (see golden.py)

Matches: policy-maxdamage, policy-random, maxdamage-random (player 1 is named first).
Every game is one JSON line in the output file, so a run can be stopped and started again:
games already in the file are skipped. Results belong outside the repository; a relative
`--out` goes under the cache directory (POKETRIX_CACHE_DIR, else %LOCALAPPDATA%/poketrix-cache).

A pair in which anything raises is quarantined, not fatal: its seed, both sides' logs and the
traceback go to data/raw/quarantine/ (git-ignored), the whole pair is left out of the scoring,
and the run goes on. The report counts quarantined pairs; more than 0.5% of a generation's
pairs makes the run invalid.

Which pokemon-showdown plays is chosen by scripts/randbats/simulator.mjs (POKETRIX_SHOWDOWN_DIR).
"""

import argparse
import json
import os
import sys
import traceback
from dataclasses import asdict
from pathlib import Path

from poketrix.advisor import PolicySettings
from poketrix.opponent import MODELS, Heuristic

from .golden import GOLDEN_FILE, record
from .play import Bridge, GameResult, MaxDamagePlayer, Player, PolicyPlayer
from .report import print_report

MATCHES = ("policy-maxdamage", "policy-random", "maxdamage-random")
QUARANTINE_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "quarantine"
GENS = (1, 2, 3, 4)


def cache_dir() -> Path:
    if "POKETRIX_CACHE_DIR" in os.environ:
        return Path(os.environ["POKETRIX_CACHE_DIR"])
    if "LOCALAPPDATA" in os.environ:
        return Path(os.environ["LOCALAPPDATA"]) / "poketrix-cache"
    return Path.home() / ".cache" / "poketrix"


def _players(match: str, settings: PolicySettings, opponent: str) -> dict[str, Player | None]:
    makers = {"policy": lambda: PolicyPlayer(settings, MODELS[opponent]()),
              "maxdamage": MaxDamagePlayer, "random": lambda: None}
    first, second = match.split("-")
    return {"p1": makers[first](), "p2": makers[second]()}


def _line(match: str, settings: dict, result: GameResult) -> dict:
    line = {"match": match, "settings": settings, "gen": result.gen,
            "index": result.index, "swap": result.swap, "winner": result.winner,
            "turns": result.turns}
    for side, tally in result.sides.items():
        guardrails = tally.guardrails
        line[side] = {
            "decisions": tally.decisions, "statuses": dict(tally.statuses),
            "latency_ms": tally.latency_ms, "illegal": tally.illegal,
            "trap_reasks": tally.trap_reasks,
            "voluntary_switches": guardrails.voluntary_switches,
            "thrown_away": guardrails.thrown_away, "self_ko": guardrails.self_ko,
        }
    return line


def run(match: str, gens: list[int], first: int, pairs: int, out: Path,
        settings: PolicySettings, opponent: str = Heuristic.version) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: dict[tuple[int, int], int] = {}  # (gen, index) -> lines already written for the pair
    if out.exists():
        for text in out.read_text(encoding="utf-8").splitlines():
            game = json.loads(text)
            key = (game["gen"], game["index"])
            seen[key] = 2 if game.get("quarantined") else seen.get(key, 0) + 1
    players = _players(match, settings, opponent)
    # What the policy played with: the report keeps runs with different settings apart.
    described = asdict(settings) | {"opponent": opponent}
    bridge = Bridge()
    print(f"{match} with {described}; simulator {bridge.simulator}; results in {out}", flush=True)
    with out.open("a", encoding="utf-8", newline="\n") as file:
        for gen in gens:
            for index in range(first, first + pairs):
                if seen.get((gen, index), 0) >= 2:
                    continue
                pair = {"match": match, "settings": described, "gen": gen, "index": index}
                swap = False
                try:  # both games or neither: half a pair would bias the result
                    lines = []
                    for swap in (False, True):
                        result = bridge.play(gen, index, swap, players)
                        lines.append(_line(match, described, result))
                except Exception:  # noqa: BLE001 - 13-A3: record it, drop the pair, carry on
                    _quarantine(pair | {"swap": swap}, bridge.log)
                    lines = [pair | {"quarantined": True}]
                    bridge.abandon()
                    bridge = Bridge()
                file.write("".join(json.dumps(line) + "\n" for line in lines))
                file.flush()
                if (index - first + 1) % 50 == 0:
                    print(f"  gen{gen}: {index - first + 1}/{pairs} pairs", flush=True)
    bridge.close()


def _quarantine(game: dict, logs: dict[str, list[str]]) -> None:
    """Keep everything needed to replay a game that raised: it becomes a regression test."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{game['match']}_gen{game['gen']}_{game['index']}_{int(game['swap'])}.json"
    record = game | {
        "traceback": traceback.format_exc(),
        "logs": {side: "\n".join(chunks) for side, chunks in logs.items()},
    }
    (QUARANTINE_DIR / name).write_text(json.dumps(record, indent=1), encoding="utf-8",
                                       newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poketrix.arena")
    commands = parser.add_subparsers(dest="command", required=True)
    play = commands.add_parser("run", help="play paired games")
    play.add_argument("match", choices=MATCHES)
    play.add_argument("--gens", type=int, nargs="+", default=list(GENS))
    play.add_argument("--first", type=int, required=True, help="the first game index (seed)")
    play.add_argument("--pairs", type=int, required=True)
    play.add_argument("--out", type=Path, required=True)
    defaults = PolicySettings()
    play.add_argument("--gamma", type=float, default=defaults.gamma)
    play.add_argument("--a-floor", type=float, default=defaults.a_floor)
    play.add_argument("--utility-scale", type=float, default=defaults.utility_scale)
    play.add_argument("--opponent", choices=sorted(MODELS), default=Heuristic.version)
    show = commands.add_parser("report", help="win rates from result files")
    show.add_argument("files", type=Path, nargs="+")
    commands.add_parser("record", help="re-record the golden games with the default policy")
    args = parser.parse_args(argv)

    def placed(path: Path) -> Path:
        return path if path.is_absolute() else cache_dir() / "arena" / path

    if args.command == "record":
        print(f"{record()} decisions recorded in {GOLDEN_FILE}")
    elif args.command == "run":
        settings = PolicySettings(gamma=args.gamma, a_floor=args.a_floor,
                                  utility_scale=args.utility_scale)
        run(args.match, args.gens, args.first, args.pairs, placed(args.out), settings,
            args.opponent)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print_report([placed(path) for path in args.files])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
