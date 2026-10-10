"""Math layer unit tests: everything the oracle fixture cannot check (see test_calc_golden)."""

import itertools
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
from poketrix.dex import Dex
from poketrix.schemas import (
    FieldState,
    PokemonSet,
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


def test_unknown_nature_and_pre_gen3_stats_are_rejected():
    with pytest.raises(ValueError, match="unknown nature 'notanature'"):
        battler("garchomp", nature="notanature")
    gengar1 = PokemonSet(species=Dex(1).species("gengar"), moves=["lick"])
    with pytest.raises(NotImplementedError, match="03c"):
        compute_stats(gengar1)


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


@pytest.mark.parametrize("move", ["pinmissile", "gyroball", "lowkick", "payback", "magnitude"])
def test_moves_outside_03a_are_reported_not_guessed(move):
    result = fixed(battler("garchomp"), move, battler("swampert"))
    assert result.damage is None and not result.ko and result.unsupported_reason


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


def test_accuracy_and_evasion_stages_change_hit_chance():
    engine = engine_for(4)
    stone_edge = DEX4.move("stoneedge")  # 80% accurate
    target = battler("swampert")
    assert engine.hit_chance(battler("garchomp"), target, stone_edge) == pytest.approx(0.8)
    evasive = battler("swampert", boosts={"evasion": 1})
    assert engine.hit_chance(battler("garchomp"), evasive, stone_edge) == pytest.approx(0.6)
    sharp = battler("garchomp", boosts={"accuracy": 6})
    assert engine.hit_chance(sharp, target, stone_edge) == 1
    assert engine.hit_chance(battler("garchomp"), evasive, DEX4.move("aerialace")) == 1


def test_high_crit_move_uses_a_higher_crit_chance():
    attacker, defender = battler("garchomp"), battler("blissey", hp=1)

    def crit_chance(move):
        return engine_for(4).damage(attacker, defender, DEX4.move(move), FieldState(), {}).crit_chance

    assert crit_chance("stoneedge") == 1 / 8
    assert crit_chance("earthquake") == 1 / 16


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


def test_generation_without_an_engine_is_reported():
    with pytest.raises(NotImplementedError, match="Gen 3"):
        engine_for(3)


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
    assert statistics.median(one_report() for _ in range(25)) < 5.0
