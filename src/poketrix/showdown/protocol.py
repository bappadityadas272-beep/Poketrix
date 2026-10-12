"""Turns one line of Showdown's battle protocol into a typed event.

Reference: sim/SIM-PROTOCOL.md of pokemon-showdown 0.11.11. Only Gens 1-4 singles are in scope.
"""

import json
import re
from collections.abc import Callable, Sequence

from poketrix.schemas import BoostStat, PlayerSlot, Status, Weather, to_id

from .events import (
    AbilityEvent,
    BoostEvent,
    CantEvent,
    CureTeamEvent,
    Effect,
    EndEvent,
    Event,
    FaintEvent,
    FieldEvent,
    FormeEvent,
    Hp,
    HpEvent,
    ItemEvent,
    MoveEvent,
    PokemonRef,
    RequestEvent,
    RequestMove,
    RequestPokemon,
    SetupEvent,
    SideEvent,
    StatusEvent,
    SwitchEvent,
    TagEvent,
    TransformEvent,
    TurnEvent,
    UnknownEvent,
    UpkeepEvent,
    VolatileEvent,
    WeatherEvent,
)

# Lines that carry nothing the tracker needs. Dropped without an event.
IGNORED = frozenset({
    "", "t:", "rule", "rated", "c", "c:", "chat", "j", "J", "join", "l", "L", "leave", "n", "N",
    "name", "raw", "html", "uhtml", "uhtmlchange", "inactive", "inactiveoff", "debug", "seed",
    "error", "bigerror", "init", "title", "deinit", "sentchoice", "split", "badge",
    "-crit", "-supereffective", "-resisted", "-miss", "-notarget", "-message", "-anim",
    "-hitcount", "-nothing", "-center", "-combine", "-waiting", "-ohko", "-prepare",
    "-mustrecharge", "message", "clearpoke", "poke", "teampreview", "swap", "replace",
    "-singleturn", "-singlemove", "-block", "-zpower", "-zbroken", "-mega", "-primal", "-burst",
    "-terastallize", "-swapsideconditions", "-fieldactivate", "-invertboost",
})
# Lines whose only use is an item or ability tag.
_TAG_ONLY = frozenset({"-immune", "-fail"})
_WEATHER = {
    "none": Weather.NONE, "raindance": Weather.RAIN, "sunnyday": Weather.SUN,
    "sandstorm": Weather.SANDSTORM, "hail": Weather.HAIL,
}
_EFFECT_KINDS = ("move", "item", "ability")
_FLAG = re.compile(r"\[[a-z]+\]")
_REQUEST = "|request|"
# Gen 1: the simulator says so when a Pokémon is about to use a move it did not pick (the
# cartridge's move-selection glitch, see `runMove` in data/mods/gen1/scripts.ts).
_DESYNC_HINT = "Desync Clause Mod activated"
DESYNC = "desync"
_NO_ABILITY = "noability"  # what a request says in Gens 1-2


def parse_ref(text: str) -> PokemonRef:
    position, _, name = text.partition(": ")
    return PokemonRef(player=PlayerSlot(position[:2]), name=name, active=len(position) > 2)


def parse_effect(text: str) -> Effect:
    kind, separator, name = text.partition(": ")
    if separator and kind in _EFFECT_KINDS:
        return Effect(kind=kind, id=to_id(name))
    return Effect(kind=None, id=to_id(text))


def parse_hp(text: str) -> Hp:
    condition, _, status = text.partition(" ")
    if status == "fnt" or condition == "0":  # some servers write a bare `0`, or `0 slp`
        return Hp(current=0, maximum=None, fainted=True)
    current, _, maximum = condition.partition("/")
    return Hp(current=int(current), maximum=int(maximum), status=Status(status) if status else None)


def parse_details(text: str) -> tuple[str, int]:
    """`Raichu, L74, M` -> ("Raichu", 74). No level means level 100."""
    species, *rest = text.split(", ")
    level = next((int(part[1:]) for part in rest if part[:1] == "L" and part[1:].isdigit()), 100)
    return species, level


def _tags(args: Sequence[str]) -> tuple[list[str], dict]:
    """Split a line's arguments from its trailing `[tag] value` parts."""
    plain: list[str] = []
    tags: dict = {}
    for arg in args:
        if arg.startswith("[from]"):
            tags["source"] = parse_effect(arg[len("[from]"):].strip())
        elif arg.startswith("[of]"):
            tags["of"] = parse_ref(arg[len("[of]"):].strip())
        elif _FLAG.match(arg):  # [still], [miss], [upkeep], [eat], [damage], ...
            tags.setdefault("flags", set()).add(arg.strip())
        else:
            plain.append(arg)
    return plain, tags


def _setup(key: str) -> Callable:
    def parse(args: list[str], tags: dict) -> Event:
        if key in ("player", "teamsize"):
            value = args[1] if args[1:] else ""
            return SetupEvent(key=key, player=PlayerSlot(args[0]), value=value)
        return SetupEvent(key=key, value=args[0] if args else "")

    return parse


def _move(args, tags) -> Event:
    target = parse_ref(args[2]) if len(args) > 2 and _is_ref(args[2]) else None
    return MoveEvent(pokemon=parse_ref(args[0]), move_id=to_id(args[1]), target=target, **tags)


def _switch(forced: bool) -> Callable:
    def parse(args, tags) -> Event:
        species, level = parse_details(args[1])
        return SwitchEvent(
            pokemon=parse_ref(args[0]), species_name=species, level=level, hp=parse_hp(args[2]),
            forced=forced, **tags,
        )

    return parse


def _forme(args, tags) -> Event:
    return FormeEvent(pokemon=parse_ref(args[0]), species_name=parse_details(args[1])[0], **tags)


def _hp(change: str) -> Callable:
    return lambda args, tags: HpEvent(
        change=change, pokemon=parse_ref(args[0]), hp=parse_hp(args[1]), **tags
    )


def _status(cured: bool) -> Callable:
    return lambda args, tags: StatusEvent(
        pokemon=parse_ref(args[0]), status=Status(args[1]), cured=cured, **tags
    )


def _boost(op: str) -> Callable:
    def parse(args, tags) -> Event:
        if op in ("boost", "unboost", "set"):
            return BoostEvent(
                op=op, pokemon=parse_ref(args[0]), stat=BoostStat(args[1]), amount=int(args[2]),
                **tags,
            )
        if op in ("swap", "copy"):
            stats = tuple(BoostStat(s.strip()) for s in args[2].split(",")) if args[2:] else ()
            return BoostEvent(
                op=op, pokemon=parse_ref(args[0]), other=parse_ref(args[1]), stats=stats, **tags
            )
        if op == "clearpositive":  # |-clearpositiveboost|TARGET|POKEMON|EFFECT
            return BoostEvent(op=op, pokemon=parse_ref(args[0]), **tags)
        return BoostEvent(op=op, pokemon=parse_ref(args[0]) if args else None, **tags)

    return parse


def _weather(args, tags) -> Event:
    flags = tags.pop("flags", set())
    return WeatherEvent(weather=_WEATHER[to_id(args[0])], upkeep="[upkeep]" in flags, **tags)


def _field(started: bool) -> Callable:
    return lambda args, tags: FieldEvent(
        started=started, condition_id=parse_effect(args[0]).id, **tags
    )


def _side(started: bool) -> Callable:
    return lambda args, tags: SideEvent(
        started=started, player=PlayerSlot(args[0][:2]), condition_id=parse_effect(args[1]).id,
        **tags,
    )


def _is_ref(text: str) -> bool:
    return text[:2] in ("p1", "p2") and ": " in text


def _volatile(phase: str) -> Callable:
    def parse(args, tags) -> Event:
        if not args or not _is_ref(args[0]) or not args[1:]:  # `-activate|EFFECT`: no Pokémon
            return TagEvent(kind=f"-{phase}", **tags)
        return VolatileEvent(
            phase=phase, pokemon=parse_ref(args[0]), effect=parse_effect(args[1]),
            detail=args[2] if args[2:] else None, **tags,
        )

    return parse


def _item(lost: bool) -> Callable:
    return lambda args, tags: ItemEvent(
        pokemon=parse_ref(args[0]) if _is_ref(args[0]) else None, item_id=to_id(args[1]),
        lost=lost, **tags,
    )


def _ability(args, tags) -> Event:
    ability = to_id(args[1]) if args[1:] else None
    return AbilityEvent(pokemon=parse_ref(args[0]), ability_id=ability, **tags)


def _hint(args, tags) -> Event | None:
    if args and args[0].startswith(_DESYNC_HINT):
        return TagEvent(kind=DESYNC)
    return None  # every other hint is commentary


def _tag_only(kind: str) -> Callable:
    def parse(args, tags) -> Event:
        pokemon = parse_ref(args[0]) if args and _is_ref(args[0]) else None
        return TagEvent(kind=kind, pokemon=pokemon, **tags)

    return parse


def _request_pokemon(data: dict) -> RequestPokemon:
    species, level = parse_details(data["details"])
    ability = to_id(data.get("baseAbility") or "")
    return RequestPokemon(
        pokemon=parse_ref(data["ident"]), species_name=species, level=level,
        hp=parse_hp(data["condition"]), active=bool(data.get("active")), stats=data["stats"],
        moves=tuple(data["moves"]), item_id=to_id(data.get("item") or "") or None,
        ability_id=None if ability in ("", _NO_ABILITY) else ability,
    )


def parse_request(payload: str) -> RequestEvent | None:
    """The JSON of a `|request|` line. An empty request (sent when a battle ends) is `None`."""
    data = json.loads(payload) if payload.strip() else None
    if not data:
        return None
    side = data["side"]
    active = (data.get("active") or [{}])[0]
    return RequestEvent(
        player=PlayerSlot(side["id"]),
        team=tuple(_request_pokemon(pokemon) for pokemon in side["pokemon"]),
        moves=tuple(
            RequestMove(move_id=move["id"], disabled=bool(move.get("disabled")))
            for move in active.get("moves", ())
        ),
        force_switch=any(data.get("forceSwitch") or ()),
        wait=bool(data.get("wait") or data.get("teamPreview")),
        trapped=bool(active.get("trapped")),
    )


_PARSERS: dict[str, Callable[[list[str], dict], Event]] = {
    **{key: _setup(key) for key in ("player", "teamsize", "gen", "tier", "gametype", "start")},
    "turn": lambda args, tags: TurnEvent(number=int(args[0])),
    "upkeep": lambda args, tags: UpkeepEvent(),
    "win": lambda args, tags: EndEvent(winner=args[0]),
    "tie": lambda args, tags: EndEvent(winner=None),
    "move": _move,
    "switch": _switch(forced=False),
    "drag": _switch(forced=True),
    "detailschange": _forme,
    "-formechange": _forme,
    "cant": lambda args, tags: CantEvent(pokemon=parse_ref(args[0]), reason=args[1], **tags),
    "faint": lambda args, tags: FaintEvent(pokemon=parse_ref(args[0])),
    "-damage": _hp("damage"),
    "-heal": _hp("heal"),
    "-sethp": _hp("sethp"),
    "-status": _status(cured=False),
    "-curestatus": _status(cured=True),
    "-cureteam": lambda args, tags: CureTeamEvent(pokemon=parse_ref(args[0]), **tags),
    "-boost": _boost("boost"),
    "-unboost": _boost("unboost"),
    "-setboost": _boost("set"),
    "-clearboost": _boost("clear"),
    "-clearpositiveboost": _boost("clearpositive"),
    "-clearnegativeboost": _boost("clearnegative"),
    "-clearallboost": _boost("clearall"),
    "-swapboost": _boost("swap"),
    "-copyboost": _boost("copy"),
    "-weather": _weather,
    "-fieldstart": _field(started=True),
    "-fieldend": _field(started=False),
    "-sidestart": _side(started=True),
    "-sideend": _side(started=False),
    "-start": _volatile("start"),
    "-end": _volatile("end"),
    "-activate": _volatile("activate"),
    "-item": _item(lost=False),
    "-enditem": _item(lost=True),
    "-ability": _ability,
    "-endability": lambda args, tags: AbilityEvent(
        pokemon=parse_ref(args[0]), ability_id=None, **tags
    ),
    "-transform": lambda args, tags: TransformEvent(
        pokemon=parse_ref(args[0]), target=parse_ref(args[1]), **tags
    ),
    "-hint": _hint,
    **{kind: _tag_only(kind) for kind in _TAG_ONLY},
}


def parse_line(line: str) -> Event | None:
    """One protocol line -> an event; `None` for lines we ignore on purpose (and non-protocol
    text). A message type the parser has never heard of becomes an `UnknownEvent`."""
    if not line.startswith("|"):
        return None
    if line.startswith(_REQUEST):  # JSON: not split into arguments
        return parse_request(line[len(_REQUEST):])
    kind, *args = line[1:].split("|")
    if kind in IGNORED:
        return None
    parser = _PARSERS.get(kind)
    if parser is None:
        return UnknownEvent(kind=kind)
    plain, tags = _tags(args)
    if parser is not _weather:
        tags.pop("flags", None)
    return parser(plain, tags)
