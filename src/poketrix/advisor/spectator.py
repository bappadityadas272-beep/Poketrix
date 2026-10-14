"""A spectator's turn seen from one player's side, so that the turn engine can advise on it.

A spectator's log (a replay, a battle being watched) gives neither player a known set, while
the engine needs one for each of "our" Pokémon it judges. Each is given its most likely set
under the evidence so far, and a request offers what that player could do: the active
Pokémon's moves and, if asked, a switch to every other Pokémon of theirs seen and still alive.
"""

from poketrix.schemas import ActionRequest, BattlePokemon, PlayerSlot
from poketrix.showdown import TurnSnapshot
from poketrix.uncloak import SetPrior, Uncloaker, hypothesis_set


def _with_likeliest_set(snapshot: TurnSnapshot, player: PlayerSlot, index: int,
                        pokemon: BattlePokemon, prior: SetPrior) -> BattlePokemon | None:
    found = next((f for f in snapshot.evidence
                  if f.player is player and f.team_index == index), None)
    if found is None or pokemon.fainted:
        return None
    posterior = Uncloaker(prior).uncloak(found.species_id, found.evidence).payload
    if posterior is None:
        return None
    likeliest = max(posterior.hypotheses, key=lambda hypothesis: hypothesis.posterior)
    return pokemon.model_copy(update={"known_set": hypothesis_set(pokemon, likeliest, prior)})


def seen_as(snapshot: TurnSnapshot, player: PlayerSlot, prior: SetPrior,
            switches: bool = False) -> TurnSnapshot | None:
    """The snapshot as `player`'s own log would show it, with likeliest sets and a request.
    None when its active Pokémon has no set to name."""
    side = snapshot.state.sides[player]
    active = _with_likeliest_set(snapshot, player, side.active_index, side.active, prior)
    if active is None:
        return None
    team = list(side.team)
    team[side.active_index] = active
    benched = []
    for index, pokemon in enumerate(side.team):
        if switches and index != side.active_index:
            known = _with_likeliest_set(snapshot, player, index, pokemon, prior)
            if known is not None:
                team[index] = known
                benched.append(index)
    request = ActionRequest(available_moves=active.known_set.moves, available_switches=benched)
    state = snapshot.state.model_copy(update={
        "perspective": player,
        "sides": snapshot.state.sides
        | {player: side.model_copy(update={"team": team, "request": request})},
    })
    return snapshot.model_copy(update={"state": state})
