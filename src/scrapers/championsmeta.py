"""ChampionsMeta scraper -- real-tournament usage stats and notable teams for
Pokémon Champions. Both pages are server-rendered (Next.js SSR, confirmed by
fetching raw HTML directly, same as metavgc.py) and explicitly cite Limitless
TCG as their underlying data source ("Data sourced from Limitless TCG").
robots.txt is fully permissive, no Crawl-delay.

Two pages:
  - /meta: a single "Usage Rankings" table for the current regulation,
    followed by a "Regulation M-A Usage History" section we must not read
    past (older data, would corrupt the current snapshot).
  - /tournaments: many tournament cards, each already tagged "Reg M-B" or
    "Reg M-A" inline, with per-card top-placement rows (player, record,
    team) and a link to the original Limitless standings page.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "championsmeta"
HEADERS = {"User-Agent": "pokemon-champions-agent/0.1 (local personal use)"}


class ChampionsMetaScrapeError(RuntimeError):
    pass


@dataclass
class UsageEntry:
    rank: int
    slug: str
    name: str
    usage_pct: float


@dataclass
class TeamEntry:
    placement: int
    player_name: str
    record: str
    pokemon_slugs: list[str]


@dataclass
class TournamentEntry:
    name: str
    organizer: str
    date_text: str
    player_count: int
    source_url: str
    teams: list[TeamEntry]


def _fetch_html(cache_name: str, url: str, client: httpx.Client) -> str:
    cache_file = CACHE_DIR / f"{cache_name}_{datetime.now(timezone.utc):%Y%m%d}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    resp = client.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


_USAGE_ROW_RE = re.compile(
    r'href="/pokemon/([a-z0-9-]+)"><img alt="([^"]+)"[\s\S]*?text-accent-blue block">([\d.]+)<!-- -->%</span>'
)


def fetch_usage_rankings(regulation_id: str, client: Optional[httpx.Client] = None) -> list[UsageEntry]:
    owns_client = client is None
    client = client or httpx.Client()
    try:
        html = _fetch_html("meta", "https://championsmeta.io/meta", client)
        if f">Regulation {regulation_id}</span>" not in html:
            raise ChampionsMetaScrapeError(
                f"Page's current-regulation badge doesn't say 'Regulation {regulation_id}' -- "
                "site may have moved to a new regulation this scraper doesn't know about."
            )
        cutoff = html.find("Usage History")
        current_section = html if cutoff == -1 else html[:cutoff]
        matches = list(_USAGE_ROW_RE.finditer(current_section))
        if not matches:
            raise ChampionsMetaScrapeError("No usage ranking rows found on /meta -- page structure may have changed.")
        return [
            UsageEntry(rank=i, slug=m.group(1), name=m.group(2), usage_pct=float(m.group(3)))
            for i, m in enumerate(matches, start=1)
        ]
    finally:
        if owns_client:
            client.close()


_BLOCK_SPLIT = '<div class="rounded-2xl border border-bg-border bg-bg-card overflow-hidden">'
_TOURNEY_HEADER_RE = re.compile(
    r'<h2 class="text-lg font-bold text-text-primary">(.*?)</h2>.*?Reg (M-[AB])</span>', re.S
)
_TOURNEY_META_RE = re.compile(r"<span>([^<]+)</span><span>([^<]+)</span><span>(\d+)\s*players</span>")
_SOURCE_URL_RE = re.compile(r'href="(https://play\.limitlesstcg\.com/tournament/[^"]+)"')
_PLAYER_ROW_RE = re.compile(
    r'class="[^"]*font-bold shrink-0[^"]*">(\d+)</span>.*?'
    r'<p class="text-sm font-semibold text-text-primary truncate">([^<]+)</p>.*?'
    r'font-mono text-text-muted w-12 shrink-0">([\d-]+)</span>'
    r'(?P<team>.*?)(?=class="[^"]*font-bold shrink-0|\Z)',
    re.S,
)
_ALT_RE = re.compile(r'alt="([a-z0-9-]+)"')


def _parse_tournament_block(block: str) -> Optional[TournamentEntry]:
    block = block.replace("<!-- -->", "")
    header_match = _TOURNEY_HEADER_RE.search(block)
    if not header_match:
        return None
    if header_match.group(2) != "M-B":  # only the currently-active regulation's tournaments
        return None
    meta_match = _TOURNEY_META_RE.search(block)
    url_match = _SOURCE_URL_RE.search(block)
    if not meta_match or not url_match:
        raise ChampionsMetaScrapeError(
            f"Tournament '{header_match.group(1)}' is missing organizer/date/player-count or a Limitless source URL."
        )
    teams = []
    for m in _PLAYER_ROW_RE.finditer(block):
        slugs = _ALT_RE.findall(m.group("team"))
        teams.append(TeamEntry(placement=int(m.group(1)), player_name=m.group(2), record=m.group(3), pokemon_slugs=slugs))
    return TournamentEntry(
        name=header_match.group(1),
        organizer=meta_match.group(1),
        date_text=meta_match.group(2),
        player_count=int(meta_match.group(3)),
        source_url=url_match.group(1),
        teams=teams,
    )


def fetch_recent_tournaments(client: Optional[httpx.Client] = None) -> list[TournamentEntry]:
    """Recent tournaments tagged for the active regulation (M-B), each with
    its top-placing teams. Older (M-A) tournament cards on the same page are
    skipped."""
    owns_client = client is None
    client = client or httpx.Client()
    try:
        html = _fetch_html("tournaments", "https://championsmeta.io/tournaments", client)
        blocks = html.split(_BLOCK_SPLIT)[1:]
        if not blocks:
            raise ChampionsMetaScrapeError("No tournament cards found on /tournaments -- page structure may have changed.")
        entries = [e for b in blocks if (e := _parse_tournament_block(b)) is not None]
        return entries
    finally:
        if owns_client:
            client.close()
