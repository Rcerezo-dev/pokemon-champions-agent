"""semantic_search_pokemon wiring, with embed_query monkeypatched so this
doesn't need a real GEMINI_API_KEY -- the actual Gemini call is covered
separately by a `live`-marked test (see test_embeddings_live.py)."""

import pytest

from src.semantic import search, store


@pytest.fixture(autouse=True)
def isolated_lancedb(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_DIR", tmp_path / "lancedb")


@pytest.fixture(autouse=True)
def fake_embed_query(monkeypatch):
    monkeypatch.setattr(search, "embed_query", lambda text: [1.0, 0.0])


def test_semantic_search_returns_typed_results():
    store.rebuild_table(
        [
            {
                "pokemon_species_id": 6,
                "name": "charizard",
                "type_primary": "fire",
                "type_secondary": "flying",
                "regulation_id": "TEST",
                "doc_text": "Charizard doc text",
                "usage_pct": 5.5,
                "verified_usage": True,
                "vector": [1.0, 0.0],
            }
        ]
    )
    results = search.semantic_search_pokemon("strong fire attacker")
    assert len(results) == 1
    r = results[0]
    assert r.pokemon_species_id == 6
    assert r.name == "charizard"
    assert r.types == ["fire", "flying"]
    assert r.doc_text == "Charizard doc text"
    assert r.usage_pct == 5.5
    assert r.verified_usage is True
    assert r.distance == pytest.approx(0.0)


def test_semantic_search_with_no_index_returns_empty():
    assert search.semantic_search_pokemon("anything") == []
