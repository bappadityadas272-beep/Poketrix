# CLAUDE.md — Poketrix

Read this whole file before doing anything. It is the hand-off checkpoint between sessions.

## What this project is

Poketrix is a real-time decision engine for competitive Pokémon (Showdown). Every number comes from
deterministic math, statistics or a data lookup; an LLM only phrases already-computed results.
Full design: `Poketrix_Architecture_Documentation.docx` (repo root).

Settled scope decisions (do not reopen without the user):
- **Generations 1–4 only** for now; Gen 5+ is a later extension. `generation` is a first-class field
  everywhere; per-gen rules live in one place: `src/poketrix/schemas/generation.py`.
- **Competitive ladder first** (Showdown). Nuzlocke/progression, knowledge graph, RAG and vision
  ingestion are deferred.
- **Math layer is built Gen 4 first**, then back-ported Gen 3 → 2 → 1.
- **Priors for the Bayesian layer** = Showdown's Gen 1–4 Random Battle set pools.

## Non-negotiable engineering rules

1. **No LLM mathematics.** Damage, stats, type multipliers, move legality: deterministic code only.
2. **Every data boundary is a Pydantic model** from `poketrix.schemas`. Don't pass raw dicts between layers.
3. **Graceful fallbacks:** subsystems return `SubsystemResult[T]` (ok / fallback / timeout / error).
4. **Latency budget:** < 500 ms end to end per turn (ingest < 50 ms, ML < 150 ms).

## Working agreement with the user (Bappaditya)

- **Stop after every step for human review.** Explain what you did and what you decided, then wait.
  The user cross-questions before anything is merged. Don't chain several steps unasked.
- **Checkpoint workflow** (details in `docs/CHECKPOINTS.md`):
  - Never commit directly to `main`. Each task gets a branch: `task/NN-short-name`.
  - Merge with `--no-ff` and tag `cp-NN` **only after the user approves** and `pytest` is green.
  - If a task gets stuck, leave its branch alone and branch again from `main`.
    Never `git reset --hard` or force-push `main`.
  - Log every new tag in the table in `docs/CHECKPOINTS.md`.
- Ask before downloading large datasets or adding heavy dependencies.

## Environment

- Windows. The repo is in `C:\Users\Lenovo\OneDrive\Desktop\Poketrix`, inside OneDrive. If git shows
  odd lock or sync errors, that's the likely cause.
- Python >= 3.10 is supported, so import `Self` from `typing_extensions`, not `typing`.
- Setup: `python -m venv .venv` → `.venv\Scripts\activate` → `pip install -e ".[dev]"` → `pytest`
- Lint: `ruff check src tests` (must be clean).
- GitHub: `https://github.com/bappadityadas272-beep/poketrix` (if `git remote -v` is empty, the
  user hasn't pushed yet; ask them).

## Current state — checkpoint `cp-01` (2026-10-10)

| Tag   | What exists |
|-------|-------------|
| cp-00 | Project skeleton (pyproject, src layout, pytest, checkpoint workflow) |
| cp-01 | `src/poketrix/schemas/` — gen-aware contracts, 35 passing tests |

Schema map (`from poketrix.schemas import ...`):
- `generation.py`: `GenRules` / `rules_for(gen)`. This is what exists per gen: types, items, abilities,
  natures, DV vs IV caps, damage-roll count (39 in Gens 1–2, 16 from Gen 3), weathers, hazards.
- `pokemon.py`: `Species`, `Move` (static dex data, one per generation), `StatSpread`,
  `PokemonSet`, `BattlePokemon` (in-battle; the opponent only has `revealed_*`), `to_id()`.
- `battle.py`: `GameState` → `SideState` (team, conditions, our `ActionRequest`) + `FieldState`.
- `outputs.py`: `DamageRange`, `KOChance`, `MathReport`, `SetPosterior`, `ActionPrediction`,
  `SubsystemResult[T]`, and `Recommendation` (the LLM guardrail). Validate it with
  `context={"state": gs, "allowed_numbers": {...}}` to reject illegal moves and invented numbers.

Known, deliberate gaps:
- Schemas check **structure + generation legality only**. Whether "stoneedge" really exists with the
  right power is the dex layer's job (Task 02).
- `BattlePokemon.volatiles` is a free-form id set. Tighten it once the Showdown parser shows the
  real set.
- Natures are stored as ids. The 25-nature table belongs to the Math layer.

## ▶ START HERE: Task 02, Dex data layer (Gens 1–4)

Branch: `git switch main && git switch -c task/02-dex-data`

**Goal:** a local, versioned, offline dex that returns schema-validated `Species` and `Move`
objects for any generation 1–4. This gives "stoneedge" real data and feeds the Math layer (Task 03).

**Step 1 — propose a data source, then STOP for review.** Candidates:
- Pokémon Showdown's own data. Its ids match the battle protocol, and it has gen-specific mods for
  Gen 1–4 stats, types and move changes. Options include the `@pkmn/dex` npm package
  (gen-aware), exported once to JSON by a small Node script.
- PokeAPI. It's the doc's original choice, but its gen-specific values (`past_types`,
  `past_values`, Gen 1 Special) need reconstruction work.
- Recommended: Showdown or `@pkmn` as the source of truth, with PokeAPI as an optional cross-check.
  Present the trade-off and let the user decide.

**Step 2 — build after approval:**
- `scripts/build_dex.*` fetches or exports the raw data, then writes a compact JSON snapshot per
  generation to `data/dex/gen{1..4}/{species,moves}.json`. The snapshot is small and committed, so
  tests run offline; raw downloads go to the git-ignored `data/raw/`.
- `src/poketrix/dex/`: `Dex(gen)` with `species(id) -> Species`, `move(id) -> Move`,
  `learnset(id)` (optional, can wait for later), and an lru-cached loader. Every record is passed
  through the schemas at load time, so bad data fails loudly.

**Acceptance tests (must pass before asking to merge):**
- Every species and move in all four snapshots validates against the schemas.
- Species counts are 151, 251, 386 and 493 for Gens 1–4.
- Gen 1 Magnemite is pure Electric; Gen 2 Magnemite is Electric/Steel.
- Gen 1 Gengar has a single Special stat of 130.
- Gen 3 Fire Punch is special; Gen 4 Fire Punch is physical.
- Gen 1 Bite is Normal-type, with 60 BP; from Gen 2 it's Dark-type.
- Gen 4 Garchomp has base stats 108/130/95/80/85/102.
- Unknown ids raise a clear `KeyError`-style error, and `Dex(5)` is rejected.
- `ruff` is clean and the full `pytest` suite is green.

**Then:** stop and ask the user for review. Once they approve, merge, tag `cp-02` and log it.

## Roadmap after Task 02

03 Math layer (type chart per gen, stat formula, damage rolls, exact KO odds, then Monte Carlo;
   Gen 4 first, verified against the Showdown damage calc) → 04 Bayesian set uncloaker →
05 Showdown battle-log parser → `GameState` → 06 orchestrator (plain state machine) and synthesis
guardrail → 07 XGBoost action predictor (needs replay data).
