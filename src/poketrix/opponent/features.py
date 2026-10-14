"""What a player can see of the other side's decision at the moment it is made.

A `DecisionView` describes one decision of the deciding player ("it") from across the field:
plain fields are about its side, `target_*` fields about the Pokémon it faces and that
Pokémon's side. Every value comes from lines read before the decision. A quantity that could
not be computed is NaN, which the learned model treats as missing.

The fields, in this order, are the model's feature vector: adding, removing or reordering one
makes every saved model stale, and `XgbModel` then refuses to load it.
"""

from dataclasses import astuple, dataclass, fields

from poketrix.schemas import HAZARDS, SideState, Status

ACTIONS = ("attack", "utility", "switch")  # the classes, in the model's order
MISSING = float("nan")
HEALTHY_FROM = 0.5  # a benched Pokémon above this share of its HP, with no status, is healthy
_STATUS_CODE = {status: code for code, status in enumerate(Status, start=1)}


@dataclass(frozen=True)
class DecisionView:
    generation: float
    turn: float
    hp: float  # share of its HP its active Pokémon has left
    target_hp: float
    status: float  # 0 for none, else the position in `Status`
    target_status: float
    boosts: float  # sum of its stat stages
    target_boosts: float
    alive: float  # Pokémon it has left, unrevealed ones included
    target_alive: float
    healthy_bench: float
    target_healthy_bench: float
    best_ko: float  # chance that its best move knocks the target out this turn
    best_share: float  # expected share of the target's remaining HP its best move removes
    target_best_ko: float  # the same two, for the target's moves against it
    target_best_share: float
    moves_first: float  # chance that it acts before the target's hardest-hitting move
    hazards: float  # layers of entry hazards on its own side
    status_move_revealed: float  # 1 if a move it has shown is a status move
    damaging_share: float  # share of its likely moveset that is damaging moves
    rating: float = MISSING  # its ladder rating, where the log states one

    def vector(self) -> tuple[float, ...]:
        return astuple(self)


FEATURES = tuple(field.name for field in fields(DecisionView))


def status_code(status: Status | None) -> float:
    return float(_STATUS_CODE.get(status, 0))


def healthy_bench(side: SideState) -> float:
    """Benched Pokémon fit to come in. One not yet revealed has taken no damage."""
    benched = (mon for index, mon in enumerate(side.team) if index != side.active_index)
    healthy = sum(mon.hp_fraction > HEALTHY_FROM and mon.status is None for mon in benched)
    return float(healthy + side.team_size - len(side.team))


def hazard_layers(side: SideState) -> float:
    return float(sum(layers for condition, layers in side.conditions.items()
                     if condition in HAZARDS))
