"""LanceDB is exercised for real here (it's an embedded local library, no
network/API key needed) -- only the Gemini embedding calls need a real key,
so these tests use synthetic vectors instead of src/semantic/embeddings.py.
Uses a throwaway DB_DIR (monkeypatched) instead of the real data/lancedb/."""

import pytest

from src.semantic import store


@pytest.fixture(autouse=True)
def isolated_lancedb(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_DIR", tmp_path / "lancedb")


def _row(species_id, name, type_primary, type_secondary, vector, usage_pct=None, verified=False):
    return {
        "pokemon_species_id": species_id,
        "name": name,
        "type_primary": type_primary,
        "type_secondary": type_secondary,
        "regulation_id": "TEST",
        "doc_text": f"{name} doc",
        "usage_pct": usage_pct,
        "verified_usage": verified,
        "vector": vector,
    }


ROWS = [
    _row(6, "charizard", "fire", "flying", [1.0, 0.0, 0.0], usage_pct=5.0, verified=True),
    _row(9, "blastoise", "water", None, [0.0, 1.0, 0.0], usage_pct=3.0, verified=False),
    _row(3, "venusaur", "grass", "poison", [0.0, 0.0, 1.0]),
]


def test_search_with_no_table_returns_empty():
    assert store.search([1.0, 0.0, 0.0]) == []


def test_search_ranks_by_similarity():
    store.rebuild_table(ROWS)
    results = store.search([1.0, 0.0, 0.0], limit=3)
    assert results[0]["name"] == "charizard"  # exact match to charizard's vector


def test_search_type_filter_matches_primary_or_secondary():
    store.rebuild_table(ROWS)
    results = store.search([0.0, 0.0, 1.0], type_filter="poison", limit=10)
    assert {r["name"] for r in results} == {"venusaur"}


def test_search_type_filter_excludes_non_matching():
    store.rebuild_table(ROWS)
    results = store.search([1.0, 0.0, 0.0], type_filter="water", limit=10)
    assert {r["name"] for r in results} == {"blastoise"}


def test_search_rejects_unsafe_type_filter():
    store.rebuild_table(ROWS)
    with pytest.raises(ValueError, match="Invalid type filter"):
        store.search([1.0, 0.0, 0.0], type_filter="fire' OR '1'='1")


def test_rebuild_table_overwrites_previous_rows():
    store.rebuild_table(ROWS)
    store.rebuild_table([_row(25, "pikachu", "electric", None, [0.0, 1.0, 0.0])])
    results = store.search([0.0, 1.0, 0.0], limit=10)
    assert {r["name"] for r in results} == {"pikachu"}
