from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PokemonSpecies(SQLModel, table=True):
    """Static species data from PokeAPI: id matches the PokeAPI pokemon id."""

    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    types: str  # comma-separated, e.g. "fire,flying"
    base_stats_json: str  # {"hp":45,"attack":49,"defense":49,"special-attack":65,"special-defense":65,"speed":45}
    is_default: bool = False  # PokeAPI's own flag for which form/name represents the species by default


class Ability(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    effect_text: str


class Move(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    type: str
    category: str  # physical / special / status
    power: Optional[int] = None
    accuracy: Optional[int] = None
    pp: Optional[int] = None
    effect_text: str


class Item(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    category: str
    effect_text: str


class Nature(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    boosted_stat: Optional[str] = None  # None for neutral natures
    lowered_stat: Optional[str] = None


class TypeChart(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    attacking_type: str = Field(index=True)
    defending_type: str = Field(index=True)
    multiplier: float


class RegulationSet(SQLModel, table=True):
    """A Pokémon Champions Regulation Set (e.g. "M-B"). id is the official code."""

    id: str = Field(primary_key=True)  # e.g. "M-B"
    name: str
    start_date: datetime
    end_date: datetime
    mega_allowed: bool
    notes: str  # ruleset text (item duplication, timers, etc.)
    source: str
    retrieved_at: datetime


class RegulationLegalPokemon(SQLModel, table=True):
    """One legal species/form entry for a regulation set. Mega/regional forms are
    their own PokemonSpecies rows (matching PokeAPI's convention), so there is no
    separate mega_allowed_for_this flag -- the mega form's row being present here
    already says it's legal."""

    id: Optional[int] = Field(default=None, primary_key=True)
    regulation_id: str = Field(foreign_key="regulationset.id", index=True)
    pokemon_species_id: int = Field(foreign_key="pokemonspecies.id", index=True)
    source: str
    retrieved_at: datetime
    verified: bool  # True only if cross-checked against a second independent source
    verification_note: Optional[str] = None


class PokemonMovepool(SQLModel, table=True):
    """Which moves a species can use in Champions. Deliberately NOT scoped to
    a regulation: Champions has no level-up/TM/egg distinction (confirmed by
    inspecting Serebii's per-species move table), so a species' movepool is
    fixed game data, not something that changes per season. What changes per
    season is which of those moves are globally enabled -- see
    RegulationLegalMove."""

    id: Optional[int] = Field(default=None, primary_key=True)
    pokemon_species_id: int = Field(foreign_key="pokemonspecies.id", index=True)
    move_id: int = Field(foreign_key="move.id", index=True)
    source: str
    retrieved_at: datetime


class RegulationLegalMove(SQLModel, table=True):
    """Flat, species-independent list of moves enabled this regulation (e.g.
    502 for M-B vs 467 for M-A) -- confirmed via MetaVGC's per-regulation
    snapshot. A move usable by a given Pokémon right now is the intersection
    of PokemonMovepool and this table for the active regulation."""

    id: Optional[int] = Field(default=None, primary_key=True)
    regulation_id: str = Field(foreign_key="regulationset.id", index=True)
    move_id: int = Field(foreign_key="move.id", index=True)
    source: str
    retrieved_at: datetime
    verified: bool
    verification_note: Optional[str] = None


class RegulationLegalItem(SQLModel, table=True):
    """Flat list of held items enabled this regulation (148 for M-B)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    regulation_id: str = Field(foreign_key="regulationset.id", index=True)
    item_id: int = Field(foreign_key="item.id", index=True)
    source: str
    retrieved_at: datetime
    verified: bool
    verification_note: Optional[str] = None
