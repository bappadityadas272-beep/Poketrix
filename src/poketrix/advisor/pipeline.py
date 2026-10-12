"""The turn engine: one decision point in, one validated and explained recommendation out.

A plain state machine. The stages run in a fixed order, each inside its own time budget and
the turn's overall one, and each answers with a `SubsystemResult`. A stage that fails, runs
out of time or has nothing to work on never stops the turn: the later stages use what there
is, and the last resort needs only the legal actions in the request.
"""

from collections.abc import Callable
from time import perf_counter

from pydantic import BaseModel, ValidationError

from poketrix.dex import Dex
from poketrix.schemas import (
    ActionPrediction,
    Decision,
    OffenceSheet,
    OpponentSets,
    OrderSheet,
    Recommendation,
    SubsystemResult,
    SubsystemStatus,
    ThreatSheet,
    TurnReport,
)
from poketrix.showdown import TurnSnapshot
from poketrix.uncloak import SetPrior, load_prior

from . import stages
from .policy import Inputs, by_power, decide, trap_risk
from .situation import Deadline, Situation
from .writer import NO_NUMBERS, Brief, TemplateWriter, Writer

TURN_BUDGET_MS = 500.0
STAGE_BUDGET_MS = {
    "uncloak": 20.0, "threats": 150.0, "offence": 100.0, "order": 10.0, "opponent": 5.0,
    "policy": 10.0,
}
_SEVERITY = {
    SubsystemStatus.OK: 0, SubsystemStatus.FALLBACK: 1, SubsystemStatus.TIMEOUT: 2,
    SubsystemStatus.ERROR: 3,
}
TRANSFORMED = "No damage numbers: a transformed Pokémon cannot be calculated."
NO_SETS = "The opponent's possible sets could not be estimated."
NO_TARGET = "Their Pokémon has fainted and its replacement is not known yet."

# What the turn assumes about the opponent when nothing could be predicted: it attacks.
THEY_ATTACK = ActionPrediction(p_attack=1.0, p_switch=0.0, p_utility=0.0, model_version="assumed")

Work = Callable[[Deadline], tuple[BaseModel, SubsystemStatus, str | None]]


class TurnAdvisor:
    def __init__(
        self, writer: Writer | None = None,
        priors: Callable[[int], SetPrior] = load_prior,
        clock: Callable[[], float] = perf_counter,
        budget_ms: float = TURN_BUDGET_MS,
    ) -> None:
        self._writer = writer or TemplateWriter()
        self._priors = priors
        self._clock = clock
        self._budget_ms = budget_ms

    def advise(self, snapshot: TurnSnapshot) -> TurnReport:
        """Advice for a snapshot that carries a request (a player's own log)."""
        state = snapshot.state
        if state.me.request is None:
            raise ValueError("this snapshot asks for no decision: it has no request")
        started = self._clock()
        turn = Deadline(self._budget_ms, self._clock)
        situation = Situation(snapshot, self._priors(state.generation), Dex(state.generation))
        numbers: dict[str, float] = {}

        def run(name: str, model: type[BaseModel], work: Work):
            return self._stage(model, work, turn.within(STAGE_BUDGET_MS[name]))

        def empty(model: type[BaseModel]) -> Work:
            """A stage with nothing to work on: a known case, so a fallback and not an error."""
            return lambda d: (model(), SubsystemStatus.FALLBACK, blocked)

        uncloak = run("uncloak", OpponentSets,
                      lambda d: stages.read_opponent(situation, d, numbers))
        posterior = None
        if uncloak.payload is not None:
            posterior = uncloak.payload.posteriors.get(situation.them.active_index)
        blocked = (
            NO_TARGET if situation.theirs.fainted
            else TRANSFORMED if situation.transformed
            else NO_SETS if posterior is None else ""
        )

        def needs_sets(stage: Callable, model: type[BaseModel]) -> Work:
            if blocked:
                return empty(model)
            return lambda d: stage(situation, posterior, d, numbers)

        threats = run("threats", ThreatSheet, needs_sets(stages.read_threats, ThreatSheet))
        offence = run("offence", OffenceSheet, needs_sets(stages.read_offence, OffenceSheet))
        order = run("order", OrderSheet, needs_sets(stages.read_order, OrderSheet))
        inputs = Inputs(
            threats=threats.payload.by_target if threats.payload else {},
            offence=offence.payload.by_attacker if offence.payload else {},
            first=order.payload.first if order.payload else {},
        )
        opponent = run(
            "opponent", ActionPrediction,
            (lambda d: (THEY_ATTACK, SubsystemStatus.FALLBACK, blocked)) if blocked
            else lambda d: stages.predict_opponent(
                situation, posterior, inputs.offence.get(situation.me.active_index, []), numbers
            ),
        )
        inputs.opponent = opponent.payload or THEY_ATTACK
        risk = numbers["trap.risk"] = trap_risk(situation, posterior)
        policy = run("policy", Decision, lambda d: self._decide(situation, inputs, numbers))
        decision = policy.payload or by_power(situation)

        active_threat = inputs.threats.get(situation.me.active_index)
        brief = Brief(
            situation, decision, numbers, caveat=blocked or None,
            ko_is_lower_bound=bool(active_threat and active_threat.ko_lower_bound),
        )
        results = (uncloak, threats, offence, order, opponent, policy)
        return TurnReport(
            generation=state.generation, turn=snapshot.turn,
            decision_index=snapshot.decision_index,
            status=max((r.status for r in results), key=_SEVERITY.__getitem__),
            latency_ms=(self._clock() - started) * 1000,
            uncloak=uncloak, threats=threats, offence=offence, order=order, opponent=opponent,
            policy=policy, recommendation=self._write(brief), numbers=numbers, trap_risk=risk,
        )

    # ------------------------------------------------------------------ stages

    def _stage(self, model: type[BaseModel], work: Work, deadline: Deadline) -> SubsystemResult:
        """Run one stage. Rule 3: it reports its failure, it never takes the turn down."""
        started = self._clock()

        def result(status: SubsystemStatus, **fields) -> SubsystemResult:
            elapsed = max(0.0, (self._clock() - started) * 1000)
            return SubsystemResult[model](status=status, latency_ms=elapsed, **fields)

        if deadline.expired():
            return result(SubsystemStatus.TIMEOUT, error="out of time before it started")
        try:
            payload, status, problem = work(deadline)
        except Exception as error:  # noqa: BLE001
            return result(SubsystemStatus.ERROR, error=f"{type(error).__name__}: {error}")
        return result(status, payload=payload, error=problem)

    @staticmethod
    def _decide(situation: Situation, inputs: Inputs, numbers: dict[str, float]):
        decision = decide(situation, inputs, numbers)
        if decision.reason != "limited":
            return decision, SubsystemStatus.OK, None
        # Nothing could be scored: fall back to the request alone.
        return by_power(situation), SubsystemStatus.FALLBACK, "no option could be scored"

    def _write(self, brief: Brief) -> Recommendation:
        """The writer's text, if the guardrail accepts it; otherwise the bare choice."""
        context = {"state": brief.situation.state, "allowed_numbers": dict(brief.numbers)}
        try:
            written = self._writer.write(brief)
            return Recommendation.model_validate(written.model_dump(), context=context)
        except (ValidationError, KeyError, ValueError):
            choice = brief.decision.choice
            bare = Recommendation(
                action=choice.action, move_id=choice.move_id, switch_index=choice.switch_index,
                headline="Recommended action (the explanation failed its checks)",
                explanation=NO_NUMBERS,
            )
            return Recommendation.model_validate(bare.model_dump(), context=context)
