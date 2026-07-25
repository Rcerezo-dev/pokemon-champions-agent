"""Serebii scraper for Pokémon Champions move/item data.

Three things, all read from plain server-rendered HTML tables:
  - the current live catalog of usable moves (moves.shtml)
  - the current live catalog of usable items (items.shtml)
  - a given species' movepool (pokedex-champions/{slug}/)

Champions collapses the level-up/TM/egg-move distinction into one flat
"can this Pokémon use this move" table (confirmed by inspecting Charizard's
page: a single "Standard Moves" table, no learn-method column), so the
per-species movepool is just every /attackdex-champions/ link on that page.

robots.txt only disallows /hidden/ranch/ and /crossword/ -- Champions pages
are unrestricted and have no Crawl-delay, but we still self-impose one to
avoid hammering the site across ~300 per-species requests.
"""

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "serebii_champions"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
COURTESY_DELAY_SECONDS = 1.0

MOVES_URL = "https://www.serebii.net/pokemonchampions/moves.shtml"
ITEMS_URL = "https://www.serebii.net/pokemonchampions/items.shtml"


class SerebiiChampionsScrapeError(RuntimeError):
    pass


def _unescape(text: str) -> str:
    return (
        text.replace("&#x27;", "'")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&eacute;", "é")
    )


def _fetch_html(cache_name: str, url: str, client: httpx.Client) -> str:
    cache_file = CACHE_DIR / f"{cache_name}_{datetime.now(timezone.utc):%Y%m%d}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    resp = client.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise SerebiiChampionsScrapeError(f"{e.response.status_code} fetching {url}") from e
    time.sleep(COURTESY_DELAY_SECONDS)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


_ATTACKDEX_RE = re.compile(r'attackdex-champions/[a-z0-9]+\.shtml">([^<]+)</a>')
_ITEMDEX_RE = re.compile(r'<td class="fooinfo"><a href="/itemdex/[a-z0-9]+\.shtml">([^<]+)</a>')


def fetch_moves_catalog(client: Optional[httpx.Client] = None) -> set[str]:
    """Every move name currently usable in Champions (live snapshot, not
    scoped to a specific regulation)."""
    owns_client = client is None
    client = client or httpx.Client()
    try:
        html = _fetch_html("moves", MOVES_URL, client)
        names = {_unescape(n) for n in _ATTACKDEX_RE.findall(html)}
        if not names:
            raise SerebiiChampionsScrapeError("No /attackdex-champions/ links found on moves.shtml -- page structure may have changed.")
        return names
    finally:
        if owns_client:
            client.close()


def fetch_items_catalog(client: Optional[httpx.Client] = None) -> set[str]:
    """Every held item currently usable in Champions (live catalog -- broader
    than any one regulation's legal set, e.g. includes Mega Stones for
    species not currently in the legal roster)."""
    owns_client = client is None
    client = client or httpx.Client()
    try:
        html = _fetch_html("items", ITEMS_URL, client)
        names = {_unescape(n) for n in _ITEMDEX_RE.findall(html)}
        if not names:
            raise SerebiiChampionsScrapeError("No itemdex links found on items.shtml -- page structure may have changed.")
        return names
    finally:
        if owns_client:
            client.close()


def fetch_species_movepool(slug: str, client: Optional[httpx.Client] = None) -> set[str]:
    """Every move name a given species can use, e.g. slug='charizard'."""
    owns_client = client is None
    client = client or httpx.Client()
    try:
        url = f"https://www.serebii.net/pokedex-champions/{slug}/"
        html = _fetch_html(f"species_{slug}", url, client)
        names = {_unescape(n) for n in _ATTACKDEX_RE.findall(html)}
        if not names:
            raise SerebiiChampionsScrapeError(f"No /attackdex-champions/ links found on pokedex-champions/{slug}/ -- page structure may have changed or slug is wrong.")
        return names
    finally:
        if owns_client:
            client.close()
