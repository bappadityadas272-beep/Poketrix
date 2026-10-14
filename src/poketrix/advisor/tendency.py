"""The opponent tendency line (ruling 15-R): what a model of ladder players expects the opponent
to do, shown beside the advice and never used by it. The policy keeps heuristic-0.

It needs nothing the turn did not already compute: the view is rebuilt from the report's
stage results, exactly as stage 5 builds it.
"""

from collections.abc import Callable

from poketrix.dex import Dex
from poketrix.opponent import ACTIONS, ModelUnavailable, OpponentModel
from poketrix.schemas import ActionPrediction, TurnReport
from poketrix.showdown import TurnSnapshot
from poketrix.uncloak import SetPrior, load_prior

from . import stages
from .situation import Situation

UNAVAILABLE = "Opponent tendency: not available"


def tendency(snapshot: TurnSnapshot, report: TurnReport, model: OpponentModel,
             priors: Callable[[int], SetPrior] = load_prior) -> ActionPrediction | None:
    """The model's odds for the opponent's next action; None where the turn engine had nothing
    to predict from (no posterior, a transformed or fainted Pokémon), as stage 5 has."""
    if report.opponent.payload is None or report.opponent.payload.model_version == "assumed":
        return None
    state = snapshot.state
    situation = Situation(snapshot, priors(state.generation), Dex(state.generation))
    ours, theirs = situation.me.active_index, situation.them.active_index
    sheets = (report.uncloak.payload, report.threats.payload, report.offence.payload,
              report.order.payload)
    posterior = sheets[0].posteriors.get(theirs) if sheets[0] else None
    if posterior is None:
        return None
    view = stages.opponent_view(
        situation, posterior,
        sheets[1].by_target.get(ours) if sheets[1] else None,
        sheets[2].by_attacker.get(ours, []) if sheets[2] else [],
        sheets[3].first.get(ours, {}) if sheets[3] else {},
    )
    return model.predict(view)


def describe(prediction: ActionPrediction | None, switch_cap: float | None = None) -> str:
    """`Opponent tendency: switch 45% · attack 50% · utility 5%`. Switch odds above
    `switch_cap` read as "70%+": the calibration does not hold them more precisely."""
    if prediction is None:
        return UNAVAILABLE

    def shown(action: str) -> str:
        value = getattr(prediction, f"p_{action}")
        if action == "switch" and switch_cap is not None and value > switch_cap:
            return f"{round(100 * switch_cap)}%+"
        return f"{round(100 * value)}%"

    order = ("switch", *(action for action in ACTIONS if action != "switch"))
    return "Opponent tendency: " + " · ".join(f"{a} {shown(a)}" for a in order)


def tendency_line(snapshot: TurnSnapshot, report: TurnReport, model: OpponentModel) -> str:
    """The line as shown: the odds, or why there are none."""
    try:
        prediction = tendency(snapshot, report, model)
    except ModelUnavailable as error:
        return f"{UNAVAILABLE} ({error})"
    return describe(prediction, getattr(model, "switch_cap", None))
