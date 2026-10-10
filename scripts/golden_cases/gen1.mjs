// Gen 1 golden cases: the hand-picked list (one case per mechanic) and the random sweep's settings.
// `mon` builds a side, `pick` a tagged case; both come from build_calc_golden.mjs.
// Spreads are in our units: `ivs` are DVs (0-15), `evs` are Stat Exp (0-65535); omitted = maximum.
// Special is one stat: the spa and spd values of a side are always equal.

export const sweepSize = 200;
export const sweepSeed = 20261015;

export function handPicked({ mon, pick }) {
  const TAUROS = mon('Tauros');
  const STARMIE = mon('Starmie');
  const ALAKAZAM = mon('Alakazam');
  const SNORLAX = mon('Snorlax');
  const GENGAR = mon('Gengar');
  const EXEGGUTOR = mon('Exeggutor');
  const CHANSEY = mon('Chansey');
  const ZAPDOS = mon('Zapdos');
  const RHYDON = mon('Rhydon');
  const JOLTEON = mon('Jolteon');
  const LAPRAS = mon('Lapras');
  const CHARIZARD = mon('Charizard');

  return [
    // type effectiveness and STAB
    pick(['neutral', 'stab'], TAUROS, 'Body Slam', STARMIE),
    pick(['neutral', 'no-stab'], TAUROS, 'Earthquake', ALAKAZAM),
    pick(['2x', 'stab'], ZAPDOS, 'Thunderbolt', STARMIE),
    pick(['4x'], STARMIE, 'Surf', RHYDON),
    pick(['4x'], ZAPDOS, 'Thunderbolt', mon('Gyarados')),
    pick(['half'], ZAPDOS, 'Thunderbolt', EXEGGUTOR),
    pick(['quarter'], EXEGGUTOR, 'Mega Drain', CHARIZARD),
    pick(['immune'], TAUROS, 'Earthquake', ZAPDOS),
    pick(['immune'], TAUROS, 'Body Slam', GENGAR),
    // the Gen 1 type chart's differences
    pick(['gen1-chart', 'ghost-vs-psychic-immune'], GENGAR, 'Lick', ALAKAZAM),
    pick(['gen1-chart', 'bug-vs-poison-2x'], mon('Golbat'), 'Leech Life', mon('Weezing')),
    pick(['gen1-chart', 'poison-vs-bug-2x'], mon('Beedrill'), 'Poison Sting', mon('Butterfree')),
    pick(['gen1-chart', 'ice-vs-fire-neutral'], LAPRAS, 'Ice Beam', mon('Arcanine')),
    // dual types: the two factors are floored one after the other, in the species' own order
    pick(['dual-type-order'], LAPRAS, 'Ice Beam', mon('Dragonite')),
    pick(['dual-type-order'], LAPRAS, 'Ice Beam', CHARIZARD),
    pick(['dual-type-order'], ALAKAZAM, 'Psychic', GENGAR),
    pick(['dual-type-order'], TAUROS, 'Body Slam', RHYDON),
    pick(['dual-type-order'], RHYDON, 'Rock Slide', CHARIZARD),
    pick(['dual-type-order'], STARMIE, 'Surf', mon('Tentacruel')),
    pick(['dual-type-order'], STARMIE, 'Blizzard', mon('Dewgong')),
    // stat stages (a critical hit ignores all of them and doubles the level instead)
    pick(['boost'], mon('Tauros', { boosts: { atk: 2 } }), 'Body Slam', SNORLAX),
    pick(['drop'], mon('Tauros', { boosts: { atk: -1 } }), 'Body Slam', SNORLAX),
    pick(['defense-boost'], TAUROS, 'Body Slam', mon('Snorlax', { boosts: { def: 2 } })),
    pick(['special-boost'], mon('Alakazam', { boosts: { spa: 2, spd: 2 } }), 'Psychic', SNORLAX),
    pick(['special-drop-on-defender'], STARMIE, 'Surf', mon('Chansey', { boosts: { spa: -2, spd: -2 } })),
    pick(['max-stages'], mon('Tauros', { boosts: { atk: 6 } }), 'Body Slam', mon('Snorlax', { boosts: { def: -6 } })),
    pick(['min-stages'], mon('Starmie', { boosts: { spa: -6, spd: -6 } }), 'Surf', mon('Chansey', { boosts: { spa: 6, spd: 6 } })),
    // burn and screens
    pick(['burn'], mon('Tauros', { status: 'brn' }), 'Body Slam', SNORLAX),
    pick(['burn-special-unaffected'], mon('Starmie', { status: 'brn' }), 'Surf', SNORLAX),
    pick(['reflect'], TAUROS, 'Body Slam', SNORLAX, { reflect: true }),
    pick(['reflect-vs-special'], STARMIE, 'Surf', SNORLAX, { reflect: true }),
    pick(['light-screen'], STARMIE, 'Surf', SNORLAX, { light_screen: true }),
    // high-crit moves: the oracle only computes their critical hit
    pick(['high-crit-move'], mon('Persian'), 'Slash', SNORLAX),
    pick(['high-crit-move'], mon('Venusaur'), 'Razor Leaf', STARMIE),
    pick(['high-crit-move'], mon('Kingler'), 'Crabhammer', RHYDON),
    pick(['high-crit-move'], mon('Machamp'), 'Karate Chop', SNORLAX),
    // defense-halving moves, level extremes, the byte limits
    pick(['explosion'], EXEGGUTOR, 'Explosion', CHANSEY),
    pick(['self-destruct'], SNORLAX, 'Self-Destruct', STARMIE),
    pick(['level-1-attacker', 'base-damage-1'], mon('Rattata', { level: 1 }), 'Tackle', mon('Golem')),
    pick(['level-1-attacker', 'zero-damage'], mon('Weedle', { level: 1 }), 'Poison Sting', GENGAR),
    pick(['level-1-defender', 'damage-cap'], mon('Snorlax', { boosts: { atk: 6 } }), 'Self-Destruct', mon('Rattata', { level: 1 })),
    pick(['level-50'], mon('Tauros', { level: 50 }), 'Body Slam', mon('Snorlax', { level: 50 })),
    pick(['byte-rollover', 'attack-over-255'], mon('Tauros', { boosts: { atk: 1 } }), 'Hyper Beam', SNORLAX),
    pick(['byte-rollover', 'defense-over-255'], TAUROS, 'Body Slam', mon('Cloyster', { boosts: { def: 1 } })),
    pick(['byte-rollover', 'special-999'], mon('Alakazam', { boosts: { spa: 6, spd: 6 } }), 'Psychic', SNORLAX),
    pick(['byte-rollover', 'reflect-doubles-first'], TAUROS, 'Body Slam', mon('Cloyster'), { reflect: true }),
    // DVs and Stat Exp
    pick(['min-dvs'], mon('Tauros', { ivs: { atk: 0, def: 0, spe: 0, spa: 0, spd: 0 } }), 'Body Slam', SNORLAX),
    pick(['no-stat-exp'], mon('Tauros', { evs: { hp: 0, atk: 0, def: 0, spe: 0, spa: 0, spd: 0 } }), 'Body Slam', mon('Snorlax', { evs: { hp: 0, def: 0 } })),
    pick(['partial-stat-exp'], mon('Starmie', { evs: { spa: 10000, spd: 10000 } }), 'Surf', mon('Snorlax', { evs: { hp: 2500, spa: 400, spd: 400 } })),
    // fixed damage (in Gen 1 it ignores type immunity)
    pick(['fixed-level', 'hits-ghost'], CHANSEY, 'Seismic Toss', GENGAR),
    pick(['fixed-level'], CHANSEY, 'Seismic Toss', SNORLAX),
    pick(['fixed-level', 'hits-normal', 'level-73'], mon('Gengar', { level: 73 }), 'Night Shade', SNORLAX),
    pick(['fixed-flat', 'hits-ghost'], mon('Magnemite'), 'Sonic Boom', GENGAR),
    pick(['fixed-flat'], mon('Dragonair'), 'Dragon Rage', CHANSEY),
    // Struggle is an ordinary Normal move in Gen 1
    pick(['struggle-is-normal', 'immune'], SNORLAX, 'Struggle', GENGAR),
    pick(['struggle-is-normal', 'stab'], SNORLAX, 'Struggle', STARMIE),
    // multi-hit moves (the oracle lists the same rolls for every hit)
    pick(['multi-hit'], JOLTEON, 'Pin Missile', EXEGGUTOR),
    pick(['multi-hit', 'two-hits'], JOLTEON, 'Double Kick', SNORLAX),
    pick(['multi-hit', 'two-hits'], mon('Beedrill'), 'Twineedle', ALAKAZAM),
    pick(['multi-hit'], mon('Fearow'), 'Fury Attack', STARMIE),
    // a few everyday matchups
    pick(['everyday'], TAUROS, 'Hyper Beam', ALAKAZAM),
    pick(['everyday'], SNORLAX, 'Body Slam', TAUROS),
    pick(['everyday'], ALAKAZAM, 'Psychic', EXEGGUTOR),
    pick(['everyday'], STARMIE, 'Blizzard', RHYDON),
    pick(['everyday'], CHARIZARD, 'Fire Blast', EXEGGUTOR),
  ];
}
