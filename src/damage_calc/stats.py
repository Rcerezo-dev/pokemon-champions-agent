"""Fase 11: Pokémon Champions' final-stat formula.

Champions fixes level at 50 and IVs at 31 for every Pokémon, and replaces
EVs with Stat Points (SP, 66 total / 32 per stat) that add directly to the
stat instead of going through the classic EV/4 conversion. Verified against
two independent sources that state the formula in different (but
algebraically equivalent) forms -- see PROGRESS.md Fase 11 for the citations
and the reduction showing they agree:
  - HP           = base + 75 + sp
  - other stats  = floor((base + 20 + sp) * nature_multiplier)
nature_multiplier is 1.1 for the boosted stat, 0.9 for the lowered stat
(same Nature rows already seeded in Fase 1), 1.0 otherwise.
"""

from typing import Optional

from src.db.models import Nature

STAT_NAMES = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]


def _nature_multiplier(stat_name: str, nature: Optional[Nature]) -> tuple[int, int]:
    """Returns (numerator, denominator) instead of a float -- avoids any risk
    of float64 multiplication landing a hair under an integer boundary and
    flooring one point too low (empirically doesn't happen in the realistic
    stat range, but this is exact by construction instead of by observation,
    which matters more for one of CLAUDE.md's two mandatory-test phases)."""
    if nature is None or stat_name == "hp":
        return 1, 1
    if nature.boosted_stat == stat_name:
        return 11, 10
    if nature.lowered_stat == stat_name:
        return 9, 10
    return 1, 1


def compute_stat(base: int, sp: int, stat_name: str, nature: Optional[Nature]) -> int:
    if stat_name == "hp":
        return base + 75 + sp
    num, den = _nature_multiplier(stat_name, nature)
    return ((base + 20 + sp) * num) // den


def compute_stats(base_stats: dict[str, int], sp_spread: dict[str, int], nature: Optional[Nature]) -> dict[str, int]:
    """base_stats/sp_spread use the project's PokeAPI-style stat names (see
    STAT_NAMES) -- callers unfamiliar with a stat simply omit it (0 SP)."""
    return {stat: compute_stat(base_stats.get(stat, 0), sp_spread.get(stat, 0), stat, nature) for stat in STAT_NAMES}
