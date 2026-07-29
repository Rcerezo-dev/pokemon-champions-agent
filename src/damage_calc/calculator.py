"""Fase 11: damage calculator, adapted from @smogon/calc.

Champions changes several mechanics the library doesn't know about natively
(SP instead of EVs, fixed level 50/IV 31, no Tera/Dynamax/Z-Move) -- rather
than reimplement the damage formula itself (the riskiest possible place to
introduce a subtle bug, per CLAUDE.md), this module computes the
Champions-specific final stats in Python (see stats.py) and hands them,
plus the move/field, to the real @smogon/calc engine running in Node via
`src/damage_calc/node/calc.js` (JSON over stdin/stdout, one process per
call -- no persistent server, matches the project's "no unnecessary
infrastructure for a local single-user tool" rule).

@smogon/calc silently accepts unknown item/ability/move/species names with
no effect instead of erroring -- dangerous for Champions-exclusive content
(e.g. the 7 Mega Stones from Fase 3 with no mainline-game equivalent, so no
entry in this library's data either). calc.js validates every name against
the library's own tables before calculating and fails loudly if any is
missing, so calling this function for one of those Pokémon/items raises
DamageCalcError instead of silently returning a wrong number.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from sqlmodel import Session, select

from src.damage_calc.stats import STAT_NAMES, compute_stats
from src.db.models import Nature, PokemonSpecies

NODE_DIR = Path(__file__).resolve().parent / "node"
CALC_SCRIPT = NODE_DIR / "calc.js"
CALC_STAT_KEY = {
    "hp": "hp",
    "attack": "atk",
    "defense": "def",
    "special-attack": "spa",
    "special-defense": "spd",
    "speed": "spe",
}
BOOSTABLE_STATS = [s for s in STAT_NAMES if s != "hp"]
SUBPROCESS_TIMEOUT_SECONDS = 30


class DamageCalcError(RuntimeError):
    pass


@dataclass
class DamageBuild:
    species: str
    ability: Optional[str] = None
    item: Optional[str] = None
    nature: Optional[str] = None
    status: str = ""  # "", "brn", "par", "psn", "tox", "slp", "frz"
    sp_spread: dict[str, int] = field(default_factory=dict)  # PokeAPI-style stat names, see stats.STAT_NAMES
    boosts: dict[str, int] = field(default_factory=dict)  # same names (no "hp"), -6..+6


@dataclass
class FieldConditions:
    game_type: Literal["singles", "doubles"] = "singles"
    weather: Optional[str] = None  # "Sun" | "Rain" | "Sand" | "Snow"
    terrain: Optional[str] = None  # "Electric" | "Grassy" | "Misty" | "Psychic"
    attacker_side: dict = field(default_factory=dict)  # e.g. {"isTailwind": true, "isHelpingHand": true}
    defender_side: dict = field(default_factory=dict)  # e.g. {"isReflect": true, "isLightScreen": true}


@dataclass
class DamageResult:
    damage_rolls: list[int]
    damage_min: int
    damage_max: int
    defender_max_hp: int
    hp_pct_min: float
    hp_pct_max: float
    ko_chance_text: str
    ko_chance: Optional[float]
    modifiers: list[str]


def _resolve_species(session: Session, name: str) -> PokemonSpecies:
    species = session.exec(select(PokemonSpecies).where(PokemonSpecies.name == name)).first()
    if species is None:
        raise DamageCalcError(f"'{name}' is not a known Pokémon in the database.")
    return species


def _resolve_nature(session: Session, name: Optional[str]) -> Optional[Nature]:
    if name is None:
        return None
    nature = session.exec(select(Nature).where(Nature.name == name)).first()
    if nature is None:
        raise DamageCalcError(f"'{name}' is not a known nature.")
    return nature


def _build_calc_pokemon_payload(session: Session, build: DamageBuild) -> tuple[dict, dict[str, int]]:
    species = _resolve_species(session, build.species)
    base_stats = json.loads(species.base_stats_json)
    nature = _resolve_nature(session, build.nature)
    raw_stats = compute_stats(base_stats, build.sp_spread, nature)

    unknown_boost_stats = set(build.boosts) - set(BOOSTABLE_STATS)
    if unknown_boost_stats:
        raise DamageCalcError(f"Unknown stat name(s) in boosts: {sorted(unknown_boost_stats)}.")

    # See calc.js's buildPokemon() for why this is a base-stat override
    # rather than the final stats themselves: @smogon/calc's calculate()
    # clones each Pokemon internally and recomputes rawStats from
    # ivs/evs/nature via its own calcStat(), discarding any post-
    # construction stat override -- overrides.baseStats is the one channel
    # that survives the clone. At IV 31/EV 0/neutral nature/level 50,
    # calcStat(base) == base + 20 (base + 75 for HP), so this is an exact
    # algebraic inverse, not a lossy SP->EV approximation.
    base_stat_override = {
        CALC_STAT_KEY[stat]: raw_stats[stat] - (75 if stat == "hp" else 20) for stat in STAT_NAMES
    }

    payload = {
        "species": build.species,
        "ability": build.ability,
        "item": build.item,
        "status": build.status,
        "boosts": {CALC_STAT_KEY[stat]: value for stat, value in build.boosts.items()},
        "baseStatOverride": base_stat_override,
    }
    return payload, raw_stats


def _modifier_breakdown(attacker: DamageBuild, defender: DamageBuild, field_conditions: FieldConditions, raw_desc: dict) -> list[str]:
    notes: list[str] = []
    if attacker.item:
        notes.append(f"Attacker item: {attacker.item}")
    if attacker.ability:
        notes.append(f"Attacker ability: {attacker.ability}")
    if attacker.nature:
        notes.append(f"Attacker nature: {attacker.nature}")
    sp_bits = [f"{v} SP {k}" for k, v in attacker.sp_spread.items() if v]
    if sp_bits:
        notes.append("Attacker SP: " + ", ".join(sp_bits))
    for stat, value in attacker.boosts.items():
        if value:
            notes.append(f"Attacker {stat} {'+' if value > 0 else ''}{value}")
    if attacker.status:
        notes.append(f"Attacker status: {attacker.status}")

    if defender.item:
        notes.append(f"Defender item: {defender.item}")
    if defender.ability:
        notes.append(f"Defender ability: {defender.ability}")
    if defender.nature:
        notes.append(f"Defender nature: {defender.nature}")
    sp_bits = [f"{v} SP {k}" for k, v in defender.sp_spread.items() if v]
    if sp_bits:
        notes.append("Defender SP: " + ", ".join(sp_bits))
    for stat, value in defender.boosts.items():
        if value:
            notes.append(f"Defender {stat} {'+' if value > 0 else ''}{value}")
    if defender.status:
        notes.append(f"Defender status: {defender.status}")

    if field_conditions.weather:
        notes.append(f"Weather: {field_conditions.weather}")
    if field_conditions.terrain:
        notes.append(f"Terrain: {field_conditions.terrain}")
    if field_conditions.game_type == "doubles":
        notes.append("Doubles field (spread-move and screen modifiers apply where relevant)")
    if raw_desc.get("isReflect"):
        notes.append("Reflect is active on the defending side")
    if raw_desc.get("isLightScreen"):
        notes.append("Light Screen is active on the defending side")
    if raw_desc.get("isAuroraVeil"):
        notes.append("Aurora Veil is active on the defending side")
    if raw_desc.get("isBurned"):
        notes.append("Attacker is burned (physical damage halved)")
    return notes


def calculate_damage(
    session: Session,
    attacker: DamageBuild,
    defender: DamageBuild,
    move_name: str,
    field_conditions: Optional[FieldConditions] = None,
) -> DamageResult:
    field_conditions = field_conditions or FieldConditions()
    if not CALC_SCRIPT.exists():
        raise DamageCalcError(
            f"{CALC_SCRIPT} not found -- run `npm install` in {NODE_DIR} first (see README.md)."
        )
    if shutil.which("node") is None:
        raise DamageCalcError("Node.js not found on PATH -- required to run the @smogon/calc-based damage engine.")

    attacker_payload, _ = _build_calc_pokemon_payload(session, attacker)
    attacker_payload["moveName"] = move_name
    defender_payload, _ = _build_calc_pokemon_payload(session, defender)

    request = {
        "gen": 9,
        "gameType": "Doubles" if field_conditions.game_type == "doubles" else "Singles",
        "field": {
            "weather": field_conditions.weather,
            "terrain": field_conditions.terrain,
            "attackerSide": field_conditions.attacker_side,
            "defenderSide": field_conditions.defender_side,
        },
        "attacker": attacker_payload,
        "defender": defender_payload,
    }

    try:
        proc = subprocess.run(
            ["node", str(CALC_SCRIPT)],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            cwd=NODE_DIR,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as e:
        raise DamageCalcError("Node.js not found on PATH -- required to run the @smogon/calc-based damage engine.") from e
    except subprocess.TimeoutExpired as e:
        raise DamageCalcError(f"Damage calculation timed out after {SUBPROCESS_TIMEOUT_SECONDS}s.") from e

    if proc.returncode != 0:
        raise DamageCalcError(proc.stderr.strip() or "calc.js failed with no error message.")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise DamageCalcError(f"calc.js returned invalid JSON: {proc.stdout!r}") from e

    damage = data["damage"]
    rolls = damage if isinstance(damage, list) and damage and isinstance(damage[0], int) else [damage]
    dmg_min, dmg_max = data["range"]
    max_hp = data["defenderMaxHP"]
    ko = data["koChance"]

    return DamageResult(
        damage_rolls=rolls,
        damage_min=dmg_min,
        damage_max=dmg_max,
        defender_max_hp=max_hp,
        hp_pct_min=round(100 * dmg_min / max_hp, 1),
        hp_pct_max=round(100 * dmg_max / max_hp, 1),
        ko_chance_text=ko["text"],
        ko_chance=ko.get("chance"),
        modifiers=_modifier_breakdown(attacker, defender, field_conditions, data["rawDesc"]),
    )
