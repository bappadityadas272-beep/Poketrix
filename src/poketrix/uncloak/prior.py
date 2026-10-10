"""The prior: Random Battle sets per species, loaded from the committed table.

The table (`data/randbats/gen{N}/sets.json`) is written by scripts/randbats/build_randbats.mjs
from Showdown's official team generator. Every row is validated against the dex and the
schemas at load time, so a stale or damaged table fails loudly instead of skewing a posterior.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from pathlib import Path
from types import MappingProxyType

from poketrix.dex import Dex
from poketrix.schemas import Generation, PokemonSet, PriorSet, Stat, StatSpread, rules_for

# src/poketrix/uncloak/prior.py -> repo root
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "randbats"


def read_set_table(path: Path, gen: Generation) -> list[PriorSet]:
    """Parse one set table (the prior or a held-out sample) into validated rows."""
    if not path.is_file():
        raise FileNotFoundError(
            f"set table missing: {path} (rebuild it with scripts/randbats/build_randbats.mjs)"
        )
    table = json.loads(path.read_text(encoding="utf-8"))
    if table["source"]["format"] != f"gen{int(gen)}randombattle":
        raise ValueError(f"{path} is not a Gen {int(gen)} Random Battle table")
    dex, rules = Dex(gen), rules_for(gen)
    default_ev = table["source"]["default_spread"]["ev"]
    rows: list[PriorSet] = []
    rank_in_species: dict[str, int] = {}
    for row in table["sets"]:
        species = dex.species(row["species"])
        # Unknown ids raise here: the table and the dex snapshot must agree.
        moves = [dex.move(move).id for move in row["moves"]]
        item = None if row["item"] is None else dex.item(row["item"]).id
        evs = {Stat(stat): default_ev for stat in Stat} if rules.has_natures else {}
        evs.update({Stat(stat): value for stat, value in row["evs"].items()})
        pokemon_set = PokemonSet(
            species=species, level=row["level"], moves=moves, item=item, ability=row["ability"],
            spread=StatSpread(ivs=row["ivs"], evs=evs),
        )
        rank = rank_in_species[species.id] = rank_in_species.get(species.id, 0) + 1
        set_id = f"{species.id}:{rank}"
        rows.append(PriorSet(set_id=set_id, pokemon_set=pokemon_set, count=row["count"]))
    return rows


class SetPrior:
    """Known sets per species for one generation. Treat the rows as read-only."""

    def __init__(self, gen: Generation | int, rows: Iterable[PriorSet]) -> None:
        self.gen = Generation(gen)
        by_species: dict[str, list[PriorSet]] = {}
        by_id: dict[str, PriorSet] = {}
        for row in rows:
            if row.pokemon_set.generation is not self.gen:
                raise ValueError(f"set {row.set_id} is not a Gen {int(self.gen)} set")
            if row.set_id in by_id:
                raise ValueError(f"duplicate set id {row.set_id!r}")
            by_id[row.set_id] = row
            by_species.setdefault(row.pokemon_set.species.id, []).append(row)
        self._by_species: Mapping[str, Sequence[PriorSet]] = MappingProxyType(
            {species: tuple(sets) for species, sets in by_species.items()}
        )
        self._by_id: Mapping[str, PriorSet] = MappingProxyType(by_id)

    def sets_for(self, species_id: str) -> Sequence[PriorSet]:
        """Every known set of a species, most frequent first; empty if the species is unknown."""
        return self._by_species.get(species_id, ())

    def pokemon_set(self, set_id: str) -> PokemonSet:
        """The full set behind a hypothesis, ready for the damage calculator."""
        try:
            return self._by_id[set_id].pokemon_set
        except KeyError:
            raise KeyError(f"unknown set id {set_id!r} in the Gen {int(self.gen)} prior") from None

    def all_sets(self) -> Sequence[PriorSet]:
        return tuple(self._by_id.values())

    def without(self, set_ids: Iterable[str]) -> "SetPrior":
        """A copy lacking some sets (used to test behaviour when the prior is out of date)."""
        dropped = set(set_ids)
        kept = (row for row in self._by_id.values() if row.set_id not in dropped)
        return SetPrior(self.gen, kept)


@cache
def load_prior(gen: Generation | int, data_dir: Path = DEFAULT_DATA_DIR) -> SetPrior:
    gen = Generation(gen)
    return SetPrior(gen, read_set_table(data_dir / f"gen{int(gen)}" / "sets.json", gen))
