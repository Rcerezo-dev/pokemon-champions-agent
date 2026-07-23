from typing import Optional

from sqlmodel import Field, SQLModel


class PokemonSpecies(SQLModel, table=True):
    """Static species data from PokeAPI: id matches the PokeAPI pokemon id."""

    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    types: str  # comma-separated, e.g. "fire,flying"
    base_stats_json: str  # {"hp":45,"attack":49,"defense":49,"special-attack":65,"special-defense":65,"speed":45}


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
