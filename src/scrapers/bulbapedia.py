"""Bulbapedia scraper for the active Pokémon Champions Regulation Set.

Uses raw wikitext (MediaWiki `action=raw`) instead of parsing rendered HTML --
Bulbapedia's Regulation Set pages use a consistent, structured wiki-markup
({{RegulationSetInfobox}}, {{CPCard|dex|name|...}}) that is far more stable
to parse than the rendered page. robots.txt allows /wiki/ with Crawl-delay: 5.
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

BASE = "https://bulbapedia.bulbagarden.net/w/index.php"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "bulbapedia"
HEADERS = {"User-Agent": "pokemon-champions-agent/0.1 (local personal use)"}
CRAWL_DELAY_SECONDS = 5


class BulbapediaScrapeError(RuntimeError):
    """Raised when the expected wiki-markup structure isn't found -- fail
    visibly instead of silently returning partial/wrong data."""


@dataclass
class CPCardEntry:
    dex_number: int
    base_name: str
    ig_suffix: Optional[str]  # e.g. "-Alola", "-Mega X" (raw ig= value, no leading dash stripped)
    form_label: Optional[str]  # human label pulled from name=...<small>(...)</small>, if present


@dataclass
class RegulationDetail:
    code: str
    start: datetime
    end: datetime
    mega_allowed: bool
    ruleset_text: str
    entries: list[CPCardEntry]


def _fetch_raw_wikitext(title: str, client: httpx.Client) -> str:
    cache_file = CACHE_DIR / f"{title.replace('/', '_')}_{datetime.now(timezone.utc):%Y%m%d}.wikitext"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    resp = client.get(BASE, params={"title": title, "action": "raw"}, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()
    time.sleep(CRAWL_DELAY_SECONDS)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


def list_regulation_codes(client: httpx.Client) -> list[str]:
    """Regulation codes in the order they appear on the index page (chronological)."""
    wikitext = _fetch_raw_wikitext("Regulation_Sets_in_Pokémon_Champions", client)
    codes = re.findall(r"\[\[Regulation Set ([^\]|]+)\]\]", wikitext)
    seen: list[str] = []
    for code in codes:
        if code not in seen:
            seen.append(code)
    if not seen:
        raise BulbapediaScrapeError(
            "No '[[Regulation Set X]]' links found on the index page -- page structure may have changed."
        )
    return seen


_CPCARD_RE = re.compile(
    r"\{\{CPCard\|(?P<dex>\d+)\|(?P<name>[^|}]+)(?P<rest>[^}]*)\}\}"
)
_IG_RE = re.compile(r"\|ig=([^|}]+)")
_NAME_OVERRIDE_SMALL_RE = re.compile(r"<small>\(([^)]+)\)</small>")


def parse_cpcard_entries(wikitext: str) -> list[CPCardEntry]:
    entries = []
    for m in _CPCARD_RE.finditer(wikitext):
        ig_match = _IG_RE.search(m.group("rest"))
        ig_suffix = ig_match.group(1).strip() if ig_match else None
        label_match = _NAME_OVERRIDE_SMALL_RE.search(m.group("rest"))
        form_label = label_match.group(1).strip() if label_match else None
        entries.append(
            CPCardEntry(
                dex_number=int(m.group("dex")),
                base_name=m.group("name").strip(),
                ig_suffix=ig_suffix,
                form_label=form_label,
            )
        )
    return entries


def _strip_wiki_markup(text: str) -> str:
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)  # [[X|Y]] / [[X]] -> Y / X
    text = re.sub(r"''+", "", text)  # ''italic''/'''bold'''
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_INFOBOX_FIELD_RE = re.compile(r"\|\s*(\w+)\s*=\s*(.+)")


def _parse_infobox(wikitext: str) -> dict[str, str]:
    box_match = re.search(r"\{\{RegulationSetInfobox(.*?)\n\}\}", wikitext, re.DOTALL)
    if not box_match:
        raise BulbapediaScrapeError("Could not find {{RegulationSetInfobox}} block.")
    fields: dict[str, str] = {}
    for line in box_match.group(1).splitlines():
        m = _INFOBOX_FIELD_RE.match(line.strip())
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def fetch_regulation_detail(code: str, client: httpx.Client) -> RegulationDetail:
    title = f"Regulation_Set_{code}"
    wikitext = _fetch_raw_wikitext(title, client)

    fields = _parse_infobox(wikitext)
    for required in ("sdate", "stime", "edate", "etime"):
        if required not in fields:
            raise BulbapediaScrapeError(f"Infobox for {code} is missing '{required}'.")
    start = datetime.strptime(f"{fields['sdate']} {fields['stime']}", "%B %d, %Y %H:%M").replace(
        tzinfo=timezone.utc
    )
    end = datetime.strptime(f"{fields['edate']} {fields['etime']}", "%B %d, %Y %H:%M").replace(
        tzinfo=timezone.utc
    )

    ruleset_match = re.search(r"==Ruleset==\s*(.*?)\n==", wikitext, re.DOTALL)
    if not ruleset_match:
        raise BulbapediaScrapeError(f"Could not find '==Ruleset==' section for {code}.")
    ruleset_text = _strip_wiki_markup(ruleset_match.group(1))
    mega_allowed = "mega evolution is enabled" in ruleset_text.lower()

    entries = parse_cpcard_entries(wikitext)
    if not entries:
        raise BulbapediaScrapeError(f"No {{{{CPCard}}}} entries found for {code} -- roster section may have changed.")

    return RegulationDetail(
        code=code,
        start=start,
        end=end,
        mega_allowed=mega_allowed,
        ruleset_text=ruleset_text,
        entries=entries,
    )


def fetch_active_regulation(client: Optional[httpx.Client] = None) -> RegulationDetail:
    owns_client = client is None
    client = client or httpx.Client()
    try:
        now = datetime.now(timezone.utc)
        candidates = list_regulation_codes(client)
        # Check most-recently-listed codes first -- the active set is almost
        # always near the end of the chronological list.
        checked = []
        for code in reversed(candidates):
            detail = fetch_regulation_detail(code, client)
            checked.append(code)
            if detail.start <= now < detail.end:
                return detail
        raise BulbapediaScrapeError(
            f"No regulation set among {checked} has start<=now<end (now={now.isoformat()}). "
            "The index page may not have been updated yet, or the schedule changed."
        )
    finally:
        if owns_client:
            client.close()
