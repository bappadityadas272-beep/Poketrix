"""Turns a decision into words. Templates only: a sentence appears when its numbers exist,
and every number printed is taken from the turn's register and cited, so the guardrail can
check it. Another writer (an LLM, later) would implement the same `Writer` protocol.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from poketrix.dex import UnknownDexEntryError
from poketrix.schemas import ActionKind, Decision, Recommendation

from .policy import SELF_FAINT, TRAP_NAMES_A_MOVE
from .situation import Situation

NO_NUMBERS = "No further numbers are available for this decision."
SACRIFICE = "sacrifices your Pokémon"  # ruling 15-R: said whenever a self-faint move is advised


@dataclass(frozen=True)
class Brief:
    """What a writer is given: the decision, the numbers it may quote, and two caveats."""

    situation: Situation
    decision: Decision
    numbers: Mapping[str, float]
    caveat: str | None = None  # why the decision rests on limited information
    ko_is_lower_bound: bool = False  # R5: one of their possible moves could not be evaluated


class Writer(Protocol):
    def write(self, brief: Brief) -> Recommendation: ...


class _Quotes:
    """Hands out numbers as text and remembers each one for `cited_numbers`."""

    def __init__(self, numbers: Mapping[str, float]) -> None:
        self._numbers = numbers
        self.cited: dict[str, float] = {}

    def pct(self, key: str, positive: bool = False) -> str | None:
        value = self._numbers.get(key)
        if value is None or (positive and value <= 0):
            return None
        self.cited[key] = value
        return f"{round(100 * value)}%"


class TemplateWriter:
    def write(self, brief: Brief) -> Recommendation:
        choice = brief.decision.choice
        quotes = _Quotes(brief.numbers)
        compose = self._move if choice.action is ActionKind.MOVE else self._switch
        headline, sentences = compose(brief, quotes)
        if brief.caveat:
            sentences.append(brief.caveat)
        return Recommendation(
            action=choice.action, move_id=choice.move_id, switch_index=choice.switch_index,
            headline=headline, explanation=" ".join(sentences) or NO_NUMBERS,
            cited_numbers=quotes.cited,
        )

    @staticmethod
    def _move_name(situation: Situation, move_id: str) -> str:
        try:
            return situation.dex.move(move_id).name
        except UnknownDexEntryError:
            return move_id.capitalize()

    def _their_attack(self, brief: Brief, quotes: _Quotes, index: int, target: str) -> list[str]:
        """What their best move does to our Pokémon `index`."""
        theirs = brief.situation.theirs.species.name
        share, ko = quotes.pct(f"their.{index}.share"), quotes.pct(f"their.{index}.p_ko")
        if share is None or ko is None:
            return []
        found = [(f"If {theirs} attacks, it takes about {share} of {target}'s remaining HP and "
                  f"knocks it out {ko} of the time.")]
        if brief.ko_is_lower_bound:
            found.append("That knock-out chance is a lower bound: one of its possible moves "
                         "could not be evaluated.")
        return found

    def _move(self, brief: Brief, quotes: _Quotes) -> tuple[str, list[str]]:
        situation, reason = brief.situation, brief.decision.reason
        index = situation.me.active_index
        ours, theirs = situation.ours.species.name, situation.theirs.species.name
        move_id = brief.decision.choice.move_id
        move = self._move_name(situation, move_id)
        share = quotes.pct(f"our.{index}.{move_id}.share")
        ko = quotes.pct(f"our.{index}.{move_id}.ko")
        sentences = [f"{move} {SACRIFICE}: {ours} faints."] if move_id in SELF_FAINT else []
        if share is not None and ko is not None:
            sentences.append(f"{move} removes about {share} of {theirs}'s remaining HP on "
                             f"average and knocks it out {ko} of the time.")
        if reason == "utility":
            sentences.append(f"{move} is worth more this turn than our best attack.")
        first = quotes.pct(f"our.{index}.{move_id}.first")
        if first is not None and reason not in ("only_option", "limited"):
            sentences.append(f"{ours} acts first {first} of the time.")
        sentences += self._their_attack(brief, quotes, index, ours)
        headline = {
            "knockout": f"{move}: {ko} to knock out {theirs}",
            "best_trade": f"{move}: about {share} of {theirs}'s remaining HP",
            "utility": f"{move}: the best use of this turn against {theirs}",
            "only_option": f"{move}: the only legal action",
        }.get(reason, f"{move}: chosen on limited information")
        return headline, sentences

    def _switch(self, brief: Brief, quotes: _Quotes) -> tuple[str, list[str]]:
        situation, decision = brief.situation, brief.decision
        target_index = decision.choice.switch_index
        ours, theirs = situation.ours.species.name, situation.theirs.species.name
        target = situation.me.team[target_index].species.name
        sentences = self._their_attack(brief, quotes, target_index, target)
        hazard = quotes.pct(f"switch.{target_index}.hazard", positive=True)
        if hazard is not None:
            sentences.append(f"Entry hazards cost {target} {hazard} of its remaining HP first.")
        if situation.request.force_switch or decision.reason == "only_option":
            return f"Send in {target}", sentences
        risk = quotes.pct("trap.risk", positive=True)
        if risk is not None:  # R14: stated, not scored (a refused switch costs nothing, R15)
            sentences.append(f"{theirs} may be able to trap {ours} ({risk}).")
            fallback = decision.alternative_move
            if brief.numbers["trap.risk"] >= TRAP_NAMES_A_MOVE and fallback is not None:
                sentences.append(f"If the switch is refused, use "
                                 f"{self._move_name(situation, fallback)}.")
        stays = quotes.pct(f"their.{situation.me.active_index}.p_ko")
        if stays is None:
            return f"Switch to {target}", sentences
        return f"Switch to {target}: {ours} is knocked out {stays} of the time if it stays", sentences
