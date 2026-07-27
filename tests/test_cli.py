"""Fase 9: smoke tests del CLI (typer) contra la BD real -- mismo criterio
que tests/test_api.py y tests/test_tools.py: un solo entorno local,
aserciones laxas (no depende de que numeros/legalidad concretos no cambien
si se re-ejecuta un scraper)."""

from typer.testing import CliRunner

from sqlmodel import Session, select

from src.cli.main import app
from src.db.database import engine
from src.db.models import UserTeam

runner = CliRunner()

_TEST_TEAM_NAME = "_pytest_test_team"


def _delete_test_team():
    with Session(engine) as session:
        for row in session.exec(select(UserTeam).where(UserTeam.name == _TEST_TEAM_NAME)):
            session.delete(row)
        session.commit()


def test_ver_meta_shows_a_table():
    result = runner.invoke(app, ["ver-meta", "--limit", "3"])
    assert result.exit_code == 0
    assert "Top 3 de uso" in result.output


def test_validar_equipo_unknown_name_exits_nonzero():
    result = runner.invoke(app, ["validar-equipo", "_no_deberia_existir_"])
    assert result.exit_code == 1
    assert "no hay ningun equipo" in result.output


def test_crear_equipo_then_validar_equipo_roundtrip():
    _delete_test_team()
    try:
        # 1 Pokemon con datos deliberadamente incompletos -- basta con que el
        # comando corra de punta a punta y guarde el equipo; la correccion de
        # las reglas ya la cubre tests/test_team_validator.py.
        stdin = "singles\nmissingno\n\n\n\n\n\nno\ny\n" + _TEST_TEAM_NAME + "\n"
        result = runner.invoke(app, ["crear-equipo"], input=stdin)
        assert result.exit_code == 0
        assert f"Guardado" in result.output

        with Session(engine) as session:
            saved = session.exec(select(UserTeam).where(UserTeam.name == _TEST_TEAM_NAME)).first()
        assert saved is not None
        assert saved.format == "singles"

        result = runner.invoke(app, ["validar-equipo", _TEST_TEAM_NAME])
        assert result.exit_code == 0
        assert "unknown_species" in result.output  # 'missingno' no existe
    finally:
        _delete_test_team()
