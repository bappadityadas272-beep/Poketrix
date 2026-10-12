"""The turn engine: stages, fallbacks, the policy on positions with an obvious answer, the
wording, and a legal recommendation at every decision of real battles."""

import json
import re

import pytest

from poketrix.advisor import Deadline, PolicySettings, TurnAdvisor, stages
from poketrix.advisor.audit import Guardrails, audit
from poketrix.advisor.latency import measure, percentile
from poketrix.advisor.pipeline import NO_SETS, NO_TARGET, TRANSFORMED
from poketrix.advisor.policy import Inputs, by_power, decide, hazard_share, trap_risk
from poketrix.advisor.situation import Situation
from poketrix.calc import acts_first_chance, compute_stats, evaluate_move, expected_hp_share
from poketrix.dex import Dex
from poketrix.schemas import (
    ActionKind,
    ActionPrediction,
    BattlePokemon,
    Generation,
    MoveOutlook,
    Recommendation,
    Stat,
    SubsystemStatus,
    ThreatReport,
)
from poketrix.showdown import parse_battle
from poketrix.showdown.validation import load_battles
from poketrix.uncloak import SetPrior, Uncloaker, load_prior

GENS = list(Generation)
OK, FALLBACK, TIMEOUT = SubsystemStatus.OK, SubsystemStatus.FALLBACK, SubsystemStatus.TIMEOUT
PRIOR = load_prior(4)
DEX = Dex(4)
ADVISOR = TurnAdvisor()

# --------------------------------------------------------------------------- building positions


def ours(species: str, has_move: str | None = None, condition: str | None = None,
         hp: float = 1.0) -> dict:
    """One of our Pokémon as a request describes it, taken from a real Random Battle set.
    `hp` is the share of its HP it has left."""
    known = next(row.pokemon_set for row in PRIOR.sets_for(species)
                 if has_move is None or has_move in row.pokemon_set.moves)
    stats = compute_stats(known)
    name = known.species.name
    return {
        "ident": f"p1: {name}", "details": f"{name}, L{known.level}",
        "condition": condition or f"{round(hp * stats[Stat.HP])}/{stats[Stat.HP]}",
        "active": False,
        "stats": {stat.value: stats[stat] for stat in Stat if stat is not Stat.HP},
        "moves": list(known.moves), "baseAbility": known.ability, "item": known.item or "",
    }


def position(team: list[dict], their: str, their_hp: str = "100/100", lines=(), **request):
    """The decision a request asks for: our `team` (the first one active) against `their`."""
    level = PRIOR.sets_for(their)[0].pokemon_set.level
    their_name = DEX.species(their).name
    lead = team[0]
    team = [lead | {"active": True}, *team[1:]]
    body = {"side": {"name": "Ash", "id": "p1", "pokemon": team}, **request}
    if "forceSwitch" not in request:
        slots = [{"move": DEX.move(m).name, "id": "hiddenpower" if m.startswith("hiddenpower")
                  else m} for m in lead["moves"]]
        body["active"] = [{"moves": request.pop("moves", slots)} | request.pop("active", {})]
        body = {"side": body["side"], "active": body["active"], **request}
    log = "\n".join([
        "|gametype|singles", "|player|p1|Ash", "|player|p2|Gary", "|gen|4",
        "|tier|[Gen 4] Random Battle", "|teamsize|p1|6", "|teamsize|p2|6", "|start",
        f"|switch|p1a: {lead['ident'][4:]}|{lead['details']}|{lead['condition']}",
        f"|switch|p2a: {their_name}|{their_name}, L{level}|{their_hp}",
        "|turn|1", *lines, "|request|" + json.dumps(body),
    ])
    record = parse_battle(log)
    assert record.anomalies == ()  # every spread was found: the stats are real
    return record.snapshots[-1]


def advise(snapshot, **options):
    advisor = TurnAdvisor(**options) if options else ADVISOR
    report = advisor.advise(snapshot)
    # Whatever happened inside, the answer is legal and its numbers are the engine's own.
    Recommendation.model_validate(
        report.recommendation.model_dump(),
        context={"state": snapshot.state, "allowed_numbers": report.numbers},
    )
    return report


def text_of(report) -> str:
    return f"{report.recommendation.headline} {report.recommendation.explanation}"


# --------------------------------------------------------------------------- the maths added


def test_expected_share_stops_at_the_hp_that_is_left():
    garchomp = BattlePokemon(species=DEX.species("garchomp"), level=74, hp_fraction=1.0,
                             known_set=PRIOR.sets_for("garchomp")[0].pokemon_set)
    magnezone = PRIOR.sets_for("magnezone")[0].pokemon_set
    full = BattlePokemon(species=magnezone.species, level=81, hp_fraction=1.0, known_set=magnezone)
    evaluation = evaluate_move(garchomp, full, DEX.move("earthquake"))
    maximum = evaluation.damage.defender_max_hp
    assert min(evaluation.damage.rolls) > maximum  # a 4x hit: far more than it has
    assert expected_hp_share(evaluation, maximum) == pytest.approx(1.0)  # overkill is worth 1
    claw = evaluate_move(garchomp, full, DEX.move("dragonclaw"))
    mean = sum(claw.damage.rolls) / len(claw.damage.rolls)
    assert expected_hp_share(claw, maximum) == pytest.approx(mean / maximum)
    assert expected_hp_share(evaluate_move(garchomp, full, DEX.move("swordsdance")), 100) is None


def test_who_acts_first():
    def mon(species, **changes):
        known = PRIOR.sets_for(species)[0].pokemon_set
        return BattlePokemon(species=known.species, level=known.level, hp_fraction=1.0,
                             known_set=known, **changes)

    jolteon, swampert = mon("jolteon"), mon("swampert")
    bolt, quake = DEX.move("thunderbolt"), DEX.move("earthquake")
    assert acts_first_chance(jolteon, swampert, bolt) == 1.0
    assert acts_first_chance(swampert, jolteon, quake) == 0.0
    assert acts_first_chance(jolteon, jolteon, bolt) == 0.5  # a Speed tie
    assert acts_first_chance(swampert, jolteon, quake, their_priority=-1) == 1.0
    assert acts_first_chance(swampert, mon("jolteon", status="par"), quake) == 1.0
    assert acts_first_chance(jolteon, swampert, bolt, their_priority=1) == 0.0


def test_a_deadline_ends_when_its_clock_says_so():
    now = [0.0]
    turn = Deadline(100, clock=lambda: now[0])
    stage = turn.within(30)
    now[0] = 0.029
    assert not stage.expired() and not turn.expired()
    now[0] = 0.031
    assert stage.expired() and not turn.expired()
    assert turn.within(500)._end == turn._end  # a stage never outlives the turn


# --------------------------------------------------------------------------- the policy's formula


def scored(snapshot, **inputs):
    situation = Situation(snapshot, PRIOR, DEX)
    numbers = {}
    return decide(situation, Inputs(**inputs), numbers), numbers


def test_the_score_is_the_documented_formula():
    snapshot = position([ours("garchomp")], "magnezone")
    threat = ThreatReport(attacker_species="magnezone", defender_species="garchomp",
                          expected_best_share=0.5, p_ko_best_move=0.1)
    decision, numbers = scored(
        snapshot,
        offence={0: [MoveOutlook(move_id="dragonclaw", expected_share=0.6, ko_probability=0.2)]},
        first={0: {"dragonclaw": 1.0}}, threats={0: threat},
        opponent=ActionPrediction(p_attack=0.8, p_switch=0.2, p_utility=0.0, model_version="t"),
    )
    # trade = 0.6 - 0.8*0.5*(1 - 0.2) = 0.28; M = 0.6 - 0.5*0.8 = 0.20; survive = 0.936;
    # M is positive, so the second exchange is worth gamma * survive * M either way.
    assert decision.choice.move_id == "dragonclaw"
    assert decision.choice.score == pytest.approx(0.28 + 0.5 * 0.936 * 0.20)
    assert numbers["score.dragonclaw"] == decision.choice.score
    unscored = [o.move_id for o in decision.options if o.score is None]
    assert sorted(unscored) == ["earthquake", "substitute", "swordsdance"]  # nothing known: last


def test_ties_go_to_the_knockout_then_accuracy_then_request_order():
    snapshot = position([ours("swampert", has_move="stoneedge")], "magnezone")

    def order(**outlooks):
        offence = {0: [MoveOutlook(move_id=m, expected_share=0.5, ko_probability=k)
                       for m, k in outlooks.items()]}
        return [o.move_id for o in scored(snapshot, offence=offence)[0].options if o.score]

    assert order(stoneedge=0.0, earthquake=0.0) == ["earthquake", "stoneedge"]  # 100% before 80%
    assert order(waterfall=0.0, earthquake=0.0) == ["earthquake", "waterfall"]  # request order
    # With nothing known of their attack the scores are equal: the knock-out chance decides.
    assert order(earthquake=0.0, stoneedge=0.3)[0] == "stoneedge"


def line_scores(k: float, matchup_is_good: bool, **settings):
    """Scores of two moves that remove the same share, one of which may knock out."""
    snapshot = position([ours("swampert", has_move="stoneedge")], "magnezone")
    threat = ThreatReport(attacker_species="magnezone", defender_species="swampert",
                          expected_best_share=0.2 if matchup_is_good else 0.9,
                          p_ko_best_move=0.0)
    offence = {0: [MoveOutlook(move_id="earthquake", expected_share=0.6, ko_probability=k),
                   MoveOutlook(move_id="waterfall", expected_share=0.6, ko_probability=0.0)]}
    situation = Situation(snapshot, PRIOR, DEX)
    decision = decide(situation, Inputs(offence=offence, threats={0: threat},
                                        first={0: {"earthquake": 1.0, "waterfall": 1.0}}),
                      {}, PolicySettings(**settings))
    return {o.move_id: o.score for o in decision.options if o.score is not None}


def test_a_knockout_never_scores_below_the_same_damage_without_one():
    """F1: a knock-out ends a bad matchup's cost and never forfeits a good one's value."""
    for good in (True, False):
        scores = line_scores(k=1.0, matchup_is_good=good)
        assert scores["earthquake"] > scores["waterfall"]
    # In a good matchup the second exchange is worth the same with or without the knock-out;
    # what the knock-out adds is the hit we no longer take.
    good = line_scores(k=1.0, matchup_is_good=True)
    assert good["earthquake"] - good["waterfall"] == pytest.approx(0.2)


def test_tempo_and_the_attack_floor_are_settings():
    slow = line_scores(k=0.0, matchup_is_good=True, gamma=1.0)["waterfall"]
    fast = line_scores(k=0.0, matchup_is_good=True, gamma=0.3)["waterfall"]
    assert slow - fast == pytest.approx(0.7 * 0.4)  # M = 0.6 - 0.2 = 0.4, and we survive
    snapshot = position([ours("garchomp"), ours("skarmory")], "skarmory")
    assumed = advise(snapshot).opponent.payload.p_attack
    assert assumed < 0.5  # Skarmory's sets are mostly status moves
    plain = advise(snapshot).numbers["score.earthquake"]
    floored = advise(snapshot, settings=PolicySettings(a_floor=0.5)).numbers["score.earthquake"]
    assert floored < plain  # taking their hit seriously lowers every stay


def test_a_move_that_faints_its_user_is_charged_everything_it_has_left():
    """F2, on the real turns: Gen 2 fixture battle 0, Muk against Piloswine."""
    decisions = {
        s.turn: s for s in parse_battle(load_battles(2)[0]["player"]).snapshots
        if s.state.me.request is not None and s.decision_index == 0
    }
    for turn in (3, 4, 5, 6):
        report = advise(decisions[turn])
        if "explosion" not in decisions[turn].state.me.request.available_moves:
            continue
        index = decisions[turn].state.me.active_index
        dealt = report.numbers[f"our.{index}.explosion.share"]
        assert dealt == pytest.approx(1.0)
        # d * (chance to act) - 1: a certain knock-out that costs our own Pokémon is worth ~0.
        assert -0.1 < report.numbers["score.explosion"] <= dealt - 1.0 + 1e-9
        assert report.recommendation.move_id != "explosion"
    assert advise(decisions[3]).recommendation.move_id == "hiddenpowerground"


@pytest.mark.parametrize(
    ("gen", "turn", "expected"),
    [
        (4, 2, "triattack"),  # F1: a certain knock-out, not the switch to Golduck
        (4, 9, "stoneedge"),  # Pinsir against Ho-Oh: unchanged
        (3, 6, "hiddenpowerghost"),  # Hitmontop against Primeape: unchanged
    ],
)
def test_real_turns_keep_their_right_answers(gen, turn, expected):
    snapshot = next(
        s for s in parse_battle(load_battles(gen)[0]["player"]).snapshots
        if s.turn == turn and s.state.me.request is not None
    )
    assert advise(snapshot).recommendation.move_id == expected


@pytest.mark.slow
def test_no_knockout_is_thrown_away_on_the_fixture_battles():
    total = Guardrails()
    for gen in GENS:
        total.merge(audit(gen))
    assert total.decisions > 300
    # The one case left is Explosion: "knocking out" at the price of our own Pokémon.
    assert [case for case in total.thrown_away if "self-KO" not in case] == []
    assert total.voluntary_switches / total.decisions < 0.25
    assert len(total.self_ko) <= 1


def test_entry_hazards_are_exact_and_the_trap_risk_comes_from_the_ability():
    rocks = ["|-sidestart|p1: Ash|move: Stealth Rock", "|-sidestart|p1: Ash|Spikes"]
    snapshot = position([ours("swampert"), ours("gyarados"), ours("skarmory")], "dugtrio",
                        lines=rocks)
    situation = Situation(snapshot, PRIOR, DEX)
    gyarados = compute_stats(snapshot.state.me.team[1].known_set)[Stat.HP]
    assert hazard_share(situation, 1) == pytest.approx((gyarados // 4) / gyarados)  # 4x, no Spikes
    skarmory = compute_stats(snapshot.state.me.team[2].known_set)[Stat.HP]
    assert hazard_share(situation, 2) == pytest.approx((skarmory // 8) / skarmory)  # neutral
    posterior = Uncloaker(PRIOR).uncloak("dugtrio", situation.evidence(0)[1]).payload
    assert trap_risk(situation, posterior) == pytest.approx(1.0)  # every Dugtrio has Arena Trap
    flying = Situation(position([ours("skarmory")], "dugtrio"), PRIOR, DEX)
    assert trap_risk(flying, posterior) == 0.0  # Arena Trap does not hold a Flying-type


# --------------------------------------------------------------------------- obvious positions


def test_a_knockout_that_is_there_is_taken():
    report = advise(position([ours("garchomp"), ours("skarmory")], "magnezone"))
    advice = report.recommendation
    assert report.status is OK and report.policy.payload.reason == "knockout"
    assert (advice.action, advice.move_id) == (ActionKind.MOVE, "earthquake")
    assert report.numbers["our.0.earthquake.ko"] > 0.9
    assert advice.headline.startswith("Earthquake:") and "to knock out Magnezone" in advice.headline


def test_about_to_be_knocked_out_with_a_safe_switch():
    team = [ours("gyarados", has_move="stoneedge", hp=0.45), ours("swampert"),
            ours("skarmory")]
    report = advise(position(team, "jolteon", lines=["|move|p2a: Jolteon|Thunderbolt|p1a: X"]))
    advice = report.recommendation
    assert report.numbers["their.0.p_ko"] > 0.9  # Gyarados goes down to Thunderbolt
    assert report.numbers["their.1.p_ko"] < 0.05  # Swampert does not mind it
    assert (advice.action, advice.switch_index) == (ActionKind.SWITCH, 1)
    assert report.policy.payload.reason == "switch"
    assert "Switch to Swampert: Gyarados is knocked out" in advice.headline


def test_a_forced_switch_sends_in_the_best_matchup():
    team = [ours("gyarados", condition="0 fnt"), ours("skarmory"), ours("swampert")]
    report = advise(position(team, "jolteon", forceSwitch=[True]))
    advice = report.recommendation
    assert report.policy.payload.reason == "forced_switch"
    assert (advice.action, advice.switch_index) == (ActionKind.SWITCH, 2)
    assert advice.headline == "Send in Swampert"
    assert [o.switch_index for o in report.policy.payload.options] == [2, 1]


def test_trapped_means_a_move_and_a_possible_trap_is_stated_not_scored():
    team = [ours("magnezone"), ours("skarmory")]
    held = advise(position(team, "dugtrio", active={"trapped": True}))
    assert held.recommendation.action is ActionKind.MOVE
    assert all(o.action is ActionKind.MOVE for o in held.policy.payload.options)

    free = advise(position(team, "dugtrio"))  # `maybeTrapped`: the switch is still offered
    assert free.trap_risk == pytest.approx(1.0) and free.numbers["trap.risk"] == free.trap_risk
    # R15: a refused switch costs nothing, so the risk changes no score...
    switches = {o.switch_index: o.score for o in free.policy.payload.options if o.switch_index}
    situation = Situation(position(team, "dugtrio"), PRIOR, DEX)
    assert trap_risk(situation, None) == 0.0 and switches[1] is not None
    # ...but a switch recommendation says so, and names the move to fall back on.
    assert free.recommendation.action is ActionKind.SWITCH
    explanation = free.recommendation.explanation
    assert "Dugtrio may be able to trap Magnezone (100%)." in explanation
    assert "If the switch is refused, use " in explanation


# --------------------------------------------------------------------------- fallbacks


def test_r5_an_unsupported_move_is_unknown_never_zero():
    report = advise(position([ours("wobbuffet"), ours("skarmory")], "swampert"))
    outlooks = {o.move_id: o for o in report.offence.payload.by_attacker[0]}
    assert outlooks["counter"].unsupported_reason and outlooks["counter"].expected_share is None
    assert "our.0.counter.share" not in report.numbers
    assert "our.0.counter.ko" not in report.numbers
    by_move = {o.move_id: o.score for o in report.policy.payload.options if o.move_id}
    assert by_move["counter"] is None and by_move["mirrorcoat"] is None
    # Facing it, their knock-out chance is only a lower bound, and the text says so.
    facing = advise(position([ours("garchomp")], "wobbuffet"))
    assert facing.threats.payload.by_target[0].ko_lower_bound
    assert "lower bound" in facing.recommendation.explanation


def test_r11_no_damage_numbers_for_a_transformed_pokemon():
    snapshot = position([ours("garchomp"), ours("skarmory")], "ditto",
                        lines=["|-transform|p2a: Ditto|p1a: Garchomp"])
    report = advise(snapshot)
    assert report.status is FALLBACK
    assert [getattr(report, s).status for s in ("threats", "offence", "order")] == [FALLBACK] * 3
    assert not any(key.startswith(("our.", "their.")) for key in report.numbers)
    advice = report.recommendation
    assert (advice.action, advice.move_id) == (ActionKind.MOVE, "earthquake")  # highest power
    assert TRANSFORMED in advice.explanation and advice.cited_numbers == {}


def test_a_stage_that_runs_out_of_time_returns_what_it_finished():
    snapshot = position([ours("garchomp"), ours("skarmory"), ours("swampert")], "magnezone")
    situation = Situation(snapshot, PRIOR, DEX)
    posterior = Uncloaker(PRIOR).uncloak("magnezone", situation.evidence(0)[1]).payload
    checks = iter([0.0, 0.0, 0.0, 1.0, 1.0])  # the deadline passes before the third target
    sheet, status, problem = stages.read_threats(
        situation, posterior, Deadline(10, clock=lambda: next(checks)), {}
    )
    assert (status, problem) == (TIMEOUT, "out of time after 2 of 3")
    assert sorted(sheet.by_target) == [0, 1]  # our active first, then the first switch-in


def test_a_turn_that_runs_out_of_time_still_gives_a_legal_answer():
    ticks = iter(range(10_000))
    slow = advise(position([ours("garchomp"), ours("skarmory")], "magnezone"),
                  clock=lambda: next(ticks) * 0.004)  # every look at the clock costs 4 ms
    assert slow.status is TIMEOUT
    assert TIMEOUT in {getattr(slow, s).status for s in ("uncloak", "threats", "offence", "order")}
    assert slow.recommendation.action in (ActionKind.MOVE, ActionKind.SWITCH)
    late = advise(position([ours("garchomp")], "magnezone"), budget_ms=0.0)
    assert late.uncloak.status is TIMEOUT and late.uncloak.error == "out of time before it started"
    assert late.recommendation.move_id == "earthquake"  # the request alone: highest power


def test_no_posterior_means_the_request_alone_decides():
    report = advise(position([ours("garchomp"), ours("skarmory")], "magnezone"),
                    priors=lambda gen: SetPrior(gen, []))
    assert report.uncloak.status is FALLBACK and report.uncloak.payload.posteriors == {}
    assert report.policy.status is FALLBACK and report.policy.payload.reason == "limited"
    assert report.recommendation.move_id == "earthquake"
    assert NO_SETS in report.recommendation.explanation
    assert report.opponent.payload.model_version == "assumed"  # they are taken to attack


def test_nothing_to_aim_at_when_their_pokemon_has_fainted():
    team = [ours("gyarados", condition="0 fnt"), ours("skarmory")]
    report = advise(position(team, "jolteon", their_hp="0 fnt", forceSwitch=[True]))
    assert report.recommendation.headline == "Send in Skarmory"
    assert NO_TARGET in report.recommendation.explanation


def test_one_legal_action_is_recommended_as_such():
    only = [{"move": "Recharge", "id": "recharge"}]
    report = advise(position([ours("garchomp")], "magnezone", moves=only,
                             active={"trapped": True}))
    assert report.policy.payload.reason == "only_option"
    assert report.recommendation.headline == "Recharge: the only legal action"
    last = by_power(Situation(position([ours("garchomp")], "magnezone"), PRIOR, DEX))
    assert last.choice.move_id == "earthquake" and last.reason == "limited"


def test_a_snapshot_without_a_request_is_refused():
    spectator = parse_battle(load_battles(4)[0]["spectator"]).snapshots[0]
    with pytest.raises(ValueError, match="no request"):
        ADVISOR.advise(spectator)


# --------------------------------------------------------------------------- real battles

_PERCENT = re.compile(r"(\d+)%")


@pytest.mark.slow
@pytest.mark.parametrize("gen", GENS)
def test_every_decision_of_a_real_battle_gets_legal_checked_advice(gen):
    """Replays the fixture player logs: a legal recommendation at every decision, and every
    number in its text is a cited number, rounded."""
    decisions = 0
    for battle in load_battles(gen):
        if "player" not in battle:
            continue
        for snapshot in parse_battle(battle["player"]).snapshots:
            if snapshot.state.me.request is None:
                continue
            decisions += 1
            report = advise(snapshot)  # checks legality and the cited numbers
            assert report.status in (OK, FALLBACK)
            advice = report.recommendation
            quoted = {round(100 * value) for value in advice.cited_numbers.values()}
            words = text_of(report)
            assert {int(n) for n in _PERCENT.findall(words)} <= quoted
            # No other digits: a number can only enter the text as a quoted percentage.
            names = [m.species.name for side in snapshot.state.sides.values() for m in side.team]
            for name in names:
                words = words.replace(name, "")
            assert not re.search(r"\d", _PERCENT.sub("", words)), words
    assert decisions > 50


def test_the_analyze_command_prints_a_turn(tmp_path, capsys):
    from poketrix.__main__ import main

    log = tmp_path / "battle.log"
    log.write_text(load_battles(4)[0]["player"], encoding="utf-8")
    assert main(["analyze", str(log), "--turn", "2"]) == 0
    printed = capsys.readouterr().out
    assert "Gen 4, turn 2, decision 0" in printed and "Recommendation (" in printed
    assert "Their likely sets" in printed and "Our options (best first):" in printed
    log.write_text(load_battles(4)[0]["spectator"], encoding="utf-8")
    main(["analyze", str(log)])
    assert "no |request| lines" in capsys.readouterr().out


@pytest.mark.timing
@pytest.mark.parametrize("gen", GENS)
def test_a_decision_fits_the_latency_target(gen):
    latency = measure(gen)
    assert percentile(latency.total_ms, 0.95) < 250  # the Phase 6 target; the hard limit is 500
