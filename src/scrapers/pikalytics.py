"""Pikalytics scraper -- used only as a second, independent source to
cross-check ChampionsMeta's top usage ranking. Its full per-Pokémon %
breakdown lives behind client-side rendering we didn't chase down, but the
homepage's "Top 20 Pokemon" section (rank + name, no %) is plain
server-rendered HTML and is enough to spot-check ChampionsMeta's top
entries. robots.txt is fully permissive, no Crawl-delay.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

URL = "https://www.pikalytics.com/"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "pikalytics"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


class PikalyticsScrapeError(RuntimeError):
    pass


def _fetch_html(client: httpx.Client) -> str:
    cache_file = CACHE_DIR / f"home_{datetime.now(timezone.utc):%Y%m%d}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    resp = client.get(URL, headers=HEADERS, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


_TOP20_RE = re.compile(r'class="tournament-top20-card[^"]*"[^>]*data-name="([^"]+)"')


def fetch_top20_names(client: Optional[httpx.Client] = None) -> list[str]:
    """Pokémon names in the current format's "Top 20 Pokemon" section, in
    rank order (no usage % -- see module docstring)."""
    owns_client = client is None
    client = client or httpx.Client()
    try:
        html = _fetch_html(client)
        names = _TOP20_RE.findall(html)
        if not names:
            raise PikalyticsScrapeError("No 'tournament-top20-card' entries found -- page structure may have changed.")
        return names
    finally:
        if owns_client:
            client.close()
