// Which pokemon-showdown the build scripts run.
//
// By default the pinned npm package. The npm releases are rare, and the live server's Random
// Battle sets move on between them, so a built git checkout can be used instead:
//
//   git clone --depth 1 https://github.com/smogon/pokemon-showdown.git  (outside this repository)
//   cd pokemon-showdown && npm install && node build
//   set POKETRIX_SHOWDOWN_DIR=<that folder>
//
// `SOURCE` goes into every file the scripts write, so a table can be traced to its source.

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const checkout = process.env.POKETRIX_SHOWDOWN_DIR;
const home = checkout || join(HERE, 'node_modules', 'pokemon-showdown');
const load = createRequire(join(home, 'package.json'));

export const { BattleStream, Dex, Teams, getPlayerStreams } = load('./dist/sim/index.js');
export const { RandomPlayerAI } = load('./dist/sim/tools/random-player-ai.js');

const { version } = JSON.parse(readFileSync(join(home, 'package.json'), 'utf8'));
const git = (...args) => execFileSync('git', ['-C', home, ...args], { encoding: 'utf8' }).trim();

// A checkout is named by its commit: the version number alone does not change between releases.
export const SOURCE = checkout
  ? { version, commit: git('rev-parse', 'HEAD'), commit_date: git('log', '-1', '--format=%cs') }
  : { version };
