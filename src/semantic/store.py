"""Fase 12: local vector store over the per-species documents (documents.py)
and their Gemini embeddings (embeddings.py).

LanceDB, not Chroma/pgvector: embedded (no server process), file-based under
data/lancedb/ (same convention as data/raw/, data/logs/), and its `.search(
vector).where(sql)` already does exactly the hybrid "structured filter then
similarity rank" the roadmap asks for (verified against LanceDB directly --
see PROGRESS.md). Chroma would work too (CLAUDE.md names both as acceptable
for a SQLite-based project) but pulls in a default ONNX embedding pipeline
we don't use, since embeddings come from Gemini.

The table is a full snapshot of the *currently* Champions-legal roster, not
a history across regulations -- seed_embeddings.py overwrites it every run,
matching the roadmap's "regenerate whenever the roster/movesets change".
"""

import re
from pathlib import Path
from typing import Optional

import lancedb

_SAFE_TYPE_NAME_RE = re.compile(r"^[a-z]+$")

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "lancedb"
TABLE_NAME = "pokemon_docs"


def connect():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(DB_DIR))


def rebuild_table(rows: list[dict]) -> None:
    """Full overwrite -- rows must each have at minimum: pokemon_species_id,
    name, type_primary, type_secondary (str | None), regulation_id, doc_text,
    usage_pct (float | None), verified_usage (bool), vector (list[float])."""
    db = connect()
    db.create_table(TABLE_NAME, data=rows, mode="overwrite")


def search(query_vector: list[float], type_filter: Optional[str] = None, limit: int = 10) -> list[dict]:
    db = connect()
    if TABLE_NAME not in db.list_tables().tables:
        return []
    table = db.open_table(TABLE_NAME)
    query = table.search(query_vector)
    if type_filter:
        t = type_filter.strip().lower()
        if not _SAFE_TYPE_NAME_RE.match(t):
            raise ValueError(f"Invalid type filter '{type_filter}' -- must be a plain type name (e.g. 'fire').")
        query = query.where(f"type_primary = '{t}' OR type_secondary = '{t}'")
    return query.limit(limit).to_list()
