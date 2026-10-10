"""Every engine must reproduce the oracle (@smogon/calc) exactly: stats and every roll.

Fixtures: tests/fixtures/calc_golden_gen{1..4}.json, written by scripts/build_calc_golden.mjs.
Inputs are in our own units (for Gens 1-2: DVs and Stat Exp).
"""

import json
from pathlib import Path

import pytest
from calc_helpers import battler

from poketrix.calc import compute_stats, engine_for
from poketrix.dex import Dex
from poketrix.schemas import FieldState, Generation, SideCondition

GENS = list(Generation)
FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURES = {
    gen: json.loads((FIXTURE_DIR / f"calc_golden_gen{int(gen)}.json").read_text(encoding="utf-8"))
    for gen in GENS
}
HAND_PICKED = [
    (gen, case) for gen in GENS for case in FIXTURES[gen]["cases"] if "sweep" not in case["tags"]
]
SWEEPS = {gen: [c for c in FIXTURES[gen]["cases"] if "sweep" in c["tags"]] for gen in GENS}
# (hand-picked cases, sweep cases, sweep cases that must actually be compared)
MINIMUM = {
    Generation.RBY: (60, 200, 180),
    Generation.GSC: (60, 200, 180),
    Generation.ADV: (60, 200, 185),
    Generation.DPP: (150, 300, 280),
}


class Unsupported(Exception):
    """The engine declined to evaluate the case."""


def side(gen, spec, extra_volatiles=()):
    # The oracle's "ability on" switch is a volatile in a real battle (Flash Fire, Slow Start).
    volatiles = [*extra_volatiles, *([spec["ability"]] if spec["ability_on"] else [])]
    return battler(
        spec["species"], level=spec["level"], nature=spec["nature"], ability=spec["ability"],
        item=spec["item"], ivs=spec["ivs"], evs=spec["evs"], boosts=spec["boosts"],
        status=spec["status"], hp=spec["hp"], volatiles=volatiles, gen_dex=Dex(gen),
    )


def run(gen, case):
    """(attacker, defender, engine outcome) for one golden case."""
    field = case["field"]
    attacker = side(gen, case["attacker"])
    defender = side(gen, case["defender"], ["foresight"] if field["foresight"] else [])
    conditions = {
        condition: 5
        for condition, key in (
            (SideCondition.REFLECT, "reflect"), (SideCondition.LIGHT_SCREEN, "light_screen"),
        )
        if field[key]
    }
    state = FieldState(weather=field["weather"], gravity_turns_left=5 if field["gravity"] else 0)
    move = Dex(gen).move(case["move"])
    return attacker, defender, engine_for(gen).evaluate(attacker, defender, move, state, conditions)


def assert_matches_oracle(gen, case):
    expected = case["expected"]
    attacker, defender, outcome = run(gen, case)
    assert {s.value: v for s, v in compute_stats(attacker.known_set).items()} == expected[
        "attacker_stats"
    ]
    assert {s.value: v for s, v in compute_stats(defender.known_set).items()} == expected[
        "defender_stats"
    ]
    if outcome.damage is None:
        raise Unsupported(outcome.unsupported_reason)
    # We never return per-hit rolls when the hits of one use differ from each other.
    assert not expected["later_hits_differ"]
    result = outcome.damage
    # No separate crit rolls means a critical hit changes nothing or cannot happen.
    crit_rolls = result.rolls if result.crit_rolls is None else result.crit_rolls
    assert list(crit_rolls) == expected["crit_rolls"]
    # For Gen 1's high-crit moves the oracle only ever computes the critical hit.
    if not expected["oracle_always_crits"]:
        assert list(result.rolls) == expected["rolls"]


@pytest.mark.parametrize("gen", GENS)
def test_fixture_is_big_enough_and_from_the_pinned_oracle(gen):
    fixture = FIXTURES[gen]
    assert fixture["source"] == {"oracle": "@smogon/calc", "version": "0.12.0", "generation": gen}
    hand_picked, sweep, _ = MINIMUM[gen]
    assert len(fixture["cases"]) - len(SWEEPS[gen]) >= hand_picked
    assert len(SWEEPS[gen]) >= sweep


@pytest.mark.parametrize(
    ("gen", "case"), HAND_PICKED,
    ids=lambda v: f"gen{int(v)}" if isinstance(v, Generation) else f"{v['id']}:{'+'.join(v['tags'])}",
)
def test_hand_picked_case_matches_oracle(gen, case):
    if "resist-berry" in case["tags"] and "multi-hit" in case["tags"]:
        assert case["expected"]["later_hits_differ"]
        with pytest.raises(Unsupported, match="resist berry"):
            assert_matches_oracle(gen, case)
        return
    assert_matches_oracle(gen, case)


@pytest.mark.parametrize("gen", GENS)
def test_random_sweep_matches_oracle(gen):
    compared, unsupported, mismatches = 0, [], []
    for case in SWEEPS[gen]:
        try:
            assert_matches_oracle(gen, case)
        except Unsupported as reason:
            unsupported.append(f"{case['move']}: {reason}")
            continue
        except AssertionError:
            mismatches.append(f"{case['id']} ({case['move']})")
        compared += 1
    assert not mismatches
    # Moves the engine declines to evaluate are skipped; nearly all of the sweep must count.
    needed = MINIMUM[gen][2]
    assert compared >= needed, f"only {compared} compared; unsupported: {sorted(set(unsupported))}"
