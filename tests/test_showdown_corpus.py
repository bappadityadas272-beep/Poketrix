"""Corpus measurements: robustness on real replays and the staleness of the prior."""

import json

import pytest
from test_showdown import play

from poketrix.schemas import Generation, SetEvidence
from poketrix.showdown import UnsupportedBattleError, parse_battle, parse_line
from poketrix.showdown.corpus import (
    ITEM_UNKNOWN,
    MOVE_UNKNOWN,
    SPECIES_UNKNOWN,
    UNSEEN_COMBINATION,
    contradiction,
    measure_floor,
    measure_replays,
    wilson_interval,
)
from poketrix.uncloak import load_prior

GENS = list(Generation)
HEADER = [
    "|gametype|singles", "|player|p1|Ash", "|player|p2|Gary", "|gen|4",
    "|tier|[Gen 4] Random Battle", "|teamsize|p1|6", "|teamsize|p2|6", "|start",
    "|switch|p1a: Garchomp|Garchomp, L74, M|100/100",
    "|switch|p2a: Swampert|Swampert, L80, M|100/100",
    "|turn|1",
]


def test_wilson_interval():
    low, high = wilson_interval(0, 4000)
    assert low == 0.0 and high == pytest.approx(0.00096, abs=1e-5)
    low, high = wilson_interval(15, 4161)
    assert low == pytest.approx(0.0022, abs=1e-4) and high == pytest.approx(0.0059, abs=1e-4)
    assert wilson_interval(0, 0) == (0.0, 1.0)  # nothing measured: nothing known


def test_contradictions_are_classified_by_what_the_prior_lacks():
    prior = load_prior(4)
    known = prior.sets_for("garchomp")[0].pokemon_set
    fits = SetEvidence(revealed_moves=known.moves[:2], item=known.item)
    assert contradiction(prior, "garchomp", fits) is None
    assert contradiction(prior, "garchomp", SetEvidence()) is None
    assert contradiction(prior, "missingno", SetEvidence()) == SPECIES_UNKNOWN
    assert contradiction(prior, "garchomp", SetEvidence(revealed_moves=["splash"])) == MOVE_UNKNOWN
    assert contradiction(prior, "garchomp", SetEvidence(item="oranberry")) == ITEM_UNKNOWN
    # Every part is known for the species, but no set has them together.
    items = {row.pokemon_set.item for row in prior.sets_for("garchomp")}
    never_together = next(
        (move, item)
        for item in sorted(items)
        for move in sorted({m for row in prior.sets_for("garchomp") for m in row.pokemon_set.moves})
        if not any(
            move in row.pokemon_set.moves and row.pokemon_set.item == item
            for row in prior.sets_for("garchomp")
        )
    )
    unseen = SetEvidence(revealed_moves=[never_together[0]], item=never_together[1])
    assert contradiction(prior, "garchomp", unseen) == UNSEEN_COMBINATION


@pytest.mark.slow
@pytest.mark.parametrize("gen", GENS)
def test_simulated_battles_never_rule_out_a_set_the_prior_knows(gen):
    """R10: with the truth known, a contradiction may only be a set the prior never sampled."""
    floor = measure_floor(gen)
    assert floor.bugs == []
    assert floor.staleness.contradicted == floor.true_set_unknown


def test_replays_are_measured_leniently(tmp_path):
    folder = tmp_path / "gen4"
    folder.mkdir()
    ladder = "\n".join(["|rated|", *HEADER, "|move|p2a: Swampert|Splash|p2a: Swampert",
                        "|turn|2", "|win|Ash"])
    custom = "\n".join(["|rated|Tournament battle", *HEADER,
                        "|move|p2a: Swampert|Splash|p2a: Swampert", "|turn|2"])
    logs = {
        "ladder": ladder,
        "tournament": custom,
        "eight": ladder.replace("|teamsize|p1|6", "|teamsize|p1|8"),
        "broken": ladder.replace("|turn|2", "|-damage|p2a: Nobody|50/100"),
    }
    for name, log in logs.items():
        (folder / f"{name}.json").write_text(json.dumps({"id": name, "log": log}), "utf-8")
    report = measure_replays(4, tmp_path)
    assert (report.replays, report.ladder_games, report.unfinished) == (4, 3, 1)
    assert report.unsupported == {"teams of 8 are not supported": 1}
    assert len(report.failures) == 1 and report.failures[0].startswith("broken: KeyError")
    # Swampert never has Splash: counted for the ladder game and, apart, for the tournament.
    assert report.staleness.reasons == {MOVE_UNKNOWN: 1} and report.staleness.pokemon == 2
    assert report.staleness_elsewhere.reasons == {MOVE_UNKNOWN: 1}


def test_out_of_scope_battles_are_refused_by_name():
    with pytest.raises(UnsupportedBattleError, match="teams of 8"):
        parse_battle("|gametype|singles\n|gen|2\n|teamsize|p1|8")
    with pytest.raises(UnsupportedBattleError, match="singles"):
        parse_battle("|gametype|doubles")


def test_hp_forms_other_servers_write():
    assert parse_line("|-damage|p2a: Swampert|0").hp.fainted
    assert parse_line("|-damage|p2a: Swampert|0 slp").hp.fainted
    tracker = play("|-damage|p2a: Swampert|0", "|faint|p2a: Swampert")
    assert tracker.state().opponent.active.fainted
    assert parse_line("|badge|p1|gold|gen4randombattle|100-10") is None
