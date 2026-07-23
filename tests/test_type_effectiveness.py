import pytest
from sqlmodel import Session, SQLModel, create_engine

from src.damage_calc.type_effectiveness import effectiveness
from src.db.models import TypeChart

CHART = [
    ("water", "fire", 2.0),
    ("fire", "water", 0.5),
    ("electric", "ground", 0.0),
    ("electric", "flying", 2.0),
    ("normal", "ghost", 0.0),
    ("fighting", "normal", 2.0),
]


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for attacking, defending, mult in CHART:
            s.add(TypeChart(attacking_type=attacking, defending_type=defending, multiplier=mult))
        s.commit()
        yield s


def test_super_effective(session):
    assert effectiveness(session, "water", ["fire"]) == 2.0


def test_not_very_effective(session):
    assert effectiveness(session, "fire", ["water"]) == 0.5


def test_immune(session):
    assert effectiveness(session, "electric", ["ground"]) == 0.0


def test_dual_type_stacks_multipliers(session):
    # electric vs ground/flying: 0x * 2x = 0x (immunity wins)
    session.add(TypeChart(attacking_type="electric", defending_type="ground", multiplier=0.0))
    assert effectiveness(session, "electric", ["ground", "flying"]) == 0.0


def test_missing_pair_raises(session):
    with pytest.raises(ValueError):
        effectiveness(session, "dragon", ["steel"])
