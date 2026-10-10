// Gen 3 golden cases: the hand-picked list (one case per mechanic) and the random sweep's settings.
// `mon` builds a side, `pick` a tagged case; both come from build_calc_golden.mjs.

export const sweepSize = 200;
export const sweepSeed = 20261013;

export function handPicked({ mon, pick }) {
  const SALAMENCE = mon('Salamence', { nature: 'Adamant', evs: { atk: 252, spe: 252, hp: 4 } });
  const STARMIE = mon('Starmie', { nature: 'Timid', ability: 'Natural Cure', evs: { spa: 252, spe: 252 } });
  const BLAZIKEN = mon('Blaziken', { nature: 'Naive', evs: { atk: 128, spa: 128, spe: 252 } });
  const SWAMPERT = mon('Swampert', { nature: 'Relaxed', evs: { hp: 252, def: 252 } });
  const BLISSEY = mon('Blissey', { nature: 'Bold', evs: { hp: 252, def: 252 } });
  const SNORLAX = mon('Snorlax', { nature: 'Adamant', ability: 'Immunity', evs: { hp: 252, atk: 252 } });
  const GENGAR = mon('Gengar', { nature: 'Timid', evs: { spa: 252, spe: 252 } });
  const TYRANITAR = mon('Tyranitar', { nature: 'Careful', evs: { hp: 252, spd: 252 } });
  const SKARMORY = mon('Skarmory', { nature: 'Impish', ability: 'Keen Eye', evs: { hp: 252, def: 252 } });
  const SHEDINJA = mon('Shedinja', { nature: 'Adamant', evs: { atk: 252 } });
  const ZAPDOS = mon('Zapdos', { nature: 'Modest', evs: { spa: 252 } });
  const HERACROSS = mon('Heracross', { ability: 'Swarm', evs: { atk: 252 } });
  const ROSELIA = mon('Roselia', { ability: 'Natural Cure', evs: { spa: 252 } });

  return [
    // type effectiveness and STAB
    pick(['neutral', 'stab'], SWAMPERT, 'Earthquake', STARMIE),
    pick(['neutral', 'no-stab'], SALAMENCE, 'Earthquake', STARMIE),
    pick(['2x', 'stab'], STARMIE, 'Surf', BLAZIKEN),
    pick(['4x'], STARMIE, 'Ice Beam', SALAMENCE),
    pick(['half'], BLAZIKEN, 'Flamethrower', STARMIE),
    pick(['quarter'], BLAZIKEN, 'Flamethrower', mon('Kingdra')),
    pick(['immune'], SALAMENCE, 'Earthquake', SKARMORY),
    pick(['immune'], SNORLAX, 'Body Slam', GENGAR),
    pick(['dual-type-order'], STARMIE, 'Ice Beam', SWAMPERT),
    pick(['dual-type-order', 'stab'], ZAPDOS, 'Thunderbolt', mon('Gyarados')),
    pick(['dual-type-order'], BLAZIKEN, 'Sky Uppercut', mon('Aggron', { ability: 'Rock Head' })),
    pick(['dual-type-order'], SALAMENCE, 'Rock Slide', mon('Charizard')),
    // stat stages and critical hits (every case also records its critical-hit rolls)
    pick(['boost'], mon('Salamence', { ...SALAMENCE, boosts: { atk: 2 } }), 'Earthquake', SWAMPERT),
    pick(['drop', 'crit-ignores-drop'], mon('Salamence', { ...SALAMENCE, boosts: { atk: -1 } }), 'Earthquake', SWAMPERT),
    pick(['defense-boost', 'crit-ignores-boost'], SALAMENCE, 'Earthquake', mon('Swampert', { ...SWAMPERT, boosts: { def: 2 } })),
    pick(['defense-drop'], STARMIE, 'Surf', mon('Blissey', { ...BLISSEY, boosts: { spd: -2 } })),
    pick(['max-stages'], mon('Salamence', { ...SALAMENCE, boosts: { atk: 6 } }), 'Aerial Ace', mon('Swampert', { ...SWAMPERT, boosts: { def: -6 } })),
    pick(['min-stages'], mon('Starmie', { ...STARMIE, boosts: { spa: -6 } }), 'Psychic', mon('Blissey', { ...BLISSEY, boosts: { spd: 6 } })),
    // burn, screens, weather
    pick(['burn'], mon('Salamence', { ...SALAMENCE, status: 'brn' }), 'Earthquake', SWAMPERT),
    pick(['burn-special-unaffected'], mon('Starmie', { ...STARMIE, status: 'brn' }), 'Surf', SWAMPERT),
    pick(['reflect'], SALAMENCE, 'Earthquake', SWAMPERT, { reflect: true }),
    pick(['reflect-vs-special'], STARMIE, 'Surf', SWAMPERT, { reflect: true }),
    pick(['light-screen'], STARMIE, 'Surf', SWAMPERT, { light_screen: true }),
    pick(['brick-break-ignores-reflect'], BLAZIKEN, 'Brick Break', BLISSEY, { reflect: true }),
    pick(['sun-fire'], BLAZIKEN, 'Flamethrower', SWAMPERT, { weather: 'sunnyday' }),
    pick(['sun-water'], STARMIE, 'Surf', BLAZIKEN, { weather: 'sunnyday' }),
    pick(['rain-water'], STARMIE, 'Surf', BLAZIKEN, { weather: 'raindance' }),
    pick(['rain-fire'], BLAZIKEN, 'Flamethrower', SWAMPERT, { weather: 'raindance' }),
    pick(['solar-beam-rain'], mon('Venusaur', { evs: { spa: 252 } }), 'Solar Beam', SWAMPERT, { weather: 'raindance' }),
    pick(['solar-beam-hail'], mon('Venusaur', { evs: { spa: 252 } }), 'Solar Beam', SWAMPERT, { weather: 'hail' }),
    pick(['solar-beam-sun'], mon('Venusaur', { evs: { spa: 252 } }), 'Solar Beam', SWAMPERT, { weather: 'sunnyday' }),
    pick(['sandstorm-no-spdef-boost'], STARMIE, 'Surf', TYRANITAR, { weather: 'sandstorm' }),
    pick(['cloud-nine-negates-weather'], mon('Golduck', { ability: 'Cloud Nine' }), 'Surf', BLAZIKEN, { weather: 'raindance' }),
    pick(['air-lock-negates-weather'], BLAZIKEN, 'Flamethrower', mon('Rayquaza'), { weather: 'sunnyday' }),
    pick(['weather-ball-sun'], ROSELIA, 'Weather Ball', SWAMPERT, { weather: 'sunnyday' }),
    pick(['weather-ball-rain'], ROSELIA, 'Weather Ball', BLAZIKEN, { weather: 'raindance' }),
    pick(['weather-ball-sand', 'physical'], ROSELIA, 'Weather Ball', ZAPDOS, { weather: 'sandstorm' }),
    pick(['weather-ball-hail'], ROSELIA, 'Weather Ball', SALAMENCE, { weather: 'hail' }),
    pick(['weather-ball-clear'], ROSELIA, 'Weather Ball', SWAMPERT),
    // defense-halving moves, level extremes, minimum damage
    pick(['explosion'], mon('Metagross', { nature: 'Adamant', evs: { atk: 252 } }), 'Explosion', BLISSEY),
    pick(['self-destruct'], SNORLAX, 'Self-Destruct', SWAMPERT),
    pick(['level-1-attacker', 'minimum-damage'], mon('Rattata', { level: 1, ability: 'Run Away' }), 'Tackle', mon('Steelix', { ability: 'Rock Head' })),
    pick(['level-1-attacker', 'special-has-no-floor-of-1'], mon('Magikarp', { level: 1 }), 'Water Gun', BLISSEY),
    pick(['level-1-defender'], SALAMENCE, 'Earthquake', mon('Rattata', { level: 1, ability: 'Run Away' })),
    pick(['level-50'], mon('Salamence', { ...SALAMENCE, level: 50 }), 'Earthquake', mon('Swampert', { ...SWAMPERT, level: 50 })),
    // fixed damage
    pick(['fixed-level'], BLISSEY, 'Seismic Toss', SWAMPERT),
    pick(['fixed-level', 'immune'], BLISSEY, 'Seismic Toss', GENGAR),
    pick(['fixed-level', 'level-73'], mon('Gengar', { ...GENGAR, level: 73 }), 'Night Shade', SWAMPERT),
    pick(['fixed-level', 'immune'], GENGAR, 'Night Shade', SNORLAX),
    pick(['fixed-flat'], mon('Dragonair'), 'Dragon Rage', SWAMPERT),
    pick(['fixed-flat'], mon('Magnemite', { ability: 'Magnet Pull' }), 'Sonic Boom', SALAMENCE),
    pick(['fixed-flat', 'immune'], mon('Magnemite', { ability: 'Magnet Pull' }), 'Sonic Boom', GENGAR),
    pick(['fixed-level', 'wonder-guard'], BLISSEY, 'Seismic Toss', SHEDINJA),
    // variable base power
    pick(['return'], SNORLAX, 'Return', SWAMPERT),
    pick(['frustration'], SNORLAX, 'Frustration', SWAMPERT),
    pick(['eruption-partial-hp'], mon('Typhlosion', { evs: { spa: 252 }, hp: 160 }), 'Eruption', SWAMPERT),
    pick(['eruption-full-hp'], mon('Typhlosion', { evs: { spa: 252 } }), 'Eruption', BLISSEY),
    pick(['water-spout-1hp'], mon('Kyogre', { hp: 1 }), 'Water Spout', BLISSEY, { weather: 'raindance' }),
    pick(['flail-low-hp'], mon('Magikarp', { hp: 3 }), 'Flail', STARMIE),
    pick(['flail-mid-hp'], mon('Magikarp', { hp: 30 }), 'Flail', STARMIE),
    pick(['flail-full-hp'], mon('Magikarp'), 'Flail', STARMIE),
    pick(['reversal-mid-hp'], mon('Heracross', { ...HERACROSS, hp: 60 }), 'Reversal', TYRANITAR),
    pick(['low-kick-heavy'], BLAZIKEN, 'Low Kick', SNORLAX),
    pick(['low-kick-light'], BLAZIKEN, 'Low Kick', mon('Pikachu')),
    pick(['facade-paralysis'], mon('Snorlax', { ...SNORLAX, status: 'par' }), 'Facade', SWAMPERT),
    pick(['facade-burn'], mon('Snorlax', { ...SNORLAX, status: 'brn' }), 'Facade', SWAMPERT),
    pick(['facade-guts'], mon('Ursaring', { ability: 'Guts', status: 'psn', evs: { atk: 252 } }), 'Facade', SWAMPERT),
    pick(['hidden-power-typed', 'special'], mon('Zapdos', { nature: 'Timid', evs: { spa: 252 } }), 'Hidden Power Ice', SALAMENCE),
    pick(['hidden-power-typed', 'physical'], SALAMENCE, 'Hidden Power Flying', HERACROSS),
    pick(['hidden-power-typed', 'physical'], HERACROSS, 'Hidden Power Ghost', GENGAR),
    // typeless damage
    pick(['typeless', 'struggle-hits-ghost'], SNORLAX, 'Struggle', GENGAR),
    pick(['typeless', 'future-sight-hits-dark'], STARMIE, 'Future Sight', TYRANITAR),
    pick(['typeless', 'no-stab'], mon('Jirachi'), 'Doom Desire', BLAZIKEN),
    // abilities that make a move do nothing
    pick(['levitate'], SALAMENCE, 'Earthquake', GENGAR),
    pick(['flash-fire'], BLAZIKEN, 'Flamethrower', mon('Houndoom', { ability: 'Flash Fire' })),
    pick(['water-absorb'], STARMIE, 'Surf', mon('Vaporeon')),
    pick(['volt-absorb'], ZAPDOS, 'Thunderbolt', mon('Jolteon')),
    pick(['wonder-guard-blocks-neutral'], STARMIE, 'Surf', SHEDINJA),
    pick(['wonder-guard-super-effective'], BLAZIKEN, 'Flamethrower', SHEDINJA),
    pick(['wonder-guard-typeless'], SNORLAX, 'Struggle', SHEDINJA),
    pick(['soundproof'], mon('Exploud'), 'Hyper Voice', mon('Mr. Mime', { ability: 'Soundproof' })),
    pick(['foresight'], SNORLAX, 'Body Slam', GENGAR, { foresight: true }),
    pick(['foresight', 'fighting'], BLAZIKEN, 'Sky Uppercut', GENGAR, { foresight: true }),
    // abilities that change the numbers
    pick(['thick-fat-fire'], BLAZIKEN, 'Flamethrower', mon('Snorlax', { ability: 'Thick Fat' })),
    pick(['thick-fat-ice'], STARMIE, 'Ice Beam', mon('Snorlax', { ability: 'Thick Fat' })),
    pick(['huge-power'], mon('Azumarill', { ability: 'Huge Power', evs: { atk: 252 } }), 'Return', BLAZIKEN),
    pick(['huge-power-special-unaffected'], mon('Azumarill', { ability: 'Huge Power' }), 'Surf', BLAZIKEN),
    pick(['pure-power'], mon('Medicham', { evs: { atk: 252 } }), 'Brick Break', TYRANITAR),
    pick(['guts-burned'], mon('Heracross', { ability: 'Guts', status: 'brn', evs: { atk: 252 } }), 'Megahorn', SWAMPERT),
    pick(['guts-no-status'], mon('Heracross', { ability: 'Guts', evs: { atk: 252 } }), 'Megahorn', SWAMPERT),
    pick(['hustle'], mon('Togetic', { ability: 'Hustle' }), 'Return', BLAZIKEN),
    pick(['marvel-scale'], SALAMENCE, 'Earthquake', mon('Milotic', { status: 'par' })),
    pick(['blaze-pinch'], mon('Blaziken', { ...BLAZIKEN, hp: 90 }), 'Flamethrower', SWAMPERT),
    pick(['blaze-above-third'], mon('Blaziken', { ...BLAZIKEN, hp: 120 }), 'Flamethrower', SWAMPERT),
    pick(['torrent-pinch'], mon('Swampert', { ...SWAMPERT, hp: 100 }), 'Surf', BLAZIKEN),
    pick(['overgrow-pinch'], mon('Venusaur', { hp: 50 }), 'Giga Drain', SWAMPERT),
    pick(['swarm-pinch'], mon('Heracross', { ...HERACROSS, hp: 60 }), 'Megahorn', STARMIE),
    pick(['flash-fire-boost'], mon('Houndoom', { ability: 'Flash Fire', ability_on: true, evs: { spa: 252 } }), 'Flamethrower', SWAMPERT),
    pick(['battle-armor-no-crit'], SALAMENCE, 'Earthquake', mon('Kabutops', { ability: 'Battle Armor' })),
    pick(['shell-armor-no-crit'], SALAMENCE, 'Earthquake', mon('Cloyster')),
    // items
    pick(['choice-band'], mon('Salamence', { ...SALAMENCE, item: 'Choice Band' }), 'Earthquake', SWAMPERT),
    pick(['choice-band-special-unaffected'], mon('Starmie', { ...STARMIE, item: 'Choice Band' }), 'Surf', SWAMPERT),
    pick(['type-item'], mon('Blaziken', { ...BLAZIKEN, item: 'Charcoal' }), 'Flamethrower', SWAMPERT),
    pick(['type-item-other-type'], mon('Blaziken', { ...BLAZIKEN, item: 'Charcoal' }), 'Sky Uppercut', SWAMPERT),
    pick(['type-item', 'physical'], mon('Salamence', { ...SALAMENCE, item: 'Soft Sand' }), 'Earthquake', STARMIE),
    pick(['sea-incense'], mon('Starmie', { ...STARMIE, item: 'Sea Incense' }), 'Surf', BLAZIKEN),
    pick(['sea-incense-other-type'], mon('Starmie', { ...STARMIE, item: 'Sea Incense' }), 'Psychic', BLAZIKEN),
    pick(['silk-scarf-struggle'], mon('Snorlax', { ...SNORLAX, item: 'Silk Scarf' }), 'Struggle', SWAMPERT),
    pick(['soul-dew-attack'], mon('Latios', { item: 'Soul Dew' }), 'Dragon Claw', SWAMPERT),
    pick(['soul-dew-defense'], STARMIE, 'Surf', mon('Latias', { item: 'Soul Dew' })),
    pick(['light-ball'], mon('Pikachu', { item: 'Light Ball' }), 'Thunderbolt', STARMIE),
    pick(['light-ball-physical-unaffected'], mon('Pikachu', { item: 'Light Ball' }), 'Quick Attack', STARMIE),
    pick(['thick-club'], mon('Marowak', { ability: 'Rock Head', item: 'Thick Club' }), 'Earthquake', TYRANITAR),
    pick(['deep-sea-tooth'], mon('Clamperl', { item: 'Deep Sea Tooth' }), 'Surf', BLAZIKEN),
    pick(['deep-sea-scale'], STARMIE, 'Thunderbolt', mon('Clamperl', { item: 'Deep Sea Scale' })),
    pick(['metal-powder'], SALAMENCE, 'Earthquake', mon('Ditto', { item: 'Metal Powder' })),
    // multi-hit moves
    pick(['multi-hit'], mon('Cloyster'), 'Icicle Spear', SALAMENCE),
    pick(['multi-hit', 'two-hits'], mon('Hitmonlee'), 'Double Kick', TYRANITAR),
  ];
}
