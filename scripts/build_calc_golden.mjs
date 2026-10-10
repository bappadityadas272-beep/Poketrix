// Generates the Gen 4 golden damage cases in tests/fixtures/calc_golden_gen4.json from
// @smogon/calc, the engine behind Showdown's damage calculator. Build-time only.
//
//   cd scripts && npm install && npm run build-calc-golden
//
// Each case records the full input plus the oracle's stats and its 16 normal and 16 critical
// rolls (a single number for fixed damage and immunities). poketrix.calc must match them exactly.
// Two groups: hand-picked cases, one per mechanic, and a seeded random sweep (items and abilities
// included) that catches rounding-order mistakes.

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import calc from '@smogon/calc';

const { ABILITIES, calculate, Field, Generations, Move, Pokemon } = calc;

const HERE = dirname(fileURLToPath(import.meta.url));
const DEX_DIR = join(HERE, '..', 'data', 'dex', 'gen4');
const OUT_FILE = join(HERE, '..', 'tests', 'fixtures', 'calc_golden_gen4.json');
const SWEEP_SIZE = 300;
const SWEEP_SEED = 20261011;

const gen = Generations.get(4);
const readDex = (name) => JSON.parse(readFileSync(join(DEX_DIR, name), 'utf8'));
const SPECIES = readDex('species.json').filter((s) => gen.species.get(s.id));
const MOVES = readDex('moves.json');
const ITEMS = readDex('items.json');
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
    abilityOn: side.ability_on,
    item: side.item ?? undefined,
    nature: side.nature,
    ivs: side.ivs,
    evs: side.evs,
    boosts: side.boosts,
    status: side.status,
    curHP: side.hp,
  });
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
    // A multi-hit move comes back as one roll list per hit; they are identical unless something
    // changes between hits (a resist berry is eaten after the first).
    later_hits_differ: laterHitsDiffer(normal.damage),
  };
  return {
    id: spec.id,
    tags: spec.tags,
    attacker,
    defender,
    move: spec.move,
    field,
    expected,
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
  if (side.item && !ITEMS.some((item) => item.name === side.item)) {
    throw new Error(`unknown item ${side.item}`);
  }
  const defaults = { level: 100, nature: 'Serious', ivs: {}, evs: {}, boosts: {}, status: null, hp: null, item: null, ability_on: false };
  return { ...defaults, ...side, ability };
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

  // ---- 03b: attacker items
  pick(['choice-band'], mon('Garchomp', { ...GARCHOMP, item: 'Choice Band' }), 'Earthquake', SWAMPERT),
  pick(['choice-band-special-unaffected'], mon('Starmie', { ...STARMIE, item: 'Choice Band' }), 'Surf', SWAMPERT),
  pick(['choice-specs'], mon('Starmie', { ...STARMIE, item: 'Choice Specs' }), 'Surf', SWAMPERT),
  pick(['life-orb'], mon('Starmie', { ...STARMIE, item: 'Life Orb' }), 'Ice Beam', GARCHOMP),
  pick(['life-orb', 'physical'], mon('Garchomp', { ...GARCHOMP, item: 'Life Orb' }), 'Outrage', SWAMPERT),
  pick(['expert-belt-super-effective'], mon('Infernape', { ...INFERNAPE, item: 'Expert Belt' }), 'Close Combat', TYRANITAR),
  pick(['expert-belt-neutral'], mon('Infernape', { ...INFERNAPE, item: 'Expert Belt' }), 'Close Combat', SWAMPERT),
  pick(['muscle-band'], mon('Garchomp', { ...GARCHOMP, item: 'Muscle Band' }), 'Earthquake', SWAMPERT),
  pick(['wise-glasses'], mon('Starmie', { ...STARMIE, item: 'Wise Glasses' }), 'Surf', SWAMPERT),
  pick(['type-item'], mon('Infernape', { ...INFERNAPE, item: 'Charcoal' }), 'Flamethrower', SWAMPERT),
  pick(['type-item-other-type'], mon('Infernape', { ...INFERNAPE, item: 'Charcoal' }), 'Close Combat', SWAMPERT),
  pick(['plate'], mon('Garchomp', { ...GARCHOMP, item: 'Earth Plate' }), 'Earthquake', SWAMPERT),
  pick(['incense'], mon('Starmie', { ...STARMIE, item: 'Sea Incense' }), 'Surf', INFERNAPE),
  pick(['silk-scarf-struggle'], mon('Snorlax', { ...SNORLAX, item: 'Silk Scarf' }), 'Struggle', SWAMPERT),
  pick(['adamant-orb'], mon('Dialga', { item: 'Adamant Orb' }), 'Draco Meteor', SWAMPERT),
  pick(['adamant-orb-other-type'], mon('Dialga', { item: 'Adamant Orb' }), 'Flamethrower', SWAMPERT),
  pick(['lustrous-orb'], mon('Palkia', { item: 'Lustrous Orb' }), 'Surf', INFERNAPE),
  pick(['griseous-orb'], mon('Giratina-Origin', { item: 'Griseous Orb' }), 'Shadow Force', STARMIE),
  pick(['griseous-orb-wrong-forme'], mon('Giratina', { item: 'Griseous Orb' }), 'Shadow Force', STARMIE),
  pick(['soul-dew-attack'], mon('Latios', { item: 'Soul Dew' }), 'Dragon Pulse', SWAMPERT),
  pick(['soul-dew-defense'], STARMIE, 'Surf', mon('Latias', { item: 'Soul Dew' })),
  pick(['light-ball'], mon('Pikachu', { item: 'Light Ball' }), 'Thunderbolt', STARMIE),
  pick(['light-ball', 'physical'], mon('Pikachu', { item: 'Light Ball' }), 'Volt Tackle', STARMIE),
  pick(['thick-club'], mon('Marowak', { ability: 'Rock Head', item: 'Thick Club' }), 'Earthquake', TYRANITAR),
  pick(['deep-sea-tooth'], mon('Clamperl', { item: 'Deep Sea Tooth' }), 'Surf', INFERNAPE),
  pick(['deep-sea-scale'], STARMIE, 'Thunderbolt', mon('Clamperl', { item: 'Deep Sea Scale' })),
  pick(['metal-powder'], GARCHOMP, 'Earthquake', mon('Ditto', { item: 'Metal Powder' })),
  pick(['metronome-first-use'], mon('Garchomp', { ...GARCHOMP, item: 'Metronome' }), 'Earthquake', SWAMPERT),
  pick(['klutz-ignores-item'], mon('Lopunny', { ability: 'Klutz', item: 'Choice Band' }), 'Return', SWAMPERT),
  // ---- 03b: defender items
  pick(['resist-berry'], INFERNAPE, 'Flamethrower', mon('Skarmory', { ...SKARMORY, item: 'Occa Berry' })),
  pick(['resist-berry-not-super-effective'], INFERNAPE, 'Flamethrower', mon('Swampert', { ...SWAMPERT, item: 'Occa Berry' })),
  pick(['chilan-berry'], SNORLAX, 'Return', mon('Swampert', { ...SWAMPERT, item: 'Chilan Berry' })),
  pick(['resist-berry', 'expert-belt'], mon('Starmie', { ...STARMIE, item: 'Expert Belt' }), 'Ice Beam', mon('Garchomp', { ...GARCHOMP, item: 'Yache Berry' })),
  pick(['iron-ball-grounds-flying'], GARCHOMP, 'Earthquake', mon('Skarmory', { ...SKARMORY, item: 'Iron Ball' })),
  pick(['iron-ball-grounds-levitate'], GARCHOMP, 'Earthquake', mon('Gengar', { ...GENGAR, item: 'Iron Ball' })),
  // ---- 03b: attacker abilities
  pick(['technician'], mon('Scizor', { ability: 'Technician', evs: { atk: 252 } }), 'Bullet Punch', TYRANITAR),
  pick(['technician-over-60'], mon('Scizor', { ability: 'Technician', evs: { atk: 252 } }), 'X-Scissor', TYRANITAR),
  pick(['technician', 'type-item'], mon('Scizor', { ability: 'Technician', item: 'Metal Coat' }), 'Bullet Punch', TYRANITAR),
  pick(['adaptability'], mon('Porygon-Z', { ability: 'Adaptability', evs: { spa: 252 } }), 'Tri Attack', SWAMPERT),
  pick(['huge-power'], mon('Azumarill', { ability: 'Huge Power', evs: { atk: 252 } }), 'Waterfall', INFERNAPE),
  pick(['pure-power'], mon('Medicham', { evs: { atk: 252 } }), 'High Jump Kick', TYRANITAR),
  pick(['guts-burned'], mon('Heracross', { ability: 'Guts', status: 'brn', evs: { atk: 252 } }), 'Close Combat', SWAMPERT),
  pick(['guts-no-status'], mon('Heracross', { ability: 'Guts', evs: { atk: 252 } }), 'Close Combat', SWAMPERT),
  pick(['hustle'], mon('Togekiss', { ability: 'Hustle' }), 'Aerial Ace', INFERNAPE),
  pick(['solar-power'], mon('Sunflora', { ability: 'Solar Power' }), 'Energy Ball', SWAMPERT, { weather: 'sunnyday' }),
  pick(['flower-gift-attack'], mon('Cherrim'), 'Return', SWAMPERT, { weather: 'sunnyday' }),
  pick(['flower-gift-defense'], STARMIE, 'Psychic', mon('Cherrim'), { weather: 'sunnyday' }),
  pick(['slow-start-active'], mon('Regigigas', { ability_on: true }), 'Return', SWAMPERT),
  pick(['blaze-pinch'], mon('Infernape', { ...INFERNAPE, hp: 90 }), 'Flamethrower', SWAMPERT),
  pick(['blaze-above-third'], mon('Infernape', { ...INFERNAPE, hp: 120 }), 'Flamethrower', SWAMPERT),
  pick(['torrent-pinch'], mon('Swampert', { ...SWAMPERT, hp: 100 }), 'Surf', INFERNAPE),
  pick(['overgrow-pinch'], mon('Venusaur', { hp: 50 }), 'Energy Ball', SWAMPERT),
  pick(['swarm-pinch'], mon('Heracross', { ability: 'Swarm', hp: 60 }), 'Megahorn', STARMIE),
  pick(['iron-fist'], mon('Hitmonchan', { ability: 'Iron Fist' }), 'Mach Punch', TYRANITAR),
  pick(['iron-fist-not-a-punch'], mon('Hitmonchan', { ability: 'Iron Fist' }), 'Close Combat', TYRANITAR),
  pick(['reckless'], mon('Hitmonlee', { ability: 'Reckless' }), 'Double-Edge', SWAMPERT),
  pick(['reckless-crash'], mon('Hitmonlee', { ability: 'Reckless' }), 'High Jump Kick', SWAMPERT),
  pick(['flash-fire-boost'], mon('Heatran', { ability_on: true, evs: { spa: 252 } }), 'Flamethrower', SWAMPERT),
  pick(['sniper-crit'], mon('Kingdra', { ability: 'Sniper' }), 'Surf', INFERNAPE),
  pick(['tinted-lens'], mon('Yanmega', { ability: 'Tinted Lens' }), 'Bug Buzz', INFERNAPE),
  pick(['normalize'], mon('Delcatty', { ability: 'Normalize' }), 'Shadow Ball', STARMIE),
  pick(['normalize', 'immune'], mon('Delcatty', { ability: 'Normalize' }), 'Thunderbolt', GENGAR),
  pick(['simple-attacker'], mon('Bibarel', { ability: 'Simple', boosts: { atk: 2 } }), 'Return', SWAMPERT),
  pick(['unaware-attacker'], mon('Bibarel', { ability: 'Unaware' }), 'Return', mon('Swampert', { ...SWAMPERT, boosts: { def: 4 } })),
  pick(['mold-breaker-thick-fat'], RAMPARDOS, 'Fire Punch', mon('Snorlax', { ability: 'Thick Fat' })),
  // ---- 03b: defender abilities
  pick(['thick-fat-fire'], INFERNAPE, 'Flamethrower', mon('Snorlax', { ability: 'Thick Fat' })),
  pick(['thick-fat-ice'], STARMIE, 'Ice Beam', mon('Snorlax', { ability: 'Thick Fat' })),
  pick(['heatproof'], INFERNAPE, 'Flamethrower', mon('Bronzong', { ability: 'Heatproof' })),
  pick(['dry-skin-fire'], INFERNAPE, 'Flamethrower', mon('Toxicroak', { ability: 'Dry Skin' })),
  pick(['filter'], INFERNAPE, 'Flamethrower', mon('Mr. Mime', { ability: 'Filter' })),
  pick(['solid-rock'], STARMIE, 'Surf', mon('Rhyperior', { ability: 'Solid Rock' })),
  pick(['marvel-scale'], GARCHOMP, 'Earthquake', mon('Milotic', { status: 'par' })),
  pick(['battle-armor-no-crit'], GARCHOMP, 'Earthquake', mon('Drapion', { ability: 'Battle Armor' })),
  pick(['shell-armor-no-crit'], GARCHOMP, 'Earthquake', mon('Cloyster', { ability: 'Shell Armor' })),
  pick(['soundproof'], mon('Exploud'), 'Hyper Voice', mon('Mr. Mime', { ability: 'Soundproof' })),
  pick(['simple-defender'], GARCHOMP, 'Earthquake', mon('Bibarel', { ability: 'Simple', boosts: { def: 2 } })),
  pick(['unaware-defender'], mon('Garchomp', { ...GARCHOMP, boosts: { atk: 6 } }), 'Earthquake', mon('Bibarel', { ability: 'Unaware' })),
  // ---- 03b: moves
  pick(['multi-hit'], mon('Cloyster', { ability: 'Shell Armor' }), 'Icicle Spear', GARCHOMP),
  pick(['multi-hit', 'skill-link'], mon('Cloyster', { ability: 'Skill Link' }), 'Icicle Spear', GARCHOMP),
  pick(['multi-hit', 'two-hits'], mon('Hitmonlee', { ability: 'Limber' }), 'Double Kick', TYRANITAR),
  pick(['multi-hit', 'resist-berry'], mon('Cloyster', { ability: 'Shell Armor' }), 'Icicle Spear', mon('Garchomp', { ...GARCHOMP, item: 'Yache Berry' })),
  pick(['low-kick-heavy'], INFERNAPE, 'Low Kick', SNORLAX),
  pick(['low-kick-light'], INFERNAPE, 'Low Kick', mon('Pikachu')),
  pick(['grass-knot'], mon('Roserade', { evs: { spa: 252 } }), 'Grass Knot', SWAMPERT),
  pick(['payback-slower'], TYRANITAR, 'Payback', STARMIE),
  pick(['payback-faster'], mon('Weavile'), 'Payback', SWAMPERT),
  pick(['payback-scarf'], mon('Tyranitar', { ...TYRANITAR, item: 'Choice Scarf', nature: 'Jolly', evs: { spe: 252 } }), 'Payback', mon('Swampert')),
  pick(['payback-paralysis'], mon('Weavile', { status: 'par' }), 'Payback', SWAMPERT),
  pick(['punishment-boosted-target'], mon('Weavile'), 'Punishment', mon('Swampert', { ...SWAMPERT, boosts: { atk: 2, def: 1, spe: -1 } })),
  pick(['punishment-unboosted'], mon('Weavile'), 'Punishment', SWAMPERT),
  pick(['natural-gift'], mon('Snorlax', { ...SNORLAX, item: 'Liechi Berry' }), 'Natural Gift', TYRANITAR),
  pick(['natural-gift-no-berry'], SNORLAX, 'Natural Gift', TYRANITAR),
  pick(['fling'], mon('Snorlax', { ...SNORLAX, item: 'Iron Ball' }), 'Fling', STARMIE),
  pick(['fling-no-item'], SNORLAX, 'Fling', STARMIE),
  pick(['judgment-plate'], mon('Arceus', { item: 'Flame Plate' }), 'Judgment', mon('Scizor', { ability: 'Swarm' })),
  pick(['judgment-no-plate'], mon('Arceus'), 'Judgment', SWAMPERT),
];

// ----------------------------------------------------------------------------- random sweep

// Abilities the sweep never rolls: the oracle changes its own input for them (a stat stage or
// the holder's types), which in a real battle reaches us through the battle log instead.
const CHANGES_ITS_INPUT = new Set(['download', 'forecast']);
// Needs "ability on" to do anything; rolled as active half the time.
const TOGGLED = new Set(['flashfire', 'slowstart']);
// Fixed-damage kinds the oracle implements; it returns 0 for the others.
const ORACLE_FIXED = (kind) => typeof kind === 'number' || kind === 'level';
// Where our rule deliberately follows the simulator instead of the oracle, or the two packages'
// item data differ (Fling). These have hand-picked cases limited to inputs where both agree.
const ORACLE_DISAGREES = new Set(['gyroball', 'fling']);
const SWEEP_MOVES = MOVES.filter(
  (m) =>
    m.category !== 'status' &&
    !ORACLE_DISAGREES.has(m.id) &&
    !m.id.startsWith('hiddenpower') && // the oracle ignores IVs; covered by hand-picked cases
    (m.fixed_damage === undefined || ORACLE_FIXED(m.fixed_damage)),
);
// Items with a damage effect, so the sweep meets them far more often than the other ~150.
const COMMON_DAMAGE_ITEMS = [
  'Choice Band', 'Choice Specs', 'Choice Scarf', 'Life Orb', 'Expert Belt', 'Muscle Band',
  'Wise Glasses', 'Iron Ball', 'Metronome', 'Macho Brace',
];
const DAMAGE_ITEMS = ITEMS.filter(
  (item) => item.boosts_type || item.resists_type || COMMON_DAMAGE_ITEMS.includes(item.name),
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
    } while (CHANGES_ITS_INPUT.has(ability));
    const side = { species: species.name, ability, level: chance(0.5) ? 100 : int(1, 100), nature: choose(NATURES) };
    if (TOGGLED.has(ability)) side.ability_on = chance(0.5);
    if (chance(0.6)) side.item = choose(chance(0.8) ? DAMAGE_ITEMS : ITEMS).name;
    if (chance(0.5)) side.ivs = Object.fromEntries(STATS.map((s) => [s, int(0, 31)]));
    let evBudget = 510;
    side.evs = {};
    for (const stat of STATS) {
      const ev = chance(0.5) ? 0 : Math.min(evBudget, int(0, 252));
      side.evs[stat] = ev;
      evBudget -= ev;
    }
    if (chance(0.4)) side.boosts = Object.fromEntries(['atk', 'def', 'spa', 'spd', 'spe'].map((s) => [s, int(-6, 6)]));
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
