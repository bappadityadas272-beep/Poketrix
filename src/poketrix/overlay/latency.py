"""How long the overlay takes from a line's arrival to the advice being ready to show.

Starts a server on a free port and posts the fixture player logs to it line by line, as the
extension does. For each line that completes a decision it times the POST (the decision is
advised inside it) plus the GET that reads the advice: the server's share of "line arrival
to advice shown". The panel shows the full figure, browser included, for each update.

    python -m poketrix.overlay.latency [battles per gen]
"""

import json
import sys
import threading
from time import perf_counter
from urllib.request import Request, urlopen

from poketrix.advisor.latency import percentile
from poketrix.schemas import Generation
from poketrix.showdown.validation import load_battles

from .server import HOST, OverlayServer


def measure(battles_per_gen: int = 2) -> dict[int, list[float]]:
    server = OverlayServer(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://{HOST}:{server.server_address[1]}"
    times: dict[int, list[float]] = {}
    try:
        for gen in Generation:
            played = [battle for battle in load_battles(gen) if "player" in battle]
            for number, battle in enumerate(played[:battles_per_gen]):
                room, decisions = f"battle-latency-{int(gen)}-{number}", 0
                for line in battle["player"].splitlines():
                    started = perf_counter()
                    body = json.dumps({"room": room, "lines": [line]}).encode()
                    with urlopen(Request(f"{base}/line", data=body, method="POST")) as answer:
                        found = json.loads(answer.read())["decisions"]
                    if found == decisions:
                        continue
                    decisions = found
                    with urlopen(f"{base}/advice?room={room}") as answer:
                        answer.read()
                    times.setdefault(int(gen), []).append((perf_counter() - started) * 1000)
    finally:
        server.shutdown()
        server.server_close()
    return times


def main() -> None:
    per_gen = int(sys.argv[1]) if sys.argv[1:] else 2
    times = measure(per_gen)
    print("| Gen | Decisions | p50 ms | p95 ms | max ms |")
    print("|-----|-----------|--------|--------|--------|")
    everything = [t for found in times.values() for t in found]
    for gen, found in [*times.items(), ("all", everything)]:
        print(f"| {gen} | {len(found)} | {percentile(found, 0.5):.0f} "
              f"| {percentile(found, 0.95):.0f} | {max(found):.0f} |")


if __name__ == "__main__":
    main()
