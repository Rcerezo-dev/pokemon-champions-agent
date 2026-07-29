"""Fase 12: Gemini embeddings (gemini-embedding-001) -- reuses GEMINI_API_KEY,
the same key already used for the Fase 7 chat loop, so this doesn't add a new
vendor/API key to the project. Chosen over a local sentence-transformers
model to avoid pulling in a ~1-2GB PyTorch dependency into what has so far
been a lightweight project (confirmed with the user).

Network is only needed when (re)building the index (seed_embeddings.py) --
search itself, once embeddings exist, still needs one embed_content call per
query (there's no local-only query embedding), but that's a single small
request, not a re-index.
"""

import os

from google.genai import Client
from google.genai.types import EmbedContentConfig

MODEL = "gemini-embedding-001"
OUTPUT_DIMENSIONALITY = 768  # smaller than the 3072 default -- plenty for a few hundred species, less storage


class EmbeddingError(RuntimeError):
    pass


def _client() -> Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EmbeddingError("GEMINI_API_KEY not set in the environment (see .env.example).")
    return Client(api_key=api_key)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embeddings for documents being indexed (task_type=RETRIEVAL_DOCUMENT)."""
    if not texts:
        return []
    response = _client().models.embed_content(
        model=MODEL,
        contents=texts,
        config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=OUTPUT_DIMENSIONALITY),
    )
    return [e.values for e in response.embeddings]


def embed_query(text: str) -> list[float]:
    """Embedding for a search query (task_type=RETRIEVAL_QUERY -- Gemini's
    embedding model is trained asymmetrically for retrieval, so document and
    query embeddings deliberately use different task types)."""
    response = _client().models.embed_content(
        model=MODEL,
        contents=text,
        config=EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=OUTPUT_DIMENSIONALITY),
    )
    return response.embeddings[0].values
