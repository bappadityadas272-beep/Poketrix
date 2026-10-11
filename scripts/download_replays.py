"""Downloads public Gen 1-4 Random Battle replays for the parser's robustness checks.

    python scripts/download_replays.py            500 replays per generation
    python scripts/download_replays.py 50         a smaller sample

Replays go to data/raw/replays/gen{N}/ (git-ignored: they contain usernames and chat, so they are
never committed). data/replays_manifest.json, which is committed, records which replay ids were
used and when they were uploaded, so a result can be traced back to its sample.

The site is a volunteer-run public service: one request at a time, at least a second apart,
an honest User-Agent, and a growing wait after any error. Already-downloaded replays are skipped,
so an interrupted run can simply be started again.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "raw" / "replays"
MANIFEST = ROOT / "data" / "replays_manifest.json"
SITE = "https://replay.pokemonshowdown.com"
USER_AGENT = "Poketrix research script (github.com/bappadityadas272-beep/Poketrix)"
GENERATIONS = (1, 2, 3, 4)
DEFAULT_COUNT = 500
SECONDS_BETWEEN_REQUESTS = 1.2
MAX_ATTEMPTS = 5
KEPT_FIELDS = ("id", "formatid", "uploadtime", "rating", "log")

_last_request = 0.0


def fetch_json(url: str):
    """One polite GET: spaced from the previous one, retried with a growing wait on errors."""
    global _last_request
    for attempt in range(1, MAX_ATTEMPTS + 1):
        time.sleep(max(0.0, _last_request + SECONDS_BETWEEN_REQUESTS - time.monotonic()))
        _last_request = time.monotonic()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == MAX_ATTEMPTS:
                raise
            wait = 10 * 2 ** (attempt - 1)
            print(f"  {type(error).__name__} on {url}; waiting {wait}s", flush=True)
            time.sleep(wait)


def recent_replays(format_id: str, count: int) -> list[dict]:
    """The newest public replays of a format, newest first (the listing pages by upload time)."""
    found: dict[str, dict] = {}
    before = None
    while len(found) < count:
        url = f"{SITE}/search.json?format={format_id}" + (f"&before={before}" if before else "")
        page = fetch_json(url)
        fresh = [entry for entry in page if entry["id"] not in found and not entry.get("private")]
        if not fresh:
            break
        found.update({entry["id"]: entry for entry in fresh})
        before = min(entry["uploadtime"] for entry in page)
    return list(found.values())[:count]


def download(gen: int, count: int) -> dict:
    format_id = f"gen{gen}randombattle"
    folder = OUT_DIR / f"gen{gen}"
    folder.mkdir(parents=True, exist_ok=True)
    listing = recent_replays(format_id, count)
    for number, entry in enumerate(listing, start=1):
        path = folder / f"{entry['id']}.json"
        if not path.exists():
            replay = fetch_json(f"{SITE}/{entry['id']}.json")
            kept = {field: replay.get(field) for field in KEPT_FIELDS}
            path.write_text(json.dumps(kept), encoding="utf-8")
        if number % 50 == 0:
            print(f"gen{gen}: {number}/{len(listing)}", flush=True)
    uploaded = [entry["uploadtime"] for entry in listing]

    def day(timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()

    return {
        "format": format_id,
        "replays": len(listing),
        "uploaded_from": day(min(uploaded)),
        "uploaded_to": day(max(uploaded)),
        "rated": sum(1 for entry in listing if entry.get("rating")),
        "ids": sorted(entry["id"] for entry in listing),
    }


def main() -> None:
    count = int(sys.argv[1]) if sys.argv[1:] else DEFAULT_COUNT
    manifest = {
        "source": SITE,
        "downloaded": datetime.now(tz=timezone.utc).date().isoformat(),
        "generations": {str(gen): download(gen, count) for gen in GENERATIONS},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    total = sum(g["replays"] for g in manifest["generations"].values())
    print(f"{total} replays in {OUT_DIR}; manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
