"""Internal, read-only API over the data seeded by Fases 1-4.

Run: uvicorn src.api.main:app --reload
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Session, select

from src.db.active_regulation import get_active_regulation
from src.db.database import engine
from src.db.models import (
    Move,
    PokemonMovepool,
    PokemonSpecies,
    RegulationLegalMove,
    RegulationLegalPokemon,
    RegulationSet,
    UsageStat,
)
from src.api.schemas import (
    MoveOut,
    PokemonDetailOut,
    PokemonSummaryOut,
    RegulationOut,
    UsageOut,
)

app = FastAPI(title="Pokémon Champions Agent API", version="0.1.0")


def get_session():
    with Session(engine) as session:
        yield session


def resolve_regulation(
    session: Session,
    regulation_id: Optional[str] = None,
) -> RegulationSet:
    if regulation_id is None:
        return get_active_regulation(session)
    reg = session.get(RegulationSet, regulation_id)
    if reg is None:
        raise HTTPException(404, f"No regulation '{regulation_id}' in the DB.")
    return reg


@app.get("/")
def root():
    return {"name": "Pokémon Champions Agent API", "docs": "/docs"}


@app.get("/regulation/active", response_model=RegulationOut)
def get_active_regulation_endpoint(session: Session = Depends(get_session)):
    reg = get_active_regulation(session)
    return RegulationOut(
        id=reg.id, name=reg.name, start_date=reg.start_date, end_date=reg.end_date, mega_allowed=reg.mega_allowed, notes=reg.notes
    )


@app.get("/pokemon/legal", response_model=list[PokemonSummaryOut])
def get_legal_pokemon(regulation_id: Optional[str] = Query(default=None), session: Session = Depends(get_session)):
    reg = resolve_regulation(session, regulation_id)
    rows = session.exec(
        select(RegulationLegalPokemon, PokemonSpecies)
        .join(PokemonSpecies, RegulationLegalPokemon.pokemon_species_id == PokemonSpecies.id)
        .where(RegulationLegalPokemon.regulation_id == reg.id)
        .order_by(PokemonSpecies.name)
    ).all()
    return [
        PokemonSummaryOut(pokemon_species_id=sp.id, name=sp.name, types=sp.types.split(","), verified=legal.verified)
        for legal, sp in rows
    ]


@app.get("/pokemon/{pokemon_id}", response_model=PokemonDetailOut)
def get_pokemon_detail(pokemon_id: int, regulation_id: Optional[str] = Query(default=None), session: Session = Depends(get_session)):
    sp = session.get(PokemonSpecies, pokemon_id)
    if sp is None:
        raise HTTPException(404, f"No Pokémon species with id {pokemon_id}.")
    reg = resolve_regulation(session, regulation_id)
    legal = session.exec(
        select(RegulationLegalPokemon).where(
            RegulationLegalPokemon.regulation_id == reg.id, RegulationLegalPokemon.pokemon_species_id == pokemon_id
        )
    ).first()
    return PokemonDetailOut(
        id=sp.id,
        name=sp.name,
        types=sp.types.split(","),
        base_stats=json.loads(sp.base_stats_json),
        is_default=sp.is_default,
        legal_in_regulation=legal is not None,
    )


@app.get("/pokemon/{pokemon_id}/legal-moves", response_model=list[MoveOut])
def get_legal_moves(pokemon_id: int, regulation_id: Optional[str] = Query(default=None), session: Session = Depends(get_session)):
    if session.get(PokemonSpecies, pokemon_id) is None:
        raise HTTPException(404, f"No Pokémon species with id {pokemon_id}.")
    reg = resolve_regulation(session, regulation_id)

    movepool_ids = {
        row.move_id
        for row in session.exec(select(PokemonMovepool).where(PokemonMovepool.pokemon_species_id == pokemon_id))
    }
    regulation_move_ids = {
        row.move_id for row in session.exec(select(RegulationLegalMove).where(RegulationLegalMove.regulation_id == reg.id))
    }
    legal_move_ids = movepool_ids & regulation_move_ids
    if not legal_move_ids:
        return []
    moves = session.exec(select(Move).where(Move.id.in_(list(legal_move_ids))).order_by(Move.name)).all()
    return [MoveOut(id=m.id, name=m.name, type=m.type, category=m.category, power=m.power, accuracy=m.accuracy, pp=m.pp) for m in moves]


@app.get("/meta/top-usage", response_model=list[UsageOut])
def get_top_usage(
    regulation_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=500),
    session: Session = Depends(get_session),
):
    reg = resolve_regulation(session, regulation_id)
    rows = session.exec(
        select(UsageStat, PokemonSpecies)
        .join(PokemonSpecies, UsageStat.pokemon_species_id == PokemonSpecies.id)
        .where(UsageStat.regulation_id == reg.id)
        .order_by(UsageStat.usage_pct.desc())
        .limit(limit)
    ).all()
    return [UsageOut(pokemon_species_id=sp.id, name=sp.name, usage_pct=u.usage_pct, verified=u.verified) for u, sp in rows]
