"""Output contracts for each subsystem, plus the synthesis-layer guardrail.

Every subsystem returns `SubsystemResult[T]`, so the orchestrator can always tell
"real answer" from "deterministic fallback" from "timed out" — rule 4 (graceful fallbacks).
"""

import math
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationInfo, model_validator
from typing_extensions import Self

from .battle import GameState
from .enums import ActionKind, Generation, SubsystemStatus
from .generation import rules_for
from .pokemon import ShowdownId, Strict

PROB_TOL = 1e-6

Probability = float  # documented alias; bounds enforced with Field(ge=0, le=1)


# --------------------------------------------------------------------------- Math layer


class DamageRange(Strict):
    """Every possible damage roll of one hit of a move, attacker -> defender, no crit."""

    generation: Generation
    move_id: ShowdownId
    attacker_species: ShowdownId
    defender_species: ShowdownId
    rolls: list[int] = Field(min_length=1)  # sorted ascending, absolute HP
    crit_rolls: list[int] | None = None
    defender_max_hp: int = Field(ge=1)
    type_multiplier: float = Field(ge=0.0, le=4.0)
    # Multi-hit moves only: number of hits per use -> probability. `rolls` are for one hit.
    hit_distribution: dict[int, float] | None = None
    # Gen 1 multi-hit moves: every hit of one use repeats the first hit's roll and crit.
    hits_share_roll: bool = False

    @model_validator(mode="after")
    def _shape(self) -> Self:
        n = rules_for(self.generation).damage_roll_count
        for name, rolls in (("rolls", self.rolls), ("crit_rolls", self.crit_rolls)):
            if rolls is None:
                continue
            # Immune / fixed-damage moves legitimately collapse to a single value.
            if len(rolls) not in (1, n):
                raise ValueError(f"Gen {int(self.generation)} {name} must have 1 or {n} entries")
            if rolls != sorted(rolls) or rolls[0] < 0:
                raise ValueError(f"{name} must be non-negative and ascending")
        if self.type_multiplier == 0 and any(self.rolls):
            raise ValueError("immune matchup cannot deal damage")
        if self.hit_distribution is not None:
            if not self.hit_distribution or not all(1 <= h <= 5 for h in self.hit_distribution):
                raise ValueError("hit_distribution needs hit counts between 1 and 5")
            total = math.fsum(self.hit_distribution.values())
            if abs(total - 1.0) > PROB_TOL or min(self.hit_distribution.values()) < 0:
                raise ValueError(f"hit_distribution probabilities sum to {total:.6f}, not 1")
        elif self.hits_share_roll:
            raise ValueError("hits_share_roll only applies to a multi-hit move")
        return self

    @property
    def min_pct(self) -> float:
        """Weakest full use of the move, as a percentage of the defender's max HP."""
        hits = min(self.hit_distribution) if self.hit_distribution else 1
        return 100 * hits * self.rolls[0] / self.defender_max_hp

    @property
    def max_pct(self) -> float:
        hits = max(self.hit_distribution) if self.hit_distribution else 1
        return 100 * hits * self.rolls[-1] / self.defender_max_hp


class KOChance(Strict):
    hits: int = Field(ge=1, le=10)  # n-hit KO
    probability: float = Field(ge=0.0, le=1.0)
    method: Literal["exact", "monte_carlo"]
    samples: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _samples(self) -> Self:
        if (self.method == "monte_carlo") != (self.samples is not None):
            raise ValueError("samples required for monte_carlo, forbidden for exact")
        return self


class MoveEvaluation(Strict):
    move_id: ShowdownId
    damage: DamageRange | None = None  # None for status moves and unsupported moves
    # Why the Math layer produced no damage for a damaging move. Never a guessed number instead.
    unsupported_reason: str | None = None
    ko: list[KOChance] = Field(default_factory=list)
    accuracy: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _unsupported_has_no_numbers(self) -> Self:
        if self.unsupported_reason is not None and (self.damage is not None or self.ko):
            raise ValueError("an unsupported move carries no damage or KO numbers")
        return self


class MathReport(Strict):
    our_moves: list[MoveEvaluation] = Field(default_factory=list)
    threats: list[MoveEvaluation] = Field(default_factory=list)  # opponent's likely moves vs us


# --------------------------------------------------------------------------- ML layer


class SetHypothesis(Strict):
    set_id: str
    moves: list[ShowdownId] = Field(min_length=1, max_length=4)
    item: ShowdownId | None = None
    ability: ShowdownId | None = None
    prior: float = Field(ge=0.0, le=1.0)
    posterior: float = Field(ge=0.0, le=1.0)


class SetPosterior(Strict):
    """Bayesian set uncloaker output for one opponent Pokémon."""

    species_id: ShowdownId
    evidence_moves: list[ShowdownId] = Field(default_factory=list)
    evidence_item: ShowdownId | None = None
    evidence_ability: ShowdownId | None = None
    hypotheses: list[SetHypothesis] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        for field in ("prior", "posterior"):
            total = math.fsum(getattr(h, field) for h in self.hypotheses)
            if abs(total - 1.0) > PROB_TOL:
                raise ValueError(f"{field}s sum to {total:.6f}, not 1")
        for h in self.hypotheses:
            consistent = (
                set(self.evidence_moves) <= set(h.moves)
                and (self.evidence_item is None or h.item == self.evidence_item)
                and (self.evidence_ability is None or h.ability == self.evidence_ability)
            )
            if not consistent and h.posterior > PROB_TOL:
                raise ValueError(f"set {h.set_id} contradicts the evidence but has posterior > 0")
        return self

    def move_probability(self, move_id: str) -> float:
        """P(opponent carries this move) = Σ posterior of sets containing it."""
        return math.fsum(h.posterior for h in self.hypotheses if move_id in h.moves)

    def item_probability(self, item_id: str | None) -> float:
        """P(opponent holds this item); `None` asks for "no item"."""
        return math.fsum(h.posterior for h in self.hypotheses if h.item == item_id)

    def ability_probability(self, ability_id: str | None) -> float:
        return math.fsum(h.posterior for h in self.hypotheses if h.ability == ability_id)


class ActionPrediction(Strict):
    """Opponent's next action distribution (XGBoost later; heuristic fallback earlier)."""

    p_attack: float = Field(ge=0.0, le=1.0)
    p_switch: float = Field(ge=0.0, le=1.0)
    p_utility: float = Field(ge=0.0, le=1.0)
    model_version: str

    @model_validator(mode="after")
    def _sums(self) -> Self:
        total = self.p_attack + self.p_switch + self.p_utility
        if abs(total - 1.0) > PROB_TOL:
            raise ValueError(f"action probabilities sum to {total:.6f}, not 1")
        return self


# --------------------------------------------------------------------------- threat report


class MoveThreat(Strict):
    """What one move the opponent may carry would do to our Pokémon.

    The damage figures are conditional on the opponent having the move and on it landing,
    taken over the set hypotheses that carry it. Percentages are of our Pokémon's maximum HP.

    Two "highest damage" figures exist, and a user interface must not mix them up:
    `worst_crit_pct` is the most this move can do and is what should be shown as "worst case";
    `worst_case_pct` is the most it can do without a critical hit and should be labelled so.
    """

    move_id: ShowdownId
    probability: float = Field(ge=0.0, le=1.0)  # P(the opponent carries this move)
    expected_pct: float | None = Field(default=None, ge=0.0)  # mean damage of one normal hit
    worst_case_pct: float | None = Field(default=None, ge=0.0)  # highest roll without a crit
    worst_crit_pct: float | None = Field(default=None, ge=0.0)  # highest roll with a crit
    ko_probability: float | None = Field(default=None, ge=0.0, le=1.0)  # one use, crits included
    # Set when the calculator cannot evaluate the move: it is then unknown, never "no damage".
    unsupported_reason: str | None = None

    @model_validator(mode="after")
    def _unsupported_has_no_numbers(self) -> Self:
        damage = (self.expected_pct, self.worst_case_pct, self.worst_crit_pct)
        numbers = (*damage, self.ko_probability)
        if self.unsupported_reason is not None and any(n is not None for n in numbers):
            raise ValueError("an unsupported move carries no damage numbers")
        if len({n is None for n in damage}) > 1:
            raise ValueError("expected and worst-case damage are given together")
        if self.expected_pct is not None:
            if self.worst_case_pct + PROB_TOL < self.expected_pct:
                raise ValueError("worst-case damage is below the expected damage")
            if self.worst_crit_pct + PROB_TOL < self.worst_case_pct:
                raise ValueError("a critical hit cannot do less than the worst normal hit")
        return self


class ThreatReport(Strict):
    """The opponent's possible moves against our Pokémon, most likely first."""

    attacker_species: ShowdownId
    defender_species: ShowdownId
    threats: list[MoveThreat] = Field(default_factory=list)
    # "If they attack, can they knock us out this turn?": for each possible set the KO chance
    # of its best move, weighted by how likely the set is. Moves are correlated inside a set,
    # so this cannot be read off the per-move figures.
    p_ko_best_move: float = Field(default=0.0, ge=0.0, le=1.0)
    # True when a possible move could not be evaluated and so counted as 0 above: the real
    # chance is then at least `p_ko_best_move`, never less.
    ko_lower_bound: bool = False

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        ids = [t.move_id for t in self.threats]
        if len(set(ids)) != len(ids):
            raise ValueError("a move is listed twice")
        odds = [t.probability for t in self.threats]
        if odds != sorted(odds, reverse=True):
            raise ValueError("threats must be ordered by probability, highest first")
        return self


# --------------------------------------------------------------------------- wrapper

T = TypeVar("T", bound=BaseModel)


class SubsystemResult(BaseModel, Generic[T]):
    status: SubsystemStatus
    latency_ms: float = Field(ge=0)
    payload: T | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.status in (SubsystemStatus.OK, SubsystemStatus.FALLBACK) and self.payload is None:
            raise ValueError(f"status {self.status.value} requires a payload")
        if self.status in (SubsystemStatus.ERROR, SubsystemStatus.TIMEOUT) and not self.error:
            raise ValueError(f"status {self.status.value} requires an error message")
        return self


# --------------------------------------------------------------------------- synthesis guardrail


class Recommendation(Strict):
    """The only object the LLM is allowed to produce.

    Validate with context to enforce legality against the live state:
        Recommendation.model_validate(llm_json, context={"state": game_state,
                                                         "allowed_numbers": {...}})
    A ValidationError here is the signal for the orchestrator to retry the LLM.
    """

    action: ActionKind
    move_id: ShowdownId | None = None
    switch_index: int | None = None
    headline: str = Field(min_length=1, max_length=120)  # "68% switch odds -> Ice Beam"
    explanation: str = Field(min_length=1, max_length=600)
    cited_numbers: dict[str, float] = Field(default_factory=dict)  # every number in the text

    @model_validator(mode="after")
    def _shape_and_legality(self, info: ValidationInfo) -> Self:
        if self.action is ActionKind.MOVE and (self.move_id is None or self.switch_index is not None):
            raise ValueError("a move recommendation needs move_id and no switch_index")
        if self.action is ActionKind.SWITCH and (self.switch_index is None or self.move_id is not None):
            raise ValueError("a switch recommendation needs switch_index and no move_id")

        ctx = info.context or {}
        state: GameState | None = ctx.get("state")
        if state is not None:
            req = state.me.request
            if req is None:
                raise ValueError("no pending request: nothing can be recommended")
            if self.action is ActionKind.MOVE and self.move_id not in req.available_moves:
                raise ValueError(f"illegal move {self.move_id!r}; legal: {req.available_moves}")
            if self.action is ActionKind.SWITCH and self.switch_index not in req.available_switches:
                raise ValueError(
                    f"illegal switch {self.switch_index}; legal: {req.available_switches}"
                )

        allowed: dict[str, float] | None = ctx.get("allowed_numbers")
        if allowed is not None:
            # Rule 1: the LLM may only repeat numbers the math/ML layers produced.
            for key, val in self.cited_numbers.items():
                if key not in allowed or abs(allowed[key] - val) > 1e-9:
                    raise ValueError(f"cited number {key}={val} was not produced by a subsystem")
        return self
