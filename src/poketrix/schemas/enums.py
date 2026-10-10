"""Enumerations shared by every layer.

Values are Showdown-style lowercase ids where Showdown has one, so the battle-log parser
can map protocol strings onto these without a lookup table.
"""

from enum import Enum, IntEnum


class Generation(IntEnum):
    RBY = 1
    GSC = 2
    ADV = 3
    DPP = 4


class PokemonType(str, Enum):
    NORMAL = "normal"
    FIRE = "fire"
    WATER = "water"
    ELECTRIC = "electric"
    GRASS = "grass"
    ICE = "ice"
    FIGHTING = "fighting"
    POISON = "poison"
    GROUND = "ground"
    FLYING = "flying"
    PSYCHIC = "psychic"
    BUG = "bug"
    ROCK = "rock"
    GHOST = "ghost"
    DRAGON = "dragon"
    DARK = "dark"  # Gen 2+
    STEEL = "steel"  # Gen 2+
    TYPELESS = "???"  # Curse's type in Gens 2-4; never a Pokémon's type here


class MoveCategory(str, Enum):
    PHYSICAL = "physical"
    SPECIAL = "special"
    STATUS = "status"


class Stat(str, Enum):
    HP = "hp"
    ATK = "atk"
    DEF = "def"
    SPA = "spa"  # in Gen 1 this *is* the single Special stat
    SPD = "spd"  # in Gen 1 always equal to SPA
    SPE = "spe"


class BoostStat(str, Enum):
    ATK = "atk"
    DEF = "def"
    SPA = "spa"
    SPD = "spd"
    SPE = "spe"
    ACCURACY = "accuracy"
    EVASION = "evasion"


class Status(str, Enum):
    BURN = "brn"
    PARALYSIS = "par"
    SLEEP = "slp"
    FREEZE = "frz"
    POISON = "psn"
    TOXIC = "tox"


class Weather(str, Enum):
    NONE = "none"
    RAIN = "raindance"  # Gen 2+
    SUN = "sunnyday"  # Gen 2+
    SANDSTORM = "sandstorm"  # Gen 2+
    HAIL = "hail"  # Gen 3+


class SideCondition(str, Enum):
    REFLECT = "reflect"
    LIGHT_SCREEN = "lightscreen"
    MIST = "mist"
    SAFEGUARD = "safeguard"  # Gen 2+
    SPIKES = "spikes"  # Gen 2+ (1 layer in Gen 2, 3 layers from Gen 3)
    STEALTH_ROCK = "stealthrock"  # Gen 4
    TOXIC_SPIKES = "toxicspikes"  # Gen 4, 2 layers
    TAILWIND = "tailwind"  # Gen 4
    LUCKY_CHANT = "luckychant"  # Gen 4


class PlayerSlot(str, Enum):
    P1 = "p1"
    P2 = "p2"


class ActionKind(str, Enum):
    MOVE = "move"
    SWITCH = "switch"


class SubsystemStatus(str, Enum):
    OK = "ok"
    FALLBACK = "fallback"  # deterministic default used instead of the real subsystem
    TIMEOUT = "timeout"
    ERROR = "error"
