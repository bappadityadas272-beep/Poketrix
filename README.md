# Poketrix

A real-time probabilistic decision engine for competitive Pokémon: deterministic math for anything
with an exact answer, probabilistic ML for genuine uncertainty, retrieval for knowledge questions —
and an LLM that only ever *explains* already-computed numbers.

**Current scope:** Generations 1–4, competitive ladder (Showdown) first. Later gens are an extension.

## Build order

| # | Phase | Status |
|---|-------|--------|
| 0 | Repo scaffold + checkpoint workflow | done |
| 1 | Shared Pydantic schemas (gen-aware) | done (cp-01) |
| 2 | Dex data layer (Gens 1–4 species/moves snapshot) | done (cp-02) |
| 3 | Deterministic Math layer (type chart, stats, damage) — Gen 4 first, then 3 → 2 → 1 | done (cp-03a, cp-03b, cp-03c) |
| 4 | Bayesian set uncloaker (Showdown Gen 1–4 Random Battle set pools as priors) | done (cp-04) |
| 5 | Showdown battle-log parser → `GameState` | done (cp-05) |
| 6 | Turn engine: a plain state machine, a score-based decision policy, template text behind a guardrail | done (cp-06) |
| 7 | Opponent model: XGBoost on real ladder decisions, shown as the "opponent tendency" | done (cp-07) |
| 8 | Overlay: a local server and a read-only Chrome extension | in progress |
| — | Knowledge graph / RAG, vision ingestion | deferred |

## Does the advice win games?

The turn engine was played in Showdown's own simulator, in Gen 1–4 Random Battles. Every game was
played twice with the two teams swapped, so the luck of the draw mostly cancels. The settings
were tuned on one set of games and then judged once on another, fixed in advance.

**It beat a player that always picks the hardest-hitting move in 77.4% of 4,000 games** (95%
interval 76.1% to 78.6%), and it won in every generation.

| Match | Gen 1 | Gen 2 | Gen 3 | Gen 4 | All (95% interval) |
|-------|-------|-------|-------|-------|--------------------|
| Poketrix against the max-damage player | 68.7% | 79.5% | 81.0% | 80.3% | **77.4%** (76.1–78.6%) |
| Poketrix against the simulator's random player | 84.7% | 95.2% | 97.3% | 96.6% | 93.5% (92.6–94.2%) |
| Max-damage against the random player, for reference | 84.2% | 88.9% | 89.9% | 86.8% | 87.5% (86.4–88.4%) |

1,000 games per cell. Across the 259,873 decisions Poketrix made, the simulator rejected none, no
decision ended in an error, and 95% took under 45 ms (the budget is 500 ms).

What this does and does not show: the advice is clearly better than greedy play and than random
play. It says nothing yet about play against people; Gen 1 is the weakest generation; and the
max-damage player uses Poketrix's own estimate of the opponent's set.

```bash
python -m poketrix analyze battle.log --turn 9   # the engine's reading of one turn of your own log
```

## The overlay (read-only)

A side panel in Chrome shows the advice for the battle in front of you: the headline, the top three
options with their numbers, the opponent's two likeliest sets, the threat, and the opponent tendency
(what ladder players do in that position; shown for information, never used by the advice).

```bash
pip install -e ".[ml]"           # NumPy for the opponent tendency (optional: without it the line says so)
python -m poketrix serve         # listens on 127.0.0.1:8765 only
```

Then load `extension/` in Chrome (`chrome://extensions` → Developer mode → Load unpacked) and click the
Poketrix button to open the panel. On `replay.pokemonshowdown.com` it advises from player 1's side,
turn by turn as the replay plays, which needs no live game.

**Fair play.** Poketrix never sends a choice and never touches your account. **It is off in rated
battles:** when a live battle is rated, the server computes nothing and the panel says "Poketrix is off
in rated battles". Advice is available in unrated games, challenges and replays.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -e ".[dev]"
pytest
```

`pytest` runs every correctness test. The latency budgets are checked separately, because they
depend on how busy the machine is:

```bash
pytest -m timing        # latency budgets only
pytest -m "not slow"    # quick run: skips the corpus evaluations
```

See `docs/CHECKPOINTS.md` for the branch/tag workflow.
