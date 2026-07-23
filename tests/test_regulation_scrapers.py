import re

from src.scrapers.bulbapedia import parse_cpcard_entries
from src.scrapers.form_matching import match_entry, resolve_species_id, slugify
from src.scrapers.pokemon_zone import _SLUG_RE
from src.scrapers.victory_road import _SENTENCE_RE

SAMPLE_WIKITEXT = """
{{Flexheader}}
{{CPCard|0006|Charizard}}
{{CPCard|0006|Charizard|ig=-Mega X}}
{{CPCard|0006|Charizard|ig=-Mega Y}}
{{CPCard|0026|Raichu}}
{{CPCard|0026|Raichu|ig=-Alola|name=[[Raichu (Pokémon)|Raichu<br><small>(Alolan Form)</small>]]}}
{{CPCard|0678|Meowstic|ig=-Female|name=[[Meowstic (Pokémon)|Meowstic<br><small>(Female)</small>]]}}
{{Flexfooter}}
"""


def test_parse_cpcard_entries():
    entries = parse_cpcard_entries(SAMPLE_WIKITEXT)
    assert len(entries) == 6
    assert entries[0].dex_number == 6
    assert entries[0].base_name == "Charizard"
    assert entries[0].ig_suffix is None
    assert entries[1].ig_suffix == "-Mega X"
    assert entries[5].form_label == "Female"


def test_slugify():
    assert slugify("Charizard") == "charizard"
    assert slugify("Mr. Mime") == "mr-mime"


FAKE_SPECIES = {
    "charizard": 6,
    "charizard-mega-x": 10034,
    "charizard-mega-y": 10035,
    "raichu": 26,
    "raichu-alola": 10100,
    "meowstic-male": 678,
    "meowstic-female": 10001,
    "aegislash-shield": 681,
    "aegislash-blade": 10026,
}
FAKE_SPECIES_BY_ID = {v: k for k, v in FAKE_SPECIES.items()}
# only "shield" is PokeAPI's default form for Aegislash; everything else here
# happens to be its own default (base-slug lookup succeeds before this is used).
FAKE_DEFAULT_SPECIES = {"aegislash-shield": 681}


def test_resolve_species_id_base_form():
    entries = parse_cpcard_entries(SAMPLE_WIKITEXT)
    species_id, note = resolve_species_id(entries[0], FAKE_SPECIES, FAKE_DEFAULT_SPECIES)
    assert species_id == 6
    assert "base slug" in note


def test_resolve_species_id_mega_x():
    entries = parse_cpcard_entries(SAMPLE_WIKITEXT)
    mega_x = entries[1]
    species_id, _ = resolve_species_id(mega_x, FAKE_SPECIES, FAKE_DEFAULT_SPECIES)
    assert species_id == 10034


def test_resolve_species_id_gendered_fallback():
    entries = parse_cpcard_entries(SAMPLE_WIKITEXT)
    meowstic_female = entries[5]
    species_id, note = resolve_species_id(meowstic_female, FAKE_SPECIES, FAKE_DEFAULT_SPECIES)
    assert species_id == 10001  # matched via ig=-Female -> "female" suffix


def test_resolve_species_id_falls_back_to_pokeapi_default_form():
    # Bulbapedia's base "Aegislash" entry has no bare "aegislash" species in
    # PokeAPI -- only "-shield" (default) and "-blade". Must use is_default,
    # not a guessed suffix list.
    entries = parse_cpcard_entries("{{CPCard|0681|Aegislash}}")
    species_id, note = resolve_species_id(entries[0], FAKE_SPECIES, FAKE_DEFAULT_SPECIES)
    assert species_id == 681
    assert "default form" in note


def test_resolve_species_id_unresolved():
    entries = parse_cpcard_entries("{{CPCard|0666|Vivillon|ig=-Fancy}}")
    species_id, note = resolve_species_id(entries[0], FAKE_SPECIES, FAKE_DEFAULT_SPECIES)
    assert species_id is None
    assert "no PokeAPI species found" in note


def test_match_entry_verified_when_pz_has_same_form():
    entries = parse_cpcard_entries(SAMPLE_WIKITEXT)
    charizard_mega_x = entries[1]
    pz_slugs = {"charizard", "charizard-mega-charizard-x", "charizard-mega-charizard-y"}
    result = match_entry(charizard_mega_x, FAKE_SPECIES, FAKE_DEFAULT_SPECIES, FAKE_SPECIES_BY_ID, pz_slugs)
    assert result.species_id == 10034
    assert result.verified is True


def test_match_entry_unverified_when_pz_missing_form():
    entries = parse_cpcard_entries(SAMPLE_WIKITEXT)
    raichu_alola = entries[4]
    pz_slugs = {"raichu"}  # no alolan form listed on Pokémon-Zone
    result = match_entry(raichu_alola, FAKE_SPECIES, FAKE_DEFAULT_SPECIES, FAKE_SPECIES_BY_ID, pz_slugs)
    assert result.species_id == 10100
    assert result.verified is False


VR_SAMPLE_TEXT = (
    "The Regulation Set M-B of Pokémon Champions is the second official ruleset "
    "confirmed in the new game. Mega Evolutions are allowed. Regulation Set M-B "
    "is the official format of in-game Ranked Battles from 17 June to 2 September 2026, "
    "and will be used in VGC events on the same dates."
)


def test_victory_road_sentence_regex():
    m = _SENTENCE_RE.search(VR_SAMPLE_TEXT)
    assert m is not None
    assert m.group("code") == "M-B"
    assert m.group("sday") == "17"
    assert m.group("smonth") == "June"
    assert m.group("eday") == "2"
    assert m.group("emonth") == "September"
    assert m.group("eyear") == "2026"


PZ_SAMPLE_HTML = (
    '<a href="/champions/pokemon/pikachu/" class="champs-pokemon-card" '
    'data-pokemon-name="pikachu" style="--type-color: #F7D02C;">'
)


def test_pokemon_zone_slug_regex():
    assert _SLUG_RE.findall(PZ_SAMPLE_HTML) == ["pikachu"]
