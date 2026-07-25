from datetime import datetime

from pydantic import BaseModel


class RegulationOut(BaseModel):
    id: str
    name: str
    start_date: datetime
    end_date: datetime
    mega_allowed: bool
    notes: str


class PokemonSummaryOut(BaseModel):
    pokemon_species_id: int
    name: str
    types: list[str]
    verified: bool


class PokemonDetailOut(BaseModel):
    id: int
    name: str
    types: list[str]
    base_stats: dict[str, int]
    is_default: bool
    legal_in_regulation: bool


class MoveOut(BaseModel):
    id: int
    name: str
    type: str
    category: str
    power: int | None
    accuracy: int | None
    pp: int | None


class UsageOut(BaseModel):
    pokemon_species_id: int
    name: str
    usage_pct: float
    verified: bool
