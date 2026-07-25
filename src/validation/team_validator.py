"""Fase 6: deterministic team-legality validator for Pokémon Champions.

Rule sources (all real, not guessed -- see PROGRESS.md for citations):
  - Team size, Species Clause, Item Clause: Serebii's regulation page +
    Victory Road's general rules (both already used as sources in Fases 2-3).
  - Duplicate-item ban, single-Mega-per-*battle* restriction: Bulbapedia's
    scraped ruleset text, already stored verbatim in RegulationSet.notes.
  - SP system (66 total / 32 per stat), Level 50, 31 IVs fixed: cross-checked
    across multiple independent community guides (game8.co, ChampDex,
    Switchblade Gaming, BattleWise AI, GameCards) that all agree on the same
    numbers with no historical variation noted -- treated as a fixed game
    mechanic (like Fase 1's type chart/natures), not per-regulation data, so
    it's a plain constant here rather than a scraped DB row.

Deliberately NOT enforced: "max 1 Mega Pokémon per team". The actual scraped
rule (RegulationSet.notes) says "a player may only Mega Evolve once per
battle" -- that's a battle-time restriction on which mons you *use*, not a
team-composition rule. A team CAN legally contain two different Mega-capable
Pokémon (each individually legal, holding different Mega Stones); the roadmap's
one-line gloss ("máx. 1 Mega") would have made this validator reject legal
teams, so the real scraped text wins per CLAUDE.md.

Deliberately NOT enforced: ability legality per species. PokemonSpecies never
captured its species->ability relationship (gap noted in Fase 5's
PROGRESS.md) -- we only check the ability *name* exists at all, not that this
species can actually have it.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

from sqlmodel import Session, select

from src.db.models import (
    Ability,
    Item,
    Move,
    Nature,
    PokemonMovepool,
    PokemonSpecies,
    RegulationLegalItem,
    RegulationLegalMove,
    RegulationLegalPokemon,
    RegulationSet,
)

SP_TOTAL_CAP = 66
SP_PER_STAT_CAP = 32
STAT_NAMES = {"hp", "attack", "defense", "special-attack", "special-defense", "speed"}
TEAM_SIZE_BOUNDS = {"singles": (3, 6), "doubles": (4, 6)}
MAX_MOVES_PER_POKEMON = 4


@dataclass
class TeamMember:
    species: str
    item: Optional[str] = None
    ability: Optional[str] = None
    nature: Optional[str] = None
    sp_spread: dict[str, int] = field(default_factory=dict)
    moves: list[str] = field(default_factory=list)


@dataclass
class Issue:
    code: str
    message: str
    member_index: Optional[int] = None


@dataclass
class ValidationResult:
    valid: bool
    issues: list[Issue]


def _check_team_size(fmt: str, members: list[TeamMember], issues: list[Issue]) -> None:
    lo, hi = TEAM_SIZE_BOUNDS[fmt]
    if not (lo <= len(members) <= hi):
        issues.append(Issue("team_size", f"{fmt} teams must have {lo}-{hi} Pokémon, got {len(members)}."))


def _check_species_clause(members: list[TeamMember], issues: list[Issue]) -> None:
    seen: dict[str, int] = {}
    for i, m in enumerate(members):
        if m.species in seen:
            issues.append(Issue("duplicate_species", f"'{m.species}' appears more than once (Species Clause).", i))
        seen.setdefault(m.species, i)


def _check_item_clause(members: list[TeamMember], issues: list[Issue]) -> None:
    seen: dict[str, int] = {}
    for i, m in enumerate(members):
        if not m.item:
            continue
        if m.item in seen:
            issues.append(Issue("duplicate_item", f"'{m.item}' is held by more than one Pokémon (Item Clause).", i))
        seen.setdefault(m.item, i)


def _check_sp_spread(members: list[TeamMember], issues: list[Issue]) -> None:
    for i, m in enumerate(members):
        unknown = set(m.sp_spread) - STAT_NAMES
        if unknown:
            issues.append(Issue("unknown_stat", f"Unknown stat name(s) in sp_spread: {sorted(unknown)}.", i))
        for stat, points in m.sp_spread.items():
            if stat in STAT_NAMES and points > SP_PER_STAT_CAP:
                issues.append(Issue("sp_over_stat_cap", f"{stat}={points} exceeds the per-stat cap of {SP_PER_STAT_CAP}.", i))
            if stat in STAT_NAMES and points < 0:
                issues.append(Issue("sp_negative", f"{stat}={points} cannot be negative.", i))
        total = sum(v for k, v in m.sp_spread.items() if k in STAT_NAMES)
        if total > SP_TOTAL_CAP:
            issues.append(Issue("sp_over_total_cap", f"Total SP {total} exceeds the cap of {SP_TOTAL_CAP}.", i))


def _check_moves_count(members: list[TeamMember], issues: list[Issue]) -> None:
    for i, m in enumerate(members):
        if len(m.moves) == 0:
            issues.append(Issue("no_moves", "Must have at least 1 move.", i))
        if len(m.moves) > MAX_MOVES_PER_POKEMON:
            issues.append(Issue("too_many_moves", f"Has {len(m.moves)} moves, max is {MAX_MOVES_PER_POKEMON}.", i))
        if len(set(m.moves)) != len(m.moves):
            issues.append(Issue("duplicate_move", "Contains the same move more than once.", i))


def validate_team(
    session: Session,
    regulation: RegulationSet,
    fmt: Literal["singles", "doubles"],
    members: list[TeamMember],
) -> ValidationResult:
    issues: list[Issue] = []

    if fmt not in TEAM_SIZE_BOUNDS:
        return ValidationResult(False, [Issue("unknown_format", f"format must be one of {list(TEAM_SIZE_BOUNDS)}.")])

    _check_team_size(fmt, members, issues)
    _check_species_clause(members, issues)
    _check_item_clause(members, issues)
    _check_sp_spread(members, issues)
    _check_moves_count(members, issues)

    species_by_name = {s.name: s for s in session.exec(select(PokemonSpecies)).all()}
    legal_species_ids = {
        r.pokemon_species_id
        for r in session.exec(select(RegulationLegalPokemon).where(RegulationLegalPokemon.regulation_id == regulation.id))
    }
    legal_item_names = {
        i.name
        for r, i in session.exec(
            select(RegulationLegalItem, Item)
            .join(Item, RegulationLegalItem.item_id == Item.id)
            .where(RegulationLegalItem.regulation_id == regulation.id)
        )
    }
    legal_move_ids_for_regulation = {
        r.move_id for r in session.exec(select(RegulationLegalMove).where(RegulationLegalMove.regulation_id == regulation.id))
    }
    move_by_name = {mv.name: mv for mv in session.exec(select(Move)).all()}
    nature_names = {n.name for n in session.exec(select(Nature)).all()}
    ability_names = {a.name for a in session.exec(select(Ability)).all()}

    for i, m in enumerate(members):
        species = species_by_name.get(m.species)
        if species is None:
            issues.append(Issue("unknown_species", f"'{m.species}' is not a known Pokémon.", i))
            continue
        if species.id not in legal_species_ids:
            issues.append(Issue("illegal_species", f"'{m.species}' is not legal in regulation {regulation.id}.", i))

        if m.item is not None and m.item not in legal_item_names:
            issues.append(Issue("illegal_item", f"'{m.item}' is not a legal held item in regulation {regulation.id}.", i))

        if m.ability is not None and m.ability not in ability_names:
            issues.append(Issue("unknown_ability", f"'{m.ability}' is not a known ability.", i))

        if m.nature is not None and m.nature not in nature_names:
            issues.append(Issue("unknown_nature", f"'{m.nature}' is not a known nature.", i))

        movepool_ids = {
            r.move_id for r in session.exec(select(PokemonMovepool).where(PokemonMovepool.pokemon_species_id == species.id))
        }
        for move_name in m.moves:
            move = move_by_name.get(move_name)
            if move is None:
                issues.append(Issue("unknown_move", f"'{move_name}' is not a known move.", i))
                continue
            if move.id not in movepool_ids:
                issues.append(Issue("move_not_in_movepool", f"'{m.species}' cannot learn '{move_name}'.", i))
            elif move.id not in legal_move_ids_for_regulation:
                issues.append(Issue("illegal_move", f"'{move_name}' is not usable in regulation {regulation.id}.", i))

    return ValidationResult(valid=len(issues) == 0, issues=issues)
