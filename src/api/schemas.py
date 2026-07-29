from datetime import datetime
from typing import Literal

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


class TeamMemberIn(BaseModel):
    species: str
    item: str | None = None
    ability: str | None = None
    nature: str | None = None
    sp_spread: dict[str, int] = {}
    moves: list[str] = []


class TeamValidateRequest(BaseModel):
    format: Literal["singles", "doubles"]
    regulation_id: str | None = None
    members: list[TeamMemberIn]


class IssueOut(BaseModel):
    code: str
    message: str
    member_index: int | None = None


class TeamValidationOut(BaseModel):
    valid: bool
    regulation_id: str
    issues: list[IssueOut]


class DamageBuildIn(BaseModel):
    species: str
    ability: str | None = None
    item: str | None = None
    nature: str | None = None
    status: str = ""
    sp_spread: dict[str, int] = {}
    boosts: dict[str, int] = {}


class FieldConditionsIn(BaseModel):
    game_type: Literal["singles", "doubles"] = "singles"
    weather: str | None = None
    terrain: str | None = None
    attacker_side: dict = {}
    defender_side: dict = {}


class DamageCalculateRequest(BaseModel):
    attacker: DamageBuildIn
    defender: DamageBuildIn
    move: str
    field: FieldConditionsIn = FieldConditionsIn()


class DamageResultOut(BaseModel):
    damage_rolls: list[int]
    damage_min: int
    damage_max: int
    defender_max_hp: int
    hp_pct_min: float
    hp_pct_max: float
    ko_chance_text: str
    ko_chance: float | None
    modifiers: list[str]
