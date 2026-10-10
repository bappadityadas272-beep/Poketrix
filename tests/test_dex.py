"""Task 02 acceptance tests: the committed Gen 1-4 dex snapshot and the `Dex` lookup API."""

import json

import pytest
from pydantic import ValidationError

from poketrix.dex import Dex, UnknownDexEntryError
from poketrix.schemas import Generation, MoveCategory, PokemonType, rules_for

GENS = list(Generation)


def stats(species):
    b = species.base_stats
    return (b.hp, b.atk, b.def_, b.spa, b.spd, b.spe)


# --------------------------------------------------------------------------- whole snapshot


@pytest.mark.parametrize("gen", GENS)
def test_snapshot_validates_and_is_stamped_with_its_generation(gen):
    dex = Dex(gen)  # loading validates every record against the schemas
    assert dex.all_species() and dex.all_moves()
    assert all(s.generation is gen for s in dex.all_species())
    assert all(m.generation is gen for m in dex.all_moves())


@pytest.mark.parametrize("gen", GENS)
def test_every_dex_number_present_exactly_up_to_gen_max(gen):
    numbers = {s.dex_number for s in Dex(gen).all_species()}
    assert numbers == set(range(1, rules_for(gen).max_dex + 1))


def test_species_counts_per_generation():
    counts = [len({s.dex_number for s in Dex(g).all_species()}) for g in GENS]
    assert counts == [151, 251, 386, 493]


@pytest.mark.parametrize("gen", GENS)
def test_abilities_only_from_gen3(gen):
    with_abilities = [s for s in Dex(gen).all_species() if s.possible_abilities]
    if rules_for(gen).has_abilities:
        assert len(with_abilities) == len(Dex(gen).all_species())
    else:
        assert not with_abilities


# --------------------------------------------------------------------------- per-gen content


def test_magnemite_gains_steel_in_gen2():
    assert Dex(1).species("magnemite").types == (PokemonType.ELECTRIC,)
    assert Dex(2).species("magnemite").types == (PokemonType.ELECTRIC, PokemonType.STEEL)


def test_gen1_gengar_single_special_130():
    gengar = Dex(1).species("gengar")
    assert gengar.base_stats.spa == gengar.base_stats.spd == 130
    assert Dex(2).species("gengar").base_stats.spd == 75


def test_fire_punch_category_follows_the_gen4_split():
    assert Dex(3).move("firepunch").category is MoveCategory.SPECIAL
    assert Dex(4).move("firepunch").category is MoveCategory.PHYSICAL


def test_bite_is_normal_in_gen1_dark_after():
    bite = Dex(1).move("bite")
    assert (bite.type, bite.base_power) == (PokemonType.NORMAL, 60)
    assert all(Dex(g).move("bite").type is PokemonType.DARK for g in (2, 3, 4))


def test_gen4_garchomp_base_stats():
    garchomp = Dex(4).species("garchomp")
    assert stats(garchomp) == (108, 130, 95, 80, 85, 102)
    assert garchomp.possible_abilities == ["sandveil"]


def test_gen1_bide_is_normal_not_typeless():
    assert Dex(1).move("bide").type is PokemonType.NORMAL
    assert Dex(2).move("curse").type is PokemonType.TYPELESS


def test_typed_hidden_powers_have_their_own_ids():
    assert Dex(4).move("hiddenpower").base_power == 0  # type and power come from IVs
    assert Dex(4).move("Hidden Power Fire").type is PokemonType.FIRE
    assert Dex(3).move("hiddenpowerbug").category is MoveCategory.PHYSICAL
    assert Dex(4).move("hiddenpowerbug").category is MoveCategory.SPECIAL


def test_later_gen_abilities_are_not_backported():
    assert Dex(3).species("pidgey").possible_abilities == ["keeneye"]
    assert Dex(4).species("pidgey").possible_abilities == ["keeneye", "tangledfeet"]


def test_battle_formes_share_the_base_dex_number():
    wash = Dex(4).species("Rotom-Wash")
    assert wash.dex_number == Dex(4).species("rotom").dex_number == 479
    assert stats(wash) != stats(Dex(4).species("rotom"))
    assert stats(Dex(3).species("deoxysspeed"))[5] == 180


# --------------------------------------------------------------------------- lookup API


def test_lookup_accepts_display_names():
    assert Dex(4).move("Stone Edge").id == "stoneedge"
    assert Dex(1).species("Mr. Mime").id == "mrmime"


def test_lookups_are_cached_across_instances():
    assert Dex(4).species("garchomp") is Dex(4).species("garchomp")


@pytest.mark.parametrize(
    ("gen", "kind", "entry"),
    [(4, "species", "notapokemon"), (3, "species", "garchomp"), (1, "move", "stoneedge")],
)
def test_unknown_id_raises_clear_keyerror(gen, kind, entry):
    with pytest.raises(KeyError) as exc:
        getattr(Dex(gen), kind)(entry)
    assert isinstance(exc.value, UnknownDexEntryError)
    assert str(exc.value) == f"unknown {kind} {entry!r} in Gen {gen}"


@pytest.mark.parametrize("gen", [0, 5, 9])
def test_unsupported_generation_rejected(gen):
    with pytest.raises(ValueError, match="unsupported generation"):
        Dex(gen)


# --------------------------------------------------------------------------- bad data fails loudly


def write_snapshot(root, gen, species, moves):
    gen_dir = root / f"gen{gen}"
    gen_dir.mkdir(parents=True)
    (gen_dir / "species.json").write_text(json.dumps(species), encoding="utf-8")
    (gen_dir / "moves.json").write_text(json.dumps(moves), encoding="utf-8")


MAGNEMITE = {
    "id": "magnemite", "name": "Magnemite", "dex_number": 81, "types": ["electric"],
    "base_stats": {"hp": 25, "atk": 35, "def": 70, "spa": 95, "spd": 95, "spe": 45},
    "possible_abilities": [],
}


def test_schema_violation_in_snapshot_fails_at_load(tmp_path):
    write_snapshot(tmp_path, 1, [{**MAGNEMITE, "types": ["electric", "steel"]}], [])
    with pytest.raises(ValidationError, match="not available to Pokémon in Gen 1"):
        Dex(1, data_dir=tmp_path)


def test_duplicate_id_in_snapshot_fails_at_load(tmp_path):
    write_snapshot(tmp_path, 1, [MAGNEMITE, MAGNEMITE], [])
    with pytest.raises(ValueError, match="duplicate id 'magnemite'"):
        Dex(1, data_dir=tmp_path)


def test_missing_snapshot_names_the_rebuild_script(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_dex"):
        Dex(1, data_dir=tmp_path)
