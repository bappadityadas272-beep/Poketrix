"""The Gen 4 engine must reproduce the oracle (@smogon/calc) exactly: stats and every roll.

Fixture: tests/fixtures/calc_golden_gen4.json, written by scripts/build_calc_golden.mjs.
"""

import json
from pathlib import Path

import pytest
from calc_helpers import DEX4, battler

from poketrix.calc import UnsupportedMoveError, compute_stats, engine_for
from poketrix.schemas import FieldState, SideCondition

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "calc_golden_gen4.json").read_text(encoding="utf-8")
)
CASES = FIXTURE["cases"]
HAND_PICKED = [c for c in CASES if "sweep" not in c["tags"]]
SWEEP = [c for c in CASES if "sweep" in c["tags"]]
ENGINE = engine_for(4)


def side(spec, volatiles=()):
    return battler(
        spec["species"], level=spec["level"], nature=spec["nature"], ability=spec["ability"],
        ivs=spec["ivs"], evs=spec["evs"], boosts=spec["boosts"], status=spec["status"],
        hp=spec["hp"], volatiles=volatiles,
    )


def run(case):
    """(attacker, defender, engine result) for one golden case."""
    field = case["field"]
    attacker = side(case["attacker"])
    defender = side(case["defender"], volatiles=["foresight"] if field["foresight"] else [])
    conditions = {
        condition: 5
        for condition, key in (
            (SideCondition.REFLECT, "reflect"), (SideCondition.LIGHT_SCREEN, "light_screen"),
        )
        if field[key]
    }
    state = FieldState(weather=field["weather"], gravity_turns_left=5 if field["gravity"] else 0)
    result = ENGINE.damage(attacker, defender, DEX4.move(case["move"]), state, conditions)
    return attacker, defender, result


def assert_matches_oracle(case):
    expected = case["expected"]
    attacker, defender, result = run(case)
    assert {s.value: v for s, v in compute_stats(attacker.known_set).items()} == expected[
        "attacker_stats"
    ]
    assert {s.value: v for s, v in compute_stats(defender.known_set).items()} == expected[
        "defender_stats"
    ]
    assert list(result.rolls) == expected["rolls"]
    # No separate crit rolls means a critical hit changes nothing (fixed damage, immunity).
    crit_rolls = result.rolls if result.crit_rolls is None else result.crit_rolls
    assert list(crit_rolls) == expected["crit_rolls"]


def test_fixture_is_big_enough_and_from_the_pinned_oracle():
    assert FIXTURE["source"] == {"oracle": "@smogon/calc", "version": "0.12.0", "generation": 4}
    assert len(HAND_PICKED) >= 30
    assert len(SWEEP) >= 200


@pytest.mark.parametrize("case", HAND_PICKED, ids=lambda c: f"{c['id']}:{'+'.join(c['tags'])}")
def test_hand_picked_case_matches_oracle(case):
    assert_matches_oracle(case)


def test_random_sweep_matches_oracle():
    compared, unsupported, mismatches = 0, [], []
    for case in SWEEP:
        try:
            assert_matches_oracle(case)
        except UnsupportedMoveError:
            unsupported.append(case["move"])
            continue
        except AssertionError:
            mismatches.append(f"{case['id']} ({case['move']})")
        compared += 1
    assert not mismatches
    # Moves the 03a engine declines to evaluate are skipped; most of the sweep must still count.
    assert compared >= 180, f"only {compared} compared; unsupported: {sorted(set(unsupported))}"
