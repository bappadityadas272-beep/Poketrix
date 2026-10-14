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

- Windows. The repo lives at `C:\dev\Poketrix` (moved out of OneDrive on 2026-10-14). If the
  working directory is still under `OneDrive\Desktop`, the move has not happened yet: say so.
  After a move the `.venv` must be recreated (it remembers its old path).
- Caches are outside the repo, under `%LOCALAPPDATA%\poketrix-cache`: `pokemon-showdown` (the
  simulator checkout; set `POKETRIX_SHOWDOWN_DIR` to it before running `poketrix.arena` or
  rebuilding the prior), `battles` (the simulated corpus) and `arena` (tuning and evaluation
  results). `data/raw/` in the repo is git-ignored and holds the 2,000 real replays.
- The user works in day sessions. "Let's resume where we left" (or "resume") starts one: read
  the tracker's current orders and carry them out. "Save it all" ends one: commit and push,
  start nothing new.
- Python >= 3.10 is supported, so import `Self` from `typing_extensions`, not `typing`.
- Setup: `python -m venv .venv` → `.venv\Scripts\activate` → `pip install -e ".[dev]"` → `pytest`
- Lint: `ruff check src tests` (must be clean).
- GitHub: `https://github.com/bappadityadas272-beep/poketrix` (if `git remote -v` is empty, the
  user hasn't pushed yet; ask them).

## Current state — `cp-07` merged (Phases 0–7 done; opponent model xgb-1 shown as "opponent tendency"); next: Phase 8, the overlay, Order 16 (2026-10-15)

| Tag   | What exists |
|-------|-------------|
| cp-00 | Project skeleton (pyproject, src layout, pytest, checkpoint workflow) |
| cp-01 | `src/poketrix/schemas/` — gen-aware contracts, 35 passing tests |
| cp-02 | `src/poketrix/dex/` + `data/dex/` — offline Gen 1–4 dex, 68 tests total |
| cp-03a | `src/poketrix/calc/` — Gen 4 damage core, exact KO odds, 231 tests total |
| cp-03b | Gen 4 items, abilities, multi-hit and remaining moves; item data; 352 tests total |
| cp-03c | Gen 3, Gen 2 and Gen 1 engines, verified against the oracle; 679 tests total |
| cp-04 | `src/poketrix/uncloak/` + `data/randbats/` — set prior, Bayesian uncloaker, threat report; 731 tests total |
| cp-05 | `src/poketrix/showdown/` — battle-log parser, spectator and player mode, evidence rules, corpus measurements; 846 tests total |
| cp-05b | Prior, held-out tables and battle fixtures rebuilt from Showdown's current source; 847 tests total |
| cp-06 | `src/poketrix/advisor/` and `src/poketrix/arena/` — turn engine, decision policy, simulator harness, golden decisions; 910 tests total |
| cp-07 | `src/poketrix/opponent/` + `data/models/` — decision dataset from real replays, xgb-1, display calibration, tendency line; 928 tests total |

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

Uncloak (`from poketrix.uncloak import Uncloaker, load_prior`):
- `Uncloaker(load_prior(gen)).uncloak(species, SetEvidence(...))` returns
  `SubsystemResult[SetPosterior]`. Status `ok` is plain Bayes over the known sets; `fallback`
  means the evidence contradicted every known set (tiers 2 and 3); it never raises.
- The prior is `data/randbats/gen{N}/sets.json`, sampled from Showdown's official generator
  (100,000 teams). Its `source` records where from: currently a git checkout at commit
  `942cda7` (2026-10-09), because npm releases are rare and the live sets move on between them.
- Rebuild: `scripts/randbats/simulator.mjs` picks the source. Default is the npm package
  (`cd scripts/randbats && npm install && npm run build-randbats`; a 181 MB install, hence the
  separate folder). For the current sets, clone `smogon/pokemon-showdown` with `--depth 1` into
  `%LOCALAPPDATA%\poketrix-cache\pokemon-showdown` (never inside the repo or OneDrive), run
  `npm install && node build` there, and set `POKETRIX_SHOWDOWN_DIR` to it. Rebuild the battle
  fixtures with the same source. Accept a rebuild only if `tests/test_uncloak.py` passes and
  `python -m poketrix.showdown.corpus` shows the floor at 0 and ladder staleness not higher.
- `SetPrior.pokemon_set(set_id)` gives the full `PokemonSet` (level and spread included) for
  the damage calculator.
- `threat_report(ours, theirs, posterior, prior, ...)` returns `SubsystemResult[ThreatReport]`:
  each move the opponent may carry with its probability and its damage to our Pokémon, plus
  `p_ko_best_move` (can they knock us out this turn?). It only joins the posterior and
  `evaluate_move`; damage rules never go here. In a UI, "worst case" is `worst_crit_pct`.
- `python -m poketrix.uncloak.evaluation` prints the held-out metrics; `tests/test_uncloak.py`
  asserts the agreed targets. Paste a new table into the tracker when the prior is rebuilt.

Showdown parser (`from poketrix.showdown import parse_battle, BattleTracker, parse_line`):
- `parse_battle(log_text)` returns a `BattleRecord`: one `TurnSnapshot` per turn with a
  validated `GameState`, a `SetEvidence` per revealed Pokémon, and the turn's typed events.
- `protocol.py` only parses lines; `tracker.py` is the only place state changes;
  `evidence.py` holds the rules for what counts as revealed or ruled out. Keep them apart.
- **Evidence rules must stay conservative**: when a line could mean two things, conclude
  nothing. Any change to them must keep `python -m poketrix.showdown.validation` at zero
  false claims, on the fixtures and on the on-demand corpus (`cd scripts/randbats &&
  node build_battles.mjs 500 raw`, then pass `data/raw/battles` to the validation).
- A battle log shows "Hidden Power" without its type: compare moves with
  `schemas.move_matches` / `moves_fit`, never with `==` or set inclusion.
- `BattlePokemon.revealed_item` is what the Pokémon holds now; `SetEvidence.item` is what it
  started with. They differ after Trick or Thief.
- **Player mode** is automatic when the log has `|request|` lines: our six Pokémon get a
  `known_set` (`ownset.py`: the spread from the prior that reproduces the request's stats) and
  exact HP, and there is one snapshot per decision with `state.me.request` set, including forced
  switches. `(turn, decision_index)` identifies a snapshot (0 = the turn's main choice); Phase 7
  uses it as the row key. The spreads come through the `SetSource` protocol, so importing the
  parser does not load the prior. Each request is checked against the log before it is believed;
  `BattleRecord.request_disagreements` must stay empty.
- A request may offer moves outside the known set: `schemas.FORCED_MOVES` (`struggle`,
  `recharge`, Gen 1 `fight`), and anything while the `transform` or `mimic` volatile is set.
- Doubles and teams of more than six raise `UnsupportedBattleError`.
- `python -m poketrix.showdown.corpus [replay dir] [battle dir]` measures robustness on real
  replays (`python scripts/download_replays.py`, into git-ignored `data/raw/replays/`; never
  commit replays, they hold usernames and chat) and the staleness of the prior. Only ladder
  games (a bare `|rated|` line) count towards staleness. Run it again after any prior rebuild.
- The player-mode ground truth needs player logs: `node build_battles.mjs 500 DIR 500` (307 MB;
  keep DIR outside OneDrive), then pass DIR to the validation.

Turn engine (`from poketrix.advisor import TurnAdvisor`):
- Evaluated once (Order 13): 77.4% of 4,000 paired games against a max-damage player, 93.5%
  against the simulator's random player. The evaluated setting is the code's default
  (`PolicySettings`: γ 0.5, `a_floor` 0, `utility_scale` 1.5). **Evaluation indices
  2,000,000–2,000,499 are used up**; a changed policy is judged on a fresh range written in the
  tracker first. A formula or setting change needs a stop.
- **Golden decisions:** `tests/test_golden_decisions.py` replays eight recorded games and
  requires every choice to come out as recorded. A refactor must keep it green; re-record
  (`python -m poketrix.arena record`) only when the policy changes on purpose, and log it.
- `poketrix.arena` (a dev tool, never imported by the runtime) plays paired games through
  `scripts/randbats/play_bridge.mjs`; results and tuning files live in
  `%LOCALAPPDATA%\poketrix-cache\arena`, quarantined games in `data/raw/quarantine/`.
- `TurnAdvisor().advise(snapshot) -> TurnReport` for a player-mode snapshot (one with a request).
  A plain state machine in `pipeline.py`: uncloak → threats → offence → order → opponent →
  policy → write. Each stage returns a `SubsystemResult` inside its own budget
  (`STAGE_BUDGET_MS`) and the turn's 500 ms; a `Deadline` is checked between units of work,
  there are no threads. There is always a legal answer: the last resort is `policy.by_power`.
- `stages.py` only joins existing layers; maths stays in `calc` (`acts_first_chance`,
  `expected_hp_share`) and in the threat report (`expected_best_share`). The policy's formula
  and its approximations are documented in `policy.py`'s docstring: keep them in step.
- `TurnReport.numbers` is the only source of `allowed_numbers`. A writer may print nothing
  else: `writer.py` quotes through `_Quotes`, and a test reads every number out of the text.
- A stage with nothing to work on (transformed Pokémon, fainted target, no posterior) returns
  `fallback` with an empty payload and the reason; `error` means it raised.
- R15: a switch refused by a trapping ability is re-asked and costs no turn (`sim/side.ts`), so
  the trapping risk is stated in the text and never scored.
- `python -m poketrix analyze <log> [--turn N]` prints a turn; `python -m
  poketrix.advisor.latency [dir] [n]` prints the per-stage latency table.
- CI: `.github/workflows/tests.yml` runs `ruff` and `pytest -m "not timing"` on 3.10 and 3.12.

Opponent model (`from poketrix.opponent import XgbModel, Heuristic, DecisionView`):
- **Ruling 15-R: the policy keeps heuristic-0 everywhere** (`TurnAdvisor(opponent_model=...)` defaults to it). xgb-1 is
  information only: `advisor/tendency.py` → "Opponent tendency: switch X% · attack Y% · utility Z%", with switch odds above
  `XgbModel.switch_cap` (0.70) shown as "70%+". Feeding xgb-1 into the policy is v2, after a human trial.
- `DecisionView` (`features.py`) is the feature vector; changing its fields makes saved models stale (`XgbModel` refuses them).
  Stage 5 builds it with `stages.opponent_view`; the dataset builds it with the same code (`dataset.view_of`).
- `XgbModel` walks the saved trees with NumPy (needs `[ml]`; XGBoost only for training) and applies the manifest's isotonic
  `display_calibration`; without NumPy or its files it raises `ModelUnavailable` and stage 5 falls back to heuristic-0.
- Rebuild: `python -m poketrix.opponent.dataset` (ladder games only, into git-ignored `data/raw/opponent/`), then
  `.training`, then `.calibration`; `.evaluation` prints the test tables. **The test split (seed 20261501) has been read twice;
  do not read it again** (calibration uses train + valid only). Labels include `stay` (a move was chosen but hidden).
- **Indices 3,000,000–3,000,199 are used up** (the Phase 7 downstream check).

Carried forward (from the Task 04 review):
- R8 is decided: no probability is held back for unseen sets. The prior is rebuilt from
  Showdown's current source instead (`cp-05b`): ladder staleness on 2,000 real replays went
  from about 0.3% in Gens 3–4 to 0 in every generation. It will drift again as the live sets
  change; the corpus measurement is how to notice.
- For Phase 6: R14, a switch recommendation must carry the trapping risk (Shadow Tag, Arena
  Trap, Magnet Pull against our Steel-type) from the ability posterior, and offer a move as
  well when it is 0.5 or more; R11, no damage numbers for a transformed Pokémon; the live
  client must pass lines in arrival order (the request comes after the `|turn|` update).
- If the test suite keeps slowing down, give the evaluation tests a `slow` marker (R9); the
  full suite stays mandatory before every merge.

Carried forward (from the 03c review):
- A move the calculator reports as unsupported (Counter, Bide, Present, …) must reach the user
  as "unsupported", through a `SubsystemResult` with status `fallback` or `error`. Later
  phases must never turn it into zero damage. Applies to Phase 6 (orchestrator).
- Gens 1–2 reports run near the 5 ms target. Optimise only if the Phase 6 end-to-end
  measurement shows the calculator is the bottleneck.
- Text files are LF on every platform (`.gitattributes`).

Known, deliberate gaps:
- `BattlePokemon.volatiles` stays a free-form id set (decision P8). The parser emits the id of
  whatever `-start` names (`substitute`, `confusion`, `leechseed`, `flashfire`, `slowstart`,
  `focusenergy`, `foresight`, …) plus `transform`.
- No items/abilities tables in the dex yet (only ability ids per species). Add when Task 03 needs them.

**Autonomy envelope (2026-10-13):** routine bug fixes with regression tests, behaviour-neutral refactors and tooling may proceed without a stop; changes to formulas, schemas, pass marks, seeds or the prior must stop for approval. Full rule: `docs/PROGRESS_TRACKER.md` → "Standing rule added: the autonomy envelope".

## ▶ START HERE

Read `docs/PROGRESS_TRACKER.md` → the **"▶ Current orders"** table at the top, then the matching **"▶ ACTIVE — Orders"** section and follow the orders in that
order. The tracker is the logbook: the user's reviewer writes verdicts and next orders there, and you
record what you built there. Always update it at the end of a step.

## Roadmap

03 Math layer (type chart per gen, stat formula, damage rolls, exact KO odds, then Monte Carlo;
   Gen 4 first, verified against the Showdown damage calc) → 04 Bayesian set uncloaker →
05 Showdown battle-log parser → `GameState` → 06 orchestrator (plain state machine) and synthesis
guardrail → 07 XGBoost action predictor (needs replay data).
