"""Fase 11 is one of the two CLAUDE.md-mandatory-tests phases. Runs the real
@smogon/calc engine via the Node bridge (no mocking -- that's the whole
point of adapting the actual library instead of reimplementing the damage
formula) against an in-memory fixture DB, same pattern as
tests/test_team_validator.py.

The expected damage numbers below are pinned from one canonical run of this
exact code (not hand-derived from the Bulbapedia damage formula -- doing
that independently is exactly the "easy to get subtly wrong" trap CLAUDE.md
warns about for this phase). Confidence instead comes from a hand-derived,
independently-checked case using round stat numbers (test_regression_case_
matches_hand_derived_formula below) that exercises the same override
mechanism end to end -- see PROGRESS.md Fase 11 for why this was necessary
(the first override approach silently discarded SP/nature and passed, then
failed this exact regression check, which is how the bug was caught).
"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from src.damage_calc.calculator import DamageBuild, DamageCalcError, FieldConditions, calculate_damage
from src.db.models import Nature, PokemonSpecies

NOW = datetime.now(timezone.utc)


def _stats(hp, atk, df, spa, spd, spe):
    return json.dumps({"hp": hp, "attack": atk, "defense": df, "special-attack": spa, "special-defense": spd, "speed": spe})


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(PokemonSpecies(id=445, name="garchomp", types="dragon,ground", base_stats_json=_stats(108, 130, 95, 80, 85, 102)))
        s.add(PokemonSpecies(id=727, name="incineroar", types="fire,dark", base_stats_json=_stats(95, 115, 90, 80, 90, 60)))
        # Real species names (@smogon/calc validates species names against
        # its own data, so the name has to resolve there) but with
        # deliberately round, made-up base stats in our DB -- isolates the
        # override mechanism from any real Pokémon's numbers. Machamp
        # (Fighting) using Tackle (Normal) has no STAB, which keeps the
        # hand-derived formula in the test below simple.
        s.add(PokemonSpecies(id=68, name="Machamp", types="fighting", base_stats_json=_stats(180, 180, 80, 80, 80, 80)))
        s.add(PokemonSpecies(id=143, name="Snorlax", types="normal", base_stats_json=_stats(180, 80, 80, 80, 80, 80)))
        s.add(Nature(id=1, name="jolly", boosted_stat="speed", lowered_stat="special-attack"))
        s.commit()
        yield s


def test_regression_case_matches_hand_derived_formula(session):
    """Fighting-type attacker, Normal-type move (no STAB) -> isolates the raw
    damage formula. 0 SP, neutral nature: atk=180+20=200, def=80+20=100.
    getBaseDamage(50, bp=40, atk=200, def=100) = floor((2*50/5+2)*40*200/100/50+2) = 37.
    16-step roll (0.85..1.00): floor(37*0.85)=31 .. floor(37*1.00)=37.
    Hand-verified independently of any calculator.py output -- this is the
    check that caught the original bug (rawStats set after construction was
    silently discarded by @smogon/calc's internal clone() on every
    calculate() call, so SP/nature had zero effect until fixed to use
    `overrides.baseStats`, the only channel that survives the clone)."""
    attacker = DamageBuild(species="Machamp")
    defender = DamageBuild(species="Snorlax")
    result = calculate_damage(session, attacker, defender, "Tackle")
    assert (result.damage_min, result.damage_max) == (31, 37)
    assert result.defender_max_hp == 255  # base HP 180 + 75 + 0 SP, per stats.py's formula


def test_sp_and_nature_change_the_result(session):
    """Same matchup, but the attacker now spends SP and has a nature that
    should measurably increase damage -- guards against a regression back to
    the bug above, where SP/nature were silently ignored."""
    baseline = calculate_damage(session, DamageBuild(species="Machamp"), DamageBuild(species="Snorlax"), "Tackle")
    boosted = calculate_damage(
        session,
        DamageBuild(species="Machamp", sp_spread={"attack": 32}),
        DamageBuild(species="Snorlax"),
        "Tackle",
    )
    assert boosted.damage_min > baseline.damage_min
    assert boosted.damage_max > baseline.damage_max


def test_garchomp_vs_incineroar_earthquake_singles(session):
    result = calculate_damage(session, DamageBuild(species="garchomp"), DamageBuild(species="incineroar"), "Earthquake")
    assert (result.damage_min, result.damage_max) == (156, 186)
    assert result.defender_max_hp == 170
    assert result.ko_chance == pytest.approx(0.5625)


def test_choice_band_sp_and_nature_stack(session):
    attacker = DamageBuild(species="garchomp", item="Choice Band", nature="jolly", sp_spread={"attack": 32, "speed": 32})
    result = calculate_damage(session, attacker, DamageBuild(species="incineroar"), "Earthquake")
    assert (result.damage_min, result.damage_max) == (282, 332)
    assert result.ko_chance == 1
    assert "Attacker item: Choice Band" in result.modifiers
    assert "Attacker nature: jolly" in result.modifiers
    assert "Attacker SP: 32 SP attack, 32 SP speed" in result.modifiers


def test_doubles_reflect_reduces_damage(session):
    attacker = DamageBuild(species="garchomp", item="Choice Band", nature="jolly", sp_spread={"attack": 32, "speed": 32})
    field = FieldConditions(game_type="doubles", defender_side={"isReflect": True})
    result = calculate_damage(session, attacker, DamageBuild(species="incineroar"), "Earthquake", field)
    assert (result.damage_min, result.damage_max) == (140, 165)
    assert "Reflect is active on the defending side" in result.modifiers


def test_unknown_species_fails_visibly(session):
    with pytest.raises(DamageCalcError, match="not a known Pokémon"):
        calculate_damage(session, DamageBuild(species="not-a-pokemon"), DamageBuild(species="incineroar"), "Tackle")


def test_champions_exclusive_mega_stone_fails_visibly_instead_of_silently_ignoring_it(session):
    """@smogon/calc silently accepts unknown item names with no effect --
    calc.js validates against the library's own item table so this raises
    instead of quietly computing a wrong (non-Mega) number. Sceptileite is
    one of the 7 Champions-exclusive Mega Stones found in Fase 3 that don't
    exist in mainline games (see PROGRESS.md)."""
    attacker = DamageBuild(species="garchomp", item="Sceptileite")
    with pytest.raises(DamageCalcError, match="Unknown item 'Sceptileite'"):
        calculate_damage(session, attacker, DamageBuild(species="incineroar"), "Earthquake")


def test_unknown_move_fails_visibly(session):
    with pytest.raises(DamageCalcError, match="Unknown move"):
        calculate_damage(session, DamageBuild(species="garchomp"), DamageBuild(species="incineroar"), "Not A Move")


def test_unknown_boost_stat_name_fails_visibly(session):
    attacker = DamageBuild(species="garchomp", boosts={"hp": 1})
    with pytest.raises(DamageCalcError, match="Unknown stat name"):
        calculate_damage(session, attacker, DamageBuild(species="incineroar"), "Earthquake")
