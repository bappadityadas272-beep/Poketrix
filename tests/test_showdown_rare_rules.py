"""Hand-written logs for what the simulated corpus rarely or never reaches.

R11: a transformed Pokémon stays marked on every snapshot. R13: every evidence rule that fired
fewer than 30 times in the 2,000 simulated battles (most of them never) is pinned here, so no
rule depends on chance for its test. The line shapes are the ones the simulator's source emits.
"""

import pytest
from test_showdown import P1, P2, active, evidence, play

from poketrix.showdown import parse_battle
from poketrix.showdown.validation import load_battles

# --------------------------------------------------------------------------- R11: Transform


def test_a_transformed_pokemon_is_marked_on_every_snapshot_until_it_leaves():
    """Later phases must not compute damage for a transformed Pokémon: the state still holds its
    own species and stats. The `transform` volatile is how they know."""
    log = """
|gametype|singles
|player|p1|Ash
|player|p2|Gary
|gen|1
|tier|[Gen 1] Random Battle
|teamsize|p1|6
|teamsize|p2|6
|start
|switch|p1a: Ditto|Ditto, L88|100/100
|switch|p2a: Tauros|Tauros, L68|100/100
|turn|1
|move|p1a: Ditto|Transform|p2a: Tauros
|-transform|p1a: Ditto|p2a: Tauros
|turn|2
|move|p1a: Ditto|Body Slam|p2a: Tauros
|-damage|p2a: Tauros|60/100
|turn|3
|switch|p1a: Mew|Mew, L65|100/100
|turn|4
"""
    snapshots = parse_battle(log, strict=True).snapshots
    ditto = [s.state.sides[P1].team[0] for s in snapshots]
    assert ["transform" in d.volatiles for d in ditto] == [False, True, True, False]
    assert all(d.species.id == "ditto" for d in ditto)  # still its own species: do not calculate
    assert snapshots[-1].evidence[0].evidence.revealed_moves == ["transform"]


# --------------------------------------------------------------------------- R13: called moves


def test_nature_power_calls_another_move():
    tracker = play("|move|p1a: Garchomp|Nature Power|p2a: Swampert",
                   "|move|p1a: Garchomp|Tri Attack|p2a: Swampert|[from] move: Nature Power")
    assert evidence(tracker).revealed_moves == ["naturepower"]
    assert tracker.rules["move not revealed: called by naturepower"] == 1


def test_mirror_move_in_the_gen1_spelling():
    tracker = play("|move|p1a: Pidgeot|Mirror Move|p2a: Tauros",
                   "|move|p1a: Pidgeot|Body Slam|p2a: Tauros|[from] Mirror Move",
                   gen=1, p1="Pidgeot, L74", p2="Tauros, L68")
    assert evidence(tracker).revealed_moves == ["mirrormove"]


# --------------------------------------------------------------------------- R13: items


def test_covet_and_switcheroo_reveal_the_other_pokemons_item():
    covet = play("|move|p1a: Garchomp|Covet|p2a: Swampert",
                 "|-enditem|p2a: Swampert|Leftovers|[silent]|[from] move: Covet|[of] p1a: Garchomp",
                 "|-item|p1a: Garchomp|Leftovers|[from] move: Covet|[of] p2a: Swampert")
    assert evidence(covet, P2).item == "leftovers" and evidence(covet, P1).item is None
    assert active(covet, P1).revealed_item == "leftovers" and active(covet, P2).item_consumed
    switcheroo = play("|move|p1a: Garchomp|Switcheroo|p2a: Swampert",
                      "|-item|p2a: Swampert|Choice Band|[from] move: Switcheroo",
                      "|-item|p1a: Garchomp|Leftovers|[from] move: Switcheroo")
    assert evidence(switcheroo, P1).item == "choiceband"
    assert evidence(switcheroo, P2).item == "leftovers"


def test_trick_from_a_pokemon_with_no_item_to_give():
    # The target loses its item and receives nothing, so its own item is only named as lost.
    tracker = play("|move|p1a: Garchomp|Trick|p2a: Swampert",
                   "|-enditem|p2a: Swampert|Leftovers|[silent]|[from] move: Trick",
                   "|-item|p1a: Garchomp|Leftovers|[from] move: Trick")
    assert evidence(tracker, P2).item == "leftovers" and evidence(tracker, P1).item is None
    assert active(tracker, P2).revealed_item is None
    assert active(tracker, P1).revealed_item == "leftovers"


def test_a_second_swap_says_nothing_about_a_set_that_was_already_swapped():
    tracker = play(
        "|move|p2a: Swampert|Trick|p1a: Garchomp",
        "|-item|p1a: Garchomp|Choice Scarf|[from] move: Trick",
        "|-item|p2a: Swampert|Leftovers|[from] move: Trick",
        "|switch|p2a: Blissey|Blissey, L80, F|100/100",
        "|turn|2",
        "|move|p1a: Garchomp|Trick|p2a: Blissey",
        "|-item|p2a: Blissey|Choice Scarf|[from] move: Trick",
        "|-item|p1a: Garchomp|Lum Berry|[from] move: Trick",
    )
    assert evidence(tracker, P1).item == "leftovers"  # unchanged by the second swap
    assert evidence(tracker, P2, 1).item == "lumberry"  # Blissey's own, seen as it left
    assert active(tracker, P1).revealed_item == "lumberry"
    assert tracker.anomalies == []


def test_trick_between_two_holders_of_the_same_item_leaves_both_holding_it():
    tracker = play("|move|p2a: Swampert|Trick|p1a: Garchomp",
                   "|-item|p1a: Garchomp|Leftovers|[from] move: Trick",
                   "|-item|p2a: Swampert|Leftovers|[from] move: Trick")
    assert active(tracker, P1).revealed_item == active(tracker, P2).revealed_item == "leftovers"
    assert evidence(tracker, P1).item == evidence(tracker, P2).item == "leftovers"


def test_frisk_in_both_line_shapes():
    gen4 = play("|-item||Leftovers|[from] ability: Frisk|[of] p1a: Banette", p1="Banette, L88, M")
    assert evidence(gen4, P2).item == "leftovers" and evidence(gen4, P1).ability == "frisk"
    named = play("|-item|p2a: Swampert|Leftovers|[from] ability: Frisk|[of] p1a: Banette",
                 p1="Banette, L88, M")
    assert evidence(named, P2).item == "leftovers" and evidence(named, P1).ability == "frisk"
    assert evidence(named, P1).item is None


def test_recycle_brings_the_same_item_back():
    tracker = play("|-enditem|p1a: Garchomp|Lum Berry|[eat]",
                   "|move|p1a: Garchomp|Recycle|p1a: Garchomp",
                   "|-item|p1a: Garchomp|Lum Berry|[from] move: Recycle")
    assert evidence(tracker).item == "lumberry"
    assert active(tracker).revealed_item == "lumberry" and not active(tracker).item_consumed


# --------------------------------------------------------------------------- R13: abilities


def test_role_play_skill_swap_and_gastro_acid_end_ability_evidence():
    role_play = play(
        "|-ability|p1a: Garchomp|Torrent|Sand Veil|[from] move: Role Play|[of] p2a: Swampert",
        "|-ability|p1a: Garchomp|Torrent",
    )
    assert evidence(role_play, P1).ability is None  # Torrent is copied, not its own
    assert active(role_play, P1).revealed_ability == "torrent"
    skill_swap = play(
        "|-activate|p1a: Garchomp|move: Skill Swap|Torrent|Sand Veil|[of] p2a: Swampert",
        "|-ability|p1a: Garchomp|Torrent", "|-ability|p2a: Swampert|Sand Veil",
    )
    assert evidence(skill_swap, P1).ability is None and evidence(skill_swap, P2).ability is None
    suppressed = play("|-endability|p2a: Swampert", "|-ability|p2a: Swampert|Torrent")
    assert evidence(suppressed, P2).ability is None
    known_first = play("|-ability|p2a: Swampert|Torrent", "|-endability|p2a: Swampert")
    assert evidence(known_first, P2).ability == "torrent"  # what was seen before still stands


def test_no_exclusions_after_an_ability_change():
    tracker = play("|-endability|p2a: Bronzong", "|move|p1a: Garchomp|Earthquake|p2a: Bronzong",
                   "|-damage|p2a: Bronzong|70/100", p2="Bronzong, L80")
    assert evidence(tracker, P2).ruled_out_abilities == frozenset()


@pytest.mark.parametrize(
    ("move", "target", "excluded"),
    [
        ("Flamethrower", "Heatran, L80, M", "flashfire"),
        ("Thunderbolt", "Electivire, L80, M", "motordrive"),
        ("Thunderbolt", "Lanturn, L80, M", "voltabsorb"),
        ("Surf", "Vaporeon, L80, M", "waterabsorb"),
        ("Earthquake", "Weezing, L80, M", "levitate"),
    ],
)
def test_n4_for_every_absorbing_ability(move, target, excluded):
    name = target.split(",")[0]
    tracker = play(f"|move|p1a: Garchomp|{move}|p2a: {name}", f"|-damage|p2a: {name}|70/100",
                   p2=target)
    # A species with a single possible ability would be contradicted by this log; the rule only
    # excludes what the species could otherwise have had, and here each one could.
    assert excluded in active(tracker, P2).species.possible_abilities
    assert evidence(tracker, P2).ruled_out_abilities == {excluded}
    assert tracker.rules["N4: damaged through an absorbing ability"] == 1


def test_rule_counts_are_reported_per_battle():
    record = parse_battle(load_battles(4)[0]["spectator"])
    assert record.rule_counts["item: named by a [from] tag"] > 0
    assert all(count > 0 for count in record.rule_counts.values())


# --------------------------------------------------------------------------- Gen 1 glitches


def test_gen1_desync_clause_move_is_not_the_pokemons_own():
    """Found in a simulated game: Nidoran-M "used" Seismic Toss, a move its side had selected
    for the Pokémon before it. The simulator announces the substitution with a hint."""
    tracker = play(
        "|move|p1a: Jigglypuff|Seismic Toss|p2a: Growlithe",
        "|switch|p1a: Nidoran-M|Nidoran-M, L88|100/100",
        "|turn|2",
        "|-hint|Desync Clause Mod activated!",
        "|-hint|In Gen 1, if both players would see the same Pokémon using different moves, ...",
        "|move|p1a: Nidoran-M|Body Slam|p2a: Growlithe",
        "|move|p1a: Nidoran-M|Thunderbolt|p2a: Growlithe",
        gen=1, p1="Jigglypuff, L88", p2="Growlithe, L88",
    )
    assert evidence(tracker, P1, 0).revealed_moves == ["seismictoss"]
    assert evidence(tracker, P1, 1).revealed_moves == ["thunderbolt"]  # the hint covers one move
    assert tracker.rules["move not revealed: Gen 1 Desync Clause"] == 1


def test_gen1_first_move_that_repeats_the_sides_last_move_reveals_nothing():
    lines = [
        "|move|p1a: Jigglypuff|Seismic Toss|p2a: Growlithe",
        "|switch|p1a: Nidoran-M|Nidoran-M, L88|100/100",
        "|turn|2",
        "|move|p1a: Nidoran-M|Seismic Toss|p2a: Growlithe",
        "|turn|3",
        "|move|p1a: Nidoran-M|Seismic Toss|p2a: Growlithe",
    ]
    gen1 = play(*lines[:4], gen=1, p1="Jigglypuff, L88", p2="Growlithe, L88")
    assert evidence(gen1, P1, 1).revealed_moves == []  # may be its side's carried-over choice
    again = play(*lines, gen=1, p1="Jigglypuff, L88", p2="Growlithe, L88")
    assert evidence(again, P1, 1).revealed_moves == ["seismictoss"]  # chosen a second time
    later = play(*lines[:4], gen=2, p1="Jigglypuff, L88", p2="Growlithe, L88")
    assert evidence(later, P1, 1).revealed_moves == ["seismictoss"]  # only Gen 1 has the glitch


def test_gen1_desync_hint_after_a_failed_counter_covers_no_later_move():
    tracker = play(
        "|move|p1a: Chansey|Counter|p2a: Growlithe",
        "|-hint|Desync Clause Mod activated!",
        "|-fail|p1a: Chansey",
        "|move|p2a: Growlithe|Body Slam|p1a: Chansey",
        gen=1, p1="Chansey, L68", p2="Growlithe, L88",
    )
    assert evidence(tracker, P2).revealed_moves == ["bodyslam"]
    assert tracker.rules["move not revealed: Gen 1 Desync Clause"] == 0
