"""Fase 10: standalone smoke check for every scraper source.

Calls each scraper's live-fetch function and reports OK/FAILED per source,
without touching the database. Meant to catch a broken selector (a website
changed its HTML/wikitext structure) as early and cheaply as possible --
lighter and faster than the full src/db/run_pipeline.py, which additionally
resolves species/writes to the DB and only reports failure at the level of
its 3 orchestrator steps (regulation/movepool/usage), not per individual
source within them.

Usage: python -m src.db.smoke_test_scrapers
"""

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.scrapers import (
    bulbapedia,
    championsmeta,
    metavgc,
    pikalytics,
    pokemon_zone,
    serebii_champions,
    victory_road,
)

LOG_DIR = Path("data/logs")


def _check_bulbapedia() -> str:
    with httpx.Client() as client:
        detail = bulbapedia.fetch_active_regulation(client)
    return f"{detail.code}: {len(detail.entries)} roster entries"


def _check_victory_road() -> str:
    summaries = victory_road.fetch_regulation_summaries()
    return f"{len(summaries)} regulation summaries"


def _check_pokemon_zone() -> str:
    slugs = pokemon_zone.fetch_current_roster_slugs()
    return f"{len(slugs)} roster slugs"


def _check_metavgc() -> str:
    with httpx.Client() as client:
        detail = bulbapedia.fetch_active_regulation(client)
        snapshot = metavgc.fetch_regulation_snapshot(detail.code, client)
    return (
        f"{len(snapshot.legal_pokemon)} legal pokemon, "
        f"{len(snapshot.allowed_items)} items, {len(snapshot.allowed_moves)} moves"
    )


def _check_serebii_moves() -> str:
    return f"{len(serebii_champions.fetch_moves_catalog())} moves"


def _check_serebii_items() -> str:
    return f"{len(serebii_champions.fetch_items_catalog())} items"


def _check_serebii_movepool() -> str:
    return f"{len(serebii_champions.fetch_species_movepool('charizard'))} moves (charizard)"


def _check_championsmeta_usage() -> str:
    with httpx.Client() as client:
        detail = bulbapedia.fetch_active_regulation(client)
        entries = championsmeta.fetch_usage_rankings(detail.code, client)
    return f"{len(entries)} usage entries"


def _check_championsmeta_tournaments() -> str:
    return f"{len(championsmeta.fetch_recent_tournaments())} tournaments"


def _check_pikalytics() -> str:
    return f"{len(pikalytics.fetch_top20_names())} top-20 names"


CHECKS = [
    ("bulbapedia", _check_bulbapedia),
    ("victory_road", _check_victory_road),
    ("pokemon_zone", _check_pokemon_zone),
    ("metavgc", _check_metavgc),
    ("serebii moves catalog", _check_serebii_moves),
    ("serebii items catalog", _check_serebii_items),
    ("serebii species movepool", _check_serebii_movepool),
    ("championsmeta usage", _check_championsmeta_usage),
    ("championsmeta tournaments", _check_championsmeta_tournaments),
    ("pikalytics", _check_pikalytics),
]


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    log_path = LOG_DIR / f"smoke_{started.strftime('%Y-%m-%dT%H-%M-%S')}.log"

    lines = [f"Smoke test run started at {started.isoformat()}"]
    failed = False
    for name, fn in CHECKS:
        try:
            detail = fn()
            lines.append(f"OK      {name}: {detail}")
        except Exception:
            failed = True
            lines.append(f"FAILED  {name}\n{traceback.format_exc()}")

    log_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nLog written to {log_path}")
    if failed:
        print("One or more sources FAILED -- a selector likely broke, see log above.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
