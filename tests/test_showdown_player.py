"""Player mode: a player's own log, with `|request|` lines, gives our full team, exact HP and
the legal actions at every decision."""

import json

import pytest
from pydantic import ValidationError

from poketrix.calc import compute_stats
from poketrix.dex import Dex
from poketrix.schemas import Generation, PlayerSlot, Stat, Status
from poketrix.showdown import events as ev
from poketrix.showdown import parse_battle, parse_line
from poketrix.showdown.ownset import own_set, set_move_id
from poketrix.showdown.validation import load_battles, validate_player
from poketrix.uncloak import load_prior

P1, P2 = PlayerSlot.P1, PlayerSlot.P2
GENS = list(Generation)

# Two of player 1's Pokémon, as Showdown's simulator sends them in Gen 4 Random Battle.
PORYGON_Z = {
    "ident": "p1: Porygon-Z", "details": "Porygon-Z, L80", "condition": "267/267", "active": True,
    "stats": {"atk": 135, "def": 157, "spa": 261, "spd": 165, "spe": 189},
    "moves": ["icebeam", "nastyplot", "hiddenpowerfighting", "triattack"],
    "baseAbility": "adaptability", "item": "lifeorb", "pokeball": "pokeball",
}
AMBIPOM = {
    "ident": "p1: Ambipom", "details": "Ambipom, L80, M", "condition": "251/251", "active": False,
    "stats": {"atk": 206, "def": 152, "spa": 142, "spd": 152, "spe": 230},
    "moves": ["pursuit", "uturn", "return102", "lowkick"],
    "baseAbility": "technician", "item": "choiceband", "pokeball": "pokeball",
}
MOVES = [
    {"move": "Ice Beam", "id": "icebeam", "pp": 16, "maxpp": 16, "disabled": False},
    {"move": "Nasty Plot", "id": "nastyplot", "pp": 32, "maxpp": 32, "disabled": True},
    {"move": "Hidden Power Fighting 70", "id": "hiddenpower", "pp": 24, "maxpp": 24},
    {"move": "Tri Attack", "id": "triattack", "pp": 16, "maxpp": 16, "disabled": False},
]
HEADER = [
    "|gametype|singles", "|player|p1|Ash", "|player|p2|Gary", "|gen|4",
    "|tier|[Gen 4] Random Battle", "|teamsize|p1|6", "|teamsize|p2|6", "|start",
    "|switch|p1a: Porygon-Z|Porygon-Z, L80|267/267",
    "|switch|p2a: Swampert|Swampert, L80, M|100/100",
    "|turn|1",
]


def request(*team, active=None, **extra) -> str:
    """A `|request|` line for player 1. Each Pokémon is a base dict with its changes."""
    side = {"name": "Ash", "id": "p1", "pokemon": [base | changes for base, changes in team]}
    body = {"side": side, **extra}
    if active is not None:
        body["active"] = [active]
    return "|request|" + json.dumps(body)


def battle(*lines) -> str:
    return "\n".join([*HEADER, *lines])


# --------------------------------------------------------------------------- the request line


def test_request_line_becomes_a_typed_event():
    event = parse_line(request((PORYGON_Z, {}), (AMBIPOM, {}), active={"moves": MOVES}))
    assert isinstance(event, ev.RequestEvent) and event.player is P1
    assert [m.move_id for m in event.moves if not m.disabled] == [
        "icebeam", "hiddenpower", "triattack"
    ]
    lead = event.team[0]
    assert (lead.species_name, lead.level, lead.active) == ("Porygon-Z", 80, True)
    assert (lead.hp.current, lead.hp.maximum) == (267, 267)
    assert lead.stats[Stat.SPA] == 261 and lead.item_id == "lifeorb"
    assert not event.force_switch and not event.wait and not event.trapped


def test_request_shapes_that_ask_for_no_move():
    fainted = (PORYGON_Z, {"condition": "0 fnt"})
    forced = parse_line(request(fainted, (AMBIPOM, {}), forceSwitch=[True]))
    assert forced.force_switch and forced.moves == () and forced.team[0].hp.fainted
    assert parse_line(request((PORYGON_Z, {}), wait=True)).wait
    assert parse_line("|request|") is None  # sent when the battle is over
    gen1 = PORYGON_Z | {"baseAbility": "noability", "item": ""}
    trapped = parse_line(request(
        (gen1, {}), active={"moves": [{"move": "Recharge", "id": "recharge"}], "trapped": True}
    ))
    assert trapped.trapped and trapped.team[0].ability_id is None
    assert trapped.team[0].item_id is None


# --------------------------------------------------------------------------- our own sets


def test_own_set_takes_the_spread_that_gives_the_requests_stats():
    dex = Dex(4)
    seen = parse_line(request((AMBIPOM, {}))).team[0]
    own, exact = own_set(seen, dex.species("ambipom"), dex, load_prior(4))
    assert exact
    assert own.moves == ["pursuit", "uturn", "return", "lowkick"]  # `return102` is Return
    assert (own.item, own.ability, own.level) == ("choiceband", "technician", 80)
    stats = compute_stats(own)
    assert {stat: stats[stat] for stat in seen.stats} == seen.stats
    assert stats[Stat.HP] == seen.hp.maximum
    assert set_move_id(dex, "hiddenpowerfighting") == "hiddenpowerfighting"


def test_stats_that_no_known_spread_gives_are_reported_not_guessed_silently():
    lines = battle(request((PORYGON_Z, {"stats": PORYGON_Z["stats"] | {"spe": 999}}),
                           active={"moves": MOVES}))
    record = parse_battle(lines)
    assert any("no known spread" in note for note in record.anomalies)
    assert record.snapshots[0].state.me.active.known_set is not None


# --------------------------------------------------------------------------- snapshots


def test_every_decision_gets_a_snapshot_with_its_request():
    hurt = (PORYGON_Z, {"condition": "170/267 par"})
    fainted = (PORYGON_Z, {"condition": "0 fnt"})
    out = (AMBIPOM, {"active": True})
    record = parse_battle(battle(
        request((PORYGON_Z, {}), (AMBIPOM, {}), active={"moves": MOVES}),
        "|move|p1a: Porygon-Z|Hidden Power|p2a: Swampert",
        "|-damage|p2a: Swampert|60/100",
        "|move|p2a: Swampert|Body Slam|p1a: Porygon-Z",
        "|-damage|p1a: Porygon-Z|170/267",
        "|-status|p1a: Porygon-Z|par",
        "|upkeep",
        "|turn|2",
        request(hurt, (AMBIPOM, {}), active={"moves": MOVES}),
        "|move|p2a: Swampert|Earthquake|p1a: Porygon-Z",
        "|-damage|p1a: Porygon-Z|0 fnt",
        "|faint|p1a: Porygon-Z",
        "|upkeep",
        request(fainted, (AMBIPOM, {}), forceSwitch=[True]),
        "|switch|p1a: Ambipom|Ambipom, L80, M|251/251",
        "|turn|3",
        request(({**PORYGON_Z, "active": False}, {"condition": "0 fnt"}), out, wait=True),
        "|win|Gary",
    ), strict=True)
    assert record.player is P1 and record.request_disagreements == {}
    first, second, replacement, third, last = record.snapshots
    assert [s.turn for s in record.snapshots] == [1, 2, 2, 3, 3]

    me = first.state.me
    assert first.state.perspective is P1 and len(me.team) == 2  # the two in the request
    assert me.request.available_moves == ["icebeam", "hiddenpowerfighting", "triattack"]
    assert me.request.available_switches == [1] and not me.request.force_switch
    assert all(mon.known_set is not None for mon in me.team)
    assert first.state.opponent.request is None

    lead = second.state.me.active
    assert (lead.hp_current, lead.hp_max, lead.status) == (170, 267, Status.PARALYSIS)
    assert lead.revealed_moves == ["hiddenpower"]

    assert replacement.state.me.request.force_switch
    assert replacement.state.me.request.available_switches == [1]
    assert replacement.state.me.team[0].fainted and replacement.state.me.team[0].hp_current == 0

    # A `wait` request asks for nothing: the turn's snapshot carries no request.
    assert third.state.me.request is None and third.state.me.active_index == 1
    assert last.final and last.state.me.request is None


def test_a_spectator_log_is_unchanged_by_player_mode():
    record = parse_battle(load_battles(4)[0]["spectator"])
    assert record.player is None and record.request_disagreements == {}
    assert all(s.state.me.request is None for s in record.snapshots)
    assert all(mon.known_set is None for mon in record.snapshots[-1].state.me.team)


def test_the_request_is_checked_against_the_log_before_it_is_believed():
    record = parse_battle(battle(
        request((PORYGON_Z, {}), (AMBIPOM, {}), active={"moves": MOVES}),
        "|turn|2",
        request((PORYGON_Z, {"condition": "200/267", "item": ""}), (AMBIPOM, {}),
                active={"moves": MOVES}),
    ))
    assert record.request_disagreements == {"hp": 1, "item": 1}
    lead = record.snapshots[-1].state.me.active
    assert lead.hp_current == 200 and lead.item_consumed  # the request is taken over


# --------------------------------------------------------------------------- legal moves


def test_forced_choices_and_borrowed_moves_validate():
    recharge = {"moves": [{"move": "Recharge", "id": "recharge"}], "trapped": True}
    record = parse_battle(battle(request((PORYGON_Z, {}), (AMBIPOM, {}), active=recharge)))
    offered = record.snapshots[0].state.me.request
    assert offered.available_moves == ["recharge"] and offered.available_switches == []

    theirs = {"moves": [{"move": "Earthquake", "id": "earthquake", "pp": 5, "maxpp": 5}]}
    transformed = parse_battle(battle(
        request((PORYGON_Z, {}), (AMBIPOM, {}), active={"moves": MOVES}),
        "|-transform|p1a: Porygon-Z|p2a: Swampert",
        "|turn|2",
        request((PORYGON_Z, {}), (AMBIPOM, {}), active=theirs),
    ))
    assert transformed.snapshots[-1].state.me.request.available_moves == ["earthquake"]

    with pytest.raises(ValidationError, match="not in known set"):
        parse_battle(battle(request((PORYGON_Z, {}), (AMBIPOM, {}), active=theirs)))


# --------------------------------------------------------------------------- ground truth


@pytest.mark.slow
@pytest.mark.parametrize("gen", GENS)
def test_player_mode_matches_the_simulator(gen):
    """Our sets are the true ones, no request contradicts the log, and the opponent looks
    exactly as it does to a spectator. The 500-battle run per generation is on demand:
    `node build_battles.mjs 500 DIR 500`, then pass DIR to the validation."""
    report = validate_player(gen)
    assert report.battles == 2 and report.own_pokemon == 12 and report.decisions > 50
    assert report.violations == []
    assert report.disagreements == {}
