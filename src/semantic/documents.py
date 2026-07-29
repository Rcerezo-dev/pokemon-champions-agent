"""Fase 12: builds the text document embedded for each Champions-legal
species.

Deliberately narrower than the roadmap's illustrative doc content (tipos,
stats, habilidades, movimientos destacados, rol típico, ítems comunes):
"rol típico" and "ítems comunes" are dropped. Neither has real backing data
-- `common_sets` (Fase 4) was never populated (ChampionsMeta doesn't expose
a per-Pokémon set breakdown), and "role" would have to be a label this code
invents (e.g. "physical sweeper"), which is exactly what CLAUDE.md's "nunca
inventes" rule forbids. Abilities/movepool ARE included because Fase 12
backfilled the missing species->ability data from the already-cached PokeAPI
responses (see seed.py) instead of guessing it.
"""

from dataclasses import dataclass

from src.db.models import Ability, Move, PokemonSpecies, UsageStat


@dataclass
class AbilityRef:
    name: str
    effect_text: str
    is_hidden: bool


@dataclass
class SpeciesDocInput:
    species: PokemonSpecies
    base_stats: dict[str, int]
    abilities: list[AbilityRef]
    legal_moves: list[Move]
    usage: UsageStat | None


def build_document(doc_input: SpeciesDocInput) -> str:
    sp = doc_input.species
    types = " / ".join(t.capitalize() for t in sp.types.split(","))
    stats = doc_input.base_stats
    stats_line = (
        f"HP {stats.get('hp', 0)}, Attack {stats.get('attack', 0)}, Defense {stats.get('defense', 0)}, "
        f"Special Attack {stats.get('special-attack', 0)}, Special Defense {stats.get('special-defense', 0)}, "
        f"Speed {stats.get('speed', 0)}"
    )

    lines = [f"{sp.name.capitalize()} ({types})", f"Base stats: {stats_line}."]

    if doc_input.abilities:
        ability_bits = []
        for a in doc_input.abilities:
            tag = " (hidden ability)" if a.is_hidden else ""
            effect = f": {a.effect_text}" if a.effect_text else ""
            ability_bits.append(f"{a.name.capitalize()}{tag}{effect}")
        lines.append("Abilities: " + "; ".join(ability_bits) + ".")

    if doc_input.legal_moves:
        moves_sorted = sorted(doc_input.legal_moves, key=lambda m: (m.type, -(m.power or 0)))
        move_bits = [f"{m.name.capitalize()} ({m.type}, {m.category}{f', {m.power} power' if m.power else ''})" for m in moves_sorted]
        lines.append(f"Legal moves this regulation ({len(move_bits)}): " + ", ".join(move_bits) + ".")
    else:
        lines.append("No legal moves recorded for this regulation.")

    if doc_input.usage is not None:
        verified = "verified" if doc_input.usage.verified else "unverified"
        lines.append(f"Usage this regulation: {doc_input.usage.usage_pct:.1f}% of teams ({verified}).")

    return "\n".join(lines)
