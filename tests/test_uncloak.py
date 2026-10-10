"""Task 04: the Random Battle set prior and the Bayesian set uncloaker.

The evaluation tests at the end are the acceptance criteria agreed in the Task 04 proposal:
they score the uncloaker on held-out generator teams (tests/fixtures/randbats_holdout_gen*.json).
"""

import json
import statistics
from collections import Counter
from functools import cache
from itertools import combinations
from time import perf_counter

import pytest
from pydantic import ValidationError

from poketrix.calc import compute_stats, evaluate_move
from poketrix.dex import Dex
from poketrix.schemas import (
    BattlePokemon,
    Generation,
    PokemonSet,
    PriorSet,
    SetEvidence,
    Stat,
    SubsystemStatus,
)
from poketrix.uncloak import SetPrior, Uncloaker, load_prior
from poketrix.uncloak.evaluation import STALE_SHARE, evaluate, load_holdout, thinned
from poketrix.uncloak.prior import read_set_table

GENS = list(Generation)
PRIOR4 = load_prior(4)
UNCLOAKER4 = Uncloaker(PRIOR4)


def uncloak(species, uncloaker=UNCLOAKER4, **evidence):
    return uncloaker.uncloak(species, SetEvidence(**evidence))


# --------------------------------------------------------------------------- the prior table


def test_set_counts_and_source_are_as_built():
    assert [len(load_prior(gen).all_sets()) for gen in GENS] == [431, 559, 1184, 1740]


@pytest.mark.parametrize("gen", GENS)
def test_every_set_is_legal_and_usable_by_the_calculator(gen):
    prior = load_prior(gen)  # loading validated species, moves, items and abilities
    for row in prior.all_sets():
        known = row.pokemon_set
        assert known.generation is gen and row.count >= 1
        assert 1 <= len(known.moves) <= 4
    # Levels are fixed per species.
    levels = {}
    for row in prior.all_sets():
        levels.setdefault(row.pokemon_set.species.id, set()).add(row.pokemon_set.level)
    assert all(len(found) == 1 for found in levels.values())
    assert compute_stats(prior.all_sets()[0].pokemon_set)[Stat.HP] > 0


def test_sets_are_listed_most_frequent_first_with_stable_ids():
    rows = PRIOR4.sets_for("garchomp")
    assert [row.set_id for row in rows] == [f"garchomp:{i}" for i in range(1, len(rows) + 1)]
    assert [row.count for row in rows] == sorted((row.count for row in rows), reverse=True)
    assert PRIOR4.pokemon_set("garchomp:1") is rows[0].pokemon_set
    assert PRIOR4.sets_for("notapokemon") == ()
    with pytest.raises(KeyError, match="unknown set id 'garchomp:999'"):
        PRIOR4.pokemon_set("garchomp:999")


def test_spread_follows_the_set():
    spreads = {
        (frozenset(row.pokemon_set.moves), tuple(sorted(row.pokemon_set.spread.ivs.items())))
        for row in PRIOR4.all_sets()
    }
    # A Hidden Power set carries the IVs that produce its type; a set without one has none listed.
    assert any(ivs and any(m.startswith("hiddenpower") for m in moves) for moves, ivs in spreads)
    garchomp = PRIOR4.sets_for("garchomp")[0].pokemon_set
    assert garchomp.level == 74 and set(garchomp.spread.evs.values()) == {85}
    tauros = load_prior(1).sets_for("tauros")[0].pokemon_set
    assert tauros.level == 68 and not tauros.spread.evs  # Gen 1: maximum Stat Exp, the default


def test_a_prior_set_goes_straight_into_the_damage_calculator():
    dex = Dex(4)

    def battler(known: PokemonSet) -> BattlePokemon:
        hp = compute_stats(known)[Stat.HP]
        return BattlePokemon(
            species=known.species, level=known.level, hp_fraction=1.0, hp_current=hp, hp_max=hp,
            known_set=known,
        )

    garchomp = battler(PRIOR4.sets_for("garchomp")[0].pokemon_set)
    swampert = battler(PRIOR4.sets_for("swampert")[0].pokemon_set)
    assert evaluate_move(garchomp, swampert, dex.move("earthquake")).damage.rolls[0] > 0


def test_bad_tables_fail_at_load(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_randbats"):
        read_set_table(tmp_path / "sets.json", Generation.DPP)

    def table(**row):
        base = {"species": "garchomp", "level": 74, "moves": ["earthquake"], "item": None,
                "ability": "sandveil", "ivs": {}, "evs": {}, "count": 1}
        source = {"format": "gen4randombattle", "default_spread": {"iv": 31, "ev": 85}}
        path = tmp_path / "sets.json"
        path.write_text(json.dumps({"source": source, "sets": [{**base, **row}]}), encoding="utf-8")
        return path

    assert len(read_set_table(table(), Generation.DPP)) == 1
    with pytest.raises(ValueError, match="not a Gen 3"):
        read_set_table(table(), Generation.ADV)
    with pytest.raises(KeyError, match="unknown move 'notamove'"):
        read_set_table(table(moves=["notamove"]), Generation.DPP)
    with pytest.raises(KeyError, match="unknown item 'notanitem'"):
        read_set_table(table(item="notanitem"), Generation.DPP)
    with pytest.raises(ValidationError, match="cannot have ability"):
        read_set_table(table(ability="levitate"), Generation.DPP)


# --------------------------------------------------------------------------- evidence schema


def test_evidence_is_coherent():
    evidence = SetEvidence(revealed_moves=["Stone Edge"], item="Choice Scarf")
    assert evidence.revealed_moves == ["stoneedge"] and evidence.item == "choicescarf"
    for bad in (
        {"revealed_moves": ["earthquake", "Earthquake"]},
        {"revealed_moves": ["a", "b", "c", "d", "e"]},
        {"item": "leftovers", "ruled_out_items": ["leftovers"]},
        {"ability": "sandveil", "ruled_out_abilities": ["sandveil"]},
    ):
        with pytest.raises(ValidationError):
            SetEvidence(**bad)


# --------------------------------------------------------------------------- tier 1: Bayes


def test_no_evidence_returns_the_prior():
    result = uncloak("Garchomp")
    assert result.status is SubsystemStatus.OK
    posterior = result.payload
    total = sum(row.count for row in PRIOR4.sets_for("garchomp"))
    assert posterior.species_id == "garchomp"
    for hypothesis, row in zip(posterior.hypotheses, PRIOR4.sets_for("garchomp")):
        assert hypothesis.set_id == row.set_id
        assert hypothesis.prior == hypothesis.posterior == pytest.approx(row.count / total)


def test_a_revealed_move_rules_out_sets_without_it():
    before, after = uncloak("garchomp").payload, uncloak("garchomp", revealed_moves=["substitute"]).payload
    assert 0 < before.move_probability("substitute") < 1
    assert after.move_probability("substitute") == pytest.approx(1)
    assert all(h.posterior == 0 for h in after.hypotheses if "substitute" not in h.moves)
    assert sum(h.prior for h in after.hypotheses) == pytest.approx(1)  # priors are untouched
    # Sets that fit keep their relative odds.
    fits = [h for h in after.hypotheses if h.posterior > 0]
    assert fits[0].posterior / fits[-1].posterior == pytest.approx(fits[0].prior / fits[-1].prior)


def test_item_and_ability_evidence():
    scarf = uncloak("garchomp", item="choicescarf").payload
    assert scarf.item_probability("choicescarf") == pytest.approx(1)
    assert all(h.posterior == 0 for h in scarf.hypotheses if h.item != "choicescarf")
    no_scarf = uncloak("garchomp", ruled_out_items=["choicescarf"]).payload
    assert no_scarf.item_probability("choicescarf") == 0
    snorlax = uncloak("snorlax").payload
    assert 0 < snorlax.ability_probability("thickfat") < 1
    thick_fat = uncloak("snorlax", ability="thickfat").payload
    assert thick_fat.ability_probability("thickfat") == pytest.approx(1)
    assert uncloak("snorlax", ruled_out_abilities=["thickfat"]).payload.ability_probability("thickfat") == 0


def test_four_revealed_moves_leave_only_item_and_ability_open():
    moves = PRIOR4.sets_for("garchomp")[0].pokemon_set.moves
    posterior = uncloak("garchomp", revealed_moves=moves).payload
    live = [h for h in posterior.hypotheses if h.posterior > 0]
    assert live and all(set(h.moves) == set(moves) for h in live)


def test_every_move_of_a_set_is_equally_likely_to_be_the_one_shown():
    dex = Dex(1)

    def row(set_id, moves, count):
        known = PokemonSet(species=dex.species("ditto"), moves=moves)
        return PriorSet(set_id=set_id, pokemon_set=known, count=count)

    prior = SetPrior(1, [row("ditto:1", ["transform"], 1),
                         row("ditto:2", ["transform", "tackle", "surf", "bodyslam"], 1)])
    posterior = uncloak("ditto", Uncloaker(prior), revealed_moves=["transform"]).payload
    # The one-move set must have shown Transform; the four-move set shows it 1 time in 4.
    assert [h.posterior for h in posterior.hypotheses] == pytest.approx([0.8, 0.2])


# --------------------------------------------------------------------------- tiers 2-4: fallbacks


def test_tier2_keeps_the_moves_and_adopts_the_item_that_was_seen():
    assert all(row.pokemon_set.item != "blacksludge" for row in PRIOR4.sets_for("garchomp"))
    result = uncloak("garchomp", revealed_moves=["earthquake"], item="blacksludge")
    assert result.status is SubsystemStatus.FALLBACK
    posterior = result.payload
    assert posterior.evidence_item == "blacksludge"
    assert all(h.item == "blacksludge" and "earthquake" in h.moves for h in posterior.hypotheses)
    assert sum(h.posterior for h in posterior.hypotheses) == pytest.approx(1)
    # The source set is still named, so its spread can be looked up.
    assert all(PRIOR4.pokemon_set(h.set_id) for h in posterior.hypotheses)


def test_tier2_when_every_item_is_ruled_out():
    items = {row.pokemon_set.item for row in PRIOR4.sets_for("garchomp")}
    result = uncloak("garchomp", ruled_out_items=sorted(items))
    assert result.status is SubsystemStatus.FALLBACK
    assert all(h.item is None for h in result.payload.hypotheses)


def test_tier3_completes_a_moveset_nobody_has_seen():
    assert all("surf" not in row.pokemon_set.moves for row in PRIOR4.sets_for("garchomp"))
    result = uncloak("garchomp", revealed_moves=["surf", "earthquake"])
    assert result.status is SubsystemStatus.FALLBACK
    posterior = result.payload
    assert all({"surf", "earthquake"} <= set(h.moves) and len(h.moves) == 4 for h in posterior.hypotheses)
    assert all(h.set_id.startswith("fallback:") for h in posterior.hypotheses)
    assert posterior.move_probability("surf") == pytest.approx(1)
    # The species' usual moves fill the open slots, the commonest most often.
    usage = Counter()
    for row in PRIOR4.sets_for("garchomp"):
        usage.update({m: row.count for m in row.pokemon_set.moves if m != "earthquake"})
    (common, _), *_, (rare, _) = usage.most_common()
    assert posterior.move_probability(common) > posterior.move_probability(rare) > 0


def test_tier3_for_a_species_the_prior_does_not_know():
    result = uncloak("notapokemon", revealed_moves=["tackle"], item="leftovers")
    assert result.status is SubsystemStatus.FALLBACK
    (only,) = result.payload.hypotheses
    assert (only.moves, only.item, only.posterior) == (["tackle"], "leftovers", 1)


def test_tier4_is_an_error_result_not_an_exception():
    result = uncloak("notapokemon")
    assert result.status is SubsystemStatus.ERROR and result.payload is None
    assert "notapokemon" in result.error


def test_four_unknown_moves_are_returned_as_they_are():
    moves = ["surf", "icebeam", "thunderbolt", "psychic"]
    posterior = uncloak("garchomp", revealed_moves=moves).payload
    assert [h.moves for h in posterior.hypotheses] == [moves]


# --------------------------------------------------------------------------- speed


def test_one_update_takes_well_under_5ms():
    species = max(
        {row.pokemon_set.species.id for row in PRIOR4.all_sets()},
        key=lambda s: len(PRIOR4.sets_for(s)),
    )
    assert len(PRIOR4.sets_for(species)) >= 40  # the largest hypothesis table
    evidence = SetEvidence(revealed_moves=[PRIOR4.sets_for(species)[0].pokemon_set.moves[0]])

    def timed():
        started = perf_counter()
        assert UNCLOAKER4.uncloak(species, evidence).status is SubsystemStatus.OK
        return (perf_counter() - started) * 1000

    timed()
    assert min(statistics.median(timed() for _ in range(25)) for _ in range(3)) < 5.0


# --------------------------------------------------------------------------- evaluation targets

# Top-1 / top-3 accuracy measured for the proposal (docs/PROGRESS_TRACKER.md, Task 04, section 5).
# The agreed target: never more than 0.02 below these.
PROPOSAL_ACCURACY = {
    (4, 0): (0.383, 0.769), (4, 1): (0.503, 0.858), (4, 2): (0.629, 0.929),
    (4, 3): (0.780, 0.980), (4, 4): (0.970, 0.999),
    (3, 0): (0.371, 0.767), (3, 2): (0.656, 0.949), (3, 4): (0.986, 1.000),
    (2, 0): (0.447, 0.842), (2, 2): (0.721, 0.975), (2, 4): (0.993, 1.000),
    (1, 0): (0.576, 0.922), (1, 2): (0.769, 0.973), (1, 4): (1.000, 1.000),
}


@cache
def held_out_metrics(gen):
    return evaluate(load_prior(gen), load_holdout(gen))


@pytest.mark.parametrize("gen", GENS)
def test_held_out_true_set_survives_and_ranks_as_agreed(gen):
    for metrics in held_out_metrics(gen):
        assert metrics.true_set_kept >= 0.999
        assert metrics.tier_share(1) >= 0.999
        reference = PROPOSAL_ACCURACY.get((int(gen), metrics.revealed))
        if reference is not None:
            assert metrics.top1_accuracy >= reference[0] - 0.02
            assert metrics.top3_accuracy >= reference[1] - 0.02


@pytest.mark.parametrize("gen", GENS)
def test_held_out_move_probabilities_are_calibrated(gen):
    for metrics in held_out_metrics(gen):
        assert metrics.move_calibration_error <= 0.02


@pytest.mark.parametrize("gen", GENS)
def test_posterior_beats_guessing_uniformly_among_the_sets_that_fit(gen):
    *partly_revealed, fully_revealed = held_out_metrics(gen)
    for metrics in partly_revealed:
        assert metrics.set_log_loss < metrics.uniform_log_loss
    # With all four moves known only a near-even item choice is left, and the two scores tie
    # to within sampling noise (Gen 2: 0.01025 against 0.01024). See the Task 04 write-up.
    assert fully_revealed.set_log_loss <= fully_revealed.uniform_log_loss + 0.001


def test_more_revealed_moves_never_make_it_worse():
    for gen in GENS:
        top1 = [m.top1_accuracy for m in held_out_metrics(gen)]
        loss = [m.set_log_loss for m in held_out_metrics(gen)]
        assert top1 == sorted(top1) and loss == sorted(loss, reverse=True)


def test_seeing_the_item_and_ability_helps():
    shown = evaluate(PRIOR4, load_holdout(4), item_and_ability_shown=True)
    for with_extras, moves_only in zip(shown, held_out_metrics(Generation.DPP)):
        assert with_extras.top1_accuracy >= moves_only.top1_accuracy
    assert shown[4].top1_accuracy == pytest.approx(shown[4].true_set_kept)  # nothing left to guess


def test_out_of_date_prior_falls_back_and_never_raises():
    """The deliberately unfair test: 5% of the sets are missing from the prior."""
    stale = thinned(PRIOR4, share=STALE_SHARE, seed=4)
    assert len(stale.all_sets()) == round(len(PRIOR4.all_sets()) * (1 - STALE_SHARE))
    metrics = evaluate(stale, load_holdout(4), item_and_ability_shown=True)
    assert 0.93 <= metrics[0].true_set_kept <= 0.97  # about 5% of the teams are now unknown
    assert metrics[0].tier_share(2) > 0 and metrics[4].tier_share(3) > 0  # both fallbacks fire
    assert all(m.move_calibration_error <= 0.05 for m in metrics)

    # Through the public call, every held-out case yields a valid result in every tier.
    uncloaker, seen = Uncloaker(stale), set()
    for truth in load_holdout(4)[::7]:
        known = truth.pokemon_set
        for k in range(len(known.moves) + 1):
            revealed = list(next(combinations(known.moves, k)))
            evidence = SetEvidence(revealed_moves=revealed, item=known.item, ability=known.ability)
            result = uncloaker.uncloak(known.species.id, evidence)
            assert result.payload is not None
            seen.add(result.status)
    assert seen == {SubsystemStatus.OK, SubsystemStatus.FALLBACK}
