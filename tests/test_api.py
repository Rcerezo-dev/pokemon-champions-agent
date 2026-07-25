"""Smoke tests against the real local DB (already seeded by Fases 1-4) --
this project has exactly one environment (one SQLite file), so a separate
test fixture DB would be pure overhead. Assertions are loose (shapes and
"at least one plausible row"), not exact counts, so they don't break every
time a scraper re-run shifts a live number.
"""

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_active_regulation():
    r = client.get("/regulation/active")
    assert r.status_code == 200
    body = r.json()
    assert body["id"]
    assert body["start_date"] < body["end_date"]


def test_legal_pokemon_contains_charizard():
    r = client.get("/pokemon/legal")
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 100
    names = {p["name"] for p in body}
    assert "charizard" in names
    assert all(isinstance(p["types"], list) and p["types"] for p in body)


def test_pokemon_detail_charizard():
    r = client.get("/pokemon/6")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "charizard"
    assert set(body["types"]) == {"fire", "flying"}
    assert body["base_stats"]["hp"] > 0
    assert body["legal_in_regulation"] is True


def test_pokemon_detail_404():
    r = client.get("/pokemon/999999")
    assert r.status_code == 404


def test_legal_moves_charizard_includes_flamethrower():
    r = client.get("/pokemon/6/legal-moves")
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 10
    names = {m["name"] for m in body}
    assert "flamethrower" in names


def test_legal_moves_404_for_unknown_species():
    r = client.get("/pokemon/999999/legal-moves")
    assert r.status_code == 404


def test_top_usage_ordered_descending():
    r = client.get("/meta/top-usage?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 10
    pcts = [row["usage_pct"] for row in body]
    assert pcts == sorted(pcts, reverse=True)


def test_top_usage_respects_limit():
    r = client.get("/meta/top-usage?limit=3")
    assert len(r.json()) == 3


def test_unknown_regulation_id_404s():
    r = client.get("/pokemon/legal?regulation_id=Z-NOPE")
    assert r.status_code == 404
