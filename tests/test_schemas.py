"""CP1 acceptance tests: schemas accept legal Gen 1-4 data and reject illegal data."""

import pytest
from conftest import species
from pydantic import ValidationError

from poketrix.schemas import (
    ActionPrediction,
    BattlePokemon,
    DamageRange,
    GameState,
    KOChance,
    Move,
    PokemonSet,
    Recommendation,
    SetHypothesis,
    SetPosterior,
    StatSpread,
    SubsystemResult,
    gen1_2_hp_dv,
    to_id,
)

# ------------------------------------------------------------------ ids


@pytest.mark.parametrize(
    "raw,expected",
    [("Stone Edge", "stoneedge"), ("Farfetch'd", "farfetchd"), ("Mr. Mime", "mrmime"),
     ("U-turn", "uturn"), ("Choice Scarf", "choicescarf")],
)
def test_to_id(raw, expected):
    assert to_id(raw) == expected


# ------------------------------------------------------------------ species / generation


def test_gen1_rejects_dark_and_steel():
    with pytest.raises(ValidationError, match="not available"):
        species(1, "magnemite", 81, ["electric", "steel"], (25, 35, 70, 95, 95, 45))
    # Same Pokémon is legal as Electric/Steel from Gen 2.
    species(2, "magnemite", 81, ["electric", "steel"], (25, 35, 70, 95, 55, 45))


def test_dex_number_capped_per_gen():
    with pytest.raises(ValidationError, match="does not exist in Gen 3"):
        species(3, "garchomp", 445, ["dragon", "ground"], (108, 130, 95, 80, 85, 102))


def test_gen1_single_special(gengar1):
    with pytest.raises(ValidationError, match="single Special"):
        species(1, "gengar", 94, ["ghost", "poison"], (60, 65, 60, 130, 75, 110))


def test_no_abilities_before_gen3():
    with pytest.raises(ValidationError, match="abilities"):
        species(2, "tyranitar", 248, ["rock", "dark"], (100, 134, 110, 95, 100, 61), ["sandstream"])


# ------------------------------------------------------------------ moves


def test_pre_split_category_follows_type():
    # Gen 3: Fire moves are always special.
    Move(id="firepunch", name="Fire Punch", generation=3, type="fire", category="special",
         base_power=75, accuracy=100, pp=15)
    with pytest.raises(ValidationError, match="must be special"):
        Move(id="firepunch", name="Fire Punch", generation=3, type="fire", category="physical",
             base_power=75, accuracy=100, pp=15)
    # Gen 4: physical/special split, so it is physical.
    Move(id="firepunch", name="Fire Punch", generation=4, type="fire", category="physical",
         base_power=75, accuracy=100, pp=15)


def test_curse_typeless_only_from_gen2():
    Move(id="curse", name="Curse", generation=2, type="???", category="status",
         base_power=0, pp=10)
    with pytest.raises(ValidationError):
        Move(id="curse", name="Curse", generation=1, type="???", category="status",
             base_power=0, pp=10)


# ------------------------------------------------------------------ sets & spreads


def test_gen1_set_rejects_item_and_nature(gengar1):
    PokemonSet(species=gengar1, moves=["Thunderbolt", "Hypnosis", "Explosion", "Night Shade"])
    with pytest.raises(ValidationError, match="held items"):
        PokemonSet(species=gengar1, moves=["thunderbolt"], item="leftovers")
    with pytest.raises(ValidationError, match="natures"):
        PokemonSet(species=gengar1, moves=["thunderbolt"], nature="timid")


def test_ability_must_belong_to_species(garchomp4):
    with pytest.raises(ValidationError, match="cannot have ability"):
        PokemonSet(species=garchomp4, moves=["earthquake"], ability="levitate")


def test_duplicate_moves_rejected(garchomp4):
    with pytest.raises(ValidationError, match="duplicate"):
        PokemonSet(species=garchomp4, moves=["Earthquake", "earthquake"])


def test_ev_limits(garchomp4):
    PokemonSet(species=garchomp4, moves=["earthquake"],
               spread=StatSpread(evs={"atk": 252, "spe": 252, "hp": 4}))
    with pytest.raises(ValidationError, match="EV total"):
        PokemonSet(species=garchomp4, moves=["earthquake"],
                   spread=StatSpread(evs={"atk": 252, "spe": 252, "hp": 252}))


def test_gen1_2_dvs(gengar1):
    assert gen1_2_hp_dv({}) == 15
    assert gen1_2_hp_dv({"atk": 14}) == 7  # atk DV even -> top HP bit cleared
    ok = StatSpread(ivs={"atk": 14, "def": 15, "spe": 15, "spa": 15, "spd": 15, "hp": 7})
    PokemonSet(species=gengar1, moves=["thunderbolt"], spread=ok)
    with pytest.raises(ValidationError, match="HP DV is derived"):
        PokemonSet(species=gengar1, moves=["thunderbolt"],
                   spread=StatSpread(ivs={"atk": 14, "spa": 15, "spd": 15, "hp": 15}))
    with pytest.raises(ValidationError, match="outside 0..15"):
        PokemonSet(species=gengar1, moves=["thunderbolt"], spread=StatSpread(ivs={"spe": 31}))
    with pytest.raises(ValidationError, match="Special DV"):
        PokemonSet(species=gengar1, moves=["thunderbolt"],
                   spread=StatSpread(ivs={"spa": 15, "spd": 10}))


# ------------------------------------------------------------------ battle state


def test_battle_pokemon_hp_consistency(garchomp4):
    with pytest.raises(ValidationError, match="disagrees"):
        BattlePokemon(species=garchomp4, hp_fraction=0.9, hp_current=100, hp_max=266)
    with pytest.raises(ValidationError, match="no status"):
        BattlePokemon(species=garchomp4, hp_fraction=0.0, status="brn")


def test_gen1_special_boosts_linked(gengar1):
    BattlePokemon(species=gengar1, hp_fraction=1, boosts={"spa": 2, "spd": 2})
    with pytest.raises(ValidationError, match="Special boosts"):
        BattlePokemon(species=gengar1, hp_fraction=1, boosts={"spa": 2})


def test_valid_gen4_state(gen4_state):
    assert gen4_state.me.active.species.id == "garchomp"
    assert gen4_state.opponent.active.revealed_moves == ["surf"]
    assert gen4_state.opponent.alive_count == 6  # 1 revealed alive + 5 unrevealed
    # Round-trips through JSON: the contract ingestion will produce.
    again = GameState.model_validate_json(gen4_state.model_dump_json(by_alias=True))
    assert again == gen4_state


def _mutate(state, **changes):
    data = state.model_dump(by_alias=True)
    for path, value in changes.items():
        node = data
        *parents, leaf = path.split("__")
        for p in parents:
            node = node[int(p) if p.isdigit() else p]
        node[leaf] = value
    return data


@pytest.mark.parametrize(
    "path,value,msg",
    [
        ("format_id", "gen3ou", "does not match"),
        ("sides__p2__conditions", {"spikes": 4}, "outside 1..3"),
        ("field__weather", "none", None),  # control: valid
        ("sides__p1__request__available_switches", [0], "active"),
        ("sides__p1__request__available_moves", ["surf"], "not in known set"),
    ],
)
def test_state_rejections(gen4_state, path, value, msg):
    data = _mutate(gen4_state, **{path: value})
    if msg is None:
        GameState.model_validate(data)
    else:
        with pytest.raises(ValidationError, match=msg):
            GameState.model_validate(data)


def test_gen3_state_rejects_stealth_rock(gen4_state):
    data = gen4_state.model_dump(by_alias=True)
    for side in data["sides"].values():
        for mon in side["team"]:
            mon["species"]["generation"] = 3
            mon["species"]["dex_number"] = 121  # starmie exists in gen 3
        side["team"] = [m for m in side["team"] if m["species"]["id"] == "starmie"]
        side["active_index"] = 0
        side["request"] = None
    data["generation"] = 3
    data["format_id"] = "gen3randombattle"
    with pytest.raises(ValidationError, match="stealthrock does not exist in Gen 3"):
        GameState.model_validate(data)


# ------------------------------------------------------------------ subsystem outputs


def test_damage_roll_counts():
    base = {"move_id": "earthquake", "attacker_species": "garchomp", "defender_species": "starmie",
                "defender_max_hp": 250, "type_multiplier": 1.0}
    DamageRange(generation=4, rolls=list(range(85, 101)), **base)  # 16 rolls
    DamageRange(generation=1, rolls=list(range(217, 256)), **base)  # 39 rolls
    with pytest.raises(ValidationError, match="16 entries"):
        DamageRange(generation=4, rolls=list(range(217, 256)), **base)
    with pytest.raises(ValidationError, match="immune"):
        DamageRange(generation=4, rolls=[10], **{**base, "type_multiplier": 0})


def test_ko_chance_method():
    KOChance(hits=1, probability=9 / 16, method="exact")
    with pytest.raises(ValidationError):
        KOChance(hits=1, probability=0.41, method="monte_carlo")


def _doc_example_posterior(post_a, post_b, post_c):
    return SetPosterior(
        species_id="tyranitar",
        evidence_moves=["stoneedge"],
        hypotheses=[
            SetHypothesis(set_id="A", moves=["stealthrock", "earthquake", "stoneedge", "toxic"],
                          prior=0.5, posterior=post_a),
            SetHypothesis(set_id="B", moves=["stealthrock", "earthquake", "firepunch", "toxic"],
                          prior=0.3, posterior=post_b),
            SetHypothesis(set_id="C", moves=["spikes", "earthquake", "stoneedge", "icepunch"],
                          prior=0.2, posterior=post_c),
        ],
    )


def test_set_posterior_doc_worked_example():
    # Architecture doc §5.2: Stone Edge revealed -> A 71.4 %, C 28.6 %, B ruled out.
    post = _doc_example_posterior(5 / 7, 0.0, 2 / 7)
    assert post.move_probability("icepunch") == pytest.approx(2 / 7)
    assert post.move_probability("earthquake") == pytest.approx(1.0)


def test_set_posterior_rejects_contradiction():
    with pytest.raises(ValidationError, match="contradicts the evidence"):
        _doc_example_posterior(0.6, 0.1, 0.3)  # B lacks Stone Edge but got mass


def test_action_prediction_sums():
    ActionPrediction(p_attack=0.19, p_switch=0.74, p_utility=0.07, model_version="heuristic-0")
    with pytest.raises(ValidationError, match="sum"):
        ActionPrediction(p_attack=0.5, p_switch=0.74, p_utility=0.07, model_version="x")


def test_subsystem_result_fallback_needs_payload():
    ap = ActionPrediction(p_attack=1, p_switch=0, p_utility=0, model_version="default")
    SubsystemResult[ActionPrediction](status="fallback", latency_ms=3, payload=ap)
    with pytest.raises(ValidationError, match="requires an error"):
        SubsystemResult[ActionPrediction](status="timeout", latency_ms=150)


# ------------------------------------------------------------------ synthesis guardrail


def _rec(**kw):
    base = {"action": "move", "move_id": "earthquake", "headline": "74% switch odds -> Earthquake",
                "explanation": "Starmie is likely to switch; Earthquake hits the likely switch-ins.",
                "cited_numbers": {"p_switch": 0.74}}
    return base | kw


def test_recommendation_legal(gen4_state):
    Recommendation.model_validate(_rec(), context={"state": gen4_state,
                                                   "allowed_numbers": {"p_switch": 0.74}})


def test_recommendation_illegal_move_rejected(gen4_state):
    with pytest.raises(ValidationError, match="illegal move"):
        Recommendation.model_validate(_rec(move_id="icebeam"), context={"state": gen4_state})


def test_recommendation_illegal_switch_rejected(gen4_state):
    with pytest.raises(ValidationError, match="illegal switch"):
        Recommendation.model_validate(
            _rec(action="switch", move_id=None, switch_index=0), context={"state": gen4_state})


def test_recommendation_invented_number_rejected(gen4_state):
    # Rule 1: the LLM cannot cite a number no subsystem produced.
    with pytest.raises(ValidationError, match="not produced by a subsystem"):
        Recommendation.model_validate(
            _rec(cited_numbers={"p_switch": 0.80}),
            context={"state": gen4_state, "allowed_numbers": {"p_switch": 0.74}})
