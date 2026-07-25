"""MetaVGC scraper -- per-regulation snapshot of legal Pokémon, allowed items
and allowed moves for Pokémon Champions. Server-rendered (Next.js SSR, no JS
execution needed -- confirmed by fetching the raw HTML directly). robots.txt
allows /guides/.

Each of the three lists lives under a `<h2 id="{slug}-{count}">` heading
followed immediately by one `<table>` of `<td>` cells, e.g.:
  <h2 id="allowed-items-148">Allowed items (148)</h2> ... <table>...</table>
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "metavgc"
HEADERS = {"User-Agent": "pokemon-champions-agent/0.1 (local personal use)"}


class MetaVGCScrapeError(RuntimeError):
    pass


@dataclass
class RegulationSnapshot:
    legal_pokemon: list[str]
    allowed_items: list[str]
    allowed_moves: list[str]
    published: Optional[str]


def _fetch_html(code: str, client: httpx.Client) -> str:
    slug = f"pokemon-champions-regulation-{code.lower()}-legal-pokemon-items-moves"
    url = f"https://metavgc.com/guides/{slug}"
    cache_file = CACHE_DIR / f"{slug}_{datetime.now(timezone.utc):%Y%m%d}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    resp = client.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


_TD_RE = re.compile(r"<td>(.*?)</td>")
_TAG_RE = re.compile(r"<[^>]+>")
_PUBLISHED_RE = re.compile(r"Published\S*\s*(?:<!--\s*-->\s*)*([A-Z][a-z]+ \d{1,2}, \d{4})")


def _extract_section(html: str, id_prefix: str) -> list[str]:
    heading_match = re.search(rf'id="{id_prefix}-\d+"', html)
    if not heading_match:
        raise MetaVGCScrapeError(f"No heading with id prefix '{id_prefix}-<count>' found -- page structure may have changed.")
    table_start = html.find("<table>", heading_match.end())
    table_end = html.find("</table>", table_start)
    if table_start == -1 or table_end == -1:
        raise MetaVGCScrapeError(f"Could not find a <table>...</table> following the '{id_prefix}' heading.")
    table_html = html[table_start:table_end]
    cells = [_TAG_RE.sub("", c).strip() for c in _TD_RE.findall(table_html)]
    values = [c for c in cells if c]
    if not values:
        raise MetaVGCScrapeError(f"'{id_prefix}' table had no non-empty <td> cells.")
    return values


def _unescape(text: str) -> str:
    return (
        text.replace("&#x27;", "'")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def fetch_regulation_snapshot(code: str, client: Optional[httpx.Client] = None) -> RegulationSnapshot:
    owns_client = client is None
    client = client or httpx.Client()
    try:
        html = _fetch_html(code, client)
        legal_pokemon = [_unescape(v) for v in _extract_section(html, "legal-pokemon")]
        allowed_items = [_unescape(v) for v in _extract_section(html, "allowed-items")]
        allowed_moves = [_unescape(v) for v in _extract_section(html, "allowed-moves")]
        published_match = _PUBLISHED_RE.search(html)
        return RegulationSnapshot(
            legal_pokemon=legal_pokemon,
            allowed_items=allowed_items,
            allowed_moves=allowed_moves,
            published=published_match.group(1) if published_match else None,
        )
    finally:
        if owns_client:
            client.close()
