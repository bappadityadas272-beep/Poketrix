"""The overlay's local server: standard library only, bound to 127.0.0.1 and nothing else.

    POST /line             {"room": "...", "lines": ["|...", ...], "source": "live" | "replay"}
    GET  /advice?room=...[&turn=N]

It never sends a choice anywhere and keeps nothing on disk, except an optional debug log of
the requests it handled (`--debug-log`).
"""

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, urlparse

from poketrix.advisor import TurnAdvisor
from poketrix.opponent import XgbModel

from .rooms import Rooms, Source

HOST = "127.0.0.1"  # never another interface: the advice is for this machine only
PORT = 8765  # the extension's manifest names this port
MAX_BODY = 1_000_000


class OverlayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = PORT, rooms: Rooms | None = None,
                 debug_log: Path | None = None) -> None:
        self.rooms = rooms or Rooms(TurnAdvisor(), XgbModel())
        self.debug_log = debug_log
        super().__init__((HOST, port), _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: OverlayServer

    def do_POST(self) -> None:
        started = perf_counter()
        if urlparse(self.path).path != "/line":
            return self._send(HTTPStatus.NOT_FOUND, {"error": "unknown path"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BODY:
                raise ValueError("body missing or too large")
            body = json.loads(self.rfile.read(length))
            room_id, lines = str(body["room"]), [str(line) for line in body["lines"]]
            source = Source(body.get("source", Source.LIVE.value))
        except (ValueError, KeyError, TypeError) as error:
            return self._send(HTTPStatus.BAD_REQUEST, {"error": f"bad request: {error}"})
        room = self.server.rooms.feed(room_id, lines, source)
        self._send(HTTPStatus.OK, {"decisions": len(room.snapshots), "rated": room.rated,
                                   "ms": round((perf_counter() - started) * 1000, 1)})

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path != "/advice":
            return self._send(HTTPStatus.NOT_FOUND, {"error": "unknown path"})
        query = parse_qs(url.query)
        room = self.server.rooms.get(query.get("room", [""])[0])
        if room is None:
            return self._send(HTTPStatus.NOT_FOUND, {"error": "unknown room"})
        try:
            turn = int(query["turn"][0]) if "turn" in query else None
        except ValueError:
            return self._send(HTTPStatus.BAD_REQUEST, {"error": "turn must be a number"})
        self._send(HTTPStatus.OK, self.server.rooms.advice(room, turn))

    def _send(self, status: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        if self.server.debug_log is not None:
            with self.server.debug_log.open("a", encoding="utf-8") as file:
                file.write(f"{self.log_date_time_string()} {format % args}\n")


def serve(port: int = PORT, debug_log: Path | None = None) -> None:
    server = OverlayServer(port, debug_log=debug_log)
    print(f"Poketrix overlay server on http://{HOST}:{port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
