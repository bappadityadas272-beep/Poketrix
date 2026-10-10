"""Loads the committed dex snapshot (`data/dex/`) into schema objects.

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

from poketrix.schemas import Generation, Item, Move, Nature, PokemonType, Species, rules_for

# src/poketrix/dex/snapshot.py -> repo root
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "dex"

_Record = TypeVar("_Record", bound=BaseModel)
_EMPTY = MappingProxyType({})


@dataclass(frozen=True)
class Snapshot:
    species: MappingProxyType  # id -> Species
    moves: MappingProxyType  # id -> Move
    items: MappingProxyType  # id -> Item (empty in Gen 1)


def _read_json(path: Path):
    if not path.is_file():
        raise FileNotFoundError(
            f"dex snapshot file missing: {path} (rebuild it with scripts/build_dex.mjs)"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_records(path: Path, model: type[_Record], extra: dict) -> MappingProxyType:
    records: dict[str, _Record] = {}
    for raw in _read_json(path):
        record = model.model_validate({**raw, **extra})
        if record.id in records:
            raise ValueError(f"duplicate id {record.id!r} in {path}")
        records[record.id] = record
    return MappingProxyType(records)


@cache
def load_snapshot(gen: Generation, data_dir: Path = DEFAULT_DATA_DIR) -> Snapshot:
    gen_dir = data_dir / f"gen{int(gen)}"
    stamp = {"generation": gen}
    has_items = rules_for(gen).has_items
    return Snapshot(
        species=_load_records(gen_dir / "species.json", Species, stamp),
        moves=_load_records(gen_dir / "moves.json", Move, stamp),
        items=_load_records(gen_dir / "items.json", Item, stamp) if has_items else _EMPTY,
    )


_CHART_MULTIPLIERS = frozenset({0, 0.5, 2})


@cache
def load_type_chart(gen: Generation, data_dir: Path = DEFAULT_DATA_DIR) -> MappingProxyType:
    """attacking type -> defending type -> multiplier; pairs that are absent are neutral (1x)."""
    path = data_dir / f"gen{int(gen)}" / "typechart.json"
    legal = rules_for(gen).pokemon_types
    chart: dict[PokemonType, MappingProxyType] = {}
    for attacking, row in _read_json(path).items():
        parsed = {PokemonType(defending): float(mult) for defending, mult in row.items()}
        bad_types = ({PokemonType(attacking)} | set(parsed)) - legal
        if bad_types:
            names = sorted(t.value for t in bad_types)
            raise ValueError(f"type(s) {names} not in Gen {int(gen)}: {path}")
        if not set(parsed.values()) <= _CHART_MULTIPLIERS:
            raise ValueError(f"type chart multipliers must be 0, 0.5 or 2: {path}")
        chart[PokemonType(attacking)] = MappingProxyType(parsed)
    if set(chart) != legal:
        raise ValueError(f"type chart must list every Gen {int(gen)} type: {path}")
    return MappingProxyType(chart)


@cache
def load_natures(data_dir: Path = DEFAULT_DATA_DIR) -> MappingProxyType:
    """nature id -> Nature."""
    return _load_records(data_dir / "natures.json", Nature, {})
