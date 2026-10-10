"""Loads one generation's committed dex snapshot (`data/dex/gen{N}/`) into schema objects.

The snapshot is written by `scripts/build_dex.mjs`. Every record is validated against
`poketrix.schemas` here, so bad data fails loudly at load time instead of deep inside the math.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

from pydantic import BaseModel

from poketrix.schemas import Generation, Move, Species

# src/poketrix/dex/snapshot.py -> repo root
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "dex"

_Record = TypeVar("_Record", bound=BaseModel)


@dataclass(frozen=True)
class Snapshot:
    species: MappingProxyType  # id -> Species
    moves: MappingProxyType  # id -> Move


def _load_records(path: Path, model: type[_Record], gen: Generation) -> MappingProxyType:
    if not path.is_file():
        raise FileNotFoundError(
            f"dex snapshot file missing: {path} (rebuild it with scripts/build_dex.mjs)"
        )
    records: dict[str, _Record] = {}
    for raw in json.loads(path.read_text(encoding="utf-8")):
        record = model.model_validate({**raw, "generation": gen})
        if record.id in records:
            raise ValueError(f"duplicate id {record.id!r} in {path}")
        records[record.id] = record
    return MappingProxyType(records)


@cache
def load_snapshot(gen: Generation, data_dir: Path = DEFAULT_DATA_DIR) -> Snapshot:
    gen_dir = data_dir / f"gen{int(gen)}"
    return Snapshot(
        species=_load_records(gen_dir / "species.json", Species, gen),
        moves=_load_records(gen_dir / "moves.json", Move, gen),
    )
