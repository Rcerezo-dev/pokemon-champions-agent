"""Internal API over the data seeded by Fases 1-4, plus the Fase 6 team
validator.

Run: uvicorn src.api.main:app --reload
"""

import json
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Session, select

from src.damage_calc.calculator import DamageBuild, DamageCalcError, FieldConditions, calculate_damage
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
    DamageCalculateRequest,
    DamageResultOut,
    IssueOut,
    MoveOut,
    PokemonDetailOut,
    PokemonSummaryOut,
    RegulationOut,
    TeamValidateRequest,
    TeamValidationOut,
    UsageOut,
)
from src.validation.team_validator import TeamMember, validate_team

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


@app.post("/team/validate", response_model=TeamValidationOut)
def post_validate_team(payload: TeamValidateRequest, session: Session = Depends(get_session)):
    reg = resolve_regulation(session, payload.regulation_id)
    members = [
        TeamMember(species=m.species, item=m.item, ability=m.ability, nature=m.nature, sp_spread=m.sp_spread, moves=m.moves)
        for m in payload.members
    ]
    result = validate_team(session, reg, payload.format, members)
    return TeamValidationOut(
        valid=result.valid,
        regulation_id=reg.id,
        issues=[IssueOut(code=i.code, message=i.message, member_index=i.member_index) for i in result.issues],
    )


@app.post("/damage/calculate", response_model=DamageResultOut)
def post_calculate_damage(payload: DamageCalculateRequest, session: Session = Depends(get_session)):
    attacker = DamageBuild(**payload.attacker.model_dump())
    defender = DamageBuild(**payload.defender.model_dump())
    field = FieldConditions(**payload.field.model_dump())
    try:
        result = calculate_damage(session, attacker, defender, payload.move, field)
    except DamageCalcError as e:
        raise HTTPException(422, str(e))
    return DamageResultOut(
        damage_rolls=result.damage_rolls,
        damage_min=result.damage_min,
        damage_max=result.damage_max,
        defender_max_hp=result.defender_max_hp,
        hp_pct_min=result.hp_pct_min,
        hp_pct_max=result.hp_pct_max,
        ko_chance_text=result.ko_chance_text,
        ko_chance=result.ko_chance,
        modifiers=result.modifiers,
    )
