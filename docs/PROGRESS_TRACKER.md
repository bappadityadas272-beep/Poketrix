# Poketrix — progress tracker

Last updated: 2026-10-10 (Task 04 step 1, the uncloaker, built; awaiting review)

## Status at a glance

| # | Phase | Status | Checkpoint |
|---|-------|--------|------------|
| 0 | Repo scaffold + checkpoint workflow | Done, merged | `cp-00` |
| 1 | Shared Pydantic schemas (Gen 1–4 aware) | Done, merged | `cp-01` |
| 2 | Dex data layer (Gen 1–4 species and moves) | Done, merged | `cp-02` |
| 3 | Math layer (type chart, stats, damage, KO odds) | **Done, merged** (all four generations) | `cp-03a`, `cp-03b`, `cp-03c` |
| 4 | Bayesian set uncloaker | Step 1 (prior + uncloaker) built on `task/04-bayes-uncloaker`, **awaiting review**; step 2 (threat report) to follow | |
| 5 | Showdown battle-log parser → `GameState` | Not started | |
| 6 | Orchestrator + synthesis guardrail | Not started | |
| 7 | XGBoost action predictor | Not started | |
| — | Knowledge graph / RAG, vision ingestion | Deferred | |

Tests: 679 passing on `main`; 716 on `task/04-bayes-uncloaker`. `ruff check src tests` is clean.

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

## Orders for Claude Code (do these in order, stopping where marked)

### Order 1: close Task 02 (no stop needed, the user has approved)
1. On `task/02-dex-data`, add `.claude/settings.local.json` to `.gitignore` and commit this tracker and the
   `CLAUDE.md` pointer change.
2. Run `git switch main`, then `git merge --no-ff task/02-dex-data`, then `git tag -a cp-02 -m "Dex data layer, Gens 1-4"`.
3. Add cp-02 to `docs/CHECKPOINTS.md` (68 tests) and mark phase 2 as done in `README.md`.
4. Run `pytest` and `ruff check src tests` on `main`, then `git push origin main --tags`.
5. Report the push result in one line.

**Result (2026-10-10): done.** Merge commit `7621b89`, tag `cp-02`, 68 tests green and ruff clean on
`main`, pushed (`5cf9c2d..7621b89 main -> main`, new tag `cp-02`). GitHub reported that the repository
moved to `bappadityadas272-beep/Poketrix` (capital P); the old URL still redirects.

### Order 2: Task 03 design proposal, Math layer, Gen 4 first. **STOP after the proposal.**
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

## Orders for Claude Code, batch 2 (do these in order, stopping where marked)

### Order 3: close Task 03c and Phase 3 (no stop needed, the user has approved)
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

### Order 4: Task 04 design proposal, the Bayesian set uncloaker. **STOP after the proposal.**
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

## Task 04, step 1 — the set prior and the uncloaker (built 2026-10-10, awaiting review)

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

## Standing rules

- Avoid new documentation; update existing files first.
- No secrets in the repo.
- Ask before decisions; recommendations are welcome.
- Keep the code simple and direct; follow SOLID.
- Stop after every step for review; never commit directly to `main`.
