from sqlmodel import Session, select

from src.db.models import TypeChart


def effectiveness(session: Session, attacking_type: str, defending_types: list[str]) -> float:
    """Combined type-effectiveness multiplier of one attacking type against
    one or two defending types (e.g. ["fire", "flying"])."""
    multiplier = 1.0
    for defending_type in defending_types:
        row = session.exec(
            select(TypeChart).where(
                TypeChart.attacking_type == attacking_type,
                TypeChart.defending_type == defending_type,
            )
        ).first()
        if row is None:
            raise ValueError(f"No type_chart entry for {attacking_type} -> {defending_type}")
        multiplier *= row.multiplier
    return multiplier
