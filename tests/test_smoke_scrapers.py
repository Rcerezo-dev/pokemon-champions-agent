"""Fase 10: live smoke tests for every scraper source.

Unlike tests/test_*_scrapers.py (which parse fixed, embedded HTML/wikitext
offline), these hit the real websites and only check that each scraper's
selectors still find *something* structurally plausible -- they don't
re-verify the parsed values. Each scraper already raises its own
`*ScrapeError` when a selector comes up empty (see src/scrapers/), so a
failure here means that exception fired against today's live page, i.e. the
site's structure likely changed.

Excluded from the default `pytest` run (see pyproject.toml's `addopts`)
because they need network and hit real third-party sites -- run explicitly:

    pytest -m live -v

Same purpose as src/db/smoke_test_scrapers.py, which runs the same checks as
a standalone script with a log file, meant for periodic/scheduled runs.
"""

import httpx
import pytest

from src.scrapers import (
    bulbapedia,
    championsmeta,
    metavgc,
    pikalytics,
    pokemon_zone,
    serebii_champions,
    victory_road,
)

pytestmark = pytest.mark.live


def test_bulbapedia_active_regulation():
    with httpx.Client() as client:
        detail = bulbapedia.fetch_active_regulation(client)
    assert detail.entries
    assert detail.start < detail.end


def test_victory_road_regulation_summaries():
    summaries = victory_road.fetch_regulation_summaries()
    assert summaries


def test_pokemon_zone_roster_slugs():
    slugs = pokemon_zone.fetch_current_roster_slugs()
    assert slugs


def test_metavgc_regulation_snapshot():
    with httpx.Client() as client:
        codes = bulbapedia.list_regulation_codes(client)
        detail = bulbapedia.fetch_active_regulation(client)
        snapshot = metavgc.fetch_regulation_snapshot(detail.code, client)
    assert codes
    assert snapshot.legal_pokemon
    assert snapshot.allowed_items
    assert snapshot.allowed_moves


def test_serebii_moves_catalog():
    names = serebii_champions.fetch_moves_catalog()
    assert names


def test_serebii_items_catalog():
    names = serebii_champions.fetch_items_catalog()
    assert names


def test_serebii_species_movepool():
    names = serebii_champions.fetch_species_movepool("charizard")
    assert names


def test_championsmeta_usage_rankings():
    with httpx.Client() as client:
        detail = bulbapedia.fetch_active_regulation(client)
        entries = championsmeta.fetch_usage_rankings(detail.code, client)
    assert entries


def test_championsmeta_recent_tournaments():
    tournaments = championsmeta.fetch_recent_tournaments()
    assert tournaments


def test_pikalytics_top20_names():
    names = pikalytics.fetch_top20_names()
    assert names
