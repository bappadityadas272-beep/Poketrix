"""The overlay's local server: its endpoints, the fair-play guard, and that a battle posted
line by line gets the same advice as `analyze`. The browser extension is checked by hand
(see the tracker)."""

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from poketrix.advisor import TurnAdvisor
from poketrix.advisor.tendency import tendency_line
from poketrix.opponent import Heuristic
from poketrix.overlay.rooms import RATED_MESSAGE, Rooms
from poketrix.overlay.server import HOST, OverlayServer
from poketrix.showdown import parse_battle
from poketrix.showdown.validation import load_battles


@pytest.fixture(scope="module")
def server():
    running = OverlayServer(port=0, rooms=Rooms(TurnAdvisor(), Heuristic()))
    thread = threading.Thread(target=running.serve_forever, daemon=True)
    thread.start()
    yield running
    running.shutdown()
    running.server_close()


def _url(server, path: str) -> str:
    return f"http://{HOST}:{server.server_address[1]}{path}"


def _post(server, body) -> dict:
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    with urlopen(Request(_url(server, "/line"), data=data, method="POST")) as answer:
        return json.loads(answer.read())


def _get(server, query: str) -> dict:
    with urlopen(_url(server, f"/advice?{query}")) as answer:
        return json.loads(answer.read())


def test_it_listens_on_this_machine_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_a_battle_posted_line_by_line_gets_the_advice_analyze_gives(server):
    log = load_battles(3)[1]["player"]
    for line in log.splitlines():
        _post(server, {"room": "battle-gen3-1", "lines": [line]})
    shown = _get(server, "room=battle-gen3-1")
    last = [s for s in parse_battle(log).snapshots if s.state.me.request is not None][-1]
    report = TurnAdvisor().advise(last)
    assert shown["status"] == "ok" and shown["mode"] == "player"
    assert (shown["turn"], shown["decision"]) == (last.turn, last.decision_index)
    assert shown["headline"] == report.recommendation.headline
    assert shown["explanation"] == report.recommendation.explanation
    assert shown["tendency"] == tendency_line(last, report, Heuristic())
    assert 1 <= len(shown["options"]) <= 3 and len(shown["sets"]) <= 2


def test_a_rated_live_battle_gets_no_advice_but_a_replay_does(server):
    log = load_battles(4)[0]["spectator"]
    lines = log.splitlines()
    lines.insert(lines.index("|start"), "|rated|")
    _post(server, {"room": "battle-rated", "lines": lines, "source": "live"})
    assert _get(server, "room=battle-rated") == {"status": "rated", "message": RATED_MESSAGE}
    assert server.rooms.get("battle-rated").advice == {}  # nothing was even computed
    _post(server, {"room": "replay-rated", "lines": lines, "source": "replay"})
    turn = _get(server, "room=replay-rated&turn=3")
    assert turn["status"] == "ok" and turn["turn"] == 3
    assert turn["mode"] == "spectator, advising p1"


def test_bad_requests_are_refused(server):
    with pytest.raises(HTTPError) as unknown:
        _get(server, "room=nowhere")
    assert unknown.value.code == 404
    for body in (b"not json", {"lines": []}, {"room": "x", "lines": [], "source": "elsewhere"}):
        with pytest.raises(HTTPError) as refused:
            _post(server, body)
        assert refused.value.code == 400
    _post(server, {"room": "battle-empty", "lines": ["|init|battle"]})
    assert _get(server, "room=battle-empty")["status"] == "waiting"
    with pytest.raises(HTTPError) as bad_turn:
        _get(server, "room=battle-empty&turn=x")
    assert bad_turn.value.code == 400
