"""Our own Pokémon, as a `|request|` describes it, turned into a full `PokemonSet`.

A request gives the moves, item, ability and final stats, but not the IVs and EVs behind
them. The spread is looked up in the Random Battle set table: the first spread of that species
that reproduces the request's stats exactly (and, for Hidden Power, its type).
"""

from poketrix.calc import compute_stats, hidden_power
from poketrix.dex import Dex, UnknownDexEntryError
from poketrix.schemas import PokemonSet, Species, Stat, StatSpread, rules_for
from poketrix.schemas.pokemon import UNTYPED_HIDDEN_POWER
from poketrix.uncloak import SetPrior

from .events import RequestPokemon


def set_move_id(dex: Dex, sent: str) -> str:
    """The dex id of a move as a request spells it: `return102` is Return at 102 power."""
    try:
        return dex.move(sent).id
    except UnknownDexEntryError:
        return dex.move(sent.rstrip("0123456789")).id


def own_set(
    seen: RequestPokemon, species: Species, dex: Dex, prior: SetPrior
) -> tuple[PokemonSet, bool]:
    """The set, and whether its spread reproduces the request's stats.

    When no known spread does, the set carries the default spread and the caller is told, so
    that nothing downstream mistakes its stats for exact ones.
    """
    moves = [set_move_id(dex, move) for move in seen.moves]

    def with_spread(spread: StatSpread, nature: str | None = None) -> PokemonSet:
        return PokemonSet(
            species=species, level=seen.level, moves=moves, item=seen.item_id,
            ability=seen.ability_id, nature=nature, spread=spread,
        )

    known = sorted(
        (row.pokemon_set for row in prior.sets_for(species.id)),
        key=lambda known_set: -len(set(known_set.moves) & set(moves)),  # likeliest spread first
    )
    tried: list[StatSpread] = []
    for known_set in known:
        if known_set.spread in tried:
            continue
        tried.append(known_set.spread)
        candidate = with_spread(known_set.spread, known_set.nature)
        if _reproduces(candidate, seen, dex):
            return candidate, True
    return with_spread(StatSpread()), False


def _reproduces(candidate: PokemonSet, seen: RequestPokemon, dex: Dex) -> bool:
    stats = compute_stats(candidate)
    if any(stats[stat] != value for stat, value in seen.stats.items()):
        return False
    if seen.hp.maximum is not None and stats[Stat.HP] != seen.hp.maximum:
        return False
    ivs = candidate.spread.ivs
    return not (ivs and rules_for(candidate.generation).has_items) or all(
        hidden_power(candidate.generation, ivs)[0] is dex.move(move).type
        for move in candidate.moves
        if move.startswith(UNTYPED_HIDDEN_POWER) and move != UNTYPED_HIDDEN_POWER
    )
