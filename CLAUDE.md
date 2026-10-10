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

## Current state — `cp-03b` merged; Task 03c built on `task/03c-gens-3-2-1`, awaiting review (2026-10-10)

| Tag   | What exists |
|-------|-------------|
| cp-00 | Project skeleton (pyproject, src layout, pytest, checkpoint workflow) |
| cp-01 | `src/poketrix/schemas/` — gen-aware contracts, 35 passing tests |
| cp-02 | `src/poketrix/dex/` + `data/dex/` — offline Gen 1–4 dex, 68 tests total |
| cp-03a | `src/poketrix/calc/` — Gen 4 damage core, exact KO odds, 231 tests total |
| cp-03b | Gen 4 items, abilities, multi-hit and remaining moves; item data; 352 tests total |
| (cp-03c pending) | Gen 3, Gen 2 and Gen 1 engines, verified against the oracle; 678 tests total |

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
- `Dex(gen)`: `species(name_or_id)`, `move(name_or_id)`, `item(name_or_id)` and `all_*()`.
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

Calc (`from poketrix.calc import ...`), all four generations:
- `evaluate_move(attacker, defender, move, field, defender_conditions) -> MoveEvaluation` and
  `build_report(...) -> SubsystemResult[MathReport]`. Both Pokémon need a `known_set`.
- One engine per generation behind the `DamageEngine` protocol (`engine.py`, one method:
  `evaluate(...) -> Outcome`), all extending `base.BaseEngine`. No generation's package imports
  another's:
  - `gen4/` and `gen3/` extend `modern.ModernEngine` (immunities, fixed damage, multi-hit) and
    supply only their formula (`engine.py`) and its stage rules (`modifiers.py`, `power.py`).
  - `classic/` holds `ClassicEngine` with `Gen1Engine` and `Gen2Engine`: one formula, and each
    subclass fills in the steps that differ.
  - Shared by all: `context.py`, `power_rules.py`, `stats.py`, `typechart.py`, `ko.py`.
- A new ability or item rule goes into the stage it belongs to, in the oracle's order; the
  formula skeleton does not change. A later generation is a new package, not a branch.
- Gens 1–2 spreads are DVs (0–15) and Stat Exp (0–65535) in `StatSpread.ivs` / `.evs`; a
  missing value is the maximum.
- Accuracy, crit rate and multi-hit counts are not in the oracle; they follow the Showdown
  simulator's source for each generation and are tested by hand and by brute force.
- The oracle is `@smogon/calc` 0.12.0: `tests/fixtures/calc_golden_gen{1..4}.json` (rebuild with
  `cd scripts && npm run build-calc-golden`; cases in `scripts/golden_cases/`). Every roll must
  match exactly; when adding a mechanic, add tagged cases to the generator first.
- A move the engine cannot evaluate returns `unsupported_reason`, never a guessed number.
- State that is not a stat stage is read from `BattlePokemon.volatiles`: `flashfire`,
  `slowstart`, `unburden`, `charge`, `focusenergy`, `foresight`, `confusion`.
- Type chart and natures come from the snapshot: `poketrix.dex.load_type_chart(gen)`,
  `load_natures()`.

Known, deliberate gaps:
- `BattlePokemon.volatiles` is a free-form id set. Tighten it once the Showdown parser shows the
  real set.
- No items/abilities tables in the dex yet (only ability ids per species). Add when Task 03 needs them.

## ▶ START HERE

Read `docs/PROGRESS_TRACKER.md` → section **"Orders for Claude Code"** and follow the orders in that
order. The tracker is the logbook: the user's reviewer writes verdicts and next orders there, and you
record what you built there. Always update it at the end of a step.

## Roadmap

03 Math layer (type chart per gen, stat formula, damage rolls, exact KO odds, then Monte Carlo;
   Gen 4 first, verified against the Showdown damage calc) → 04 Bayesian set uncloaker →
05 Showdown battle-log parser → `GameState` → 06 orchestrator (plain state machine) and synthesis
guardrail → 07 XGBoost action predictor (needs replay data).
