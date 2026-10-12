"""Command line:  python -m poketrix analyze <battle log> [--turn N]

Prints what the engine sees and advises at one decision of a player's own battle log (one
that has `|request|` lines): the state, the opponent's likely sets, its threats, our options
with their scores, and the recommendation. Without `--turn` it takes the last decision.
"""

import argparse
import sys
from pathlib import Path

from poketrix.advisor import TurnAdvisor
from poketrix.schemas import ActionKind, BattlePokemon, TurnReport
from poketrix.showdown import TurnSnapshot, parse_battle

_TOP = 3


def _pct(value: float | None) -> str:
    return "  ? " if value is None else f"{round(100 * value):3d}%"


def _line(pokemon: BattlePokemon) -> str:
    status = f" {pokemon.status.value}" if pokemon.status else ""
    boosts = "".join(f" {stat.value}{stage:+d}" for stat, stage in pokemon.boosts.items())
    return f"{pokemon.species.name} L{pokemon.level} {round(100 * pokemon.hp_fraction)}%{status}{boosts}"


def _revealed(pokemon: BattlePokemon) -> str:
    return ", ".join(pokemon.revealed_moves) or "none"


def render(snapshot: TurnSnapshot, report: TurnReport) -> str:
    state = snapshot.state
    me, them = state.me, state.opponent
    out = [
        f"Gen {int(state.generation)}, turn {snapshot.turn}, decision {snapshot.decision_index}",
        f"  ours:   {_line(me.active)}",
        f"  theirs: {_line(them.active)}   revealed moves: {_revealed(them.active)}",
    ]
    sets = report.uncloak.payload
    posterior = sets.posteriors.get(them.active_index) if sets else None
    if posterior is not None:
        out.append(f"\nTheir likely sets ({len(posterior.hypotheses)} possible):")
        likely = sorted(posterior.hypotheses, key=lambda h: -h.posterior)[:_TOP]
        out += [f"  {_pct(h.posterior)}  {', '.join(h.moves)}"
                f"{' @ ' + h.item if h.item else ''}" for h in likely]
    threats = report.threats.payload
    threat = threats.by_target.get(me.active_index) if threats else None
    if threat is not None:
        out.append(f"\nIf they attack {me.active.species.name}: knock-out "
                   f"{_pct(threat.p_ko_best_move).strip()}, expected "
                   f"{_pct(threat.expected_best_share).strip()} of its remaining HP")
        out += [
            f"  {_pct(t.probability)} to have {t.move_id}: "
            + (f"unknown ({t.unsupported_reason})" if t.unsupported_reason
               else "no damage" if t.expected_pct is None
               else f"about {t.expected_pct:.0f}% of max HP, knock-out {_pct(t.ko_probability).strip()}")
            for t in threat.threats[:_TOP + 2]
        ]
    decision = report.policy.payload
    if decision is not None:
        out.append("\nOur options (best first):")
        for option in decision.options:
            if option.action is ActionKind.MOVE:
                key = f"our.{me.active_index}.{option.move_id}"
                detail = (f"removes {_pct(report.numbers.get(key + '.share')).strip()}, "
                          f"knock-out {_pct(report.numbers.get(key + '.ko')).strip()}")
                name = option.move_id
            else:
                name = f"switch to {me.team[option.switch_index].species.name}"
                key = f"their.{option.switch_index}"
                detail = (f"takes {_pct(report.numbers.get(key + '.share')).strip()}, "
                          f"knocked out {_pct(report.numbers.get(key + '.p_ko')).strip()}")
            score = "  not scored" if option.score is None else f"{option.score:+.3f}"
            out.append(f"  {score}  {name:<28}{detail}")
    advice = report.recommendation
    out += [
        f"\nRecommendation ({report.status.value}, {report.latency_ms:.0f} ms):",
        f"  {advice.headline}",
        f"  {advice.explanation}",
    ]
    return "\n".join(out)


def analyze(log: str, turn: int | None = None) -> str:
    record = parse_battle(log)
    decisions = [s for s in record.snapshots if s.state.me.request is not None]
    if not decisions:
        return ("No decision found: the log has no |request| lines, so it is a spectator's "
                "log and holds no team of our own to advise.")
    chosen = decisions[-1:] if turn is None else [s for s in decisions if s.turn == turn]
    if not chosen:
        return f"No decision at turn {turn}; the log has turns 1 to {decisions[-1].turn}."
    advisor = TurnAdvisor()
    return "\n\n".join(render(snapshot, advisor.advise(snapshot)) for snapshot in chosen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poketrix")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("analyze", help="advice for one turn of a battle log")
    command.add_argument("log", type=Path, help="a player's own battle log (text)")
    command.add_argument("--turn", type=int, help="the turn to analyse (default: the last)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    print(analyze(args.log.read_text(encoding="utf-8"), args.turn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
