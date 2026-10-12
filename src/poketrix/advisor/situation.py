"""What every stage of the turn engine looks at: one decision point and the data to judge it."""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from poketrix.dex import Dex
from poketrix.schemas import (
    ActionRequest,
    BattlePokemon,
    GameState,
    SetEvidence,
    SetPosterior,
    SideState,
)
from poketrix.showdown import TurnSnapshot
from poketrix.uncloak import SetPrior, hypothesis_set

TRANSFORMED = "transform"


class Deadline:
    """A point in time that work must not run past.

    The stages are CPU-bound, so nothing can stop them from outside: each one asks between
    units of work whether its time is up and, if so, returns what it has finished.
    """

    def __init__(self, budget_ms: float, clock: Callable[[], float] = perf_counter) -> None:
        self._clock = clock
        self._end = clock() + budget_ms / 1000

    def expired(self) -> bool:
        return self._clock() >= self._end

    def within(self, budget_ms: float) -> "Deadline":
        """A stage's own deadline: its budget from now, but never later than this one."""
        stage = Deadline(budget_ms, self._clock)
        stage._end = min(stage._end, self._end)
        return stage


@dataclass(frozen=True)
class Situation:
    snapshot: TurnSnapshot
    prior: SetPrior
    dex: Dex

    @property
    def state(self) -> GameState:
        return self.snapshot.state

    @property
    def me(self) -> SideState:
        return self.state.me

    @property
    def them(self) -> SideState:
        return self.state.opponent

    @property
    def request(self) -> ActionRequest:
        return self.me.request

    @property
    def ours(self) -> BattlePokemon:
        return self.me.active

    @property
    def theirs(self) -> BattlePokemon:
        return self.them.active

    @property
    def attackers(self) -> list[int]:
        """Our Pokémon that may be the one acting next: the active one if it has a move to
        choose, then every legal switch-in. Indices into our team."""
        staying = [] if self.request.force_switch else [self.me.active_index]
        return staying + list(self.request.available_switches)

    @property
    def transformed(self) -> bool:
        """R11: the state holds a transformed Pokémon's own species and stats, not the copied
        ones, so no damage may be computed for it."""
        return any(TRANSFORMED in mon.volatiles for mon in (self.ours, self.theirs))

    def evidence(self, their_index: int) -> tuple[str, SetEvidence]:
        """The prior's key for one of their Pokémon, and what the battle has shown of it."""
        for found in self.snapshot.evidence:
            if found.player is self.them.player and found.team_index == their_index:
                return found.species_id, found.evidence
        raise KeyError(f"no evidence recorded for their Pokémon {their_index}")

    def their_sets(self, posterior: SetPosterior) -> list[tuple[float, BattlePokemon]]:
        """Their active Pokémon under each distinct item, ability and spread it may have, with
        the probability of each. Sets that differ only in moves are one entry: what we do to
        a Pokémon, and how fast it is, does not depend on its moves."""
        merged: dict[tuple, list] = {}
        for hypothesis in posterior.hypotheses:
            if hypothesis.posterior <= 0:
                continue
            known = hypothesis_set(self.theirs, hypothesis, self.prior)
            key = (known.item, known.ability, known.spread.model_dump_json())
            if key not in merged:
                merged[key] = [0.0, self.theirs.model_copy(update={"known_set": known})]
            merged[key][0] += hypothesis.posterior
        return [(weight, pokemon) for weight, pokemon in merged.values()]
