"""Runs paired simulator games and reports win rates.

    python -m poketrix.arena run policy-maxdamage --first 2000000 --pairs 500 --out eval.jsonl
    python -m poketrix.arena report eval.jsonl [more.jsonl ...]

Matches: policy-maxdamage, policy-random, maxdamage-random (player 1 is named first).
Every game is one JSON line in the output file, so a run can be stopped and started again:
games already in the file are skipped. Results belong outside the repository; a relative
`--out` goes under the cache directory (POKETRIX_CACHE_DIR, else %LOCALAPPDATA%/poketrix-cache).

Which pokemon-showdown plays is chosen by scripts/randbats/simulator.mjs (POKETRIX_SHOWDOWN_DIR).
"""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from poketrix.advisor import PolicySettings

from .play import Bridge, GameResult, MaxDamagePlayer, Player, PolicyPlayer
from .report import print_report

MATCHES = ("policy-maxdamage", "policy-random", "maxdamage-random")
GENS = (1, 2, 3, 4)


def cache_dir() -> Path:
    if "POKETRIX_CACHE_DIR" in os.environ:
        return Path(os.environ["POKETRIX_CACHE_DIR"])
    if "LOCALAPPDATA" in os.environ:
        return Path(os.environ["LOCALAPPDATA"]) / "poketrix-cache"
    return Path.home() / ".cache" / "poketrix"


def _players(match: str, settings: PolicySettings) -> dict[str, Player | None]:
    makers = {"policy": lambda: PolicyPlayer(settings), "maxdamage": MaxDamagePlayer,
              "random": lambda: None}
    first, second = match.split("-")
    return {"p1": makers[first](), "p2": makers[second]()}


def _line(match: str, settings: PolicySettings, result: GameResult) -> dict:
    line = {"match": match, "settings": asdict(settings), "gen": result.gen,
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
        settings: PolicySettings) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for text in out.read_text(encoding="utf-8").splitlines():
            game = json.loads(text)
            done.add((game["gen"], game["index"], game["swap"]))
    players = _players(match, settings)
    bridge = Bridge()
    print(f"{match} with {settings}; simulator {bridge.simulator}; results in {out}", flush=True)
    with out.open("a", encoding="utf-8", newline="\n") as file:
        for gen in gens:
            for index in range(first, first + pairs):
                for swap in (False, True):
                    if (gen, index, swap) in done:
                        continue
                    result = bridge.play(gen, index, swap, players)
                    file.write(json.dumps(_line(match, settings, result)) + "\n")
                file.flush()
                if (index - first + 1) % 50 == 0:
                    print(f"  gen{gen}: {index - first + 1}/{pairs} pairs", flush=True)
    bridge.close()


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
    show = commands.add_parser("report", help="win rates from result files")
    show.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args(argv)

    def placed(path: Path) -> Path:
        return path if path.is_absolute() else cache_dir() / "arena" / path

    if args.command == "run":
        settings = PolicySettings(gamma=args.gamma, a_floor=args.a_floor,
                                  utility_scale=args.utility_scale)
        run(args.match, args.gens, args.first, args.pairs, placed(args.out), settings)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print_report([placed(path) for path in args.files])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
