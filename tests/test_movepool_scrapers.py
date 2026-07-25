from src.db.seed_movepool import _base_slug_for_serebii
from src.scrapers.metavgc import MetaVGCScrapeError, _extract_section, _unescape
from src.scrapers.serebii_champions import _ATTACKDEX_RE, _ITEMDEX_RE

METAVGC_SAMPLE_HTML = """
<h2 id="legal-pokemon-3">Legal Pokemon (3)</h2><div><table><thead><tr><th></th></tr></thead>
<tbody><tr><td>Charizard</td><td>Pikachu</td></tr><tr><td>Mega Blaziken</td></tr></tbody></table></div>
<h2 id="allowed-items-2">Allowed items (2)</h2><div><table><thead><tr><th></th></tr></thead>
<tbody><tr><td>Life Orb</td><td>King&#x27;s Rock</td></tr></tbody></table></div>
<h2 id="allowed-moves-2">Allowed moves (2)</h2><div><table><thead><tr><th></th></tr></thead>
<tbody><tr><td>Flamethrower</td><td>Dragon Dance</td></tr></tbody></table></div>
"""


def test_extract_section_pokemon():
    values = _extract_section(METAVGC_SAMPLE_HTML, "legal-pokemon")
    assert values == ["Charizard", "Pikachu", "Mega Blaziken"]


def test_extract_section_items_unescaped():
    values = [_unescape(v) for v in _extract_section(METAVGC_SAMPLE_HTML, "allowed-items")]
    assert values == ["Life Orb", "King's Rock"]


def test_extract_section_missing_heading_raises():
    try:
        _extract_section(METAVGC_SAMPLE_HTML, "banned-pokemon")
        assert False, "expected MetaVGCScrapeError"
    except MetaVGCScrapeError:
        pass


SEREBII_MOVES_SAMPLE = (
    '<td rowspan="2" class="fooinfo"><a href="/attackdex-champions/flamethrower.shtml">Flamethrower</a></td>'
    '<td rowspan="2" class="fooinfo"><a href="/attackdex-champions/dragondance.shtml">Dragon Dance</a></td>'
)


def test_serebii_attackdex_regex():
    assert _ATTACKDEX_RE.findall(SEREBII_MOVES_SAMPLE) == ["Flamethrower", "Dragon Dance"]


SEREBII_ITEMS_SAMPLE = (
    '<td class="cen"><a href="/itemdex/bigroot.shtml"><img src="x.png" /></a></td>'
    '<td class="fooinfo"><a href="/itemdex/bigroot.shtml">Big Root</a></td>'
    '<td class="fooinfo"><a href="/itemdex/kingsrock.shtml">King&#x27;s Rock</a></td>'
)


def test_serebii_itemdex_regex():
    assert _ITEMDEX_RE.findall(SEREBII_ITEMS_SAMPLE) == ["Big Root", "King&#x27;s Rock"]


def test_base_slug_strips_known_mega_suffix():
    assert _base_slug_for_serebii("charizard-mega-x") == "charizard"
    assert _base_slug_for_serebii("charizard-mega-y") == "charizard"


def test_base_slug_strips_regional_suffix():
    assert _base_slug_for_serebii("raichu-alola") == "raichu"


def test_base_slug_strips_multi_token_breed_suffix():
    assert _base_slug_for_serebii("tauros-paldea-combat-breed") == "tauros"


def test_base_slug_no_suffix_unchanged():
    assert _base_slug_for_serebii("pikachu") == "pikachu"


def test_base_slug_strips_default_form_own_suffix():
    # These species' *default* PokeAPI form is itself suffixed -- no bare
    # base name exists in PokeAPI at all.
    assert _base_slug_for_serebii("aegislash-shield") == "aegislash"
    assert _base_slug_for_serebii("gourgeist-average") == "gourgeist"
    assert _base_slug_for_serebii("lycanroc-midday") == "lycanroc"
    assert _base_slug_for_serebii("palafin-zero") == "palafin"


def test_base_slug_applies_serebii_specific_override():
    assert _base_slug_for_serebii("mr-rime") == "mr.rime"
