"""Victory Road scraper -- used only to cross-check the regulation code, dates
and mega-evolution flag that Bulbapedia already gave us. Victory Road's roster
listing is a gallery of images (no extractable text), so it can't corroborate
individual Pokémon legality -- only Pokémon-Zone does that (see pokemon_zone.py).
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

URL = "https://victoryroad.pro/champions-regulations/"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "victory_road"
HEADERS = {"User-Agent": "pokemon-champions-agent/0.1 (local personal use)"}


class VictoryRoadScrapeError(RuntimeError):
    pass


@dataclass
class VictoryRoadRegulationSummary:
    code: str
    start_day: int
    start_month: str
    end_day: int
    end_month: str
    end_year: int
    mega_allowed: bool


_SENTENCE_RE = re.compile(
    r"Regulation Set (?P<code>[\w-]+) is the official format of in-game Ranked Battles "
    r"from (?P<sday>\d{1,2}) (?P<smonth>\w+) to (?P<eday>\d{1,2}) (?P<emonth>\w+) (?P<eyear>\d{4})"
)
_MEGA_RE = re.compile(r"Mega Evolutions? (are|is) allowed", re.IGNORECASE)


def _fetch_html(client: httpx.Client) -> str:
    cache_file = CACHE_DIR / f"champions-regulations_{datetime.now(timezone.utc):%Y%m%d}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    resp = client.get(URL, headers=HEADERS, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


def fetch_regulation_summaries(client: Optional[httpx.Client] = None) -> list[VictoryRoadRegulationSummary]:
    owns_client = client is None
    client = client or httpx.Client()
    try:
        html = _fetch_html(client)
        flat = re.sub(r"<[^>]+>", " ", html.replace("\n", " "))
        flat = re.sub(r"\s+", " ", flat)

        summaries = []
        for m in _SENTENCE_RE.finditer(flat):
            mega_match = _MEGA_RE.search(flat[max(0, m.start() - 300) : m.end() + 300])
            summaries.append(
                VictoryRoadRegulationSummary(
                    code=m.group("code"),
                    start_day=int(m.group("sday")),
                    start_month=m.group("smonth"),
                    end_day=int(m.group("eday")),
                    end_month=m.group("emonth"),
                    end_year=int(m.group("eyear")),
                    mega_allowed=bool(mega_match),
                )
            )
        if not summaries:
            raise VictoryRoadScrapeError(
                "Could not find any 'Regulation Set X is the official format...' sentence -- page wording may have changed."
            )
        return summaries
    finally:
        if owns_client:
            client.close()
