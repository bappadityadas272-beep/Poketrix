// Exports the Gen 1-4 dex snapshot from @pkmn/dex (Pokémon Showdown's data) to
// data/dex/gen{1..4}/{species,moves}.json. Build-time only; Python reads the committed JSON.
//
//   cd scripts && npm install && npm run build-dex
//
// Records use the field names of poketrix.schemas.Species / Move, minus `generation`
// (implied by the folder). Types and categories are lowercased to match the schema enums.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { Dex, toID } from '@pkmn/dex';

const GENS = [1, 2, 3, 4];
const FIRST_GEN_WITH_ABILITIES = 3;
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, '..', 'data', 'dex');

// Showdown keeps later-gen and fan-made entries in every gen's dex, flagged isNonstandard.
const existsIn = (gen) => (entry) => !entry.isNonstandard && entry.gen <= gen;

function speciesRecord(dex, s) {
  // Showdown lists a species' modern abilities in every gen; keep those that exist in this one.
  const abilities =
    dex.gen < FIRST_GEN_WITH_ABILITIES
      ? []
      : Object.values(s.abilities)
          .map((name) => dex.abilities.get(name))
          .filter(existsIn(dex.gen))
          .map((a) => a.id);
  return {
    id: s.id,
    name: s.name,
    dex_number: s.num,
    types: s.types.map((t) => t.toLowerCase()),
    base_stats: s.baseStats,
    possible_abilities: abilities,
  };
}

// Deliberate departures from Showdown, keyed by `gen:moveid`.
// Gen 1 Bide is Normal-type on cartridge; Showdown's "???" is an engine device for ignoring
// type effectiveness, and typeless moves only exist from Gen 2 in our schemas.
const MOVE_TYPE_OVERRIDES = { '1:bide': 'normal' };

// Showdown gives the 16 typed Hidden Powers ("Hidden Power Fire") the shared id `hiddenpower`.
// Key them by their own name so ids stay unique and match the ids used in set pools.
const moveId = (m) => toID(m.name);

function moveRecord(gen, m) {
  const id = moveId(m);
  return {
    id,
    name: m.name,
    type: MOVE_TYPE_OVERRIDES[`${gen}:${id}`] ?? m.type.toLowerCase(),
    category: m.category.toLowerCase(),
    base_power: m.basePower,
    accuracy: m.accuracy === true ? null : m.accuracy,
    pp: m.pp,
    priority: m.priority,
  };
}

// One record per line: compact, and a data change shows up as a one-line git diff.
function writeRecords(path, records) {
  writeFileSync(path, `[\n${records.map((r) => JSON.stringify(r)).join(',\n')}\n]\n`);
}

for (const gen of GENS) {
  const dex = Dex.forGen(gen);
  const species = dex.species
    .all()
    .filter(existsIn(gen))
    .sort((a, b) => a.num - b.num || a.id.localeCompare(b.id))
    .map((s) => speciesRecord(dex, s));
  const moves = dex.moves
    .all()
    .filter(existsIn(gen))
    .sort((a, b) => moveId(a).localeCompare(moveId(b)))
    .map((m) => moveRecord(gen, m));

  const dir = join(OUT_DIR, `gen${gen}`);
  mkdirSync(dir, { recursive: true });
  writeRecords(join(dir, 'species.json'), species);
  writeRecords(join(dir, 'moves.json'), moves);
  console.log(`gen${gen}: ${species.length} species, ${moves.length} moves`);
}

const { version } = JSON.parse(
  readFileSync(join(HERE, 'node_modules', '@pkmn', 'dex', 'package.json'), 'utf8'),
);
writeFileSync(
  join(OUT_DIR, 'manifest.json'),
  `${JSON.stringify({ source: '@pkmn/dex', version, generations: GENS }, null, 2)}\n`,
);
