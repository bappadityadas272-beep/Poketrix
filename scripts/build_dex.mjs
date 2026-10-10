// Exports the Gen 1-4 dex snapshot from @pkmn/dex (Pokémon Showdown's data) to
// data/dex/gen{1..4}/{species,moves,typechart}.json, data/dex/gen{2..4}/items.json and
// data/dex/natures.json.
// Build-time only; Python reads the committed JSON.
//
//   cd scripts && npm install && npm run build-dex
//
// Records use the field names of poketrix.schemas.Species / Move, minus `generation`
// (implied by the folder) and minus fields left at their schema default. Types and categories
// are lowercased to match the schema enums.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { Dex, toID } from '@pkmn/dex';
// Which item boosts or resists which type is code, not data, in Showdown; the damage oracle
// keeps it as lookup functions, so those two columns are read from there.
import oracleItems from '@smogon/calc/dist/items.js';

const GENS = [1, 2, 3, 4];
const FIRST_GEN_WITH_ABILITIES = 3;
const FIRST_GEN_WITH_ITEMS = 2;
const FIRST_GEN_WITH_BERRY_EFFECTS = 4; // resist berries, Fling, Natural Gift
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
    weight_kg: s.weightkg,
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

// Fixed-damage moves that Showdown implements as code callbacks rather than data.
const CALLBACK_FIXED_DAMAGE = {
  superfang: 'half_hp',
  psywave: 'psywave',
  endeavor: 'endeavor',
  counter: 'reactive',
  mirrorcoat: 'reactive',
  metalburst: 'reactive',
  bide: 'reactive',
};

// Moves that deal typeless damage (no type effectiveness, no STAB), by generation.
const TYPELESS_DAMAGE = {
  bide: [1],
  struggle: [2, 3, 4],
  futuresight: [2, 3, 4],
  doomdesire: [3, 4],
};

function fixedDamage(m) {
  if (m.ohko) return 'ohko';
  if (m.damage !== undefined && m.damage !== null) return m.damage; // a number or 'level'
  return CALLBACK_FIXED_DAMAGE[m.id];
}

function moveRecord(gen, m) {
  const id = moveId(m);
  const fixed = m.category === 'Status' ? undefined : fixedDamage(m);
  const record = {
    id,
    name: m.name,
    type: MOVE_TYPE_OVERRIDES[`${gen}:${id}`] ?? m.type.toLowerCase(),
    category: m.category.toLowerCase(),
    // Showdown's Gen 1 data uses 1 as a placeholder power for fixed-damage moves.
    base_power: fixed === undefined ? m.basePower : 0,
    accuracy: m.accuracy === true ? null : m.accuracy,
    pp: m.pp,
    priority: m.priority,
  };
  if (fixed !== undefined) record.fixed_damage = fixed;
  if (TYPELESS_DAMAGE[id]?.includes(gen)) record.ignores_type_chart = true;
  if (m.critRatio !== 1) record.crit_ratio = m.critRatio;
  if (m.multihit) record.multihit = [m.multihit].flat().slice(0, 2);
  if (record.multihit?.length === 1) record.multihit.push(record.multihit[0]);
  const flags = [
    m.flags.punch && 'punch',
    m.flags.sound && 'sound',
    (m.recoil || m.hasCrashDamage) && 'recoil',
  ].filter(Boolean);
  if (flags.length) record.flags = flags;
  return record;
}

function itemRecord(dex, item) {
  // A type name, lowercased, if that type exists in this generation.
  const typeIn = (name) => {
    const type = name && dex.types.get(name);
    return type && type.exists && !type.isNonstandard ? name.toLowerCase() : undefined;
  };
  const record = { id: item.id, name: item.name };
  const boosts = typeIn(oracleItems.getItemBoostType(item.name));
  if (boosts) record.boosts_type = boosts;
  if (typeIn(item.onPlate)) record.plate_type = typeIn(item.onPlate);
  if (dex.gen >= FIRST_GEN_WITH_BERRY_EFFECTS) {
    const resists = typeIn(oracleItems.getBerryResistType(item.name));
    if (resists) record.resists_type = resists;
    if (item.fling?.basePower) record.fling_power = item.fling.basePower;
    if (item.naturalGift) {
      record.natural_gift_type = item.naturalGift.type.toLowerCase();
      record.natural_gift_power = item.naturalGift.basePower;
    }
  }
  return record;
}

// Showdown's damageTaken codes, read from the defending type's side.
const DAMAGE_TAKEN_MULTIPLIER = { 1: 2, 2: 0.5, 3: 0 };

// attacking type -> defending type -> multiplier; neutral (1x) pairs are omitted.
function typeChart(dex) {
  const types = dex.types.all().filter((t) => !t.isNonstandard);
  const chart = {};
  for (const attacking of types) {
    const row = {};
    for (const defending of types) {
      const multiplier = DAMAGE_TAKEN_MULTIPLIER[defending.damageTaken[attacking.name]];
      if (multiplier !== undefined) row[defending.id] = multiplier;
    }
    chart[attacking.id] = row;
  }
  return chart;
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
  writeFileSync(join(dir, 'typechart.json'), `${JSON.stringify(typeChart(dex), null, 1)}
`);
  if (gen >= FIRST_GEN_WITH_ITEMS) {
    const items = dex.items
      .all()
      .filter(existsIn(gen))
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((item) => itemRecord(dex, item));
    writeRecords(join(dir, 'items.json'), items);
  }
  console.log(`gen${gen}: ${species.length} species, ${moves.length} moves`);
}

// Natures are the same in every generation that has them: id -> raised / lowered stat.
const natures = Object.fromEntries(
  Dex.forGen(4)
    .natures.all()
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((n) => [n.id, n.plus ? { plus: n.plus, minus: n.minus } : {}]),
);
writeRecords(
  join(OUT_DIR, 'natures.json'),
  Object.entries(natures).map(([id, effect]) => ({ id, ...effect })),
);

const { version } = JSON.parse(
  readFileSync(join(HERE, 'node_modules', '@pkmn', 'dex', 'package.json'), 'utf8'),
);
writeFileSync(
  join(OUT_DIR, 'manifest.json'),
  `${JSON.stringify({ source: '@pkmn/dex', version, generations: GENS }, null, 2)}\n`,
);
