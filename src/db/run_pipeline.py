"""Fase 8: automatizacion del pipeline de scraping (Fases 2-4).

Ejecuta seed_regulation -> seed_movepool -> seed_usage en orden, capturando
la salida de cada uno (ya trae resumenes de exito/discrepancias) a un log
con fecha en data/logs/, y avisa si el Regulation Set activo esta por
terminar. Cada paso se ejecuta aunque el anterior falle -- un fallo de
scraping se registra de forma visible en el log, nunca en silencio.

Uso manual: python -m src.db.run_pipeline
Programacion periodica: ver scripts/register_scheduled_task.ps1
(registra una tarea diaria en el Task Scheduler de Windows).
"""

import contextlib
import io
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from src.db import seed_movepool, seed_regulation, seed_usage
from src.db.active_regulation import get_active_regulation
from src.db.database import engine

LOG_DIR = Path("data/logs")
REGULATION_WARNING_DAYS = 7

STEPS = [
    ("regulation (Fase 2)", seed_regulation.main),
    ("movepool (Fase 3)", seed_movepool.main),
    ("usage (Fase 4)", seed_usage.main),
]


def _run_step(name: str, fn) -> str:
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            fn()
        status = "OK"
    except Exception:
        status = "FAILED"
        buf.write(traceback.format_exc())
    return f"--- {name}: {status} ---\n{buf.getvalue()}"


def _check_regulation_proximity() -> str:
    try:
        with Session(engine) as session:
            reg = get_active_regulation(session)
    except Exception as e:
        return f"--- regulation proximity: FAILED ({e}) ---"
    end = reg.end_date if reg.end_date.tzinfo else reg.end_date.replace(tzinfo=timezone.utc)
    days_left = (end - datetime.now(timezone.utc)).days
    level = "WARNING" if days_left <= REGULATION_WARNING_DAYS else "OK"
    return f"--- regulation proximity: {level} - {reg.id} termina en {days_left} dias ({end.date()}) ---"


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    log_path = LOG_DIR / f"pipeline_{started.strftime('%Y-%m-%dT%H-%M-%S')}.log"

    lines = [f"Pipeline run started at {started.isoformat()}"]
    failed = False
    for name, fn in STEPS:
        result = _run_step(name, fn)
        lines.append(result)
        if result.split("\n", 1)[0].endswith("FAILED ---"):
            failed = True
    lines.append(_check_regulation_proximity())

    log_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {log_path}")
    if failed:
        print("One or more steps FAILED -- see log for the traceback.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
