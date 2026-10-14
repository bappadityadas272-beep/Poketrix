"""What the side panel shows for one decision, as plain JSON: the headline, the top three
options with their numbers, the opponent's two likeliest sets, the threat line and the
opponent tendency. Every number comes from the turn's report; nothing is computed here."""

from poketrix.dex import Dex, UnknownDexEntryError
from poketrix.schemas import ActionKind, TurnReport
from poketrix.showdown import TurnSnapshot

TOP_OPTIONS, TOP_SETS = 3, 2


def _pct(value: float | None) -> str:
    return "?" if value is None else f"{round(100 * value)}%"


def _name(dex: Dex, move_id: str) -> str:
    try:
        return dex.move(move_id).name
    except UnknownDexEntryError:
        return move_id


def panel(snapshot: TurnSnapshot, report: TurnReport, tendency: str, mode: str) -> dict:
    state, numbers = snapshot.state, report.numbers
    me, them = state.me, state.opponent
    dex = Dex(state.generation)
    options = []
    decision = report.policy.payload
    for option in (decision.options if decision else [])[:TOP_OPTIONS]:
        if option.action is ActionKind.MOVE:
            key = f"our.{me.active_index}.{option.move_id}"
            label = _name(dex, option.move_id)
            detail = (f"removes {_pct(numbers.get(key + '.share'))}, "
                      f"knock-out {_pct(numbers.get(key + '.ko'))}")
        else:
            key = f"their.{option.switch_index}"
            label = f"Switch to {me.team[option.switch_index].species.name}"
            detail = (f"takes {_pct(numbers.get(key + '.share'))}, "
                      f"knocked out {_pct(numbers.get(key + '.p_ko'))}")
        options.append({"label": label, "score": option.score, "detail": detail})
    sets = []
    found = report.uncloak.payload
    posterior = found.posteriors.get(them.active_index) if found else None
    if posterior is not None:
        for h in sorted(posterior.hypotheses, key=lambda h: -h.posterior)[:TOP_SETS]:
            sets.append({"probability": _pct(h.posterior),
                         "moves": [_name(dex, move) for move in h.moves], "item": h.item})
    threat = None
    threats = report.threats.payload
    sheet = threats.by_target.get(me.active_index) if threats else None
    if sheet is not None:
        threat = (f"If {them.active.species.name} attacks: knock-out "
                  f"{_pct(sheet.p_ko_best_move)}, about {_pct(sheet.expected_best_share)} of "
                  f"{me.active.species.name}'s remaining HP")
    advice = report.recommendation
    return {
        "status": "ok", "mode": mode, "generation": int(state.generation),
        "turn": snapshot.turn, "decision": snapshot.decision_index,
        "ours": me.active.species.name, "theirs": them.active.species.name,
        "headline": advice.headline, "explanation": advice.explanation,
        "options": options, "sets": sets, "threat": threat, "tendency": tendency,
        "engine_ms": round(report.latency_ms, 1),
    }
