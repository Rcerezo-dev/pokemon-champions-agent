"""Offline, deterministic tests for the Fase 12 document builder -- no DB,
no network. Confirms the deliberate omissions (no invented "role" label, no
common_sets) and that real data (abilities, movepool, usage) renders."""

from datetime import datetime, timezone

from src.db.models import Move, PokemonSpecies, UsageStat
from src.semantic.documents import AbilityRef, SpeciesDocInput, build_document

SPECIES = PokemonSpecies(id=6, name="charizard", types="fire,flying", base_stats_json="{}", is_default=True)
STATS = {"hp": 78, "attack": 84, "defense": 78, "special-attack": 109, "special-defense": 85, "speed": 100}


def test_includes_name_types_and_stats():
    doc = build_document(SpeciesDocInput(species=SPECIES, base_stats=STATS, abilities=[], legal_moves=[], usage=None))
    assert "Charizard (Fire / Flying)" in doc
    assert "Special Attack 109" in doc


def test_includes_abilities_with_effect_and_hidden_tag():
    abilities = [
        AbilityRef(name="blaze", effect_text="Powers up Fire-type moves when HP is low.", is_hidden=False),
        AbilityRef(name="solar-power", effect_text="Boosts Sp. Atk in sun but loses HP.", is_hidden=True),
    ]
    doc = build_document(SpeciesDocInput(species=SPECIES, base_stats=STATS, abilities=abilities, legal_moves=[], usage=None))
    assert "Blaze: Powers up Fire-type moves when HP is low." in doc
    assert "Solar-power (hidden ability): Boosts Sp. Atk in sun but loses HP." in doc


def test_includes_legal_moves_with_type_category_power():
    moves = [
        Move(id=1, name="flamethrower", type="fire", category="special", power=90, accuracy=100, pp=15, effect_text=""),
        Move(id=2, name="air-slash", type="flying", category="special", power=75, accuracy=95, pp=15, effect_text=""),
    ]
    doc = build_document(SpeciesDocInput(species=SPECIES, base_stats=STATS, abilities=[], legal_moves=moves, usage=None))
    assert "Legal moves this regulation (2):" in doc
    assert "Flamethrower (fire, special, 90 power)" in doc


def test_status_move_omits_power():
    moves = [Move(id=3, name="swords-dance", type="normal", category="status", power=None, accuracy=None, pp=20, effect_text="")]
    doc = build_document(SpeciesDocInput(species=SPECIES, base_stats=STATS, abilities=[], legal_moves=moves, usage=None))
    assert "Swords-dance (normal, status)" in doc
    assert "power)" not in doc


def test_no_legal_moves_says_so_explicitly():
    doc = build_document(SpeciesDocInput(species=SPECIES, base_stats=STATS, abilities=[], legal_moves=[], usage=None))
    assert "No legal moves recorded for this regulation." in doc


def test_includes_usage_with_verified_flag():
    usage = UsageStat(
        regulation_id="M-B", pokemon_species_id=6, usage_pct=12.34, source="x", retrieved_at=datetime.now(timezone.utc), verified=True
    )
    doc = build_document(SpeciesDocInput(species=SPECIES, base_stats=STATS, abilities=[], legal_moves=[], usage=usage))
    assert "Usage this regulation: 12.3% of teams (verified)." in doc


def test_never_invents_role_or_common_items():
    doc = build_document(SpeciesDocInput(species=SPECIES, base_stats=STATS, abilities=[], legal_moves=[], usage=None))
    for forbidden in ("sweeper", "wall", "tank", "role:", "common item"):
        assert forbidden not in doc.lower()
