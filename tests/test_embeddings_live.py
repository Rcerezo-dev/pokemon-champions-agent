"""Fase 12: the one thing test_semantic_search.py can't cover by
monkeypatching -- an actual Gemini embedding call. Needs GEMINI_API_KEY in
.env, so it's excluded from the default `pytest` run like the Fase 10
scraper smoke tests; run explicitly with `pytest -m live`.
"""

import pytest

from src.semantic.embeddings import OUTPUT_DIMENSIONALITY, embed_documents, embed_query

pytestmark = pytest.mark.live


def test_embed_query_returns_a_vector_of_the_expected_size():
    vector = embed_query("a fast physical attacker with high speed")
    assert len(vector) == OUTPUT_DIMENSIONALITY
    assert any(v != 0 for v in vector)


def test_embed_documents_batches_multiple_texts():
    vectors = embed_documents(["Charizard is a Fire/Flying Pokemon.", "Blastoise is a Water Pokemon."])
    assert len(vectors) == 2
    assert len(vectors[0]) == OUTPUT_DIMENSIONALITY
    assert vectors[0] != vectors[1]


def test_embed_documents_empty_list_returns_empty():
    assert embed_documents([]) == []
