"""Math layer unit tests: everything the oracle fixture cannot check (see test_calc_golden)."""

import itertools
import math
import statistics
from time import perf_counter

import pytest
from calc_helpers import DEX4, battler

from poketrix.calc import (
    apply_stage,
    build_report,
    compute_stats,
    effectiveness,
    engine_for,
    evaluate_move,
    hidden_power,
    ko_chances,
)
from poketrix.calc.context import build_context
from poketrix.calc.gen4.power import POWER_RULES
from poketrix.calc.power_rules import resolve_power
from poketrix.dex import Dex
from poketrix.schemas import (
    FieldState,
    Generation,
    PokemonType,
    SideCondition,
    Stat,
    SubsystemStatus,
)

T = PokemonType

# --------------------------------------------------------------------------- type chart


def test_gen1_type_chart_quirks():
    assert effectiveness(1, T.GHOST, [T.PSYCHIC]) == 0
    assert effectiveness(1, T.BUG, [T.POISON]) == 2
    assert effectiveness(1, T.POISON, [T.BUG]) == 2
    assert effectiveness(1, T.ICE, [T.FIRE]) == 1


@pytest.mark.parametrize("gen", [2, 3, 4])
def test_gen2_to_4_type_chart(gen):
    assert effectiveness(gen, T.GHOST, [T.STEEL]) == 0.5
    assert effectiveness(gen, T.DARK, [T.STEEL]) == 0.5
    assert effectiveness(gen, T.GHOST, [T.PSYCHIC]) == 2
    assert effectiveness(gen, T.BUG, [T.POISON]) == 0.5
    assert effectiveness(gen, T.ICE, [T.FIRE]) == 0.5


def test_dual_types_multiply_and_typeless_is_neutral():
    assert effectiveness(4, T.ICE, [T.DRAGON, T.GROUND]) == 4
    assert effectiveness(4, T.FIRE, [T.WATER, T.DRAGON]) == 0.25
    assert effectiveness(4, T.GROUND, [T.STEEL, T.FLYING]) == 0
    assert effectiveness(4, T.TYPELESS, [T.GHOST, T.STEEL]) == 1


# --------------------------------------------------------------------------- stats


def test_gen4_stats_with_nature_and_evs():
    garchomp = battler("garchomp", nature="jolly", evs={"atk": 252, "spe": 252, "hp": 4})
    stats = compute_stats(garchomp.known_set)
    assert [stats[s] for s in Stat] == [358, 359, 226, 176, 206, 333]


def test_stats_scale_with_level_and_ivs():
    lv50 = compute_stats(battler("garchomp", level=50, ivs={"atk": 0}).known_set)
    assert (lv50[Stat.HP], lv50[Stat.ATK], lv50[Stat.SPE]) == (183, 135, 122)


def test_shedinja_always_has_1_hp():
    assert compute_stats(battler("shedinja", evs={"hp": 252}).known_set)[Stat.HP] == 1


def test_unknown_nature_is_rejected():
    with pytest.raises(ValueError, match="unknown nature 'notanature'"):
        battler("garchomp", nature="notanature")


@pytest.mark.parametrize(
    ("stage", "expected"),
    [(0, 100), (1, 150), (2, 200), (6, 400), (-1, 66), (-2, 50), (-6, 25)],
)
def test_stat_stages(stage, expected):
    assert apply_stage(100, stage) == expected


# --------------------------------------------------------------------------- Hidden Power


@pytest.mark.parametrize(
    ("ivs", "expected"),
    [
        ({}, (T.DARK, 70)),
        ({"atk": 30, "def": 30}, (T.ICE, 70)),
        ({"atk": 30, "spa": 30, "spe": 30}, (T.FIRE, 70)),
        ({"atk": 30, "spa": 30}, (T.GRASS, 70)),
        ({s.value: 0 for s in Stat}, (T.FIGHTING, 30)),
    ],
)
def test_hidden_power_from_ivs(ivs, expected):
    assert hidden_power(4, {Stat(k): v for k, v in ivs.items()}) == expected


def test_engine_derives_hidden_power_from_listed_ivs():
    garchomp = battler("garchomp")
    ice_ivs = battler("zapdos", ivs={"atk": 30, "def": 30})
    plain = battler("zapdos")
    # Listed IVs win, whichever Hidden Power entry the set names.
    derived = evaluate_move(ice_ivs, garchomp, DEX4.move("hiddenpower"))
    typed = evaluate_move(plain, garchomp, DEX4.move("hiddenpowerice"))
    assert derived.damage.type_multiplier == typed.damage.type_multiplier == 4
    assert derived.damage.rolls[-1] <= typed.damage.rolls[-1]  # Def IV 30 costs nothing here
    mislabelled = evaluate_move(ice_ivs, garchomp, DEX4.move("hiddenpowerfire"))
    assert mislabelled.damage.type_multiplier == 4


def test_untyped_hidden_power_without_ivs_is_unsupported():
    result = evaluate_move(battler("zapdos"), battler("garchomp"), DEX4.move("hiddenpower"))
    assert result.damage is None and not result.ko
    assert "Hidden Power" in result.unsupported_reason


# --------------------------------------------------------------------------- fixed damage


def fixed(attacker, move, defender):
    return evaluate_move(attacker, defender, DEX4.move(move))


def test_super_fang_halves_current_hp_and_respects_immunity():
    assert fixed(battler("raticate"), "superfang", battler("blissey", hp=301)).damage.rolls == [150]
    assert fixed(battler("raticate"), "superfang", battler("blissey", hp=1)).damage.rolls == [1]
    assert fixed(battler("raticate"), "superfang", battler("gengar")).damage.rolls == [0]


def test_endeavor_brings_target_down_to_user_hp():
    low = battler("rattata", level=1, hp=1)
    assert fixed(low, "endeavor", battler("blissey", hp=500)).damage.rolls == [499]
    assert fixed(battler("blissey"), "endeavor", battler("rattata")).damage.rolls == [0]


def test_ohko_takes_all_hp_with_level_based_accuracy():
    blissey = battler("blissey", hp=400)
    hit = fixed(battler("lapras", level=100), "sheercold", battler("blissey", level=90, hp=400))
    assert hit.damage.rolls == [400] and hit.accuracy == pytest.approx(0.40)
    assert hit.ko[0].probability == pytest.approx(0.40)
    lower = fixed(battler("lapras", level=80), "sheercold", blissey)
    assert lower.damage.rolls == [0] and lower.accuracy == 0
    sturdy = battler("skarmory", ability="sturdy")
    assert fixed(battler("lapras"), "sheercold", sturdy).damage.rolls == [0]
    steelix = battler("steelix", ability="sturdy")
    mold_breaker = fixed(battler("rampardos", ability="moldbreaker"), "fissure", steelix)
    assert mold_breaker.damage.rolls == [steelix.hp_max]  # Mold Breaker ignores Sturdy


@pytest.mark.parametrize("move", ["counter", "mirrorcoat", "metalburst", "bide", "psywave"])
def test_fixed_damage_the_engine_cannot_know_is_unsupported(move):
    result = fixed(battler("blissey"), move, battler("swampert"))
    assert result.damage is None and result.unsupported_reason


@pytest.mark.parametrize("move", ["magnitude", "present", "trumpcard", "beatup", "triplekick"])
def test_moves_the_engine_cannot_evaluate_are_reported_not_guessed(move):
    result = fixed(battler("garchomp"), move, battler("swampert"))
    assert result.damage is None and not result.ko and result.unsupported_reason


def test_unmodelled_ability_is_reported_not_guessed():
    rivalry = battler("nidoking", ability="rivalry")
    result = fixed(rivalry, "earthquake", battler("swampert"))
    assert result.damage is None and "Rivalry" in result.unsupported_reason
    assert fixed(rivalry, "toxic", battler("swampert")).unsupported_reason is None  # status move


def test_status_move_has_accuracy_but_no_damage():
    result = fixed(battler("gengar"), "hypnosis", battler("swampert"))
    assert result.damage is None and result.unsupported_reason is None
    assert result.accuracy == pytest.approx(0.60)


# --------------------------------------------------------------------------- KO odds


def brute_force_ko(rolls, crit_rolls, crit_chance, hit_chance, hp, uses):
    """Enumerate every outcome of `uses` attacks."""
    outcomes = [(0, 1 - hit_chance)]
    outcomes += [(r, hit_chance * (1 - crit_chance) / len(rolls)) for r in rolls]
    if crit_rolls is not None:
        outcomes += [(r, hit_chance * crit_chance / len(crit_rolls)) for r in crit_rolls]
    total = 0.0
    for combo in itertools.product(outcomes, repeat=uses):
        if sum(damage for damage, _ in combo) >= hp:
            probability = 1.0
            for _, p in combo:
                probability *= p
            total += probability
    return total


@pytest.mark.parametrize(
    ("rolls", "crit_rolls", "crit_chance", "hit_chance", "hp"),
    [
        ([40, 42, 44, 47], [80, 84, 88, 94], 1 / 16, 1.0, 100),
        ([40, 42, 44, 47], [80, 84, 88, 94], 1 / 8, 0.8, 131),
        ([10, 10, 11, 12], [20, 21, 22, 24], 1 / 16, 0.9, 45),
        ([50], None, 0.0, 0.3, 120),
        ([0], None, 0.0, 1.0, 10),
    ],
)
def test_ko_odds_match_brute_force(rolls, crit_rolls, crit_chance, hit_chance, hp):
    chances = ko_chances(rolls, crit_rolls, crit_chance, hit_chance, hp, max_hits=3)
    assert [c.hits for c in chances] == [1, 2, 3]
    assert all(c.method == "exact" for c in chances)
    for c in chances:
        expected = brute_force_ko(rolls, crit_rolls, crit_chance, hit_chance, hp, c.hits)
        assert c.probability == pytest.approx(expected, abs=1e-12)


def test_ko_odds_on_a_real_matchup():
    # Garchomp Earthquake into 252/252 Relaxed Swampert: 127-150 normally, 255-300 on a crit.
    result = evaluate_move(
        battler("garchomp", nature="jolly", evs={"atk": 252, "spe": 252, "hp": 4}),
        battler("swampert", nature="relaxed", evs={"hp": 252, "def": 252}),
        DEX4.move("earthquake"),
    )
    assert (result.damage.rolls[0], result.damage.rolls[-1]) == (127, 150)
    assert result.damage.defender_max_hp == 404
    one, two, three, four = (c.probability for c in result.ko)
    assert [c.hits for c in result.ko] == [1, 2, 3, 4]
    assert one == 0  # even a max crit (300) leaves it standing
    assert 1 / 256 < two < 1 - (15 / 16) ** 2  # two crits always KO; one crit only sometimes
    damage = result.damage
    for uses, probability in ((2, two), (3, three)):
        expected = brute_force_ko(damage.rolls, damage.crit_rolls, 1 / 16, 1.0, 404, uses)
        assert probability == pytest.approx(expected, abs=1e-12)
    assert three < 1 and four == 1  # 3 x 127 = 381 < 404, 4 x 127 = 508


# --------------------------------------------------------------------------- accuracy
# Not in the oracle: these follow the Showdown simulator's Gen 4 rules (see calc/gen4/chance.py).


def accuracy(attacker, move, defender, **field):
    return evaluate_move(attacker, defender, DEX4.move(move), FieldState(**field)).accuracy


def test_accuracy_and_evasion_stages_are_applied_separately():
    target = battler("swampert")
    assert accuracy(battler("garchomp"), "stoneedge", target) == pytest.approx(0.8)
    evasive = battler("swampert", boosts={"evasion": 1})
    assert accuracy(battler("garchomp"), "stoneedge", evasive) == pytest.approx(0.6)
    assert accuracy(battler("garchomp", boosts={"accuracy": 6}), "stoneedge", target) == 1
    assert accuracy(battler("garchomp"), "aerialace", evasive) == 1  # never misses
    # +1 accuracy against +2 evasion: 80 x 4/3 x 3/5, not the combined stage -1 (x 3/4).
    mixed = accuracy(
        battler("garchomp", boosts={"accuracy": 1}), "stoneedge",
        battler("swampert", boosts={"evasion": 2}),
    )
    assert mixed == pytest.approx(0.64)


def test_abilities_that_change_accuracy():
    swampert = battler("swampert")
    butterfree = battler("butterfree", ability="compoundeyes")
    assert accuracy(butterfree, "sleeppowder", swampert) == pytest.approx(0.75 * 1.3)
    togekiss = battler("togekiss", ability="hustle")
    assert accuracy(togekiss, "skyattack", swampert) == pytest.approx(0.9 * 0.8)  # physical
    assert accuracy(togekiss, "airslash", swampert) == pytest.approx(0.95)  # special
    machamp = battler("machamp", ability="noguard")
    assert accuracy(machamp, "dynamicpunch", battler("swampert", boosts={"evasion": 6})) == 1
    assert accuracy(battler("garchomp"), "stoneedge", machamp) == 1  # No Guard works both ways
    confused = battler("pidgeot", ability="tangledfeet", volatiles=["confusion"])
    assert accuracy(battler("starmie"), "surf", confused) == pytest.approx(0.5)
    simple = battler("bibarel", ability="simple", boosts={"accuracy": -1})
    assert accuracy(simple, "surf", swampert) == pytest.approx(3 / 5)  # the drop counts double
    unaware = battler("bibarel", ability="unaware")
    assert accuracy(battler("garchomp", boosts={"accuracy": -6}), "earthquake", unaware) == 1


def test_weather_evasion_abilities():
    sand_veil = battler("garchomp", ability="sandveil")
    starmie = battler("starmie")
    assert accuracy(starmie, "surf", sand_veil) == 1
    assert accuracy(starmie, "surf", sand_veil, weather="sandstorm") == pytest.approx(0.8)
    snow_cloak = battler("froslass", ability="snowcloak")
    assert accuracy(starmie, "surf", snow_cloak, weather="hail") == pytest.approx(0.8)
    cloud_nine = battler("golduck", ability="cloudnine")
    assert accuracy(cloud_nine, "surf", sand_veil, weather="sandstorm") == 1
    mold_breaker = battler("rampardos", ability="moldbreaker")
    assert accuracy(mold_breaker, "surf", sand_veil, weather="sandstorm") == 1


def test_items_and_field_effects_that_change_accuracy():
    swampert = battler("swampert")
    assert accuracy(battler("garchomp", item="widelens"), "stoneedge", swampert) == pytest.approx(0.88)
    assert accuracy(battler("garchomp"), "stoneedge", battler("swampert", item="brightpowder")) == (
        pytest.approx(0.72)
    )
    assert accuracy(battler("garchomp"), "stoneedge", battler("swampert", item="laxincense")) == (
        pytest.approx(0.72)
    )
    # Zoom Lens only helps the Pokémon that moves second.
    assert accuracy(battler("tyranitar", item="zoomlens"), "stoneedge", battler("starmie")) == (
        pytest.approx(0.96)
    )
    assert accuracy(battler("starmie", item="zoomlens"), "hydropump", battler("tyranitar")) == (
        pytest.approx(0.8)
    )
    assert accuracy(battler("magnezone"), "zapcannon", swampert, gravity_turns_left=3) == (
        pytest.approx(0.5 * 5 / 3)
    )
    foreseen = battler("swampert", boosts={"evasion": 3}, volatiles=["foresight"])
    assert accuracy(battler("garchomp"), "stoneedge", foreseen) == pytest.approx(0.8)


def test_ohko_accuracy_ignores_stages_but_not_no_guard():
    evasive = battler("blissey", level=90, boosts={"evasion": 6})
    assert accuracy(battler("lapras"), "sheercold", evasive) == pytest.approx(0.40)
    assert accuracy(battler("machamp", ability="noguard"), "fissure", evasive) == 1


# --------------------------------------------------------------------------- critical hits


def crit_chance(attacker, move, defender=None):
    outcome = engine_for(4).evaluate(
        attacker, defender or battler("blissey"), DEX4.move(move), FieldState()
    )
    return outcome.damage.crit_chance


def test_crit_stage_adds_move_ability_item_and_focus_energy():
    assert crit_chance(battler("garchomp"), "earthquake") == 1 / 16
    assert crit_chance(battler("garchomp"), "stoneedge") == 1 / 8
    assert crit_chance(battler("garchomp", item="scopelens"), "stoneedge") == 1 / 4
    assert crit_chance(battler("garchomp", item="razorclaw"), "earthquake") == 1 / 8
    absol = battler("absol", ability="superluck", item="scopelens")
    assert crit_chance(absol, "nightslash") == 1 / 3
    assert crit_chance(battler("garchomp", volatiles=["focusenergy"]), "earthquake") == 1 / 4
    assert crit_chance(battler("farfetchd", item="stick"), "slash") == 1 / 3
    assert crit_chance(battler("chansey", item="luckypunch"), "return") == 1 / 4
    assert crit_chance(battler("garchomp", item="luckypunch"), "earthquake") == 1 / 16
    stacked = battler("absol", ability="superluck", item="scopelens", volatiles=["focusenergy"])
    assert crit_chance(stacked, "nightslash") == 1 / 2  # capped


def test_battle_armor_blocks_crits_unless_mold_breaker():
    armored = battler("drapion", ability="battlearmor")
    blocked = engine_for(4).evaluate(battler("garchomp"), armored, DEX4.move("earthquake"), FieldState())
    assert blocked.damage.crit_rolls is None and blocked.damage.crit_chance == 0
    assert crit_chance(battler("rampardos", ability="moldbreaker"), "earthquake", armored) == 1 / 16


# --------------------------------------------------------------------------- simulator-rule moves


def power_of(attacker, move, defender, field=None, attacker_conditions=None):
    context = build_context(
        attacker, defender, DEX4.move(move), field or FieldState(), attacker_conditions or {}, {}
    )
    return resolve_power(context, POWER_RULES)


def test_gyro_ball_follows_the_simulator_and_adds_one():
    bronzong, starmie = battler("bronzong"), battler("starmie")  # Speed 102 and 266
    assert power_of(bronzong, "gyroball", starmie) == 25 * 266 // 102 + 1 == 66
    assert power_of(bronzong, "gyroball", battler("bronzong")) == 26  # the oracle says 25
    slowest = battler("bronzong", nature="brave", ivs={"spe": 0}, boosts={"spe": -6})
    assert power_of(slowest, "gyroball", starmie) == 150  # capped
    scarfed = battler("bronzong", item="choicescarf")  # Speed 153
    assert power_of(scarfed, "gyroball", starmie) == 25 * 266 // 153 + 1


def test_punishment_counts_accuracy_and_evasion_boosts():
    weavile = battler("weavile")
    boosted = battler("swampert", boosts={"atk": 2, "evasion": 1, "spe": -3})
    assert power_of(weavile, "punishment", boosted) == 120  # the oracle says 100
    maxed = battler("swampert", boosts={"atk": 6, "def": 6})
    assert power_of(weavile, "punishment", maxed) == 200  # capped


def test_payback_doubles_when_moving_second():
    weavile, swampert = battler("weavile"), battler("swampert")
    assert power_of(weavile, "payback", swampert) == 50
    assert power_of(swampert, "payback", weavile) == 100
    trick_room = FieldState(trick_room_turns_left=3)
    assert power_of(weavile, "payback", swampert, trick_room) == 100
    assert power_of(swampert, "payback", weavile, trick_room) == 50
    tailwind = {SideCondition.TAILWIND: 2}
    assert power_of(swampert, "payback", weavile, attacker_conditions=tailwind) == 50


# --------------------------------------------------------------------------- multi-hit moves


def test_hit_distribution_of_multi_hit_moves():
    garchomp = battler("garchomp")
    spear = evaluate_move(battler("cloyster", ability="shellarmor"), garchomp, DEX4.move("iciclespear"))
    assert spear.damage.hit_distribution == {2: 3 / 8, 3: 3 / 8, 4: 1 / 8, 5: 1 / 8}
    skill_link = evaluate_move(battler("cloyster", ability="skilllink"), garchomp, DEX4.move("iciclespear"))
    assert skill_link.damage.hit_distribution == {5: 1.0}
    assert skill_link.damage.rolls == spear.damage.rolls  # the rolls are per hit
    assert skill_link.damage.max_pct == pytest.approx(5 * 100 * spear.damage.rolls[-1] / garchomp.hp_max)
    assert spear.damage.min_pct == pytest.approx(2 * 100 * spear.damage.rolls[0] / garchomp.hp_max)
    double_kick = evaluate_move(battler("hitmonlee"), garchomp, DEX4.move("doublekick"))
    assert double_kick.damage.hit_distribution == {2: 1.0}
    assert evaluate_move(battler("garchomp"), garchomp, DEX4.move("earthquake")).damage.hit_distribution is None


def brute_force_multi_hit_ko(rolls, crit_rolls, crit_chance, hit_chance, hits_per_use, hp, uses):
    """Enumerate hit counts and every hit's outcome for `uses` attacks."""
    one_hit = [(r, (1 - crit_chance) / len(rolls)) for r in rolls]
    one_hit += [(r, crit_chance / len(crit_rolls)) for r in crit_rolls]
    one_use = [(0, 1 - hit_chance)]
    for hits, p_hits in hits_per_use.items():
        for combo in itertools.product(one_hit, repeat=hits):
            probability = hit_chance * p_hits
            for _, p in combo:
                probability *= p
            one_use.append((sum(damage for damage, _ in combo), probability))
    knockouts = []
    for combo in itertools.product(one_use, repeat=uses):
        if sum(damage for damage, _ in combo) >= hp:
            knockouts.append(math.prod(p for _, p in combo))
    return math.fsum(knockouts)


@pytest.mark.parametrize("hp", [20, 33, 45, 70, 110])
def test_multi_hit_ko_odds_match_brute_force(hp):
    rolls, crit_rolls, hits_per_use = [10, 12], [21], {2: 0.6, 3: 0.4}
    chances = ko_chances(rolls, crit_rolls, 1 / 8, 0.9, hp, max_hits=3, hit_distribution=hits_per_use)
    for c in chances:
        expected = brute_force_multi_hit_ko(rolls, crit_rolls, 1 / 8, 0.9, hits_per_use, hp, c.hits)
        assert c.probability == pytest.approx(expected, abs=1e-12)


# --------------------------------------------------------------------------- held items


def test_consumed_item_no_longer_counts():
    swampert, earthquake = battler("swampert"), DEX4.move("earthquake")
    banded = battler("garchomp", item="choiceband")
    plain = evaluate_move(battler("garchomp"), swampert, earthquake).damage.rolls
    assert evaluate_move(banded, swampert, earthquake).damage.rolls != plain
    knocked_off = banded.model_copy(update={"item_consumed": True})
    assert evaluate_move(knocked_off, swampert, earthquake).damage.rolls == plain


def test_revealed_item_is_used_when_the_set_names_none():
    swampert, earthquake = battler("swampert"), DEX4.move("earthquake")
    revealed = battler("garchomp").model_copy(update={"revealed_item": "choiceband"})
    banded = evaluate_move(battler("garchomp", item="choiceband"), swampert, earthquake)
    assert evaluate_move(revealed, swampert, earthquake).damage.rolls == banded.damage.rolls


def test_unknown_item_is_an_error_result_not_a_guess():
    odd = battler("garchomp").model_copy(update={"revealed_item": "notanitem"})
    result = build_report(odd, battler("swampert"), [DEX4.move("earthquake")])
    assert result.status is SubsystemStatus.ERROR and "unknown item 'notanitem'" in result.error


# --------------------------------------------------------------------------- inputs and report


def test_opponent_without_exact_hp_uses_the_displayed_fraction():
    full = battler("swampert")
    seen = full.model_copy(update={"hp_fraction": 0.25, "hp_current": None, "hp_max": None})
    result = evaluate_move(battler("garchomp"), seen, DEX4.move("earthquake"))
    assert result.ko[0].probability == 1  # 25% of 341 HP = 85


def test_fainted_defender_gets_no_ko_odds():
    fainted = battler("swampert", hp=0)
    assert evaluate_move(battler("garchomp"), fainted, DEX4.move("earthquake")).ko == []


def test_calculator_needs_a_known_set_and_one_generation():
    garchomp, swampert = battler("garchomp"), battler("swampert")
    unknown = swampert.model_copy(update={"known_set": None})
    with pytest.raises(ValueError, match="known_set"):
        evaluate_move(garchomp, unknown, DEX4.move("earthquake"))
    with pytest.raises(ValueError, match="same generation"):
        evaluate_move(garchomp, swampert, Dex(3).move("earthquake"))


def test_build_report_covers_both_directions():
    garchomp = battler("garchomp", nature="jolly", evs={"atk": 252, "spe": 252})
    starmie = battler("starmie", ability="naturalcure", nature="timid", evs={"spa": 252})
    result = build_report(
        garchomp, starmie,
        our_moves=[DEX4.move(m) for m in ("earthquake", "outrage", "stoneedge", "swordsdance")],
        their_moves=[DEX4.move(m) for m in ("icebeam", "surf")],
        their_conditions={SideCondition.REFLECT: 5},
    )
    assert result.status is SubsystemStatus.OK and result.latency_ms >= 0
    report = result.payload
    assert [m.move_id for m in report.our_moves] == [
        "earthquake", "outrage", "stoneedge", "swordsdance",
    ]
    assert report.our_moves[3].damage is None  # status move
    assert report.threats[0].damage.type_multiplier == 4  # Ice Beam into Garchomp
    assert report.threats[0].damage.attacker_species == "starmie"
    unscreened = evaluate_move(garchomp, starmie, DEX4.move("earthquake"))
    assert report.our_moves[0].damage.rolls[-1] < unscreened.damage.rolls[-1]  # their Reflect
    assert report.our_moves[0].damage.crit_rolls == unscreened.damage.crit_rolls  # crits ignore it


def test_build_report_returns_an_error_result_instead_of_raising():
    unknown = battler("swampert").model_copy(update={"known_set": None})
    result = build_report(battler("garchomp"), unknown, [DEX4.move("earthquake")])
    assert result.status is SubsystemStatus.ERROR and result.payload is None
    assert "known_set" in result.error


def test_every_supported_generation_has_an_engine():
    assert [engine_for(gen).gen for gen in Generation] == list(Generation)
    with pytest.raises(ValueError):
        engine_for(5)


# --------------------------------------------------------------------------- latency


def test_four_moves_into_six_targets_under_5ms():
    garchomp = battler("garchomp", nature="jolly", evs={"atk": 252, "spe": 252})
    moves = [DEX4.move(m) for m in ("earthquake", "outrage", "stoneedge", "fireblast")]
    targets = [
        battler(name, evs={"hp": 252})
        for name in ("swampert", "skarmory", "blissey", "gengar", "tyranitar", "starmie")
    ]

    def one_report():
        started = perf_counter()
        for target in targets:
            result = build_report(garchomp, target, moves)
            assert result.status is SubsystemStatus.OK
        return (perf_counter() - started) * 1000

    one_report()  # warm the stat and type-chart caches
    # Best of three batches, so a burst of unrelated load on the machine does not fail the test.
    medians = [statistics.median(one_report() for _ in range(25)) for _ in range(3)]
    assert min(medians) < 5.0
