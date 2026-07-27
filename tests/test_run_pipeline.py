"""Fase 8: tests del orquestador. No re-ejecuta los scrapers reales (son
lentos y dependen de red) -- solo la logica propia de run_pipeline.py:
captura de exito/fallo por paso y el aviso de proximidad de regulation,
esto ultimo contra la BD real ya sembrada (misma idea que tests/test_api.py)."""

from src.db.run_pipeline import _check_regulation_proximity, _run_step


def test_run_step_ok_captures_stdout():
    def fn():
        print("hello from step")

    result = _run_step("dummy", fn)
    assert result.startswith("--- dummy: OK ---")
    assert "hello from step" in result


def test_run_step_failed_captures_traceback():
    def fn():
        raise ValueError("boom")

    result = _run_step("dummy", fn)
    assert result.startswith("--- dummy: FAILED ---")
    assert "ValueError: boom" in result


def test_check_regulation_proximity_against_real_db():
    result = _check_regulation_proximity()
    assert result.startswith("--- regulation proximity:")
    assert "OK" in result or "WARNING" in result
