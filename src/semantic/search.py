"""Fase 12: the semantic_search_pokemon entry point -- structured filter
first (only species already indexed, i.e. legal in the regulation the index
was last built for, optionally narrowed by type), then similarity ranking
over that subset, per the roadmap's "búsqueda híbrida"."""

from dataclasses import dataclass
from typing import Optional

from src.semantic import store
from src.semantic.embeddings import embed_query


@dataclass
class SemanticSearchResult:
    pokemon_species_id: int
    name: str
    types: list[str]
    doc_text: str
    usage_pct: Optional[float]
    verified_usage: bool
    distance: float


def semantic_search_pokemon(query: str, type_filter: Optional[str] = None, limit: int = 10) -> list[SemanticSearchResult]:
    query_vector = embed_query(query)
    rows = store.search(query_vector, type_filter=type_filter, limit=limit)
    return [
        SemanticSearchResult(
            pokemon_species_id=r["pokemon_species_id"],
            name=r["name"],
            types=[t for t in (r["type_primary"], r["type_secondary"]) if t],
            doc_text=r["doc_text"],
            usage_pct=r["usage_pct"],
            verified_usage=r["verified_usage"],
            distance=r["_distance"],
        )
        for r in rows
    ]
