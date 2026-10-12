"""Decision policy v0: one score per legal action, no learning, no randomness.

Every quantity is a share of the HP a Pokémon has *left*, between 0 and 1, so a certain
knock-out is 1 whatever was left and damage past a knock-out counts for nothing.

    d, k    our move: expected share of their remaining HP it removes; chance it knocks out
    D, K    their best move against one of ours: expected share; chance it knocks out
    f       chance that we act first
    a       chance that they attack this turn (never below `a_floor`)
    γ       tempo: what a second exchange is worth next to the one happening now

    act(m)    = 1 − a·K·(1 − f)            we get to act: they do not knock us out first
    trade(m)  = d·act − a·D·(1 − k·f)
                We deal our damage if we get to act; we take theirs unless we knock them out
                first.
    M(X)      = the best trade(m) of X's moves with a = 1: how X fares against their Pokémon.
    stay, m   : S = trade(m) + γ·P(we survive)·[(1 − k·act)·M + k·act·max(M, 0)]
                The second exchange is against their Pokémon if it is still there (M, with
                M = M(active)). If we knocked it out, we cannot be worse off than still
                facing it: a knock-out ends a bad matchup's cost and keeps a good one's value.
    switch, X : S = −a·D(X) − hazard(X) + γ·P(X survives the hit)·M(X)
    forced    : S = M(X) − hazard(X)

A move that makes its user faint (Explosion, Self-Destruct) costs everything we have left:
trade(m) = d·act − 1, and there is no second exchange.

Worked example. Our move removes d = 0.60 and knocks out k = 0.20 of the time; we are faster
(f = 1); they attack a = 0.80 of the time for D = 0.50, K = 0.10; γ = 0.5. Then act = 1 and
trade = 0.60 − 0.80·0.50·(1 − 0.20) = 0.28. With a = 1, M = 0.60 − 0.50·0.80 = 0.20. We
survive with 1 − 0.80·0.10·(1 − 0.20) = 0.936. M is positive, so the second exchange is
worth M whether or not we knocked it out: S = 0.28 + 0.5·0.936·0.20 = 0.374. Had M been
−0.20, only the 0.80 of the time their Pokémon is still there would count:
S = 0.28 + 0.5·0.936·0.80·(−0.20) = 0.205.

Approximations, all deliberate for v0: `trade` assumes they stay in (when they switch, our
hit lands on something unknown); `M` uses the HP from before the exchange; their move is
taken to have no priority; recoil, a recharge turn, set-up moves, PP, weather turns and Gen 1
trapping moves that stop the target from acting are not modelled. A possible trapping ability does not lower a
switch's score: the simulator refuses such a switch and asks again without costing the turn
(R15), so the risk is reported, not scored.

Status moves: recovery, entry hazards and sleep, paralysis and poison have a value below;
every other status move is never recommended. The constants are provisional.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from poketrix.calc import effectiveness
from poketrix.calc.stats import battle_stats, current_hp
from poketrix.dex import UnknownDexEntryError
from poketrix.schemas import (
    FORCED_MOVES,
    ActionKind,
    ActionPrediction,
    BattlePokemon,
    Decision,
    MoveCategory,
    MoveOutlook,
    OptionScore,
    PokemonType,
    SetPosterior,
    SideCondition,
    Stat,
    Status,
    ThreatReport,
    rules_for,
)

from .situation import Situation


@dataclass(frozen=True)
class PolicySettings:
    """The policy's tunable numbers. Tuned on the tuning seeds only, never on evaluation games."""

    gamma: float = 0.5  # tempo: the weight of the second exchange
    a_floor: float = 0.0  # their attack chance is taken to be at least this
    utility_scale: float = 1.0  # multiplies every status-move value below


DEFAULT_SETTINGS = PolicySettings()
# Moves whose user faints. Showdown marks them `selfdestruct`; the dex snapshot does not carry
# that field, and these five are all there are in Gens 1-4.
SELF_FAINT = frozenset({"explosion", "selfdestruct", "memento", "healingwish", "lunardance"})

# ---- provisional constants (decision Q2): tuned on the tuning seeds only, in Order 13.
RECOVERY = {
    "recover": 0.5, "softboiled": 0.5, "roost": 0.5, "slackoff": 0.5, "milkdrink": 0.5,
    "moonlight": 0.5, "morningsun": 0.5, "synthesis": 0.5, "rest": 1.0,
}
REST_DISCOUNT = 0.5  # Rest heals fully but costs two turns asleep
HAZARD_VALUE_PER_BENCHED = 0.06  # per Pokémon of theirs that may still have to switch in
STATUS_VALUE = {Status.SLEEP: 0.60, Status.PARALYSIS: 0.30, Status.TOXIC: 0.30,
                Status.POISON: 0.15}
STATUS_MOVES = {
    "spore": Status.SLEEP, "sleeppowder": Status.SLEEP, "hypnosis": Status.SLEEP,
    "lovelykiss": Status.SLEEP, "sing": Status.SLEEP, "grasswhistle": Status.SLEEP,
    "darkvoid": Status.SLEEP,
    "thunderwave": Status.PARALYSIS, "stunspore": Status.PARALYSIS, "glare": Status.PARALYSIS,
    "toxic": Status.TOXIC, "poisonpowder": Status.POISON, "poisongas": Status.POISON,
}
HAZARD_MOVES = {
    "spikes": SideCondition.SPIKES, "stealthrock": SideCondition.STEALTH_ROCK,
    "toxicspikes": SideCondition.TOXIC_SPIKES,
}
KNOCKOUT_HEADLINE = 0.5  # from this chance on, the advice is "go for the knock-out"
TRAP_NAMES_A_MOVE = 0.5  # R14: from this risk on, a switch also names the move to fall back on

_TRAPPING = ("shadowtag", "arenatrap", "magnetpull")
_SPIKES_SHARE = {1: 1 / 8, 2: 1 / 6, 3: 1 / 4}
_POISON_IMMUNE = {PokemonType.POISON, PokemonType.STEEL}


@dataclass
class Inputs:
    """What the earlier stages produced. Anything may be missing: the policy then scores what
    it can and leaves the rest unscored."""

    threats: Mapping[int, ThreatReport] = field(default_factory=dict)
    offence: Mapping[int, list[MoveOutlook]] = field(default_factory=dict)
    first: Mapping[int, Mapping[str, float]] = field(default_factory=dict)
    opponent: ActionPrediction | None = None  # None: they are taken to attack


# --------------------------------------------------------------------------- small facts


def _grounded(pokemon: BattlePokemon) -> bool:
    ability = pokemon.known_set.ability if pokemon.known_set else pokemon.revealed_ability
    return PokemonType.FLYING not in pokemon.species.types and ability != "levitate"


def hazard_share(situation: Situation, index: int) -> float:
    """Share of its remaining HP a switch-in loses to Spikes and Stealth Rock on entry."""
    pokemon = situation.me.team[index]
    conditions = situation.me.conditions
    maximum = battle_stats(pokemon)[Stat.HP]
    lost = 0
    if SideCondition.STEALTH_ROCK in conditions:
        multiplier = effectiveness(situation.state.generation, PokemonType.ROCK,
                                   pokemon.species.types)
        lost += int(maximum * multiplier / 8)
    if SideCondition.SPIKES in conditions and _grounded(pokemon):
        lost += int(maximum * _SPIKES_SHARE[conditions[SideCondition.SPIKES]])
    return min(1.0, lost / max(1, current_hp(pokemon, maximum)))


def trap_risk(situation: Situation, posterior: SetPosterior | None) -> float:
    """R14: the chance that their ability stops our active Pokémon from switching out."""
    if posterior is None or situation.request.force_switch:
        return 0.0
    ours = situation.ours
    applies = {
        "shadowtag": True,
        "arenatrap": _grounded(ours),
        "magnetpull": PokemonType.STEEL in ours.species.types,
    }
    return min(1.0, sum(
        hypothesis.posterior for hypothesis in posterior.hypotheses
        if hypothesis.ability in _TRAPPING and applies[hypothesis.ability]
    ))


def _utility_value(situation: Situation, move_id: str) -> float:
    """What a status move is worth this turn, in the same unit as damage; 0 for most."""
    ours, theirs = situation.ours, situation.theirs
    try:
        move = situation.dex.move(move_id)
    except UnknownDexEntryError:
        return 0.0
    accuracy = (move.accuracy or 100) / 100
    if move_id in RECOVERY:
        maximum = battle_stats(ours)[Stat.HP]
        left = current_hp(ours, maximum)
        healed = min(maximum - left, int(maximum * RECOVERY[move_id]))
        return min(1.0, healed / max(1, left)) * (REST_DISCOUNT if move_id == "rest" else 1.0)
    if move_id in HAZARD_MOVES:
        condition = HAZARD_MOVES[move_id]
        layers = situation.them.conditions.get(condition, 0)
        if layers >= rules_for(situation.state.generation).side_condition_max_layers.get(condition, 0):
            return 0.0
        return HAZARD_VALUE_PER_BENCHED * (situation.them.alive_count - 1)
    status = STATUS_MOVES.get(move_id)
    if status is None or theirs.status is not None or "substitute" in theirs.volatiles:
        return 0.0
    types = set(theirs.species.types)
    if status in (Status.TOXIC, Status.POISON) and types & _POISON_IMMUNE:
        return 0.0
    if move_id == "thunderwave" and PokemonType.GROUND in types:
        return 0.0
    asleep = any(mon.status is Status.SLEEP for mon in situation.them.team)
    if status is Status.SLEEP and asleep:  # Sleep Clause: only one of theirs at a time
        return 0.0
    return STATUS_VALUE[status] * accuracy


# --------------------------------------------------------------------------- scoring


@dataclass(frozen=True)
class _Line:
    """One move of ours as the formula sees it."""

    move_id: str
    d: float  # share removed, or the value of a status move
    k: float
    f: float
    damaging: bool

    @property
    def self_faint(self) -> bool:
        return self.move_id in SELF_FAINT


class _Scorer:
    def __init__(self, situation: Situation, inputs: Inputs, settings: PolicySettings) -> None:
        self.situation = situation
        self.inputs = inputs
        self.settings = settings
        opponent = inputs.opponent
        self.a = max(settings.a_floor, 1.0 if opponent is None else opponent.p_attack)

    def lines(self, index: int) -> list[_Line]:
        """The scoreable moves of one of our Pokémon. Status moves only for the active one:
        what a switch-in would do with them next turn is not judged."""
        active = index == self.situation.me.active_index
        first = self.inputs.first.get(index, {})
        found = []
        for outlook in self.inputs.offence.get(index, []):
            f = first.get(outlook.move_id, 0.5)
            if outlook.expected_share is not None:
                found.append(_Line(outlook.move_id, outlook.expected_share,
                                   outlook.ko_probability, f, True))
            elif active and outlook.unsupported_reason is None:
                value = self.settings.utility_scale * _utility_value(
                    self.situation, outlook.move_id
                )
                if value > 0:
                    found.append(_Line(outlook.move_id, value, 0.0, f, False))
        return found

    def their(self, index: int) -> tuple[float, float]:
        """(D, K) against our Pokémon `index`; no damage known counts as none."""
        report = self.inputs.threats.get(index)
        return (0.0, 0.0) if report is None else (report.expected_best_share, report.p_ko_best_move)

    def acts(self, line: _Line, index: int, a: float) -> float:
        """The chance that we get to use the move: they do not knock us out first."""
        return 1 - a * self.their(index)[1] * (1 - line.f)

    def trade(self, line: _Line, index: int, a: float) -> float:
        dealt = line.d * self.acts(line, index, a)
        if line.self_faint:
            return dealt - 1.0  # whatever happens, our Pokémon is gone
        return dealt - a * self.their(index)[0] * (1 - line.k * line.f)

    def matchup(self, index: int) -> float | None:
        """M(X): None when none of X's moves could be evaluated."""
        damaging = [line for line in self.lines(index) if line.damaging]
        if not damaging:
            return None
        return max(self.trade(line, index, 1.0) for line in damaging)

    def stay(self, line: _Line) -> float:
        index = self.situation.me.active_index
        now = self.trade(line, index, self.a)
        if line.self_faint:
            return now
        _, k_them = self.their(index)
        survive = 1 - self.a * k_them * (1 - line.k * line.f)
        knocked_out = line.k * self.acts(line, index, self.a)
        matchup = self.matchup(index) or 0.0
        after = (1 - knocked_out) * matchup + knocked_out * max(matchup, 0.0)
        return now + self.settings.gamma * survive * after

    def switch(self, index: int) -> float | None:
        matchup = self.matchup(index)
        if matchup is None or index not in self.inputs.threats:
            return None
        hazard = hazard_share(self.situation, index)
        if self.situation.request.force_switch:
            return matchup - hazard
        d_them, k_them = self.their(index)
        again = self.settings.gamma * (1 - self.a * k_them) * matchup
        return -self.a * d_them - hazard + again


def decide(situation: Situation, inputs: Inputs, numbers: dict[str, float],
           settings: PolicySettings = DEFAULT_SETTINGS) -> Decision:
    """Score every legal action and order them: score, then knock-out chance, then accuracy,
    then a move before a switch, then the request's own order."""
    request, scorer = situation.request, _Scorer(situation, inputs, settings)
    lines = {line.move_id: line for line in scorer.lines(situation.me.active_index)}
    ranked = []
    for position, move_id in enumerate(request.available_moves):
        line = lines.get(move_id)
        score = None if line is None else scorer.stay(line)
        option = OptionScore(action=ActionKind.MOVE, move_id=move_id, score=score)
        ranked.append((_key(situation, option, line, position), option))
    for position, index in enumerate(request.available_switches):
        option = OptionScore(action=ActionKind.SWITCH, switch_index=index,
                             score=scorer.switch(index))
        if option.score is not None:
            numbers[f"switch.{index}.hazard"] = hazard_share(situation, index)
        ranked.append((_key(situation, option, None, position), option))
    options = [option for _, option in sorted(ranked, key=lambda pair: pair[0])]
    for option in options:
        if option.score is not None:
            numbers[f"score.{option.move_id or option.switch_index}"] = option.score
    best_move = next((o.move_id for o in options
                      if o.action is ActionKind.MOVE and o.score is not None), None)
    choice = options[0]
    return Decision(
        options=options, reason=_reason(situation, choice, lines, len(options)),
        alternative_move=best_move if choice.action is ActionKind.SWITCH else None,
    )


def _key(situation: Situation, option: OptionScore, line: _Line | None, position: int) -> tuple:
    scored = option.score is not None
    accuracy = 0
    if option.move_id is not None and option.move_id not in FORCED_MOVES:
        try:
            accuracy = situation.dex.move(option.move_id).accuracy or 100
        except UnknownDexEntryError:
            accuracy = 0
    return (
        not scored, -(option.score or 0.0), -(line.k if line else 0.0), -accuracy,
        option.action is ActionKind.SWITCH, position,
    )


def _reason(situation: Situation, choice: OptionScore, lines: Mapping[str, _Line],
            count: int) -> str:
    if count == 1:
        return "only_option"
    if choice.score is None:
        return "limited"
    if choice.action is ActionKind.SWITCH:
        return "forced_switch" if situation.request.force_switch else "switch"
    line = lines[choice.move_id]
    if not line.damaging:
        return "utility"
    return "knockout" if line.k >= KNOCKOUT_HEADLINE else "best_trade"


def by_power(situation: Situation) -> Decision:
    """The last resort, needing only the request: the legal move with the highest base
    power, else the first legal action."""
    def power(move_id: str) -> int:
        try:
            move = situation.dex.move(move_id)
        except UnknownDexEntryError:
            return 0
        return 0 if move.category is MoveCategory.STATUS else move.base_power

    request = situation.request
    moves = sorted(request.available_moves, key=lambda move_id: -power(move_id))
    options = [OptionScore(action=ActionKind.MOVE, move_id=move_id) for move_id in moves]
    options += [OptionScore(action=ActionKind.SWITCH, switch_index=index)
                for index in request.available_switches]
    return Decision(options=options, reason="only_option" if len(options) == 1 else "limited")
