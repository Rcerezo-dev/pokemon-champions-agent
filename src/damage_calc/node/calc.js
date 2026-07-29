// Fase 11: thin bridge to the real @smogon/calc engine.
//
// Reads one JSON request from stdin, writes one JSON response to stdout.
// All Champions-specific adjustments (level 50, IV 31, SP-derived stats
// instead of EVs, no Tera/Dynamax/Z-Move) are done on the Python side
// (src/damage_calc/calculator.py) *before* the request is built -- this
// script's only job is to feed already-computed data into the unmodified
// library and hand back its raw result. It deliberately does not use the
// library's EV/nature-flavored `desc()`/`fullDesc()` text (meaningless for
// Champions' SP system) -- it returns the structured `rawDesc` object
// instead, and Python builds the Champions-flavored breakdown from it.
//
// @smogon/calc silently accepts unknown item/ability/move names (stores the
// string with no effect, no error) instead of failing -- dangerous for
// Champions-exclusive content (e.g. the 7 Mega Stones from Fase 3 that
// don't exist in mainline games and therefore aren't in this library's
// data either). So every name is looked up and validated explicitly here,
// per the project rule of failing visibly instead of silently computing a
// wrong number.

const calc = require("@smogon/calc");

function fail(message) {
  process.stderr.write(message + "\n");
  process.exit(1);
}

function readStdin() {
  const chunks = [];
  process.stdin.on("data", (c) => chunks.push(c));
  return new Promise((resolve, reject) => {
    process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    process.stdin.on("error", reject);
  });
}

function requireEntity(gen, kind, singular, name) {
  const table = { species: gen.species, abilities: gen.abilities, items: gen.items, moves: gen.moves }[kind];
  const found = table.get(calc.toID(name));
  if (!found) {
    throw new Error(`Unknown ${singular} '${name}' -- not modeled by @smogon/calc@${require("@smogon/calc/package.json").version} ` +
      "(typo, or Champions-exclusive content with no mainline-game equivalent, e.g. a custom Mega Stone).");
  }
  return found;
}

function buildPokemon(gen, build, extraOptions) {
  requireEntity(gen, "species", "species", build.species);
  if (build.ability) requireEntity(gen, "abilities", "ability", build.ability);
  if (build.item) requireEntity(gen, "items", "item", build.item);

  // IMPORTANT: calc.calculate() clones both Pokemon internally (calc.js's
  // top-level `calculate`) and clone() rebuilds rawStats from scratch via
  // ivs/evs/nature/level -- it does NOT copy a post-construction override of
  // `.rawStats`/`.stats` (confirmed by tracing it; such an override is
  // silently discarded the moment calculate() runs). The only override
  // channel that survives clone() is `overrides.baseStats`, which patches
  // the species data used *inside* the library's own calcStat() call.
  //
  // Champions' final-stat formula (see stats.py) reduces, at IV 31/EV 0/
  // neutral nature/level 50, to a clean invertible shift of the library's
  // own formula: final = base + 20 + sp (or +75 for HP). So Python sends
  // `baseStatOverride[stat] = final_stat - 20` (`- 75` for HP) as a "fake"
  // base stat, and calcStat(fakeBase, iv=31, ev=0, nature=neutral) lands
  // back on exactly the intended final stat. Nature is forced to a neutral
  // placeholder here because Python's final stat already has the real
  // nature multiplier baked in.
  const pokemon = new calc.Pokemon(gen, build.species, Object.assign({
    level: 50,
    ability: build.ability || undefined,
    item: build.item || undefined,
    status: build.status || "",
    boosts: build.boosts || {},
    nature: "Serious",
    overrides: { baseStats: build.baseStatOverride },
  }, extraOptions));
  return pokemon;
}

async function main() {
  const raw = await readStdin();
  let req;
  try {
    req = JSON.parse(raw);
  } catch (e) {
    fail(`Invalid JSON on stdin: ${e.message}`);
    return;
  }

  const gen = calc.Generations.get(req.gen || 9);

  let attacker, defender, move, field;
  try {
    attacker = buildPokemon(gen, req.attacker, { moves: [req.attacker.moveName] });
    defender = buildPokemon(gen, req.defender, {});
    requireEntity(gen, "moves", "move", req.attacker.moveName);
    move = new calc.Move(gen, req.attacker.moveName, req.hits ? { hits: req.hits } : {});
    field = new calc.Field({
      gameType: req.gameType || "Singles",
      weather: req.field && req.field.weather ? req.field.weather : undefined,
      terrain: req.field && req.field.terrain ? req.field.terrain : undefined,
      attackerSide: (req.field && req.field.attackerSide) || {},
      defenderSide: (req.field && req.field.defenderSide) || {},
    });
  } catch (e) {
    fail(e.message);
    return;
  }

  let result;
  try {
    result = calc.calculate(gen, attacker, defender, move, field);
  } catch (e) {
    fail(`@smogon/calc raised while calculating: ${e.message}`);
    return;
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    damage: result.damage,
    range: result.range(),
    koChance: result.kochance(),
    rawDesc: result.rawDesc,
    defenderMaxHP: defender.maxHP(),
  }));
}

main().catch((e) => fail(`Unexpected error: ${e.stack || e.message}`));
