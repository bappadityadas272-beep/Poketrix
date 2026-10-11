"""Follows a battle event by event and produces a validated `GameState` whenever asked.

The tracker is the only place battle state changes. It keeps more than a `GameState` holds:
nicknames, the item a Pokémon holds now as opposed to the one it started with, and the short
memory the evidence rules need (what happened since the last move, during this turn).
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from poketrix.dex import Dex, UnknownDexEntryError
from poketrix.schemas import (
    HAZARDS,
    BattlePokemon,
    BoostStat,
    FieldState,
    GameState,
    Generation,
    MoveCategory,
    PlayerSlot,
    SetEvidence,
    SideCondition,
    SideState,
    Species,
    Status,
    Weather,
    rules_for,
)

from . import events as ev
from .evidence import (
    ABSORBING_ABILITIES,
    END_OF_TURN_RECOVERY_ITEMS,
    EvidenceBook,
    chose_the_move,
)

_STANDARD_DURATION = 5  # turns of weather, screens, Trick Room and Gravity without an item
_ITEM_SWAPPING_MOVES = frozenset({"trick", "switcheroo", "thief", "covet"})
_ABILITY_SWAPPING_MOVES = frozenset({"skillswap", "roleplay", "worryseed", "gastroacid"})
_BATON_PASSED = frozenset({
    "substitute", "focusenergy", "leechseed", "confusion", "ingrain", "curse",
})
_BLOCKS_ITEM_RECOVERY = frozenset({"embargo", "healblock"})
_GEN1_SCREENS = {"reflect": SideCondition.REFLECT, "lightscreen": SideCondition.LIGHT_SCREEN}
# Moves whose type in battle is not the one the dex lists; they prove nothing about immunities.
_TYPE_VARIES = frozenset({"weatherball", "judgment", "naturalgift"})
# `[from]` sources of end-of-turn HP changes. Seeing one means the last move has fully resolved.
_END_OF_TURN_SOURCES = frozenset({
    "psn", "tox", "brn", "sandstorm", "hail", "leechseed", "curse", "nightmare",
    "partiallytrapped", "leftovers", "blacksludge", "stickybarb",
})
_DELAYED_DAMAGE = frozenset({"futuresight", "doomdesire"})  # lands at the end of a later turn
_SIDE_CONDITIONS = {condition.value: condition for condition in SideCondition}
_OTHER = {PlayerSlot.P1: PlayerSlot.P2, PlayerSlot.P2: PlayerSlot.P1}


@dataclass
class _Mon:
    nickname: str
    species: Species  # the current forme
    set_species_id: str  # the forme it was first sent out as: its identity for the uncloaker
    level: int
    book: EvidenceBook
    hp_fraction: float = 1.0
    fainted: bool = False
    status: Status | None = None
    boosts: dict[BoostStat, int] = field(default_factory=dict)
    volatiles: set[str] = field(default_factory=set)
    held_item: str | None = None  # what it holds now, as far as the log has shown
    item_lost: bool = False
    ability: str | None = None  # its ability now, as far as the log has shown
    transformed: bool = False
    mimicked_move: str | None = None
    # Memory for the "no Leftovers recovery" rule, reset every turn. `seen_at_full_hp` is
    # cleared when a move leaves the Pokémon damaged, which always happens before the
    # end-of-turn effects; later end-of-turn damage does not clear it, because that can come
    # after the moment Leftovers would have acted.
    seen_at_full_hp: bool = True
    recovered_by_item: bool = False

    def leave_field(self) -> None:
        self.boosts.clear()
        self.volatiles.clear()
        self.transformed = False
        self.mimicked_move = None
        self.book.left_the_field()


@dataclass
class _Side:
    name: str = ""
    team_size: int = 6
    mons: list[_Mon] = field(default_factory=list)
    active: _Mon | None = None
    conditions: dict[SideCondition, int] = field(default_factory=dict)  # hazard -> layers
    started: dict[SideCondition, int] = field(default_factory=dict)  # timed -> turn it began


@dataclass
class _Attack:
    """The move in progress: what the evidence rules need to know about it."""

    attacker: _Mon
    defender: _Mon | None
    move_id: str
    chosen: bool
    target_lost_hp: bool = False
    life_orb_recoil: bool = False


class BattleTracker:
    def __init__(self) -> None:
        self.gen: Generation | None = None
        self.format_id = ""
        self.turn = 0
        self.winner: str | None = None
        self.ended = False
        self.unknown: Counter[str] = Counter()
        # How often each evidence rule fired: shows which rules a corpus actually exercised.
        self.rules: Counter[str] = Counter()
        self._sides = {slot: _Side() for slot in PlayerSlot}
        self._weather = Weather.NONE
        self._weather_since: int | None = None  # None: started by an ability, open-ended
        self._field_since: dict[str, int] = {}  # "trickroom" / "gravity" -> turn it began
        self._attack: _Attack | None = None
        # Pokémon whose items the item lines being read right now have swapped (Trick shows as
        # two lines): each still counts as "before the swap" when the other line names its item.
        self._swapping: set[int] = set()
        self._after_upkeep = False
        self._dex: Dex | None = None
        self._item_ids: frozenset[str] = frozenset()
        self._handlers: dict[type, Callable] = {
            ev.SetupEvent: self._on_setup,
            ev.TurnEvent: self._on_turn,
            ev.UpkeepEvent: self._on_upkeep,
            ev.EndEvent: self._on_end,
            ev.MoveEvent: self._on_move,
            ev.SwitchEvent: self._on_switch,
            ev.FormeEvent: self._on_forme,
            ev.CantEvent: self._on_cant,
            ev.FaintEvent: self._on_faint,
            ev.HpEvent: self._on_hp,
            ev.StatusEvent: self._on_status,
            ev.CureTeamEvent: self._on_cure_team,
            ev.BoostEvent: self._on_boost,
            ev.WeatherEvent: self._on_weather,
            ev.FieldEvent: self._on_field,
            ev.SideEvent: self._on_side,
            ev.VolatileEvent: self._on_volatile,
            ev.ItemEvent: self._on_item,
            ev.AbilityEvent: self._on_ability,
            ev.TransformEvent: self._on_transform,
            ev.TagEvent: self._on_tag,
            ev.UnknownEvent: lambda event: self.unknown.update([event.kind]),
        }

    # ------------------------------------------------------------------ public

    def apply(self, event: ev.Event) -> None:
        if not isinstance(event, ev.ItemEvent):
            self._swapping.clear()
        self._handlers[type(event)](event)

    @property
    def anomalies(self) -> list[str]:
        """Things the evidence rules did not expect (a fifth own move, two original items)."""
        return [
            f"{slot.value} {mon.nickname}: {text}"
            for slot, side in self._sides.items()
            for mon in side.mons
            for text in mon.book.anomalies
        ]

    def evidence(self) -> dict[tuple[PlayerSlot, int], SetEvidence]:
        """Evidence about every revealed Pokémon, keyed by (player, index in the team)."""
        return {
            (slot, index): mon.book.evidence()
            for slot, side in self._sides.items() for index, mon in enumerate(side.mons)
        }

    def set_species_id(self, slot: PlayerSlot, index: int) -> str:
        return self._sides[slot].mons[index].set_species_id

    def state(self, perspective: PlayerSlot = PlayerSlot.P1) -> GameState:
        """A validated snapshot. Needs both leads on the field."""
        return GameState(
            generation=self.gen, format_id=self.format_id, turn=self.turn,
            perspective=perspective,
            sides={slot: self._side_state(slot) for slot in PlayerSlot},
            field=self._field_state(),
        )

    # ------------------------------------------------------------------ snapshots

    def _elapsed_left(self, since: int) -> int:
        return max(1, _STANDARD_DURATION - (self.turn - since))

    def _field_state(self) -> FieldState:
        def left(key: str) -> int:
            return self._elapsed_left(self._field_since[key]) if key in self._field_since else 0

        weather_left = None
        if self._weather is not Weather.NONE and self._weather_since is not None:
            weather_left = self._elapsed_left(self._weather_since)
        return FieldState(
            weather=self._weather, weather_turns_left=weather_left,
            trick_room_turns_left=left("trickroom"), gravity_turns_left=left("gravity"),
        )

    def _side_state(self, slot: PlayerSlot) -> SideState:
        side = self._sides[slot]
        conditions = dict(side.conditions)
        conditions.update({c: self._elapsed_left(since) for c, since in side.started.items()})
        # In Gen 1 Reflect and Light Screen sit on the Pokémon, not on its side of the field.
        if side.active is not None:
            for volatile, condition in _GEN1_SCREENS.items():
                if volatile in side.active.volatiles:
                    conditions[condition] = 1
        return SideState(
            player=slot, name=side.name or None, team_size=max(side.team_size, len(side.mons)),
            team=[self._battle_pokemon(mon) for mon in side.mons],
            active_index=None if side.active is None else side.mons.index(side.active),
            conditions=conditions,
        )

    def _battle_pokemon(self, mon: _Mon) -> BattlePokemon:
        rules = rules_for(self.gen)
        return BattlePokemon(
            species=mon.species, level=mon.level,
            hp_fraction=0.0 if mon.fainted else mon.hp_fraction,
            status=None if mon.fainted else mon.status,
            boosts={stat: stage for stat, stage in mon.boosts.items() if stage},
            volatiles=set(mon.volatiles),
            revealed_moves=list(mon.book.moves),
            revealed_item=mon.held_item if rules.has_items and not mon.item_lost else None,
            item_consumed=mon.item_lost and rules.has_items,
            revealed_ability=mon.ability if rules.has_abilities else None,
        )

    # ------------------------------------------------------------------ lookups

    def _mon(self, ref: ev.PokemonRef) -> _Mon:
        side = self._sides[ref.player]
        for mon in side.mons:
            if mon.nickname == ref.name:
                return mon
        raise KeyError(f"{ref.player.value}: {ref.name} was never sent out")

    def _species(self, name: str) -> Species:
        """The dex entry for a species name; cosmetic formes fall back to their base species."""
        while True:
            try:
                return self._dex.species(name)
            except UnknownDexEntryError:
                name, separator, _ = name.rpartition("-")
                if not separator:
                    raise

    # ------------------------------------------------------------------ evidence bookkeeping

    def _credit_tag(
        self, event: ev.Event, pokemon: ev.PokemonRef | None, of_owns_ability: bool = False
    ) -> None:
        """A `[from] item: X` or `[from] ability: X` tag reveals X on its owner.

        An item is always the line's own Pokémon's (Leftovers, Life Orb, a status orb). An
        ability's owner depends on the line: `[of]` names the owner when the ability acted on
        someone else (Static paralysing, Intimidate lowering, Sand Stream starting weather:
        `of_owns_ability`), but on a heal `[of]` is the attacker whose move was absorbed. Where
        the line does not settle it, nothing is concluded.
        """
        source = event.source
        if source is None or source.kind not in ("item", "ability"):
            return
        if source.kind == "item":
            if pokemon is not None:
                self.rules["item: named by a [from] tag"] += 1
                self._holds(self._mon(pokemon), source.id)
            return
        if event.of is not None and of_owns_ability:
            self.rules["ability: [from] tag, owner is [of]"] += 1
            self._has_ability(self._mon(event.of), source.id)
        elif pokemon is not None and event.of in (None, pokemon):
            self.rules["ability: [from] tag, owner is the line's Pokémon"] += 1
            self._has_ability(self._mon(pokemon), source.id)

    def _holds(self, mon: _Mon, item_id: str) -> None:
        if not mon.item_lost:
            mon.held_item = item_id
        mon.book.saw_item(item_id)

    def _mark_swapped(self, mon: _Mon) -> None:
        if not mon.book.item_swapped:
            mon.book.item_swapped = True
            self._swapping.add(id(mon))

    def _has_ability(self, mon: _Mon, ability_id: str) -> None:
        if not mon.book.ability_changed:
            mon.ability = ability_id
        mon.book.saw_ability(ability_id)

    def _rule_out_items(self, mon: _Mon, rule: str, *item_ids: str) -> None:
        before = len(mon.book.ruled_out_items)
        mon.book.rule_out_items(*item_ids)
        self.rules[rule] += len(mon.book.ruled_out_items) > before

    def _close_attack(self, battle_over: bool = False) -> None:
        """N2: a chosen damaging move hit, and no Life Orb recoil followed."""
        attack, self._attack = self._attack, None
        if attack is None or battle_over or self.gen is not Generation.DPP:
            return
        attacker = attack.attacker
        if not (attack.chosen and attack.target_lost_hp) or attack.life_orb_recoil:
            return
        no_recoil_possible = attacker.book.may_have("magicguard") or attacker.book.may_have("klutz")
        if attacker.fainted or no_recoil_possible:
            return
        self._rule_out_items(attacker, "N2: no Life Orb recoil", "lifeorb")

    def _close_turn(self) -> None:
        """N1: on the field all turn below full HP, and no Leftovers-style recovery came."""
        if not rules_for(self.gen).has_items:
            return
        for side in self._sides.values():
            mon = side.active
            if mon is None or mon.fainted or mon.seen_at_full_hp or mon.recovered_by_item:
                continue
            if mon.book.may_have("klutz") or mon.volatiles & _BLOCKS_ITEM_RECOVERY:
                continue
            self._rule_out_items(mon, "N1: no end-of-turn recovery", *END_OF_TURN_RECOVERY_ITEMS)

    def _took_move_damage(self, attack: _Attack) -> None:
        """N4: losing HP to a move excludes the abilities that would have absorbed it."""
        attack.target_lost_hp = True
        defender, attacker = attack.defender, attack.attacker
        if not rules_for(self.gen).has_abilities or defender is None:
            return
        try:
            move = self._dex.move(attack.move_id)
        except UnknownDexEntryError:
            return
        if (
            move.ignores_type_chart or move.id in _TYPE_VARIES or move.id.startswith("hiddenpower")
            or attacker.book.may_have("moldbreaker") or attacker.book.may_have("normalize")
            or attacker.transformed or defender.transformed
        ):
            return
        abilities = ABSORBING_ABILITIES.get(move.type, ())
        grounded = "gravity" in self._field_since or "ingrain" in defender.volatiles
        if "levitate" in abilities and grounded:
            return
        if defender.book.item_swapped:  # an Iron Ball could have been passed on
            abilities = tuple(a for a in abilities if a != "levitate")
        before = len(defender.book.ruled_out_abilities)
        defender.book.rule_out_abilities(*abilities)
        self.rules["N4: damaged through an absorbing ability"] += (
            len(defender.book.ruled_out_abilities) > before
        )

    # ------------------------------------------------------------------ handlers

    def _on_setup(self, event: ev.SetupEvent) -> None:
        if event.key == "player":
            self._sides[event.player].name = event.value
        elif event.key == "teamsize":
            self._sides[event.player].team_size = int(event.value)
        elif event.key == "gen":
            self.gen = Generation(int(event.value))
            self._dex = Dex(self.gen)
            self._item_ids = frozenset(item.id for item in self._dex.all_items())
        elif event.key == "tier":
            self.format_id = "".join(c for c in event.value.lower() if c.isalnum())
        elif event.key == "gametype" and event.value != "singles":
            raise ValueError(f"only singles battles are supported, not {event.value!r}")

    def _on_turn(self, event: ev.TurnEvent) -> None:
        self._close_attack()
        if self.turn:
            self._close_turn()
        self.turn = event.number
        self._after_upkeep = False
        for side in self._sides.values():
            if side.active is not None:
                side.active.seen_at_full_hp = side.active.hp_fraction >= 1.0
                side.active.recovered_by_item = False

    def _on_upkeep(self, event: ev.UpkeepEvent) -> None:
        self._close_attack()
        self._after_upkeep = True

    def _on_end(self, event: ev.EndEvent) -> None:
        self._close_attack(battle_over=True)
        self.winner, self.ended = event.winner, True

    def _on_move(self, event: ev.MoveEvent) -> None:
        self._close_attack()
        mon = self._mon(event.pokemon)
        chosen = self._chose(mon, event)
        if chosen:
            before = len(mon.book.ruled_out_items)
            mon.book.chose(event.move_id)
            self.rules["N3: second move in one stay"] += len(mon.book.ruled_out_items) > before
        defender = self._sides[_OTHER[event.pokemon.player]].active
        damaging = False
        try:
            move = self._dex.move(event.move_id)
            damaging = move.category is not MoveCategory.STATUS and move.fixed_damage is None
        except UnknownDexEntryError:
            pass
        self._attack = _Attack(mon, defender, event.move_id, chosen and damaging)

    def _chose(self, mon: _Mon, event: ev.MoveEvent) -> bool:
        """Whether the move is one of the Pokémon's own four, counting why when it is not."""
        source = event.source
        if not chose_the_move(event.move_id, source):
            called = f"called by {source.id}" if source is not None else "Struggle or recharge"
            self.rules[f"move not revealed: {called}"] += 1
            return False
        if mon.transformed:
            self.rules["move not revealed: used while transformed"] += 1
            return False
        if event.move_id == mon.mimicked_move:
            self.rules["move not revealed: gained through Mimic"] += 1
            return False
        if source is not None:
            self.rules["move revealed: continuation of its own move"] += 1
        return True

    def _on_switch(self, event: ev.SwitchEvent) -> None:
        self._close_attack()
        side = self._sides[event.pokemon.player]
        previous = side.active
        species = self._species(event.species_name)
        mon = next((m for m in side.mons if m.nickname == event.pokemon.name), None)
        if mon is None:
            book = EvidenceBook(species, self._item_ids)
            mon = _Mon(event.pokemon.name, species, species.id, event.level, book)
            side.mons.append(mon)
        baton_pass = event.source is not None and event.source.id == "batonpass"
        passed = baton_pass and previous is not None
        boosts = dict(previous.boosts) if passed else {}
        volatiles = previous.volatiles & _BATON_PASSED if passed else set()
        if previous is not None and previous is not mon:
            previous.leave_field()
        mon.species, mon.level = species, event.level
        mon.boosts, mon.volatiles = boosts, set(volatiles)
        self._set_hp(mon, event.hp)
        # A Pokémon that arrives after the end-of-turn effects cannot have been healed by them.
        mon.seen_at_full_hp = self._after_upkeep or mon.hp_fraction >= 1.0
        mon.recovered_by_item = False
        side.active = mon

    def _on_forme(self, event: ev.FormeEvent) -> None:
        self._credit_tag(event, event.pokemon)
        self._mon(event.pokemon).species = self._species(event.species_name)

    def _on_cant(self, event: ev.CantEvent) -> None:
        self._close_attack()
        self._credit_tag(event, event.pokemon)

    def _on_faint(self, event: ev.FaintEvent) -> None:
        mon = self._mon(event.pokemon)
        mon.fainted, mon.hp_fraction, mon.status = True, 0.0, None

    def _set_hp(self, mon: _Mon, hp: ev.Hp) -> None:
        mon.hp_fraction = hp.fraction
        mon.fainted = hp.fainted
        mon.status = None if hp.fainted else hp.status
        if mon.hp_fraction >= 1.0:
            mon.seen_at_full_hp = True

    def _on_hp(self, event: ev.HpEvent) -> None:
        mon = self._mon(event.pokemon)
        if event.change == "heal":  # Water Absorb, Poison Heal: the healed Pokémon's own ability
            self._credit_tag(event.model_copy(update={"of": None}), event.pokemon)
        else:  # Rough Skin, Liquid Ooze: the ability of the Pokémon named by [of]
            self._credit_tag(event, event.pokemon, of_owns_ability=True)
        source = event.source
        if source is not None and source.id in _END_OF_TURN_SOURCES:
            self._close_attack()
        attack = self._attack
        if source is not None and source.kind == "item" and event.of is None:
            if event.change == "heal" and source.id in END_OF_TURN_RECOVERY_ITEMS:
                mon.recovered_by_item = True
            if attack is not None and source.id == "lifeorb" and mon is attack.attacker:
                attack.life_orb_recoil = True
        if (
            event.change == "damage" and source is None and attack is not None
            and mon is attack.defender and mon is not attack.attacker
        ):
            self._took_move_damage(attack)
            self._set_hp(mon, event.hp)
            if mon.hp_fraction < 1.0 and not self._after_upkeep:
                mon.seen_at_full_hp = False
            return
        self._set_hp(mon, event.hp)

    def _on_status(self, event: ev.StatusEvent) -> None:
        self._credit_tag(event, event.pokemon, of_owns_ability=not event.cured)
        self._mon(event.pokemon).status = None if event.cured else event.status

    def _on_cure_team(self, event: ev.CureTeamEvent) -> None:
        for mon in self._sides[event.pokemon.player].mons:
            mon.status = None

    def _on_boost(self, event: ev.BoostEvent) -> None:
        self._credit_tag(event, event.pokemon, of_owns_ability=True)
        if event.op == "clearall":
            for side in self._sides.values():
                if side.active is not None:
                    side.active.boosts.clear()
            return
        mon = self._mon(event.pokemon)
        boosts = mon.boosts
        if event.op in ("boost", "unboost"):
            change = event.amount if event.op == "boost" else -event.amount
            boosts[event.stat] = max(-6, min(6, boosts.get(event.stat, 0) + change))
        elif event.op == "set":
            boosts[event.stat] = event.amount
        elif event.op == "clear":
            boosts.clear()
        elif event.op == "clearpositive":
            mon.boosts = {stat: stage for stat, stage in boosts.items() if stage < 0}
        elif event.op == "clearnegative":
            mon.boosts = {stat: stage for stat, stage in boosts.items() if stage > 0}
        elif event.op == "copy":
            mon.boosts = dict(self._mon(event.other).boosts)
        elif event.op == "swap":
            other = self._mon(event.other)
            for stat in event.stats or tuple(BoostStat):
                mine, theirs = boosts.get(stat, 0), other.boosts.get(stat, 0)
                boosts[stat], other.boosts[stat] = theirs, mine

    def _on_weather(self, event: ev.WeatherEvent) -> None:
        if event.upkeep:  # the end-of-turn phase has begun
            self._close_attack()
        self._credit_tag(event, None, of_owns_ability=True)
        if event.weather is not self._weather or not event.upkeep:
            by_ability = event.source is not None and event.source.kind == "ability"
            self._weather_since = None if by_ability else self.turn
        self._weather = event.weather

    def _on_field(self, event: ev.FieldEvent) -> None:
        if event.condition_id not in ("trickroom", "gravity"):
            return
        if event.started:
            self._field_since[event.condition_id] = self.turn
        else:
            self._field_since.pop(event.condition_id, None)

    def _on_side(self, event: ev.SideEvent) -> None:
        condition = _SIDE_CONDITIONS.get(event.condition_id)
        side = self._sides[event.player]
        max_layers = rules_for(self.gen).side_condition_max_layers
        if condition is None or condition not in max_layers:
            return
        if not event.started:
            side.conditions.pop(condition, None)
            side.started.pop(condition, None)
        elif condition in HAZARDS:
            layers = side.conditions.get(condition, 0) + 1
            side.conditions[condition] = min(max_layers[condition], layers)
        else:
            side.started[condition] = self.turn

    def _on_volatile(self, event: ev.VolatileEvent) -> None:
        mon = self._mon(event.pokemon)
        self._credit_tag(event, event.pokemon)
        effect = event.effect
        if effect.id in _DELAYED_DAMAGE:  # its damage is not from the move in progress
            self._close_attack()
        if effect.kind == "ability":  # `-start|P|ability: Flash Fire`: the ability is P's own
            self.rules["ability: named as the effect itself"] += 1
            self._has_ability(mon, effect.id)
        if effect.id == "mimic" and event.detail:
            mon.mimicked_move = "".join(c for c in event.detail.lower() if c.isalnum())
        if effect.id in _ABILITY_SWAPPING_MOVES:
            self.rules[f"ability changed by {effect.id}"] += 1
            mon.book.ability_was_changed()
            if event.of is not None:
                self._mon(event.of).book.ability_was_changed()
        if event.phase == "start" and effect.id:
            mon.volatiles.add(effect.id)
        elif event.phase == "end":
            mon.volatiles.discard(effect.id)

    def _on_item(self, event: ev.ItemEvent) -> None:
        if event.pokemon is not None:
            mon = self._mon(event.pokemon)
        elif event.of is not None:  # Gen 4 Frisk: the item of the Pokémon facing [of]
            mon = self._sides[_OTHER[event.of.player]].active
        else:
            return
        if mon is None:
            return
        source = event.source
        if source is not None and source.kind == "ability" and event.of is not None:
            # `-item|Q|X|[from] ability: Frisk|[of] P`: the ability is P's, the item Q's.
            self.rules["ability: revealed by showing another's item (Frisk)"] += 1
            self._has_ability(self._mon(event.of), source.id)
        if event.lost:
            self.rules["item: lost (-enditem)"] += 1
            mon.book.saw_item(event.item_id)
            mon.held_item, mon.item_lost = None, True
            return
        swapped = source is not None and source.kind == "move" and source.id in _ITEM_SWAPPING_MOVES
        if swapped:
            # P now holds what the other Pokémon held: that was the *other* one's item.
            self.rules[f"item swapped by {source.id}"] += 1
            opposing = self._sides[_OTHER[event.pokemon.player]].active
            giver = self._mon(event.of) if event.of else opposing
            if giver is not None and giver is not mon:
                first_swap = not giver.book.item_swapped or id(giver) in self._swapping
                giver.book.saw_item(event.item_id, before_swap=first_swap)
                self._mark_swapped(giver)
                if giver.held_item == event.item_id or source.id in ("thief", "covet"):
                    giver.held_item = None
            self._mark_swapped(mon)
            mon.held_item, mon.item_lost = event.item_id, False
            return
        self.rules["item: announced (-item)"] += 1
        mon.item_lost = False  # Recycle brings a used item back
        self._holds(mon, event.item_id)

    def _on_ability(self, event: ev.AbilityEvent) -> None:
        mon = self._mon(event.pokemon)
        source = event.source
        if event.ability_id is None:  # suppressed
            self.rules["ability suppressed (-endability)"] += 1
            mon.book.ability_was_changed()
            mon.ability = None
            return
        if source is not None and source.kind == "ability" and source.id == "trace":
            # `-ability|P|A|[from] ability: Trace|[of] Q`: P has Trace and now copies Q's A.
            self.rules["ability copied by Trace"] += 1
            self._has_ability(mon, "trace")
            if event.of is not None:
                self._has_ability(self._mon(event.of), event.ability_id)
            mon.book.ability_was_changed()
            mon.ability = event.ability_id
            return
        if source is not None and source.kind == "move":  # Role Play, Skill Swap, ...
            self.rules[f"ability changed by {source.id}"] += 1
            mon.book.ability_was_changed()
            mon.ability = event.ability_id
            return
        self.rules["ability: announced (-ability)"] += 1
        self._has_ability(mon, event.ability_id)

    def _on_transform(self, event: ev.TransformEvent) -> None:
        mon = self._mon(event.pokemon)
        self._credit_tag(event, event.pokemon)
        self.rules["transformed"] += 1
        mon.transformed = True
        mon.volatiles.add("transform")
        mon.book.ability_was_changed()

    def _on_tag(self, event: ev.TagEvent) -> None:
        self._credit_tag(event, event.pokemon)
