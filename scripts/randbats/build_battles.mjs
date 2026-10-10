// Plays seeded Random Battles with Showdown's own simulator and two random players, and saves
// what each viewer receives together with both true teams. Build-time only.
//
//   cd scripts/randbats && npm install
//   npm run build-battles                 the committed fixtures: 10 battles per generation
//   node build_battles.mjs 500 raw        500 per generation into data/raw/battles/ (git-ignored)
//
// The parser's evidence rules are checked against these, because here the truth is known:
// a move the parser calls "revealed" must be in the true set, a ruled-out item must not be the
// true item, and so on. Random players do not play like people, but they exercise the mechanics.
//
// One file per generation: {"source": {...}, "battles": [{seed, teams, spectator}]}.
// `spectator` is the public log, which is what a saved replay contains.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import showdown from 'pokemon-showdown';
import randomPlayer from 'pokemon-showdown/dist/sim/tools/random-player-ai.js';

const { BattleStream, getPlayerStreams, Teams } = showdown;
const { RandomPlayerAI } = randomPlayer;

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const ALL_GENS = [1, 2, 3, 4];
const FIXTURE_BATTLES = 10;
const BASE_SEED = 20261201;
const { version: SIMULATOR_VERSION } = JSON.parse(
  readFileSync(join(HERE, 'node_modules', 'pokemon-showdown', 'package.json'), 'utf8'),
);

const toID = (text) => text.toLowerCase().replace(/[^a-z0-9]/g, '');

// The true set of one Pokémon, in the ids the dex uses. `name` is what the log calls it.
const truth = (gen, pokemon) => ({
  name: pokemon.name,
  species: pokemon.species,
  level: pokemon.level,
  moves: pokemon.moves.map(toID),
  item: pokemon.item ? toID(pokemon.item) : null,
  ability: gen >= 3 ? toID(pokemon.ability) : null,
});

async function collect(stream) {
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return chunks.join('\n');
}

async function play(gen, index) {
  const format = `gen${gen}randombattle`;
  const seed = [BASE_SEED, gen, index & 0xffff, index >>> 16];
  const teams = {
    p1: Teams.generate(format, { seed: [...seed, 1].slice(1) }),
    p2: Teams.generate(format, { seed: [...seed, 2].slice(1) }),
  };
  const streams = getPlayerStreams(new BattleStream());
  const spectator = collect(streams.spectator);
  const p1 = new RandomPlayerAI(streams.p1, { seed: [seed[1], seed[2], seed[3], 11] });
  const p2 = new RandomPlayerAI(streams.p2, { seed: [seed[1], seed[2], seed[3], 22] });
  void p1.start();
  void p2.start();
  void streams.omniscient.write(
    `>start ${JSON.stringify({ formatid: format, seed })}\n` +
      `>player p1 ${JSON.stringify({ name: 'Player One', team: Teams.pack(teams.p1) })}\n` +
      `>player p2 ${JSON.stringify({ name: 'Player Two', team: Teams.pack(teams.p2) })}`,
  );
  return {
    seed,
    teams: { p1: teams.p1.map((p) => truth(gen, p)), p2: teams.p2.map((p) => truth(gen, p)) },
    spectator: await spectator,
  };
}

const count = Number(process.argv[2]) || FIXTURE_BATTLES;
const outDir = process.argv[3] === 'raw' ? join(ROOT, 'data', 'raw', 'battles') : join(ROOT, 'tests', 'fixtures');
mkdirSync(outDir, { recursive: true });
for (const gen of ALL_GENS) {
  const battles = [];
  for (let index = 0; index < count; index++) battles.push(await play(gen, index));
  const source = { simulator: 'pokemon-showdown', version: SIMULATOR_VERSION, format: `gen${gen}randombattle`, base_seed: BASE_SEED };
  const path = join(outDir, `battles_gen${gen}.json`);
  writeFileSync(path, `{"source":${JSON.stringify(source)},"battles":[\n${battles.map((b) => JSON.stringify(b)).join(',\n')}\n]}\n`);
  console.log(`gen${gen}: ${battles.length} battles -> ${path}`);
}
