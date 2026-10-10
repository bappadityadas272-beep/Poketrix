// Gen 2 golden cases: the hand-picked list (one case per mechanic) and the random sweep's settings.
// `mon` builds a side, `pick` a tagged case; both come from build_calc_golden.mjs.
// Spreads are in our units: `ivs` are DVs (0-15), `evs` are Stat Exp (0-65535); omitted = maximum.

export const sweepSize = 200;
export const sweepSeed = 20261014;

export function handPicked({ mon, pick }) {
  const SNORLAX = mon('Snorlax');
  const STARMIE = mon('Starmie');
  const ZAPDOS = mon('Zapdos');
  const TYRANITAR = mon('Tyranitar');
  const SKARMORY = mon('Skarmory');
  const GENGAR = mon('Gengar');
  const BLISSEY = mon('Blissey');
  const MACHAMP = mon('Machamp');
  const CHARIZARD = mon('Charizard');
  const EXEGGUTOR = mon('Exeggutor');
  const SUICUNE = mon('Suicune');
  const DRAGONITE = mon('Dragonite');

  return [
    // type effectiveness and STAB (the two type factors are multiplied before the one floor)
    pick(['neutral', 'stab'], SNORLAX, 'Body Slam', STARMIE),
    pick(['neutral', 'no-stab'], SNORLAX, 'Earthquake', STARMIE),
    pick(['2x', 'stab'], STARMIE, 'Surf', CHARIZARD),
    pick(['4x'], ZAPDOS, 'Thunderbolt', mon('Gyarados')),
    pick(['4x', 'fighting-vs-dark-rock'], MACHAMP, 'Cross Chop', TYRANITAR),
    pick(['half'], CHARIZARD, 'Flamethrower', STARMIE),
    pick(['quarter'], CHARIZARD, 'Flamethrower', mon('Kingdra')),
    pick(['immune'], SNORLAX, 'Earthquake', ZAPDOS),
    pick(['immune'], SNORLAX, 'Body Slam', GENGAR),
    pick(['steel-resists-ghost'], GENGAR, 'Shadow Ball', SKARMORY),
    pick(['dark-is-special'], TYRANITAR, 'Crunch', STARMIE),
    pick(['dual-type-product'], STARMIE, 'Ice Beam', DRAGONITE),
    pick(['dual-type-product'], STARMIE, 'Surf', mon('Kingdra')),
    pick(['dual-type-product'], ZAPDOS, 'Thunderbolt', mon('Lanturn')),
    pick(['dual-type-product'], CHARIZARD, 'Fire Blast', mon('Scizor')),
    // stat stages and the Gen 2 critical-hit rule (stages count only if they favour the attacker)
    pick(['boost', 'crit-keeps-stages'], mon('Snorlax', { boosts: { atk: 2 } }), 'Body Slam', SUICUNE),
    pick(['drop', 'crit-ignores-stages'], mon('Snorlax', { boosts: { atk: -1 } }), 'Body Slam', SUICUNE),
    pick(['defense-boost', 'crit-ignores-stages'], SNORLAX, 'Body Slam', mon('Suicune', { boosts: { def: 2 } })),
    pick(['equal-stages', 'crit-ignores-stages'], mon('Snorlax', { boosts: { atk: 1 } }), 'Body Slam', mon('Suicune', { boosts: { def: 1 } })),
    pick(['defense-drop', 'crit-keeps-stages'], STARMIE, 'Surf', mon('Blissey', { boosts: { spd: -2 } })),
    pick(['max-stages'], mon('Machamp', { boosts: { atk: 6 } }), 'Cross Chop', mon('Suicune', { boosts: { def: -6 } })),
    pick(['min-stages'], mon('Starmie', { boosts: { spa: -6 } }), 'Psychic', mon('Blissey', { boosts: { spd: 6 } })),
    // burn and screens (a critical hit that ignores stages also ignores them)
    pick(['burn'], mon('Snorlax', { status: 'brn' }), 'Body Slam', SUICUNE),
    pick(['burn', 'crit-keeps-stages'], mon('Snorlax', { status: 'brn', boosts: { atk: 1 } }), 'Body Slam', SUICUNE),
    pick(['burn-special-unaffected'], mon('Starmie', { status: 'brn' }), 'Surf', SNORLAX),
    pick(['reflect'], SNORLAX, 'Body Slam', SUICUNE, { reflect: true }),
    pick(['reflect', 'crit-keeps-stages'], mon('Snorlax', { boosts: { atk: 2 } }), 'Body Slam', SUICUNE, { reflect: true }),
    pick(['reflect-vs-special'], STARMIE, 'Surf', SNORLAX, { reflect: true }),
    pick(['light-screen'], STARMIE, 'Surf', SNORLAX, { light_screen: true }),
    // weather
    pick(['sun-fire'], CHARIZARD, 'Flamethrower', SNORLAX, { weather: 'sunnyday' }),
    pick(['sun-water'], STARMIE, 'Surf', CHARIZARD, { weather: 'sunnyday' }),
    pick(['rain-water'], STARMIE, 'Surf', CHARIZARD, { weather: 'raindance' }),
    pick(['rain-fire'], CHARIZARD, 'Flamethrower', SNORLAX, { weather: 'raindance' }),
    pick(['solar-beam-rain'], EXEGGUTOR, 'Solar Beam', SUICUNE, { weather: 'raindance' }),
    pick(['solar-beam-sun'], EXEGGUTOR, 'Solar Beam', SUICUNE, { weather: 'sunnyday' }),
    pick(['sandstorm-changes-nothing'], STARMIE, 'Surf', TYRANITAR, { weather: 'sandstorm' }),
    // defense-halving moves, level extremes, the byte limits
    pick(['explosion'], EXEGGUTOR, 'Explosion', BLISSEY),
    pick(['self-destruct'], SNORLAX, 'Self-Destruct', SUICUNE),
    pick(['level-1-attacker', 'minimum-damage'], mon('Rattata', { level: 1 }), 'Tackle', mon('Steelix')),
    pick(['level-1-defender', 'damage-cap'], mon('Snorlax', { boosts: { atk: 6 } }), 'Self-Destruct', mon('Rattata', { level: 1 })),
    pick(['level-50'], mon('Snorlax', { level: 50 }), 'Body Slam', mon('Suicune', { level: 50 })),
    pick(['byte-rollover', 'attack-over-255'], mon('Snorlax', { boosts: { atk: 1 } }), 'Double-Edge', SUICUNE),
    pick(['byte-rollover', 'defense-over-255'], MACHAMP, 'Cross Chop', mon('Skarmory', { boosts: { def: 2 } })),
    pick(['byte-rollover', 'wraps-past-1023'], mon('Marowak', { item: 'Thick Club', boosts: { atk: 6 } }), 'Earthquake', SNORLAX),
    // DVs and Stat Exp
    pick(['min-dvs'], mon('Snorlax', { ivs: { atk: 0, def: 0, spe: 0, spa: 0, spd: 0 } }), 'Body Slam', SUICUNE),
    pick(['no-stat-exp'], mon('Snorlax', { evs: { hp: 0, atk: 0, def: 0, spe: 0, spa: 0, spd: 0 } }), 'Body Slam', mon('Suicune', { evs: { hp: 0, def: 0 } })),
    pick(['partial-stat-exp'], mon('Starmie', { evs: { spa: 10000, spd: 10000 } }), 'Surf', mon('Snorlax', { evs: { hp: 2500, spa: 400, spd: 400 } })),
    // fixed damage (after the type check in Gen 2)
    pick(['fixed-level'], BLISSEY, 'Seismic Toss', SNORLAX),
    pick(['fixed-level', 'immune'], BLISSEY, 'Seismic Toss', GENGAR),
    pick(['fixed-level', 'level-73'], mon('Gengar', { level: 73 }), 'Night Shade', SUICUNE),
    pick(['fixed-level', 'immune'], GENGAR, 'Night Shade', SNORLAX),
    pick(['fixed-flat'], mon('Dragonair'), 'Dragon Rage', SNORLAX),
    pick(['fixed-flat'], mon('Magnemite'), 'Sonic Boom', SUICUNE),
    // variable base power
    pick(['return'], SNORLAX, 'Return', SUICUNE),
    pick(['frustration'], SNORLAX, 'Frustration', SUICUNE),
    pick(['flail-low-hp', 'no-random-factor'], mon('Magikarp', { hp: 3 }), 'Flail', STARMIE),
    pick(['flail-full-hp', 'no-random-factor'], mon('Magikarp'), 'Flail', STARMIE),
    pick(['reversal-mid-hp', 'no-random-factor'], mon('Heracross', { hp: 60 }), 'Reversal', TYRANITAR),
    pick(['hidden-power-typed', 'special'], ZAPDOS, 'Hidden Power Ice', DRAGONITE),
    pick(['hidden-power-typed', 'physical'], MACHAMP, 'Hidden Power Bug', EXEGGUTOR),
    // typeless damage
    pick(['typeless', 'struggle-hits-ghost'], SNORLAX, 'Struggle', GENGAR),
    pick(['typeless', 'future-sight-hits-dark'], STARMIE, 'Future Sight', mon('Umbreon')),
    // items
    pick(['type-item'], mon('Charizard', { item: 'Charcoal' }), 'Flamethrower', SNORLAX),
    pick(['type-item-other-type'], mon('Charizard', { item: 'Charcoal' }), 'Earthquake', SNORLAX),
    pick(['type-item', 'physical'], mon('Machamp', { item: 'Black Belt' }), 'Cross Chop', SNORLAX),
    pick(['pink-bow'], mon('Snorlax', { item: 'Pink Bow' }), 'Body Slam', SUICUNE),
    pick(['polkadot-bow'], mon('Snorlax', { item: 'Polkadot Bow' }), 'Body Slam', SUICUNE),
    pick(['pink-bow-struggle'], mon('Snorlax', { item: 'Pink Bow' }), 'Struggle', SUICUNE),
    pick(['dragon-fang-does-nothing'], mon('Dragonite', { item: 'Dragon Fang' }), 'Outrage', SUICUNE),
    pick(['dragon-scale-boosts-dragon'], mon('Dragonite', { item: 'Dragon Scale' }), 'Outrage', SUICUNE),
    pick(['light-ball'], mon('Pikachu', { item: 'Light Ball' }), 'Thunderbolt', STARMIE),
    pick(['light-ball-physical-unaffected'], mon('Pikachu', { item: 'Light Ball' }), 'Quick Attack', STARMIE),
    pick(['thick-club'], mon('Marowak', { item: 'Thick Club' }), 'Earthquake', TYRANITAR),
    pick(['thick-club-special-unaffected'], mon('Marowak', { item: 'Thick Club' }), 'Fire Blast', EXEGGUTOR),
    pick(['metal-powder'], SNORLAX, 'Body Slam', mon('Ditto', { item: 'Metal Powder' })),
    pick(['metal-powder', 'special'], STARMIE, 'Surf', mon('Ditto', { item: 'Metal Powder' })),
    // foresight, multi-hit
    pick(['foresight'], SNORLAX, 'Body Slam', GENGAR, { foresight: true }),
    pick(['foresight', 'fighting'], MACHAMP, 'Cross Chop', GENGAR, { foresight: true }),
    pick(['multi-hit'], mon('Beedrill'), 'Pin Missile', EXEGGUTOR),
    pick(['multi-hit', 'two-hits'], mon('Nidoking'), 'Double Kick', TYRANITAR),
  ];
}
