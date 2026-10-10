// Generates the Gen 4 golden damage cases in tests/fixtures/calc_golden_gen4.json from
// @smogon/calc, the engine behind Showdown's damage calculator. Build-time only.
//
//   cd scripts && npm install && npm run build-calc-golden
//
// Each case records the full input plus the oracle's stats and its 16 normal and 16 critical
// rolls (a single number for fixed damage and immunities). poketrix.calc must match them exactly.
// Two groups: hand-picked cases, one per mechanic, and a seeded random sweep that catches
// rounding-order mistakes. Stage 03a has no held items, so no case uses one.

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import calc from '@smogon/calc';

const { ABILITIES, calculate, Field, Generations, Move, Pokemon } = calc;

const HERE = dirname(fileURLToPath(import.meta.url));
const DEX_DIR = join(HERE, '..', 'data', 'dex', 'gen4');
const OUT_FILE = join(HERE, '..', 'tests', 'fixtures', 'calc_golden_gen4.json');
const SWEEP_SIZE = 220;
const SWEEP_SEED = 20261010;

const gen = Generations.get(4);
const readDex = (name) => JSON.parse(readFileSync(join(DEX_DIR, name), 'utf8'));
const SPECIES = readDex('species.json').filter((s) => gen.species.get(s.id));
const MOVES = readDex('moves.json');
const speciesByName = new Map(SPECIES.map((s) => [s.name, s]));

const toID = (text) => text.toLowerCase().replace(/[^a-z0-9]/g, '');
// Cases store ability ids, as our dex does; the oracle only recognises display names.
const ABILITY_NAME = new Map(ABILITIES[4].map((name) => [toID(name), name]));

// Our weather ids (Showdown move ids) -> the oracle's names.
const WEATHER = { sunnyday: 'Sun', raindance: 'Rain', sandstorm: 'Sand', hail: 'Hail' };

// ----------------------------------------------------------------------------- oracle

function oraclePokemon(side) {
  return new Pokemon(gen, side.species, {
    level: side.level,
    ability: ABILITY_NAME.get(side.ability),
    abilityOn: false,
    nature: side.nature,
    ivs: side.ivs,
    evs: side.evs,
    boosts: side.boosts,
    status: side.status,
    curHP: side.hp,
  });
}

const rollList = (damage) => (typeof damage === 'number' ? [damage] : damage);

function runCase(spec) {
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
  const run = (isCrit) =>
    calculate(gen, oraclePokemon(attacker), oraclePokemon(defender), new Move(gen, spec.move, { isCrit }), oracleField());
  const normal = run(false);
  return {
    id: spec.id,
    tags: spec.tags,
    attacker,
    defender,
    move: spec.move,
    field,
    expected: {
      attacker_stats: normal.attacker.rawStats,
      defender_stats: normal.defender.rawStats,
      rolls: rollList(normal.damage),
      crit_rolls: rollList(run(true).damage),
    },
  };
}

// The oracle falls back to a species' first ability; make that explicit so both sides agree.
function fillSide(side) {
  const species = speciesByName.get(side.species);
  if (!species) throw new Error(`unknown species ${side.species}`);
  const ability = toID(side.ability ?? species.possible_abilities[0]);
  if (!species.possible_abilities.includes(ability) || !ABILITY_NAME.has(ability)) {
    throw new Error(`${side.species} cannot have ${ability}`);
  }
  return { level: 100, nature: 'Serious', ivs: {}, evs: {}, boosts: {}, status: null, hp: null, ...side, ability };
}

// ----------------------------------------------------------------------------- hand-picked

const mon = (species, extra = {}) => ({ species, ...extra });
const GARCHOMP = mon('Garchomp', { nature: 'Jolly', evs: { atk: 252, spe: 252, hp: 4 } });
const STARMIE = mon('Starmie', { nature: 'Timid', ability: 'Natural Cure', evs: { spa: 252, spe: 252 } });
const INFERNAPE = mon('Infernape', { nature: 'Naive', evs: { atk: 128, spa: 128, spe: 252 } });
const SWAMPERT = mon('Swampert', { nature: 'Relaxed', evs: { hp: 252, def: 252 } });
const BLISSEY = mon('Blissey', { nature: 'Bold', evs: { hp: 252, def: 252 } });
const SNORLAX = mon('Snorlax', { nature: 'Adamant', ability: 'Immunity', evs: { hp: 252, atk: 252 } });
const GENGAR = mon('Gengar', { nature: 'Timid', evs: { spa: 252, spe: 252 } });
const TYRANITAR = mon('Tyranitar', { nature: 'Careful', evs: { hp: 252, spd: 252 } });
const SKARMORY = mon('Skarmory', { nature: 'Impish', ability: 'Keen Eye', evs: { hp: 252, def: 252 } });
const SHEDINJA = mon('Shedinja', { nature: 'Adamant', evs: { atk: 252 } });
const RAMPARDOS = mon('Rampardos', { nature: 'Adamant', evs: { atk: 252 } });

let handPickedCount = 0;
const pick = (tags, attacker, move, defender, field = {}) => ({
  id: `hand-${String(++handPickedCount).padStart(2, '0')}`,
  tags,
  attacker,
  move,
  defender,
  field,
});

const HAND_PICKED = [
  // type effectiveness and STAB
  pick(['neutral', 'stab'], GARCHOMP, 'Earthquake', SWAMPERT),
  pick(['neutral', 'no-stab'], GARCHOMP, 'Stone Edge', STARMIE),
  pick(['2x', 'stab'], STARMIE, 'Surf', INFERNAPE),
  pick(['4x'], STARMIE, 'Ice Beam', GARCHOMP),
  pick(['4x'], mon('Lucario', { ability: 'Inner Focus', evs: { spa: 252 } }), 'Aura Sphere', TYRANITAR),
  pick(['half'], INFERNAPE, 'Flamethrower', STARMIE),
  pick(['quarter'], INFERNAPE, 'Flamethrower', mon('Kingdra', { ability: 'Sniper' })),
  pick(['immune'], GARCHOMP, 'Earthquake', SKARMORY),
  pick(['immune'], SNORLAX, 'Body Slam', GENGAR),
  pick(['dual-type-order'], STARMIE, 'Ice Beam', SWAMPERT),
  pick(['dual-type-order', 'stab'], mon('Zapdos', { nature: 'Modest', evs: { spa: 252 } }), 'Thunderbolt', mon('Gyarados')),
  pick(['dual-type-order'], INFERNAPE, 'Close Combat', mon('Heatran')),
  pick(['dual-type-order'], mon('Abomasnow'), 'Wood Hammer', mon('Empoleon')),
  // stat stages and critical hits (every case also records its critical-hit rolls)
  pick(['boost'], mon('Garchomp', { ...GARCHOMP, boosts: { atk: 2 } }), 'Earthquake', SWAMPERT),
  pick(['drop', 'crit-ignores-drop'], mon('Garchomp', { ...GARCHOMP, boosts: { atk: -1 } }), 'Earthquake', SWAMPERT),
  pick(['defense-boost', 'crit-ignores-boost'], GARCHOMP, 'Earthquake', mon('Swampert', { ...SWAMPERT, boosts: { def: 2 } })),
  pick(['defense-drop'], STARMIE, 'Surf', mon('Blissey', { ...BLISSEY, boosts: { spd: -2 } })),
  pick(['max-stages'], mon('Garchomp', { ...GARCHOMP, boosts: { atk: 6 } }), 'Dragon Claw', mon('Swampert', { ...SWAMPERT, boosts: { def: -6 } })),
  pick(['min-stages'], mon('Starmie', { ...STARMIE, boosts: { spa: -6 } }), 'Psychic', mon('Blissey', { ...BLISSEY, boosts: { spd: 6 } })),
  // burn, screens, weather
  pick(['burn'], mon('Garchomp', { ...GARCHOMP, status: 'brn' }), 'Earthquake', SWAMPERT),
  pick(['burn-special-unaffected'], mon('Starmie', { ...STARMIE, status: 'brn' }), 'Surf', SWAMPERT),
  pick(['reflect'], GARCHOMP, 'Earthquake', SWAMPERT, { reflect: true }),
  pick(['reflect-vs-special'], STARMIE, 'Surf', SWAMPERT, { reflect: true }),
  pick(['light-screen'], STARMIE, 'Surf', SWAMPERT, { light_screen: true }),
  pick(['brick-break-ignores-reflect'], INFERNAPE, 'Brick Break', BLISSEY, { reflect: true }),
  pick(['sun-fire'], INFERNAPE, 'Flamethrower', SWAMPERT, { weather: 'sunnyday' }),
  pick(['sun-water'], STARMIE, 'Surf', INFERNAPE, { weather: 'sunnyday' }),
  pick(['rain-water'], STARMIE, 'Surf', INFERNAPE, { weather: 'raindance' }),
  pick(['rain-fire'], INFERNAPE, 'Flamethrower', SWAMPERT, { weather: 'raindance' }),
  pick(['solar-beam-rain'], mon('Venusaur', { evs: { spa: 252 } }), 'Solar Beam', SWAMPERT, { weather: 'raindance' }),
  pick(['solar-beam-sun'], mon('Venusaur', { evs: { spa: 252 } }), 'Solar Beam', SWAMPERT, { weather: 'sunnyday' }),
  pick(['sandstorm-rock-spdef'], STARMIE, 'Surf', TYRANITAR, { weather: 'sandstorm' }),
  pick(['sandstorm-physical-unaffected'], GARCHOMP, 'Earthquake', TYRANITAR, { weather: 'sandstorm' }),
  pick(['cloud-nine-negates-weather'], mon('Golduck', { ability: 'Cloud Nine' }), 'Surf', INFERNAPE, { weather: 'raindance' }),
  pick(['air-lock-negates-weather'], INFERNAPE, 'Flamethrower', mon('Rayquaza'), { weather: 'sunnyday' }),
  pick(['weather-ball-sun'], mon('Roserade', { evs: { spa: 252 } }), 'Weather Ball', SWAMPERT, { weather: 'sunnyday' }),
  pick(['weather-ball-rain'], mon('Roserade', { evs: { spa: 252 } }), 'Weather Ball', INFERNAPE, { weather: 'raindance' }),
  pick(['weather-ball-sand'], mon('Roserade', { evs: { spa: 252 } }), 'Weather Ball', mon('Zapdos'), { weather: 'sandstorm' }),
  pick(['weather-ball-hail'], mon('Roserade', { evs: { spa: 252 } }), 'Weather Ball', GARCHOMP, { weather: 'hail' }),
  pick(['weather-ball-clear'], mon('Roserade', { evs: { spa: 252 } }), 'Weather Ball', SWAMPERT),
  // defense-halving moves, level extremes, minimum damage
  pick(['explosion'], mon('Metagross', { nature: 'Adamant', evs: { atk: 252 } }), 'Explosion', BLISSEY),
  pick(['self-destruct'], SNORLAX, 'Self-Destruct', SWAMPERT),
  pick(['level-1-attacker', 'minimum-damage'], mon('Rattata', { level: 1, ability: 'Run Away' }), 'Tackle', mon('Steelix', { ability: 'Rock Head' })),
  pick(['level-1-defender'], GARCHOMP, 'Earthquake', mon('Rattata', { level: 1, ability: 'Run Away' })),
  pick(['level-50'], mon('Garchomp', { ...GARCHOMP, level: 50 }), 'Earthquake', mon('Swampert', { ...SWAMPERT, level: 50 })),
  // fixed damage
  pick(['fixed-level'], BLISSEY, 'Seismic Toss', SWAMPERT),
  pick(['fixed-level', 'immune'], BLISSEY, 'Seismic Toss', GENGAR),
  pick(['fixed-level', 'level-73'], mon('Gengar', { ...GENGAR, level: 73 }), 'Night Shade', SWAMPERT),
  pick(['fixed-level', 'immune'], GENGAR, 'Night Shade', SNORLAX),
  pick(['fixed-flat'], mon('Dragonair', { ability: 'Shed Skin' }), 'Dragon Rage', SWAMPERT),
  pick(['fixed-flat'], mon('Magnemite', { ability: 'Magnet Pull' }), 'Sonic Boom', GARCHOMP),
  pick(['fixed-flat', 'immune'], mon('Magnemite', { ability: 'Magnet Pull' }), 'Sonic Boom', GENGAR),
  pick(['fixed-level', 'wonder-guard'], BLISSEY, 'Seismic Toss', SHEDINJA),
  // variable base power
  pick(['return'], SNORLAX, 'Return', SWAMPERT),
  pick(['frustration'], SNORLAX, 'Frustration', SWAMPERT),
  pick(['eruption-partial-hp'], mon('Typhlosion', { evs: { spa: 252 }, hp: 160 }), 'Eruption', SWAMPERT),
  pick(['eruption-full-hp'], mon('Typhlosion', { evs: { spa: 252 } }), 'Eruption', BLISSEY),
  pick(['water-spout-1hp'], mon('Kyogre', { hp: 1 }), 'Water Spout', BLISSEY, { weather: 'raindance' }),
  pick(['flail-low-hp'], mon('Magikarp', { hp: 3 }), 'Flail', STARMIE),
  pick(['flail-full-hp'], mon('Magikarp'), 'Flail', STARMIE),
  pick(['reversal-mid-hp'], mon('Heracross', { ability: 'Swarm', evs: { atk: 252 }, hp: 60 }), 'Reversal', TYRANITAR),
  pick(['brine-half-hp'], mon('Tentacruel', { ability: 'Clear Body' }), 'Brine', mon('Infernape', { ...INFERNAPE, hp: 146 })),
  pick(['brine-above-half'], mon('Tentacruel', { ability: 'Clear Body' }), 'Brine', mon('Infernape', { ...INFERNAPE, hp: 148 })),
  pick(['facade-paralysis'], mon('Ursaring', { ability: 'Quick Feet', status: 'par', evs: { atk: 252 } }), 'Facade', SWAMPERT),
  pick(['facade-burn'], mon('Snorlax', { ...SNORLAX, status: 'brn' }), 'Facade', SWAMPERT),
  pick(['wake-up-slap-asleep'], mon('Machamp', { ability: 'No Guard' }), 'Wake-Up Slap', mon('Blissey', { ...BLISSEY, status: 'slp' })),
  pick(['crush-grip'], mon('Regigigas'), 'Crush Grip', mon('Swampert', { ...SWAMPERT, hp: 200 })),
  pick(['wring-out-full-hp'], mon('Tangrowth', { ability: 'Chlorophyll' }), 'Wring Out', BLISSEY),
  pick(['hidden-power-typed'], mon('Zapdos', { nature: 'Timid', evs: { spa: 252 } }), 'Hidden Power Ice', GARCHOMP),
  pick(['hidden-power-typed'], mon('Heatran', { evs: { spa: 252 } }), 'Hidden Power Grass', SWAMPERT),
  // typeless damage
  pick(['typeless', 'struggle-hits-ghost'], SNORLAX, 'Struggle', GENGAR),
  pick(['typeless', 'future-sight-hits-dark'], STARMIE, 'Future Sight', TYRANITAR),
  pick(['typeless', 'no-stab'], mon('Jirachi'), 'Doom Desire', INFERNAPE),
  // abilities that make a move do nothing
  pick(['levitate'], GARCHOMP, 'Earthquake', GENGAR),
  pick(['levitate', 'gravity'], GARCHOMP, 'Earthquake', GENGAR, { gravity: true }),
  pick(['gravity-grounds-flying'], GARCHOMP, 'Earthquake', SKARMORY, { gravity: true }),
  pick(['flash-fire'], INFERNAPE, 'Flamethrower', mon('Heatran')),
  pick(['water-absorb'], STARMIE, 'Surf', mon('Vaporeon')),
  pick(['dry-skin-water'], STARMIE, 'Surf', mon('Toxicroak', { ability: 'Dry Skin' })),
  pick(['volt-absorb'], mon('Zapdos'), 'Thunderbolt', mon('Jolteon')),
  pick(['motor-drive'], mon('Zapdos'), 'Thunderbolt', mon('Electivire')),
  pick(['wonder-guard-blocks-neutral'], STARMIE, 'Surf', SHEDINJA),
  pick(['wonder-guard-super-effective'], INFERNAPE, 'Flamethrower', SHEDINJA),
  pick(['wonder-guard-typeless'], SNORLAX, 'Struggle', SHEDINJA),
  pick(['wonder-guard-fire-fang'], mon('Arcanine', { ability: 'Intimidate' }), 'Fire Fang', SHEDINJA),
  pick(['mold-breaker-levitate'], RAMPARDOS, 'Earthquake', mon('Bronzong', { ability: 'Levitate' })),
  pick(['mold-breaker-wonder-guard'], RAMPARDOS, 'Zen Headbutt', SHEDINJA),
  pick(['scrappy'], mon('Kangaskhan', { ability: 'Scrappy', evs: { atk: 252 } }), 'Return', GENGAR),
  pick(['foresight'], SNORLAX, 'Body Slam', GENGAR, { foresight: true }),
  pick(['foresight', 'fighting'], INFERNAPE, 'Close Combat', GENGAR, { foresight: true }),
];

// ----------------------------------------------------------------------------- random sweep

// Abilities whose damage effect belongs to stage 03b. The sweep never rolls them.
const NOT_YET_MODELLED = new Set([
  'adaptability', 'battlearmor', 'shellarmor', 'blaze', 'overgrow', 'torrent', 'swarm', 'dryskin',
  'filter', 'solidrock', 'flowergift', 'guts', 'heatproof', 'hugepower', 'purepower', 'hustle',
  'ironfist', 'marvelscale', 'normalize', 'reckless', 'rivalry', 'simple', 'sniper', 'solarpower',
  'soundproof', 'technician', 'thickfat', 'tintedlens', 'unaware', 'download', 'forecast',
]);
// Fixed-damage kinds the oracle implements; it returns 0 for the others.
const ORACLE_FIXED = (kind) => typeof kind === 'number' || kind === 'level';
const SWEEP_MOVES = MOVES.filter(
  (m) =>
    m.category !== 'status' &&
    !m.multihit && // the oracle returns one roll list per hit
    !m.id.startsWith('hiddenpower') && // the oracle ignores IVs; covered by hand-picked cases
    (m.fixed_damage === undefined || ORACLE_FIXED(m.fixed_damage)),
);
const NATURES = JSON.parse(readFileSync(join(DEX_DIR, '..', 'natures.json'), 'utf8')).map((n) => n.id);
const STATS = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];

function mulberry32(seed) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function sweep(count, seed) {
  const random = mulberry32(seed);
  const int = (low, high) => low + Math.floor(random() * (high - low + 1));
  const choose = (list) => list[int(0, list.length - 1)];
  const chance = (p) => random() < p;

  function randomSide(statuses) {
    let species;
    let ability;
    do {
      species = choose(SPECIES);
      ability = choose(species.possible_abilities);
    } while (NOT_YET_MODELLED.has(ability));
    const side = { species: species.name, ability, level: chance(0.5) ? 100 : int(1, 100), nature: choose(NATURES) };
    if (chance(0.5)) side.ivs = Object.fromEntries(STATS.map((s) => [s, int(0, 31)]));
    let evBudget = 510;
    side.evs = {};
    for (const stat of STATS) {
      const ev = chance(0.5) ? 0 : Math.min(evBudget, int(0, 252));
      side.evs[stat] = ev;
      evBudget -= ev;
    }
    if (chance(0.4)) side.boosts = Object.fromEntries(['atk', 'def', 'spa', 'spd'].map((s) => [s, int(-6, 6)]));
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
        weather: chance(0.5) ? 'none' : choose(Object.keys(WEATHER)),
        reflect: chance(0.15),
        light_screen: chance(0.15),
        gravity: chance(0.05),
        foresight: chance(0.05),
      },
    });
  }
  return cases;
}

// ----------------------------------------------------------------------------- output

const cases = [...HAND_PICKED, ...sweep(SWEEP_SIZE, SWEEP_SEED)].map(runCase);
const { version } = JSON.parse(
  readFileSync(join(HERE, 'node_modules', '@smogon', 'calc', 'package.json'), 'utf8'),
);
const header = JSON.stringify({ oracle: '@smogon/calc', version, generation: 4 });
writeFileSync(
  OUT_FILE,
  `{"source":${header},"cases":[\n${cases.map((c) => JSON.stringify(c)).join(',\n')}\n]}\n`,
);
console.log(`${cases.length} cases (${HAND_PICKED.length} hand-picked, ${SWEEP_SIZE} sweep) -> ${OUT_FILE}`);
