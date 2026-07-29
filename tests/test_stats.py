"""Fase 11 is the other CLAUDE.md-mandatory-tests phase (damage engine).
Champions' SP formula (see src/damage_calc/stats.py) is verified against two
independent sources, cross-checked in PROGRESS.md -- these are exact,
hand-computed values, not fixture guesses.
"""

from src.damage_calc.stats import compute_stat, compute_stats
from src.db.models import Nature

JOLLY = Nature(id=1, name="jolly", boosted_stat="speed", lowered_stat="special-attack")


def test_hp_formula_is_base_plus_75_plus_sp():
    assert compute_stat(108, 0, "hp", None) == 183  # Garchomp, 0 SP
    assert compute_stat(108, 32, "hp", None) == 215
    assert compute_stat(1, 0, "hp", None) == 76


def test_hp_ignores_nature():
    assert compute_stat(108, 0, "hp", JOLLY) == 183


def test_other_stat_formula_neutral_nature():
    # (base + 20 + sp) with no nature -> Garchomp attack, 0 SP
    assert compute_stat(130, 0, "attack", None) == 150
    assert compute_stat(130, 32, "attack", None) == 182


def test_other_stat_formula_boosted_and_lowered_nature():
    # Jolly: +speed, -special-attack. (102+20)*1.1=134.2 -> 134; (80+20)*0.9=90.0 -> 90
    assert compute_stat(102, 0, "speed", JOLLY) == 134
    assert compute_stat(80, 0, "special-attack", JOLLY) == 90
    # unaffected stat gets no multiplier
    assert compute_stat(95, 0, "defense", JOLLY) == 115


def test_other_stat_flooring():
    # (base + 20 + sp) * 1.1 with a fractional result must floor, not round
    # base=99, sp=0, speed is Jolly's boosted stat -> (119)*1.1 = 130.9 -> floors to 130
    assert compute_stat(99, 0, "speed", JOLLY) == 130


def test_compute_stats_covers_all_six_and_defaults_missing_sp_to_zero():
    base = {"hp": 108, "attack": 130, "defense": 95, "special-attack": 80, "special-defense": 85, "speed": 102}
    stats = compute_stats(base, {"attack": 32}, None)
    assert stats == {"hp": 183, "attack": 182, "defense": 115, "special-attack": 100, "special-defense": 105, "speed": 122}
