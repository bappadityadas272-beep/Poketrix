# Poketrix — progress tracker

Last updated: 2026-10-15 (batch 10, build to the end: B1–B10 behind flags, then F1)

## Status at a glance

| # | Phase | Status | Checkpoint |
|---|-------|--------|------------|
| 0 | Repo scaffold + checkpoint workflow | Done, merged | `cp-00` |
| 1 | Shared Pydantic schemas (Gen 1–4 aware) | Done, merged | `cp-01` |
| 2 | Dex data layer (Gen 1–4 species and moves) | Done, merged | `cp-02` |
| 3 | Math layer (type chart, stats, damage, KO odds) | **Done, merged** (all four generations) | `cp-03a`, `cp-03b`, `cp-03c` |
| 4 | Bayesian set uncloaker | **Done, merged** (prior, uncloaker, threat report) | `cp-04` |
| 5 | Showdown battle-log parser → `GameState` | **Done, merged** (spectator + player mode; prior rebuilt from Showdown commit 942cda7) | `cp-05`, `cp-05b` |
| 6 | Turn engine: orchestrator + decision policy + template synthesis | **Done, merged.** Evaluation passed on every mark: 77.4% (76.1–78.6) against max-damage over 12,000 games | `cp-06` |
| 7 | XGBoost action predictor | **Done, merged.** xgb-1: log-loss +0.14 over both baselines, ECE 0.016; shown as "opponent tendency", the policy keeps heuristic-0 (15-R) | `cp-07` |
| — | Knowledge graph / RAG, vision ingestion | Deferred | |

Tests: 928 passing on `main` (`cp-07`) in the default run, plus the timing tests with `pytest -m timing`. `ruff` is clean.

## ▶ Current orders (read this first)

**Approach (user, 2026-10-14): build first, verify at the end.** Every remaining feature is built behind a flag that is OFF by
default, so `main` keeps behaving exactly like `cp-08`. One final paired evaluation (F1) decides which flags are switched on.

| Order | What | Stop? | Status |
|-------|------|-------|--------|
| 13–15 | Phase 6 evaluation, hygiene, Phase 7 | — | **Done** (`cp-06`, `cp-07`) |
| 16 | Phase 8 overlay MVP | — | **Done:** replay demo passed (23 ms); the rated-guard bug was found and fixed. Live recheck deferred to F2. `cp-08` |
| 17 | v1 wrap-up (README, v2 list) | — | README and v2 list merged; `v1.0` waits for F3 |
| B1 | Self-KO audit and `selfko_guard` | No | Queued |
| B2 | Opponent priority in move order (`opp_priority`) | No | Queued |
| B3 | Recoil and recharge costs (`self_costs`) | No | Queued |
| B4 | Set-up moves (`setup_value`) | No | Queued |
| B5 | Gen 1 diagnosis and fixes for its top 2 causes (`gen1_*`) | No | Queued |
| B6 | More Gen 2 replays, xgb-2, tail calibration | No | Queued |
| B7 | xgb inside the policy as an option (`opponent_model`) | No | Queued |
| B8 | Independent baseline bot in the arena | No | Queued |
| B9 | Human-agreement proxy on real replays | No | Queued |
| B10 | Housekeeping (logbook archive, dex `selfdestruct`, Gen 1 desync, timing on AC) | No | Queued |
| F1 | Final tuning and paired evaluation (seeds 4,000,000–4,000,499) | **Yes, the first review stop** | Queued |
| F2 | Manual rechecks: the rated guard live, a live game | With the user | Queued |
| F3 | Decoration and `v1.0` | With the user | Queued |

The full text is in "▶ ACTIVE — Orders for Claude Code, batch 10".

## Phase 0 — scaffold (`cp-00`)

- `pyproject.toml`, `src/` layout, pytest and ruff configuration.
- Checkpoint workflow in `docs/CHECKPOINTS.md`: one branch per task, merge `--no-ff` and tag
  `cp-NN` only after human review.

## Phase 1 — schemas (`cp-01`)

`src/poketrix/schemas/`, 35 tests.

- `enums.py`: generations, types, categories, stats, statuses, weathers, side conditions.
- `generation.py`: `GenRules` / `rules_for(gen)`, the single place for per-generation rules.
- `pokemon.py`: `Species`, `Move`, `StatSpread`, `PokemonSet`, `BattlePokemon`, `to_id()`.
- `battle.py`: `GameState`, `SideState`, `FieldState`, `ActionRequest`.
- `outputs.py`: `DamageRange`, `KOChance`, `MathReport`, `SetPosterior`, `ActionPrediction`,
  `SubsystemResult[T]`, `Recommendation` (the LLM guardrail).

## Phase 2 — dex data layer (approved 2026-10-10)

Branch `task/02-dex-data`, merged into `main` as `cp-02`.

What was built:

- `scripts/build_dex.mjs` (+ `scripts/package.json`, `package-lock.json`): exports the snapshot
  from `@pkmn/dex` 0.10.11. Rebuild with `cd scripts && npm install && npm run build-dex`.
  Node is build-time only.
- `data/dex/gen{1..4}/{species,moves}.json` and `data/dex/manifest.json`: committed snapshot,
  about 413 KB, so tests run offline.

  | Gen | Species records | Distinct dex numbers | Moves |
  |-----|-----------------|----------------------|-------|
  | 1 | 151 | 151 | 165 |
  | 2 | 251 | 251 | 267 |
  | 3 | 392 | 386 | 370 |
  | 4 | 530 | 493 | 483 |

- `src/poketrix/dex/snapshot.py`: cached loader; validates every record against the schemas and
  rejects duplicate ids and missing files.
- `src/poketrix/dex/dex.py`: `Dex(gen)` with `species()`, `move()`, `all_species()`,
  `all_moves()`; `UnknownDexEntryError` (a `KeyError`) for unknown ids; `ValueError` for
  unsupported generations.
- `tests/test_dex.py`: 33 tests covering all acceptance criteria from `CLAUDE.md`.
- `CLAUDE.md` and `README.md` updated; `node_modules/` added to `.gitignore`.

Decisions taken with the user:

| Decision | Choice |
|----------|--------|
| Data source | `@pkmn/dex` (Showdown data) |
| Alternate formes | Included, sharing the base dex number |
| Learnsets | Deferred |
| Gen 1 Bide type | Stored as Normal, not Showdown's `???` |

Calls made during the build (confirmed at review, see below):

- Typed Hidden Powers are keyed by their own ids (`hiddenpowerfire`, …) because Showdown gives
  all 16 the shared id `hiddenpower`. They carry Showdown's 70 base power; the real type and
  power from IVs is left to the Math layer.
- Abilities are empty in Gens 1–2 and limited to abilities that exist in that generation from
  Gen 3 (Showdown lists modern abilities in every generation).

## Review of Task 02 (2026-10-10, reviewer: Claude in claude.ai, on behalf of the user)

Verdict: **APPROVED.** 68/68 tests pass on the user's machine. Spot checks on the snapshot:

- Gen 1 type quirks are correct: Bite, Gust and Karate Chop are Normal-type, and Blizzard has 90% accuracy.
- Hidden Power exists only from Gen 2. Before Gen 4 its category follows its type (HP Bug and HP Fighting are physical); in Gen 4 it is always special.
- Abilities are limited to each generation. Gen 3 and Gen 4 Gengar only have Levitate, and Gen 3 Blaziken only has Blaze.
- Formes are present: Deoxys ×4, Rotom ×6 and Giratina-Origin.

Open calls, now **confirmed**:

1. **Typed Hidden Powers** (`hiddenpowerfire` and so on) at 70 base power. This also matches how Showdown's Random Battle
   set pools name them, which helps Task 04. Condition: the Math layer derives Hidden Power's type and power
   from IVs when they are known, falls back to 70 only when they aren't, and never computes damage for the
   untyped `hiddenpower` placeholder (Normal-type, 0 base power).
2. **Abilities limited per generation** from Gen 3, and empty in Gens 1–2.

Findings to carry forward. None of them block the merge.

- **F1: fixed-damage moves.** The snapshot stores base power 1 for moves like Seismic Toss, which is Showdown's convention.
  Seismic Toss, Night Shade, Dragon Rage, Sonic Boom, Super Fang, Psywave, Bide, Counter, Mirror Coat, Endeavor and
  OHKO moves must **not** go through the damage formula. `Move` needs a field that marks this.
  That's a schema change, so Task 03 has to propose it.
- **F2: Gen 1 Bide is stored as Normal**, as decided. Because it deals fixed damage (F1), it ignores the
  type chart in the Math layer, so a Ghost-type isn't immune to it. Add a test.
- **F3:** `.claude/settings.local.json` is per-machine Claude Code configuration. Add it to `.gitignore` and don't commit it.
- **F4:** this tracker file is untracked. Commit it with the merge, because it is the logbook.

## [Completed] Orders for Claude Code (do these in order, stopping where marked)

### ✅ DONE — Order 1: close Task 02 (no stop needed, the user has approved) _(→ cp-02)_
1. On `task/02-dex-data`, add `.claude/settings.local.json` to `.gitignore` and commit this tracker and the
   `CLAUDE.md` pointer change.
2. Run `git switch main`, then `git merge --no-ff task/02-dex-data`, then `git tag -a cp-02 -m "Dex data layer, Gens 1-4"`.
3. Add cp-02 to `docs/CHECKPOINTS.md` (68 tests) and mark phase 2 as done in `README.md`.
4. Run `pytest` and `ruff check src tests` on `main`, then `git push origin main --tags`.
5. Report the push result in one line.

**Result (2026-10-10): done.** Merge commit `7621b89`, tag `cp-02`, 68 tests green and ruff clean on
`main`, pushed (`5cf9c2d..7621b89 main -> main`, new tag `cp-02`). GitHub reported that the repository
moved to `bappadityadas272-beep/Poketrix` (capital P); the old URL still redirects.

### ✅ DONE — Order 2: Task 03 design proposal, Math layer, Gen 4 first. **STOP after the proposal.** _(→ proposal approved, built as cp-03a/b/c)_
Branch: `task/03-math-gen4`. Write the proposal as a new section in this tracker, not as a new file.
It must cover:

- **Package name:** `poketrix.calc`. Don't use `poketrix.math`, because it reads as the standard library's `math`.
- **Type chart per generation:** `effectiveness(gen, move_type, defender_types) -> float`.
  - Gen 1 has quirks: Ghost does 0× to Psychic, Bug and Poison are 2× against each other, and Ice is 1× against Fire.
  - Gens 2–4 use the 17-type chart, in which Steel resists Ghost and Dark.
- **Stat formula:** Gens 3–4 use IVs, EVs and natures. Gens 1–2 use DVs and Stat Exp. Include the 25-nature table.
- **Gen 4 damage formula with an exact roll list (16 rolls).** Keep the integer rounding and the order the modifiers apply in exactly as the games do; that's
  where hand-written calculators usually go wrong. Split it into two stages:
  - **03a:** the core formula, STAB, type effectiveness, critical hits (2×, ignoring stat drops and screens), burn, Reflect and Light Screen, and weather.
  - **03b:** common items and abilities (Choice Band/Specs, Life Orb, Expert Belt, Technician, Adaptability, Huge Power,
    Levitate, Thick Fat, Flash Fire). It can be a separate checkpoint.
- **Fixed-damage path (F1):** propose the schema change and how it's handled, for example a
  `fixed_damage: Literal["level", "half_hp", ...] | int | None` field on `Move`, rebuilt into the snapshot.
- **Exact KO odds:** over 16 rolls × crit chance (1/16 at stage 0 in Gens 2–4) × accuracy, with
  n-hit KO chances by convolving the roll distribution, giving `KOChance(method="exact")`. Monte Carlo is kept for
  cases with secondary effects or across several turns, and is not part of 03a.
- **Verification oracle:** generate golden test cases at build time with **`@smogon/calc`**, the engine behind
  Showdown's damage calculator. Use Node in `scripts/`, the same pattern as `build_dex`, and write the cases to
  `tests/fixtures/calc_golden_gen4.json`, at least 30 of them, including crits, burn, screens, weather, STAB and immunities.
  The Python calculator must match every roll list exactly. Propose how the cases are chosen.
- **Latency target:** a 4-move × 6-matchup report computes in under 5 ms. Include a small timing test.
- **Out of scope for Task 03:** Gens 1–3 (they become Task 03c after Gen 4 is checked), Hidden Power derived from IVs beyond
  a helper function, doubles, and multi-turn effects.

Then **stop** and ask the user to approve or adjust the proposal before writing any calculator code.

## Task 03 design proposal — Math layer, Gen 4 first (2026-10-10, approved)

Branch `task/03-math-gen4`. The formula below was read from the
source of `@smogon/calc` 0.12.0 (`mechanics/gen4.js`), the oracle we have to match.

### Corrections to the review findings

- **F1 is narrower than stated.** Base power 1 appears only in the **Gen 1** snapshot (Counter, Dragon
  Rage, Night Shade, Psywave, Seismic Toss, Sonic Boom, Super Fang). Gens 2–4 store 0 for these.
  The schema change is still needed, because nothing marks *how* they deal damage.
- **Fixed damage still respects type immunity in Gen 4.** The oracle checks immunity before the
  fixed-damage path, so Seismic Toss does 0 to a Ghost-type. F2 (Bide ignoring the type chart) is a
  Gen 1 rule and belongs to Task 03c; the fixed-damage design below carries a per-move flag for it.

### Package layout: `poketrix.calc`

| Module | Responsibility |
|--------|----------------|
| `typechart.py` | `effectiveness(gen, move_type, defender_types) -> float` |
| `stats.py` | Stat formulas (Gens 3–4 now), nature table, stat-stage multipliers |
| `hidden_power.py` | `hidden_power(gen, ivs) -> (type, power)` helper |
| `engine.py` | `DamageEngine` protocol and `engine_for(gen)` registry |
| `gen4.py` | Gen 4 engine: variable roll damage and fixed damage |
| `ko.py` | Exact n-hit KO odds from a per-hit damage distribution |
| `report.py` | Builds `MoveEvaluation` / `MathReport`, wrapped in `SubsystemResult` |

One engine class per generation behind one protocol, so Gens 3 → 1 are added in 03c without
touching the Gen 4 code. Engines work on plain integers internally and build Pydantic models once
at the boundary, which is what keeps the latency target reachable.

**Inputs reuse existing schemas; no new input types.** An engine takes
`(attacker: BattlePokemon, defender: BattlePokemon, move: Move, field: FieldState,
defender_conditions)`. Both Pokémon must carry a `known_set` (stats come from it). For the opponent,
Task 04 will supply a copy with `known_set` filled from a set hypothesis.

### Type chart

- Data, not code: export each generation's chart from `@pkmn/dex` to
  `data/dex/gen{N}/typechart.json` with the existing build script, validated at load.
- `effectiveness` multiplies the per-type factors. The Gen 4 engine applies the two defender types
  as **separate floored steps**, ordered by the canonical type order (Normal, Fire, Water, …,
  Steel), as the oracle does; that order changes results by 1 HP in some 4× and ½×2 cases.
- Acceptance checks: Gen 1 Ghost → Psychic 0×, Bug ↔ Poison 2×, Ice → Fire 1×; Gens 2–4 Steel
  resists Ghost and Dark; `???` (Curse, Struggle) is neutral against everything.

### Stat formula

- Gens 3–4: `HP = floor((2B + IV + floor(EV/4)) × L / 100) + L + 10`;
  other stats `floor((floor((2B + IV + floor(EV/4)) × L / 100) + 5) × nature)`, nature as 110/100/90
  in integer arithmetic. Shedinja's HP is 1.
- Gens 1–2 (DVs, Stat Exp) are written in 03c, but `stats.py` is split by `rules_for(gen)` so the
  slot exists.
- The 25-nature table is exported from `@pkmn/dex` to `data/dex/natures.json`, not typed by hand.
- Stat stages: `floor(stat × (2 + n) / 2)` for boosts, `floor(stat × 2 / (2 − n))` for drops.
- Missing IVs default to 31 and missing EVs to 0 (the convention already documented on `StatSpread`).

### Gen 4 damage formula (exact order, all steps floored)

1. Base power (03b adds power modifiers here, each floored: Technician, type-boosting items,
   Thick Fat, pinch abilities).
2. Attack: raw stat, then stage. **A critical hit ignores negative attacker stages.** (03b: Huge
   Power, Guts, Hustle, Choice Band/Specs, and similar.)
3. Defense: raw stat, then stage. **A critical hit ignores positive defender stages.** Sandstorm
   gives Rock-types ×1.5 Special Defense; Explosion and Self-Destruct halve Defense; minimum 1.
4. `base = floor(floor(floor(2L/5 + 2) × power × A / 50) / D)`
5. Burn: `floor(base × 0.5)` for physical moves.
6. Reflect / Light Screen: `floor(base × 0.5)`, skipped on a critical hit.
7. Weather: sun/rain `floor(× 1.5)` or `floor(× 0.5)` on Fire/Water; Solar Beam halved in rain,
   sand and hail.
8. (03b: Flash Fire boost.) Then `base += 2`.
9. Critical hit: `× 2`. (03b: Sniper ×3, then Life Orb `floor(× 1.3)`.)
10. For each roll `r` in 85…100: `floor(base × r / 100)`, then `floor(× STAB)`, `floor(× type1)`,
    `floor(× type2)`, (03b: Filter/Solid Rock, Expert Belt, Tinted Lens, resist berries), then
    `max(1, …)`.
11. An immune matchup returns the single roll `[0]`.

Non-integer multipliers (1.3, 1.2, 1.1) use the same double-precision operations as the oracle, so
results match bit for bit.

**Stage split**

- **03a (cp-03a):** steps 1–11 without items and abilities, plus fixed damage, exact KO odds, the
  type chart, stats, the golden fixtures and the timing test.
- **03b (cp-03b):** items and abilities listed in the orders, plus crit-stage modifiers, multi-hit
  moves and weight-based moves.

### Fixed-damage path (F1) — proposed schema change

Showdown only has *data* for three cases (`damage: 40`, `damage: 'level'`, `ohko`). Super Fang,
Psywave, Endeavor, Counter, Mirror Coat, Metal Burst and Bide are code callbacks there, so the build
script needs a small explicit id table for them.

New optional field on `Move`:

```python
fixed_damage: int | FixedDamage | None = None

class FixedDamage(str, Enum):
    LEVEL = "level"              # Seismic Toss, Night Shade
    HALF_TARGET_HP = "half_hp"   # Super Fang: max(1, floor(current HP / 2))
    PSYWAVE = "psywave"          # level × (50…150)/100, a roll list of its own
    TARGET_TO_USER_HP = "endeavor"
    OHKO = "ohko"                # target's current HP, if it lands
    REACTIVE = "reactive"        # Counter, Mirror Coat, Metal Burst, Bide: depends on damage taken
```

- An `int` is a flat amount (Sonic Boom 20, Dragon Rage 40).
- Validator: `fixed_damage` set ⇒ `base_power == 0` and the move is not a status move. The build
  script therefore writes 0 instead of Showdown's Gen 1 placeholder 1.
- `REACTIVE` moves cannot be evaluated before the turn, so they produce no damage estimate.
- A second new field, `ignores_type_chart: bool = False`, is set for Gen 1 Bide (F2) and used in 03c.
- Type immunity is checked before fixed damage in Gen 4, as in the oracle.
- The snapshot is rebuilt and the dex tests extended for these fields.

Two further `Move` fields are needed for correct numbers and are proposed with the same rebuild:
`crit_ratio: int = 1` (high-crit moves such as Stone Edge, for KO odds) and
`multihit: tuple[int, int] | None` (03b).

### Moves whose power is not a constant

20-odd Gen 4 moves have base power 0 or a conditional power (Return, Gyro Ball, Low Kick, Grass
Knot, Flail, Reversal, Eruption, Water Spout, Punishment, Fling, Natural Gift, Magnitude, …).

- 03a implements the ones that need only data we already hold: Return/Frustration (102, maximum
  happiness assumed, as the oracle does), Gyro Ball, Eruption/Water Spout, Flail/Reversal, Brine,
  Facade, Wake-Up Slap, Crush Grip/Wring Out, Punishment.
- The rest wait for 03b (they need species weight or item data).
- A move the engine cannot evaluate must be reported as *unsupported*, never as a guessed number.
  That needs one new optional field, `MoveEvaluation.unsupported_reason: str | None`.

### Exact KO odds

- Per-hit distribution = miss (`1 − accuracy`, damage 0) + non-crit (uniform over 16 rolls) + crit
  (uniform over the 16 crit rolls).
- Crit chance by stage in Gen 4: 1/16, 1/8, 1/4, 1/3, 1/2; `crit_ratio` picks the stage in 03a.
- Accuracy = move accuracy × accuracy/evasion stage multiplier; `None` accuracy never misses.
- n-hit KO for n = 1…4: convolve the distribution n times over integer counts with a common
  denominator, then `P(total ≥ defender's current HP)`. The result is `KOChance(method="exact")`.
- Stated assumptions: no healing, residual damage, hazards or switching between hits. Those are
  Monte Carlo territory and stay out of 03a.
- Verified by brute-force enumeration in tests, because the oracle's own KO text ignores crits and
  accuracy and so cannot be the reference here.

### Hidden Power

- `hidden_power(gen, ivs)` implements the Gens 3–4 type and power (30–70) formula.
- The engine derives type and power when the attacker's set lists all six IVs; otherwise a typed
  entry (`hiddenpowerfire`) is used at 70; the untyped `hiddenpower` placeholder is unsupported.

### Verification oracle

- `scripts/build_calc_golden.mjs` with `@smogon/calc` pinned at 0.12.0 (MIT, build-time only, added
  to `scripts/package.json`) writes `tests/fixtures/calc_golden_gen4.json`.
- Each case stores the full input (species, level, nature, IVs, EVs, stages, status, current HP,
  move, weather, screens), the oracle's computed stats, and its 16 non-crit and 16 crit rolls.
- **Case selection, proposed:** about 40 hand-picked cases, each tagged with the mechanic it
  targets, plus about 200 seeded-random matchups restricted to 03a mechanics.
  - Hand-picked coverage: neutral, STAB, 2×, 4×, ½, ¼, immunity, dual types in both orders, crit
    with boosted and dropped stages, burn, each screen, screens with crit, sun, rain, sandstorm
    with a Rock-type, Explosion, level 1 and level 100 extremes, minimum-damage 1, every fixed-damage
    kind, each variable-power move in 03a, Hidden Power.
  - The random sweep is what catches rounding-order bugs; the seed is fixed so the file is stable.
- The Python engine must reproduce every stat and every roll list exactly. 03b adds its own tagged
  cases to the same file.

### Latency

- Target: a 4-move × 6-matchup report (24 evaluations with KO odds) in under 5 ms.
- A timing test asserts the median over repeated runs, with headroom so it is not flaky on a busy
  machine. Computed stats are cached per set.

### Out of scope for Task 03a/03b

Gens 1–3 (Task 03c), doubles, multi-turn effects, Monte Carlo, and building a `MathReport` straight
from a `GameState` for the opponent (needs Task 04's set hypotheses).

### Decisions asked before any code

| # | Question | Recommendation |
|---|----------|----------------|
| Q1 | Type chart and natures: export from `@pkmn/dex`, or type the tables by hand in Python? | Export (one source of truth, no transcription errors) |
| Q2 | Accept the `Move` changes: `fixed_damage`, `ignores_type_chart`, `crit_ratio`, `multihit`, and base power 0 for fixed-damage moves in Gen 1? | Accept |
| Q3 | Accept `MoveEvaluation.unsupported_reason` so unsupported moves are reported, not guessed? | Accept |
| Q4 | Golden cases: 40 hand-picked + 200 seeded-random (about 150 KB committed), or hand-picked only? | Both |
| Q5 | Move the **immunity abilities** (Levitate, Flash Fire, Water Absorb, Volt Absorb, Motor Drive, Dry Skin, Wonder Guard) from 03b into 03a? Without them 03a reports Earthquake damage on Gengar, Rotom and Bronzong. | Move into 03a |
| Q6 | Add `@smogon/calc` 0.12.0 as a build-time dependency in `scripts/`? | Yes |
| Q7 | Update the git remote to the new URL `…/Poketrix.git` reported by GitHub? | Yes |

### Decisions (2026-10-10, user)

Q1 export from `@pkmn/dex` · Q2 accepted · Q3 accepted · Q4 both groups · Q5 immunity abilities moved
into 03a · Q6 `@smogon/calc` 0.12.0 added · Q7 git remote updated to `…/Poketrix.git`.

## Task 03a — Gen 4 math core (approved 2026-10-10)

Branch `task/03-math-gen4`, merged into `main` as `cp-03a`.
Tests: **231 passing** (68 before + 163 new); `ruff check src tests` is clean.

### Result against the oracle

- `tests/fixtures/calc_golden_gen4.json` holds **310 cases** from `@smogon/calc` 0.12.0: 90
  hand-picked (one per mechanic, tagged) and 220 seeded-random.
- The engine reproduces the oracle's stats and all 16 normal and 16 critical rolls **exactly** in
  every case it evaluates: all 90 hand-picked and 215 of the 220 random ones.
- The other 5 random cases use moves 03a declines to evaluate (Fling ×2, Trump Card, Present,
  Punishment); the test skips them and requires at least 180 compared.
- No formula change was needed after the first run. The only failure was a fixture mistake (a
  hand-picked case used Pure Power, a 03b ability), fixed in the generator.
- `@pkmn/dex` and `@smogon/calc` agree on every Gen 4 species' stats and types and on every
  damaging move's power, type and category. Four cosmetic formes (Burmy-Sandy, Burmy-Trash,
  Shellos-East, Gastrodon-East) are missing from the oracle and are left out of the random sweep.
- Latency: the 4-move × 6-target report takes about **3.4 ms** (median) on this machine against the
  5 ms target; the timing test asserts the median of 25 runs.

### What was built

- **Schemas:** `Move.fixed_damage`, `Move.ignores_type_chart`, `Move.crit_ratio`, `Move.multihit`,
  `FixedDamage` enum, `Nature`, `MoveEvaluation.unsupported_reason`.
- **Snapshot** (`scripts/build_dex.mjs`, rebuilt): the new move fields, `gen{N}/typechart.json`,
  `natures.json`. Fixed-damage moves have base power 0 in every generation.
- **Dex:** `load_type_chart(gen)` and `load_natures()`, validated at load.
- **`src/poketrix/calc/`:**
  - `typechart.py` — `effectiveness(gen, move_type, defender_types)`.
  - `stats.py` — Gens 3–4 stat formula (cached), stat stages, current HP.
  - `hidden_power.py` — type and power from IVs.
  - `engine.py` — `DamageEngine` protocol, `DamageResult`, `UnsupportedMoveError`, registry.
  - `gen4.py` — the Gen 4 engine.
  - `ko.py` — exact 1- to 4-hit KO odds.
  - `report.py` — `evaluate_move(...)` → `MoveEvaluation`; `build_report(...)` →
    `SubsystemResult[MathReport]` (returns an ERROR result instead of raising).
- **Oracle generator:** `scripts/build_calc_golden.mjs` (`npm run build-calc-golden`).
- **Tests:** `tests/test_calc_golden.py`, `tests/test_calc.py`, additions to `test_dex.py` and
  `test_schemas.py`, shared builders in `tests/calc_helpers.py`.

### What the Gen 4 engine covers in 03a

- The core formula, STAB, both type factors in canonical order, critical hits, burn, Reflect and
  Light Screen (Brick Break ignores them), sun and rain, Solar Beam in bad weather, sandstorm's
  Special Defense boost for Rock-types, Explosion and Self-Destruct.
- Immunities: type immunity, Levitate, Flash Fire, Water Absorb, Dry Skin (Water), Volt Absorb,
  Motor Drive, Wonder Guard (with its typeless and Fire Fang exceptions).
- Added beyond the Q5 list because they decide immunity or weather and cost a line each: Mold
  Breaker, Scrappy, Foresight, Gravity, Air Lock, Cloud Nine, and Sturdy against OHKO moves.
- Fixed damage: flat amounts, level-based, Super Fang, Endeavor, OHKO moves (accuracy from the
  level difference). Type immunity is checked first.
- Variable power: Return, Frustration, Eruption, Water Spout, Flail, Reversal, Brine, Facade,
  Wake-Up Slap, Crush Grip, Wring Out, Weather Ball.
- Typeless damage: Struggle, Future Sight, Doom Desire.
- Hidden Power: derived from the set's IVs when any are listed; otherwise the typed entry at 70.

### Reported as unsupported, never guessed

`MoveEvaluation.unsupported_reason` is set and no numbers are given for: multi-hit moves; Counter,
Mirror Coat, Metal Burst and Bide; Psywave; untyped Hidden Power without IVs; Payback, Gyro Ball,
Punishment and Beat Up; and variable-power moves without a rule yet (Low Kick, Grass Knot, Fling,
Natural Gift, Magnitude, Present, Trump Card, Spit Up).

### Known limits of 03a (by design, until 03b)

- **Held items and all other abilities are ignored.** A Choice Band, Life Orb, Technician or Thick
  Fat holder gets the unmodified number, not an "unsupported" marker.
- Exact KO odds assume nothing else changes HP between hits.
- When only the displayed HP fraction is known, current HP is that fraction of max HP, rounded.
- Future Sight and Doom Desire are given the normal crit chance; Gravity's accuracy boost is not
  applied.
- Gens 1–3 have no engine yet (`engine_for(3)` raises `NotImplementedError`).

### Review questions (all answered 2026-10-10: the user chose every recommendation)

| # | Question | Recommendation |
|---|----------|----------------|
| R1 | **Gyro Ball and Punishment:** from the oracle's source, Gyro Ball is `floor(25 × target Speed / user Speed)` and Punishment counts only the five battle stats. As I recall the Showdown simulator, it adds 1 to Gyro Ball and also counts accuracy and evasion boosts for Punishment; I have not verified that against its source. Which do we follow? | Verify against the simulator source in 03b, follow the simulator, and exclude the disputed part from the golden comparison |
| R2 | **Psywave** has 11 possible outcomes, but `DamageRange` accepts only 1 or 16 rolls. Relax the validator, or leave Psywave unsupported? | Leave unsupported; it is not a competitive move |
| R3 | The fixture is 266 KB, above the 150 KB estimate. Keep all 310 cases? | Keep |
| R4 | Should 03b mark a move as unsupported when the attacker or defender has an item or ability the engine does not model yet, instead of returning the unmodified number? | Yes, once 03b defines the list of modelled items and abilities |

Carried into 03b: R1 (verify Gyro Ball and Punishment against the simulator source and follow the
simulator) and R4 (unsupported marker for unmodelled items and abilities). R2: Psywave stays
unsupported. R3: all 310 cases are kept.

## Task 03b design proposal — Gen 4 items, abilities and remaining moves (2026-10-10, approved)

Branch `task/03b-items-abilities`.

### R1 verified against the simulator source

Read from `smogon/pokemon-showdown` (`data/moves.ts`, `sim/pokemon.ts`; `data/mods/gen4/moves.ts`
has no override for either move):

- **Gyro Ball:** `floor(25 × target Speed / user Speed) + 1`, capped at 150, and 1 if the division is
  not finite. The oracle omits the `+ 1`.
- **Punishment:** `60 + 20 × positiveBoosts()`, capped at 200, where `positiveBoosts()` sums every
  positive stage including accuracy and evasion. The oracle counts only the five battle stats.

03b follows the simulator for both. Golden cases for them are restricted to inputs where the two
agree (Punishment without accuracy/evasion boosts); the differing part gets hand-written tests that
cite the simulator rule.

### Scope

"What matters for damage" is defined as every ability and item whose effect the oracle's Gen 4
damage code applies. 03b models all of them except what is listed under *stays unsupported*.

**Abilities**

| Stage of the formula | Abilities |
|---|---|
| Move type / immunity | Normalize, Soundproof, Klutz (ignores its own item) |
| Base power | Technician, Thick Fat, Heatproof, Dry Skin (Fire ×1.25), Blaze / Overgrow / Torrent / Swarm, Iron Fist, Reckless |
| Attack | Huge Power, Pure Power, Guts, Hustle, Solar Power, Flower Gift, Slow Start, Simple, Unaware |
| Defense | Marvel Scale, Flower Gift, Simple, Unaware |
| Final damage | Flash Fire boost, Adaptability, Sniper, Filter, Solid Rock, Tinted Lens |
| Critical hits | Battle Armor, Shell Armor (no crits), Super Luck (crit stage) |
| Multi-hit | Skill Link |

Intimidate and Download need no code: their stat changes arrive as stages in the battle log.
Slow Start and an activated Flash Fire are read from `BattlePokemon.volatiles` (`slowstart`,
`flashfire`), which the Task 05 parser will set.

**Items**

- Choice Band, Choice Specs, Life Orb, Expert Belt, Muscle Band, Wise Glasses.
- Type-boosting items and plates (×1.2), Adamant / Lustrous / Griseous Orb.
- Species items: Light Ball, Thick Club, Soul Dew, Deep Sea Tooth, Deep Sea Scale, Metal Powder.
- Damage-halving berries.
- Iron Ball (grounding), Scope Lens and Razor Claw (crit stage).
- Speed for turn-order moves: Choice Scarf, Iron Ball, Quick Powder, the EV-training items.
- A consumed or removed item (`item_consumed`) counts as no item.

**Moves**

- Multi-hit moves: per-hit rolls plus the Gen 4 hit-count odds (2–5 hits: 3/8, 3/8, 1/8, 1/8;
  Skill Link always 5), folded into the exact KO odds.
- Weight-based: Low Kick, Grass Knot.
- Speed-based: Gyro Ball (simulator rule), Payback.
- Punishment (simulator rule), Natural Gift, Fling, Judgment with a plate.

**Stays unsupported** (reported with a reason): Magnitude and Psywave (their outcomes do not fit the
16-roll `DamageRange`), Present, Trump Card, Spit Up, Beat Up, Triple Kick, the reactive moves, and
anything involving Rivalry (needs gender, which no schema carries).

### R4 — unsupported marker for unmodelled items and abilities

The engine keeps one explicit set of damage-relevant abilities and items it does **not** model
(after 03b: Rivalry, and nothing else known). If either Pokémon has one and the move is damaging,
the result is `unsupported_reason`, not a number. Everything outside that set is either modelled or
has no damage effect in the oracle's source.

### Data and schema changes needed

| Change | Why | Source |
|---|---|---|
| `Species.weight_kg` | Low Kick, Grass Knot | `@pkmn/dex` |
| `Move.flags` limited to `punch`, `sound`, `recoil` | Iron Fist, Soundproof, Reckless | `@pkmn/dex` (`flags`, `recoil`, `hasCrashDamage`) |
| New `Item` schema and `data/dex/gen{2..4}/items.json`: id, name, `boosts_type`, `resists_type`, `fling_power`, `natural_gift` | every item rule above; also lets `Dex.item()` reject unknown item ids | `@pkmn/dex` for existence, Fling and Natural Gift; the oracle's own tables (`@smogon/calc/dist/items`, read at build time) for type boosts and resist berries, which are code, not data, in Showdown |
| `DamageRange.hit_distribution: dict[int, float] \| None` | multi-hit moves; `rolls` stays per hit, and `min_pct` / `max_pct` account for the hit count | — |

### Code structure

- `gen4.py` keeps the formula skeleton and the order of stages.
- `gen4_modifiers.py` holds the ability and item rules as ordered steps per stage (base power,
  attack, defense, final damage, per-roll), so adding a rule never edits the formula. The order
  inside each stage, including which rules are mutually exclusive, is copied from the oracle.
- `speed.py` computes effective Speed (stages, paralysis, items, weather abilities, Tailwind) and
  turn order under Trick Room.
- `ko.py` gains the hit-count distribution; crit chance comes from the crit stage (move, ability,
  item).

### Verification

- Generator: about 80 new hand-picked cases, one per ability, item and move rule above, tagged.
- The random sweep is regenerated with items and all modelled abilities switched on (300 cases,
  new fixed seed); it replaces the 03a sweep, whose mechanics it contains.
- Every roll must still match exactly, except the two simulator-rule moves as described.
- Crit stages, hit-count odds and accuracy are outside the oracle (it takes "crit: yes/no" as an
  input), so they are tested by brute-force enumeration and against the simulator's Gen 4 rules.
- Latency target unchanged: 4 moves × 6 targets under 5 ms.

### Decisions asked before any code

| # | Question | Recommendation |
|---|----------|----------------|
| B1 | Add the `Item` schema and per-generation `items.json`, with type boosts and resist berries read from the oracle's tables at build time? | Yes |
| B2 | Add `Species.weight_kg` to the schema and snapshot? | Yes |
| B3 | Add `Move.flags` limited to `punch`, `sound`, `recoil`? | Yes |
| B4 | Add `DamageRange.hit_distribution` for multi-hit moves? | Yes |
| B5 | **Payback** doubles if the user moves after the target, which depends on the opponent's choice (priority move, switch). Evaluate it by Speed comparison as the oracle does, or leave it unsupported? | Speed comparison, with Trick Room respected |
| B6 | **Metronome (item)** needs the count of consecutive uses, which no schema carries. Assume the first use (no boost), as the oracle does by default, or mark unsupported? | Assume first use |
| B7 | Confirm the *stays unsupported* list above, including Rivalry. | Confirm |
| B8 | **Accuracy modifiers** (Gravity, Compound Eyes, Hustle, No Guard, Sand Veil, Snow Cloak, Tangled Feet, Wide Lens, Zoom Lens, BrightPowder, Lax Incense) change KO odds but are not in the oracle. Include them in 03b, verified against the simulator source with hand-written tests, or defer? | Include |
| B9 | Fixture: replace the 03a sweep with the new 300-case sweep (about 470 cases and 450 KB in total), or keep both (about 690 cases, 650 KB)? | Replace |

### Decisions (2026-10-10, user)

B1–B9: the user chose every recommendation (item schema and data, species weight, move flags,
hit distribution, Payback by Speed, Metronome as first use, the unsupported list, accuracy
modifiers included, 03a sweep replaced).

## Task 03b — Gen 4 items, abilities and remaining moves (approved 2026-10-10)

Branch `task/03b-items-abilities`, merged into `main` as `cp-03b`.
Tests: **352 passing** (231 before + 121 new); `ruff check src tests` is clean.

### Result against the oracle

- The fixture now holds **486 cases**: 186 hand-picked (90 from 03a + 96 new, one per item,
  ability and move rule) and a new 300-case random sweep with items and abilities switched on
  (250 of its compared cases have a held item on at least one side). It is 452 KB.
- Every case the engine evaluates matches the oracle's stats and all normal and critical rolls
  **exactly**: 185 hand-picked and 295 of the 300 random ones.
- The one hand-picked case not compared is the multi-hit move into a resist berry, where the test
  asserts the engine reports *unsupported* (the oracle confirms the later hits differ).
- The 5 random cases not compared: Triple Kick ×2 and Present (unsupported moves), and 2 with a
  Rivalry attacker (unsupported ability).
- No formula change was needed after the first run against the new fixture; the only failures were
  three fixture mistakes (abilities a species cannot have in Gen 4, one move name), which the
  generator and the dex rejected.
- Latency: the 4-move × 6-target report takes about **3.0 ms** (median, quiet machine) against the
  5 ms target. The timing test now takes the best of three 25-run medians, because one run failed
  at 6 ms while the machine was busy.

### What was built

- **Schemas:** `Species.weight_kg`, `Move.flags` (`MoveFlag`: punch, sound, recoil), `Item`,
  `DamageRange.hit_distribution` (and `min_pct` / `max_pct` now cover a full use of the move).
- **Snapshot:** weights, move flags, and `data/dex/gen{2..4}/items.json` (62 / 106 / 210 items).
  Type boosts and resist berries are read from the oracle's tables at build time; Fling and
  Natural Gift values come from `@pkmn/dex`. `data/dex` is 497 KB.
- **Dex:** `Dex.item(id)` and `Dex.all_items()`.
- **`src/poketrix/calc/gen4/`** replaces the single `gen4.py`:

  | Module | Responsibility |
  |---|---|
  | `engine.py` | The formula's skeleton, stage order, fixed damage |
  | `context.py` | Resolves abilities, items, HP and weather once (Klutz, Mold Breaker, Air Lock) |
  | `movetype.py` | Effective move type, type factors, abilities that negate a move |
  | `power.py` | Per-move power rules and base-power modifiers |
  | `modifiers.py` | Attack, Defense and damage modifiers |
  | `speed.py` | Effective Speed and turn order |
  | `chance.py` | Accuracy, crit stage, multi-hit counts |

- **`ko.py`:** multi-hit moves, and a faster algorithm (KO odds for the benchmark went from about
  1.75 ms to 1.0 ms).
- **Tests:** the golden comparison, plus brute-force and simulator-rule tests in `test_calc.py`.

### Everything from the proposal's scope is in

All abilities, items and moves listed in the proposal are modelled. Two rules follow the Showdown
simulator instead of the oracle, as decided in R1: Gyro Ball (`+ 1`) and Punishment (accuracy and
evasion boosts count). Their differing part is covered by hand-written tests.

Accuracy and crit-stage rules were read from the simulator's Gen 4 source
(`data/mods/gen4/scripts.ts`, `abilities.ts`, `items.ts`, `sim/battle-actions.ts`): the stage
tables, Compound Eyes 1.3, Hustle 0.8, Sand Veil / Snow Cloak 0.8, Tangled Feet 0.5, Wide Lens 1.1,
Zoom Lens 1.2, BrightPowder / Lax Incense 0.9, Gravity 5/3, No Guard, Simple, Unaware, Foresight;
crit stages from the move, Super Luck, Scope Lens, Razor Claw, Focus Energy, Lucky Punch and Stick;
2–5 hits at 3/8, 3/8, 1/8, 1/8.

### Changes to what 03a delivered

- **Accuracy and evasion stages are now applied separately**, as the simulator does. 03a combined
  them into one stage, which gave a different answer when both were non-zero (+1 accuracy into +2
  evasion on an 80% move is 64%, not 60%).
- **The engine contract is one method.** `DamageEngine.evaluate(...)` returns an `Outcome` (hit
  chance, damage or `None`, unsupported reason, defender HP) instead of separate `damage` and
  `hit_chance` calls. It halves the per-move setup work and keeps the unsupported reason inside
  the engine. `evaluate_move` and `build_report` are unchanged for callers, apart from a new
  optional `attacker_conditions` argument (Tailwind).
- **A package instead of two files.** The proposal named `gen4_modifiers.py` and `speed.py`; the
  rules are split by formula stage across the seven modules above.

### Still unsupported (reported with a reason)

Magnitude, Psywave, Present, Trump Card, Spit Up, Beat Up, Triple Kick, Counter, Mirror Coat, Metal
Burst, Bide, untyped Hidden Power without IVs, any damaging move from a Rivalry user, and a
multi-hit move into a resist berry that would activate.

### Known limits

- **Not verified by the oracle:** accuracy, crit stages and hit counts (it takes them as inputs).
  They are tested against the simulator's rules and by brute-force enumeration.
- Accuracy is a real number; the simulator's integer rounding can differ by up to one percentage
  point.
- Payback and Zoom Lens use a Speed comparison; the opponent's priority moves and switches are not
  known at this point.
- Forecast and Download are not modelled: Castform must be given as its current forme, and
  Download's boost is expected as a stat stage, both of which the Task 05 parser will supply.
- Slow Start, an activated Flash Fire, Unburden, Charge and Focus Energy are read from
  `BattlePokemon.volatiles`.
- Fling's power comes from `@pkmn/dex`; the oracle returns 0 for seven items it has no entry for
  (Big Root, BrightPowder, Griseous Orb, Metronome, Sticky Barb, Grip Claw, Shell Bell), so Fling
  and Gyro Ball are left out of the random sweep and covered by hand-picked cases.
- Future Sight and Doom Desire are given the normal crit chance.
- Exact KO odds still assume nothing else changes HP between hits.

Next is Task 03c (Gens 3 → 2 → 1 engines), which starts with a design proposal.

## Task 03c — Gens 3, 2 and 1 damage engines (approved 2026-10-10)

Branch `task/03c-gens-3-2-1`, merged into `main` as `cp-03c`.
Tests: **678 passing** at review (352 before + 326 new), 679 after Order 3; `ruff check src tests` is clean.

### Decisions (2026-10-10, user)

| # | Question | Decision |
|---|----------|----------|
| C1 | Checkpointing | All three generations on one branch, one review |
| C2 | Reference where the oracle and the simulator differ | Oracle for damage rolls (every case machine-verified); simulator for accuracy, crit rate and hit counts; every difference found is listed below |
| C3 | Gen 1 multi-hit moves (every hit repeats the first hit's roll and crit) | Model it now |
| C4 | Fixture size | About 60 hand-picked + 200 random per generation |

### Result against the oracle

| Gen | Hand-picked | Random compared | Random skipped (reported unsupported) | 4-move × 6-target report |
|-----|-------------|-----------------|---------------------------------------|--------------------------|
| 1 | 65 of 65 | 200 of 200 | — | about 4.2 ms |
| 2 | 80 of 80 | 194 of 200 | Magnitude ×3, Present ×2, Triple Kick | about 3.9 ms |
| 3 | 118 of 118 | 196 of 200 | Triple Kick ×2, Present, Spit Up | about 2.8 ms |
| 4 | 185 of 186 | 293 of 300 | Magnitude ×2, Trump Card ×2, Triple Kick, Spit Up, one Rivalry attacker (listed below) | about 3.0 ms |

- Every compared case matches the oracle's stats and all normal and critical rolls **exactly**
  (39 rolls per list in Gens 1–2, 16 in Gens 3–4).
- All three new engines matched on their first full run; no formula change was needed.
- The fixtures total 1.4 MB (Gen 1: 284 KB, Gen 2: 300 KB, Gen 3: 312 KB, Gen 4: 476 KB).

**Fixture log** (R2). All four were generated with `@smogon/calc` 0.12.0 and `@pkmn/dex` 0.10.11.
A regeneration that changes any of these numbers is a deliberate change and must be logged here.

| Gen | Sweep seed | Hand-picked | Sweep | Sweep cases compared |
|-----|------------|-------------|-------|----------------------|
| 1 | 20261015 | 65 | 200 | 200 |
| 2 | 20261014 | 80 | 200 | 194 |
| 3 | 20261013 | 118 | 200 | 196 |
| 4 | 20261011 | 186 | 300 | 293 |

The Gen 4 sweep went from 295 compared (03b) to 293 because the generator was generalised to
all generations, which changed its random sequence; the seed is the same. Its 7 skipped cases:

| Case | Attacker | Move | Why it is reported unsupported |
|------|----------|------|--------------------------------|
| sweep-035 | Wormadam | Magnitude | seven possible powers do not fit one roll list |
| sweep-045 | Buizel | Magnitude | same |
| sweep-073 | Carnivine | Trump Card | power depends on remaining PP, which is not tracked |
| sweep-074 | Aggron | Trump Card | same |
| sweep-110 | Suicune | Triple Kick | each hit has its own power and accuracy check |
| sweep-263 | Granbull | Spit Up | power depends on the Stockpile count, which is not tracked |
| sweep-289 | Nidoran-M (Rivalry) | Energy Ball | Rivalry depends on gender, which is not tracked |

### What was built

- **Shared code moved out of the Gen 4 package**, so no generation imports another:
  - `calc/base.py` — `BaseEngine.evaluate` (context, hit chance, damage or unsupported reason).
  - `calc/context.py` — `Side` / `Context`, now for every generation.
  - `calc/power_rules.py` — reusable per-move power rules and the unsupported-move list.
  - `calc/modern/` — what Gens 3 and 4 share: `engine.py` (immunities, fixed damage, multi-hit),
    `movetype.py`, `speed.py`, `chance.py`.
- **`calc/gen3/`** — `engine.py` and `modifiers.py`: the Gen 3 formula (items and abilities change
  the stat itself, type items give 10%, Sea Incense 5%, category follows the type).
- **`calc/classic/`** — `engine.py` with `ClassicEngine` and its `Gen1Engine` / `Gen2Engine`
  subclasses, and `chance.py`. One formula; each subclass fills in what differs (critical hits,
  type-factor rounding, the random roll, items and weather from Gen 2).
- **Stats:** the Gens 1–2 formula (DVs, Stat Exp, derived HP DV) and their stat-stage table.
- **Hidden Power** from DVs (Gen 2).
- **KO odds:** `hits_share_roll` for Gen 1 multi-hit moves; `DamageRange.hits_share_roll` carries it.
- **Generator:** `scripts/build_calc_golden.mjs` now builds all four fixtures; the hand-picked
  cases live in `scripts/golden_cases/gen{1..4}.mjs`. It rejects a case whose species, ability,
  item or move does not exist in that generation.
- **Tests:** `test_calc_golden.py` covers all generations; `test_calc_gens123.py` holds the
  stat, Hidden Power, accuracy, crit-rate and shared-roll tests.

### Accuracy, crit rate and hit counts (from the simulator's per-generation source)

- **Gen 1:** accuracy on a 0–255 scale against a random byte, so a 100% move hits 255/256; the
  stage table is the stat-stage table. Crit rate from base Speed (Tauros 55/256); high-crit moves
  ×8, capped at 255/256; Focus Energy lowers it (the Gen 1 bug). OHKO moves fail against a faster
  target. Multi-hit: 2–5 hits at 3/8, 3/8, 1/8, 1/8, all repeating one roll.
- **Gen 2:** same 0–255 scale, but 255 always hits; its own stage tables; BrightPowder subtracts
  20; OHKO accuracy grows by 2 per level of difference. Crit stages 17, 32, 64, 85, 128 out of
  256; Scope Lens and Focus Energy add one; Stick and Lucky Punch set stage 3; Flail and Reversal
  never crit.
- **Gen 3:** the Gen 4 rules, except Lax Incense is ×0.95.

### Differences between the oracle and the simulator that I found

Per decision C2 the damage rolls follow the oracle in each of these:

1. **Gen 1 high-crit moves.** The oracle always treats Slash, Razor Leaf, Crabhammer and Karate
   Chop as critical hits. We return both the normal and the critical rolls and use the
   simulator's crit rate, so only the critical rolls are compared for these four moves.
2. **Gen 1 Explosion and Self-Destruct.** The oracle halves Defense before it checks whether a
   stat exceeds 255 (which divides both stats by 4); the simulator checks first and halves
   after. When Attack is at most 255 and Defense is between 256 and 511, only the simulator
   divides by 4, and the coarser rounding changes the result by a few HP: Gengar's Explosion
   into Golem is 77–91 with the oracle's order and would top out at 93 with the simulator's.
   (Corrected during Order 3: I first described this as "a point of Defense".) Pinned by
   `test_gen1_explosion_halves_defense_before_the_byte_check`.
3. **Gen 1 one-hit KO moves.** The simulator deals 65535 damage; we report the target's
   remaining HP. The oracle does not model them.
4. **Gen 2 Present.** The oracle runs its glitched formula with a fixed power of 40; we report
   it as unsupported (its power is random).

I compared only the parts of the simulator I read for the odds rules; this is not a full audit.

### Known limits

- Unsupported in every generation it exists in: Counter, Mirror Coat, Bide, Psywave, Magnitude,
  Present, Triple Kick, Beat Up, Spit Up, untyped Hidden Power without IVs/DVs.
- Gen 1 Speed for the OHKO check is stages plus paralysis; the Gen 1 stat-reapplication glitches
  are not modelled.
- Gen 1 partial-trapping moves (Wrap, Bind) are evaluated as single hits.
- Multi-turn power growth (Rollout, Fury Cutter) and Pursuit's doubling on a switch are not
  modelled: the listed base power is used.
- Gen 1 multi-hit KO odds use a longer roll list (up to 312 values), so those evaluations are
  slower than the rest.
- I planned three commits, one per generation; the shared test file and generator serve all
  generations, so it is one commit.

On approval: merge `--no-ff`, tag `cp-03c`, log it, push. That completes Phase 3 (Math layer).
Next is Task 04, the Bayesian set uncloaker, starting with a design proposal.

## Review of Task 03c (2026-10-10, reviewer: Claude in claude.ai, on behalf of the user)

Verdict: **APPROVED.** This completes Phase 3.

I checked the following on the user's machine:

- **Tests:** 678 of 678 pass on `task/03c-gens-3-2-1` (commit `df05740`).
- **Gen 4, 185 of 186 hand-picked:** expected. The one case not compared is the multi-hit move into a resist berry,
  which is tested to report *unsupported*, carried over from 03b.
- **Gen 1–2 odds rules:** checked against known game behaviour.
  - Gen 1: crit rate is base Speed ÷ 2 out of 256 (Tauros gets 55/256), high-crit moves get ×8 capped at 255, and the Focus Energy bug lowers the rate.
  - Gen 1 multi-hit is 2/3/4/5 hits with chances 3/8, 3/8, 1/8, 1/8, and every hit reuses one roll.
  - Gen 2 crit stages are 17, 32, 64, 85 and 128 out of 256.
  - All correct.
- **Divergence calls (1–4):** I agree with each. Using the simulator's crit rate for Gen 1 high-crit moves
  is more correct than the oracle's "always crit". Reporting Present as unsupported, and OHKO
  damage as the target's remaining HP, are both right for KO-probability purposes.
- **Shared-module refactor:** Gen 4 behaviour is unchanged (its oracle cases still match), and no generation
  imports another. Good structure.

Findings. None block the merge, but R1 must be done before the merge commit (Order 3).

- **R1: line endings.** Git on Windows checks files out with CRLF, so any non-Windows git (CI, the
  reviewer's Linux shell, a future Mac) sees every file as modified: 26 files showed as changed with zero
  real changes. Add a `.gitattributes` with `* text=auto eol=lf` and mark `*.json`, `*.py`, `*.md`
  and `*.mjs` as `text eol=lf`. Then run `git add --renormalize .` and commit it on the task branch as
  "chore: normalise line endings". Check that `pytest` is still green afterwards, because the fixtures are JSON.
- **R2: fixture log.** The Gen 4 random sweep went from 295 of 300 (03b) to 293 of 300 cases compared, because the
  generator code changed. Per-generation seeds already keep the generations independent, which is good. In the 03c result
  table, replace "as in 03b" with the 7 skipped Gen 4 cases by name, and record each fixture's
  seed and the `@smogon/calc` version in the tracker. A future regeneration then shows up as a deliberate change.
- **R3: Gen 1 Explosion.** Add one test that pins our behaviour (the oracle's order) and names the
  one-point simulator difference in its docstring, so nobody later "fixes" it by accident.
- **R4: latency.** Gens 1–2 are near the 5 ms report target, and Gen 1 multi-hit KO odds are slower (up to
  312 values). No action now. Phase 6 will measure the end-to-end turn against the 500 ms budget, and
  if Gen 1 is the bottleneck we'll profile it then. This follows the "upgrade only when proven" rule.
- **R5: callers of unsupported moves.** Later phases must treat the unsupported list (Counter, Bide, Present, …) as a
  `SubsystemResult` with status `fallback` or `error`, and never as zero damage. Carry this forward to Phase 6.

## [Completed] Orders for Claude Code, batch 2 (do these in order, stopping where marked)

### ✅ DONE — Order 3: close Task 03c and Phase 3 (no stop needed, the user has approved) _(→ cp-03c)_
1. On `task/03c-gens-3-2-1`, do R1 (line endings) as its own commit, then R2 and R3. Run `pytest` and
   `ruff check src tests`; both must be green.
2. Run `git switch main`, then `git merge --no-ff task/03c-gens-3-2-1`, then
   `git tag -a cp-03c -m "Math layer: Gens 3, 2, 1 damage engines"`.
3. Add cp-03c to `docs/CHECKPOINTS.md` with the test count, mark Phase 3 as done in this table and in
   `README.md`, and push with `git push origin main --tags`.
4. Report the push result in one line under this order.

**Result (2026-10-10): done.** R1–R3 applied (`.gitattributes` and renormalisation as their own
commit; fixture log added; Gen 1 Explosion pinned by a test), 679 tests green and ruff clean on
`main`, pushed: `a5980b2..dcee5f6 main -> main`, new tag `cp-03c`. R4 and R5 are recorded in
`CLAUDE.md` under "Carried forward".

### ✅ DONE — Order 4: Task 04 design proposal, the Bayesian set uncloaker. **STOP after the proposal.** _(→ proposal approved, built as cp-04)_
Branch: `task/04-bayes-uncloaker`. Write the proposal as a new section in this tracker. This is the first
layer that is genuinely machine learning, so the proposal must show how we will **measure** it, not
just how we will build it.

The proposal must cover:

1. **Where the prior comes from.** First read Showdown's Random Battle data for Gens 1–4 and report the
   actual file layout. The current data may be *movepools plus generation rules* (roles, essential
   and exclusive moves) rather than a list of finished sets with frequencies. If so, the true prior is
   whatever the team generator produces. Compare these options and recommend one:
   - **(a) Sample the official generator.** Run Showdown's own random-team generator (the
     `pokemon-showdown` npm package, Node at build time only, the same pattern as `build_dex`) for N teams per
     gen, and count the distinct (moves, item, ability) sets per species and level. This is the
     empirical prior. Propose N, and show how much counts move between two seeds, to justify N.
   - **(b) Parse the movepools** and derive set probabilities analytically. Exact if it works, but
     it means re-implementing generator logic, so it's fragile.
   - **(c) Smogon usage statistics** for the Gen 1–4 Random Battle formats, if they exist for these formats.
   Record the source version and pin it, as was done for `@pkmn/dex` and `@smogon/calc`.
2. **What a hypothesis is.** Is it a distinct (frozenset of moves, item, ability) tuple, and what about
   the spread? In Random Battles the level, EVs and IVs are mostly fixed per species. Say so if the data confirms it.
3. **Evidence and updates.** For 04a: revealed moves, item (including consumed or knocked off, such as Leftovers recovery
   or a berry eaten) and ability. Bayes over the hypothesis table gives `SetPosterior`, with `move_probability`,
   item and ability marginals. Also cover negative evidence: a Pokémon that has used 4 distinct moves has
   revealed its whole moveset.
   For 04b, a proposal only, built later: **damage-based evidence.** The likelihood of an observed damage %
   under each hypothesis's stats and item, using our calc engines, for example telling Choice Band from Life Orb, or
   detecting Life Orb recoil. Recommend whether 04b is part of Phase 4 or deferred.
4. **Zero-probability safety.** Sampling can miss rare sets, so real evidence may contradict every
   hypothesis. Propose the fallback, for example backing off to per-move marginals with smoothing, returned as
   `SubsystemResult(status="fallback")`, never an exception. `SetPosterior`'s schema validator must
   still hold.
5. **Evaluation, the ML part.** Build a held-out test set by sampling *fresh* generator teams with a
   different seed. Reveal k = 0..4 random moves (plus the item and ability where shown), and report:
   - the share of cases where the true set keeps a non-zero posterior (target 100% on the main path);
   - log-loss and Brier score of the posterior over sets, and of P(move) for the unrevealed moves;
   - calibration: a reliability table of predicted P(move) against observed frequency, in 10 bins;
   - top-1 and top-3 set accuracy as k grows.
   Propose the targets, and commit the evaluation script so the numbers can be reproduced.
6. **Consumer contract.** Show how the Math layer uses the posterior: a *threat report*, meaning the
   expected and worst-case damage to our active Pokémon weighted by P(move), with no new calc code. Propose the function
   signature only.
7. **Size and speed.** The prior tables are committed per gen; give their size estimate and a cap of about 5 MB in
   total. One posterior update must take under 5 ms per Pokémon (the ML budget is under 150 ms per turn).
8. **Decisions to ask the user,** with a recommendation for each: the prior source, N, hypothesis
   granularity, whether 04b is in Phase 4, and the evaluation targets.

Then **stop** and ask the user to approve or adjust the proposal before writing any code.

## Task 04 design proposal — Bayesian set uncloaker (2026-10-10, approved)

Branch `task/04-bayes-uncloaker`. The numbers below come from
throwaway scripts run in a temp folder outside the repo, against `pokemon-showdown` 0.11.11.

### 1. Where the prior comes from

**What Showdown's Random Battle data actually is** (`data/random-battles/gen{N}/` in
`smogon/pokemon-showdown`): movepools plus generator code, not finished sets with frequencies.

| Gen | Data file | Layout | Generator |
|-----|-----------|--------|-----------|
| 1 | `data.json` (25 KB, 146 species) | per species: `level`, `moves`, and optional `essentialMoves`, `exclusiveMoves`, `comboMoves` | `teams.ts` (13 KB) |
| 2 | `sets.json` (51 KB, 141 species, 267 role sets) | per species: `level`, `sets[]` of `role` + `movepool` (+ `preferredTypes`) | `teams.ts` (19 KB) |
| 3 | `sets.json` (103 KB, 220 species, 394 role sets) | as Gen 2, plus `abilities` per role set | `teams.ts` (30 KB) |
| 4 | `sets.json` (121 KB, 295 species, 464 role sets) | as Gen 3 | `teams.ts` (29 KB) |

- A role's movepool has up to 10 moves; the generator picks 4 by rules (role, STAB, team needs).
- **Items are not in the data at all.** They are chosen by code (`getPriorityItem`, `getItem`)
  from the moves, ability, role and whether the Pokémon leads.
- Choices also depend on the rest of the team (screens, Rapid Spin, Spikes already present).

So the true prior is whatever the generator produces. The three options:

| Option | Verdict |
|--------|---------|
| **(a) Sample the official generator** | **Recommended.** `Teams.generate('gen4randombattle', {seed})` from the `pokemon-showdown` npm package works for all four formats and takes under 1 ms per team. |
| (b) Parse the movepools analytically | Not recommended: it means re-implementing about 90 KB of generator rules, including the item code and the team-level dependencies. |
| (c) Smogon usage statistics | **Not available.** The monthly stats listings (checked 2025-12 and 2026-08) contain `gen4ou` but no Random Battle format. |

**How many teams (N).** Two independent seeds were compared at three sizes. "Mass on unseen sets"
is the share of the second sample's Pokémon whose exact set never appeared in the first; "seed
distance" is the mean total-variation distance between the two samples' per-species set
frequencies.

| Teams per seed | Measure | Gen 1 | Gen 2 | Gen 3 | Gen 4 |
|----------------|---------|-------|-------|-------|-------|
| 2,000 | mass on unseen sets | 0.07% | 0.03% | 1.33% | 1.64% |
| 2,000 | seed distance | 0.075 | 0.078 | 0.195 | 0.169 |
| 20,000 | mass on unseen sets | under 0.005% | under 0.005% | 0.01% | 0.01% |
| 20,000 | seed distance | 0.020 | 0.020 | 0.067 | 0.048 |
| 100,000 | mass on unseen sets | under 0.005% | under 0.005% | under 0.005% | under 0.005% |
| 100,000 | seed distance | 0.008 | 0.010 | 0.032 | 0.022 |

At 100,000 teams: 431 / 584 / 1,346 / 1,746 distinct sets (Gens 1–4), a median of 3–5 and a
maximum of 42 per species, and the rarest species still has 66 samples (Gen 3). Generating them
takes about 1 to 1.5 minutes per generation. **Recommendation: N = 100,000 teams per generation.**

**Pinning.** `pokemon-showdown` 0.11.11 (MIT), the seeds and N are written to a manifest next to
the tables, as for `@pkmn/dex` and `@smogon/calc`.

**Two things you should know about this dependency:**

- It is heavy: 183 packages, 181 MB installed. It is build-time only and git-ignored, and I would
  put it in its own `scripts/randbats/package.json` so the usual `npm install` for the dex and
  the fixtures does not pull it in.
- The live Showdown server changes its Random Battle sets more often than the npm package is
  published. A pinned prior can be behind the ladder; section 4 and the shift test in section 5
  are how we stay safe when it is.

### 2. What a hypothesis is

- One hypothesis = (species, the set of moves, item, ability).
- **Level is fixed per species**: in 100,000 teams no species appeared at two levels in any
  generation.
- **The spread is not one per species** (31 / 63 / 134 / 89 species show more than one), because
  the generator derives it from the moves: Hidden Power's IVs, Attack 0 with no physical move,
  Speed 0 for Gyro Ball or Trick Room. Otherwise it is 85 EVs in every stat and no nature (Gens
  3–4), or maximum DVs and Stat Exp (Gens 1–2). I expect the spread to be a function of the set;
  the build script asserts that and fails if a set shows two spreads.
- So each table row carries: moves, item, ability, count, and the level and spread needed to
  build a `PokemonSet` for the calculator.
- Generator formes the dex does not have (cosmetic ones such as the Unown letters) are folded
  into their base species; real formes (Rotom-Wash, Deoxys-Speed) keep their own rows.

### 3. Evidence and updates (04a)

- **Input:** a new `SetEvidence` schema — `revealed_moves`, `item`, `ruled_out_items`, `ability`,
  `ruled_out_abilities`. The Task 05 parser fills it; until then tests build it directly.
- **Update:** posterior ∝ prior count × likelihood. The likelihood is 0 for a set that lacks a
  revealed move, has a different item or ability than the revealed one, or has a ruled-out item
  or ability; otherwise `1 / C(moves in set, moves revealed)`, which treats every move of a set as
  equally likely to have been shown. That factor only matters between sets of different sizes
  (Ditto has one move).
- **Negative evidence:**
  - four distinct moves revealed: the moveset is known, and only item and ability remain open;
  - a consumed or removed item is still evidence of what the item was;
  - `ruled_out_items` lets the parser say "took damage and did not recover at end of turn, so not
    Leftovers", "attacked with no recoil, so not Life Orb", "used two different moves in a row,
    so not a Choice item". The uncloaker only applies these; detecting them is Task 05's job.
- **Output:** the existing `SetPosterior` (hypotheses with prior and posterior, and
  `move_probability`), plus item and ability marginals computed the same way. No change to
  `SetPosterior` is needed; `PokemonSet`s for the calculator come from a lookup by `set_id`.
- **Not evidence:** a move called by Sleep Talk, Metronome or Copycat is not one of the user's
  four slots unless the log shows it as such. That distinction is also Task 05's.

**04b, damage-based evidence** (the likelihood of an observed damage percentage under each
hypothesis, using the calc engines, for example Choice Band against Life Orb). Recommendation:
**defer it until after Task 05.** It needs observed damage from real logs, and its value depends
on how precise the log's HP percentages are, which we cannot measure before the parser exists.
`SetEvidence` is designed so a per-hypothesis likelihood can be added later without changing 04a.

### 4. Zero-probability safety

At N = 100,000 the sampling itself almost never misses a set, so evidence that contradicts every
hypothesis will mostly mean the prior is stale or the log is unusual. The uncloaker backs off in
tiers and never raises:

| Tier | When | What is returned | Status |
|------|------|------------------|--------|
| 1 | some hypothesis fits all the evidence | the Bayes posterior | `ok` |
| 2 | none fits, but some fit the revealed moves | the posterior from the moves alone; the conflicting item or ability evidence is kept in the output and each hypothesis takes the revealed item or ability | `fallback` |
| 3 | no known set contains the revealed moves | one synthesised hypothesis per plausible completion: the revealed moves plus the species' most likely other moves, weighted by smoothed per-move frequencies | `fallback` |
| 4 | the species is not in the table and nothing is revealed | no payload, with an error message | `error` |

In every tier with a payload the `SetPosterior` validator holds: probabilities sum to 1, and no
hypothesis that contradicts the evidence has a posterior above 0.

### 5. Evaluation

**Method.** Build the prior from one seed; evaluate on fresh teams from a different seed. For each
held-out Pokémon and each k = 0…4, reveal k of its moves at random and compare the posterior with
the truth. The script is committed (`scripts/randbats/evaluate.*` driving the Python uncloaker),
and its output table is pasted into this tracker so the numbers can be reproduced.

**What a throwaway version already measures** (prior from 20,000 teams, 5,000 held-out teams,
moves only, no item or ability revealed):

| Gen | k | True set kept | Top-1 | Top-3 | Set log-loss | Move Brier | Move calibration error |
|-----|---|---------------|-------|-------|--------------|------------|------------------------|
| 4 | 0 | 99.98% | 0.383 | 0.769 | 1.408 | 0.152 | 0.003 |
| 4 | 1 | 99.98% | 0.503 | 0.858 | 1.037 | 0.141 | 0.003 |
| 4 | 2 | 99.98% | 0.629 | 0.929 | 0.703 | 0.135 | 0.006 |
| 4 | 3 | 99.98% | 0.780 | 0.980 | 0.383 | 0.133 | 0.010 |
| 4 | 4 | 99.98% | 0.970 | 0.999 | 0.047 | — | — |
| 3 | 0 | 99.99% | 0.371 | 0.767 | 1.401 | 0.158 | 0.004 |
| 3 | 2 | 99.997% | 0.656 | 0.949 | 0.629 | 0.132 | 0.006 |
| 3 | 4 | 99.997% | 0.986 | 1.000 | 0.022 | — | — |
| 2 | 0 | 100% | 0.447 | 0.842 | 1.134 | 0.151 | 0.003 |
| 2 | 2 | 100% | 0.721 | 0.975 | 0.471 | 0.117 | 0.008 |
| 2 | 4 | 100% | 0.993 | 1.000 | 0.010 | — | — |
| 1 | 0 | 100% | 0.576 | 0.922 | 0.865 | 0.098 | 0.002 |
| 1 | 2 | 100% | 0.769 | 0.973 | 0.446 | 0.097 | 0.003 |
| 1 | 4 | 100% | 1.000 | 1.000 | 0.000 | — | — |

Reading it: with nothing revealed the single most likely set is right 37–58% of the time and the
true set is in the top three 77–92% of the time; two revealed moves raise top-3 to 93–97%. With
all four moves known, what remains is the item (and ability), which is why Gen 4 stops at 97%.

**Proposed targets** (tested, so a regression fails the suite):

| Metric | Target |
|--------|--------|
| True set keeps a non-zero posterior on tier 1 | at least 99.9% in every generation and every k |
| The uncloaker never raises | 100% of held-out cases return a `SubsystemResult` |
| Move calibration error (10 bins) | at most 0.02 at every k |
| Set log-loss | lower than "uniform over the sets that fit the evidence" at every k |
| Top-1 and top-3 accuracy | reported per k; must not fall more than 0.02 below the table above |

**What this evaluation can and cannot show.** Held-out teams come from the same generator as the
prior, so this measures whether the implementation is correct and well calibrated; a Bayes
posterior over the true prior is the best possible answer here. It does **not** measure how the
model does when the ladder's sets have moved on. For that I propose one more, deliberately unfair
test: delete a random 5% of sets from the prior, evaluate on the full held-out data, and report
how often tiers 2 and 3 fire and how good their move probabilities are. Real-ladder accuracy can
only be measured once Task 05 can read real battle logs.

### 6. Consumer contract

The Math layer uses the posterior through one new function, with no new calculator code:

```python
def threat_report(
    ours: BattlePokemon, theirs: BattlePokemon, posterior: SetPosterior, prior: SetPrior,
    field: FieldState, our_conditions: SideConditions, their_conditions: SideConditions,
) -> SubsystemResult[ThreatReport]
```

For each move the opponent may carry it gives P(move), the damage to our active Pokémon averaged
over the hypotheses that carry it, and the worst case among them. It builds each hypothesis's
`PokemonSet` from the prior table and calls the existing `evaluate_move`. Signature only for now;
`ThreatReport` would be a small new output schema. A move the calculator reports as unsupported
stays unsupported in the report (review finding R5).

### 7. Size and speed

- **Tables:** `data/randbats/gen{N}/sets.json`, one row per set. The set keys alone total about
  280 KB for all four generations; with counts, levels and spreads I estimate **under 1 MB in
  total**, well inside the 5 MB cap.
- **Speed:** one update filters at most 42 hypotheses for a species. The target of 5 ms per
  Pokémon should be met with a wide margin; a timing test will assert it.

### 8. Decisions asked before any code

| # | Question | Recommendation |
|---|----------|----------------|
| D1 | Prior source: sample the official generator (a), parse movepools (b), or usage stats (c, not available)? | (a) |
| D2 | Accept `pokemon-showdown` 0.11.11 as a build-time dependency (181 MB installed, git-ignored), in its own `scripts/randbats/` folder? | Yes |
| D3 | N = 100,000 teams per generation for the prior (about 1.5 minutes each to build)? | Yes |
| D4 | Hypothesis = (species, moves, item, ability), with level and spread stored per set? | Yes |
| D5 | Include `ruled_out_items` / `ruled_out_abilities` in 04a's evidence, to be filled by the Task 05 parser? | Yes |
| D6 | 04b (damage-based evidence): part of Phase 4, or deferred until after Task 05? | Defer |
| D7 | Accept the evaluation targets in section 5, including the 5%-deleted shift test? | Yes |
| D8 | Add the `threat_report` function and `ThreatReport` schema in Task 04, or leave the consumer side to Phase 6? | Add it in Task 04, as a second step after the uncloaker is reviewed |
| D9 | Package name: `poketrix.uncloak`? | Yes |

### Decisions (2026-10-10, user)

D1–D9: the user chose every recommendation. The prior is sampled from the official generator
(`pokemon-showdown` 0.11.11, in its own `scripts/randbats/` folder), 100,000 teams per
generation; a hypothesis is (species, moves, item, ability) with level and spread per set;
ruled-out items and abilities are part of the evidence; damage-based evidence (04b) is deferred
until after Task 05; the evaluation targets and the 5%-removed test are accepted; the threat
report is a second step after this one is reviewed; the package is `poketrix.uncloak`.

## Task 04, step 1 — the set prior and the uncloaker (approved 2026-10-11)

Branch `task/04-bayes-uncloaker`. Not merged, not tagged, not pushed.
Tests: **716 passing** (679 before + 37 new); `ruff check src tests` is clean. The suite now takes
about 10 seconds instead of 3, because the evaluation runs inside it.

### What was built

- **Generator sampling:** `scripts/randbats/build_randbats.mjs` (`npm run build-randbats`, about
  6 minutes for all four generations). It writes two tables per generation in one format:
  the prior and a held-out sample from a different seed.

  | Gen | Prior sets (100,000 teams, seed 20261101) | Held-out sets (20,000 teams, seed 20261102) |
  |-----|--------------------------------------------|----------------------------------------------|
  | 1 | 431 | 431 |
  | 2 | 559 | 559 |
  | 3 | 1,184 | 1,184 |
  | 4 | 1,740 | 1,723 |

  The prior tables (`data/randbats/gen{N}/sets.json`) total 663 KB; the held-out tables
  (`tests/fixtures/randbats_holdout_gen{N}.json`) 657 KB.
- **Confirmed by the build:** level is fixed per species, and the spread is a function of the
  set (the script fails if one set shows two spreads; it did not).
- **Schemas:** `SetEvidence`, `PriorSet`; `SetPosterior` gained `item_probability` and
  `ability_probability` (methods only).
- **`poketrix.uncloak`:**
  - `prior.py` — `SetPrior` and `load_prior(gen)`. Every row is checked against the dex and
    becomes a full `PokemonSet`, so a hypothesis goes straight into the damage calculator.
  - `uncloaker.py` — `Uncloaker.uncloak(species, evidence) -> SubsystemResult[SetPosterior]`,
    with the four tiers from the proposal. It never raises.
  - `evaluation.py` — the committed evaluation. `python -m poketrix.uncloak.evaluation` prints
    the tables below.

### Evaluation results

Scored exactly, by enumerating every way to reveal k of a held-out set's moves, weighted by how
often the generator produced the set. k = number of moves revealed.

**Full prior, moves revealed**

| Gen | k | True set kept | Top-1 | Top-3 | Set log-loss | Uniform log-loss | Move Brier | Move calibration error | Tier 2 | Tier 3 |
|-----|---|---------------|-------|-------|--------------|------------------|------------|------------------------|--------|--------|
| 1 | 0 | 100.0000% | 0.577 | 0.921 | 0.863 | 0.916 | 0.0974 | 0.0012 | 0.00% | 0.00% |
| 1 | 1 | 100.0000% | 0.672 | 0.950 | 0.651 | 0.691 | 0.0890 | 0.0012 | 0.00% | 0.00% |
| 1 | 2 | 100.0000% | 0.772 | 0.973 | 0.441 | 0.469 | 0.0760 | 0.0010 | 0.00% | 0.00% |
| 1 | 3 | 100.0000% | 0.882 | 0.990 | 0.222 | 0.237 | 0.0530 | 0.0008 | 0.00% | 0.00% |
| 1 | 4 | 100.0000% | 1.000 | 1.000 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.00% | 0.00% |
| 2 | 0 | 100.0000% | 0.450 | 0.847 | 1.131 | 1.187 | 0.1502 | 0.0012 | 0.00% | 0.00% |
| 2 | 1 | 100.0000% | 0.590 | 0.933 | 0.759 | 0.792 | 0.1069 | 0.0014 | 0.00% | 0.00% |
| 2 | 2 | 100.0000% | 0.725 | 0.977 | 0.469 | 0.486 | 0.0713 | 0.0014 | 0.00% | 0.00% |
| 2 | 3 | 100.0000% | 0.861 | 0.996 | 0.221 | 0.228 | 0.0387 | 0.0010 | 0.00% | 0.00% |
| 2 | 4 | 100.0000% | 0.993 | 1.000 | 0.010 | 0.010 | 0.0000 | 0.0000 | 0.00% | 0.00% |
| 3 | 0 | 100.0000% | 0.378 | 0.779 | 1.371 | 1.446 | 0.1581 | 0.0012 | 0.00% | 0.00% |
| 3 | 1 | 100.0000% | 0.520 | 0.883 | 0.960 | 1.009 | 0.1182 | 0.0013 | 0.00% | 0.00% |
| 3 | 2 | 100.0000% | 0.662 | 0.949 | 0.618 | 0.650 | 0.0838 | 0.0011 | 0.00% | 0.00% |
| 3 | 3 | 100.0000% | 0.817 | 0.987 | 0.308 | 0.327 | 0.0479 | 0.0008 | 0.00% | 0.00% |
| 3 | 4 | 100.0000% | 0.984 | 1.000 | 0.023 | 0.033 | 0.0000 | 0.0000 | 0.00% | 0.00% |
| 4 | 0 | 99.9975% | 0.378 | 0.764 | 1.412 | 1.517 | 0.1534 | 0.0012 | 0.00% | 0.00% |
| 4 | 1 | 99.9975% | 0.498 | 0.859 | 1.035 | 1.107 | 0.1203 | 0.0015 | 0.00% | 0.00% |
| 4 | 2 | 99.9975% | 0.630 | 0.932 | 0.698 | 0.746 | 0.0923 | 0.0017 | 0.00% | 0.00% |
| 4 | 3 | 99.9975% | 0.783 | 0.982 | 0.373 | 0.403 | 0.0582 | 0.0012 | 0.00% | 0.00% |
| 4 | 4 | 99.9975% | 0.970 | 1.000 | 0.046 | 0.058 | 0.0000 | 0.0000 | 0.00% | 0.00% |

**Full prior, moves plus item and ability revealed**

| Gen | k | True set kept | Top-1 | Top-3 | Set log-loss | Uniform log-loss | Move Brier | Move calibration error | Tier 2 | Tier 3 |
|-----|---|---------------|-------|-------|--------------|------------------|------------|------------------------|--------|--------|
| 1 | 0 | 100.0000% | 0.577 | 0.921 | 0.863 | 0.916 | 0.0974 | 0.0012 | 0.00% | 0.00% |
| 1 | 1 | 100.0000% | 0.672 | 0.950 | 0.651 | 0.691 | 0.0890 | 0.0012 | 0.00% | 0.00% |
| 1 | 2 | 100.0000% | 0.772 | 0.973 | 0.441 | 0.469 | 0.0760 | 0.0010 | 0.00% | 0.00% |
| 1 | 3 | 100.0000% | 0.882 | 0.990 | 0.222 | 0.237 | 0.0530 | 0.0008 | 0.00% | 0.00% |
| 1 | 4 | 100.0000% | 1.000 | 1.000 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.00% | 0.00% |
| 2 | 0 | 100.0000% | 0.471 | 0.861 | 1.060 | 1.104 | 0.1423 | 0.0029 | 0.00% | 0.00% |
| 2 | 1 | 100.0000% | 0.609 | 0.942 | 0.711 | 0.738 | 0.1017 | 0.0013 | 0.00% | 0.00% |
| 2 | 2 | 100.0000% | 0.740 | 0.981 | 0.436 | 0.450 | 0.0681 | 0.0009 | 0.00% | 0.00% |
| 2 | 3 | 100.0000% | 0.872 | 0.997 | 0.201 | 0.207 | 0.0372 | 0.0010 | 0.00% | 0.00% |
| 2 | 4 | 100.0000% | 1.000 | 1.000 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.00% | 0.00% |
| 3 | 0 | 100.0000% | 0.478 | 0.849 | 1.076 | 1.121 | 0.1253 | 0.0009 | 0.00% | 0.00% |
| 3 | 1 | 100.0000% | 0.600 | 0.922 | 0.754 | 0.781 | 0.0959 | 0.0011 | 0.00% | 0.00% |
| 3 | 2 | 100.0000% | 0.723 | 0.968 | 0.481 | 0.496 | 0.0687 | 0.0011 | 0.00% | 0.00% |
| 3 | 3 | 100.0000% | 0.857 | 0.994 | 0.231 | 0.237 | 0.0394 | 0.0009 | 0.00% | 0.00% |
| 3 | 4 | 100.0000% | 1.000 | 1.000 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.00% | 0.00% |
| 4 | 0 | 99.9975% | 0.507 | 0.858 | 1.009 | 1.074 | 0.1121 | 0.0016 | 0.00% | 0.00% |
| 4 | 1 | 99.9975% | 0.609 | 0.920 | 0.738 | 0.781 | 0.0903 | 0.0016 | 0.00% | 0.00% |
| 4 | 2 | 99.9975% | 0.720 | 0.966 | 0.491 | 0.519 | 0.0707 | 0.0015 | 0.00% | 0.00% |
| 4 | 3 | 99.9975% | 0.848 | 0.994 | 0.248 | 0.261 | 0.0451 | 0.0011 | 0.00% | 0.00% |
| 4 | 4 | 99.9975% | 1.000 | 1.000 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.00% | 0.00% |

**Prior with a random 5% of sets removed, moves revealed**

| Gen | k | True set kept | Top-1 | Top-3 | Set log-loss | Uniform log-loss | Move Brier | Move calibration error | Tier 2 | Tier 3 |
|-----|---|---------------|-------|-------|--------------|------------------|------------|------------------------|--------|--------|
| 1 | 0 | 94.4867% | 0.553 | 0.873 | 0.841 | 0.892 | 0.1146 | 0.0254 | 0.00% | 0.00% |
| 1 | 1 | 94.4867% | 0.640 | 0.900 | 0.635 | 0.674 | 0.1073 | 0.0245 | 0.00% | 2.16% |
| 1 | 2 | 94.4349% | 0.732 | 0.921 | 0.430 | 0.458 | 0.0947 | 0.0217 | 0.00% | 3.32% |
| 1 | 3 | 94.4349% | 0.834 | 0.936 | 0.217 | 0.232 | 0.0694 | 0.0166 | 0.00% | 4.47% |
| 1 | 4 | 94.4349% | 0.944 | 0.944 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.00% | 5.57% |
| 2 | 0 | 95.0000% | 0.442 | 0.813 | 1.096 | 1.153 | 0.1602 | 0.0157 | 0.00% | 0.00% |
| 2 | 1 | 95.0000% | 0.574 | 0.892 | 0.731 | 0.765 | 0.1191 | 0.0176 | 0.00% | 1.42% |
| 2 | 2 | 94.9244% | 0.698 | 0.930 | 0.449 | 0.466 | 0.0841 | 0.0164 | 0.00% | 2.50% |
| 2 | 3 | 94.9244% | 0.823 | 0.946 | 0.210 | 0.217 | 0.0496 | 0.0139 | 0.00% | 3.68% |
| 2 | 4 | 94.9244% | 0.943 | 0.949 | 0.009 | 0.009 | 0.0000 | 0.0000 | 0.00% | 4.97% |
| 3 | 0 | 95.4433% | 0.373 | 0.755 | 1.328 | 1.399 | 0.1635 | 0.0112 | 0.00% | 0.00% |
| 3 | 1 | 95.4433% | 0.509 | 0.849 | 0.926 | 0.973 | 0.1257 | 0.0125 | 0.00% | 0.64% |
| 3 | 2 | 95.4045% | 0.642 | 0.909 | 0.595 | 0.625 | 0.0932 | 0.0123 | 0.00% | 1.63% |
| 3 | 3 | 95.4045% | 0.786 | 0.943 | 0.296 | 0.314 | 0.0572 | 0.0095 | 0.00% | 2.94% |
| 3 | 4 | 95.4045% | 0.939 | 0.954 | 0.023 | 0.033 | 0.0000 | 0.0000 | 0.00% | 4.50% |
| 4 | 0 | 95.0333% | 0.370 | 0.742 | 1.371 | 1.475 | 0.1617 | 0.0159 | 0.00% | 0.00% |
| 4 | 1 | 95.0333% | 0.484 | 0.826 | 1.003 | 1.075 | 0.1309 | 0.0162 | 0.00% | 1.08% |
| 4 | 2 | 95.0148% | 0.607 | 0.891 | 0.674 | 0.723 | 0.1046 | 0.0157 | 0.00% | 1.90% |
| 4 | 3 | 95.0148% | 0.750 | 0.935 | 0.360 | 0.389 | 0.0697 | 0.0145 | 0.00% | 3.04% |
| 4 | 4 | 95.0148% | 0.923 | 0.950 | 0.045 | 0.057 | 0.0000 | 0.0000 | 0.00% | 4.76% |

**Prior with a random 5% of sets removed, moves plus item and ability revealed**

| Gen | k | True set kept | Top-1 | Top-3 | Set log-loss | Uniform log-loss | Move Brier | Move calibration error | Tier 2 | Tier 3 |
|-----|---|---------------|-------|-------|--------------|------------------|------------|------------------------|--------|--------|
| 1 | 0 | 94.4867% | 0.553 | 0.873 | 0.841 | 0.892 | 0.1146 | 0.0254 | 0.00% | 0.00% |
| 1 | 1 | 94.4867% | 0.640 | 0.900 | 0.635 | 0.674 | 0.1073 | 0.0245 | 0.00% | 2.16% |
| 1 | 2 | 94.4349% | 0.732 | 0.921 | 0.430 | 0.458 | 0.0947 | 0.0217 | 0.00% | 3.32% |
| 1 | 3 | 94.4349% | 0.834 | 0.936 | 0.217 | 0.232 | 0.0694 | 0.0166 | 0.00% | 4.47% |
| 1 | 4 | 94.4349% | 0.944 | 0.944 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.00% | 5.57% |
| 2 | 0 | 95.0000% | 0.461 | 0.827 | 1.027 | 1.072 | 0.1534 | 0.0206 | 0.19% | 0.00% |
| 2 | 1 | 95.0000% | 0.591 | 0.900 | 0.684 | 0.711 | 0.1146 | 0.0196 | 0.12% | 1.42% |
| 2 | 2 | 94.9244% | 0.713 | 0.934 | 0.417 | 0.432 | 0.0814 | 0.0167 | 0.08% | 2.50% |
| 2 | 3 | 94.9244% | 0.834 | 0.947 | 0.191 | 0.197 | 0.0483 | 0.0139 | 0.08% | 3.68% |
| 2 | 4 | 94.9244% | 0.949 | 0.949 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.10% | 4.97% |
| 3 | 0 | 95.4433% | 0.471 | 0.821 | 1.037 | 1.081 | 0.1321 | 0.0131 | 0.70% | 0.00% |
| 3 | 1 | 95.4433% | 0.587 | 0.885 | 0.724 | 0.750 | 0.1048 | 0.0136 | 0.59% | 0.64% |
| 3 | 2 | 95.4045% | 0.701 | 0.926 | 0.460 | 0.474 | 0.0793 | 0.0126 | 0.49% | 1.63% |
| 3 | 3 | 95.4045% | 0.824 | 0.949 | 0.220 | 0.226 | 0.0493 | 0.0098 | 0.31% | 2.94% |
| 3 | 4 | 95.4045% | 0.954 | 0.954 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.09% | 4.50% |
| 4 | 0 | 95.0333% | 0.495 | 0.826 | 0.977 | 1.043 | 0.1230 | 0.0181 | 0.74% | 0.00% |
| 4 | 1 | 95.0333% | 0.589 | 0.881 | 0.713 | 0.757 | 0.1030 | 0.0172 | 0.73% | 1.08% |
| 4 | 2 | 95.0148% | 0.692 | 0.920 | 0.474 | 0.502 | 0.0847 | 0.0166 | 0.69% | 1.90% |
| 4 | 3 | 95.0148% | 0.810 | 0.945 | 0.239 | 0.252 | 0.0579 | 0.0150 | 0.55% | 3.04% |
| 4 | 4 | 95.0148% | 0.950 | 0.950 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0.23% | 4.76% |

### Against the agreed targets

| Target | Result |
|--------|--------|
| True set keeps a non-zero posterior on tier 1 in at least 99.9% of cases | **Met:** 100% in Gens 1–3, 99.9975% in Gen 4 |
| The uncloaker never raises | **Met:** every held-out case returns a result, also with 5% of the sets removed |
| Move calibration error at most 0.02 at every k | **Met:** at most 0.0017 with moves only, 0.0029 with item and ability |
| Top-1 and top-3 accuracy within 0.02 of the proposal's table | **Met** |
| Set log-loss lower than "uniform over the sets that fit" at every k | **Met for k = 0…3. Not met at k = 4 in Gen 2:** 0.01025 against 0.01024 |
| One update under 5 ms | **Met** for the species with the most sets (42) |

**The one miss.** With all four moves known, the only thing left to guess is a near-even choice
between items, and the prior's frequencies and the held-out sample's differ by sampling noise.
The posterior is then no better than a coin flip, by 0.00001 nats in Gen 2. The test asserts
"strictly lower for k ≤ 3, within 0.001 at k = 4". If you would rather keep the original target,
the alternatives are a larger prior sample or dropping the k = 4 comparison.

### What the out-of-date-prior test shows

With a random 5% of sets removed:

- About 5% of held-out Pokémon run a set the prior no longer knows. While nothing has been
  revealed that contradicts a known set, the uncloaker gives the missing set probability 0;
  tier 1 does not reserve any probability for "a set I have not seen".
- As moves are revealed the fallbacks take over: tier 3 handles up to 5.6% of cases at k = 4,
  and tier 2 up to 0.74% when the item and ability are shown.
- Move calibration error rises from under 0.003 to at most 0.025.

So a stale prior degrades gradually and never crashes, but it is over-confident until the
evidence contradicts it. Whether tier 1 should hold back a small share for unseen sets is a
question for your reviewer; I have not added it because it was not in the proposal.

### Known limits

- The evaluation uses teams from the same generator as the prior. It shows the implementation
  is correct and calibrated; it cannot show accuracy on the live ladder.
- The evidence is taken as given. Deciding what counts as a revealed move (not one called by
  Sleep Talk or Metronome) and detecting ruled-out items is the Task 05 parser's job.
- In tier 2 a hypothesis keeps the `set_id` of the set it came from, with the observed item or
  ability in place of that set's own. The threat report (step 2) must build its `PokemonSet`
  from the hypothesis fields plus the source set's spread.
- Tier 3 fills open move slots from the species' six most frequent moves, treating them as
  independent. It is a rough completion, not a model of the generator.

### Next (after review)

Step 2: `threat_report` and the `ThreatReport` schema (decision D8), then the Phase 4 merge and
`cp-04`.

## Task 04, step 2 — the threat report (approved 2026-10-11, with additions R6–R7)

Branch `task/04-bayes-uncloaker`. Not merged, not tagged, not pushed.
Tests: **725 passing** (716 before + 9 new); `ruff check src tests` is clean.

Step 1 was approved by the user on 2026-10-11, including the changed log-loss test (strictly
lower than uniform for k ≤ 3, within 0.001 at k = 4). Holding back probability for unseen sets
on the main path was not requested and is not added.

### What was built

- **Schemas:** `MoveThreat` and `ThreatReport`.
- **`poketrix.uncloak.threat`:**

  ```python
  threat_report(ours, theirs, posterior, prior, field, our_conditions, their_conditions)
      -> SubsystemResult[ThreatReport]
  ```

  `ours` is our Pokémon with its known set; `theirs` is the opponent as the battle shows it
  (species, level, HP bar). For every hypothesis with a non-zero posterior it builds the
  opponent's full set and calls the existing `evaluate_move`. No calculator code was added.

### What a `MoveThreat` says

For each move the opponent may carry, most likely first:

| Field | Meaning |
|-------|---------|
| `probability` | P(the opponent carries the move), the posterior's `move_probability` |
| `expected_pct` | mean damage of one normal hit, as a percentage of our maximum HP, averaged over the hypotheses that carry the move |
| `worst_case_pct` | the highest roll among those hypotheses **without** a critical hit |
| `worst_crit_pct` | the highest roll **with** a critical hit: the figure a UI should call "worst case" (R6) |
| `ko_probability` | chance that one use knocks our Pokémon out from its current HP |
| `unsupported_reason` | set when the calculator cannot evaluate the move |

And on the `ThreatReport` itself (R7):

| Field | Meaning |
|-------|---------|
| `p_ko_best_move` | "if they attack, can they knock us out this turn?": for each possible set, the KO chance of its best move, weighted by the set's posterior |
| `ko_lower_bound` | `True` when a possible move could not be evaluated and counted as 0, so the real chance is at least `p_ko_best_move` |

Where a critical hit is impossible or changes nothing (fixed damage, Battle Armor),
`worst_crit_pct` equals `worst_case_pct`. The optional `p_has_ohko_move` was left out, as the
review allowed.

- The damage figures are conditional on the opponent having the move and on a normal hit:
  `expected_pct` and `worst_case_pct` leave out misses and critical hits; `ko_probability`
  includes both, because it comes from the calculator's exact KO odds.
- A multi-hit move's figures cover a whole use.
- **Review finding R5 holds here:** a move the calculator cannot evaluate (Counter, …) is listed
  with its probability and a reason, and with no damage numbers. A status move has neither
  numbers nor a reason.

### How hypotheses become sets

- Moves, item and ability are the hypothesis's own, so a tier 2 fallback's observed item is used.
- The spread comes from the table set the hypothesis names; for a tier 3 fallback (a completed
  moveset) from the species' most common set.
- The level is the one the battle shows.
- A move's damage depends on the attacker's item, ability and spread, not on its other moves, so
  each such combination is evaluated once and shared between hypotheses.

### Speed

For the species with the most hypotheses (42) the report takes about 5 ms (median) on this
machine; the test allows 50 ms. Uncloaking plus the threat report for one opposing Pokémon is
well inside the 150 ms ML budget per turn.

### Known limits

- The report covers one opposing Pokémon against one of ours. Building it for a whole turn from
  a `GameState` (active Pokémon, side conditions, evidence from the log) is Phase 6's job, with
  the Phase 5 parser supplying the evidence.
- `expected_pct` is not weighted by accuracy or crit chance; use `ko_probability` when those
  matter.
- If one hypothesis's version of a move is unsupported, the move is reported as unsupported.

On approval: merge `--no-ff`, tag `cp-04`, log it, push. That completes Phase 4. Next is Phase 5,
the Showdown battle-log parser, starting with a design proposal.

## Review of Task 04, step 2 (2026-10-11, reviewer: Claude in claude.ai, on behalf of the user)

Verdict: **APPROVED**, subject to two small additions (R6, R7) before the merge. They are pre-approved:
if their acceptance checks pass, merge without another stop.

I checked the following on the user's machine:

- **Tests:** 725 of 725 pass on `481e479`, the working tree is clean, and R1 worked (`.gitattributes` is in, with no
  line-ending noise).
- **Reuse:** the threat report adds no calculator code and shares one evaluation per (item, ability, spread)
  combination. That's the right design.
- **R5:** honoured. Unsupported moves carry a reason and no numbers.
- **Tier 2 and 3 fallbacks** produce valid reports.

### Findings

- **R6: "worst case" leaves out critical hits. Fix before the merge.** `worst_case_pct` is the highest
  *normal* roll. In the overlay, "worst case 48%" would be false when a crit does 72%, and crits are
  common in Gen 1 (fast Pokémon land them about 20% of the time). Keep the field, but add
  `worst_crit_pct` (the highest critical roll among the hypotheses that carry the move) and have the
  docstring say plainly which one the UI should call "worst case". Leave `expected_pct` as it is (a normal hit,
  conditional on the move existing). It is honestly labelled, and `ko_probability` covers accuracy and crits.
- **R7: one headline number per matchup. Add before the merge.** The per-move marginals can't
  answer the question the overlay actually needs: *"if they attack, can they KO me this turn?"* That's because
  moves are correlated inside a set. Add to `ThreatReport`:
  - `p_ko_best_move = Σ_h P(h) · max_{m ∈ h} KO(m, h)`, the posterior-weighted chance that the
    opponent's best move for each set KOs us. Unsupported and status moves count as 0 inside the max, and
    the report notes `ko_lower_bound=True` whenever an unsupported move had a non-zero
    probability, so the number is a lower bound and never overstated.
  - `p_has_ohko_move = Σ_h P(h) · [max_{m ∈ h} KO(m, h) ≥ 0.5]` is optional. Skip it if it adds noise.
  These are pure aggregation over results the report already computes. They add no calculator calls.
- **R8: holding back probability for unseen sets. Decision: not now, measure first.** The prior is pinned to
  `pokemon-showdown` 0.11.11, while the live ladder's Random Battle sets change between Showdown releases,
  so staleness is the real risk. But the 5%-removed test shows the fallbacks catch it without crashing, and
  any hold-back size picked today would be a guess. Phase 5 will measure, on real replays, how often a revealed
  move contradicts every tier-1 set (the *staleness rate*), and that number decides whether to add
  a hold-back, a rebuild cadence, or both. This follows the "upgrade only when proven" rule.
- **R9: test speed. Optional.** The suite went from 3 s to 14 s because the evaluation runs inside it. If it
  keeps growing, add a `slow` pytest marker for the evaluation tests (`pytest -m "not slow"` for quick
  runs), with the full suite still required before every merge. Don't do this now.

## [Completed] Orders for Claude Code, batch 3 (do these in order, stopping where marked)

### ✅ DONE — Order 5: R6 + R7, then close Phase 4 (pre-approved, no stop if the checks pass) _(→ cp-04)_
1. On `task/04-bayes-uncloaker`, add `worst_crit_pct` to `MoveThreat` (R6), and add `p_ko_best_move` and
   `ko_lower_bound` to `ThreatReport` (R7). Update the docstrings and this tracker's "What a `MoveThreat` says"
   table.
2. Acceptance checks. Each needs a test:
   - `worst_crit_pct >= worst_case_pct` wherever both are set.
   - A hand-built 2-set posterior where only set A carries an OHKO move gives `p_ko_best_move` equal to
     P(A) times that move's KO probability, worked out by hand in the test.
   - With an unsupported move at non-zero probability, `ko_lower_bound` is `True`.
   - `p_ko_best_move` lies between the largest single `ko_probability × probability` and the sum over all
     moves of `ko_probability × probability`. That's a sanity bound; check it on 50 random held-out cases.
   - Full `pytest` green, `ruff` clean, and the report still under 50 ms in the timing test.
3. If all checks pass: run `git switch main`, then `git merge --no-ff task/04-bayes-uncloaker`, then
   `git tag -a cp-04 -m "Bayesian set uncloaker + threat report"`. Log it in `docs/CHECKPOINTS.md`, mark Phase 4
   as done here and in `README.md`, and run `git push origin main --tags`. Report the result in one line under this order.
   If any check fails, **stop** and report instead of merging.

**Result (2026-10-11): all checks passed.** R6 and R7 added with six new tests (731 in total):
`worst_crit_pct >= worst_case_pct` everywhere; the hand-worked case gives 0.75 × 0.30 = 0.225;
an unsupported move sets `ko_lower_bound`; the bounds hold on 50 seeded held-out matchups;
ruff clean; the report stays under 50 ms. Merged, tagged and pushed:
`dcee5f6..2d3887f main -> main`, new tag `cp-04`.

### ✅ DONE — Order 6: Phase 5 design proposal, the Showdown battle-log parser. **STOP after the proposal.** _(→ proposal approved, step 1 built and approved)_
Branch: `task/05-showdown-parser`. Write the proposal as a new section in this tracker.
Phase 5 is a **pure library**: Showdown protocol text in, then `GameState` snapshots plus uncloaker evidence
out. No live connection, browser extension or WebSocket client; those come later. The proposal must cover:

1. **Inputs and two viewpoints.**
   - **Spectator mode** is a saved replay log. There is no `|request|`, so both sides are only what has been revealed.
   - **Player mode** is a live log plus our `|request|` JSON, which gives our full team and `ActionRequest`.
   Both must produce valid `GameState`s. First read the protocol documentation (`sim/SIM-PROTOCOL.md` in
   the pinned `pokemon-showdown` 0.11.11) and list the message types we handle and the ones we ignore on purpose.
2. **Architecture.** I recommend an event-sourced design: `parse_line -> Event` (typed Pydantic events) →
   `reduce(state, event) -> state` → an immutable `GameState` snapshot at each `|turn|`. That makes every turn
   replayable and testable, and it gives Phase 7 (XGBoost) its training rows for free. Propose an alternative
   only if it is clearly simpler.
3. **HP and identity details.** Spectator HP is shown as a percentage (check whether any Gen 1–4 format uses
   another scale). Map nicknames to species with `|switch|`/`|drag|` details, handle `|detailschange|`
   and forme changes (Rotom, Giratina, Deoxys, Castform), level from details, and Gen 1–2 specifics.
4. **Evidence rules for the uncloaker.** List each rule with a test case. This is where wrong data would quietly
   corrupt the posterior.
   - A move counts as revealed only when the Pokémon chose it. Exclude calls through Sleep Talk, Metronome,
     Mirror Move, Copycat, Assist, Me First, Snatch and Magic Coat (the `[from]` tags). Handle Transform and
     Gen 1 Mimic, where moves used while transformed are not the user's own.
   - Items come from `-item`, `-enditem` (consumed, eaten, knocked off), Leftovers and Black Sludge healing via
     `[from] item:`, and **Trick/Switcheroo swaps**: the received item is not the original set's item.
     Choice lock is inferred.
   - Abilities come from `-ability` and `[from] ability:` tags (Intimidate, Pressure, Sand Stream, …).
   - Ruled-out evidence, only where it is certain. Example: a Pokémon that was damaged and ended the turn on the field
     without a Leftovers heal in Gen 2+ doesn't hold Leftovers. Propose the exact list, and exclude anything ambiguous.
5. **Real-data corpus and validation.** Propose N public Gen 1–4 Random Battle replays (`gen1randombattle` …
   `gen4randombattle`), with the source and a download script (Node or Python, at build time). **Ask before
   downloading.** Checks:
   - every replay parses with no exception, and every turn snapshot validates against the schemas;
   - the final state agrees with the log (fainted counts against `|win|`, the last HP values);
   - parse and update time per event is under 1 ms, well inside the 50 ms ingest budget;
   - **R8 staleness rate:** for every opponent Pokémon, the share whose revealed evidence contradicts all tier-1
     sets, per generation. Report it, because it decides the hold-back question.
   - Commit a small sample of replays (license and size permitting) as offline fixtures; keep the rest in git-ignored `data/raw/`.
6. **Out of scope:** the live client and overlay, doubles, team preview (no Gen 1–4 singles format uses it), and Phase 6 orchestration.
7. **Decisions to ask the user,** with a recommendation for each: the architecture, corpus size and source, the list of
   ruled-out evidence rules, and which fixtures to commit.

Then **stop** and ask the user to approve or adjust the proposal before writing any parser code.

## Task 05 design proposal — Showdown battle-log parser (2026-10-11, approved)

Branch `task/05-showdown-parser`. The observations below come from
`sim/SIM-PROTOCOL.md` in the pinned `pokemon-showdown` 0.11.11 and from 500 battles I simulated
locally with that package (200 in Gen 4, 100 each in Gens 1–3), in a temp folder outside the repo.
No replay has been downloaded; I only queried the public replay search listing to see that all
four formats have recent replays.

### 1. Inputs and the two viewpoints

- **Spectator mode:** a saved replay log. Both sides are known only through what has been
  revealed. No `|request|`.
- **Player mode:** the log one player receives, which also carries `|request|` JSON with our full
  team (moves, item, ability, exact HP, computed stats) and the legal choices.

Both produce valid `GameState`s. Snapshots start at turn 1, when both leads are on the field
(`GameState` needs at least one Pokémon per side).

**Message types we handle** (the count is how often each appeared in the 200 Gen 4 battles):

| Group | Types |
|-------|-------|
| Setup | `player`, `teamsize`, `gametype` (anything but singles is rejected), `gen`, `tier`, `start` |
| Turn structure | `turn` (7,372), `upkeep`, `win`, `tie`, `request` |
| Major actions | `move` (13,150), `switch` (2,242), `drag`, `detailschange`, `-formechange`, `cant`, `faint` |
| HP and status | `-damage` (9,933), `-heal` (6,901), `-sethp`, `-status`, `-curestatus`, `-cureteam` |
| Stat stages | `-boost`, `-unboost`, `-setboost`, `-swapboost`, `-copyboost`, `-clearboost`, `-clearallboost`, `-clearpositiveboost`, `-clearnegativeboost` |
| Field and sides | `-weather`, `-fieldstart`, `-fieldend`, `-sidestart`, `-sideend` |
| Volatiles | `-start`, `-end`, `-transform`, `-prepare`, `-mustrecharge` |
| Items and abilities | `-item`, `-enditem`, `-ability`, `-endability`, and the `[from] item:` / `[from] ability:` tags on any line |

**Ignored on purpose:** `-crit`, `-supereffective`, `-resisted`, `-miss`, `-notarget`, `-hint`,
`-message`, `-anim`, `-hitcount`, `-singleturn`, `-singlemove`, `-activate`, `-immune` and `-fail`
(the last four are still scanned for ability tags), the timestamp `t:`, chat and room lines
(`c`, `c:`, `j`, `l`, `n`, `raw`, `html`, `inactive`, `inactiveoff`), `rule`, and everything that
does not exist in Gens 1–4 singles (`teampreview`, `poke`, `clearpoke`, `swap`, `replace`,
`-mega`, `-zpower`, …). An unknown type is counted, not an error, so a newer log still parses;
tests run in a strict mode that fails on any unknown type.

### 2. Architecture

Event-sourced, as the order recommends, with one adjustment:

```
parse_line(text) -> Event | None          typed, immutable Pydantic events
BattleTracker.apply(event)                 the only place state changes
BattleTracker.snapshot() -> TurnSnapshot   at every |turn|, and at the end
```

- `TurnSnapshot` holds the turn number, a validated `GameState`, a `SetEvidence` for every
  revealed Pokémon, and the events of the turn. A battle is a list of these, so every turn can
  be replayed and tested, and Phase 7 gets its training rows from the same list.
- **The adjustment:** the order sketches a pure `reduce(state, event) -> state` over immutable
  states. I recommend one small mutable tracker with immutable *snapshots* instead. The tracker
  must remember things that are not part of `GameState` (nickname-to-slot maps, whether an item
  is still the original one, which moves were used during the current stay), and copying a
  validated `GameState` on every one of roughly 450 lines per battle costs far more than copying
  it once per turn. Replayability is unchanged: the event list is the source of truth, and
  applying it again gives the same snapshots.
- Package `poketrix.showdown`: `protocol.py` (events and `parse_line`), `tracker.py` (state),
  `evidence.py` (the rules of section 4, separate so they can be tested alone), `request.py`
  (player mode), `replay.py` (`parse_battle(text, perspective=None) -> list[TurnSnapshot]`).
- No network code: text in, snapshots out.

**Player mode and spreads.** `|request|` gives our Pokémon's moves, item, ability and computed
stats, but not EVs or IVs, which the calculator's `known_set` needs. In Random Battle the spread
follows from the set, so the parser looks it up in the Phase 4 prior table and checks that our
computed stats equal the stats in the request; a mismatch is reported, not silently accepted.

### 3. HP and identity

- **HP scale:** all four formats run with "HP Percentage Mod". In 500 simulated battles every
  spectator HP value was `N/100`, or `0 fnt`, optionally followed by a status. No Gen 1–4 Random
  Battle format uses the 48-pixel scale. In player mode our own side shows exact `current/max`,
  which fills `hp_current` / `hp_max`.
- **Identity:** a Pokémon is keyed by (player, nickname); `switch` and `drag` carry the details
  string that gives species and level (`Raichu, L74`; no level means 100). Gender and shininess
  are ignored.
- **Forme changes:** `detailschange` and `-formechange` replace the species for types and stats
  (Castform's Forecast appeared in the sample). The Pokémon's set identity for the uncloaker
  stays the forme it was sent out as.
- **Transform:** `-transform` marks the Pokémon as transformed until it leaves the field.
- **Gens 1–2:** no abilities, and no items in Gen 1; nothing else differs in the log format.
- **Field timers:** the log does not say how many turns of weather, screens, Trick Room or
  Gravity remain. The tracker counts from when each started and reports the standard duration
  minus the turns elapsed; weather from an ability is reported as open-ended.

### 4. Evidence rules for the uncloaker

Wrong evidence would silently corrupt the posterior, so every rule gets its own log-snippet test,
and all of them are checked against ground truth (section 5).

**Revealed moves.** A `|move|` line reveals a move only if the Pokémon chose it:

| Situation | Counts as revealed? |
|-----------|---------------------|
| Plain `|move|P|Move|…` | Yes |
| `[from]` names another move that calls moves: Sleep Talk, Metronome, Mirror Move, Copycat, Assist, Me First, Snatch, Magic Coat, Nature Power | No (the calling move itself was revealed by its own line) |
| `[from] lockedmove`, or `[from]` naming the move itself (second turn of Sky Attack, Pursuit on a switch) | Yes, it is the Pokémon's own move |
| Any move while transformed | No |
| A move gained through Mimic, until the Pokémon leaves the field | No |
| Struggle | No |

The tag's spelling differs by generation and both must be read: Gen 4 writes
`[from] move: Sleep Talk`, Gens 1–3 write `[from] Sleep Talk`.

**Items.** The tracker keeps two things per Pokémon: the item it holds now (for the damage
calculator, in `BattlePokemon.revealed_item`) and its original item (for `SetEvidence.item`).

- Revealed as original: `-item` without a swapping source, `-enditem` (eaten, consumed, knocked
  off), and any `[from] item: X` tag (Leftovers and Black Sludge recovery, Life Orb recoil, a
  status from Toxic Orb or Flame Orb, a berry's boost).
- **Trick, Switcheroo, Thief, Covet:** `-item|P|X|[from] move: Trick` means P now holds X, and X
  was the *other* Pokémon's original item if that one had not swapped before. From then on
  neither Pokémon's later item reveals count as original.
- A positive "it must hold a Choice item" is never inferred; repeating a move proves nothing.

**Abilities.** `-ability|P|A`, and `[from] ability: A` on any line. With an `[of] Q` part the
ability is Q's; without one it belongs to the Pokémon on the line. Trace, Skill Swap and Role
Play are handled like item swaps: the copied ability is not the copier's original.

**Ruled out, only where it is certain:**

| # | Rule | Exclusions that keep it certain |
|---|------|--------------------------------|
| N1 | Not Leftovers and not Black Sludge: the Pokémon was on the field at the end of a turn, alive, below 100% HP, and no item recovery followed (Gen 2+) | Pokémon that may have Klutz; under Embargo or Heal Block; item already swapped |
| N2 | Not Life Orb: it chose a damaging move, the target lost HP directly (not a substitute), and no Life Orb recoil followed (Gen 4) | Pokémon that may have Magic Guard; item already swapped |
| N3 | Not a Choice item: it chose two different moves during one stay on the field (Gens 3–4) | called moves and Struggle do not count; item already swapped; Pokémon that may have Klutz |
| N4 | Not an absorbing ability (Levitate, Flash Fire, Water Absorb, Volt Absorb, Motor Drive, Dry Skin): it lost HP to a move of the absorbed type | attacker may have Mold Breaker; Gravity or Iron Ball for Levitate; ability already changed |

Left out as ambiguous: Focus Sash, resist berries, Lum and Sitrus Berry timing, Shell Bell, and
any rule based on damage amounts (that is the deferred 04b).

### 5. Corpus and validation

Two corpora, because they answer different questions.

**A. Simulated battles, with ground truth.** A script plays seeded Random Battles with the pinned
simulator and two random players, and saves the spectator log, one player's log with requests,
and both true teams. Nothing is downloaded. This is the only way to check the evidence rules
against the truth:

- every move the parser calls revealed is in that Pokémon's true set;
- every original item and ability it reports is the true one;
- nothing it rules out is true;
- in player mode, the `known_set` it builds reproduces the stats in the request.

The target for all four is 100% over 500 battles per generation (about 450 log lines and 37
turns per Gen 4 battle; 8–19 KB per log). The limit of this corpus: random players do not play
like people, so move and switch patterns are unrealistic even though the mechanics are covered
widely.

**B. Real replays, for robustness and the R8 staleness rate.** Public replays from
`replay.pokemonshowdown.com` (its search listing and each replay's `.log`), which exist for all
four formats as of 2026-10-10. Checks:

- every replay parses without an exception and every snapshot validates;
- the final state agrees with the log (`|win|`, fainted counts, last HP values);
- parsing and applying one event takes under 1 ms;
- **staleness rate (R8):** per generation, the share of opposing Pokémon whose final evidence
  makes the uncloaker leave tier 1, split into tier 2 and tier 3, and listed by upload month.

**What gets committed.** Simulated logs contain no personal data, so a small sample is committed
as offline fixtures. Real replays contain usernames and chat, so I recommend committing none of
them: they stay in git-ignored `data/raw/`, and only aggregate numbers go into this tracker.

### 6. Out of scope

The live client, WebSocket or browser overlay; doubles; team preview (no Gen 1–4 Random Battle
uses it); Phase 6 orchestration; and using damage amounts as evidence (04b).

### 7. Decisions asked before any code

| # | Question | Recommendation |
|---|----------|----------------|
| P1 | Architecture: typed events, one mutable tracker, immutable per-turn snapshots (instead of a pure reducer over immutable states)? | Yes |
| P2 | Add the simulated corpus (pinned simulator, no download) as the ground-truth test of the evidence rules? It reuses the `pokemon-showdown` install from Phase 4. | Yes |
| P3 | Simulated corpus size: 500 battles per generation generated on demand (git-ignored), 10 per generation committed as fixtures (about 0.5 MB)? | Yes |
| P4 | **May I download real replays?** 500 per generation (2,000 in total, roughly 30 MB), from the public replay site at about one request per second (about 35 minutes), into git-ignored `data/raw/`. | Yes |
| P5 | Commit no real replays (usernames and chat), only aggregate results? | Yes |
| P6 | Ruled-out rules N1–N4 as listed, with their exclusions? | Yes, all four |
| P7 | Player mode: take our spreads from the Phase 4 prior table and verify them against the request's stats? | Yes |
| P8 | Keep `BattlePokemon.volatiles` free-form, with the parser emitting a documented list, or turn it into a closed enum now? | Keep free-form; document the list |
| P9 | Build order: spectator mode and the evidence rules first (stop for review), then player mode and the real-replay measurements? | Yes, two steps |

### Decisions (2026-10-11, user)

P1–P9: the user chose every recommendation. Typed events with one mutable tracker and per-turn
snapshots; simulated battles as ground truth (500 per generation on demand, 10 per generation
committed); real replays may be downloaded (500 per generation, into git-ignored `data/raw/`)
and none are committed; rules N1–N4; own spreads from the prior table in player mode; volatiles
stay free-form; two build steps.

## Task 05, step 1 — spectator-mode parser and evidence rules (approved 2026-10-11)

Branch `task/05-showdown-parser`. Not merged, not tagged, not pushed. No replay was downloaded
in this step; that belongs to step 2.

Tests: 807 in total (731 before + 76 new). `ruff check src tests` is clean. **Test status needs
your attention:** all 76 new tests and all functional tests pass, but the five calculator *timing*
tests now fail intermittently on this machine (three full runs: 1, 5 and 2 failures, all of them
timing tests). See "Timing tests under load" below.

### What was built

- **`scripts/randbats/build_battles.mjs`** (`npm run build-battles`): plays seeded Random
  Battles with the pinned simulator and two random players, and saves the spectator log with both
  true teams. Fixtures: 10 battles per generation in `tests/fixtures/battles_gen{N}.json`
  (575 KB in total, 1,725 turns). The 500-per-generation corpus (30 MB) is generated on demand
  into git-ignored `data/raw/battles/`.
- **`poketrix.showdown`:**

  | Module | Responsibility |
  |--------|----------------|
  | `events.py` | 22 immutable, typed events |
  | `protocol.py` | `parse_line(text) -> Event \| None` |
  | `tracker.py` | `BattleTracker`: the only place state changes; builds validated `GameState`s |
  | `evidence.py` | `EvidenceBook`: the evidence rules, separate from state tracking |
  | `replay.py` | `parse_battle(text) -> BattleRecord` with one `TurnSnapshot` per turn |
  | `validation.py` | checks the evidence against true teams; `python -m poketrix.showdown.validation [dir]` |

- **Schemas:** `move_matches` / `moves_fit` (see "Hidden Power" below).

### Ground-truth validation

Every claim the parser makes about a set was compared with the true team:

| Gen | Battles | Turns | Pokémon seen | Moves revealed | Items identified | Abilities identified | Exclusions made | False claims |
|-----|---------|-------|--------------|----------------|------------------|----------------------|-----------------|--------------|
| 1 | 500 | 18,504 | 5,440 | 13,827 | — | — | — | 0 |
| 2 | 500 | 36,244 | 5,085 | 15,126 | 3,945 | — | 259 | 0 |
| 3 | 500 | 23,088 | 5,349 | 14,063 | 3,812 | 679 | 1,353 | 0 |
| 4 | 500 | 17,759 | 5,361 | 12,323 | 3,493 | 1,175 | 4,652 | 0 |

- 2,000 battles, 21,235 Pokémon, 55,339 revealed moves, 11,250 items, 1,854 abilities and 6,264
  exclusions: **no false claim**, no anomaly, and no unknown message type (strict mode).
- Which exclusions fired: Leftovers 2,149 and Black Sludge 1,051 (N1), Life Orb 1,182 (N2),
  Choice items 1,877 (N3), Water Absorb 5 (N4).
- End to end on the committed fixtures: evidence parsed from the log keeps the true set alive in
  the uncloaker's main path for at least 99.5% of Pokémon in every generation.
- Speed: 0.07 ms per log line including a validated snapshot every turn (target: under 1 ms).

### What the validation caught while building

Each of these would have corrupted the posterior silently:

1. **Hidden Power's type is not in the log.** The log says "Hidden Power"; sets say
   `hiddenpowerice`. The untyped id would have contradicted every known set. Now one rule,
   `move_matches`, says the untyped move matches any typed one; the uncloaker, the `SetPosterior`
   validator and `BattlePokemon` all use it. This is a small change to approved Phase 4 code.
2. **A stolen item was credited to the thief.** After Thief, the thief's Leftovers recovery was
   read as its own item. An item received through a swap now never counts as original.
3. **`[of]` does not always name the owner.** On `-heal … [from] ability: Water Absorb|[of] X`,
   X is the attacker. Abilities on a heal are credited to the healed Pokémon; `[of]` names the
   owner only where the ability acted on someone else (Static, Intimidate, Sand Stream, Rough
   Skin).
4. **N3 excluded Choice items in Gen 1.** Exclusions are now limited to items that exist in the
   generation and abilities the species can have.

### Changes to the proposed rules

- **N1 is narrower than proposed.** "Below 100% at the end of the turn" is not safe: poison,
  burn and weather damage can come after the moment Leftovers would act, so a full-HP holder is
  not healed and then drops below 100%. N1 now requires the Pokémon to have been below full HP
  *before* the end-of-turn phase (damaged by a move this turn, or already damaged when the turn
  began), with no reading of 100% since.
- **N2 and N4 close when the end-of-turn phase begins**, so Future Sight or poison damage is
  never mistaken for damage from the last move.
- **Once the item (or ability) is known, nothing more is ruled out for it.**
- Handled as proposed: called moves in both tag spellings, own-move continuations, Transform,
  Mimic, Struggle, Trick/Switcheroo/Thief/Covet, Trace, Baton Pass, cosmetic formes, Gen 1
  Reflect and Light Screen (they sit on the Pokémon; the snapshot mirrors them into the side
  conditions the calculator reads).

### Timing tests under load

- The five tests that assert a report takes under 5 ms (8 ms for Gens 1–2) failed in some full
  runs today. Measured alone, the report's best time is unchanged (about 3 ms), but the median
  varies from 3.8 to 11 ms between runs. With my changes stashed, the same test took 11 ms, so
  this is not a regression from Phase 5.
- The likely cause is machine load: OneDrive is the top CPU consumer on this PC (the repository
  is inside OneDrive, so it syncs `node_modules`, `.venv` and the 30 MB of `data/raw/`).
- I have changed nothing about these tests. Options for you: move the repository out of
  OneDrive or exclude those folders from sync; or apply review item R9 (a `slow` / `timing`
  marker) so that timing is checked separately from correctness.

### Known limits

- Random players do not play like people; the simulated corpus proves the rules sound for the
  mechanics it reaches, not for every situation on the ladder. N4 fired only 5 times.
- A transformed Pokémon keeps its own species in the state (its copied stats and types are not
  modelled); Kecleon's Color Change type is not tracked.
- Timers the log does not show (weather, screens, Trick Room, Gravity) are the standard five
  turns minus the turns elapsed; Light Clay and the weather rocks are not known.
- Spectator mode only. Player mode (`|request|`, our own full team) and the real-replay
  measurements, including the R8 staleness rate, are step 2.

### Next (after review)

Step 2: player mode, the replay download script, robustness on real replays, and the staleness
rate. Then the Phase 5 merge and `cp-05`.

## Review of Task 05, step 1 (2026-10-11, reviewer: Claude in claude.ai, on behalf of the user)

Verdict: **APPROVED.** I checked the following on the user's machine:

- **Tests:** 807 of 807 pass on `51775a8` (Linux shell; see R12 for the Windows timing failures).
- **cp-04:** merged with R6 and R7 included.
- **The ground-truth approach is the strongest validation in the project so far.** Playing simulated battles with known teams
  turned "the parser looks right" into "0 false claims in 74,707 checked claims (moves, items, abilities and exclusions)". The four bugs it caught
  (untyped Hidden Power, the item stolen by Thief, the `[of]` owner, Choice items in Gen 1) are exactly the silent
  corruptions the review warned about.
- **Changes to approved work, all accepted:**
  - `move_matches` for Hidden Power in the Phase 4 code. It's the correct fix, and the reason is documented.
  - The narrower N1, and N2/N4 closing at the start of the end-of-turn phase. Safer than what I proposed, and well argued.
  - Ruling nothing out once an item or ability is known.

### Findings

- **R10: explain the remaining 0.5%. This is part of step 2.** The parser makes no false claims, and the battles come from the
  same generator as the prior. So when the true set loses all probability, it should only be because the set never
  appeared in the 100,000-team sample. Classify every such Pokémon on the fixtures, and on the 500-per-gen
  corpus, as:
  - **(a)** its true set is absent from the prior table, which is coverage and acceptable; or
  - **(b)** its true set is present but was ruled out, which is a **bug** and must be fixed before `cp-05`.
  Report (a) per gen. It is the *synthetic floor* of the staleness rate (R8). Real replays will show the floor
  plus actual drift between the pinned simulator version and the live ladder.
- **R11: a transformed Pokémon in later phases.** The state keeps a transformed Pokémon's own species, so any
  damage calculation involving it would be wrong. That matters in Gen 1, with Ditto and Mew. The parser already
  marks `transform` in volatiles. Carry this into Phase 6: if either active Pokémon is transformed, the orchestrator
  must return `fallback` for the calculator and threat report, never numbers. Phase 5 needs no change, just a
  test that the volatile is present on the snapshot.
- **R12: timing tests fail on the user's PC because of OneDrive load.** It's not a regression. Two actions:
  - **Apply R9 now:** add `timing` and `slow` pytest markers. The default `pytest` run (and the pre-merge check) runs
    correctness only, with `-m "not timing"`, and timing is checked separately with `pytest -m timing`, with
    the results logged here. Keep the thresholds as they are.
  - **For the user (not Claude Code):** exclude `.venv`, `scripts/**/node_modules` and `data/raw` from OneDrive sync, or
    move the repository out of OneDrive, for example to `C:\dev\Poketrix`. GitHub is the backup now, so OneDrive adds little.
    The user decides.
- **R13: rules that rarely fire.** N4 fired only 5 times, and random players rarely use Trick, Baton Pass or Sleep
  Talk. For every evidence rule that fired fewer than 30 times in the corpus, add a **hand-written log fixture**
  (a few lines of protocol text) with the expected evidence, so each rule has a test that doesn't depend on chance.

## [Completed] Orders for Claude Code, batch 4 (do these in order, stopping where marked)

### ✅ DONE — Order 7: test hygiene (pre-approved, no stop) _(→ e8c35e9)_
On `task/05-showdown-parser`:
1. R12/R9: add the `timing` and `slow` markers, set the default `addopts` to `-m "not timing"`, document
   `pytest -m timing` in `README.md`, and run it once, logging the medians here.
2. R11: add a test that the transformed volatile is present on the snapshot.
3. R13: add a hand-written fixture for each rule that fired fewer than 30 times.
4. Commit. Full suite green and `ruff` clean.

**Result (2026-10-12): done.** Default run: 819 passed, 8 deselected (the timing tests); `ruff` clean.

- **R12 / R9.** `timing` and `slow` markers registered in `pyproject.toml`; `addopts` excludes
  `timing` by default; `README.md` documents `pytest -m timing` and `pytest -m "not slow"`. Eight
  timing tests are marked. The per-generation report test mixed correctness with a time limit, so
  it is now two tests. `slow` marks the uncloaker evaluation and the parser's ground-truth run;
  they still run by default.
- **`pytest -m timing`, run once as ordered: 4 passed, 4 failed.** The laptop was on battery
  (50%, Balanced plan) at about 50% CPU load, with the replay download for Order 8 running:

  | Timing test | Best | Median | Limit | Result |
  |-------------|------|--------|-------|--------|
  | Gen 4 report, 4 moves × 6 targets | 6.9 ms | 10.4 ms | 5 ms | failed here; passed inside the run above |
  | Gen 1 report, 30 evaluations | 12.0 ms | 14.6 ms | 8 ms | failed |
  | Gen 2 report, 30 evaluations | 8.2 ms | 11.4 ms | 8 ms | failed |
  | Gen 3 report, 30 evaluations | 7.2 ms | 8.6 ms | 8 ms | failed |
  | Gen 4 report, 30 evaluations | 6.7 ms | 7.9 ms | 8 ms | failed in the run, passed when measured |
  | Uncloaker update, 42 hypotheses | 0.9 ms | 1.0 ms | 5 ms | passed |
  | Threat report, 42 hypotheses | 8.5 ms | 10.1 ms | 50 ms | passed |
  | Parsing, per log line | 0.11 ms | 0.13 ms | 1 ms | passed |

  The same calculator code measured 2.9 ms best and 3.0–3.4 ms median on 2026-10-10 and
  2026-10-11. Thresholds are unchanged, as ordered. **These numbers should be taken again on AC
  power with nothing else running** before anyone reads them as the calculator's speed.
- **R11.** `test_a_transformed_pokemon_is_marked_on_every_snapshot_until_it_leaves` (Gen 1 Ditto):
  the `transform` volatile is on every snapshot while transformed and gone after the switch.
- **R13.** The tracker now counts how often each evidence rule fires (`BattleRecord.rule_counts`;
  `python -m poketrix.showdown.validation` prints the table). Over the 2,000 simulated battles:

  | Evidence rule | Times fired | Hand-written test |
  |---------------|-------------|-------------------|
  | N4: damaged through an absorbing ability | 5 | one per ability (Flash Fire, Motor Drive, Volt Absorb, Water Absorb, Levitate), plus the exclusions |
  | Move called by Mirror Move | 16 | yes, in the Gen 1 spelling |
  | Move called by Metronome, Copycat, Assist, Me First, Snatch, Magic Coat | 0 each | yes (already there) |
  | Move called by Nature Power | 0 | added |
  | Item swapped by Covet | 0 | added |
  | Item announced by a plain `-item` (Recycle) | 0 | added |
  | Ability shown through Frisk | 0 | added, in both line shapes |
  | Ability changed by Role Play, Skill Swap; suppressed (`-endability`) | 0 each | added |
  | Item swapped by Switcheroo | 44 | added anyway |
  | Ability copied by Trace | 76 | yes |
  | Every other rule | 129 to 82,724 | covered by the corpus and by hand |

  Writing them found one real bug: in Gen 4, Frisk's line names no Pokémon
  (`|-item||Leftovers|[from] ability: Frisk|[of] …`), which would have raised an exception on a
  real log. It is now read as "the Pokémon facing the Frisk user". A second, smaller fix: an item
  brought back by Recycle is held again.

### ✅ DONE — Order 8: Task 05 step 2. **STOP after it is built, for review before `cp-05`.** _(→ c3fe27d, 76c6328; approved 2026-10-12)_
1. **Player mode.** Parse `|request|` JSON into our full team (`known_set`, with spreads from the prior table as decided) and
   an `ActionRequest` every turn. **Ground truth again:** have the simulation script also save each player's
   own stream (with requests). Check that our team, HP, available moves and switches match the
   simulator exactly on all 500 battles per gen, and that every `ActionRequest` validates against the `GameState`.
2. **Real replay download.** Already authorised: 500 per gen, into git-ignored `data/raw/`. Be polite:
   at least 1 second between requests, an honest User-Agent, and backoff on errors. Record the replay ids and date range in a
   manifest. Commit the script and the manifest, not the replays.
3. **Robustness on real replays.** Run in lenient mode: 100% of replays parse without an exception.
   List every unknown message type and anomaly with counts. Then fix them, or document why they're ignored.
   Sanity checks that need no ground truth:
   - no Pokémon has more than 4 distinct self-chosen moves;
   - no Pokémon has two different original items or abilities;
   - every snapshot validates.
   Any violation is a parser bug.
4. **R10 + R8, the staleness rate.** For each gen, report:
   - the synthetic floor (R10 (a));
   - the real rate, meaning the share of opponent Pokémon whose evidence contradicts every tier-1 set, with a 95% confidence interval;
   - the share of those due to a move absent from the species' prior movepool versus an unseen combination of known moves.
   Then **recommend** one of: no change, a hold-back of x%, a prior rebuild against the current `pokemon-showdown`
   release, or both. The user decides at review.
5. Record everything in this tracker, then **stop**. On approval, the merge and `cp-05` follow.

**Result (2026-10-12): built, awaiting review.** Default run: 840 passed, 8 deselected (timing);
`ruff` clean. Nothing is merged; `cp-05` waits for approval.

#### 1. Player mode

- `protocol.py` parses `|request|` into a typed `RequestEvent` (our six Pokémon with exact HP,
  stats, moves, item and ability; the offered moves; forced switch, wait, trapped).
- `ownset.py` (new) turns a request Pokémon into a `PokemonSet`. The spread is the first one of
  that species in the prior table that reproduces the request's stats exactly and, for Hidden
  Power, its type. If none does, the default spread is used and the battle's `anomalies` say so.
- `tracker.py`: the first request fixes our team of six and its order. Every request is first
  compared with what the log had shown (HP, status, fainted, active, held item), any difference
  is counted in `disagreements`, and then the request is taken over. The resulting
  `ActionRequest` stays open only until the next event.
- `replay.py`: a player's log gives one snapshot per decision, with the request in
  `state.me.request`. A replacement chosen during a turn gets a snapshot of its own. A spectator
  log behaves exactly as before.
- `build_battles.mjs` also saves player 1's own stream. The fixtures keep it for the first two
  battles per generation (fixtures grew from 0.58 MB to 1.6 MB). The update timestamps are now
  written as 0, so regenerating the fixtures gives identical files.

Ground truth, 500 simulated battles per generation (`node build_battles.mjs 500 DIR 500`, then
`python -m poketrix.showdown.validation DIR`; the corpus is 307 MB, so it was built outside the
repo):

| Gen | Battles | Our Pokémon (sets and spreads exact) | Decisions | Forced switches | Request disagreed with the log | Violations |
|-----|---------|--------------------------------------|-----------|-----------------|--------------------------------|------------|
| 1 | 500 | 3,000 of 3,000 | 20,679 | 2,175 | 0 | 0 |
| 2 | 500 | 3,000 of 3,000 | 38,424 | 2,180 | 0 | 0 |
| 3 | 500 | 3,000 of 3,000 | 25,297 | 2,209 | 0 | 0 |
| 4 | 500 | 3,000 of 3,000 | 20,082 | 2,323 | 0 | 0 |

"Violations" covers: a set that differs from the true one, a spread that does not reproduce
the request's stats, a decision without a request, and any difference between the opponent (state
and evidence) as seen in player mode and as seen by a spectator of the same battle. Every one of
the 104,482 `ActionRequest`s validated against its `GameState`. The spectator check from step 1
was run again on the same battles: still 0 false claims.

Offered moves that are not in the active Pokémon's set, all 2,000 battles: Struggle 1,174, Gen 1
"Fight" (held by a trapping move) 1,695, Recharge 270, while transformed 2,043, while holding a
Mimic move 303. These are legitimate, which is why the schema check had to change (decision D1
below).

One bug found by the corpus: from Gen 2 on, Mimic is announced with `-activate`, not `-start`,
so the `mimic` volatile was only set in Gen 1. It is now set in every generation.

#### 2. Real replays

`scripts/download_replays.py` (standard library only): 1.2 s between requests, the User-Agent
names this project, growing waits after errors, resumable. 2,000 replays (26 MB) are in
git-ignored `data/raw/replays/`. Only `id`, `formatid`, `uploadtime`, `rating` and `log` are kept.
Committed: the script and `data/replays_manifest.json` (replay ids and upload dates, no names).

| Gen | Replays | Uploaded | Ladder games | Tournament or challenge games |
|-----|---------|----------|--------------|-------------------------------|
| 1 | 500 | 2026-09-27 to 2026-10-11 | 379 | 121 |
| 2 | 500 | 2026-07-16 to 2026-10-11 | 135 | 365 |
| 3 | 500 | 2026-09-28 to 2026-10-11 | 394 | 106 |
| 4 | 500 | 2026-09-26 to 2026-10-11 | 365 | 135 |

A ladder game is one whose log has a bare `|rated|` line. Tournament and challenge games can run
under custom rules, so they count for robustness but not for staleness.

#### 3. Robustness (`python -m poketrix.showdown.corpus`)

| Gen | Replays | Raised an exception | Refused as out of scope | Unknown message types | Anomalies, ladder | Anomalies, other games |
|-----|---------|---------------------|-------------------------|-----------------------|-------------------|------------------------|
| 1 | 500 | 0 | 0 | 0 | 0 | 0 |
| 2 | 500 | 0 | 2 | 0 | 0 | 10 |
| 3 | 500 | 0 | 0 | 0 | 0 | 0 |
| 4 | 500 | 0 | 0 | 0 | 0 | 0 |

65,822 turns in total. What the first run found, and what was done:

| Finding | Count | Action |
|---------|-------|--------|
| Unknown message type `badge` | 60 lines | Ignored on purpose (a ladder decoration) |
| HP written as a bare `0` or `0 slp` (replays uploaded by a side server, ids starting `rom-`) | 2 replays raised | Fixed: read as fainted |
| `teamsize` of 8 (tournament games under a custom rule) | 2 replays raised | Now refused with `UnsupportedBattleError`, the same way doubles are (decision D3) |
| "A fifth own move was seen" | 10, all in Gen 2 tournament games | Not a parser bug: those games run under custom rules (a level-100 Omastar, Glare on Ampharos, five moves). 0 on the ladder |
| Two original items or abilities on one Pokémon | 0 | |
| A snapshot that fails validation | 0 | |

#### 4. Staleness (R10 and R8)

Measured on the final evidence of every Pokémon that was sent out, on both sides.
"Contradicted" means the uncloaker left tier 1: no known set fits everything revealed.

Synthetic floor (R10), 2,000 simulated battles: **0 of 21,235** Pokémon contradicted in any
generation (95% interval per generation: 0% to 0.08%). So there are no class (b) cases (a known
set wrongly ruled out), and in this sample no class (a) cases either.

Real ladder games:

| Gen | Pokémon | Contradicted | 95% interval | Move the species never has in the prior | Item the species never holds | Known parts, unseen combination |
|-----|---------|--------------|--------------|------------------------------------------|------------------------------|---------------------------------|
| 1 | 3,949 | 0 (0.00%) | 0.00% to 0.10% | 0 | 0 | 0 |
| 2 | 1,373 | 0 (0.00%) | 0.00% to 0.28% | 0 | 0 | 0 |
| 3 | 4,161 | 15 (0.36%) | 0.22% to 0.59% | 8 | 0 | 7 |
| 4 | 3,694 | 12 (0.32%) | 0.19% to 0.57% | 10 | 2 | 0 |

No species was missing from the prior and no ability was unknown. The contradictions are not
spread evenly; they sit in eight species:

| Gen | Species | Contradicted, of those seen with two or more moves revealed | What was seen |
|-----|---------|--------------------------------------------------------------|---------------|
| 3 | Seaking | 8 of 17 | Megahorn, Protect, Toxic, Surf together |
| 3 | Medicham | 3 of 9 | Bulk Up with Shadow Ball and Substitute |
| 3 | Primeape | 3 of 13 | Bulk Up, Rock Slide, Substitute |
| 3 | Aggron | 1 of 7 | Rock Slide, Substitute, Toxic |
| 4 | Ho-Oh | 4 of 8 | Brave Bird, Recover, Sacred Fire, Substitute |
| 4 | Charizard | 4 of 7 | Leftovers; Air Slash, Earthquake, Fire Blast, Roost, Will-O-Wisp |
| 4 | Mightyena | 2 of 11 | Heal Bell, Taunt, Toxic, Super Fang |
| 4 | Jirachi | 1 of 5 | Calm Mind, Psychic, Signal Beam, Thunderbolt |

About half of the appearances of Seaking, Ho-Oh and Charizard contradict the prior. That
pattern is what a changed set list looks like, not random noise: the live server evidently
gives these species sets that `pokemon-showdown` 0.11.11 (the npm release the prior was sampled
from) does not have. This was not confirmed against the server's current data files.

For reference, tournament and challenge games: Gen 1 1 of 1,250, Gen 2 18 of 3,815, Gen 3 3 of
1,162, Gen 4 8 of 1,521. The Gen 2 cases are the custom-rule games described above.

Limits of this measurement: the Gen 2 ladder sample is small (135 games); a Pokémon that
revealed nothing cannot contradict anything, so the rate per Pokémon with two or more moves
shown is higher than the table's; and it is one two-week sample.

**Recommendation (the user decides):**

- **No hold-back.** The rate is 0% to 0.4%, and when it happens the uncloaker already falls
  back to tiers 2 and 3 and reports `fallback`; it never raises. A flat hold-back would take
  probability from every species to cover eight.
- **Rebuild the prior from Showdown's current source** (a git checkout of the live data, not
  the npm release) and run this measurement again as the acceptance check. The staleness is
  specific to a few species, which a rebuild fixes and a hold-back does not. It needs a
  download of roughly 200 MB, so it needs your go-ahead, and it can be its own small order
  after `cp-05`.
- Keep `python -m poketrix.showdown.corpus` as the check to repeat whenever the prior is rebuilt.

#### Decisions taken while building, for your review

| # | Decision | Why | Alternative |
|---|----------|-----|-------------|
| D1 | `SideState` now accepts offered moves outside the known set in three cases: `struggle`, `recharge`, `fight` (`FORCED_MOVES`); while the active Pokémon is transformed or holds a Mimic move (`BORROWS_MOVES`); and an untyped `hiddenpower` for a typed one | The simulator really offers these (5,485 times in the corpus); the old check rejected a true request | Keep the strict check and drop such requests |
| D2 | In player mode a snapshot is a decision, so a forced switch during a turn has its own snapshot with the same turn number | The guardrail needs the legal actions at every decision, not once per turn | One snapshot per turn, forced switches not represented |
| D3 | Teams larger than six are refused with `UnsupportedBattleError` | Only custom-rule games have them; the schema's limit of six stays true for every supported format | Raise the schema limit to Showdown's maximum of 24 |
| D4 | The showdown package now imports the prior (`uncloak`) and the stat formula (`calc`) to build our own sets | "Spreads from the prior table", as decided in P-decisions; the formula is not duplicated | Pass the prior in from the caller only (the tracker already accepts it as an argument) |
| D5 | Only ladder games count towards staleness | Custom rules say nothing about the prior | Count every game (Gen 2 would read 0.35%) |

Open points for Phase 6:

- In the simulator's stream a request arrives after the update that ends with `|turn|`. The
  tracker applies lines in the order it is given, so the live client must pass them in arrival
  order.
- `maybeTrapped` (Shadow Tag or Arena Trap not yet revealed) is not represented: the switches
  are listed as legal and the simulator may reject one.
- R11 still stands: no damage for a transformed Pokémon.
- The timing tests were not run again; the machine was busy with the download and the corpus
  builds. They should be taken on AC power with nothing else running.

## Review of Task 05, step 2 (2026-10-12, reviewer: Claude in claude.ai, on behalf of the user)

Verdict: **APPROVED.** I checked the following on the user's machine (`76c6328`):

- **Tests:** the default run gives 840 passed with 8 timing tests deselected. The timing tests then passed on their own
  (8 of 8, run from the reviewer's shell). Order 7 is confirmed done.
- **Player mode against ground truth:**
  - 12,000 of 12,000 sets and spreads are exact.
  - 104,482 of 104,482 requests validate.
  - No request disagreed with the log.
  - Still 0 false evidence claims.
- **Real replays:** 2,000 of 2,000 parse, apart from 2 games with 8-Pokémon teams, which are refused by name. Two real-world bugs were found
  and fixed: the bare `0` fainted HP, and Mimic's `-activate` from Gen 2 on.
- **R10 is closed:** the synthetic floor is 0 of 21,235, so the evidence rules never kill a set the prior knows. The 0.5% gap
  seen in step 1 was prior coverage, not a bug.
- **R8 is measured:**
  - Gens 1–2 show 0 contradictions.
  - Gens 3–4 show 0.3–0.4%, concentrated in 8 species. Seaking, Ho-Oh and Charizard are each about 50% contradicted.
  - That's a changed set list, not noise.

### Decisions

| # | Decision | Ruling |
|---|----------|--------|
| R8 | Hold back probability or rebuild | **No hold-back. Rebuild the prior from the current source**, as Order 10. The pattern is per-species drift, which only a rebuild fixes. |
| D1 | Accept offered moves outside the known set (`FORCED_MOVES`, `BORROWS_MOVES`, untyped Hidden Power) | **Accepted.** Each of the three cases must have its own test with a real request, and `BORROWS_MOVES` applies to the active Pokémon only. If either is missing, add it in Order 9. |
| D2 | One snapshot per decision in player mode | **Accepted, with an addition:** add `decision_index` (0 = the turn's main choice, 1+ = forced switches within the turn), so `(turn, decision_index)` uniquely identifies a decision. Phase 7 needs that as the row key for training data. Do it in Order 9. |
| D3 | Refuse teams over six | **Accepted.** |
| D4 | The showdown package imports `uncloak` (the prior) and `calc` (the stat formula) | **Accepted for `calc`**, because the stat formula is a pure function and duplicating it would be worse. **For the prior**, see Advice A1 (optional). |
| D5 | Staleness counts ladder games only | **Accepted.** Keep reporting both numbers, as now. |

### Carried into Phase 6 (from Order 8's open points and earlier reviews)

- **R5:** an unsupported move gives a fallback or unknown result, never zero damage.
- **R11:** a transformed Pokémon gets no damage numbers.
- **Line order:** the live client must pass lines in arrival order, with the request after the `|turn|` update.
- **New, R14 (trapping):** `maybeTrapped` is not represented. The orchestrator must estimate the trapping risk from the
  uncloaker: P(the opponent's ability is Shadow Tag or Arena Trap, or Magnet Pull against our Steel-type), using the ability marginal.
  Any switch recommendation must carry that risk, and when it is ≥ 0.5 the policy must also give a move alternative.

## [Completed] Orders for Claude Code, batch 5 (do these in order, stopping where marked)

### ✅ DONE — Order 9: finish and close Phase 5 (pre-approved, no stop if green) _(→ cp-05)_
1. On `task/05-showdown-parser`, add `decision_index` (D2), and check the D1 tests (three cases, active Pokémon only).
2. Run the full suite and `ruff`, then `pytest -m timing`, with AC power and the machine idle if possible. Log the medians.
3. Run `git switch main`, then `git merge --no-ff task/05-showdown-parser`, then `git tag -a cp-05 -m "Showdown parser: spectator + player mode, evidence, staleness"`.
   Then update `docs/CHECKPOINTS.md` and `README.md`, mark Phase 5 as done in the status table, and run `git push origin main --tags`.
4. Mark Order 9 as Done in "▶ Current orders".

**Result (2026-10-13): done, merged and tagged `cp-05`.** 846 passed in the default run (840 + 6
new); `ruff` clean.

| Item | What was done |
|------|---------------|
| D2 | `TurnSnapshot.decision_index`: 0 for the turn's main choice, 1 and up for replacements chosen during the turn. The closing snapshot of a log takes the next index, so `(turn, decision_index)` is unique over every snapshot. A spectator log has 0 everywhere except that closing snapshot. |
| D1 | One test per case with a real request: each of `struggle`, `recharge`, `fight`; a move held through Mimic; an untyped `hiddenpower` standing for the typed one (and still rejecting a foreign move beside it). A fourth test shows `BORROWS_MOVES` excuses the active Pokémon only: the same volatile on a benched Pokémon excuses nothing. |
| A1 | Applied. `ownset.py` takes a `SetSource` protocol (`sets_for`), and the tracker's default source imports the prior on first use. Importing `poketrix.showdown` no longer loads `poketrix.uncloak`; a spectator log never does. |
| Timing | `pytest -m timing`: 8 of 8 passed. The laptop was on battery (66%) at 14% CPU load, so not the AC-power run the order asked for. Medians: parsing 0.008 ms per log line; one posterior update 0.53 ms (41 hypotheses); a whole player-mode battle with 33 decisions 29 ms. |

### ✅ DONE — Order 10: rebuild the prior from Showdown's current source (R8) _(→ cp-05b)_
The user is told about the download size in the reviewer's message. If the user said no, skip this order and mark it "Skipped".
Branch: `task/05b-prior-rebuild`.
1. **Smallest source first:** check whether an npm release of `pokemon-showdown` newer than 0.11.11 contains the
   updated Gen 1–4 Random Battle data. If it does, pin that release. If not, make a shallow git checkout (`--depth 1`) at a
   **recorded commit SHA**. Keep the checkout **outside the repository and outside OneDrive**, for example
   `%LOCALAPPDATA%\poketrix-cache\pokemon-showdown`. Commit only the rebuilt prior tables and the manifest
   (source, version or SHA, date).
2. Rebuild the prior with the same sampling (100,000 teams per gen, the same seeds policy).
3. **Acceptance checks.** All must pass to merge without a stop:
   - The Task 04 evaluation targets are still met (calibration error ≤ 0.02, true set non-zero on tier 1 in ≥ 99.9%,
     log-loss as agreed).
   - The synthetic floor (R10) is still 0 on the simulator corpus. Regenerate the corpus with the new source.
   - The real-replay staleness (ladder games) has **dropped**, both overall and for the 8 named species.
     Report a before/after table per gen and per species.
   - Prior tables stay ≤ 5 MB in total, and the full suite plus `ruff` are green.
4. If all checks pass: merge `--no-ff`, tag `cp-05b`, log it, push, and mark the order Done. If any fails: **stop** and
   report the table instead.

**Result (2026-10-13): all acceptance checks passed; merged and tagged `cp-05b`.** 847 passed in
the default run; `ruff` clean.

Source: npm has no release after 0.11.11 (published 2026-07-28), so the prior is sampled from a
shallow git checkout at commit `942cda71d14bf0618bd57991708a2e2734b6daba` (2026-10-09), kept in
`%LOCALAPPDATA%\poketrix-cache\pokemon-showdown` (247 MB after `npm install` and `node build`).
`scripts/randbats/simulator.mjs` (new) chooses the source: the npm package by default, or the
checkout named by `POKETRIX_SHOWDOWN_DIR`. Each table's `source` records the commit and its date.
With the npm source the scripts still reproduce the old tables byte for byte. Same sampling as
before: 100,000 teams per generation, the same seeds.

| Gen | Sets before | Sets after | Sets removed | Sets added | Species whose sets changed |
|-----|-------------|------------|--------------|------------|----------------------------|
| 1 | 431 | 431 | 2 | 2 | 1 (Beedrill) |
| 2 | 559 | 559 | 0 | 0 | 0 |
| 3 | 1,184 | 1,174 | 198 | 188 | 39 |
| 4 | 1,740 | 1,732 | 352 | 344 | 53 |

| Acceptance check | Result |
|------------------|--------|
| Task 04 evaluation targets (asserted by `tests/test_uncloak.py`) | Met. True set kept on tier 1: 100% in Gens 1–3, 99.9975% in Gen 4. Largest move calibration error with the full prior: 0.0029 |
| Synthetic floor (R10), corpus regenerated from the new source | 0 of 21,233 contradicted, 0 bugs. Spectator evidence: 0 false claims. Player mode: 12,000 of 12,000 sets exact, 103,699 requests, 0 violations |
| Real-replay staleness has dropped | Yes, to 0 (table below) |
| Prior tables at most 5 MB | 0.66 MB |
| Full suite and `ruff` | Green |

Staleness on the same 2,000 real replays, ladder games:

| Gen | Before | After |
|-----|--------|-------|
| 1 | 0 of 3,949 | 0 of 3,949 |
| 2 | 0 of 1,373 | 0 of 1,373 |
| 3 | 15 of 4,161 (0.36%) | **0 of 4,161** (95% interval 0% to 0.09%) |
| 4 | 12 of 3,694 (0.32%) | **0 of 3,694** (95% interval 0% to 0.10%) |

| Species (ladder contradictions) | Before | After |
|---------------------------------|--------|-------|
| Gen 3: Seaking / Primeape / Medicham / Aggron | 8 / 3 / 3 / 1 | 0 / 0 / 0 / 0 |
| Gen 4: Charizard / Ho-Oh / Mightyena / Jirachi | 5 / 4 / 2 / 1 | 0 / 0 / 0 / 0 |

Tournament and challenge games: Gens 3–4 went from 3 and 8 to 0 and 0; Gens 1–2 are unchanged at 1
and 18, which are the custom-rule games.

One tracker bug found by the new corpus and fixed: when Trick swaps two copies of the same item
(Leftovers for Leftovers), the second line cleared the item the first line had just handed over,
so the state showed no item. Player mode caught it as 3 request disagreements; the evidence was
never wrong. It has its own test.

The battle fixtures and the held-out tables were regenerated from the same source.

### ✅ DONE — Order 11: Phase 6 design proposal, the turn engine. **STOP after the proposal.** _(→ proposal decided 2026-10-12)_
Branch: `task/06-orchestrator`. Write the proposal as a new section in this tracker. Phase 6 turns one player-mode
snapshot into one validated, explained recommendation within 500 ms. Cover:

1. **Pipeline.** A plain state machine, not LangGraph (per the architecture doc): `GameState` + evidence →
   uncloaker (every revealed opponent) → threat report (their active against our active and each of our switch-ins) →
   our move evaluations against their active, weighted by the posterior → policy → `Recommendation` → text. Every
   stage returns a `SubsystemResult` and has a timeout. A single `TurnReport` schema carries all intermediate results,
   so every number in the text can be traced to its source.
2. **Decision policy v0, deterministic with no ML.** Propose a transparent rule set and say exactly how ties are broken.
   For example: who moves first (speed, priority, Trick Room, paralysis); our best move by the chance we KO before they KO us; when to
   switch (their `p_ko_best_move` is high, we can't win the exchange, and a switch-in takes the least expected
   damage); R14 trapping risk; R5 and R11 fallbacks. The opponent's action prior is a **heuristic placeholder**
   (`ActionPrediction` with `model_version="heuristic-0"`) until Phase 7 replaces it.
3. **Evaluation, the headline result of the project so far.** Have the policy play real games in the pinned simulator
   through a Python ↔ Node bridge that streams the battle protocol. Measure the win rate over at least 500 games per gen against:
   - (a) the simulator's random player;
   - (b) a "max damage" baseline that always picks the highest expected-damage move.
   Report 95% intervals. Propose the bridge design, and keep the bridge a dev tool, not part of the runtime.
4. **Synthesis.** v0 uses **templates, no LLM**: the headline and explanation are generated from `TurnReport` fields. The
   `Recommendation` guardrail checks legality and `allowed_numbers`. An LLM writer is an optional later step behind the
   same interface, with the API key from an environment variable and never in the repo. Recommend when it should be added, if at all.
5. **Latency.** p50 and p95 per decision on the corpus, against the 500 ms budget, with a per-stage breakdown. Profile Gen 1
   multi-hit cases (R4) here.
6. **Out of scope:** the live client and overlay (Phase 8), XGBoost (Phase 7), doubles.
7. **Decisions to ask the user,** with a recommendation for each: the policy rules, the evaluation opponents and game counts,
   the bridge design, templates versus an LLM, and the `TurnReport` shape.

Then **stop** for the user's approval before writing any code.

## Task 06 design proposal — the turn engine (decided 2026-10-12, approved with changes)

Branch `task/06-orchestrator`. No code yet. Goal: one player-mode snapshot in, one validated
and explained recommendation out, in under 500 ms, with every number traceable.

### 1. Pipeline

New package `src/poketrix/advisor/`. A plain state machine: a table of stages run in order, each
returning a `SubsystemResult`, each with a budget.

| # | Stage | Input → output | Budget | If it fails or times out |
|---|-------|----------------|--------|--------------------------|
| 1 | Uncloak | evidence of each opposing Pokémon still alive → `SetPosterior` each | 20 ms | That Pokémon has no posterior; stages 2–4 skip it and say so |
| 2 | Threats | their active against our active and each legal switch-in → `ThreatReport` each | 150 ms | Switches are not scored; the policy chooses among moves only |
| 3 | Offence | each legal move against their active, over the set hypotheses → `MoveOutlook` | 100 ms | Moves are ranked by what was evaluated; the rest are "unknown" |
| 4 | Order | P(we move first) per move: priority, speed over the hypotheses, paralysis, Trick Room, Choice Scarf | 10 ms | 0.5 is assumed and reported as assumed |
| 5 | Opponent | `ActionPrediction`, `model_version="heuristic-0"` | 5 ms | Assume they attack |
| 6 | Policy | everything above → scored options → one choice | 10 ms | The legal move with the highest expected damage, else the first legal action |
| 7 | Write | the choice → `Recommendation`, validated against the state and `allowed_numbers` | 5 ms | A fixed minimal sentence with no numbers |

- **Timeouts without threads.** The work is CPU-bound Python, so a thread cannot be stopped from
  outside. One `Deadline` is passed down; a stage checks it between units of work (per Pokémon,
  per move) and returns `timeout` with what it has finished. Stages are ordered so the most
  useful work happens first (our active before the bench).
- **There is always a legal answer.** The last fallback needs only the request.
- **`TurnReport`** (new schema in `schemas/outputs.py`) carries: the snapshot key
  `(turn, decision_index)`; every stage's `SubsystemResult` (payload, status, latency); the scored
  options; the final `Recommendation`; and `numbers`, a flat `dict[str, float]` in which each
  stage registers what it computed under a stable key (`our.icebeam.ko`, `their.p_ko`,
  `switch.2.expected_pct`, `trap.risk`). `numbers` is exactly what the guardrail receives as
  `allowed_numbers`, so a number in the text is traceable to a stage by its key.

### 2. Decision policy v0 (deterministic, no ML)

All quantities are fractions of *remaining* HP, weighted by the posterior.

| Symbol | Meaning | Source |
|--------|---------|--------|
| `d(m)` | Expected share of their active's remaining HP our move `m` removes, accuracy included | Offence |
| `k(m)` | P(`m` knocks their active out this turn) | Offence (exact KO odds) |
| `D(X)` | Expected share of our Pokémon X's remaining HP their best move removes | Threats |
| `K(X)` | P(they knock X out this turn if they attack) = `p_ko_best_move` | Threats |
| `f(m)` | P(we move before them) | Order |
| `a` | P(they attack) | Opponent |
| `t` | P(we are trapped) (R14) | Ability marginal of the posterior |

- **One exchange with move `m`:** `trade(m) = d(m)·(1 − a·K·(1 − f(m))) − a·D·(1 − k(m)·f(m))`.
  We deal our damage unless they knock us out first; we take theirs unless we knock them out first.
- **Matchup value of our Pokémon X against their active:** `M(X) = max over X's moves of trade(m)` with `a = 1`.
- **Staying, move `m`:** `S = trade(m) + P(we survive the turn)·M(active)`.
- **Switching to X:** `S = −a·D(X) − hazard(X) + P(X survives the hit)·M(X)`. The switch-in takes
  the hit now and then has its own matchup. `hazard(X)` is the exact entry damage.
- **Trapping (R14):** `t` = P(their ability is Shadow Tag or Arena Trap and applies, or Magnet Pull
  against our Steel-type). A switch scores `(1 − t)·S(switch) + t·S(best move)`. Any switch
  recommendation states `t` when it is above 0, and when `t ≥ 0.5` the text also names the best move.
- **Forced switch:** the legal switch-in with the highest `M(X) − hazard(X)`.
- **Status and utility moves.** v0 scores three kinds and nothing else: recovery (the HP it
  restores, as if it were damage undone), a hazard that is not up yet, and a sleep, paralysis or
  poison move on a healthy target. The last two get fixed, documented constants (decision Q2). Every
  other status move scores 0 and is never recommended in v0.
- **Ties, in order:** higher score; higher `k`; higher accuracy; a move before a switch; the
  request's own order. No randomness, so a game replays identically.
- **Opponent heuristic-0:** `p_switch = clamp(0.10 + 0.40·k_best, 0.05, 0.60)` if they have a
  healthy Pokémon on the bench, else 0, where `k_best` is our best KO chance on their active. The
  rest is split between attack and utility by the share of damaging moves in their posterior
  moveset. These constants are placeholders that Phase 7 replaces.
- **Fallbacks.** R5: an unsupported move has no `d` or `k`; it is listed as unknown, never as 0,
  and if their best move is unsupported the text says the KO chance is a lower bound. R11: if
  either active is transformed there are no damage numbers; the engine returns status `fallback`
  with the highest-power legal move and says why.

Known limits of v0: it looks one exchange ahead plus the following matchup; it does not plan
set-up moves, PP, weather turns, or predict their switch-in.

### 3. Evaluation: win rate in the simulator

- **Bridge (dev tool, not runtime).** `scripts/randbats/play_bridge.mjs` runs battles in the pinned
  simulator, one long-lived process for many games. For a side marked `external` it prints every
  protocol chunk as a JSON line and reads that side's choice (`move 2`, `switch 3`) from stdin. A
  side marked `random` is the simulator's own `RandomPlayerAI`.
- **Python side.** `scripts/play_games.py` feeds the lines to `BattleTracker`, calls a `Player`
  (`choose(snapshot) -> Recommendation`) and sends the choice back. Two players: the policy, and
  the max-damage baseline, which uses the same Offence stage and always picks the highest
  expected damage (a forced switch goes to the first legal Pokémon). Both use only what their own
  side can see.
- **Matches:** policy against random and policy against max-damage, 500 games per generation
  each (4,000 games), with fixed seeds. Plus max-damage against random, 200 per generation, to
  show how strong the baseline is.
- **Reported per generation and opponent:** wins of games with the 95% Wilson interval, average
  turns, the share of decisions that ended in `fallback`, `timeout` or `error`, and choices the
  simulator rejected (must be 0; any is a bug).
- **Cost:** about 35 decisions per game for each external side. At 50–150 ms per decision that is
  2–5 hours in one process; four processes in parallel bring it under 90 minutes.
- **What it proves and what it does not.** Beating these two shows the pipeline's advice is better
  than random and than greedy play. It says nothing yet about play against people.

### 4. Synthesis

- v0 is **templates, no LLM**: one template per kind of decision (attack for the knock-out, best
  trade, defensive switch, forced switch, limited information). The headline fits 120 characters,
  the explanation 600.
- A template may only print values from `TurnReport.numbers`. `cited_numbers` holds those exact
  values and the guardrail checks them and the action's legality. An extra test reads every number
  out of the generated text and requires it to be the rounded form of a cited one.
- Writers sit behind one small `Writer` protocol (`write(report) -> Recommendation`). An LLM writer
  would be a second implementation: key from an environment variable, never in the repo, with
  the template as its fallback when validation fails twice.
- **Recommendation:** no LLM in Phase 6. It cannot improve the decision, and a network call does
  not fit the 500 ms budget. Consider it in Phase 8 as an on-demand "explain more", outside the budget.

### 5. Latency

- Measure p50 and p95 per decision and per stage on the player-mode corpus (2,000 decisions per
  generation, sampled with a fixed seed), on AC power with the machine idle. Gen 1 multi-hit
  cases (R4) are reported separately.
- Expected from the Phase 3–5 measurements: about 10 ms per threat report with the largest
  hypothesis table, so up to 60 ms for six; Offence is of the same order. Target p95 under
  250 ms; the hard limit stays 500 ms.
- Optimise only what the measurement shows: first a per-turn cache of `evaluate_move` results,
  then evaluating switch-ins only when staying scores badly.

### 6. Out of scope

The live client and overlay (Phase 8), the XGBoost predictor (Phase 7), doubles, an LLM writer,
multi-turn search.

### 7. Decisions for the user

| # | Question | Recommendation |
|---|----------|----------------|
| Q1 | Policy: the one-exchange-plus-matchup score above, or a simpler rule list (attack if we can KO, switch if they can)? | The score. It is one formula, every term is a number we already compute, and the rule list is its special cases |
| Q2 | Status moves in v0: recovery, hazards and sleep/paralysis/poison with fixed constants; all others never recommended? | Yes. Propose constants at review of the build, tuned only against the simulator results, and report them |
| Q3 | Opponents and game counts: random and max-damage, 500 games per generation each, plus 200 of max-damage against random? | Yes |
| Q4 | Pass marks for Phase 6: win rate above 50% against both, with the interval's lower end above 50%? | Yes as the minimum to merge; report the real numbers whatever they are |
| Q5 | Bridge: one Node process, JSON lines over stdin and stdout, both sides drivable from Python? | Yes. No new dependency, and it reuses the pinned simulator |
| Q6 | Templates only in Phase 6, the LLM writer deferred to Phase 8? | Yes |
| Q7 | `TurnReport` as described, added to `schemas/outputs.py`, with `numbers` as the single source for `allowed_numbers`? | Yes |
| Q8 | Timeouts by a shared deadline checked between units of work, no threads or processes? | Yes. Simple, deterministic, and enough for CPU-bound stages |
| Q9 | Build order: (a) Offence, Order and `TurnReport`; (b) policy and templates; (c) bridge and win rates; with a stop after (b) and after (c)? | Yes: two reviews, the second with the headline numbers |
| Q10 | Advice A3 (`python -m poketrix analyze <log>`) in step (b), A4 (README results table) after step (c), A2 (GitHub Actions) as a separate small commit now? | Yes to all three, if you want CI on the repository |

## Review of Order 10 (cp-05b) — 2026-10-12, reviewer

**Accepted.** The rebuild was the right call, and it was measured properly:

- Ladder staleness in Gens 3–4 went from 27 to 0, and all 8 named species are at 0.
- The synthetic floor is still 0, the uncloaker targets are still met, and the tables are 0.66 MB.
- The source is pinned to Showdown commit `942cda7` (2026-10-09).
- The Trick same-item bug was found by the regenerated corpus and fixed with its own test.

Keep `python -m poketrix.showdown.corpus` as the standing check. Re-run it before any real-play claim, because the live
server keeps changing sets.

## Review of the Task 06 proposal — decisions (2026-10-12, reviewer, for the user)

Verdict: **APPROVED WITH CHANGES.** The pipeline, the deadline-based timeouts, `TurnReport.numbers` as the single
source for `allowed_numbers`, and the fallback ladder are all good. The changes below are part of the build.

| # | Decision | Ruling |
|---|----------|--------|
| Q1 | Score-based policy | **Yes**, with these clarifications: `d(m)` and `D(X)` are capped at 1, because overkill has no value. A share of remaining HP stays a share (a KO counts as 1, whatever HP was left). Document `trade`, `M` and `S` in the module docstring with one worked example. |
| Q2 | Status moves (recovery, hazards, sleep/para/poison), others 0 | **Yes.** The constants are tuned **only on separate tuning seeds**, never on the evaluation seeds (see E2). Report the constants and the tuning runs. |
| Q3 | Opponents and counts | **Yes, with paired games (E1).** Raise max-damage against random to **500 per gen**, so the two win rates against random can be compared on equal footing. |
| Q4 | Pass marks | **Replaced by E3.** "Above 50% against random" is too low a bar to mean anything. |
| Q5 | Bridge | **Yes**, plus R15 below. |
| Q6 | Templates only, no LLM in Phase 6 | **Yes.** |
| Q7 | `TurnReport` in `schemas/outputs.py` | **Yes.** |
| Q8 | Shared deadline, no threads | **Yes.** |
| Q9 | Build (a), then (b), then (c); stop after (b) and after (c) | **Yes.** |
| Q10 | A3 in (b), A4 after (c), A2 now | **Yes to all three.** A2 only adds a workflow file under `.github/workflows/`. It changes no repository setting, and no secrets are involved. |

### Evaluation design (E1–E3) — replaces Q4

- **E1: paired games.** Team luck dominates Random Battles. For every seed, play the game **twice with the teams
  swapped**: the policy gets team A, then team B. Score each pair. That cancels most of the team luck, so
  500 pairs per gen tell us much more than 500 single games. The report gives the win rate over games,
  plus "pairs won 2–0 / split / lost 0–2".
- **E2: separate seeds.** Use one seed range for tuning (the Q2 constants, any thresholds) and a different, fixed range for
  the reported evaluation. Write both ranges in the tracker before running, so the evaluation can't be tuned to.
- **E3: pass marks for `cp-06`.**
  1. **Against max-damage, the real test:** pooled over the four gens (2,000 pairs), the 95% Wilson lower
     bound of the game win rate is **above 50%**, and no single gen's point estimate is below 45%.
  2. **Against random:** the policy's win rate is **not lower** than max-damage's own win rate against random. The
     policy's interval lower bound must be at or above max-damage's point estimate, per gen.
  3. **Health:** 0 illegal choices, `error` in 0 decisions, `timeout` in under 1% of decisions, and p95 latency under 250 ms.
  If any mark is missed, **stop and report.** No tuning on the evaluation seeds to get past it.

### New finding R15: a failed switch while trapped is probably free in Showdown

`maybeTrapped` means the switch might be refused. In Showdown's protocol a refused switch normally comes back as
`|error|[Unavailable choice]` followed by a **new request with `trapped: true`**, and the player simply chooses
again without losing the turn. **Verify this in the pinned simulator's source** (Gens 1–4) before building. If it holds:

- The policy does **not** discount switches by `t`. The text still mentions the trapping risk. Simplify the R14 rule to this.
- The bridge and the player must handle that re-request. These refusals are **legitimate**, are counted separately as
  "trap re-asks", and are **not** counted as illegal choices.

If it doesn't hold in some generation, keep the `t` discount for that generation only, and say so.

### Smaller notes

- `trade(m)` assumes they stay in. When they switch (`p_switch`), our hit lands on an unknown Pokémon. That's fine for v0,
  but list it under Known limits.
- `M(active)` uses the HP before the exchange. That's an accepted approximation; note it in the docstring.
- Gen 1: a trapping move (Wrap, Bind) can stop the target from acting. v0 ignores that. Note it, and don't model it.

## [Completed] Orders for Claude Code, batch 6 (Order 13 is carried into batch 7)

### ✅ DONE — Order 12: Phase 6 build, steps (a) and (b). **STOP after (b)** for review. _(→ 8f6109f, 1b4e19b; approved 2026-10-13)_
Branch: `task/06-orchestrator`.
0. **A2 first,** as its own small commit: a GitHub Actions workflow that installs, runs `ruff`, then runs `pytest -m "not timing"`
   on Python 3.10 and 3.12, on push and on pull requests. Check that it runs green on the pushed branch.
1. **Check R15** in the simulator source, and record what you find (file and line, per gen) in this tracker.
2. **(a):** the Offence and Order stages, the `TurnReport` schema with `numbers`, the stage runner with `Deadline`, and the fallback
   ladder. Test every fallback path (R5 unsupported, R11 transformed, a timeout part-way through a stage, a missing posterior).
3. **(b):** the policy (Q1 with the clarifications, R15 outcome, Q2 with *provisional* constants), templates behind `Writer`,
   the guardrail wiring, and A3 (`python -m poketrix analyze <log> [--turn N]`). Tests:
   - hand-built positions where the right choice is obvious: a KO available, about to be KO'd with a safe switch, a forced switch, trapped;
   - the "every number in the text is a cited, rounded number" test;
   - replaying a player-mode fixture produces a legal recommendation at every decision;
   - latency p50 and p95 per stage on the corpus sample (timing marker).
4. Write it up in this tracker: what was built, the latency table, and three example outputs of `analyze` on real turns. Then **stop**.

**Result (2026-10-13): steps (a) and (b) built, awaiting review.** 870 passed in the default run
(847 + 23 new); `ruff` clean. Nothing is merged. **Two findings (F1, F2) need a decision before
Order 13.**

#### 0. CI (A2) and R15

- A2 applied in `8f6109f`: `.github/workflows/tests.yml` runs `ruff` and
  `pytest -m "not timing"` on Python 3.10 and 3.12, on push and pull requests. The first run on
  `task/06-orchestrator` was green.
- **R15 holds in every generation.** `sim/side.ts` (commit `942cda7`), `chooseSwitch`, lines
  984–997: a switch chosen while `pokemon.trapped` goes to `emitChoiceError` (lines 527–537),
  which sends `|error|[Unavailable choice] Can't switch: The active Pokémon is trapped`, sets
  `trapped: true` in the request and sends that request again. The turn is not spent. The Gen 1–4
  mods do not override it. `maybeTrapped` is set by Shadow Tag, Arena Trap and Magnet Pull
  (`data/abilities.ts` 197–207, 2518–2527, 4158–4167; Gen 3 versions in
  `data/mods/gen3/abilities.ts`), so it only arises in Gens 3–4. **Outcome:** the policy does
  not lower a switch's score for the trapping risk; the text states it.

#### 1. What was built

| Part | Where | What it does |
|------|-------|--------------|
| Contracts | `schemas/outputs.py` | `TurnReport` with each stage's `SubsystemResult`, the scored options and `numbers`; `MoveOutlook`, `OptionScore`, `Decision` and the stage payloads |
| Maths added | `calc/order.py`, `calc/report.py` | `acts_first_chance` (priority, then each generation's own Speed rule, Trick Room) and `expected_hp_share` (capped at the HP that is left) |
| Threat report | `uncloak/threat.py` | New `expected_best_share`: the D of the formula, computed per set like `p_ko_best_move` |
| Stages 1–5 | `advisor/stages.py` | Uncloak, threats, offence, order, opponent heuristic-0. Each checks its deadline between units of work and records its numbers |
| Policy | `advisor/policy.py` | The Q1 score, with the formula and a worked example in the docstring; hazards exact; R14 risk from the ability posterior; provisional Q2 constants |
| Writer | `advisor/writer.py` | `Writer` protocol and `TemplateWriter`. A sentence appears only when its numbers exist |
| Runner | `advisor/pipeline.py` | `TurnAdvisor.advise(snapshot) -> TurnReport`: the stage table, `Deadline`, the fallback ladder, the guardrail check |
| A3 | `python -m poketrix analyze <log> [--turn N]` | Prints the state, their likely sets, their threats, our scored options and the advice |
| Latency tool | `python -m poketrix.advisor.latency [dir] [n]` | The table below |

Fallback paths, each with a test: R5 (an unsupported move stays unscored, never 0; a lower bound
is said in the text), R11 (transformed: `fallback`, no damage numbers, highest-power legal move),
a stage timing out part-way (keeps what it finished), a whole turn out of time, no posterior,
their Pokémon fainted, a single legal action.

Provisional Q2 constants (to be tuned on the tuning seeds only): recovery = the HP restored as a
share of the HP left (Rest × 0.5); a hazard not yet up = 0.06 per benched opponent; sleep 0.60,
paralysis 0.30, Toxic 0.30, poison 0.15, each × accuracy.

#### 2. Latency

2,000 decisions per generation sampled from the 500-battle corpus (seed 20261301). The laptop was
on battery at about 10% load, so not the AC-power run.

| Gen | Total p50 | Total p95 | Max | Threats p50 / p95 | Offence p50 / p95 | Other stages p95 | Decisions not `ok` |
|-----|-----------|-----------|-----|-------------------|-------------------|------------------|--------------------|
| 1 | 13.6 ms | 38.8 ms | 131 ms | 7.0 / 22.3 | 4.8 / 14.6 | each under 1.5 | 59 `fallback` |
| 2 | 9.4 ms | 26.7 ms | 179 ms | 4.7 / 16.2 | 3.2 / 9.3 | each under 1.5 | 47 `fallback` |
| 3 | 8.9 ms | 31.9 ms | 173 ms | 4.4 / 18.4 | 3.2 / 11.2 | each under 1.5 | 26 `fallback` |
| 4 | 9.1 ms | 30.9 ms | 176 ms | 4.4 / 18.2 | 3.3 / 11.9 | each under 1.5 | 45 `fallback` |

p95 is 6 to 9 times under the 250 ms target; no `timeout` and no `error` in 8,000 decisions. The
`fallback` decisions are transformed Pokémon, a fainted target, and evidence outside the prior.
`pytest -m timing`: the 4 new tests pass; of the 8 older ones, the Gen 1 and Gen 2 calculator
tests missed their 8 ms limit on battery (8.5 and 8.8 ms) and the other 6 passed.

#### 3. Three real turns (`analyze`, fixture battle 0)

**Gen 4, turn 9: a knock-out is taken.**
```
ours:   Pinsir L84     theirs: Ho-Oh L72
  +1.377  stoneedge      removes 80%, knock-out 80%
  +0.641  closecombat    removes 30%, knock-out 0%
  +0.109  switch to Zapdos   takes 38%, knocked out 0%
Stone Edge: 80% to knock out Ho-Oh
Stone Edge removes about 80% of Ho-Oh's remaining HP on average and knocks it out 80% of the
time. Pinsir acts first 100% of the time. If Ho-Oh attacks, it takes about 82% of Pinsir's
remaining HP and knocks it out 6% of the time.
```

**Gen 3, turn 6: the best trade.**
```
ours:   Hitmontop L87 71%     theirs: Primeape L84 41% def+1
  +0.399  hiddenpowerghost   removes 68%, knock-out 6%
  +0.378  switch to Zapdos   takes 36%, knocked out 2%
Hidden Power Ghost: about 68% of Primeape's remaining HP
Hidden Power Ghost removes about 68% ... Hitmontop acts first 0% of the time. If Primeape
attacks, it takes about 51% of Hitmontop's remaining HP and knocks it out 10% of the time.
```

**Gen 4, turn 2: a switch that I think is wrong (finding F1).**
```
ours:   Porygon-Z L79 64% spa+2     theirs: Qwilfish L83 100%
  +0.845  switch to Golduck   takes 46%, knocked out 29%
  +0.718  triattack           removes 100%, knock-out 100%
Switch to Golduck: Porygon-Z is knocked out 33% of the time if it stays
```

#### 4. Findings that need a decision before Order 13

| # | Finding | Evidence | Recommendation |
|---|---------|----------|----------------|
| F1 | **The approved score gives up certain knock-outs for a switch.** A knock-out now and a knock-out next turn by the switch-in are worth the same, and staying is charged a second exchange against a Pokémon that will already be gone (`M(active)`) | On the 8 fixture battles the engine advises a voluntary switch in 114 of 337 decisions (34%), and in 16 of them a move with a 90% or higher knock-out chance was available. The turn above: Tri Attack knocks out 100% of the time and scores 0.718; the switch scores 0.845 | Two changes to the formula, both still closed-form: (1) the second exchange counts only if their Pokémon is still there, `P(both alive)·M(active)`; (2) a tempo factor γ on every second-exchange term (start at 0.5, tune on the tuning seeds). I did not make them: they change the approved Q1 formula |
| F2 | **A move's cost to ourselves is not scored.** Explosion and Self-Destruct count as a free knock-out; recoil and Hyper Beam's recharge turn cost nothing | Gen 2 fixture battle, turns 3–7: "Explosion: 100% to knock out Piloswine" at every decision | Charge a self-KO move the HP share it gives up (1.0), in `trade`. Leave recoil and recharge for later and list them under known limits |
| F3 | The opponent heuristic makes `a` small against sets full of status moves (0.19 in the turn above), so taking a hit looks nearly free | Same turn: half of Qwilfish's likely moves are hazards or status | Leave it for Order 13: `a` is one of the placeholders, and F1's fix removes most of its effect. Report its effect in the tuning runs |

Other notes: the order stage takes their move to have no priority (known limit); a switch-in's
status moves are not judged; `maybeTrapped` itself is still not in the request schema, so the
risk comes from the posterior alone.

Deviations from the proposal, small: `TurnReport` holds the `SubsystemResult` of each stage as
typed fields (`uncloak`, `threats`, `offence`, `order`, `opponent`, `policy`) rather than a list;
a stage with nothing to work on (R11, a fainted target, no posterior) returns `fallback` with an
empty payload and the reason, not `error`; the writer receives a `Brief` (decision, numbers,
caveats), because a `TurnReport` cannot exist before its recommendation.

### ⤷ MOVED — Order 13: see batch 7 (its text there replaces this one)
1. The bridge (Q5 + R15), the two players, paired games (E1), and the seed ranges written here first (E2).
2. Tune the Q2 constants on the tuning seeds only, and report them.
3. Run the evaluation: policy against max-damage and policy against random, 500 pairs per gen each, plus max-damage against random, 500 per gen.
4. Report per gen and pooled: win rates with Wilson intervals, pair outcomes, average turns, fallback, timeout and error shares,
   trap re-asks, and latency p50 and p95. Then the E3 verdict.
5. If E3 passes: A4 (a README results table), then **stop** for review before the `cp-06` merge. If it fails: **stop** and report, with no
   tuning on the evaluation seeds.

## Review of Order 12 (2026-10-13, reviewer, for the user)

Verdict: **APPROVED**, with the score fixes below to be made before the win-rate run.

What's good:

- **R15 settled from the source.** `sim/side.ts` `chooseSwitch` re-asks a trapped switch with `trapped: true`, and no turn is
  spent. Switches are not discounted for trapping; the text still states the risk. Correct.
- **Latency:** p95 is 27–39 ms per gen, with 0 timeouts and 0 errors in 8,000 decisions (measured on battery). That's far inside 250 ms.
- **Fallback ladder:** every path has a test. `numbers` → `allowed_numbers` is wired up, and CI is green.
- **The three deviations** (typed stage fields on `TurnReport`, `fallback` with a reason rather than `error`, the `Brief` handed
  to the writer): **all accepted.** Each is cleaner than what was proposed.
- **Raising F1–F3 instead of patching them quietly was exactly right.** The `analyze` output made the flaw visible, which
  is what it's for.

### Decisions on F1–F3

| # | Ruling |
|---|--------|
| F1 | **Accepted, both parts.** (1) The second exchange counts only if both Pokémon are still in: staying = `trade(m) + γ·P(we survive)·(1 − P(we KO))·M(active)`. (2) Tempo factor `γ` on **every** second-exchange term, on the stay side *and* the switch side, so the two stay comparable: switching = `−a·D(X) − hazard(X) + γ·P(X survives)·M(X)`. Start at γ = 0.5. Tune it on the tuning seeds from the grid {0.3, 0.5, 0.7, 1.0} only. Update the docstring formula and its worked example. |
| F2 | **Accepted, generalised.** Any move whose user faints (Showdown's `selfdestruct` flag: Explosion, Self-Destruct, Memento, Healing Wish, Lunar Dance where they exist) is charged `1.0` (its own remaining HP) in `trade`, and its stay value has `P(we survive) = 0`. Recoil is **optional (A7):** the calculator already has absolute damage, so recoil's share of our HP = `recoil_fraction × expected_absolute_damage / our_remaining_hp`, capped at 1. Add it if it takes under an hour; otherwise it goes under known limits with the Hyper Beam recharge. |
| F3 | **Deferred to Order 13, as recommended,** but as a *tuned* knob: add `a_floor` (the opponent's attack probability is at least this value), tuned on the tuning seeds from {0, 0.5}. Report its effect. |

### Guardrail metrics. Report them on the fixtures after the fix, and again on the evaluation games

- **Thrown-away KOs:** the share of decisions where the engine advises a *voluntary* switch while a move with KO ≥ 90% and
  `f ≥ 0.9` (we move first) was legal. Target **0**. Any case left must be listed with its numbers.
- **Voluntary switch rate:** report it before the fix (114 / 337 = 34%) and after. There's no target; it is a sanity signal.
- **Self-KO rate:** how often a self-KO move is advised, and in what positions (it should mostly be the last Pokémon or a
  guaranteed trade).

### Timing note
The Gen 1 and Gen 2 calculator timing tests ran at 8.5 and 8.8 ms against an 8 ms limit, **on battery**. Re-run them on AC power before
`cp-06`. If they still fail on AC, report the medians and propose a new limit then. Don't change the limit now.

## [Partly completed] Orders for Claude Code, batch 7 (Order 13 continues under batch 8's amendments)

### ✅ DONE — Order 12b: the score fixes (pre-approved, no stop if the checks pass) _(→ f93bb0b; accepted 2026-10-13)_
On `task/06-orchestrator`:
1. Make F1 (both parts, with γ a named parameter defaulting to 0.5), F2 (the self-faint charge), and F3's `a_floor` parameter
   (default 0). Recoil (A7) is optional.
2. **Regression tests from the real turns:**
   - Gen 4, fixture battle 0, turn 2: Porygon-Z must choose **Tri Attack**, not the Golduck switch.
   - Gen 2, the Explosion turns 3–7: Explosion must no longer be advised at full value. Assert the score now includes the
     self-faint charge, and give the expected choice.
   - The Pinsir and Hitmontop turns must keep their current choices.
3. Report the three guardrail metrics on the 8 fixture battles, before and after. Thrown-away KOs must be 0, or each case listed.
4. Full suite green, `ruff` clean, CI green. Then go straight to Order 13. If a check fails, **stop** and report.

**Result (2026-10-13): done.** 877 passed in the default run (870 + 7 new); `ruff` clean.

- **F1, F2, `a_floor`** are in `advisor/policy.py` behind `PolicySettings` (`gamma` 0.5,
  `a_floor` 0, `utility_scale` 1). Self-faint moves are a named set of five: the dex snapshot
  does not carry Showdown's `selfdestruct` field. Recoil (A7) was not added; it is listed with
  the recharge turn under known limits.
- **One correction to the ruled F1 formula, decided by the user on 2026-10-13.** As ruled,
  `(1 − P(we KO))·M(active)` made a knock-out *forfeit* a good matchup's value: on the fixtures
  the engine declined a 90%+ knock-out move in 17 of 90 chances (Gen 1: Body Slam 1.228 over a
  certain, first-moving Earthquake knock-out at 0.998). Now, after our knock-out, the second
  exchange counts as `max(M, 0)`:
  `stay = trade(m) + γ·P(we survive)·[(1 − k·act)·M + k·act·max(M, 0)]`.
  A knock-out ends a bad matchup's cost and keeps a good one's value. A test asserts that a
  knock-out never scores below the same damage without one. The 13 declined knock-outs left
  are 6 Explosions and 7 turns where we are slower and they knock us out first if they attack.
- **Regression tests from the real turns:** Porygon-Z now chooses Tri Attack (0.776 against
  0.375 for the Golduck switch); Muk's Explosion scores −0.008 (`d·act − 1`) and Hidden Power
  Ground is advised on turn 3; Pinsir keeps Stone Edge and Hitmontop keeps Hidden Power Ghost.

| Guardrail, 8 fixture battles, 337 decisions | Before | After |
|----------------------------------------------|--------|-------|
| Voluntary switches | 114 (34%) | 68 (20%) |
| Thrown-away knock-outs (KO ≥ 90% and first ≥ 90%) | 0 | 1 |
| Self-KO move advised | 10 | 1 |

The one thrown-away case is Explosion (Gen 3 battle 1, turn 2: knocks out 100%, acts first
100%, the engine switches instead), so it is a refused trade, not a thrown-away knock-out; the
test excludes self-KO moves and requires 0. "Before" is 0 by the reviewer's definition because
the 16 cases reported under Order 12 did not all move first. The one self-KO advice left is
Gen 3 battle 1, turn 3: Explosion at 100% with six Pokémon left on each side, where every other
option scores below 0. `python -m poketrix.advisor.audit [dir]` prints this table.

### Order 13: the bridge and the win rates (replaces the batch-6 text). **STOP with the results, before `cp-06`.**
1. The bridge (Q5 + R15: trap re-asks counted separately), the policy and max-damage players, and paired games (E1).
   **Write the tuning and evaluation seed ranges here before running anything** (E2).
2. **Tune on the tuning seeds only:** γ ∈ {0.3, 0.5, 0.7, 1.0}, `a_floor` ∈ {0, 0.5}, and the Q2 constants (small steps around the
   provisional values). Use about 100 pairs per gen against max-damage for each setting. Keep the grid to what's listed, so that
   tuning can't overfit. Report every setting's win rate, and pick by pooled win rate.
3. Freeze the chosen settings, then run the evaluation: policy against max-damage and policy against random, 500 pairs per gen each,
   plus max-damage against random, 500 per gen.
4. Report per gen and pooled:
   - win rates with Wilson intervals, and pair outcomes (2–0, split, 0–2);
   - average turns;
   - the fallback, timeout and error shares, and trap re-asks;
   - the three guardrail metrics;
   - p50 and p95 latency (on AC power if possible).
   Then give the **E3 verdict.**
5. E3 passes → write A4 (the README results table), then **stop** for review before the `cp-06` merge. E3 fails → **stop** and
   report, with no tuning on the evaluation seeds.

**Plan, written on 2026-10-13 before any tuning or evaluation game was played (E2).**

A game is fixed by `(generation, index)`: `play_bridge.mjs` derives both teams and the battle
seed from base seed 20261401 and the index. A pair is the same index played twice with the two
teams swapped. Simulator: the pinned checkout, commit `942cda7`.

| Purpose | Game indices, per generation | Pairs per generation |
|---------|------------------------------|----------------------|
| Harness testing only (not reported) | 900,000 and up | a few |
| **Tuning** | 1,000,000 to 1,000,099 | 100 |
| **Evaluation** | 2,000,000 to 2,000,499 | 500 |

Tuning, against max-damage only, 100 pairs per generation per setting (800 games each):

1. γ ∈ {0.3, 0.5, 0.7, 1.0} × `a_floor` ∈ {0, 0.5}, with `utility_scale` 1.0: 8 settings.
2. With the best (γ, `a_floor`): `utility_scale` ∈ {0.5, 1.5}, which moves every Q2 constant by
   half. 2 more settings.

The setting with the highest pooled win rate is frozen; a tie goes to the setting nearest the
defaults (γ 0.5, `a_floor` 0, `utility_scale` 1). Nothing else is tried. The evaluation then
runs once on the evaluation indices with the frozen setting.

## Review of Order 12b and the mid-run report (2026-10-13, reviewer, for the user)

**Order 12b: accepted.**
- **The user's correction is right, and the reviewer's ruling was wrong.** The F1 formula as I ruled it made a knock-out
  forfeit a good matchup's value (17 of 90 declined KOs). `stay = trade + γ·P(survive)·[(1 − k·act)·M + k·act·max(M, 0)]` is
  the correct form. The test that "a KO never scores below the same damage without one" is the right guard, so keep it permanent.
  The lesson for the process is that **measured behaviour beats a reviewer's formula.** The autonomy envelope below makes that the default.
- **Guardrails:**
  - Voluntary switches went from 34% to 20%.
  - Thrown-away KOs are 0 by definition; the single Explosion case is a refused self-KO trade, correctly excluded.
  - Self-KO advice went from 10 to 1, and that one is defensible (every other option scores below 0).
- **The Gen 1 Desync Clause fix (`e2a556f`) is accepted**, with 0 false claims still on the ground-truth set. See 13-A2 about the tuning runs.

## ▶ ACTIVE — Orders for Claude Code, batch 8

## Reviewer note on tuning step 1 (2026-10-13)

**Claude Code's question ("raise the strict against-random pass mark first, or run as written?") is answered: amendment 13-A1
replaces it.** Apply 13-A1…A5, then run the evaluation. Don't wait for anything else.

Reading of the eight-setting table (100 pairs per gen against max-damage, tuning indices):

- **The defaults lead:** γ 0.5 with no attack floor, at 77.8% pooled (74.7–80.5%). That is the best sign tuning can give, because the
  pre-registered tie rule and the winner agree, so there is little winner's-curse risk in freezing it.
- **The top five are within about 2 points** and inside each other's intervals, so the policy is not sensitive to γ in 0.3–0.7.
  Only γ 1.0 is clearly worse, which confirms that F1's tempo factor matters.
- **The attack floor (F3) never helped.** Keep `a_floor = 0`, and leave F3 to Phase 7's learned opponent model.
- **Gen 1 is the weak spot,** at about 65% for every setting, against 74–85% elsewhere. It's insensitive to γ, so the cause is likely
  Gen 1 mechanics the policy doesn't model, not the tuning. It is added to the Order 15 backlog as item 0 (below).
- **13-A2 still applies.** Re-run the Gen 1 slice of the five settings that ran before `e2a556f`, then rebuild the table. Gen 1 is the
  weakest gen, and the top five are 2 points apart, so same-code Gen 1 numbers could reorder them. If the leader is still γ 0.5 / floor
  0, freeze it. If the order changes, apply the pre-written rule to the rebuilt table.
- **Expectation for the evaluation:** a pass on E3.1 against max-damage is likely, given about 78% on tuning seeds, with
  some regression to expect on fresh seeds. Report the real numbers, whatever they are.

**Addition to the Order 15 backlog, item 0: Gen 1 diagnosis.** Before any new feature, take 50 lost Gen 1 *evaluation-adjacent*
games (from the tuning range or a fresh diagnostic range; **never the evaluation range**) and tag the deciding turn of each:
- full paralysis or freeze luck;
- crits (high-crit moves, Speed-based crit rate);
- partial trapping (Wrap, Bind, Fire Spin, Clamp);
- Hyper Beam with no recharge after a KO;
- Explosion's Defense halving;
- status that the score undervalues (sleep);
- a policy mistake.

The tag counts decide which Gen 1 mechanic is worth modelling first.

### Order 13, amendments 13-A1…A5. **Apply all of these before the first evaluation game.** Tuning may continue meanwhile.

- **13-A1: replace pass mark E3.2 (against random).** As written, it needed the policy's lower bound to reach max-damage's own
  win rate. Near the ceiling (max-damage won 21 of 24 scratch games) that demands roughly 97% or more, so it measures nearness to
  100%, not skill. That was the reviewer's mistake. **New E3.2, non-inferiority:** per generation, the 95% interval of
  *(policy's win rate − max-damage's win rate), both against random*, has a lower end above **−2 percentage points**. In plain
  words: against easy opponents, the policy must not lose noticeably more often than greedy play does. Use the Newcombe/Wilson
  interval for a difference of two proportions. E3.1 (beating max-damage head to head) remains **the** headline test, and E3.3 is unchanged.
- **13-A2: clean tuning data.** The Gen 1 fix doesn't only touch games that crashed. It ignores a first move whenever it
  repeats the side's last one (187 of 500 battles), so Gen 1 posteriors, and with them decisions, differed in the five settings
  run before it. **Re-run only the Gen 1 slice (100 pairs) of those five settings** on the fixed code: about 1,000 games, roughly a seventh of
  the tuning cost. Rebuild the eight-setting table from same-code results only, then pick by the pre-written rule. Do not
  change the selection rule now that results are in.
- **13-A3: quarantine instead of halting.** A new tracker bug must not kill a multi-hour run, and must not be hidden either.
  On any exception in the harness or the tracker:
  - save the seed, the full log and the traceback to `data/raw/quarantine/`;
  - drop **the whole pair** from the scoring, so no partial pair biases the result;
  - continue with the next pair.

  Report the quarantine count per generation. **Health mark (added to E3.3): at most 0.5% of pairs quarantined per
  generation.** Above that, the run is invalid. Stop, fix, and re-run that generation on its same indices. Every quarantined game
  becomes a regression test after the run.
- **13-A4: the burned-seed rule (only if E3 fails).** Evaluation indices 2,000,000–2,000,499 are used **once**. You may
  analyse the evaluation games to diagnose a failure, but any change after that is version v1 and is judged on a **fresh** range
  (3,000,000–3,000,499), written here before it runs. No re-running the old range with new code to "see if it passes now".
- **13-A5: also report the pair-level view.** Give the mean pair score (0, 0.5 or 1 per pair) with a bootstrap 95% interval
  (10,000 resamples, fixed seed) next to the game-level Wilson interval. Treating games as independent is conservative under pairing;
  the pair view shows the real precision. The verdict stays on E3 as amended.

Then carry on with Order 13 steps 3–5 as written, and **stop with the results** before `cp-06`.

#### Order 13, checkpoint of 2026-10-13 (Claude Code): tuning finished, setting frozen, **stopped before the evaluation on a pass-mark question**

No evaluation game has been played. Indices 2,000,000–2,000,499 are untouched.

**Amendments applied** (`ad2fb53`, 889 tests): 13-A1 (Newcombe interval of the difference, margin −2 points, per generation),
13-A3 (a pair that raises is quarantined to `data/raw/quarantine/`, dropped whole, counted; over 0.5% of a generation's pairs fails
the health mark), 13-A5 (mean pair score with a bootstrap interval over pairs, 10,000 resamples, seed 20261402). Only whole pairs
are scored. 13-A4 is a rule, not code.

**13-A2 done, for all eight step-1 settings, not five.** Their Gen 1 slices (1,600 games) were replayed on the fixed code; the
earlier Gen 1 games are kept apart in `tune/before_gen1_fix/`. **Every one of the 1,600 games had the same winner as before**, so
the table's Gen 1 column and the order did not change: the fix alters evidence in rare positions, and none of them changed a
decision on these seeds. No pair was quarantined.

**Final tuning table** (tuning indices, 100 pairs per generation, against max-damage, same code throughout):

| γ | `a_floor` | `utility_scale` | Gen 1 | Gen 2 | Gen 3 | Gen 4 | Pooled | 95% interval |
|---|-----------|-----------------|-------|-------|-------|-------|--------|--------------|
| **0.5** | **0** | **1.5** | 65.0% | 81.5% | 82.0% | 85.0% | **78.4%** | 75.4% to 81.1% |
| 0.5 | 0 | 1.0 | 66.5% | 80.5% | 79.5% | 84.5% | 77.8% | 74.7% to 80.5% |
| 0.7 | 0 | 1.0 | 66.5% | 79.0% | 80.0% | 81.5% | 76.8% | 73.7% to 79.5% |
| 0.3 | 0.5 | 1.0 | 65.5% | 79.5% | 76.0% | 83.5% | 76.1% | 73.1% to 78.9% |
| 0.5 | 0.5 | 1.0 | 65.0% | 79.0% | 78.0% | 82.5% | 76.1% | 73.1% to 78.9% |
| 0.3 | 0 | 1.0 | 65.5% | 78.5% | 78.0% | 81.5% | 75.9% | 72.8% to 78.7% |
| 0.7 | 0.5 | 1.0 | 66.5% | 77.0% | 76.5% | 79.5% | 74.9% | 71.8% to 77.8% |
| 0.5 | 0 | 0.5 | 61.0% | 75.0% | 77.0% | 79.5% | 73.1% | 69.9% to 76.1% |
| 1.0 | 0 | 1.0 | 63.0% | 77.0% | 77.0% | 74.0% | 72.8% | 69.6% to 75.7% |
| 1.0 | 0.5 | 1.0 | 61.0% | 73.0% | 76.5% | 75.0% | 71.4% | 68.1% to 74.4% |

No illegal choice and no thrown-away knock-out in any of the 8,000 games.

**Frozen setting, by the pre-written rule (highest pooled win rate): γ 0.5, `a_floor` 0, `utility_scale` 1.5.** It leads the
defaults by 5 games in 800 (78.4% against 77.8%), well inside the noise, so some of that lead is luck; the rule was written before
the results and is applied as written. Halving the status-move values (0.5) is clearly worse, so status moves earn their place.

**Why I stopped: the amended mark E3.2 is close to a coin flip in Gen 1, whatever the policy does.** To see where the rates sit I
played the two against-random matches on the *tuning* indices with the frozen setting (a dry run: nothing was tuned on it):

| Gen | Policy against random | Max-damage against random | Difference | Interval at 200 games each |
|-----|-----------------------|---------------------------|------------|-----------------------------|
| 1 | 88.5% | 87.5% | +1.0 | −5.5 to +7.5 |
| 2 | 94.0% | 91.5% | +2.5 | −2.7 to +7.8 |
| 3 | 94.5% | 86.0% | +8.5 | +2.7 to +14.5 |
| 4 | 96.5% | 88.0% | +8.5 | +3.3 to +14.0 |

At the evaluation's size (1,000 games per player per generation) and rates near 88%, the Newcombe interval reaches about 2.9
points each way. A lower end above −2 therefore needs an observed lead of about **+0.9 points or more**. If the true Gen 1 lead is
about +1, as the dry run suggests, Gen 1 passes roughly half the time by chance alone, and two policies that are exactly level
would fail it most of the time. That is the same flaw 13-A1 set out to remove, in a milder form: the mark tests the sample size,
not the policy. And the evaluation indices can be used only once (13-A4).

Everything else in the dry run would pass: against max-damage 78.4% pooled, 0 illegal, 0 errors, 0 timeouts in 53,020
decisions, p95 26 ms, 0 quarantined pairs.

**Decision needed (a pass mark, so outside the autonomy envelope). Options, with my recommendation first:**

| # | Option | Effect |
|---|--------|--------|
| P1 (recommended) | Judge E3.2 **pooled** over the four generations at the −2-point margin (4,000 games each: the interval is about 1.4 points each way, so level policies pass), and per generation only require the lower end above **−5 points** | The mark can tell "level" from "clearly behind"; a generation that is really 5 points worse still fails |
| P2 | Keep the per-generation −2 margin and play the two against-random matches with **2,000 pairs** per generation (indices 2,000,000–2,001,999 for those two matches only) | Interval about 2 points each way; level policies still fail about half the time, so this alone does not fix it |
| P3 | Run it as amended | Gen 1, and possibly Gen 2, pass or fail largely by chance; a fail burns the evaluation range |

After the ruling: one command per match runs the evaluation (about 12,000 games, under two hours), then the report and verdict.

#### Reviewer ruling 13-A6 on E3.2 (2026-10-13): **P1 adopted.** Run the evaluation.

**The arithmetic is confirmed.** At about 88% and 1,000 games per player, the Newcombe half-width is ±2.85 points per generation, so the
per-generation −2 margin needs an observed lead of about +0.9 points. That makes it a coin flip for a policy that is truly about +1 ahead.
Pooled over four gens (4,000 games each), the half-width is about ±1.3 points. Stopping to ask was right: this is the second
pass-mark flaw that measurement caught before the seeds were spent. For future pass marks, the reviewer will do the
power check *before* writing the mark.

**The final E3.2 (replaces 13-A1's per-generation form):**
- **Pooled:** the policy's win rate against random minus max-damage's win rate against random, with each generation weighted equally
  (equal n). The 95% Newcombe interval must have a lower end **above −2 points**.
- **Per generation (a safety net):** each generation's interval must have a lower end **above −5 points**, so a clearly worse
  generation still fails. At ±2.85 (standard error about 1.45 points) the cut is an observed lead below −2.15. A truly level generation passes about 93% of the time; one truly +1 ahead (the Gen 1 dry run) passes about 98.5%; one truly 5 points behind fails about 97.5% of the time.
- **Supplementary only, not part of the verdict:** if the two against-random matches use the same game indices (same teams, same battle
  seed), also report a paired analysis by index (discordant counts and the paired difference interval). It shows the real precision,
  but the verdict uses the pre-registered unpaired rule above.

E3.1 (head to head against max-damage: pooled lower bound above 50%, no gen below 45%) and E3.3 (health, including the
0.5% quarantine mark) are unchanged. 13-A4 (burned seeds) still applies.

**Other points from the checkpoint:**
- **13-A2:** done for all eight settings, and 1,600 of 1,600 Gen 1 games had the same winner. The tuning table is clean.
- **The frozen setting** is `utility_scale` 1.5, chosen by the pre-written rule. It leads the defaults by only 5 games in 800, which is noise.
  It's correct to apply the rule as written. 1.5 sits at the edge of the grid, so **don't** extend tuning now. Note "`utility_scale` > 1.5 untested" in
  the v1 backlog.
- **The dry-run numbers were on tuning indices,** so they are not evidence for the verdict. Don't quote them as results.

**Go:** run the evaluation on indices 2,000,000–2,000,499 with the frozen setting, then report per Order 13 step 4 with the E3 verdict
under 13-A6, and **stop** before `cp-06`.

### ⤷ SUPERSEDED by batch 9 (14-lite) — Order 14: hygiene after `cp-06` is approved

1. **Repository location (the user does this, with Claude Code checking):** close VS Code, move the repository from OneDrive to
   `C:\dev\Poketrix`, and reopen it. The git remote is unaffected. Claude Code then confirms that `git status` is clean and `pytest` is green.
2. **Timing on AC power** from the new location. If the Gen 1 and Gen 2 calculator tests still miss 8 ms, report the medians
   and propose a limit. Don't change the limit without approval.
3. **Archive the logbook** (approved exception to "avoid new documentation", because it is a move, not new content). Move the full
   write-ups of Phases 0–6 and the completed orders into `docs/history/phases-0-6.md`, unchanged. Keep this file to:
   - status at a glance and current orders;
   - a one-table **decision index** (id → one line → link to the history anchor);
   - the active orders, the advice section and the standing rules.

   Target: under 400 lines. `CLAUDE.md` points to both files.
4. **A8: a golden-decision replay test in CI.** Commit 2–3 full game transcripts per gen (both sides' streams with requests)
   and the policy's recorded choices. A pure-Python test replays them through the tracker and the advisor and asserts that the decisions are identical.
   This puts the whole decision pipeline under CI without Node or the simulator. Re-record only when the policy deliberately changes, and note it here.
5. **Dex field:** add Showdown's `selfdestruct` flag to the dex snapshot, and replace the hard-coded five-move list with it, without
   any behaviour change (the A8 test proves it).
6. **Gen 1 desync, exact detection:** check whether the pinned simulator's protocol marks a Desync Clause substitution
   (a `-message`, a `-hint` or a tag). If it does, use exact detection and stop ignoring the 187 first moves. Re-run the ground-truth
   check (it must stay at 0 false claims). If it doesn't, keep the conservative rule and record why.

### ⤷ SUPERSEDED by batch 9 — Order 15: Phase 7 design proposal, plus the v1 policy backlog

Phase 7 replaces `heuristic-0` with a learned opponent-action model (XGBoost) trained on real replay decisions.
Propose the following:
- **Data:** per-decision snapshots from the 2,000 real replays (plus more, if useful, with a polite download), keyed by
  `(battle, turn, decision_index)`. The label is attack, switch or status/utility. Features come only from information visible
  at that moment. Split by battle, never by turn, so nothing leaks between train and test.
- **Metrics against heuristic-0:** log-loss, Brier score and calibration, plus the **downstream** effect: the policy's
  win rate against max-damage with the learned model in place of heuristic-0, on a fresh evaluation range.
- **The v1 policy backlog**, each item to be judged on that fresh range:
  1. **Opponent priority in move order:** P(their best move has priority), from the posterior (Gen 4: Sucker Punch,
     ExtremeSpeed, Aqua Jet, Ice Shard, Bullet Punch, Mach Punch; in all gens: Quick Attack).
  2. Recoil and Hyper Beam's recharge cost.
  3. Set-up moves.
  4. A second, independent baseline that doesn't use our estimator, so "beats max-damage" isn't only measured against ourselves.
- **Human-play proxy:** agreement between our advice and the winning player's actual choices in real replays. It is cheap,
  it uses no new data, and it is the first signal about play against people.

## Reviewer ruling 13-A7 (2026-10-14): the Phase 6 evaluation result and health mark 3e

**Verdict on the evaluation as played (11,994 games, reserved indices, frozen setting):**

| Mark | Requirement | Result | |
|------|-------------|--------|--|
| E3.1 | Against max-damage: pooled lower bound above 50%, no gen below 45% | 77.4% (76.0–78.6); lowest gen is Gen 1 at 68.7% | **Pass** |
| E3.2 pooled | Policy minus max-damage, both against random: lower bound above −2 points | +6.0 (+4.7 to +7.3) | **Pass** |
| E3.2 per gen | Lower bound above −5 points | Gen 1 +0.5, Gens 2–4 +6 to +10 | **Pass** |
| E3.3 | 0 illegal, 0 errors, timeouts under 1%, p95 under 250 ms | 0 / 0 / 0.01% / 45 ms | **Pass** |
| E3.3, quarantine | At most 0.5% of pairs per gen | Gen 4 policy v max-damage: 3 of 500 = **0.60%** | **Missed** |

The policy result is real and robust. Even counting all 6 dropped games as losses gives 79.8% in Gen 4 and 77.3% pooled. The
regression from tuning (78.4%) to evaluation (77.4%) is about 1 point, as expected.

**Ruling: S1, with a determinism safeguard.** The two orders conflicted, and that's the reviewer's drafting error. 13-R's
"health mark missed → stop, no re-runs" did not exempt **13-A3**, which was written earlier for exactly this case ("fix, and re-run
that generation on its same indices"). The specific, pre-registered rule governs. 13-A4 (burned seeds) still governs *policy*
failures, and this is not one. S2 would spend Phase 7's fresh range on a tracker bug. S3 would bend a pre-registered mark after
seeing results. Neither is acceptable.

### Order 13-A7 (no stop if every check passes)
On `task/06-orchestrator`:
1. **Commit or stash the uncommitted golden-test work first**, so the fix lands in a clean, separate commit.
2. **Fix the Ditto bug in the tracker:** a transformed Ditto must keep its **own** set identity. A species with only one
   ability must not cause Ditto's set to be read as the target's. Use the 3 quarantined games as regression tests. Also look for the same
   pattern in Gens 1–3 (Ditto exists from Gen 1, and Mew can Transform), and test it. The ground-truth validation must stay at 0 false claims.
   This is a tracker fix inside the autonomy envelope. The **policy is unchanged.**
3. **Re-run only Gen 4, policy v max-damage, on indices 2,000,000–2,000,499,** with the frozen setting.
4. **Determinism check, required:** the 497 pairs that were *not* quarantined must reproduce **exactly** the same outcomes, winner by winner,
   as the first run. That proves the fix touched only the broken games, and that the re-run can't have changed the
   result in any other way. If even one non-quarantined pair differs: **stop** and report.
5. Re-judge 3e for that cell. If quarantine is at most 0.5% (it is expected to be 0), the full E3 verdict is **PASS**. Then follow
   13-R's pass path: A4 README table → record the golden games → green `pytest` → merge `--no-ff` → tag `cp-06` → push → log.
6. **Tell the user you are idle** so they can move the repository, then continue with 14-lite and Phase 7 as written.

#### Order 13-A7 result (2026-10-14): **E3 PASSES. `cp-06` merged and tagged.**

| Step | Result |
|------|--------|
| Fix (`e8c6ac0`) | While a Pokémon is transformed, a `-formechange` line is the copy's look and no longer changes its species. Tested for Arceus and Giratina (Gen 4) and Deoxys (Gen 3); a real forme change (Castform) still works. Gens 1–2 have no forme-change lines. The three quarantined games are a fixture (`tests/fixtures/quarantined_games.json.gz`) and now read through from both players' logs. Ground truth: still 0 false claims on 2,000 battles |
| Re-run | Gen 4, policy v max-damage, indices 2,000,000–2,000,499, frozen setting, into its own file; the first run's file is untouched |
| **Determinism check** | **994 of 994 games of the 497 untouched pairs are identical: same winner, same number of turns, same number of decisions** |
| The three pairs | 2000063: won 1 of 2; 2000252: won 2; 2000350: won 2 |
| Quarantine | 0 pairs in every generation and match |

Final figures, with Gen 4 of policy v max-damage from the re-run and everything else as first played:

| Match | Gen 1 | Gen 2 | Gen 3 | Gen 4 | Pooled | 95% interval |
|-------|-------|-------|-------|-------|--------|--------------|
| Policy v max-damage | 68.7% | 79.5% | 81.0% | 80.3% (803 of 1,000) | **77.4%** (3,095 of 4,000) | 76.1–78.6% |
| Policy v random | 84.7% | 95.2% | 97.3% | 96.6% | 93.5% | 92.6–94.2% |
| Max-damage v random | 84.2% | 88.9% | 89.9% | 86.8% | 87.5% | 86.4–88.4% |

All E3 marks pass: 1a (lower bound 76.1%), 1b (lowest generation 68.7%), 2a (+6.0, interval +4.7 to +7.3), 2b (all four), 3a
(0 illegal), 3b (0 errors in 259,873 decisions), 3c (28 timeouts), 3d (p95 45 ms), 3e (0 quarantined). The report is saved at
`%LOCALAPPDATA%\poketrix-cache\arena\eval_report_final.txt`.

Pass path carried out:
- **A4:** the README has the results table and the headline sentence, with what the result does and does not show.
- **The evaluated setting is now the code's default** (`PolicySettings.utility_scale` 1.5; γ and `a_floor` were already the
  defaults), so what ships is what was measured.
- **A8 (Order 14-lite), done here because 13-A7 asks for it:** `tests/fixtures/golden_decisions.json.gz` holds two games per
  generation (policy against max-damage, both sides' streams, 519 decisions, 48 KB). `tests/test_golden_decisions.py` replays them
  in plain Python and requires every choice of both players to come out as recorded. Re-record with
  `python -m poketrix.arena record`, only when the policy changes on purpose. The harness's line handling moved into
  `read_chunk`, shared by live play and the replay.
- 910 tests pass; `ruff` clean; merged `--no-ff`, tagged `cp-06`, pushed.

### Notes for v2 (no action now)
- **Self-destruct advice:** about 1 per 12 games, and about half of those with a KO chance under 50%. Audit it in v2, and consider requiring a
  KO chance threshold or "last Pokémon" for self-faint moves.
- **Gen 1** is the weakest generation (68.7% against max-damage, about level against random). The Gen 1 diagnosis stays v2 item 0.

## Reviewer note: `cp-06` verified (2026-10-14)

**13-A7 was carried out exactly as ruled.**
- The root cause was a forme-change line while transformed (not abilities), and it is now fixed for Arceus, Giratina and Deoxys, with the 3 games as fixtures.
- Ground truth is still at 0 false claims.
- **Determinism: 994 of 994 untouched games are identical in winner, turn count and decision count.**
- The 3 pairs now play, winning 5 of 6 games.

E3 **passes on every mark, with no quarantine anywhere.** Making the evaluated setting the code default (`utility_scale` 1.5) is correct:
what ships is what was measured. A8 (the golden-decision test, 8 games, 519 decisions) is in `cp-06`. The reviewer checked `main` = `origin/main` =
`1446c1d`, tagged `cp-06`. **Phase 6 is complete.**

The next stop is Phase 7's results (Order 15). Order 14-lite is now just: the user's move, then recreate `.venv` and confirm green.

## ▶ ACTIVE — Orders for Claude Code, batch 9 (written 2026-10-14 while the evaluation runs)

Context: the user wants a demonstrable v1 by **2026-10-16**. To avoid waiting on reviews, the designs below are **decided in
advance**. Claude Code builds directly and stops only where marked, or when something contradicts these specs (as with F1). The
autonomy envelope still applies.

### Order 13-R: what to do when the evaluation finishes
Write the full report into this file first (per Order 13 step 4, with the E3 verdict under 13-A6). Then:

- **PASS** (E3.1, E3.2 and E3.3 all met, 0 illegal choices, quarantine ≤ 0.5% per gen, nothing anomalous):
  1. Write A4 (the README results table: the three match-ups per gen and pooled, with intervals, plus the headline sentence).
  2. Merge `--no-ff` to `main`, tag `cp-06`, push, and log it. **Pre-approved. No stop.**
  3. Update the explainer facts in the README only. The reviewer updates the claude.ai docs.
  4. Continue with Order 14-lite.
- **FAIL, or anything anomalous** (an unexplained result, a health mark missed, a quarantine spike): **stop** and report. No
  changes, no re-runs. 13-A4 applies: the evaluation range is used up.

#### Order 13-R result (2026-10-14): **every win-rate mark passes; E3 fails on one health mark (3e). Stopped. Nothing changed, nothing re-run.**

The one evaluation run: indices 2,000,000–2,000,499, frozen setting (γ 0.5, `a_floor` 0, `utility_scale` 1.5), code at `8ba9888`,
simulator commit `942cda7`, 11,994 games scored. The full report is saved at `%LOCALAPPDATA%\poketrix-cache\arena\eval_report.txt`.

| Match | Gen | Games | Win rate | 95% interval (games) | Pair score (bootstrap) | Pairs 2–0 / split / 0–2 | Avg turns |
|-------|-----|-------|----------|----------------------|------------------------|--------------------------|-----------|
| **Policy v max-damage** | 1 | 1,000 | 68.7% | 65.8–71.5% | 66.0–71.4% | 226 / 235 / 39 | 26.1 |
| | 2 | 1,000 | 79.5% | 76.9–81.9% | 77.0–81.9% | 314 / 167 / 19 | 46.9 |
| | 3 | 1,000 | 81.0% | 78.5–83.3% | 78.6–83.4% | 324 / 162 / 14 | 26.6 |
| | 4 | 994 | 80.3% | 77.7–82.6% | 77.9–82.6% | 312 / 174 / 11 | 22.4 |
| | **all** | 3,994 | **77.4%** | **76.0–78.6%** | 76.1–78.6% | 1,176 / 738 / 83 | 30.5 |
| Policy v random | 1 | 1,000 | 84.7% | 82.3–86.8% | 82.5–86.9% | 356 / 135 / 9 | 29.0 |
| | 2 | 1,000 | 95.2% | 93.7–96.4% | 93.9–96.4% | 452 / 48 / 0 | 42.1 |
| | 3 | 1,000 | 97.3% | 96.1–98.1% | 96.3–98.2% | 473 / 27 / 0 | 26.1 |
| | 4 | 1,000 | 96.6% | 95.3–97.6% | 95.5–97.7% | 466 / 34 / 0 | 23.8 |
| | all | 4,000 | 93.5% | 92.6–94.2% | 92.7–94.2% | 1,747 / 244 / 9 | 30.2 |
| Max-damage v random | 1 | 1,000 | 84.2% | 81.8–86.3% | 82.0–86.3% | 349 / 144 / 7 | 23.0 |
| | 2 | 1,000 | 88.9% | 86.8–90.7% | 86.9–90.8% | 394 / 101 / 5 | 40.5 |
| | 3 | 1,000 | 89.9% | 87.9–91.6% | 88.1–91.7% | 401 / 97 / 2 | 27.6 |
| | 4 | 1,000 | 86.8% | 84.6–88.8% | 84.7–88.8% | 376 / 116 / 8 | 23.3 |
| | all | 4,000 | 87.5% | 86.4–88.4% | 86.5–88.5% | 1,520 / 458 / 22 | 28.6 |

Tuning predicted 78.4% against max-damage; the fresh seeds give 77.4%. The pair-level intervals are no wider than the game-level
ones, so the pairing did its job.

| E3 mark (13-A6) | Result | Numbers |
|-----------------|--------|---------|
| 1a. Against max-damage, pooled lower bound above 50% | **Pass** | 3,090 of 3,994 = 77.4%, lower bound 76.0% |
| 1b. No generation below 45% | **Pass** | lowest is Gen 1 at 68.7% |
| 2a. Against random, pooled: not more than 2 points behind max-damage | **Pass** | 93.5% against 87.5%: +6.0 (+4.7 to +7.3) |
| 2b. Per generation: not more than 5 points behind | **Pass**, all four | Gen 1 +0.5 (−2.7 to +3.7); Gen 2 +6.3; Gen 3 +7.4; Gen 4 +9.8 |
| 3a. No illegal choice | **Pass** | 0 |
| 3b. No decision ended in `error` | **Pass** | 0 of 259,697 |
| 3c. `timeout` under 1% of decisions | **Pass** | 29 (0.01%) |
| 3d. p95 latency under 250 ms | **Pass** | 45 ms (three matches ran side by side; the laptop was on mains for most of the run) |
| 3e. At most 0.5% of a generation's pairs quarantined | **FAIL** | Gen 4, policy v max-damage: **3 of 500 pairs = 0.60%**. Every other generation and match: 0 |

**The three quarantined pairs are one bug.** In Gen 4, Ditto transforms into a Pokémon whose species has a single ability (Arceus
twice, Giratina once). The log then says `|-formechange|p1a: Ditto|Arceus|`, the tracker takes Ditto's species to be Arceus, and
the snapshot carries Ditto's own set (ability Limber) under that species, which the schema rejects ("Arceus cannot have ability
limber"). The Castform rule of `cp-05` (a forme change makes the set that forme's) is applied to a transformation, where it does not
belong. It never appeared in the 2,000-battle ground truth, in tuning (8,000 games) or in the other 11,500 evaluation games. The
seeds, both sides' logs and the tracebacks are in `data/raw/quarantine/` (indices 2000063, 2000252, 2000350).

**Could the six dropped games change a win-rate mark? No.** Counting all six as losses: Gen 4 would be 798 of 1,000 = 79.8% and
the pooled figure 3,090 of 4,000 = 77.3%, with a lower bound still near 76%.

Guardrails on the evaluation games:

| | Policy v max-damage | Policy v random |
|---|---|---|
| Voluntary switches (share of decisions) | 11.1% | 13.0% |
| Thrown-away knock-outs | 0 | 0 |
| Trap re-asks (R15), all legitimate | 36 | 43 |
| `fallback` decisions | 2.75% | 2.51% |
| Self-KO move advised | 319 (0.24% of decisions, 1 game in 12) | 288 (0.23%) |
| … of which the knock-out chance was 90% or more | 154 | 99 |
| … of which it was under 50% | 142 | 152 |

The self-KO figure is worth a look in v2: about half the time Explosion is advised with a knock-out chance under 50%, which
means every other option scored below "lose this Pokémon for some damage". It is rare, but it is not the "mostly a guaranteed
trade" the guardrail hoped for.

Supplementary, not part of the verdict: the against-random games compared game by game (same teams and seed), policy minus
max-damage: Gen 1 +0.5 (−2.5 to +3.5), Gen 2 +6.3 (+4.0 to +8.6), Gen 3 +7.4 (+5.4 to +9.4), Gen 4 +9.8 (+7.5 to +12.1), pooled
+6.0 (+4.8 to +7.2). The policy won 437 games max-damage lost; the reverse happened 197 times.

**Verdict by the letter: E3 fails, on 3e alone.** I stopped as 13-R says: no fix, no re-run, `cp-06` not tagged, README untouched.

**The two orders disagree on what comes next, so this needs a ruling:**

| # | Option | What it means |
|---|--------|---------------|
| S1 (recommended) | Follow 13-A3 as written: fix the Ditto bug with the three quarantined games as regression tests, then **re-run Gen 4 of policy v max-damage on its same indices** and judge 3e again. Nothing else is replayed | This is the remedy 13-A3 names for exactly this case. The policy is untouched; only the tracker stops rejecting a legal game. 498 of the 500 pairs should replay move for move; the three pairs get played |
| S2 | Treat the range as burned (13-A4): fix the bug, then run the whole evaluation again on 3,000,000–3,000,499 | Cleanest, costs about an hour, and uses the range Order 15 had set aside for its downstream check |
| S3 | Accept the result with 3e recorded as missed by 0.1 point, on the worst-case arithmetic above | No more games; the health mark is waived once, in writing |

Not committed, in the working tree: the golden-decision test and its recorder (Order 14-lite A8), written while the run was
going. They change no behaviour of the evaluated code, and they stay uncommitted until this is ruled.

### Order 14-lite: hygiene that v1 needs (no stop)
1. **The user** moves the repository out of OneDrive to `C:\dev\Poketrix` when convenient. Ask them once, then confirm a clean
   `git status` and a green `pytest` afterwards. If they don't move it, carry on regardless.
2. **A8, the golden-decision replay test in CI** (2 games per gen). This protects the policy during Phases 7–8, so do it now.
3. **Deferred to v2:** logbook archiving, the dex `selfdestruct` field, exact Gen 1 desync detection, and timing on AC. Note them in the v2 list.

### Order 15: Phase 7, the learned opponent-action model. **Build directly. STOP with the results.**
Branch: `task/07-opponent-model`.

**Data**
- Source: the 2,000 real replays already downloaded. **Exclude** custom-rule or tournament games (those flagged in Order 8) and any game the parser
  refuses. The use of more downloads is pre-authorised (polite, same script, up to +500 per gen), but only if a gen has fewer
  than 3,000 labelled decisions after the exclusions.
- Rows: one per **voluntary decision** per side (in spectator view both players count), from snapshots taken **before** the decision.
  - Exclude forced switches.
  - Exclude turns with no choice: recharge, Bide or Thrash/Outrage/Petal Dance lock, Rollout or Uproar lock, Gen 1 partial-trap lock, Sky Attack/Solar Beam/Skull Bash second turns.
  - **Label:** `attack` (a damaging move), `utility` (a status or non-damaging move), or `switch`.
- **Features, visible at decision time only,** computed from that side's view of its opponent, using our own engines:
  - generation and turn;
  - both actives' HP fractions, statuses, sums of their boosts, and alive and healthy-bench counts;
  - our engine's quantities from the deciding side's point of view: its best KO chance and expected damage on the target, the target's
    `p_ko_best_move` and expected damage against it, P(it moves first);
  - hazards on its side, and whether its revealed moves include a status move;
  - ladder rating where the replay states it (else missing).

  **No future information:** a feature may only come from lines before the decision. Add a test that recomputes the features from a truncated log and gets identical values.
- **Split by battle,** 70 / 15 / 15, stratified by gen, with seed 20261501. Nothing from a test battle is used for training or for early stopping.

**Model**
- XGBoost, multiclass (3 classes), as an **optional dependency** (`pip install -e ".[ml]"`). If it isn't installed, the stage falls back
  to `heuristic-0` with status `fallback`.
- Small search on the validation split only: depth ∈ {3, 5}, learning rate ∈ {0.05, 0.1}, early stopping on validation log-loss.
  Then **isotonic or temperature calibration** fitted on validation.
- Saved as XGBoost's JSON in `data/models/opponent-xgb-1.json`, with a manifest (data ids, split seed, features, metrics).
  `ActionPrediction.model_version = "xgb-1"`. Inference must stay under 2 ms per decision.

**Metrics, on the test split, per gen and pooled, against two baselines** (the per-gen base rates, and `heuristic-0`):
- log-loss, Brier score, accuracy, and a 10-bin reliability table with expected calibration error (ECE);
- a battle-level bootstrap 95% interval for the log-loss improvement (resampling battles, not rows).

**Pass marks for Phase 7** (power check done by the reviewer: 15% of about 2,000 battles is about 300 test battles, roughly 10,000 decisions; with the
battle-level bootstrap, a pooled log-loss gain of about 0.01–0.02 is detectable, while per-gen estimates are noisier, so per gen is point-estimate only):
1. The pooled log-loss improvement over **both** baselines has a bootstrap lower bound above 0.
2. Pooled ECE ≤ 0.03 after calibration.
3. Per gen: log-loss is not worse than the base-rate baseline (the point estimate).

**Downstream check, as a sanity check only, not the pass mark.** Our simulator opponents are bots, and a model of *humans*
can make bot games worse even when it predicts people better. So: the policy with `xgb-1` against max-damage, 200 pairs per gen,
on a **fresh** range 3,000,000–3,000,199, compared with `heuristic-0` on the same indices.
- Report the paired difference.
- Flag it (don't fail it) if the pooled lower bound is below −3 points.
- **Write the range here before running.**

**Then stop with:** the metric tables, the calibration table, the downstream result, and the 10 most important features. The reviewer
decides whether the `xgb-1` model becomes the default.

**Downstream range, written before any game was played (2026-10-15): indices 3,000,000–3,000,199, Gens 1–4, policy v max-damage,
once with `--opponent heuristic-0` and once with `--opponent xgb-1`, same code (`a4c3e63`), same simulator. Used once.**

#### Order 15 result (2026-10-15): **all three pass marks met; the downstream sanity check is flagged** (pooled −1.6 points, lower bound −3.5).

**What was built** (`src/poketrix/opponent/`, on `task/07-opponent-model`):
- `features.py`: `DecisionView`, 20 features. Stage 5 builds it from stages 2–4 (`stages.opponent_view`) and asks an injected
  `OpponentModel` (`TurnAdvisor(opponent_model=...)`). The default is still `heuristic-0`, numerically unchanged: the golden decisions pass.
- `models.py`: `Heuristic` (heuristic-0, now a function of the view) and `XgbModel`. If NumPy (`[ml]`) or the saved files are missing,
  it raises `ModelUnavailable` and stage 5 answers with heuristic-0 and status `fallback`.
- `dataset.py`, `training.py`, `evaluation.py`: development tools (`python -m poketrix.opponent.<name>`). The dataset is
  `data/raw/opponent/decisions.jsonl` (git-ignored); the model is `data/models/opponent-xgb-1.json` plus `.manifest.json`, which holds
  the battle ids per split, the seed, the features, the search, the temperature and the test metrics.
- Arena: `run ... --opponent {heuristic-0,xgb-1}`. The report compares two settings of one match game by game.
- `tests/test_opponent.py` (14 tests): labels, the leakage test (the log cut right after the turn line gives identical features on 4
  fixture battles), the split, fallback, NumPy trees equal to XGBoost's margins, latency, metric arithmetic. 923 tests pass; `ruff` is clean.

**Data.** Only ladder games (a bare `|rated|` line): 1,273 of the 2,000 replays; 727 tournament or challenge games are left out, and 18
more have no decision. That leaves 1,255 battles and 71,036 decisions. Every gen is far above 3,000, so nothing more was downloaded.
The test split is **188 battles** (the power check assumed about 300) with 11,275 decisions (it assumed about 10,000).

| Gen | Battles (train / valid / test) | Decisions | attack | utility | switch | stay |
|-----|-------------------------------|-----------|--------|---------|--------|------|
| 1 | 259 / 56 / 55 | 19,621 | 51% | 16% | 14% | 18% |
| 2 | 93 / 20 / 20 | 10,681 | 44% | 22% | 17% | 16% |
| 3 | 275 / 59 / 59 | 23,718 | 45% | 25% | 20% | 10% |
| 4 | 251 / 54 / 54 | 17,016 | 47% | 23% | 18% | 12% |

**Two departures from the spec, both ruled by the user on 2026-10-15 before any test metric was seen:**
1. **Hidden stays are kept** as a 4th label, `stay`. These are 9,627 decisions where the Pokémon fainted before acting or could not move
   (asleep, frozen, fully paralysed, flinched, infatuated). It chose a move; the log doesn't show which. Dropping them inflated the switch
   rate exactly where it matters: when the decider was about to be knocked out (≥ 90%), 27.3% in the kept rows against 20.6% with them,
   and when asleep, 62.6% against 22.0%. Training splits each one into attack and utility by its gen's visible shares (0.77 / 0.66 / 0.64
   / 0.67 attack). Scoring: −log(P(attack) + P(utility)) in log-loss. Brier, accuracy and the top-choice ECE use the visible rows only.
   The switch reliability uses every row.
2. **No rating feature.** Every ladder game states the ratings, while the model runs where none is known (bots, unrated games). With rating
   kept and then hidden on the test split, Gen 2 log-loss was 0.897, worse than its base rates (0.866). The model was retrained without it
   (same grid, seed and split), **so the test split has been read twice**: once with rating, once without.

Also excluded, as the spec lists: locked or two-turn continuations (tagged `[from] lockedmove`, or the same locking move again after
staying in, since Gen 2 logs don't tag Rollout or Solar Beam), recharge, Truant, being dragged out, and positions the engine refuses
(transformed, no posterior).

**Model.** XGBoost, multiclass. Validation search: depth 3 / rate 0.05 → 1,375 trees, 0.7223; 3 / 0.1 → 679, 0.7225;
**5 / 0.05 → 485, 0.7182 (chosen)**; 5 / 0.1 → 278, 0.7201. Temperature 0.969 (validation 0.7182 → 0.7180). Inference walks the saved
trees with NumPy (equal to XGBoost's margins within 1e-4, tested): **0.28 ms median, 0.60 ms p95** per prediction (XGBoost's own call was
1.2 / 3.9 ms, over the 2 ms budget).

**Test split, per gen and pooled** (log-loss on every row; Brier, accuracy and ECE on the visible rows):

| Gen | Predictor | Rows | Log-loss | Brier | Accuracy | ECE (top choice) | ECE (switch) |
|---|---|---|---|---|---|---|---|
| 1 | base rates | 3,219 | 0.7843 | 0.5455 | 61.8% | 0.0375 | 0.0152 |
| | heuristic-0 | | 0.7762 | 0.5295 | 55.5% | 0.0660 | 0.0987 |
| | **xgb-1** | | **0.6138** | 0.4237 | 68.8% | 0.0306 | 0.0104 |
| 2 | base rates | 2,112 | 0.8663 | 0.5893 | 56.4% | 0.0228 | 0.0099 |
| | heuristic-0 | | 0.9220 | 0.6355 | 52.8% | 0.1332 | 0.0976 |
| | **xgb-1** | | **0.8236** | 0.5370 | 60.3% | 0.0495 | 0.0773 |
| 3 | base rates | 3,794 | 0.9743 | 0.6366 | 47.6% | 0.0387 | 0.0072 |
| | heuristic-0 | | 0.9625 | 0.6214 | 47.9% | 0.0854 | 0.1181 |
| | **xgb-1** | | **0.8169** | 0.5270 | 59.3% | 0.0219 | 0.0187 |
| 4 | base rates | 2,150 | 0.9019 | 0.5912 | 56.3% | 0.0156 | 0.0064 |
| | heuristic-0 | | 0.8708 | 0.5664 | 53.2% | 0.0742 | 0.1112 |
| | **xgb-1** | | **0.7320** | 0.4736 | 63.8% | 0.0112 | 0.0199 |
| all | base rates | 11,275 | 0.8860 | 0.5945 | 54.7% | 0.0165 | 0.0025 |
| | heuristic-0 | | 0.8842 | 0.5885 | 51.9% | 0.0577 | 0.1074 |
| | **xgb-1** | | **0.7440** | 0.4906 | 62.9% | **0.0157** | 0.0147 |

Log-loss improvement of xgb-1, battle bootstrap (2,000 resamples, seed 20261502):

| Gen | Over base rates | Over heuristic-0 |
|---|---|---|
| 1 | +0.171 (+0.150 to +0.190) | +0.162 (+0.137 to +0.188) |
| 2 | +0.043 (−0.081 to +0.159) | +0.098 (−0.013 to +0.211) |
| 3 | +0.157 (+0.136 to +0.179) | +0.146 (+0.117 to +0.174) |
| 4 | +0.170 (+0.147 to +0.193) | +0.139 (+0.114 to +0.162) |
| **all** | **+0.142 (+0.102 to +0.170)** | **+0.140 (+0.107 to +0.166)** |

Reliability of xgb-1 on the pooled test split:

| Bin | Top choice: rows | predicted | observed | P(switch): rows | predicted | observed |
|---|---|---|---|---|---|---|
| 0.0–0.1 | | | | 4,265 | 0.047 | 0.051 |
| 0.1–0.2 | | | | 3,093 | 0.145 | 0.141 |
| 0.2–0.3 | | | | 1,727 | 0.244 | 0.239 |
| 0.3–0.4 | 326 | 0.375 | 0.383 | 930 | 0.345 | 0.308 |
| 0.4–0.5 | 1,842 | 0.457 | 0.462 | 563 | 0.445 | 0.442 |
| 0.5–0.6 | 2,235 | 0.550 | 0.549 | 305 | 0.546 | 0.561 |
| 0.6–0.7 | 1,866 | 0.647 | 0.648 | 193 | 0.643 | 0.632 |
| 0.7–0.8 | 1,503 | 0.748 | 0.703 | 86 | 0.743 | 0.523 |
| 0.8–0.9 | 1,281 | 0.849 | 0.816 | 69 | 0.849 | 0.348 |
| 0.9–1.0 | 665 | 0.939 | 0.899 | 44 | 0.949 | 0.273 |

| Pass mark | Result |
|---|---|
| 1. Pooled log-loss gain over **both** baselines, bootstrap lower bound > 0 | **Pass**: +0.102 over base rates, +0.107 over heuristic-0 |
| 2. Pooled ECE ≤ 0.03 after calibration | **Pass**: 0.0157 (top choice); 0.0147 for P(switch) |
| 3. Per gen, log-loss not worse than base rates | **Pass**: 0.614 < 0.784; 0.824 < 0.866; 0.817 < 0.974; 0.732 < 0.902 |

**Downstream check (2026-10-15), indices 3,000,000–3,000,199, policy v max-damage, 1,600 games per model, 0 quarantined, 0 illegal,
0 errors: ⚑ FLAGGED. The pooled lower bound, −3.5 points, is below −3.** This is a sanity check, not a pass mark.

| Gen | heuristic-0 | xgb-1 | Only xgb-1 won / only heuristic-0 won | Paired difference (95%) |
|---|---|---|---|---|
| 1 | 65.2% | 59.0% | 21 / 46 | **−6.2 (−10.2 to −2.3)** |
| 2 | 80.2% | 79.8% | 33 / 35 | −0.5 (−4.5 to +3.5) |
| 3 | 78.8% | 81.2% | 32 / 22 | +2.5 (−1.1 to +6.1) |
| 4 | 84.5% | 82.2% | 18 / 27 | −2.2 (−5.5 to +1.0) |
| **all** | **77.2%** | **75.6%** | 104 / 130 | **−1.6 (−3.5 to +0.2)** |

Other differences with xgb-1: self-KO moves advised 198 against 125 (Gen 1: 79 against 53; Gen 2: 62 against 34); voluntary switches
13.0% against 12.7%; p95 latency 49.7 ms against 48.1 ms; `fallback` 2.62% against 2.71%. The loss is concentrated in Gen 1, where
xgb-1 is the best predictor of people (log-loss 0.614 against 0.776). This is the case the spec warned about: a better model of humans
playing against a bot. The policy only reads `p_attack` (the `a` in its formula), and xgb-1's `a` is calibrated on ladder players, not on
max-damage, which attacks every turn. **Recommendation: keep heuristic-0 as the turn engine's default; ship xgb-1 for the overlay's
opponent read (human opponents), and judge it there.** The reviewer decides.

Ten most important features (total gain): `alive` 14.5, `damaging_share` 13.8, `best_share` 10.2, `boosts` 7.4, `generation` 7.1,
`moves_first` 7.0, `best_ko` 6.7, `target_boosts` 6.6, `target_status` 5.8, `target_best_share` 4.4.

**Known limits.**
- Gen 2 is the weak spot: only 93 training battles, its gain interval crosses 0, and switch ECE is 0.077.
- P(switch) above 0.7 is overconfident: 199 rows predicted 0.85 on average, observed 0.40. The top choice and the pooled ECE are fine.
- `damaging_share` (posterior share of damaging moves) is a feature the spec did not list. Heuristic-0 needs it, so every row must carry it
  for heuristic-0 to be scored. It only uses what is visible at decision time.
- Training rows give the decider's opponent its most likely set (a spectator log shows neither set). In a game, the owner knows the real set.

## Reviewer ruling 15-R (2026-10-15): Phase 7 approved

1. **Approved:** xgb-1 meets all three pass marks. The downstream flag is the expected effect of a model of humans playing against bots.
2. **Option A:** the policy keeps heuristic-0 as its opponent model everywhere, the overlay included, because that is the version `cp-06`
   validated. xgb-1 is information only: a separate line, "Opponent tendency: switch X% · attack Y% · utility Z%", in the overlay
   and in `analyze`. Feeding xgb-1 into the policy is v2, after a human trial.
3. **P(switch) tail fix before display** (rows predicted near 0.85 switched only 40% of the time):
   - refit per-class isotonic calibration by cross-fitting (5 folds by battle) on train + validation battles only, never reading the
     test split again;
   - report the cross-fitted reliability table;
   - until the tail bins hold within ±0.10, display switch odds above 0.70 as "70%+".
4. **Writer:** any recommendation of a self-faint move must say "sacrifices your Pokémon". Text only, no policy change; the
   golden-decision test must still pass.
5. **Accepted as reported:** the NumPy tree walk, the `damaging_share` feature, the removal of the rating feature, and the test split
   being read twice (recorded).
6. **Added to the v2 list:** more Gen 2 data (93 training battles), the self-KO audit (now urgent), and xgb-1 inside the policy after a
   human trial.
7. Then merge `--no-ff`, tag `cp-07`, push, update the Current orders table, and start Order 16 as specified: xgb-1 shown as the
   "opponent tendency" line, the fair-play guard kept, and a stop with a demo (screenshots and latency numbers).

#### Ruling 15-R carried out (2026-10-15)

| Item | Done |
|---|---|
| Option A | The policy keeps heuristic-0 everywhere (unchanged default). `advisor/tendency.py` rebuilds stage 5's view from the turn's report and asks xgb-1; `analyze` prints "Opponent tendency: switch X% · attack Y% · utility Z%". No schema change |
| Tail fix | `opponent/calibration.py`: cross-fitted on train + valid only (59,761 decisions, 1,067 battles, 5 folds by battle, seed 20261503); **the test split was not read**. Two isotonic maps, one for P(switch) on every row and one for the attack share of the rest on visible rows, so the three odds always sum to 1. Stored in the manifest as `display_calibration`; `XgbModel.predict` applies them |
| Cap | **Kept: switch odds above 70% are shown as "70%+".** After the maps, the 0.8–0.9 bin is 0.826 against 0.690 (29 rows) and the 0.9–1.0 bin is 0.975 against 0.600 (5 rows) |
| Writer | A self-faint move's advice begins "<Move> sacrifices your Pokémon: <ours> faints." Golden decisions pass |
| Tests | 928 pass (+5: the tendency line and cap, the tendency equals stage 5's view, the isotonic fit, `analyze`, the sacrifice text); `ruff` is clean |

Cross-fitted reliability of P(switch), every row (out of fold; "with maps" = maps fitted on the other four folds):

| Bin | Rows before | Predicted | Observed | Rows with maps | Predicted | Observed |
|---|---|---|---|---|---|---|
| 0.0–0.1 | 22,589 | 0.048 | 0.044 | 23,335 | 0.046 | 0.046 |
| 0.1–0.2 | 17,011 | 0.146 | 0.149 | 14,768 | 0.146 | 0.146 |
| 0.2–0.3 | 9,574 | 0.245 | 0.251 | 11,113 | 0.245 | 0.243 |
| 0.3–0.4 | 5,213 | 0.345 | 0.356 | 4,777 | 0.351 | 0.353 |
| 0.4–0.5 | 2,843 | 0.444 | 0.459 | 2,754 | 0.442 | 0.441 |
| 0.5–0.6 | 1,540 | 0.544 | 0.552 | 1,851 | 0.544 | 0.541 |
| 0.6–0.7 | 760 | 0.642 | 0.638 | 880 | 0.635 | 0.637 |
| 0.7–0.8 | 175 | 0.741 | 0.754 | 249 | 0.742 | 0.727 |
| 0.8–0.9 | 52 | 0.836 | 0.788 | 29 | 0.826 | **0.690** |
| 0.9–1.0 | 4 | 0.916 | 0.500 | 5 | 0.975 | **0.600** |

ECE of P(switch): 0.0055 before, 0.0013 with the maps. Top choice on visible rows: 0.0054 before, 0.0105 with them (both well inside 0.03).

**For the reviewer:** out of fold, the trees were already close in the tail (0.836 against 0.788 over 52 rows). The test split's 0.85 → 0.40
is not reproduced on train + valid, which points to those 188 test battles rather than the model. The maps change little, and only the
two sparsest bins (34 rows in all) keep the cap on. Note: I first set a 30-row minimum per bin, which would have lifted the cap on a
29-row bin. I removed it before anything was committed: the ruling says the tail bins must hold, and the cap stays.

#### Ruling 15-R outcome (reviewer, 2026-10-15)
- **The "70%+" cap stays:** the cross-fitted 0.8–0.9 bin is 0.826 predicted against 0.690 observed.
- **The test-tail error is clustered:** those 199 test rows (0.85 predicted, 0.40 observed) come from a few battles, so a few
  switch-happy players can skew them. One more reason to keep the cap and not over-trust the tail.
- **Removing the 30-case rule was correct:** it would have lifted the cap on a technicality, and nothing was committed with it.

### Order 16: Phase 8, the overlay MVP. **Build directly. STOP with a demo.**
Branch: `task/08-overlay`. A **read-only advisor** for the user's own browser. It never sends a choice and never touches credentials.

- **Local server:** `python -m poketrix serve`, bound to **127.0.0.1 only**. One `BattleTracker` + `TurnAdvisor` per battle room.
  Endpoints: `POST /line` (room id + a batch of protocol lines) and `GET /advice?room=` (the latest `TurnReport`, rendered for the panel).
  Use the standard library or one small dependency. No authentication beyond localhost, and no data persisted except an optional debug log.
- **Browser extension (Chrome, Manifest V3):** host permissions **only** for `play.pokemonshowdown.com`,
  `replay.pokemonshowdown.com` and `http://127.0.0.1:<port>`.
  - A page script observes the Showdown client's incoming battle messages, including the user's own `|request|`, and forwards
    them to the local server in arrival order.
  - A side panel shows the headline, the top 3 scored options with their numbers, the opponent's likely set (top 2), and the threat line.
- **Fair-play guard, enforced in code:** if the battle is rated (the protocol's `|rated|` line), the panel shows
  "Poketrix is off in rated battles" and the server returns no advice. Advice is available in unrated games, challenges and replays.
  State this in the README.
- **Demo mode:** on `replay.pokemonshowdown.com`, advise from the perspective of p1 (spectator mode), so the demo needs no live game.
- **Tests:**
  - Server: unit tests for each endpoint, plus a replayed fixture battle posted line by line, giving the same advice as `analyze`.
  - Extension: a manual checklist, with screenshots in the tracker.
  - Latency from a line's arrival to the advice shown: p95 under 300 ms on the user's machine.
- **Then stop with:** the screenshots, a short screen recording (optional), the latency numbers, and the known limits.

#### Order 16 result (2026-10-15): built on `task/08-overlay`; **stopped for the demo** (screenshots come from the user's Chrome)

| Part | What |
|---|---|
| Server | `python -m poketrix serve [--port 8765] [--debug-log FILE]`: standard library only, bound to **127.0.0.1**. `POST /line` {room, lines, source} feeds the room's `BattleReader` in arrival order and advises the newest live decision at once; `GET /advice?room=[&turn=N]` returns the panel JSON. Memory only; nothing persisted except the optional debug log |
| Fair-play guard | `overlay/rooms.py`: a live battle with a `|rated|` line gets **no advice computed at all** and the panel shows "Poketrix is off in rated battles". Replays are exempt (they are over). Tested |
| Demo mode | Spectator snapshots (replays, watched battles) are advised from p1's side: `advisor/spectator.seen_as` gives p1's Pokémon their likeliest sets and offers switches to every p1 Pokémon seen alive. The dataset uses the same function; it was rebuilt **byte-identical** after the move |
| Panel | Headline and explanation, top 3 options with their numbers, the opponent's 2 likeliest sets, the threat line, the opponent tendency (xgb-1, labelled "not used by the advice", switch odds over 70% as "70%+"), the engine's time and the time from the line's arrival to the panel showing it |
| Extension | `extension/` (Manifest V3): host permissions only for `play.pokemonshowdown.com`, `replay.pokemonshowdown.com` and `http://127.0.0.1:8765`. `page.js` (page world) wraps the client's WebSocket and only listens; `relay.js` → `background.js` posts to the server, per room, in order; `replay.js` sends `<replay>.log` once and follows the on-screen turn; `panel.*` is the side panel. No credentials, no choices sent |
| Tests | `tests/test_overlay.py` (4): 127.0.0.1 only; a fixture battle posted line by line gives exactly `analyze`'s advice and tendency; the rated guard (live off, replay on); bad requests (404, 400). 932 tests pass; `ruff` is clean |

**Latency**, server share of "line arrival → advice ready" (`python -m poketrix.overlay.latency 5`: fixture player logs posted line by line over HTTP,
337 decisions, xgb-1 tendency included): **p50 10 ms, p95 23 ms, max 149 ms** (target: p95 under 300 ms). The first request after starting
takes about 230 ms (it loads the prior, the dex and the model). The browser's full figure is shown in the panel footer for every update,
and goes into the screenshots.

Checked against the running server with a real Gen 4 ladder replay: turn 5 advised from p1's side (Regirock against Gengar: "Rock Slide:
about 49% of Gengar's remaining HP", tendency "switch 21% · attack 62% · utility 17%"); the same log posted as a live battle → "Poketrix
is off in rated battles".

**Manual checklist (the user, in Chrome):**

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Load `extension/` unpacked; the server is running | The extension loads with no errors | **Pass** (2026-10-14, the user's Chrome) |
| 2 | Open a replay on `replay.pokemonshowdown.com`, click the Poketrix button | The panel shows p1's advice; the turn follows the replay as it plays | **Pass.** Gen 4 replay, turn 5: the same advice the server gave in the scripted check, with every panel part present. Screenshot: `docs/demo/replay.png` (cropped to the panel) |
| 3 | Stop the server and reload | "The Poketrix server is not running" | |
| 4 | An unrated challenge or a random battle against a friend on `play.pokemonshowdown.com` | Player-mode advice at each decision | Skipped by the user: **not tested**, see known limits |
| 5 | Watch a **rated** live battle | "Poketrix is off in rated battles" | **Bug found, fixed (`4cf79ab`), recheck pending.** The battle watched was Gen 9: the parser raised on `|gen|9` inside the request, before the `|rated|` line, and the panel said "server not running". Now `|rated|` is looked for before parsing, and an unreadable battle is answered as out of scope. Regression test added |
| 6 | Panel footer | "shown N ms after the line arrived" under 300 ms | **Pass:** engine 13 ms, shown 23 ms after the line arrived. The stale footer seen on the error message is fixed |

**Known limits.** The live-client hook (step 4) was not tested: it needs a live game, and the user skipped it in the demo. It listens to the client's
WebSocket, plain or SockJS frames. In demo mode p1's sets are the likeliest ones under the evidence, not the real ones. The replay turn
is read from the page's "Turn N" counter; if the page changes, the panel shows turn 1. The port is fixed at 8765 because the manifest
names it.

### Order 17: v1 wrap-up (no stop)
1. **README:** what Poketrix is, a quickstart (install, `analyze`, `serve` + loading the extension), the results tables (calculator oracle,
   uncloaker calibration, parser ground truth, Phase 6 evaluation, Phase 7 metrics), the fair-play note, and the known limits.
2. Tag `v1.0` on `main` once Orders 15 and 16 are approved and merged (`cp-07`, `cp-08`).
3. **The v2 list** in this file: the Gen 1 diagnosis, priority moves, recoil and recharge, set-up moves, an independent baseline, a human trial,
   `utility_scale` > 1.5, logbook archiving, the dex field, exact desync detection, timing on AC, and Gen 5+.
   Added by ruling 15-R: more Gen 2 data (93 training battles), **the self-KO audit (urgent)**, and xgb-1 inside the policy after a
   human trial.

## v2 list (consolidated 2026-10-15, Order 17)

| Area | Item | Source |
|------|------|--------|
| Policy | **Self-KO audit (urgent):** Explosion is advised with a knock-out chance under 50% about half the time; 198 cases with xgb-1 against 125 | 13-R, 15-R |
| Policy | xgb-1 inside the policy for human opponents, only after a human trial | 15-R |
| Policy | Gen 1 diagnosis (the weakest generation: 68.7% against max-damage) | 13-R |
| Policy | Opponent priority moves, recoil and recharge, set-up moves, `utility_scale` above 1.5 | 13-R |
| Data | More Gen 2 replays: 93 training battles, and its gain interval crosses 0 | 15-R |
| Opponent model | Recheck the P(switch) tail on new battles; lift the "70%+" cap only when every bin from 0.7 up holds within ±0.10 | 15-R |
| Evaluation | An independent baseline (not using Poketrix's own set estimate) and a human trial | 13-R |
| Overlay | Live-client hook tested in real games; a configurable port | Order 16 |
| Housekeeping | Logbook archiving, the dex `selfdestruct` field, exact Gen 1 desync detection, timing on AC power | 14-lite |
| Scope | Gen 5+; then the original design's knowledge layer, Nuzlocke mode and vision | design doc |

## ▶ ACTIVE — Orders for Claude Code, batch 10, "build to the end" (2026-10-14)

The user chose **build first, verify at the end.** Carry it out with no review stops; stop only for a real blocker (a broken test that
can't be fixed, data that can't be got, or a measurement that contradicts this spec).

**0. Merge the overlay now.** Merge `task/08-overlay` `--no-ff`, tag `cp-08`, push. The rated-guard live recheck is deferred to F2 (the
fix and its unit test are in). Then merge the wrap-up branch onto `main`. No `v1.0` yet.

**Safety rules for the whole batch (non-negotiable):**
- Every behaviour change goes behind a `PolicySettings` (or config) flag that **defaults to OFF**. With all flags off, behaviour stays
  identical to `cp-08`: the golden-decision test passes unchanged after every commit.
- One branch per item (`task/10-B1-...`). Merge each to `main` when its unit tests, the full suite, `ruff` and CI are green. No stop; each
  merge gets a tag (`cp-10-B1`, …).
- No evaluation seeds while building. Game-based checks use the tuning range (1,000,000+) or a new diagnostic range (5,000,000+),
  written here first.
- Keep this tracker updated after each item: what was built, its flag name, its tests.

**Build list, in order:**
- **B1, self-KO audit (urgent).** Measure how often self-faint moves are advised and when (Pokémon left, KO chance, whether the
  alternative was worse), on the tuning range. Flag `selfko_guard`: a self-faint move is allowed only when its KO chance is at least a
  threshold (parameter, default 0.8) or it's our last useful Pokémon.
- **B2, opponent priority in move order.** Flag `opp_priority`: P(their best move has priority), from the posterior (Sucker Punch,
  ExtremeSpeed, Aqua Jet, Ice Shard, Bullet Punch, Mach Punch, Quick Attack, Vacuum Wave, Shadow Sneak, Fake Out), lowers f(m), following
  each generation's priority rules.
- **B3, recoil and recharge.** Flag `self_costs`: recoil share = recoil fraction × expected absolute damage ÷ our remaining HP, capped at
  1. Hyper Beam's recharge costs a turn's exchange, except in Gen 1 when it KOs (no recharge there).
- **B4, set-up moves.** Flag `setup_value`: a boosting move scores the value of the boosted next exchange (with γ), only when we survive
  the opponent's best hit this turn with high probability. Cap the number of set-up turns.
- **B5, Gen 1 diagnosis.** On 50 lost Gen 1 games from the tuning or diagnostic range, tag what decided each (paralysis or freeze luck,
  crits, partial trapping, Hyper Beam, Explosion's Defense halving, sleep undervalued, a policy mistake) and count. Fix the top 2 causes
  behind `gen1_*` flags.
- **B6, more Gen 2 data.** About 500 more Gen 2 ladder replays (pre-authorised, polite, same script). Retrain as xgb-2 with the same spec on
  a fresh battle split; redo the P(switch) tail calibration (cross-fitting, train + validation only). Report the metrics; xgb-1 stays the
  default until F1.
- **B7, xgb inside the policy as an option.** Flag `opponent_model` = heuristic-0 | xgb, default heuristic-0. Meant only for human
  opponents (the overlay).
- **B8, an independent baseline bot.** A simple heuristic player that uses neither our estimator nor our calculator (Showdown's visible
  information plus basic type and power rules), added to the arena as a third opponent.
- **B9, human-agreement proxy.** On the real-replay test split: how often our advice matches the winner's actual choice, against how often
  it matches the loser's. Per gen. The first signal about play against people.
- **B10, housekeeping.** Archive the logbook into `docs/history/` (under 400 lines left, plus a decision index); the dex `selfdestruct`
  field replacing the hard-coded list; exact Gen 1 desync detection (ground truth stays at 0 false claims); timing tests on AC power.

**F1, the final verification (after B1–B10).**
- Write the plan here before running: the flags to tune, a small grid per flag, the tuning seeds (fresh indices in the 1,000,000 range),
  and the final evaluation seeds **4,000,000–4,000,499, used once**.
- Tune each flag on the tuning seeds, against max-damage and the independent baseline (B8).
- Final paired evaluation: the candidate setting (the best passing flags on) against `cp-08` (all flags off). Opponents: max-damage,
  random and B8, 500 pairs per gen each.
- **Pass, per flag:** pooled paired difference lower bound > −1 point against max-damage and against B8; no health regressions (0 illegal
  moves, timeouts under 1%, p95 under 250 ms). Only flags that pass become default ON. Record everything.
- **STOP with the F1 report: the first review stop.**

**After F1 (the user and the reviewer):** F2, the manual rechecks (the rated guard live, a live game). F3, decoration (README polish, demo
images, explainer doc), then tag `v1.0`. Out of scope: Gen 5+.

## Standing rule added: the autonomy envelope (2026-10-13)

So that review round trips aren't needed for routine work, Claude Code may act **without stopping** inside this envelope,
logging each item here afterwards:
- bug fixes in the tracker, parser or harness that come with a regression test, as long as ground truth stays at 0 false claims;
- refactors with no behaviour change, proven by the existing tests and the golden-decision test (A8, once it exists);
- tooling, logging, reports and documentation moves.

Claude Code **must stop and ask** before changing any of these:
- an approved formula or scoring term;
- a schema field's meaning;
- a pass mark or threshold;
- the seed ranges;
- the prior or its source;
- anything that alters evaluation results after they are seen.

When unsure, ask. And when measurement contradicts a reviewer ruling (as with F1), report it with the numbers. Don't
follow the ruling silently.

## Advice for Claude Code (optional — apply when it fits, note it in the tracker when you do)

These are suggestions, not orders. None needs a separate stop. Apply one when you are already working nearby, and
log it as "A#: applied in <commit>". Skip any that you judge not worth it, with a one-line reason.

- **A1: depend on an interface for the prior (D4).** `showdown` should not import `uncloak` at module level. Take
  the prior through the existing argument (or a small `SetSource` protocol), so parsing never loads the prior tables
  unless player mode needs them. That's dependency inversion, per the SOLID standing rule. It's cheap, and best done in Order 9.
- **A2: continuous integration.** Add a GitHub Actions workflow running `pip install -e ".[dev]"`, `ruff check src tests` and
  `pytest -m "not timing"` on push and on pull requests, with Python 3.10 and 3.12. No secrets are needed. It catches a broken
  `main` even when the local machine is busy. It's a small, separate commit, any time.
- **A3: a demo command.** `python -m poketrix analyze <replay.log> [--turn N]` prints the parsed state, the posterior
  for the opponent's active Pokémon and its threat report. It's useful for manual checks in Phase 6 and for showing the project.
  Best done in Order 11's build, or alongside it.
- **A4: README quickstart.** Five lines (install, run the tests, the demo command) and the results table (oracle match,
  calibration, 0 false claims, staleness). This is a portfolio project, so the README is its front page.
- **A5: keep heavy data out of OneDrive.** `data/raw/` now holds 2,000 replays, and the rebuild adds a source checkout.
  Put caches under `%LOCALAPPDATA%\poketrix-cache` (configurable with an environment variable). The user may also move
  the repository to `C:\dev\Poketrix`; mention it again if timing tests fail.
- **A6: tracker length.** This file is over 2,000 lines. Don't split it without the user's OK (the standing rule
  is "avoid new documentation"), but keep each new section short. Results go in tables, and prose only for what a table
  can't say.

## Standing rules

- Avoid new documentation; update existing files first.
- No secrets in the repo.
- Ask before decisions; recommendations are welcome.
- Keep the code simple and direct; follow SOLID.
- Stop after every step for review; never commit directly to `main`.
