"""Thin client for the public PokeAPI (https://pokeapi.co).

Every response is cached as raw JSON under data/raw/pokeapi/ so re-running
the seed script doesn't re-hit the API and reprocessing never needs a
re-fetch (per CLAUDE.md: cache raw source data with date -- file mtime
serves as the retrieval date here since PokeAPI data has no source/date
columns in the schema, it's static reference data).
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://pokeapi.co/api/v2"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "pokeapi"


_UNSAFE_CHARS = str.maketrans({c: "_" for c in "?&=:*<>|\""})


def _cache_path(path: str) -> Path:
    safe = path.strip("/").replace("/", "_").translate(_UNSAFE_CHARS)
    return CACHE_DIR / f"{safe}.json"


async def fetch_json(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    cache_file = _cache_path(path)
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    resp = await client.get(f"{BASE_URL}/{path.lstrip('/')}")
    resp.raise_for_status()
    data = resp.json()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


async def fetch_list(client: httpx.AsyncClient, endpoint: str) -> list[dict[str, str]]:
    """Full list of {name, url} for an endpoint (e.g. 'pokemon', 'move')."""
    data = await fetch_json(client, f"{endpoint}?limit=100000")
    return data["results"]


async def fetch_many(
    client: httpx.AsyncClient, urls: list[str], concurrency: int = 15
) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)

    async def _get(url: str) -> dict[str, Any]:
        path = url.split("/api/v2/", 1)[1]
        async with sem:
            return await fetch_json(client, path)

    return await asyncio.gather(*[_get(u) for u in urls])


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "pokemon-champions-agent/0.1 (local personal use)"})
