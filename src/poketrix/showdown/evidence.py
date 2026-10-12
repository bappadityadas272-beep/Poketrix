"""What a battle log proves about one Pokémon's set.

Wrong evidence would silently corrupt the uncloaker's posterior, so every rule here is
conservative: when a line could mean two things, nothing is concluded. The rules are checked
against simulated battles whose true teams are known (see `validation.py`).
"""

from poketrix.schemas import PokemonType, SetEvidence, Species

from .events import Effect

# A move seen with one of these `[from]` tags was chosen by the Pokémon itself: it is the
# continuation of a move it already used.
_OWN_MOVE_TAGS = frozenset({"lockedmove"})
# Moves that are never a slot of a Random Battle set but can appear after `|move|`.
_NEVER_A_SET_MOVE = frozenset({"struggle", "recharge"})

CHOICE_ITEMS = ("choiceband", "choicespecs", "choicescarf")
END_OF_TURN_RECOVERY_ITEMS = ("leftovers", "blacksludge")
# Abilities that make a move of one type do nothing, so taking damage from it excludes them.
ABSORBING_ABILITIES = {
    PokemonType.FIRE: ("flashfire",),
    PokemonType.WATER: ("waterabsorb", "dryskin"),
    PokemonType.ELECTRIC: ("voltabsorb", "motordrive"),
    PokemonType.GROUND: ("levitate",),
}


def chose_the_move(move_id: str, source: Effect | None) -> bool:
    """Whether a `|move|` line shows a move the Pokémon picked from its own four.

    A move called by another move (Sleep Talk, Metronome, Mirror Move, Copycat, Assist, Me First,
    Snatch, Magic Coat, Nature Power) carries a `[from]` tag naming the caller. Gens 1-3 write
    `[from] Sleep Talk`, Gen 4 writes `[from] move: Sleep Talk`; both arrive here as an id. Any
    tag we do not positively know to mean "its own move" is treated as a call.
    """
    if move_id in _NEVER_A_SET_MOVE:
        return False
    return source is None or source.id in _OWN_MOVE_TAGS or source.id == move_id


class EvidenceBook:
    """Collects the evidence about one Pokémon as the battle goes on."""

    def __init__(self, species: Species, items_in_generation: frozenset[str]) -> None:
        self._may_have = frozenset(species.possible_abilities)
        self._items_in_generation = items_in_generation
        self.moves: list[str] = []
        self.item: str | None = None  # the item it started the battle with, once seen
        self.ability: str | None = None  # the ability it started with, once seen
        self.ruled_out_items: set[str] = set()
        self.ruled_out_abilities: set[str] = set()
        self.item_swapped = False  # a Trick-like move has changed what it holds
        self.ability_changed = False
        self.anomalies: list[str] = []
        self._moves_this_stay: set[str] = set()

    def may_have(self, ability: str) -> bool:
        return ability in self._may_have

    # ------------------------------------------------------------------ moves

    def chose(self, move_id: str) -> None:
        """The Pokémon picked this move itself."""
        if move_id not in self.moves:
            if len(self.moves) == 4:
                self.anomalies.append(f"a fifth own move was seen: {move_id}")
                return
            self.moves.append(move_id)
        self._moves_this_stay.add(move_id)
        # N3: a Choice item locks the holder into the first move it picks during a stay.
        if len(self._moves_this_stay) > 1 and not self.may_have("klutz"):
            self.rule_out_items(*CHOICE_ITEMS)

    def left_the_field(self) -> None:
        self._moves_this_stay.clear()

    # ------------------------------------------------------------------ items

    def saw_item(self, item_id: str, before_swap: bool = False) -> None:
        """The Pokémon was seen holding (or losing) this item.

        After a swap the item is someone else's, so it says nothing about the set; `before_swap`
        is for the one line that shows what the Pokémon held just before the swap.
        """
        if self.item_swapped and not before_swap:
            return
        if self.item is not None and self.item != item_id:
            self.anomalies.append(f"two original items were seen: {self.item}, {item_id}")
            return
        if item_id in self.ruled_out_items:
            self.anomalies.append(f"item {item_id} was seen after being ruled out")
        self.item = item_id
        self.ruled_out_items.clear()  # the item is known: nothing else needs excluding

    def rule_out_items(self, *item_ids: str) -> None:
        if self.item_swapped or self.item is not None:  # nothing left to narrow down
            return
        self.ruled_out_items.update(i for i in item_ids if i in self._items_in_generation)

    # ------------------------------------------------------------------ abilities

    def saw_ability(self, ability_id: str) -> None:
        if self.ability_changed:
            return
        if self.ability is not None and self.ability != ability_id:
            self.anomalies.append(f"two original abilities were seen: {self.ability}, {ability_id}")
            return
        if ability_id in self.ruled_out_abilities:
            self.anomalies.append(f"ability {ability_id} was seen after being ruled out")
        self.ability = ability_id
        self.ruled_out_abilities.clear()

    def ability_was_changed(self) -> None:
        """Trace, Skill Swap, Role Play, Transform, Gastro Acid: no longer the original."""
        self.ability_changed = True

    def rule_out_abilities(self, *ability_ids: str) -> None:
        if self.ability_changed or self.ability is not None:
            return
        self.ruled_out_abilities.update(a for a in ability_ids if a in self._may_have)

    # ------------------------------------------------------------------ result

    def evidence(self) -> SetEvidence:
        return SetEvidence(
            revealed_moves=list(self.moves), item=self.item,
            ruled_out_items=frozenset(self.ruled_out_items), ability=self.ability,
            ruled_out_abilities=frozenset(self.ruled_out_abilities),
        )
