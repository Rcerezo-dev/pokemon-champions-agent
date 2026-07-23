"""Pokémon-Zone scraper -- second, independent source for the current
regulation's roster, used to cross-check Bulbapedia's {{CPCard}} list.

The page is plain server-rendered HTML (no JS rendering needed), but
Cloudflare blocks httpx by TLS fingerprint even with a browser User-Agent
(confirmed: real Chrome UA + HTTP/2 still gets 403). curl's TLS handshake
passes, so this shells out to curl instead of pulling in a
fingerprint-spoofing dependency for one source.
# ponytail: curl subprocess as the Cloudflare workaround; switch to
# curl_cffi (or similar) if more sources need the same treatment.
"""

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

URL = "https://www.pokemon-zone.com/champions/pokemon/"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "pokemon_zone"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class PokemonZoneScrapeError(RuntimeError):
    pass


_SLUG_RE = re.compile(r'href="/champions/pokemon/([a-z0-9-]+)/"')


def _fetch_html() -> str:
    cache_file = CACHE_DIR / f"champions-pokemon_{datetime.now(timezone.utc):%Y%m%d}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    try:
        result = subprocess.run(
            ["curl", "-sL", "-A", USER_AGENT, URL],
            capture_output=True,
            timeout=30,
            check=True,
        )
    except FileNotFoundError as e:
        raise PokemonZoneScrapeError("curl not found on PATH -- required to fetch Pokémon-Zone (Cloudflare-blocked via httpx).") from e
    except subprocess.CalledProcessError as e:
        raise PokemonZoneScrapeError(f"curl failed fetching {URL}: {e.stderr!r}") from e
    html = result.stdout.decode("utf-8", errors="replace")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(html, encoding="utf-8")
    return html


def fetch_current_roster_slugs() -> set[str]:
    """Slugs (e.g. 'raichu-alolan-form') of every Pokémon shown on the roster
    page, which defaults to the current regulation's legal list."""
    html = _fetch_html()
    if '"Current"' not in html and ">Current<" not in html:
        raise PokemonZoneScrapeError(
            "Page no longer marks a regulation as 'Current' -- can't confirm this listing "
            "is the active regulation's roster."
        )
    slugs = set(_SLUG_RE.findall(html))
    if not slugs:
        raise PokemonZoneScrapeError("No 'data-pokemon-name' cards found -- page structure may have changed.")
    return slugs
