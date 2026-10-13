"""Plays whole games in the simulator, through scripts/randbats/play_bridge.mjs.

A `Player` sees exactly what its own side sees (its log and its requests) and answers each
request. Games come in pairs: the same battle seed and the same two teams, played twice with
the teams swapped, so that most of the luck of the draw cancels.
"""

import json
import os
import subprocess
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from poketrix.advisor import PolicySettings, TurnAdvisor, stages
from poketrix.advisor.audit import Guardrails
from poketrix.advisor.policy import by_power
from poketrix.advisor.situation import Situation
from poketrix.dex import Dex
from poketrix.schemas import ActionKind, OptionScore, PlayerSlot, TurnReport, move_matches
from poketrix.showdown import BattleReader, TurnSnapshot
from poketrix.showdown import events as ev
from poketrix.uncloak import Uncloaker, load_prior

BRIDGE_DIR = Path(__file__).resolve().parents[3] / "scripts" / "randbats"
RANDOM = "random"  # the simulator's own RandomPlayerAI
_UNAVAILABLE = "[Unavailable choice]"  # a switch refused by a trapping ability (R15)
_DEFAULT = "default"  # the simulator's first legal action: what we send after an invalid choice


@dataclass(frozen=True)
class Choice:
    option: OptionScore
    report: TurnReport | None = None  # what the turn engine made of the decision, if it ran


class Player(Protocol):
    def choose(self, snapshot: TurnSnapshot) -> Choice: ...


class PolicyPlayer:
    """Plays what the turn engine recommends."""

    def __init__(self, settings: PolicySettings | None = None) -> None:
        self._advisor = TurnAdvisor(settings=settings or PolicySettings())

    def choose(self, snapshot: TurnSnapshot) -> Choice:
        report = self._advisor.advise(snapshot)
        advice = report.recommendation
        return Choice(
            OptionScore(action=advice.action, move_id=advice.move_id,
                        switch_index=advice.switch_index),
            report,
        )


class MaxDamagePlayer:
    """The greedy baseline: always the move with the highest expected damage, using the same
    estimate of the opponent's set as the engine. It never switches unless it must, and then
    sends in the first Pokémon it may."""

    def choose(self, snapshot: TurnSnapshot) -> Choice:
        generation = snapshot.state.generation
        situation = Situation(snapshot, load_prior(generation), Dex(generation))
        request = situation.request
        if request.force_switch:
            first = request.available_switches[0]
            return Choice(OptionScore(action=ActionKind.SWITCH, switch_index=first))
        if not request.available_moves:
            return Choice(by_power(situation).choice)
        best = None
        if not (situation.transformed or situation.theirs.fainted):
            species_id, evidence = situation.evidence(situation.them.active_index)
            posterior = Uncloaker(situation.prior).uncloak(species_id, evidence).payload
            if posterior is not None:
                outlooks = stages.move_outlooks(
                    situation, situation.me.active_index, situation.their_sets(posterior)
                )
                known = [o for o in outlooks if o.expected_share is not None]
                best = max(known, key=lambda o: o.expected_share, default=None)
        if best is None:
            return Choice(by_power(situation).choice)
        return Choice(OptionScore(action=ActionKind.MOVE, move_id=best.move_id))


# --------------------------------------------------------------------------- results


@dataclass
class SideTally:
    """What one externally played side did during a game."""

    decisions: int = 0
    statuses: Counter = field(default_factory=Counter)  # engine status per decision
    latency_ms: list[float] = field(default_factory=list)
    illegal: int = 0  # choices the simulator rejected: any is a bug
    trap_reasks: int = 0  # switches refused by a trapping ability and asked again (legitimate)
    guardrails: Guardrails = field(default_factory=Guardrails)
    choices: list[OptionScore] = field(default_factory=list)  # every decision, in order


@dataclass
class GameResult:
    gen: int
    index: int
    swap: bool
    winner: str | None  # "p1", "p2", or None for a tie
    turns: int
    sides: dict[str, SideTally]


# --------------------------------------------------------------------------- the bridge


def to_choice(snapshot: TurnSnapshot, option: OptionScore, nickname: str | None) -> str:
    """A decision in the simulator's words: `move 2`, `switch 3` (positions in the request)."""
    request = next(e for e in reversed(snapshot.events) if isinstance(e, ev.RequestEvent))
    if option.action is ActionKind.MOVE:
        for position, offered in enumerate(request.moves, start=1):
            if not offered.disabled and move_matches(offered.move_id, option.move_id):
                return f"move {position}"
        raise ValueError(f"{option.move_id} is not offered by the request")
    for position, pokemon in enumerate(request.team, start=1):
        if pokemon.pokemon.name == nickname:
            return f"switch {position}"
    raise ValueError(f"{nickname} is not in the request")


REFUSED, INVALID = "refused", "invalid"


def read_chunk(reader: BattleReader, chunk: str) -> Iterator[TurnSnapshot | str]:
    """What one chunk of a player's stream asks of that player: each decision it must make
    (a snapshot), and each choice of its the simulator turned down (`REFUSED` when a trapping
    ability stops a switch and the request comes again, `INVALID` otherwise)."""
    for line in chunk.split("\n"):
        if line.startswith("|error|"):
            yield REFUSED if _UNAVAILABLE in line else INVALID
            continue
        snapshot = reader.feed(line)
        if snapshot is not None and snapshot.state.me.request is not None:
            yield snapshot


class Bridge:
    """One simulator process, playing one game at a time."""

    def __init__(self, showdown_dir: str | None = None) -> None:
        env = dict(os.environ)
        if showdown_dir:
            env["POKETRIX_SHOWDOWN_DIR"] = showdown_dir
        self._node = subprocess.Popen(
            ["node", "play_bridge.mjs"], cwd=BRIDGE_DIR, env=env, text=True, encoding="utf-8",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1,
        )
        self.simulator = self._read()["simulator"]
        self._game = 0
        # What each externally played side received in the game being played: the evidence
        # kept when a game has to be quarantined.
        self.log: dict[str, list[str]] = {}

    def close(self) -> None:
        self._node.stdin.close()
        self._node.wait(timeout=10)

    def abandon(self) -> None:
        """Stop a process whose game went wrong; the caller starts a fresh one."""
        self._node.kill()
        self._node.wait(timeout=10)

    def _send(self, **message) -> None:
        self._node.stdin.write(json.dumps(message) + "\n")
        self._node.stdin.flush()

    def _read(self) -> dict:
        line = self._node.stdout.readline()
        if not line:
            raise RuntimeError("the simulator bridge stopped")
        return json.loads(line)

    def play(self, gen: int, index: int, swap: bool, players: dict[str, Player | None]) -> GameResult:
        """One game. `players` maps "p1" and "p2" to a player, or to None for the simulator's
        random player."""
        kinds = {side: RANDOM if player is None else "external" for side, player in players.items()}
        self._send(cmd="start", gen=gen, index=index, swap=swap, **kinds)
        readers = {side: BattleReader() for side, player in players.items() if player}
        tallies = {side: SideTally() for side in readers}
        self.log = {side: [] for side in readers}
        self._game += 1
        while True:
            message = self._read()
            if message["game"] != self._game:
                continue  # the last lines of a battle that has already ended
            if message.get("end"):
                return GameResult(gen, index, swap, message["winner"], message["turns"], tallies)
            side = message["side"]
            self.log[side].append(message["chunk"])
            for asked in read_chunk(readers[side], message["chunk"]):
                if asked == REFUSED:
                    tallies[side].trap_reasks += 1  # the request comes again, corrected
                elif asked == INVALID:
                    tallies[side].illegal += 1
                    self._send(cmd="choose", side=side, choice=_DEFAULT)
                else:
                    choice = self._decide(players[side], readers[side], asked, tallies[side])
                    self._send(cmd="choose", side=side, choice=choice)

    @staticmethod
    def _decide(player: Player, reader: BattleReader, snapshot: TurnSnapshot,
                tally: SideTally) -> str:
        choice = player.choose(snapshot)
        tally.decisions += 1
        tally.choices.append(choice.option)
        if choice.report is not None:
            tally.statuses[choice.report.status.value] += 1
            tally.latency_ms.append(round(choice.report.latency_ms, 2))
            tally.guardrails.add(snapshot, choice.report)
        nickname = None
        if choice.option.action is ActionKind.SWITCH:
            slot = PlayerSlot(snapshot.state.perspective)
            nickname = reader.tracker.nickname(slot, choice.option.switch_index)
        return to_choice(snapshot, choice.option, nickname)
