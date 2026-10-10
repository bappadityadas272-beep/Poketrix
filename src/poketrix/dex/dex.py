"""`Dex(gen)`: offline lookup of schema-validated `Species` and `Move` for one generation."""

from collections.abc import Mapping
from pathlib import Path

from poketrix.schemas import Generation, Item, Move, Species, to_id

from .snapshot import DEFAULT_DATA_DIR, load_snapshot


class UnknownDexEntryError(KeyError):
    """Raised when an id is not in the dex of the requested generation."""

    def __init__(self, kind: str, entry_id: str, gen: Generation) -> None:
        super().__init__(f"unknown {kind} {entry_id!r} in Gen {int(gen)}")
        self.kind = kind
        self.entry_id = entry_id
        self.gen = gen

    def __str__(self) -> str:  # KeyError would otherwise show the repr of the message
        return self.args[0]


class Dex:
    """Static data for one generation. Returned objects are shared: treat them as read-only."""

    def __init__(self, gen: Generation | int, data_dir: Path = DEFAULT_DATA_DIR) -> None:
        try:
            self.gen = Generation(gen)
        except ValueError:
            supported = ", ".join(str(int(g)) for g in Generation)
            raise ValueError(
                f"unsupported generation {gen!r}; supported generations: {supported}"
            ) from None
        self._snapshot = load_snapshot(self.gen, data_dir)

    def species(self, name_or_id: str) -> Species:
        return self._get("species", self._snapshot.species, name_or_id)

    def move(self, name_or_id: str) -> Move:
        return self._get("move", self._snapshot.moves, name_or_id)

    def item(self, name_or_id: str) -> Item:
        return self._get("item", self._snapshot.items, name_or_id)

    def all_species(self) -> list[Species]:
        return list(self._snapshot.species.values())

    def all_moves(self) -> list[Move]:
        return list(self._snapshot.moves.values())

    def all_items(self) -> list[Item]:
        return list(self._snapshot.items.values())

    def _get(self, kind: str, table: Mapping, name_or_id: str):
        entry_id = to_id(name_or_id)
        try:
            return table[entry_id]
        except KeyError:
            raise UnknownDexEntryError(kind, entry_id, self.gen) from None
