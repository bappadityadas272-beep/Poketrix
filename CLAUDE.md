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

## Current state — Task 02 built on `task/02-dex-data`, awaiting review (2026-10-10)

| Tag   | What exists |
|-------|-------------|
| cp-00 | Project skeleton (pyproject, src layout, pytest, checkpoint workflow) |
| cp-01 | `src/poketrix/schemas/` — gen-aware contracts, 35 passing tests |
| (cp-02 pending) | `src/poketrix/dex/` + `data/dex/` — offline Gen 1–4 dex, 68 tests total |

Schema map (`from poketrix.schemas import ...`):
- `generation.py`: `GenRules` / `rules_for(gen)`. This is what exists per gen: types, items, abilities,
  natures, DV vs IV caps, damage-roll count (39 in Gens 1–2, 16 from Gen 3), weathers, hazards.
- `pokemon.py`: `Species`, `Move` (static dex data, one per generation), `StatSpread`,
  `PokemonSet`, `BattlePokemon` (in-battle; the opponent only has `revealed_*`), `to_id()`.
- `battle.py`: `GameState` → `SideState` (team, conditions, our `ActionRequest`) + `FieldState`.
- `outputs.py`: `DamageRange`, `KOChance`, `MathReport`, `SetPosterior`, `ActionPrediction`,
  `SubsystemResult[T]`, and `Recommendation` (the LLM guardrail). Validate it with
  `context={"state": gs, "allowed_numbers": {...}}` to reject illegal moves and invented numbers.

Dex (`from poketrix.dex import Dex, UnknownDexEntryError`):
- `Dex(gen)`: `species(name_or_id)`, `move(name_or_id)`, `all_species()`, `all_moves()`.
  Unknown ids raise `UnknownDexEntryError` (a `KeyError`); `Dex(5)` raises `ValueError`.
- `dex/snapshot.py` loads `data/dex/gen{N}/{species,moves}.json` once per gen (cached) and
  validates every record against the schemas. Returned objects are shared: treat as read-only.
- Source of truth: `@pkmn/dex` (Showdown data), version recorded in `data/dex/manifest.json`.
  Rebuild: `cd scripts && npm install && npm run build-dex`. Node is build-time only.
- Snapshot conventions (decided with the user):
  - Battle formes are included (Deoxys, Rotom, Wormadam, Giratina-Origin, Shaymin-Sky, Arceus
    types, Castform…), sharing the base `dex_number`. Count species by distinct dex number.
  - Gen 1 Bide is stored as Normal (cartridge type), not Showdown's `???`.
  - Typed Hidden Powers are keyed `hiddenpowerfire` etc. (Showdown shares the id `hiddenpower`),
    with Showdown's max-IV 70 BP. Real HP type/power from IVs/DVs is the Math layer's job.
  - Abilities are empty in Gens 1–2 and limited to those existing in that gen from Gen 3.
  - Learnsets are deferred.

Known, deliberate gaps:
- `BattlePokemon.volatiles` is a free-form id set. Tighten it once the Showdown parser shows the
  real set.
- Natures are stored as ids. The 25-nature table belongs to the Math layer.
- No items/abilities tables in the dex yet (only ability ids per species). Add when Task 03 needs them.

## ▶ START HERE: review Task 02, then Task 03

1. User reviews `task/02-dex-data`. After approval: merge `--no-ff` into `main`, tag `cp-02`,
   log it in `docs/CHECKPOINTS.md`, mark it done in `README.md`.
2. Then Task 03, Math layer (see roadmap). Propose the design first and stop for review.

## Roadmap

03 Math layer (type chart per gen, stat formula, damage rolls, exact KO odds, then Monte Carlo;
   Gen 4 first, verified against the Showdown damage calc) → 04 Bayesian set uncloaker →
05 Showdown battle-log parser → `GameState` → 06 orchestrator (plain state machine) and synthesis
guardrail → 07 XGBoost action predictor (needs replay data).
