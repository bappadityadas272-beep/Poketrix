// Plays Random Battles in the simulator for a program that talks to it over stdin and stdout.
// A development tool for measuring win rates (see `python -m poketrix.arena`); the engine
// itself never runs it.
//
// One JSON object per line, in both directions. One battle at a time.
//
//   in   {"cmd":"start","gen":4,"index":7,"swap":false,"p1":"external","p2":"random"}
//        {"cmd":"choose","side":"p1","choice":"move 2"}
//   out  {"game":3,"side":"p1","chunk":"<what that player's stream received>"}   external sides
//        {"game":3,"end":true,"winner":"p1"|"p2"|null,"turns":42}
//
// Teams and the battle are fixed by (gen, index). With "swap" the two sides exchange teams,
// so that a pair of games (swap false, then true) cancels most of the luck of the draw.
// A "random" side is the simulator's own RandomPlayerAI.
//
// `game` counts the battles started. A finished battle's streams may still deliver their last
// lines after the next one has begun, so the reader must drop messages of an earlier game.

import { createInterface } from 'node:readline';

import { BattleStream, RandomPlayerAI, SOURCE, Teams, getPlayerStreams } from './simulator.mjs';

const BASE_SEED = 20261401;
const NAMES = { p1: 'Player One', p2: 'Player Two' };
const say = (message) => process.stdout.write(`${JSON.stringify(message)}\n`);

let streams = null;
let game = 0;

async function relay(stream, side, number) {
  for await (const chunk of stream) say({ game: number, side, chunk });
}

async function watch(omniscient, number) {
  let turns = 0;
  for await (const chunk of omniscient) {
    for (const line of chunk.split('\n')) {
      if (line.startsWith('|turn|')) turns = Number(line.slice(6));
      else if (line.startsWith('|win|')) {
        const winner = line.slice(5) === NAMES.p1 ? 'p1' : 'p2';
        say({ game: number, end: true, winner, turns });
      } else if (line === '|tie') say({ game: number, end: true, winner: null, turns });
    }
  }
}

function start({ gen, index, swap, p1, p2 }) {
  const format = `gen${gen}randombattle`;
  const seed = [BASE_SEED, gen, index & 0xffff, index >>> 16];
  const teams = [1, 2].map((n) => Teams.generate(format, { seed: [gen, seed[2], seed[3], n] }));
  if (swap) teams.reverse();
  streams = getPlayerStreams(new BattleStream());
  game += 1;
  void watch(streams.omniscient, game);
  for (const [side, kind] of [['p1', p1], ['p2', p2]]) {
    if (kind === 'external') void relay(streams[side], side, game);
    else void new RandomPlayerAI(streams[side], { seed: [gen, seed[2], seed[3], 33] }).start();
  }
  void streams.omniscient.write(
    `>start ${JSON.stringify({ formatid: format, seed })}\n` +
      `>player p1 ${JSON.stringify({ name: NAMES.p1, team: Teams.pack(teams[0]) })}\n` +
      `>player p2 ${JSON.stringify({ name: NAMES.p2, team: Teams.pack(teams[1]) })}`,
  );
}

say({ ready: true, simulator: SOURCE });
for await (const line of createInterface({ input: process.stdin })) {
  if (!line.trim()) continue;
  const message = JSON.parse(line);
  if (message.cmd === 'start') start(message);
  else if (message.cmd === 'choose') void streams[message.side].write(message.choice);
}
process.exit(0);
