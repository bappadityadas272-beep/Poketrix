// Builds the Random Battle set tables for Gens 1-4 by sampling Showdown's official team
// generator. Build-time only; Python reads the committed JSON.
//
//   cd scripts/randbats && npm install && npm run build-randbats      (all generations)
//   node build_randbats.mjs 4                                         (one generation)
//
// Two tables per generation, from different seeds, in the same format:
//   data/randbats/gen{N}/sets.json                 the prior (PRIOR.teams teams)
//   tests/fixtures/randbats_holdout_gen{N}.json    held-out teams for the evaluation
//
// One row per distinct set: species, level, moves, item, ability, spread and how often the
// generator produced it. Spreads are in our units (Gens 1-2: DVs and Stat Exp; a value at the
// generation's default is omitted). Ids are Showdown ids, as everywhere in the dex.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import showdown from 'pokemon-showdown';

const { Dex, Teams } = showdown;

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const ALL_GENS = [1, 2, 3, 4];
const PRIOR = { seed: 20261101, teams: 100000 };
const HOLDOUT = { seed: 20261102, teams: 20000 };
const STATS = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
const { version: GENERATOR_VERSION } = JSON.parse(
  readFileSync(join(HERE, 'node_modules', 'pokemon-showdown', 'package.json'), 'utf8'),
);

const toID = (text) => text.toLowerCase().replace(/[^a-z0-9]/g, '');

// What the generator gives every Pokémon unless the set calls for something else.
function defaultSpread(gen) {
  return gen <= 2 ? { iv: 15, ev: 65535 } : { iv: 31, ev: 85 };
}

// The generator's IVs and EVs in our units, keeping only what differs from the default.
function spreadOf(gen, pokemon) {
  const fallback = defaultSpread(gen);
  const ivs = {};
  const evs = {};
  for (const stat of STATS) {
    // Gens 1-2: Showdown stores a DV as an even IV and maximum Stat Exp as EV 255. The HP DV is
    // derived from the other four, so it is never stored.
    const iv = gen <= 2 ? Math.floor(pokemon.ivs[stat] / 2) : pokemon.ivs[stat];
    const ev = gen <= 2 ? (pokemon.evs[stat] >= 255 ? 65535 : pokemon.evs[stat] ** 2) : pokemon.evs[stat];
    if (iv !== fallback.iv && !(gen <= 2 && stat === 'hp')) ivs[stat] = iv;
    if (ev !== fallback.ev) evs[stat] = ev;
  }
  return { ivs, evs };
}

function sample(gen, { seed, teams }, speciesIds) {
  const format = `gen${gen}randombattle`;
  const rows = new Map(); // set key -> row
  // The generator has formes our dex does not list separately (the Unown letters): use the base.
  const speciesId = (name) => {
    const id = toID(name);
    if (speciesIds.has(id)) return id;
    const base = toID(Dex.species.get(name).baseSpecies);
    if (!speciesIds.has(base)) throw new Error(`gen${gen}: ${name} is not in the dex snapshot`);
    return base;
  };
  for (let i = 0; i < teams; i++) {
    for (const pokemon of Teams.generate(format, { seed: [seed, i & 0xffff, i >>> 16, gen] })) {
      const row = {
        species: speciesId(pokemon.species),
        level: pokemon.level,
        moves: pokemon.moves.map(toID).sort(),
        item: pokemon.item ? toID(pokemon.item) : null,
        ability: gen >= 3 ? toID(pokemon.ability) : null,
        ...spreadOf(gen, pokemon),
      };
      const key = [row.species, row.moves.join(','), row.item, row.ability].join('|');
      const seen = rows.get(key);
      if (!seen) {
        rows.set(key, { ...row, count: 1 });
        continue;
      }
      // A hypothesis must determine its stats: the same set never comes with two spreads.
      const same = ['level', 'ivs', 'evs'].every((f) => JSON.stringify(seen[f]) === JSON.stringify(row[f]));
      if (!same) throw new Error(`gen${gen}: set ${key} appears with two different levels or spreads`);
      seen.count++;
    }
  }
  return [...rows.values()].sort(
    (a, b) => a.species.localeCompare(b.species) || b.count - a.count || a.moves.join().localeCompare(b.moves.join()),
  );
}

function write(path, gen, source, rows) {
  const header = {
    generator: 'pokemon-showdown',
    version: GENERATOR_VERSION,
    format: `gen${gen}randombattle`,
    seed: source.seed,
    teams: source.teams,
    default_spread: defaultSpread(gen),
  };
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(
    path,
    `{"source":${JSON.stringify(header)},"sets":[\n${rows.map((r) => JSON.stringify(r)).join(',\n')}\n]}\n`,
  );
}

const requested = process.argv.slice(2).map(Number);
for (const gen of requested.length ? requested : ALL_GENS) {
  const dexSpecies = JSON.parse(readFileSync(join(ROOT, 'data', 'dex', `gen${gen}`, 'species.json'), 'utf8'));
  const speciesIds = new Set(dexSpecies.map((s) => s.id));
  const prior = sample(gen, PRIOR, speciesIds);
  const holdout = sample(gen, HOLDOUT, speciesIds);
  write(join(ROOT, 'data', 'randbats', `gen${gen}`, 'sets.json'), gen, PRIOR, prior);
  write(join(ROOT, 'tests', 'fixtures', `randbats_holdout_gen${gen}.json`), gen, HOLDOUT, holdout);
  console.log(`gen${gen}: prior ${prior.length} sets, holdout ${holdout.length} sets`);
}
