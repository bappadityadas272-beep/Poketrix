"""Task 04, step 2: the threat report (set posterior x damage calculator)."""

import statistics
from time import perf_counter

import pytest
from calc_helpers import DEX4, battler
from pydantic import ValidationError

from poketrix.calc import evaluate_move
from poketrix.schemas import (
    BattlePokemon,
    MoveThreat,
    PokemonSet,
    PriorSet,
    SetEvidence,
    SubsystemStatus,
    ThreatReport,
)
from poketrix.uncloak import SetPrior, Uncloaker, load_prior, threat_report

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
    with pytest.raises(ValidationError, match="below the expected"):
        MoveThreat(move_id="surf", probability=0.5, expected_pct=10, worst_case_pct=5)
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
