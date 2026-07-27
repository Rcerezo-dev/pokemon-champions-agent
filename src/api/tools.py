"""Tool definitions + dispatcher for the Fase 7 Claude integration.

Tools call the Fase 5-6 endpoint functions directly, in-process -- FastAPI's
route decorators return the original callable unchanged, so
`get_legal_pokemon` etc. are just plain functions here, no HTTP involved.
"""

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from src.api.main import (
    get_active_regulation_endpoint,
    get_legal_moves,
    get_legal_pokemon,
    get_pokemon_detail,
    get_top_usage,
    post_validate_team,
)
from src.api.schemas import TeamValidateRequest
from src.db.database import engine

TOOLS: list[dict] = [
    {
        "name": "get_active_regulation",
        "description": (
            "Devuelve el Regulation Set de Pokemon Champions vigente ahora mismo: "
            "nombre, fechas de vigencia, si Mega Evolucion esta permitida y notas de "
            "reglas (objetos duplicados, timers, etc.)."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_legal_pokemon",
        "description": (
            "Lista las especies/formas de Pokemon legales en una regulation (por "
            "defecto la activa). Usar antes de proponer cualquier Pokemon concreto "
            "para un equipo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "regulation_id": {
                    "type": "string",
                    "description": "Codigo de la regulation, p.ej. 'M-B'. Si se omite, usa la regulation activa.",
                },
            },
        },
    },
    {
        "name": "get_pokemon_detail",
        "description": (
            "Detalle de una especie: tipos, stats base, si es la forma por defecto, "
            "y si es legal en la regulation consultada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pokemon_id": {"type": "integer", "description": "id de la especie (PokeAPI id)."},
                "regulation_id": {"type": "string", "description": "Codigo de la regulation. Si se omite, usa la activa."},
            },
            "required": ["pokemon_id"],
        },
    },
    {
        "name": "get_legal_moves",
        "description": (
            "Movimientos que una especie puede usar y que estan habilitados en la "
            "regulation consultada (interseccion de su movepool con el pool global "
            "de movimientos activos)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pokemon_id": {"type": "integer", "description": "id de la especie."},
                "regulation_id": {"type": "string", "description": "Codigo de la regulation. Si se omite, usa la activa."},
            },
            "required": ["pokemon_id"],
        },
    },
    {
        "name": "get_meta_usage",
        "description": (
            "Ranking de % de uso real en torneos por especie para una regulation "
            "(dato duro, no percepcion). Cada fila indica si esta `verified` "
            "(contrastado entre 2 o mas fuentes)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "regulation_id": {"type": "string", "description": "Codigo de la regulation. Si se omite, usa la activa."},
                "limit": {"type": "integer", "description": "Maximo de filas a devolver (por defecto 20)."},
            },
        },
    },
    {
        "name": "validate_team",
        "description": (
            "Valida un equipo completo contra todas las reglas de Pokemon Champions: "
            "tamano de equipo por formato, Species/Item Clause, legalidad de "
            "especie/movimiento/item en la regulation, SP (66 total, max 32 por "
            "stat), numero de movimientos, y existencia de habilidad/naturaleza. "
            "Llamar SIEMPRE antes de presentar un equipo como valido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["singles", "doubles"]},
                "regulation_id": {"type": "string", "description": "Codigo de la regulation. Si se omite, usa la activa."},
                "members": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "species": {"type": "string"},
                            "item": {"type": "string"},
                            "ability": {"type": "string"},
                            "nature": {"type": "string"},
                            "sp_spread": {"type": "object", "additionalProperties": {"type": "integer"}},
                            "moves": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["species"],
                    },
                },
            },
            "required": ["format", "members"],
        },
    },
]


def run_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a single tool call against the real seeded DB. Returns a
    JSON-able dict -- either the result or {"error": ...} if a species/
    regulation id wasn't found, so the model can react instead of crashing."""
    with Session(engine) as session:
        try:
            if name == "get_active_regulation":
                return get_active_regulation_endpoint(session=session).model_dump(mode="json")
            if name == "get_legal_pokemon":
                rows = get_legal_pokemon(regulation_id=tool_input.get("regulation_id"), session=session)
                return {"pokemon": [r.model_dump(mode="json") for r in rows]}
            if name == "get_pokemon_detail":
                detail = get_pokemon_detail(
                    pokemon_id=tool_input["pokemon_id"],
                    regulation_id=tool_input.get("regulation_id"),
                    session=session,
                )
                return detail.model_dump(mode="json")
            if name == "get_legal_moves":
                rows = get_legal_moves(
                    pokemon_id=tool_input["pokemon_id"],
                    regulation_id=tool_input.get("regulation_id"),
                    session=session,
                )
                return {"moves": [r.model_dump(mode="json") for r in rows]}
            if name == "get_meta_usage":
                rows = get_top_usage(
                    regulation_id=tool_input.get("regulation_id"),
                    limit=tool_input.get("limit", 20),
                    session=session,
                )
                return {"usage": [r.model_dump(mode="json") for r in rows]}
            if name == "validate_team":
                payload = TeamValidateRequest(
                    format=tool_input["format"],
                    regulation_id=tool_input.get("regulation_id"),
                    members=tool_input["members"],
                )
                return post_validate_team(payload, session=session).model_dump(mode="json")
            return {"error": f"Unknown tool '{name}'."}
        except HTTPException as e:
            return {"error": e.detail}
