// Generates the golden damage cases in tests/fixtures/calc_golden_gen{1..4}.json from
// @smogon/calc, the engine behind Showdown's damage calculator. Build-time only.
//
//   cd scripts && npm install && npm run build-calc-golden        (all generations)
//   node build_calc_golden.mjs 3                                    (one generation)
//
// Each case records the full input plus the oracle's stats and its normal and critical rolls
// (a single number for fixed damage and immunities). poketrix.calc must match them exactly.
// Two groups per generation: hand-picked cases, one per mechanic (golden_cases/gen{N}.mjs), and a
// seeded random sweep that catches rounding-order mistakes.
//
// Inputs are written in our own units. For Gens 1-2 that means DVs (0-15) and Stat Exp
// (0-65535) under `ivs` / `evs`; they are converted to the oracle's IV / EV scale here.

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import calc from '@smogon/calc';

const { ABILITIES, calculate, Field, Generations, Move, Pokemon } = calc;

const HERE = dirname(fileURLToPath(import.meta.url));
const DEX_ROOT = join(HERE, '..', 'data', 'dex');
const FIXTURES = join(HERE, '..', 'tests', 'fixtures');
const ALL_GENS = [1, 2, 3, 4];
const STATS = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
const NATURES = JSON.parse(readFileSync(join(DEX_ROOT, 'natures.json'), 'utf8')).map((n) => n.id);
const { version: ORACLE_VERSION } = JSON.parse(
  readFileSync(join(HERE, 'node_modules', '@smogon', 'calc', 'package.json'), 'utf8'),
);

const toID = (text) => text.toLowerCase().replace(/[^a-z0-9]/g, '');
// Our weather ids (Showdown move ids) -> the oracle's names, in the order they were introduced.
const WEATHER = { sunnyday: 'Sun', raindance: 'Rain', sandstorm: 'Sand', hail: 'Hail' };
const WEATHERS_BY_GEN = {
  1: [],
  2: ['sunnyday', 'raindance', 'sandstorm'],
  3: Object.keys(WEATHER),
  4: Object.keys(WEATHER),
};

// Abilities the sweep never rolls: the oracle changes its own input for them (a stat stage or
// the holder's types), which in a real battle reaches us through the battle log instead.
const CHANGES_ITS_INPUT = new Set(['download', 'forecast']);
// Needs "ability on" to do anything; rolled as active half the time.
const TOGGLED = new Set(['flashfire', 'slowstart']);
// Fixed-damage kinds the oracle implements; it returns 0 for the others.
const ORACLE_FIXED = (kind) => typeof kind === 'number' || kind === 'level';
// In Gen 1 the oracle always treats these as critical hits, so its "normal" rolls are crit rolls.
const GEN1_ALWAYS_CRIT = new Set(['crabhammer', 'razorleaf', 'slash', 'karatechop']);
// Items with a damage effect, so the sweep meets them far more often than the rest.
const COMMON_DAMAGE_ITEMS = [
  'Choice Band', 'Choice Specs', 'Choice Scarf', 'Life Orb', 'Expert Belt', 'Muscle Band',
  'Wise Glasses', 'Iron Ball', 'Metronome', 'Macho Brace',
];

function mulberry32(seed) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const perHit = (damage) => (Array.isArray(damage) && Array.isArray(damage[0]) ? damage : [damage]);
const rollList = (damage) => {
  const first = perHit(damage)[0];
  return typeof first === 'number' ? [first] : first;
};
const laterHitsDiffer = (damage) => {
  const hits = perHit(damage).map((rolls) => JSON.stringify(rolls));
  return hits.some((rolls) => rolls !== hits[0]);
};

function buildGeneration(genNum, definition) {
  const gen = Generations.get(genNum);
  const dexDir = join(DEX_ROOT, `gen${genNum}`);
  const readDex = (name) => JSON.parse(readFileSync(join(dexDir, name), 'utf8'));
  const SPECIES = readDex('species.json').filter((s) => gen.species.get(s.id));
  const MOVES = readDex('moves.json');
  const ITEMS = existsSync(join(dexDir, 'items.json')) ? readDex('items.json') : [];
  const speciesByName = new Map(SPECIES.map((s) => [s.name, s]));
  const moveNames = new Set(MOVES.map((m) => m.name));
  // Cases store ability ids, as our dex does; the oracle only recognises display names.
  const ABILITY_NAME = new Map((ABILITIES[genNum] ?? []).map((name) => [toID(name), name]));
  const classic = genNum <= 2; // DVs and Stat Exp instead of IVs, EVs and natures
  const weathers = WEATHERS_BY_GEN[genNum];

  // ------------------------------------------------------------------------------- oracle

  // Our DVs (0-15) -> the oracle's IVs; our Stat Exp -> the oracle's EVs (it squares them back).
  const scaled = (values, convert) =>
    Object.fromEntries(Object.entries(values).map(([stat, value]) => [stat, convert(value)]));
  const oracleSpread = (side) =>
    classic
      ? { ivs: scaled(side.ivs, (dv) => dv * 2), evs: scaled(side.evs, (exp) => Math.round(Math.sqrt(exp))) }
      : { ivs: side.ivs, evs: side.evs };

  function oraclePokemon(side) {
    return new Pokemon(gen, side.species, {
      level: side.level,
      ability: ABILITY_NAME.get(side.ability),
      abilityOn: side.ability_on,
      item: side.item ?? undefined,
      nature: side.nature ?? undefined,
      ...oracleSpread(side),
      boosts: side.boosts,
      status: side.status,
      curHP: side.hp,
    });
  }

  // The oracle falls back to a species' first ability; make that explicit so both sides agree.
  function fillSide(side) {
    const species = speciesByName.get(side.species);
    if (!species) throw new Error(`gen${genNum}: unknown species ${side.species}`);
    let ability = null;
    if (species.possible_abilities.length) {
      ability = toID(side.ability ?? species.possible_abilities[0]);
      if (!species.possible_abilities.includes(ability) || !ABILITY_NAME.has(ability)) {
        throw new Error(`gen${genNum}: ${side.species} cannot have ${ability}`);
      }
    }
    if (side.item && !ITEMS.some((item) => item.name === side.item)) {
      throw new Error(`gen${genNum}: unknown item ${side.item}`);
    }
    const defaults = {
      level: 100, nature: classic ? null : 'Serious', ivs: {}, evs: {}, boosts: {},
      status: null, hp: null, item: null, ability_on: false,
    };
    return { ...defaults, ...side, ability };
  }

  function runCase(spec) {
    if (!moveNames.has(spec.move)) throw new Error(`gen${genNum}: unknown move ${spec.move}`);
    const attacker = fillSide(spec.attacker);
    const defender = fillSide(spec.defender);
    const field = { weather: 'none', reflect: false, light_screen: false, gravity: false, foresight: false, ...spec.field };
    const oracleField = () =>
      new Field({
        weather: WEATHER[field.weather],
        isGravity: field.gravity,
        defenderSide: {
          isReflect: field.reflect,
          isLightScreen: field.light_screen,
          isForesight: field.foresight,
        },
      });
    const moveOptions = { ability: ABILITY_NAME.get(attacker.ability), item: attacker.item ?? undefined };
    const run = (isCrit) =>
      calculate(
        gen,
        oraclePokemon(attacker),
        oraclePokemon(defender),
        new Move(gen, spec.move, { ...moveOptions, isCrit }),
        oracleField(),
      );
    const normal = run(false);
    const expected = {
      attacker_stats: normal.attacker.rawStats,
      defender_stats: normal.defender.rawStats,
      rolls: rollList(normal.damage),
      crit_rolls: rollList(run(true).damage),
      // A multi-hit move comes back as one roll list per hit; they are identical unless
      // something changes between hits (a resist berry is eaten after the first).
      later_hits_differ: laterHitsDiffer(normal.damage),
      oracle_always_crits: genNum === 1 && GEN1_ALWAYS_CRIT.has(toID(spec.move)),
    };
    return { id: spec.id, tags: spec.tags, attacker, defender, move: spec.move, field, expected };
  }

  // -------------------------------------------------------------------------- hand-picked

  let handPickedCount = 0;
  const mon = (species, extra = {}) => ({ species, ...extra });
  const pick = (tags, attacker, move, defender, field = {}) => ({
    id: `hand-${String(++handPickedCount).padStart(2, '0')}`,
    tags,
    attacker,
    move,
    defender,
    field,
  });
  const handPicked = definition.handPicked({ mon, pick });

  // ------------------------------------------------------------------------- random sweep

  const excluded = new Set(definition.sweepExcludedMoves ?? []);
  const SWEEP_MOVES = MOVES.filter(
    (m) =>
      m.category !== 'status' &&
      !excluded.has(m.id) &&
      !m.id.startsWith('hiddenpower') && // the oracle ignores IVs; covered by hand-picked cases
      (m.fixed_damage === undefined || ORACLE_FIXED(m.fixed_damage)),
  );
  const DAMAGE_ITEMS = ITEMS.filter(
    (item) => item.boosts_type || item.resists_type || COMMON_DAMAGE_ITEMS.includes(item.name),
  );

  function sweep(count, seed) {
    const random = mulberry32(seed);
    const int = (low, high) => low + Math.floor(random() * (high - low + 1));
    const choose = (list) => list[int(0, list.length - 1)];
    const chance = (p) => random() < p;

    function modernSpread(side) {
      if (chance(0.5)) side.ivs = Object.fromEntries(STATS.map((s) => [s, int(0, 31)]));
      let evBudget = 510;
      side.evs = {};
      for (const stat of STATS) {
        const ev = chance(0.5) ? 0 : Math.min(evBudget, int(0, 252));
        side.evs[stat] = ev;
        evBudget -= ev;
      }
    }

    // One Special DV and one Special Stat Exp serve both special stats; the HP DV is derived.
    function classicSpread(side) {
      if (chance(0.5)) {
        const special = int(0, 15);
        side.ivs = { atk: int(0, 15), def: int(0, 15), spe: int(0, 15), spa: special, spd: special };
      }
      side.evs = {};
      for (const stat of ['hp', 'atk', 'def', 'spe', 'spa']) {
        if (chance(0.5)) continue; // omitted = maximum
        const root = int(0, 255);
        side.evs[stat] = root * root;
        if (stat === 'spa') side.evs.spd = side.evs.spa;
      }
    }

    function randomSide(statuses) {
      let species;
      let ability;
      do {
        species = choose(SPECIES);
        ability = species.possible_abilities.length ? choose(species.possible_abilities) : null;
      } while (CHANGES_ITS_INPUT.has(ability));
      const side = { species: species.name, level: chance(0.5) ? 100 : int(1, 100) };
      if (ability) side.ability = ability;
      if (!classic) side.nature = choose(NATURES);
      if (TOGGLED.has(ability)) side.ability_on = chance(0.5);
      if (ITEMS.length && chance(0.6)) side.item = choose(chance(0.8) ? DAMAGE_ITEMS : ITEMS).name;
      (classic ? classicSpread : modernSpread)(side);
      if (chance(0.4)) {
        side.boosts = Object.fromEntries(['atk', 'def', 'spa', 'spd', 'spe'].map((s) => [s, int(-6, 6)]));
        if (genNum === 1) side.boosts.spd = side.boosts.spa; // one Special stat
      }
      if (chance(0.3)) side.status = choose(statuses);
      if (chance(0.3)) side.hp = int(1, oraclePokemon(fillSide(side)).maxHP());
      return side;
    }

    const cases = [];
    for (let i = 1; i <= count; i++) {
      cases.push({
        id: `sweep-${String(i).padStart(3, '0')}`,
        tags: ['sweep'],
        attacker: randomSide(['brn', 'brn', 'par', 'psn', 'tox']),
        defender: randomSide(['slp', 'par', 'brn']),
        move: choose(SWEEP_MOVES).name,
        field: {
          weather: weathers.length && chance(0.5) ? choose(weathers) : 'none',
          reflect: chance(0.15),
          light_screen: chance(0.15),
          gravity: genNum >= 4 && chance(0.05),
          foresight: genNum >= 2 && chance(0.05),
        },
      });
    }
    return cases;
  }

  // ------------------------------------------------------------------------------- output

  const cases = [...handPicked, ...sweep(definition.sweepSize, definition.sweepSeed)].map(runCase);
  const header = JSON.stringify({ oracle: '@smogon/calc', version: ORACLE_VERSION, generation: genNum });
  const outFile = join(FIXTURES, `calc_golden_gen${genNum}.json`);
  writeFileSync(outFile, `{"source":${header},"cases":[\n${cases.map((c) => JSON.stringify(c)).join(',\n')}\n]}\n`);
  console.log(`gen${genNum}: ${cases.length} cases (${handPicked.length} hand-picked, ${definition.sweepSize} sweep)`);
}

const requested = process.argv.slice(2).map(Number);
for (const genNum of requested.length ? requested : ALL_GENS) {
  buildGeneration(genNum, await import(`./golden_cases/gen${genNum}.mjs`));
}
