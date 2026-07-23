"""Matches Bulbapedia's {{CPCard}} roster entries to our PokeAPI-backed
PokemonSpecies rows, and cross-checks each match against Pokémon-Zone's
roster slugs as the second independent source required before marking
something `verified`.

The three sources don't share a common ID or naming scheme, so this is a
best-effort alias/normalization matcher, not an exact join. When a form
can't be resolved or cross-checked, that is logged and stored as
verified=False with a note -- never guessed silently (CLAUDE.md: scrapers
must fail visibly, not save partial/corrupt data as if it were solid).
"""

import re
from dataclasses import dataclass
from typing import Optional

from src.scrapers.bulbapedia import CPCardEntry

# ig= value (lowercased) -> PokeAPI name suffix. Covers the regional/mega/
# cosmetic-form families seen in Regulation Set M-A/M-B. New regulations may
# introduce ig= values not listed here -- those fall back to a naive
# lowercase-and-dash guess (see resolve_species_id), which either matches or
# is reported as unresolved; it is never assumed correct silently.
IG_ALIAS: dict[str, str] = {
    "alola": "alola",
    "galar": "galar",
    "hisui": "hisui",
    "mega": "mega",
    "mega x": "mega-x",
    "mega y": "mega-y",
    "paldea aqua": "paldea-aqua-breed",
    "paldea blaze": "paldea-blaze-breed",
    "paldea combat": "paldea-combat-breed",
    "heat": "heat",
    "wash": "wash",
    "frost": "frost",
    "fan": "fan",
    "mow": "mow",
    "dusk": "dusk",
    "midnight": "midnight",
    "dawn": "dawn",
    "eternal": "eternal",
    "jumbo": "super",  # Bulbapedia "Jumbo Variety" == PokeAPI "-super"
    "small": "small",
    "large": "large",
    "female": "female",
}

# PZ slug tokens that are filler or synonyms of a Bulbapedia ig= token.
_PZ_TOKEN_SYNONYMS = {
    "alolan": "alola",
    "galarian": "galar",
    "hisuian": "hisui",
    "paldean": "paldea",
    "form": "",
    "forme": "",
    "variety": "",
    "flower": "",
    "the": "",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass
class MatchResult:
    species_id: Optional[int]
    resolve_note: str
    verified: bool
    verify_note: str


def resolve_species_id(
    entry: CPCardEntry, species_by_name: dict[str, int], default_species_by_name: dict[str, int]
) -> tuple[Optional[int], str]:
    base_slug = slugify(entry.base_name)

    if entry.ig_suffix is None:
        if base_slug in species_by_name:
            return species_by_name[base_slug], "matched base slug"
        # PokeAPI's default form doesn't always share the bare species slug
        # (e.g. Aegislash's default is 'aegislash-shield', not 'aegislash') --
        # use PokeAPI's own is_default flag rather than guessing a suffix.
        for name, species_id in default_species_by_name.items():
            if name == base_slug or name.startswith(base_slug + "-"):
                return species_id, f"matched PokeAPI default form '{name}'"
        return None, f"no PokeAPI species found for base '{entry.base_name}' (no exact or default-form match)"

    ig_key = entry.ig_suffix.lstrip("-").lower()
    suffix = IG_ALIAS.get(ig_key, ig_key.replace(" ", "-"))
    candidate = f"{base_slug}-{suffix}"
    if candidate in species_by_name:
        return species_by_name[candidate], "matched via ig= suffix"
    return None, f"no PokeAPI species found (base='{entry.base_name}', ig='{entry.ig_suffix}', tried '{candidate}')"


def _normalized_suffix_tokens(slug: str, base_slug: str) -> set[str]:
    remainder = slug
    if remainder.startswith(base_slug):
        remainder = remainder[len(base_slug):].strip("-")
    tokens = [t for t in remainder.split("-") if t]
    base_tokens = set(base_slug.split("-"))
    normalized = set()
    for t in tokens:
        t = _PZ_TOKEN_SYNONYMS.get(t, t)
        if t and t not in base_tokens:
            normalized.add(t)
    return normalized


def cross_check_with_pokemon_zone(
    entry: CPCardEntry, resolved_species_name: str, pz_slugs: set[str]
) -> tuple[bool, str]:
    """True/note for whether some Pokémon-Zone slug plausibly corresponds to
    this same form, using normalized suffix-token comparison (not exact
    string match -- the two sites use different slug conventions)."""
    base_slug = slugify(entry.base_name)

    same_species_slugs = [s for s in pz_slugs if s == base_slug or s.startswith(base_slug + "-")]
    if not same_species_slugs:
        return False, f"'{base_slug}' not found at all in Pokémon-Zone's current roster"

    if entry.ig_suffix is None:
        # No variant modifier on Bulbapedia's side -- Pokémon-Zone represents
        # "whichever form is default" with the bare base slug too, regardless
        # of what PokeAPI's internal suffix for that default form happens to
        # be (e.g. Aegislash's default is technically "-shield", but PZ just
        # calls it "aegislash"). So compare against ig=, not our resolved name.
        if base_slug in pz_slugs:
            return True, "base form present on both sources"
        return False, f"base form '{base_slug}' not listed on Pokémon-Zone (only variants: {same_species_slugs})"

    our_suffix_tokens = _normalized_suffix_tokens(resolved_species_name, base_slug)

    for pz_slug in same_species_slugs:
        pz_tokens = _normalized_suffix_tokens(pz_slug, base_slug)
        # only ours-as-subset-of-theirs: an empty pz_tokens (bare base slug)
        # must never satisfy a non-empty our_suffix_tokens.
        if pz_tokens and our_suffix_tokens <= pz_tokens:
            return True, f"matched Pokémon-Zone slug '{pz_slug}'"

    return False, (
        f"no Pokémon-Zone slug among {same_species_slugs} matches suffix tokens {our_suffix_tokens} "
        "(same species listed, but not this specific form)"
    )


def match_entry(
    entry: CPCardEntry,
    species_by_name: dict[str, int],
    default_species_by_name: dict[str, int],
    species_by_id: dict[int, str],
    pz_slugs: set[str],
) -> MatchResult:
    species_id, resolve_note = resolve_species_id(entry, species_by_name, default_species_by_name)
    if species_id is None:
        return MatchResult(None, resolve_note, False, "not verified: species unresolved")

    verified, verify_note = cross_check_with_pokemon_zone(entry, species_by_id[species_id], pz_slugs)
    return MatchResult(species_id, resolve_note, verified, verify_note)
