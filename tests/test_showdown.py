"""Task 05, step 1: the Showdown battle-log parser in spectator mode.

Three layers: single protocol lines, the evidence rules (one small log per rule), and whole
simulated battles whose true teams are known (tests/fixtures/battles_gen*.json).
"""

from time import perf_counter

import pytest

from poketrix.schemas import (
    BoostStat,
    Generation,
    PlayerSlot,
    SetEvidence,
    SideCondition,
    Status,
    SubsystemStatus,
    Weather,
    move_matches,
    moves_fit,
)
from poketrix.showdown import BattleTracker, parse_battle, parse_line
from poketrix.showdown import events as ev
from poketrix.showdown.validation import load_battles, validate
from poketrix.uncloak import Uncloaker, load_prior

P1, P2 = PlayerSlot.P1, PlayerSlot.P2
GENS = list(Generation)


def play(*lines, gen=4, p1="Garchomp, L74, M", p2="Swampert, L80, M"):
    """A tracker that has read a battle start, both leads, and the given lines."""
    tracker = BattleTracker()
    header = [
        "|gametype|singles", "|player|p1|Ash", "|player|p2|Gary", f"|gen|{gen}",
        f"|tier|[Gen {gen}] Random Battle", "|teamsize|p1|6", "|teamsize|p2|6", "|start",
        f"|switch|p1a: {p1.split(',')[0]}|{p1}|100/100",
        f"|switch|p2a: {p2.split(',')[0]}|{p2}|100/100",
        "|turn|1",
    ]
    for line in [*header, *lines]:
        event = parse_line(line)
        if event is not None:
            tracker.apply(event)
    return tracker


def evidence(tracker, slot=P1, index=0) -> SetEvidence:
    return tracker.evidence()[(slot, index)]


def active(tracker, slot=P1):
    return tracker.state().sides[slot].active


# --------------------------------------------------------------------------- single lines


def test_pokemon_references_hp_and_details():
    switch = parse_line("|switch|p1a: Sparky|Raichu, L74, M|63/100 par")
    assert isinstance(switch, ev.SwitchEvent)
    assert (switch.pokemon.player, switch.pokemon.name, switch.pokemon.active) == (P1, "Sparky", True)
    assert (switch.species_name, switch.level, switch.forced) == ("Raichu", 74, False)
    assert (switch.hp.current, switch.hp.maximum, switch.hp.status) == (63, 100, Status.PARALYSIS)
    assert parse_line("|drag|p2a: Deoxys|Deoxys-Speed|100/100").level == 100  # no level shown
    assert parse_line("|drag|p2a: Deoxys|Deoxys-Speed|100/100").forced
    fainted = parse_line("|-damage|p2a: Swampert|0 fnt")
    assert fainted.hp.fainted and fainted.hp.fraction == 0
    exact = parse_line("|-damage|p1a: Garchomp|243/301")  # our own side in player mode
    assert exact.hp.fraction == pytest.approx(243 / 301)
    bench = parse_line("|-curestatus|p1: Garchomp|slp|[msg]")
    assert not bench.pokemon.active and bench.cured


def test_from_and_of_tags_in_both_spellings():
    gen4 = parse_line("|move|p1a: Registeel|Iron Head|p2a: Lugia|[from] move: Sleep Talk")
    gen2 = parse_line("|move|p2a: Piloswine|Ice Beam|p1a: Bellossom|[from] Sleep Talk")
    assert (gen4.source.kind, gen4.source.id) == ("move", "sleeptalk")
    assert (gen2.source.kind, gen2.source.id) == (None, "sleeptalk")
    assert gen4.move_id == "ironhead" and gen4.target.name == "Lugia"
    heal = parse_line("|-heal|p2a: Quagsire|43/100 tox|[from] ability: Water Absorb|[of] p1a: Blastoise")
    assert (heal.source.kind, heal.source.id, heal.of.name) == ("ability", "waterabsorb", "Blastoise")
    weather = parse_line("|-weather|RainDance|[upkeep]")
    assert weather.weather is Weather.RAIN and weather.upkeep
    assert not parse_line("|-weather|Sandstorm|[from] ability: Sand Stream|[of] p2a: Tyranitar").upkeep


def test_format_names_in_brackets_are_not_tags():
    tier = parse_line("|tier|[Gen 4] Random Battle")
    assert (tier.key, tier.value) == ("tier", "[Gen 4] Random Battle")


@pytest.mark.parametrize(
    "line",
    ["|", "|t:|1791660683", "|rule|Sleep Clause Mod: Limit one foe put to sleep", "|-crit|p1a: X",
     "|-supereffective|p2a: Y", "|c|~|hello|there", "|inactive|Time left: 120 sec", "not protocol",
     "|-miss|p1a: X|p2a: Y", "|upkeep|extra"][:9],
)
def test_lines_ignored_on_purpose(line):
    assert parse_line(line) is None


def test_unknown_message_type_is_counted_not_fatal():
    unknown = parse_line("|-futuremessage|p1a: X|whatever")
    assert isinstance(unknown, ev.UnknownEvent) and unknown.kind == "-futuremessage"
    tracker = play("|-futuremessage|p1a: Garchomp|x", "|-futuremessage|y")
    assert tracker.unknown == {"-futuremessage": 2}
    log = "|gen|4\n|tier|[Gen 4] Random Battle\n|-futuremessage|x"
    with pytest.raises(ValueError, match="unknown message types"):
        parse_battle(log, strict=True)


def test_only_singles_are_accepted():
    with pytest.raises(ValueError, match="singles"):
        BattleTracker().apply(parse_line("|gametype|doubles"))


# --------------------------------------------------------------------------- revealed moves


def test_a_chosen_move_is_revealed_once():
    tracker = play("|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|turn|2",
                   "|move|p1a: Garchomp|Earthquake|p2a: Swampert")
    assert evidence(tracker).revealed_moves == ["earthquake"]
    assert active(tracker).revealed_moves == ["earthquake"]


@pytest.mark.parametrize("tag", ["[from] move: Sleep Talk", "[from] Sleep Talk", "[from] move: Metronome",
                                 "[from] Mirror Move", "[from] move: Copycat", "[from] move: Assist",
                                 "[from] move: Me First", "[from] move: Magic Coat", "[from] move: Snatch"])
def test_a_called_move_is_not_revealed(tag):
    tracker = play(f"|move|p1a: Garchomp|Fire Blast|p2a: Swampert|{tag}")
    assert evidence(tracker).revealed_moves == []


def test_the_calling_move_itself_is_revealed():
    tracker = play("|move|p1a: Garchomp|Sleep Talk|p1a: Garchomp",
                   "|move|p1a: Garchomp|Outrage|p2a: Swampert|[from] move: Sleep Talk")
    assert evidence(tracker).revealed_moves == ["sleeptalk"]


def test_continuing_its_own_move_counts_as_chosen():
    tracker = play("|move|p1a: Garchomp|Outrage|p2a: Swampert", "|turn|2",
                   "|move|p1a: Garchomp|Outrage|p2a: Swampert|[from] lockedmove", "|turn|3",
                   "|move|p1a: Garchomp|Sky Attack|p2a: Swampert|[from] Sky Attack")
    assert evidence(tracker).revealed_moves == ["outrage", "skyattack"]


def test_moves_used_while_transformed_are_not_its_own():
    tracker = play("|move|p1a: Ditto|Transform|p2a: Swampert", "|-transform|p1a: Ditto|p2a: Swampert",
                   "|turn|2", "|move|p1a: Ditto|Earthquake|p2a: Swampert", p1="Ditto, L90")
    assert evidence(tracker).revealed_moves == ["transform"]
    assert "transform" in active(tracker).volatiles


def test_a_mimicked_move_is_not_its_own_and_struggle_never_is():
    tracker = play("|move|p1a: Garchomp|Mimic|p2a: Swampert", "|-activate|p1a: Garchomp|move: Mimic|Surf",
                   "|turn|2", "|move|p1a: Garchomp|Surf|p2a: Swampert", "|turn|3",
                   "|move|p1a: Garchomp|Struggle|p2a: Swampert")
    assert evidence(tracker).revealed_moves == ["mimic"]
    gen1 = play("|-start|p1a: Clefable|Mimic|Surf", "|move|p1a: Clefable|Surf|p2a: Tauros",
                gen=1, p1="Clefable, L74", p2="Tauros, L68")
    assert evidence(gen1).revealed_moves == []


def test_hidden_power_is_revealed_without_its_type():
    tracker = play("|move|p1a: Garchomp|Hidden Power|p2a: Swampert")
    assert evidence(tracker).revealed_moves == ["hiddenpower"]


def test_untyped_hidden_power_matches_any_typed_one():
    assert move_matches("hiddenpower", "hiddenpowerice")
    assert not move_matches("hiddenpowerice", "hiddenpower") and not move_matches("hiddenpower", "surf")
    assert moves_fit(["hiddenpower", "surf"], ["surf", "hiddenpowerfire", "rest", "toxic"])
    assert not moves_fit(["hiddenpower"], ["surf", "rest"])
    # In the uncloaker: sets with any Hidden Power survive, the others are ruled out.
    prior = load_prior(4)
    species = next(
        row.pokemon_set.species.id for row in prior.all_sets()
        if any(m.startswith("hiddenpower") for m in row.pokemon_set.moves)
    )
    result = Uncloaker(prior).uncloak(species, SetEvidence(revealed_moves=["hiddenpower"]))
    assert result.status is SubsystemStatus.OK
    posterior = result.payload
    assert posterior.move_probability("hiddenpower") == pytest.approx(1)
    for hypothesis in posterior.hypotheses:
        has_one = any(m.startswith("hiddenpower") for m in hypothesis.moves)
        assert (hypothesis.posterior > 0) == has_one


# --------------------------------------------------------------------------- items


def test_item_revealed_by_recovery_recoil_status_and_loss():
    leftovers = play("|-heal|p1a: Garchomp|56/100|[from] item: Leftovers")
    assert evidence(leftovers).item == "leftovers" and active(leftovers).revealed_item == "leftovers"
    orb = play("|-damage|p1a: Garchomp|90/100|[from] item: Life Orb")
    assert evidence(orb).item == "lifeorb"
    toxic_orb = play("|-status|p1a: Garchomp|tox|[from] item: Toxic Orb")
    assert evidence(toxic_orb).item == "toxicorb"
    eaten = play("|-enditem|p1a: Garchomp|Lum Berry|[eat]")
    assert evidence(eaten).item == "lumberry"
    mon = active(eaten)
    assert mon.revealed_item is None and mon.item_consumed  # known, but no longer held
    knocked = play("|-enditem|p1a: Garchomp|Choice Scarf|[from] move: Knock Off|[of] p2a: Swampert")
    assert evidence(knocked).item == "choicescarf"


def test_trick_swaps_what_they_hold_but_not_what_they_started_with():
    tracker = play(
        "|move|p2a: Swampert|Trick|p1a: Garchomp",
        "|-item|p1a: Garchomp|Choice Scarf|[from] move: Trick",
        "|-item|p2a: Swampert|Leftovers|[from] move: Trick",
        "|turn|2",
        "|-heal|p2a: Swampert|50/100|[from] item: Leftovers",  # Garchomp's old Leftovers at work
    )
    assert evidence(tracker, P1).item == "leftovers"  # what Garchomp started with
    assert evidence(tracker, P2).item == "choicescarf"
    assert active(tracker, P1).revealed_item == "choicescarf"  # what each holds now
    assert active(tracker, P2).revealed_item == "leftovers"


def test_thief_reveals_the_victims_item_only():
    tracker = play(
        "|move|p1a: Garchomp|Thief|p2a: Swampert",
        "|-item|p1a: Garchomp|Leftovers|[from] move: Thief|[of] p2a: Swampert",
        "|-heal|p1a: Garchomp|60/100|[from] item: Leftovers",
        "|turn|2", "|turn|3",
    )
    assert evidence(tracker, P2).item == "leftovers"
    assert evidence(tracker, P1).item is None  # the stolen item is not Garchomp's own
    assert active(tracker, P1).revealed_item == "leftovers" and active(tracker, P2).revealed_item is None
    assert evidence(tracker, P1).ruled_out_items == frozenset()  # nothing is concluded after a swap


# --------------------------------------------------------------------------- abilities


def test_ability_announced_or_tagged():
    announced = play("|-ability|p2a: Swampert|Pressure")
    assert evidence(announced, P2).ability == "pressure" and active(announced, P2).revealed_ability == "pressure"
    immune = play("|-immune|p1a: Garchomp|[from] ability: Levitate")
    assert evidence(immune).ability == "levitate"
    started = play("|-start|p1a: Garchomp|ability: Flash Fire")
    assert evidence(started).ability == "flashfire" and "flashfire" in active(started).volatiles


def test_of_names_the_owner_when_the_ability_acts_on_someone_else():
    static = play("|-status|p1a: Garchomp|par|[from] ability: Static|[of] p2a: Swampert")
    assert evidence(static, P2).ability == "static" and evidence(static, P1).ability is None
    weather = play("|-weather|Sandstorm|[from] ability: Sand Stream|[of] p2a: Swampert")
    assert evidence(weather, P2).ability == "sandstream"
    intimidate = play("|-unboost|p1a: Garchomp|atk|1|[from] ability: Intimidate|[of] p2a: Swampert")
    assert evidence(intimidate, P2).ability == "intimidate"
    rough_skin = play("|-damage|p1a: Garchomp|88/100|[from] ability: Rough Skin|[of] p2a: Swampert")
    assert evidence(rough_skin, P2).ability == "roughskin"


def test_on_a_heal_of_names_the_attacker_not_the_owner():
    tracker = play("|-heal|p2a: Swampert|80/100|[from] ability: Water Absorb|[of] p1a: Garchomp")
    assert evidence(tracker, P2).ability == "waterabsorb"
    assert evidence(tracker, P1).ability is None


def test_trace_reveals_both_abilities_once():
    tracker = play("|-ability|p1a: Garchomp|Torrent|[from] ability: Trace|[of] p2a: Swampert",
                   "|-ability|p1a: Garchomp|Torrent")
    assert evidence(tracker, P1).ability == "trace"  # what it started with
    assert evidence(tracker, P2).ability == "torrent"
    assert active(tracker, P1).revealed_ability == "torrent"  # what it has now


# --------------------------------------------------------------------------- ruled out


def test_n1_no_recovery_means_no_leftovers():
    hit = ["|move|p2a: Swampert|Surf|p1a: Garchomp", "|-damage|p1a: Garchomp|60/100"]
    tracker = play(*hit, "|upkeep", "|turn|2")
    assert evidence(tracker).ruled_out_items == {"leftovers", "blacksludge"}
    assert "leftovers" not in evidence(tracker, P2).ruled_out_items  # at full HP: no heal due
    # Already below full HP when the turn began: the same conclusion a turn later.
    later = play(*hit, "|-heal|p1a: Garchomp|66/100|[from] item: Leftovers", "|upkeep", "|turn|2",
                 "|upkeep", "|turn|3")
    assert evidence(later).item == "leftovers" and evidence(later).ruled_out_items == frozenset()


def test_n1_end_of_turn_damage_alone_proves_nothing():
    # Poison can act after the moment Leftovers would have: a full-HP holder is not healed.
    tracker = play("|-damage|p1a: Garchomp|88/100 psn|[from] psn", "|upkeep", "|turn|2")
    assert evidence(tracker).ruled_out_items == frozenset()


@pytest.mark.parametrize(
    "lines",
    [
        ["|-damage|p1a: Garchomp|60/100", "|-heal|p1a: Garchomp|66/100|[from] item: Leftovers"],
        ["|-damage|p1a: Garchomp|60/100", "|-heal|p1a: Garchomp|100/100|[from] move: Wish"],
        ["|-damage|p1a: Garchomp|60/100", "|-start|p1a: Garchomp|move: Heal Block"],
        ["|-damage|p1a: Garchomp|0 fnt", "|faint|p1a: Garchomp"],
    ],
)
def test_n1_exclusions(lines):
    tracker = play("|move|p2a: Swampert|Surf|p1a: Garchomp", *lines, "|upkeep", "|turn|2")
    assert "leftovers" not in evidence(tracker).ruled_out_items


def test_n1_does_not_apply_to_a_replacement_or_a_possible_klutz_or_gen1():
    replacement = play(
        "|faint|p1a: Garchomp", "|upkeep", "|switch|p1a: Blissey|Blissey, L80, F|40/100", "|turn|2"
    )
    assert evidence(replacement, P1, 1).ruled_out_items == frozenset()
    klutz = play("|move|p2a: Swampert|Surf|p1a: Lopunny", "|-damage|p1a: Lopunny|60/100",
                 "|upkeep", "|turn|2", p1="Lopunny, L88, F")
    assert evidence(klutz).ruled_out_items == frozenset()
    gen1 = play("|move|p2a: Snorlax|Body Slam|p1a: Tauros", "|-damage|p1a: Tauros|60/100",
                "|upkeep", "|turn|2", gen=1, p1="Tauros, L68", p2="Snorlax, L68")
    assert evidence(gen1).ruled_out_items == frozenset()


def test_n2_a_damaging_move_without_recoil_means_no_life_orb():
    tracker = play("|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|-damage|p2a: Swampert|55/100",
                   "|move|p2a: Swampert|Protect|p2a: Swampert")
    assert "lifeorb" in evidence(tracker).ruled_out_items
    assert "lifeorb" not in evidence(tracker, P2).ruled_out_items  # it used no damaging move


@pytest.mark.parametrize(
    "lines",
    [
        # the recoil came
        ["|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|-damage|p2a: Swampert|55/100",
         "|-damage|p1a: Garchomp|90/100|[from] item: Life Orb"],
        # the target lost no HP (a substitute took it)
        ["|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|-activate|p2a: Swampert|Substitute|[damage]"],
        # a status move
        ["|move|p1a: Garchomp|Swords Dance|p1a: Garchomp"],
        # a called move
        ["|move|p1a: Garchomp|Earthquake|p2a: Swampert|[from] move: Sleep Talk",
         "|-damage|p2a: Swampert|55/100"],
        # fixed damage
        ["|move|p1a: Garchomp|Seismic Toss|p2a: Swampert", "|-damage|p2a: Swampert|70/100"],
    ],
)
def test_n2_exclusions(lines):
    tracker = play(*lines, "|move|p2a: Swampert|Protect|p2a: Swampert")
    assert "lifeorb" not in evidence(tracker).ruled_out_items


def test_n2_is_gen4_only_and_skips_magic_guard_and_the_battles_last_hit():
    gen3 = play("|move|p1a: Salamence|Earthquake|p2a: Swampert", "|-damage|p2a: Swampert|55/100",
                "|upkeep", gen=3, p1="Salamence, L74, M")
    assert "lifeorb" not in evidence(gen3).ruled_out_items
    magic_guard = play("|move|p1a: Clefable|Return|p2a: Swampert", "|-damage|p2a: Swampert|80/100",
                       "|upkeep", p1="Clefable, L80, F")
    assert "lifeorb" not in evidence(magic_guard).ruled_out_items
    last_hit = play("|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|-damage|p2a: Swampert|0 fnt",
                    "|faint|p2a: Swampert", "|win|Ash")
    assert "lifeorb" not in evidence(last_hit).ruled_out_items


def test_n3_two_different_moves_in_one_stay_mean_no_choice_item():
    tracker = play("|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|turn|2",
                   "|move|p1a: Garchomp|Outrage|p2a: Swampert")
    assert {"choiceband", "choicespecs", "choicescarf"} <= evidence(tracker).ruled_out_items


def test_n3_needs_one_stay_and_chosen_moves():
    switched = play("|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|turn|2",
                    "|switch|p1a: Blissey|Blissey, L80, F|100/100", "|turn|3",
                    "|switch|p1a: Garchomp|Garchomp, L74, M|100/100", "|turn|4",
                    "|move|p1a: Garchomp|Outrage|p2a: Swampert")
    assert "choicescarf" not in evidence(switched).ruled_out_items
    called = play("|move|p1a: Garchomp|Sleep Talk|p1a: Garchomp",
                  "|move|p1a: Garchomp|Outrage|p2a: Swampert|[from] move: Sleep Talk")
    assert "choicescarf" not in evidence(called).ruled_out_items
    gen2 = play("|move|p1a: Snorlax|Body Slam|p2a: Suicune", "|turn|2",
                "|move|p1a: Snorlax|Earthquake|p2a: Suicune", gen=2, p1="Snorlax, L63", p2="Suicune, L65")
    assert evidence(gen2).ruled_out_items == frozenset()  # no Choice items in Gen 2


def test_n4_damage_from_an_absorbed_type_rules_the_ability_out():
    ground = play("|move|p1a: Garchomp|Earthquake|p2a: Bronzong", "|-damage|p2a: Bronzong|70/100",
                  p2="Bronzong, L80")
    assert evidence(ground, P2).ruled_out_abilities == {"levitate"}  # so it has Heatproof
    water = play("|move|p1a: Garchomp|Surf|p2a: Toxicroak", "|-damage|p2a: Toxicroak|40/100",
                 p2="Toxicroak, L80, M")
    assert evidence(water, P2).ruled_out_abilities == {"dryskin"}
    neutral = play("|move|p1a: Garchomp|Outrage|p2a: Bronzong", "|-damage|p2a: Bronzong|80/100",
                   p2="Bronzong, L80")
    assert evidence(neutral, P2).ruled_out_abilities == frozenset()


def test_n4_exclusions():
    mold_breaker = play("|move|p1a: Rampardos|Earthquake|p2a: Bronzong", "|-damage|p2a: Bronzong|70/100",
                        p1="Rampardos, L80, M", p2="Bronzong, L80")
    assert evidence(mold_breaker, P2).ruled_out_abilities == frozenset()
    gravity = play("|-fieldstart|move: Gravity", "|move|p1a: Garchomp|Earthquake|p2a: Bronzong",
                   "|-damage|p2a: Bronzong|70/100", p2="Bronzong, L80")
    assert evidence(gravity, P2).ruled_out_abilities == frozenset()
    hidden_power = play("|move|p1a: Garchomp|Hidden Power|p2a: Bronzong", "|-damage|p2a: Bronzong|90/100",
                        p2="Bronzong, L80")
    assert evidence(hidden_power, P2).ruled_out_abilities == frozenset()
    indirect = play("|move|p1a: Garchomp|Earthquake|p2a: Bronzong",
                    "|-damage|p2a: Bronzong|90/100|[from] Spikes", p2="Bronzong, L80")
    assert evidence(indirect, P2).ruled_out_abilities == frozenset()


def test_ruled_out_evidence_never_contradicts_what_was_seen():
    tracker = play("|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|-damage|p2a: Swampert|55/100",
                   "|-damage|p1a: Garchomp|90/100|[from] item: Life Orb", "|upkeep", "|turn|2")
    found = evidence(tracker)
    assert found.item == "lifeorb" and "lifeorb" not in found.ruled_out_items
    assert tracker.anomalies == []


# --------------------------------------------------------------------------- state tracking


def test_hp_status_boosts_and_fainting():
    tracker = play("|-damage|p2a: Swampert|63/100 par", "|-boost|p1a: Garchomp|atk|2",
                   "|-unboost|p2a: Swampert|def|1", "|-boost|p1a: Garchomp|atk|6")
    garchomp, swampert = active(tracker, P1), active(tracker, P2)
    assert swampert.hp_fraction == 0.63 and swampert.status is Status.PARALYSIS
    assert garchomp.boosts == {BoostStat.ATK: 6} and swampert.boosts == {BoostStat.DEF: -1}
    fainted = play("|-damage|p2a: Swampert|0 fnt", "|faint|p2a: Swampert")
    assert active(fainted, P2).fainted and active(fainted, P2).status is None


def test_switching_resets_boosts_and_volatiles_but_baton_pass_keeps_them():
    switched = play("|-boost|p1a: Garchomp|atk|2", "|-start|p1a: Garchomp|Substitute",
                    "|switch|p1a: Blissey|Blissey, L80, F|100/100")
    state = switched.state()
    assert state.sides[P1].active.species.id == "blissey" and state.sides[P1].active.boosts == {}
    assert state.sides[P1].team[0].boosts == {} and state.sides[P1].team[0].volatiles == set()
    assert [m.species.id for m in state.sides[P1].team] == ["garchomp", "blissey"]
    passed = play("|-boost|p1a: Garchomp|atk|2", "|-start|p1a: Garchomp|Substitute",
                  "|switch|p1a: Blissey|Blissey, L80, F|100/100|[from] Baton Pass")
    assert active(passed).boosts == {BoostStat.ATK: 2} and "substitute" in active(passed).volatiles


def test_haze_heal_bell_and_stat_swaps():
    haze = play("|-boost|p1a: Garchomp|atk|2", "|-unboost|p2a: Swampert|def|1", "|-clearallboost")
    assert active(haze, P1).boosts == {} and active(haze, P2).boosts == {}
    bell = play("|-status|p1a: Garchomp|par", "|switch|p1a: Blissey|Blissey, L80, F|100/100",
                "|-cureteam|p1a: Blissey|[from] move: Heal Bell")
    assert bell.state().sides[P1].team[0].status is None
    swap = play("|-boost|p1a: Garchomp|atk|2", "|-swapboost|p1a: Garchomp|p2a: Swampert|atk")
    assert active(swap, P2).boosts == {BoostStat.ATK: 2} and active(swap, P1).boosts == {}


def test_weather_field_and_side_conditions():
    tracker = play("|-weather|Sandstorm|[from] ability: Sand Stream|[of] p2a: Swampert",
                   "|-fieldstart|move: Trick Room", "|-sidestart|p1: Ash|Spikes",
                   "|-sidestart|p1: Ash|Spikes", "|-sidestart|p2: Gary|move: Stealth Rock",
                   "|-sidestart|p2: Gary|Reflect", "|turn|2", "|turn|3")
    state = tracker.state()
    assert state.field.weather is Weather.SANDSTORM and state.field.weather_turns_left is None
    assert state.field.trick_room_turns_left == 3  # started on turn 1, now turn 3
    assert state.sides[P1].conditions == {SideCondition.SPIKES: 2}
    assert state.sides[P2].conditions == {SideCondition.STEALTH_ROCK: 1, SideCondition.REFLECT: 3}
    ended = play("|-sidestart|p2: Gary|Reflect", "|-sideend|p2: Gary|Reflect", "|-weather|RainDance",
                 "|turn|2", "|-weather|none")
    assert ended.state().sides[P2].conditions == {} and ended.state().field.weather is Weather.NONE
    rain = play("|-weather|RainDance", "|turn|2", "|-weather|RainDance|[upkeep]", "|turn|3")
    assert rain.state().field.weather_turns_left == 3  # a move's weather: five turns in all


def test_gen1_reflect_sits_on_the_pokemon():
    tracker = play("|-start|p1a: Alakazam|Reflect", gen=1, p1="Alakazam, L68", p2="Tauros, L68")
    assert tracker.state().sides[P1].conditions == {SideCondition.REFLECT: 1}
    switched = play("|-start|p1a: Alakazam|Reflect", "|switch|p1a: Chansey|Chansey, L68|100/100",
                    gen=1, p1="Alakazam, L68", p2="Tauros, L68")
    assert switched.state().sides[P1].conditions == {}  # it left with the Pokémon


def test_forme_change_and_cosmetic_formes():
    castform = play("|-formechange|p1a: Castform|Castform-Rainy|[msg]|[from] ability: Forecast",
                    p1="Castform, L90, M")
    assert active(castform).species.id == "castformrainy"
    assert evidence(castform).ability == "forecast"
    assert castform.set_species_id(P1, 0) == "castform"  # its key in the set prior
    unown = play(gen=3, p1="Unown-Q, L100", p2="Swampert, L80, M")
    assert active(unown).species.id == "unown"


def test_snapshot_is_a_valid_game_state():
    tracker = play("|move|p1a: Garchomp|Earthquake|p2a: Swampert", "|-damage|p2a: Swampert|55/100",
                   "|upkeep", "|turn|2")
    state = tracker.state(perspective=P2)
    assert (state.generation, state.format_id, state.turn) == (Generation.DPP, "gen4randombattle", 2)
    assert state.me.player is P2 and state.me.name == "Gary" and state.opponent.name == "Ash"
    assert state.me.active.level == 80 and state.opponent.team_size == 6
    assert state.me.request is None and state.me.active.known_set is None  # spectator mode


# --------------------------------------------------------------------------- whole battles


@pytest.mark.parametrize("gen", GENS)
def test_evidence_is_sound_on_simulated_battles(gen):
    """The acceptance test: against the true teams, the parser never claims anything false."""
    report = validate(gen)
    assert report.violations == [] and report.anomalies == []
    assert report.unknown_message_types == {}
    assert report.battles == 10 and report.pokemon > 80
    assert report.revealed_moves > 200  # the rules do fire
    if gen >= Generation.GSC:
        assert report.items_identified > 50 and sum(report.ruled_out.values()) > 0
    if gen >= Generation.ADV:
        assert report.abilities_identified >= 10 and sum(report.ruled_out.values()) > 20


@pytest.mark.parametrize("gen", GENS)
def test_every_turn_has_a_valid_snapshot_and_the_end_agrees_with_the_log(gen):
    for battle in load_battles(gen):
        log = battle["spectator"]
        record = parse_battle(log, strict=True)
        turns = [s.turn for s in record.snapshots if not s.final]
        assert turns == list(range(1, len(turns) + 1))
        assert record.snapshots[-1].final and record.ended
        assert sum(len(s.events) for s in record.snapshots) > len(turns)
        last = record.snapshots[-1].state
        winner = next(side for side in last.sides.values() if side.name == record.winner)
        loser = next(side for side in last.sides.values() if side.name != record.winner)
        assert winner.active is not None and not winner.active.fainted
        assert sum(p.fainted for p in loser.team) == log.count(f"|faint|{loser.player.value}a: ")
        assert loser.alive_count == 0 or "forfeited" in log
        # Each snapshot carries the evidence of exactly the Pokémon revealed so far.
        for snapshot in record.snapshots:
            assert len(snapshot.evidence) == sum(len(s.team) for s in snapshot.state.sides.values())


@pytest.mark.parametrize("gen", GENS)
def test_parsed_evidence_keeps_the_true_set_alive_in_the_uncloaker(gen):
    """End to end: log -> evidence -> posterior. The prior is from the same generator, so the
    true set must almost always be a live hypothesis on the main path."""
    uncloaker, kept, total = Uncloaker(load_prior(gen)), 0, 0
    for battle in load_battles(gen):
        last = parse_battle(battle["spectator"]).snapshots[-1]
        for found in last.evidence:
            name = last.state.sides[found.player].team[found.team_index].species.name
            truth = next(
                m for m in battle["teams"][found.player.value]
                if found.species_id in (_key(m["species"]), _key(m["name"])) or _key(m["species"]).startswith(found.species_id)
            )
            result = uncloaker.uncloak(found.species_id, found.evidence)
            total += 1
            kept += result.status is SubsystemStatus.OK and any(
                h.posterior > 0 and set(h.moves) == set(truth["moves"])
                and h.item == truth["item"] and h.ability == truth["ability"]
                for h in result.payload.hypotheses
            )
            assert name  # the species resolved against the dex
    assert kept / total >= 0.995


def _key(text):
    return "".join(c for c in text.lower() if c.isalnum())


def test_parsing_is_fast():
    log = load_battles(4)[0]["spectator"]
    lines = sum(1 for line in log.splitlines() if line.startswith("|"))
    started = perf_counter()
    parse_battle(log)
    per_line_ms = (perf_counter() - started) * 1000 / lines
    assert per_line_ms < 1.0  # the ingest budget is 50 ms per turn
