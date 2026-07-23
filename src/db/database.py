import os
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine

from src.db import models  # noqa: F401 -- registers tables on SQLModel.metadata

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "pokemon_champions.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(DATABASE_URL)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
