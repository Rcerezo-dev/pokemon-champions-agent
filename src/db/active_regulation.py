from datetime import datetime, timezone

from sqlmodel import Session, select

from src.db.models import RegulationSet


def get_active_regulation(session: Session) -> RegulationSet:
    now = datetime.now(timezone.utc)
    for reg in session.exec(select(RegulationSet)).all():
        start = reg.start_date if reg.start_date.tzinfo else reg.start_date.replace(tzinfo=timezone.utc)
        end = reg.end_date if reg.end_date.tzinfo else reg.end_date.replace(tzinfo=timezone.utc)
        if start <= now < end:
            return reg
    raise RuntimeError("No active RegulationSet in the DB -- run `python -m src.db.seed_regulation` first.")
