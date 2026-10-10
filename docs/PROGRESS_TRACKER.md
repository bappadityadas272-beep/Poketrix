# Poketrix — progress tracker

Last updated: 2026-10-10 (Phase 3 complete, merged as cp-03c; Task 04 design proposal next)

## Status at a glance

| # | Phase | Status | Checkpoint |
|---|-------|--------|------------|
| 0 | Repo scaffold + checkpoint workflow | Done, merged | `cp-00` |
| 1 | Shared Pydantic schemas (Gen 1–4 aware) | Done, merged | `cp-01` |
| 2 | Dex data layer (Gen 1–4 species and moves) | Done, merged | `cp-02` |
| 3 | Math layer (type chart, stats, damage, KO odds) | **Done, merged** (all four generations) | `cp-03a`, `cp-03b`, `cp-03c` |
| 4 | Bayesian set uncloaker | Next: design proposal (Order 4) | |
| 5 | Showdown battle-log parser → `GameState` | Not started | |
| 6 | Orchestrator + synthesis guardrail | Not started | |
| 7 | XGBoost action predictor | Not started | |
| — | Knowledge graph / RAG, vision ingestion | Deferred | |

Tests: 679 passing. `ruff check src tests` is clean.

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

## Standing rules

- Avoid new documentation; update existing files first.
- No secrets in the repo.
- Ask before decisions; recommendations are welcome.
- Keep the code simple and direct; follow SOLID.
- Stop after every step for review; never commit directly to `main`.
