"""Contracts of the set uncloaker's inputs: what has been observed about an opponent's
Pokémon, and one row of the Random Battle set table that serves as the prior."""

from pydantic import Field, model_validator
from typing_extensions import Self

from .pokemon import PokemonSet, ShowdownId, Strict


class SetEvidence(Strict):
    """Everything a battle has revealed so far about one opposing Pokémon's set.

    `ruled_out_*` holds negative evidence the battle-log parser can establish (no Leftovers
    recovery, no Life Orb recoil, a second different move without switching: not a Choice item).
    """

    revealed_moves: list[ShowdownId] = Field(default_factory=list, max_length=4)
    item: ShowdownId | None = None  # seen, even if since consumed or knocked off
    ruled_out_items: frozenset[ShowdownId] = frozenset()
    ability: ShowdownId | None = None
    ruled_out_abilities: frozenset[ShowdownId] = frozenset()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if len(set(self.revealed_moves)) != len(self.revealed_moves):
            raise ValueError("duplicate revealed moves")
        if self.item is not None and self.item in self.ruled_out_items:
            raise ValueError(f"item {self.item!r} is both revealed and ruled out")
        if self.ability is not None and self.ability in self.ruled_out_abilities:
            raise ValueError(f"ability {self.ability!r} is both revealed and ruled out")
        return self


class PriorSet(Strict):
    """One distinct set the Random Battle generator produces, and how often it produced it."""

    set_id: str = Field(min_length=1)  # "<species id>:<rank by frequency>", stable per table
    pokemon_set: PokemonSet
    count: int = Field(ge=1)
