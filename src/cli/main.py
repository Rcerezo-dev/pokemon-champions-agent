"""Fase 9: CLI de uso (typer/rich) -- crear-equipo, validar-equipo, ver-meta.

Reutiliza el motor de validacion (Fase 6) y `resolve_regulation` de la API
(Fase 5) directamente via importacion, sin pasar por HTTP -- mismo criterio
in-process que ya usa src/api/tools.py (Fase 7).

Uso: python -m src.cli.main --help
"""

import json
from datetime import datetime, timezone
from typing import Optional

import typer
from fastapi import HTTPException
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from src.api.main import resolve_regulation
from src.db.active_regulation import get_active_regulation
from src.db.database import engine, init_db
from src.db.models import PokemonSpecies, UsageStat, UserTeam
from src.validation.team_validator import TEAM_SIZE_BOUNDS, TeamMember, ValidationResult, validate_team

app = typer.Typer(help="Asistente de equipos de Pokémon Champions")
console = Console()

STAT_ORDER = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]


def _resolve_or_exit(session: Session, regulation_id: Optional[str]):
    try:
        return resolve_regulation(session, regulation_id)
    except HTTPException as e:
        console.print(f"[bold red]Error:[/] {e.detail}")
        raise typer.Exit(1)


def _print_validation(result: ValidationResult, regulation_id: str) -> None:
    if result.valid:
        console.print(f"[bold green]Equipo valido[/] para la regulation {regulation_id}.")
        return
    console.print(f"[bold red]Equipo invalido[/] para la regulation {regulation_id} -- {len(result.issues)} problema(s):")
    table = Table(show_header=True, header_style="bold")
    table.add_column("#")
    table.add_column("Codigo")
    table.add_column("Mensaje")
    for issue in result.issues:
        table.add_row(str(issue.member_index) if issue.member_index is not None else "-", issue.code, issue.message)
    console.print(table)


@app.command("ver-meta")
def ver_meta(
    regulation_id: Optional[str] = typer.Option(None, "--regulation-id", help="Por defecto, la regulation activa."),
    limit: int = typer.Option(20, "--limit", help="Cuantos Pokemon mostrar."),
):
    """Muestra el % de uso real en torneos de los Pokemon mas usados."""
    init_db()
    with Session(engine) as session:
        reg = _resolve_or_exit(session, regulation_id)
        rows = session.exec(
            select(UsageStat, PokemonSpecies)
            .join(PokemonSpecies, UsageStat.pokemon_species_id == PokemonSpecies.id)
            .where(UsageStat.regulation_id == reg.id)
            .order_by(UsageStat.usage_pct.desc())
            .limit(limit)
        ).all()

    table = Table(title=f"Top {limit} de uso -- {reg.id}")
    table.add_column("#", justify="right")
    table.add_column("Pokemon")
    table.add_column("% uso", justify="right")
    table.add_column("Verificado")
    for i, (u, sp) in enumerate(rows, start=1):
        table.add_row(str(i), sp.name, f"{u.usage_pct:.1f}%", "si" if u.verified else "no")
    console.print(table)


@app.command("validar-equipo")
def validar_equipo(
    nombre: str = typer.Argument(..., help="Nombre del equipo guardado con 'crear-equipo'."),
    regulation_id: Optional[str] = typer.Option(
        None, "--regulation-id", help="Por defecto, la regulation activa (util para ver si un equipo viejo sigue siendo legal)."
    ),
):
    """Revalida un equipo ya guardado contra las reglas actuales."""
    init_db()
    with Session(engine) as session:
        team = session.exec(
            select(UserTeam).where(UserTeam.name == nombre).order_by(UserTeam.created_at.desc())
        ).first()
        if team is None:
            console.print(f"[bold red]Error:[/] no hay ningun equipo guardado con el nombre '{nombre}'.")
            raise typer.Exit(1)
        reg = _resolve_or_exit(session, regulation_id)
        members = [TeamMember(**m) for m in json.loads(team.team_json)]
        result = validate_team(session, reg, team.format, members)
    _print_validation(result, reg.id)


@app.command("crear-equipo")
def crear_equipo():
    """Construye un equipo Pokemon a Pokemon, lo valida y opcionalmente lo guarda."""
    init_db()
    with Session(engine) as session:
        reg = get_active_regulation(session)

        fmt = ""
        while fmt not in TEAM_SIZE_BOUNDS:
            fmt = typer.prompt("Formato (singles/doubles)").strip().lower()
        lo, hi = TEAM_SIZE_BOUNDS[fmt]
        console.print(f"Equipo para regulation [bold]{reg.id}[/] ({fmt}): entre {lo} y {hi} Pokemon.")

        members: list[TeamMember] = []
        while True:
            console.print(f"\n-- Pokemon #{len(members) + 1} --")
            species = typer.prompt("Especie (nombre interno, ej. 'charizard')").strip().lower()
            item = typer.prompt("Objeto (vacio = ninguno)", default="", show_default=False).strip() or None
            ability = typer.prompt("Habilidad (vacio = ninguna)", default="", show_default=False).strip() or None
            nature = typer.prompt("Naturaleza (vacio = ninguna)", default="", show_default=False).strip() or None
            sp_line = typer.prompt(
                f"SP como {','.join(STAT_ORDER)} (ej. '0,0,0,32,0,32'; vacio = todo 0)", default="", show_default=False
            ).strip()
            sp_spread: dict[str, int] = {}
            if sp_line:
                parts = [p.strip() for p in sp_line.split(",")]
                if len(parts) == len(STAT_ORDER):
                    sp_spread = {stat: int(p) for stat, p in zip(STAT_ORDER, parts) if p}
                else:
                    console.print("[yellow]Aviso:[/] numero de valores no coincide con las stats -- se ignora el SP.")
            moves_line = typer.prompt("Movimientos separados por coma (ej. 'flamethrower,solar-beam')", default="", show_default=False).strip()
            moves = [m.strip() for m in moves_line.split(",") if m.strip()]

            members.append(TeamMember(species=species, item=item, ability=ability, nature=nature, sp_spread=sp_spread, moves=moves))

            if len(members) >= hi:
                break
            if not typer.confirm("Anadir otro Pokemon?", default=len(members) < lo):
                break

        result = validate_team(session, reg, fmt, members)
        _print_validation(result, reg.id)

        if typer.confirm("Guardar este equipo?", default=True):
            name = typer.prompt("Nombre para guardarlo").strip()
            session.add(
                UserTeam(
                    created_at=datetime.now(timezone.utc),
                    regulation_id=reg.id,
                    name=name,
                    format=fmt,
                    team_json=json.dumps([m.__dict__ for m in members]),
                )
            )
            session.commit()
            console.print(f"[bold green]Guardado[/] como '{name}'. Usa 'validar-equipo {name}' para revalidarlo mas adelante.")


if __name__ == "__main__":
    app()
