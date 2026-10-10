import pytest

from poketrix.schemas import (
    ActionRequest,
    BaseStats,
    BattlePokemon,
    GameState,
    Generation,
    PlayerSlot,
    PokemonSet,
    SideState,
    Species,
)


def species(gen, sid, dex, types, stats, abilities=()):
    hp, atk, df, spa, spd, spe = stats
    return Species(
        id=sid, name=sid.title(), generation=gen, dex_number=dex, types=tuple(types),
        base_stats=BaseStats(hp=hp, atk=atk, **{"def": df}, spa=spa, spd=spd, spe=spe),
        possible_abilities=list(abilities),
    )


@pytest.fixture
def garchomp4():
    return species(4, "garchomp", 445, ["dragon", "ground"], (108, 130, 95, 80, 85, 102),
                   ["sandveil"])


@pytest.fixture
def starmie4():
    return species(4, "starmie", 121, ["water", "psychic"], (60, 75, 85, 100, 85, 115),
                   ["illuminate", "naturalcure"])


@pytest.fixture
def gengar1():
    return species(1, "gengar", 94, ["ghost", "poison"], (60, 65, 60, 130, 130, 110))


@pytest.fixture
def gen4_state(garchomp4, starmie4):
    my_set = PokemonSet(
        species=garchomp4, level=76,
        moves=["Earthquake", "Outrage", "Stone Edge", "Swords Dance"],
        item="Choice Scarf", ability="Sand Veil", nature="Jolly",
    )
    me = SideState(
        player=PlayerSlot.P1,
        team=[BattlePokemon(species=garchomp4, level=76, hp_fraction=1.0, hp_current=266,
                            hp_max=266, known_set=my_set),
              BattlePokemon(species=starmie4, level=80, hp_fraction=0.5)],
        active_index=0,
        request=ActionRequest(available_moves=my_set.moves, available_switches=[1]),
    )
    opp = SideState(
        player=PlayerSlot.P2,
        team=[BattlePokemon(species=starmie4, level=79, hp_fraction=0.68,
                            revealed_moves=["surf"])],
        active_index=0, conditions={"stealthrock": 1, "spikes": 2},
    )
    return GameState(generation=Generation.DPP, format_id="gen4randombattle", turn=3,
                     perspective=PlayerSlot.P1, sides={PlayerSlot.P1: me, PlayerSlot.P2: opp})
