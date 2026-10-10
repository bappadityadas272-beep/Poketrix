# Poketrix — progress tracker

Last updated: 2026-10-10 (Task 03a merged as cp-03a; Task 03b design proposal awaiting approval)

## Status at a glance

| # | Phase | Status | Checkpoint |
|---|-------|--------|------------|
| 0 | Repo scaffold + checkpoint workflow | Done, merged | `cp-00` |
| 1 | Shared Pydantic schemas (Gen 1–4 aware) | Done, merged | `cp-01` |
| 2 | Dex data layer (Gen 1–4 species and moves) | Done, merged | `cp-02` |
| 3 | Math layer (type chart, stats, damage, KO odds) | 03a (Gen 4 core) done, merged; 03b (items, abilities) design proposed, **awaiting approval**; 03c (Gens 3 → 1) after | `cp-03a` |
| 4 | Bayesian set uncloaker | Not started | |
| 5 | Showdown battle-log parser → `GameState` | Not started | |
| 6 | Orchestrator + synthesis guardrail | Not started | |
| 7 | XGBoost action predictor | Not started | |
| — | Knowledge graph / RAG, vision ingestion | Deferred | |

Tests: 231 passing. `ruff check src tests` is clean.

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

## Task 03b design proposal — Gen 4 items, abilities and remaining moves (2026-10-10, awaiting approval)

Branch `task/03b-items-abilities`. No 03b code exists yet.

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

### Decisions needed before any code

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

## Standing rules

- Avoid new documentation; update existing files first.
- No secrets in the repo.
- Ask before decisions; recommendations are welcome.
- Keep the code simple and direct; follow SOLID.
- Stop after every step for review; never commit directly to `main`.
