"""Task 04, step 2: the threat report (set posterior x damage calculator)."""

import random
import statistics
from time import perf_counter

import pytest
from calc_helpers import DEX4, battler
from pydantic import ValidationError

from poketrix.calc import compute_stats, evaluate_move
from poketrix.schemas import (
    BattlePokemon,
    MoveThreat,
    PokemonSet,
    PriorSet,
    SetEvidence,
    Stat,
    SubsystemStatus,
    ThreatReport,
)
from poketrix.uncloak import SetPrior, Uncloaker, load_prior, threat_report
from poketrix.uncloak.evaluation import load_holdout

PRIOR4 = load_prior(4)
UNCLOAKER4 = Uncloaker(PRIOR4)


def opponent(species, level=None, hp_fraction=1.0):
    """An opposing Pokémon as a battle shows it: species, level and HP bar, no set."""
    known = PRIOR4.sets_for(species)
    return BattlePokemon(
        species=DEX4.species(species), hp_fraction=hp_fraction,
        level=level or (known[0].pokemon_set.level if known else 100),
    )


def report_for(ours, theirs, prior=PRIOR4, **evidence):
    posterior = Uncloaker(prior).uncloak(theirs.species.id, SetEvidence(**evidence)).payload
    return posterior, threat_report(ours, theirs, posterior, prior)


def test_lists_every_possible_move_with_its_posterior_probability():
    ours, theirs = battler("swampert"), opponent("garchomp")
    posterior, result = report_for(ours, theirs)
    assert result.status is SubsystemStatus.OK and result.latency_ms >= 0
    report = result.payload
    assert (report.attacker_species, report.defender_species) == ("garchomp", "swampert")
    possible = {move for h in posterior.hypotheses for move in h.moves}
    assert {t.move_id for t in report.threats} == possible
    for threat in report.threats:
        assert threat.probability == pytest.approx(posterior.move_probability(threat.move_id))
    odds = [t.probability for t in report.threats]
    assert odds == sorted(odds, reverse=True)


def test_a_revealed_move_is_certain_and_impossible_sets_drop_out():
    ours, theirs = battler("swampert"), opponent("garchomp")
    _, result = report_for(ours, theirs, revealed_moves=["substitute"])
    threats = {t.move_id: t for t in result.payload.threats}
    assert threats["substitute"].probability == pytest.approx(1)
    live = [h for h in UNCLOAKER4.uncloak("garchomp", SetEvidence(revealed_moves=["substitute"]))
            .payload.hypotheses if h.posterior > 0]
    assert set(threats) == {move for h in live for move in h.moves}


def two_set_prior():
    """Garchomp with two equally likely sets that differ in item and in one move."""
    species = DEX4.species("garchomp")

    def row(set_id, moves, item):
        known = PokemonSet(species=species, level=74, moves=moves, item=item, ability="sandveil")
        return PriorSet(set_id=set_id, pokemon_set=known, count=1)

    return SetPrior(4, [
        row("garchomp:1", ["earthquake", "outrage", "swordsdance", "counter"], "choiceband"),
        row("garchomp:2", ["earthquake", "outrage", "stoneedge", "pinmissile"], None),
    ])


def test_damage_is_the_posterior_weighted_average_over_hypotheses():
    prior, ours, theirs = two_set_prior(), battler("swampert"), opponent("garchomp", level=74)
    _, result = report_for(ours, theirs, prior)
    threats = {t.move_id: t for t in result.payload.threats}

    def direct(set_id):
        attacker = theirs.model_copy(update={"known_set": prior.pokemon_set(set_id)})
        damage = evaluate_move(attacker, ours, DEX4.move("earthquake")).damage
        return 100 * statistics.mean(damage.rolls) / damage.defender_max_hp, damage.max_pct

    (banded_mean, banded_max), (plain_mean, plain_max) = direct("garchomp:1"), direct("garchomp:2")
    assert banded_mean > plain_mean  # Choice Band
    earthquake = threats["earthquake"]
    assert earthquake.probability == pytest.approx(1)
    assert earthquake.expected_pct == pytest.approx((banded_mean + plain_mean) / 2)
    assert earthquake.worst_case_pct == pytest.approx(banded_max) and banded_max > plain_max
    assert 0 <= earthquake.ko_probability <= 1

    stone_edge = threats["stoneedge"]  # only the second set has it
    assert stone_edge.probability == pytest.approx(0.5)
    attacker = theirs.model_copy(update={"known_set": prior.pokemon_set("garchomp:2")})
    alone = evaluate_move(attacker, ours, DEX4.move("stoneedge")).damage
    assert stone_edge.expected_pct == pytest.approx(100 * statistics.mean(alone.rolls) / alone.defender_max_hp)


def test_status_unsupported_and_multi_hit_moves():
    _, result = report_for(battler("swampert"), opponent("garchomp", level=74), two_set_prior())
    threats = {t.move_id: t for t in result.payload.threats}
    setup = threats["swordsdance"]
    assert setup.expected_pct is None and setup.unsupported_reason is None  # a status move
    counter = threats["counter"]  # the calculator cannot evaluate it: unknown, not harmless
    assert counter.unsupported_reason and counter.expected_pct is None
    assert counter.ko_probability is None and counter.probability == pytest.approx(0.5)
    pin_missile = threats["pinmissile"]  # expected damage covers a whole use (2-5 hits)
    assert pin_missile.worst_case_pct > pin_missile.expected_pct > 0


def test_ko_probability_follows_our_remaining_hp():
    theirs = opponent("garchomp")
    healthy = report_for(battler("swampert"), theirs)[1].payload
    weak = report_for(battler("swampert", hp=1), theirs)[1].payload

    def ko(report, move):
        return next(t for t in report.threats if t.move_id == move).ko_probability

    assert ko(healthy, "earthquake") == 0
    assert ko(weak, "earthquake") == pytest.approx(1)


def test_fallback_posteriors_are_usable():
    ours, theirs = battler("swampert"), opponent("garchomp")
    # Tier 2: an item no Garchomp set has. Tier 3: a move no Garchomp set has.
    for evidence in ({"item": "blacksludge"}, {"revealed_moves": ["surf"]}):
        fallback = UNCLOAKER4.uncloak("garchomp", SetEvidence(**evidence))
        assert fallback.status is SubsystemStatus.FALLBACK
        result = threat_report(ours, theirs, fallback.payload, PRIOR4)
        assert result.status is SubsystemStatus.OK and result.payload.threats
    surf = next(t for t in result.payload.threats if t.move_id == "surf")
    assert surf.probability == pytest.approx(1) and surf.expected_pct > 0


def test_failures_come_back_as_error_results():
    theirs = opponent("garchomp")
    posterior = UNCLOAKER4.uncloak("garchomp", SetEvidence()).payload
    no_set = battler("swampert").model_copy(update={"known_set": None})
    result = threat_report(no_set, theirs, posterior, PRIOR4)
    assert result.status is SubsystemStatus.ERROR and "known_set" in result.error


def test_threat_schema_rules():
    assert MoveThreat(move_id="counter", probability=0.5, unsupported_reason="reactive")
    with pytest.raises(ValidationError, match="no damage numbers"):
        MoveThreat(move_id="counter", probability=0.5, unsupported_reason="x", expected_pct=1,
                   worst_case_pct=2)
    with pytest.raises(ValidationError, match="given together"):
        MoveThreat(move_id="surf", probability=0.5, expected_pct=10)
    with pytest.raises(ValidationError, match="given together"):
        MoveThreat(move_id="surf", probability=0.5, expected_pct=10, worst_case_pct=12)
    with pytest.raises(ValidationError, match="below the expected"):
        MoveThreat(move_id="surf", probability=0.5, expected_pct=10, worst_case_pct=5,
                   worst_crit_pct=20)
    with pytest.raises(ValidationError, match="critical hit cannot do less"):
        MoveThreat(move_id="surf", probability=0.5, expected_pct=10, worst_case_pct=12,
                   worst_crit_pct=11)
    assert MoveThreat(move_id="surf", probability=0.5, expected_pct=10, worst_case_pct=12,
                      worst_crit_pct=24)
    likely = MoveThreat(move_id="surf", probability=0.9)
    unlikely = MoveThreat(move_id="icebeam", probability=0.1)
    assert ThreatReport(attacker_species="a", defender_species="b", threats=[likely, unlikely])
    with pytest.raises(ValidationError, match="ordered by probability"):
        ThreatReport(attacker_species="a", defender_species="b", threats=[unlikely, likely])
    with pytest.raises(ValidationError, match="listed twice"):
        ThreatReport(attacker_species="a", defender_species="b", threats=[likely, likely])


def test_report_for_the_largest_hypothesis_table_is_fast():
    species = max(
        {row.pokemon_set.species.id for row in PRIOR4.all_sets()},
        key=lambda s: len(PRIOR4.sets_for(s)),
    )
    ours, theirs = battler("swampert"), opponent(species)
    posterior = UNCLOAKER4.uncloak(species, SetEvidence()).payload

    def timed():
        started = perf_counter()
        assert threat_report(ours, theirs, posterior, PRIOR4).status is SubsystemStatus.OK
        return (perf_counter() - started) * 1000

    timed()
    # Part of the ML budget of 150 ms per turn; uncloaking itself takes well under 5 ms.
    assert min(statistics.median(timed() for _ in range(9)) for _ in range(3)) < 50.0


# --------------------------------------------------------------------------- R6: critical hits


def test_worst_crit_is_never_below_the_worst_normal_hit():
    prior, ours, theirs = two_set_prior(), battler("swampert"), opponent("garchomp", level=74)
    _, result = report_for(ours, theirs, prior)
    threats = {t.move_id: t for t in result.payload.threats}
    for threat in threats.values():
        if threat.worst_case_pct is not None:
            assert threat.worst_crit_pct >= threat.worst_case_pct >= threat.expected_pct
    # Earthquake: the highest critical roll of the stronger (Choice Band) hypothesis.
    attacker = theirs.model_copy(update={"known_set": prior.pokemon_set("garchomp:1")})
    damage = evaluate_move(attacker, ours, DEX4.move("earthquake")).damage
    assert threats["earthquake"].worst_crit_pct == pytest.approx(
        100 * damage.crit_rolls[-1] / damage.defender_max_hp
    )
    assert threats["earthquake"].worst_crit_pct > 1.9 * threats["earthquake"].worst_case_pct
    assert threats["swordsdance"].worst_crit_pct is None  # a status move
    assert threats["counter"].worst_crit_pct is None  # unsupported


def test_worst_crit_equals_worst_case_when_a_crit_changes_nothing():
    ours, theirs = battler("swampert"), opponent("blissey")
    posterior = UNCLOAKER4.uncloak("blissey", SetEvidence(revealed_moves=["seismictoss"])).payload
    report = threat_report(ours, theirs, posterior, PRIOR4).payload
    toss = next(t for t in report.threats if t.move_id == "seismictoss")
    assert toss.worst_crit_pct == toss.worst_case_pct == toss.expected_pct  # fixed damage


# --------------------------------------------------------------------------- R7: the headline


def ohko_prior():
    """Set A (3 in 4) carries Fissure; set B (1 in 4) carries no damaging move."""
    species = DEX4.species("garchomp")

    def row(set_id, moves, count):
        known = PokemonSet(species=species, level=74, moves=moves, ability="sandveil")
        return PriorSet(set_id=set_id, pokemon_set=known, count=count)

    return SetPrior(4, [
        row("garchomp:1", ["fissure", "swordsdance"], 3),
        row("garchomp:2", ["swordsdance", "substitute"], 1),
    ])


def test_p_ko_best_move_worked_by_hand():
    # Both Pokémon are level 74, so Fissure lands 30% of the time and then always knocks out:
    # KO(Fissure | A) = 0.30. Set A has probability 3/4 and set B cannot deal damage, so
    # p_ko_best_move = 0.75 x 0.30 + 0.25 x 0 = 0.225.
    ours, theirs = battler("swampert", level=74), opponent("garchomp", level=74)
    _, result = report_for(ours, theirs, ohko_prior())
    report = result.payload
    assert report.p_ko_best_move == pytest.approx(0.225)
    assert report.ko_lower_bound is False
    fissure = next(t for t in report.threats if t.move_id == "fissure")
    assert (fissure.probability, fissure.ko_probability) == pytest.approx((0.75, 0.30))


def test_p_ko_best_move_takes_the_best_move_of_each_set_not_a_sum():
    # A healthy Swampert survives almost everything; at 1 HP every damaging move knocks it
    # out, and a set with three such moves still counts once.
    theirs = opponent("garchomp")
    healthy = report_for(battler("swampert"), theirs)[1].payload
    assert healthy.p_ko_best_move < 0.01  # only a rare critical hit from one set
    weak = report_for(battler("swampert", hp=1), theirs)[1].payload
    assert 0.9 < weak.p_ko_best_move <= 1
    assert sum(t.probability * (t.ko_probability or 0) for t in weak.threats) > 1.5


def test_an_unsupported_move_makes_the_headline_a_lower_bound():
    _, result = report_for(battler("swampert"), opponent("garchomp", level=74), two_set_prior())
    report = result.payload
    assert any(t.unsupported_reason for t in report.threats)  # Counter, at probability 0.5
    assert report.ko_lower_bound is True
    assert report_for(battler("swampert"), opponent("garchomp"))[1].payload.ko_lower_bound is False


def test_p_ko_best_move_stays_within_its_bounds_on_held_out_teams():
    """max_m P(m) KO(m)  <=  p_ko_best_move  <=  sum_m P(m) KO(m), on 50 random matchups."""
    rng = random.Random(20261011)
    holdout = load_holdout(4)
    our_sets = PRIOR4.all_sets()
    informative = 0
    for _ in range(50):
        truth = rng.choice(holdout).pokemon_set
        mine = rng.choice(our_sets).pokemon_set
        max_hp = compute_stats(mine)[Stat.HP]
        hp = rng.randint(1, max_hp)  # often low, so knockouts are possible
        ours = BattlePokemon(
            species=mine.species, level=mine.level, hp_fraction=hp / max_hp, hp_current=hp,
            hp_max=max_hp, known_set=mine,
        )
        theirs = BattlePokemon(species=truth.species, level=truth.level, hp_fraction=1.0)
        revealed = rng.sample(truth.moves, rng.randint(0, len(truth.moves)))
        posterior = UNCLOAKER4.uncloak(truth.species.id, SetEvidence(revealed_moves=revealed))
        result = threat_report(ours, theirs, posterior.payload, PRIOR4)
        assert result.status is SubsystemStatus.OK
        report = result.payload
        per_move = [t.probability * (t.ko_probability or 0.0) for t in report.threats]
        assert max(per_move) - 1e-9 <= report.p_ko_best_move <= sum(per_move) + 1e-9
        for threat in report.threats:
            if threat.worst_case_pct is not None:
                assert threat.worst_crit_pct >= threat.worst_case_pct
        informative += 0 < report.p_ko_best_move < 1
    assert informative >= 10  # the bounds were exercised, not trivially 0 = 0 = 0
