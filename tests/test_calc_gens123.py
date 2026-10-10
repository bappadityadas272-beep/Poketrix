"""Gens 1-3: what the oracle fixtures cannot check (see test_calc_golden for the damage rolls).

Stats and stat stages, Hidden Power from DVs, and the accuracy, critical-hit and multi-hit rules,
which follow the Showdown simulator's per-generation code.
"""

import itertools
import math
import statistics
from time import perf_counter

import pytest
from calc_helpers import battler
from pydantic import ValidationError

from poketrix.calc import (
    apply_stage_classic,
    build_report,
    compute_stats,
    engine_for,
    evaluate_move,
    hidden_power,
    ko_chances,
)
from poketrix.dex import Dex
from poketrix.schemas import (
    DamageRange,
    FieldState,
    Generation,
    PokemonType,
    Stat,
    SubsystemStatus,
)

T = PokemonType
DEX = {gen: Dex(gen) for gen in Generation}


def mon(gen, species, **kwargs):
    return battler(species, gen_dex=DEX[gen], **kwargs)


def evaluate(gen, attacker, move, defender, **field):
    return evaluate_move(attacker, defender, DEX[gen].move(move), FieldState(**field))


def crit_chance(gen, attacker, move, defender=None):
    target = defender or mon(gen, "snorlax")
    outcome = engine_for(gen).evaluate(attacker, target, DEX[gen].move(move), FieldState())
    return outcome.damage.crit_chance


# --------------------------------------------------------------------------- Gens 1-2 stats


def test_gen1_stats_from_max_dvs_and_stat_exp():
    stats = compute_stats(mon(1, "tauros").known_set)
    assert [stats[s] for s in Stat] == [353, 298, 288, 238, 238, 318]


def test_gen2_splits_special_but_keeps_one_special_dv():
    stats = compute_stats(mon(2, "alakazam").known_set)
    assert (stats[Stat.SPA], stats[Stat.SPD]) == (368, 268)


def test_hp_dv_is_derived_from_the_other_dvs():
    # Attack DV 14 is even, so the HP DV loses its 8: HP DV 7 instead of 15.
    lower = compute_stats(mon(1, "tauros", ivs={"atk": 14}).known_set)
    assert lower[Stat.HP] == 353 - 16 and lower[Stat.ATK] == 298 - 2


def test_stat_exp_bonus_is_the_capped_square_root():
    def attack(stat_exp):
        return compute_stats(mon(1, "tauros", evs={"atk": stat_exp}).known_set)[Stat.ATK]

    assert attack(0) == 235  # (100 + 15) x 2 + 5
    assert attack(65535) == attack(65025) == 298  # the square root is capped at 255
    assert attack(100) == 235 + 2  # ceil(sqrt(100)) // 4
    assert attack(101) == 235 + 2  # ceil(sqrt(101)) = 11


@pytest.mark.parametrize(
    ("stat", "stage", "expected"),
    [(100, 0, 100), (100, 1, 150), (100, 6, 400), (100, -1, 66), (100, -6, 25),
     (300, 6, 999), (2, -6, 1)],
)
def test_classic_stat_stages_stay_between_1_and_999(stat, stage, expected):
    assert apply_stage_classic(stat, stage) == expected


# --------------------------------------------------------------------------- Hidden Power


@pytest.mark.parametrize(
    ("dvs", "expected"),
    [
        ({}, (T.DARK, 70)),
        ({"atk": 15, "def": 13}, (T.ICE, 70)),
        ({"atk": 14, "def": 12}, (T.FIRE, 70)),
        ({"atk": 0, "def": 0, "spe": 0, "spa": 0, "spd": 0}, (T.FIGHTING, 31)),
    ],
)
def test_gen2_hidden_power_from_dvs(dvs, expected):
    assert hidden_power(2, {Stat(k): v for k, v in dvs.items()}) == expected


def test_hidden_power_does_not_exist_in_gen1():
    with pytest.raises(ValueError, match="Gen 1"):
        hidden_power(1, {})


def test_gen2_engine_derives_hidden_power_and_its_category():
    dragonite = mon(2, "dragonite")
    ice = evaluate(2, mon(2, "zapdos", ivs={"atk": 15, "def": 13}), "hiddenpower", dragonite)
    typed = evaluate(2, mon(2, "zapdos"), "hiddenpowerice", dragonite)
    assert ice.damage.type_multiplier == typed.damage.type_multiplier == 4
    # DV 13 changes Zapdos's HP (derived DV) but not its Special Attack: same rolls.
    assert ice.damage.rolls == typed.damage.rolls


def test_gen3_derived_hidden_power_uses_its_types_category():
    # IVs for Hidden Power Fighting (physical in Gen 3) on a special attacker.
    alakazam = mon(3, "alakazam", ivs={"def": 30, "spa": 30, "spd": 30, "spe": 30})
    assert hidden_power(3, alakazam.known_set.spread.ivs)[0] is T.FIGHTING
    derived = evaluate(3, alakazam, "hiddenpower", mon(3, "snorlax", ability="immunity"))
    typed = evaluate(3, alakazam, "hiddenpowerfighting", mon(3, "snorlax", ability="immunity"))
    assert derived.damage.rolls == typed.damage.rolls  # Attack, not Special Attack


# --------------------------------------------------------------------------- Gen 1 odds


def test_gen1_accuracy_is_out_of_256():
    tauros, snorlax = mon(1, "tauros"), mon(1, "snorlax")
    assert evaluate(1, tauros, "bodyslam", snorlax).accuracy == 255 / 256
    assert evaluate(1, tauros, "hyperbeam", snorlax).accuracy == 229 / 256  # 90%
    assert evaluate(1, tauros, "swift", snorlax).accuracy == 1  # never misses
    evasive = mon(1, "snorlax", boosts={"evasion": 1})
    assert evaluate(1, tauros, "bodyslam", evasive).accuracy == 168 / 256  # x 66/100
    sharp = mon(1, "tauros", boosts={"accuracy": 6})
    assert evaluate(1, sharp, "hyperbeam", snorlax).accuracy == 255 / 256  # capped


def test_gen1_crit_rate_comes_from_base_speed():
    assert crit_chance(1, mon(1, "tauros"), "bodyslam") == 55 / 256  # base Speed 110
    assert crit_chance(1, mon(1, "snorlax"), "bodyslam", mon(1, "tauros")) == 15 / 256  # base 30
    assert crit_chance(1, mon(1, "persian"), "slash") == 255 / 256  # high-crit move, capped
    focused = mon(1, "tauros", volatiles=["focusenergy"])
    assert crit_chance(1, focused, "bodyslam") == 13 / 256  # the Focus Energy bug lowers it


def test_gen1_high_crit_move_still_has_separate_normal_rolls():
    result = evaluate(1, mon(1, "persian"), "slash", mon(1, "snorlax"))
    assert result.damage.crit_rolls[0] > result.damage.rolls[-1]


def test_gen1_ohko_needs_at_least_equal_speed():
    tauros, rhydon = mon(1, "tauros"), mon(1, "rhydon")
    hit = evaluate(1, tauros, "horndrill", rhydon)
    assert hit.damage.rolls == [rhydon.hp_max] and hit.accuracy == 76 / 256
    miss = evaluate(1, rhydon, "horndrill", tauros)
    assert miss.damage.rolls == [0] and miss.accuracy == 0
    paralysed = mon(1, "tauros", status="par")  # Speed is quartered
    assert evaluate(1, rhydon, "horndrill", paralysed).damage.rolls == [paralysed.hp_max]


def test_gen1_fixed_damage_ignores_immunity_but_ohko_does_not():
    chansey, gengar = mon(1, "chansey"), mon(1, "gengar")
    toss = evaluate(1, chansey, "seismictoss", gengar)
    assert toss.damage.rolls == [100] and toss.damage.type_multiplier == 1
    assert evaluate(1, mon(1, "raticate"), "superfang", gengar).damage.rolls == [gengar.hp_max // 2]
    assert evaluate(1, mon(1, "tauros"), "horndrill", gengar).damage.rolls == [0]  # Normal vs Ghost


def test_gen1_multi_hit_repeats_one_roll():
    result = evaluate(1, mon(1, "jolteon"), "pinmissile", mon(1, "exeggutor"))
    assert result.damage.hits_share_roll
    assert result.damage.hit_distribution == {2: 3 / 8, 3: 3 / 8, 4: 1 / 8, 5: 1 / 8}
    assert evaluate(1, mon(1, "jolteon"), "doublekick", mon(1, "snorlax")).damage.hits_share_roll
    assert not evaluate(1, mon(1, "tauros"), "bodyslam", mon(1, "snorlax")).damage.hits_share_roll
    assert not evaluate(2, mon(2, "beedrill"), "pinmissile", mon(2, "exeggutor")).damage.hits_share_roll


def brute_force_shared_roll_ko(rolls, crit_rolls, crit_chance, hit_chance, hits_per_use, hp, uses):
    """Each use: miss, or one roll (normal or critical) repeated for every hit."""
    one_use = [(0, 1 - hit_chance)]
    for hits, p_hits in hits_per_use.items():
        one_use += [(hits * r, hit_chance * p_hits * (1 - crit_chance) / len(rolls)) for r in rolls]
        one_use += [(hits * r, hit_chance * p_hits * crit_chance / len(crit_rolls)) for r in crit_rolls]
    knockouts = [
        math.prod(p for _, p in combo)
        for combo in itertools.product(one_use, repeat=uses)
        if sum(damage for damage, _ in combo) >= hp
    ]
    return math.fsum(knockouts)


@pytest.mark.parametrize("hp", [20, 33, 47, 70, 110])
def test_shared_roll_ko_odds_match_brute_force(hp):
    rolls, crit_rolls = [10, 11, 12], [19, 23]
    hits_per_use = {2: 3 / 8, 3: 3 / 8, 4: 1 / 8, 5: 1 / 8}
    chances = ko_chances(
        rolls, crit_rolls, 55 / 256, 0.9, hp, max_hits=3,
        hit_distribution=hits_per_use, hits_share_roll=True,
    )
    for c in chances:
        expected = brute_force_shared_roll_ko(rolls, crit_rolls, 55 / 256, 0.9, hits_per_use, hp, c.hits)
        assert c.probability == pytest.approx(expected, abs=1e-12)


def test_shared_roll_differs_from_independent_hits():
    kwargs = {"hit_distribution": {2: 1.0}, "max_hits": 1}
    shared = ko_chances([10, 20], None, 0.0, 1.0, 30, hits_share_roll=True, **kwargs)
    independent = ko_chances([10, 20], None, 0.0, 1.0, 30, **kwargs)
    assert shared[0].probability == 0.5  # 20 + 20 only
    assert independent[0].probability == 0.75  # 10 + 20, 20 + 10, 20 + 20


def test_shared_roll_flag_needs_a_multi_hit_move():
    base = {"generation": 1, "move_id": "pinmissile", "attacker_species": "jolteon",
            "defender_species": "exeggutor", "rolls": [10] * 39, "defender_max_hp": 100,
            "type_multiplier": 4.0}
    assert DamageRange(**base, hit_distribution={2: 1.0}, hits_share_roll=True).hits_share_roll
    with pytest.raises(ValidationError, match="multi-hit"):
        DamageRange(**base, hits_share_roll=True)


# --------------------------------------------------------------------------- Gen 2 odds


def test_gen2_accuracy():
    snorlax, suicune = mon(2, "snorlax"), mon(2, "suicune")
    assert evaluate(2, snorlax, "bodyslam", suicune).accuracy == 1  # 255 always hits in Gen 2
    assert evaluate(2, mon(2, "starmie"), "hydropump", snorlax).accuracy == 204 / 256  # 80%
    evasive = mon(2, "suicune", boosts={"evasion": 1})
    assert evaluate(2, snorlax, "bodyslam", evasive).accuracy == 191 / 256  # x 0.75
    foreseen = mon(2, "suicune", boosts={"evasion": 1}, volatiles=["foresight"])
    assert evaluate(2, snorlax, "bodyslam", foreseen).accuracy == 1
    powdered = mon(2, "suicune", item="brightpowder")
    assert evaluate(2, snorlax, "bodyslam", powdered).accuracy == 235 / 256  # 255 - 20


def test_gen2_ohko_accuracy_grows_with_the_level_gap():
    lapras = mon(2, "lapras")
    assert evaluate(2, lapras, "horndrill", mon(2, "snorlax")).accuracy == 76 / 256
    assert evaluate(2, lapras, "horndrill", mon(2, "snorlax", level=90)).accuracy == 96 / 256
    lower = evaluate(2, mon(2, "lapras", level=90), "horndrill", mon(2, "snorlax"))
    assert lower.accuracy == 0 and lower.damage.rolls == [0]


def test_gen2_crit_stages():
    snorlax = mon(2, "snorlax")
    assert crit_chance(2, snorlax, "bodyslam") == 17 / 256
    assert crit_chance(2, mon(2, "persian"), "slash") == 64 / 256
    assert crit_chance(2, mon(2, "snorlax", item="scopelens"), "bodyslam") == 32 / 256
    assert crit_chance(2, mon(2, "snorlax", volatiles=["focusenergy"]), "bodyslam") == 32 / 256
    assert crit_chance(2, mon(2, "farfetchd", item="stick"), "peck") == 64 / 256
    assert crit_chance(2, mon(2, "chansey", item="luckypunch"), "return") == 64 / 256


def test_gen2_flail_has_one_value_and_never_crits():
    result = evaluate(2, mon(2, "magikarp", hp=3), "flail", mon(2, "starmie"))
    assert len(result.damage.rolls) == 1 and result.damage.crit_rolls is None
    assert result.ko[0].probability in (0.0, 1.0)  # no randomness beyond accuracy (which is 100%)


def test_gen2_fixed_damage_respects_immunity():
    gengar = mon(2, "gengar")
    assert evaluate(2, mon(2, "blissey"), "seismictoss", gengar).damage.rolls == [0]
    assert evaluate(2, mon(2, "raticate"), "superfang", gengar).damage.rolls == [0]
    assert evaluate(2, mon(2, "raticate"), "superfang", mon(2, "snorlax", hp=301)).damage.rolls == [150]


# --------------------------------------------------------------------------- Gen 3 odds


def test_gen3_shares_gen4_odds_except_lax_incense():
    swampert = mon(3, "swampert")
    assert evaluate(3, mon(3, "salamence"), "rockslide", swampert).accuracy == pytest.approx(0.9)
    incense = mon(3, "swampert", item="laxincense")
    assert evaluate(3, mon(3, "starmie", ability="naturalcure"), "surf", incense).accuracy == (
        pytest.approx(0.95)
    )
    gen4_incense = mon(4, "swampert", item="laxincense")
    assert evaluate(4, mon(4, "starmie", ability="naturalcure"), "surf", gen4_incense).accuracy == (
        pytest.approx(0.9)
    )
    assert crit_chance(3, mon(3, "salamence"), "earthquake", swampert) == 1 / 16
    assert crit_chance(3, mon(3, "salamence", item="scopelens"), "earthquake", swampert) == 1 / 8
    assert crit_chance(3, mon(3, "absol"), "slash", swampert) == 1 / 8


def test_gen3_multi_hit_hits_are_independent():
    result = evaluate(3, mon(3, "cloyster"), "iciclespear", mon(3, "salamence"))
    assert result.damage.hit_distribution == {2: 3 / 8, 3: 3 / 8, 4: 1 / 8, 5: 1 / 8}
    assert not result.damage.hits_share_roll


# --------------------------------------------------------------------------- every generation


@pytest.mark.parametrize("gen", [1, 2, 3])
@pytest.mark.parametrize("move", ["counter", "bide", "psywave"])
def test_moves_no_engine_can_evaluate_are_reported(gen, move):
    result = evaluate(gen, mon(gen, "chansey"), move, mon(gen, "snorlax"))
    assert result.damage is None and not result.ko and result.unsupported_reason


@pytest.mark.parametrize("gen", [2, 3])
@pytest.mark.parametrize("move", ["present", "magnitude", "triplekick"])
def test_variable_power_moves_without_a_rule_are_reported(gen, move):
    result = evaluate(gen, mon(gen, "snorlax"), move, mon(gen, "starmie"))
    assert result.damage is None and result.unsupported_reason


@pytest.mark.parametrize("gen", list(Generation))
def test_report_works_and_is_fast_in_every_generation(gen):
    tauros = mon(gen, "tauros")
    moves = [DEX[gen].move(m) for m in ("bodyslam", "earthquake", "hyperbeam", "blizzard")]
    targets = [
        mon(gen, name)
        for name in ("snorlax", "starmie", "alakazam", "gengar", "exeggutor", "rhydon")
    ]

    def one_report():
        started = perf_counter()
        for target in targets:
            result = build_report(tauros, target, moves, their_moves=moves[:1])
            assert result.status is SubsystemStatus.OK
            assert all(m.damage is not None for m in result.payload.our_moves)
        return (perf_counter() - started) * 1000

    one_report()  # warm the caches
    # Best of three batches, so a burst of unrelated load on the machine does not fail the test.
    medians = [statistics.median(one_report() for _ in range(15)) for _ in range(3)]
    assert min(medians) < 8.0  # 30 evaluations; Gens 1-2 carry 39 rolls each
