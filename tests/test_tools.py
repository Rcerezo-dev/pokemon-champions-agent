"""Smoke tests for the Fase 7 tool dispatcher, against the real seeded DB --
same rationale as tests/test_api.py: one local environment, loose
assertions so a scraper re-run doesn't break these. Does not call the
Anthropic API (that's exercised manually via src/cli/chat.py, per
PROGRESS.md)."""

from src.api.tools import run_tool


def test_get_active_regulation():
    result = run_tool("get_active_regulation", {})
    assert result["id"]
    assert result["start_date"] < result["end_date"]


def test_get_legal_pokemon_contains_charizard():
    result = run_tool("get_legal_pokemon", {})
    names = {p["name"] for p in result["pokemon"]}
    assert "charizard" in names


def test_get_pokemon_detail_charizard():
    result = run_tool("get_pokemon_detail", {"pokemon_id": 6})
    assert result["name"] == "charizard"
    assert set(result["types"]) == {"fire", "flying"}


def test_get_pokemon_detail_unknown_species_returns_error():
    result = run_tool("get_pokemon_detail", {"pokemon_id": 999999})
    assert "error" in result


def test_get_legal_moves_charizard_includes_flamethrower():
    result = run_tool("get_legal_moves", {"pokemon_id": 6})
    names = {m["name"] for m in result["moves"]}
    assert "flamethrower" in names


def test_get_meta_usage_respects_limit():
    result = run_tool("get_meta_usage", {"limit": 3})
    assert len(result["usage"]) == 3


def test_validate_team_unknown_regulation_returns_error():
    result = run_tool(
        "validate_team",
        {"format": "singles", "regulation_id": "Z-NOPE", "members": []},
    )
    assert "error" in result


def test_unknown_tool_name_returns_error():
    result = run_tool("not_a_real_tool", {})
    assert "error" in result


def test_calculate_damage_charizard_flamethrower_vs_blastoise():
    result = run_tool(
        "calculate_damage",
        {
            "attacker": {"species": "charizard", "sp_spread": {"special-attack": 32}},
            "defender": {"species": "blastoise"},
            "move": "flamethrower",
        },
    )
    assert result["damage_min"] > 0
    assert result["damage_min"] <= result["damage_max"] <= result["defender_max_hp"] * 5  # sane upper bound


def test_calculate_damage_unknown_species_returns_error():
    result = run_tool(
        "calculate_damage",
        {"attacker": {"species": "not-a-real-pokemon"}, "defender": {"species": "blastoise"}, "move": "flamethrower"},
    )
    assert "error" in result
