from src.db.seed_usage import _resolve_species_id
from src.scrapers.championsmeta import (
    _USAGE_ROW_RE,
    ChampionsMetaScrapeError,
    _parse_tournament_block,
)
from src.scrapers.pikalytics import _TOP20_RE

USAGE_SAMPLE_HTML = (
    '<span class="text-xs font-semibold text-accent-blue">Regulation M-B</span>'
    '<table><tbody>'
    '<tr><td><a href="/pokemon/garchomp"><img alt="Garchomp"/><span class="font-bold text-accent-blue block">34.9<!-- -->%</span></a></td></tr>'
    '<tr><td><a href="/pokemon/incineroar"><img alt="Incineroar"/><span class="font-bold text-accent-blue block">33.4<!-- -->%</span></a></td></tr>'
    '</tbody></table>'
    '<h2>Regulation M-A<!-- --> Usage History</h2>'
    '<tr><td><a href="/pokemon/old-mon"><img alt="OldMon"/><span class="font-bold text-accent-blue block">99.9<!-- -->%</span></a></td></tr>'
)


def test_usage_row_regex_stops_before_history_section():
    cutoff = USAGE_SAMPLE_HTML.find("Usage History")
    current = USAGE_SAMPLE_HTML[:cutoff]
    matches = _USAGE_ROW_RE.findall(current)
    assert matches == [("garchomp", "Garchomp", "34.9"), ("incineroar", "Incineroar", "33.4")]


TOURNAMENT_BLOCK_MB = """
<h2 class="text-lg font-bold text-text-primary">Neme Weekly Tour #66</h2><span class="rounded bg-accent-blue/10 border border-accent-blue/20 px-1.5 py-0.5 text-[10px] font-semibold text-accent-blue">Reg M-B</span>
<span>IRGamers</span><span>July 24, 2026</span><span>21<!-- --> <!-- -->players</span>
<a href="https://play.limitlesstcg.com/tournament/6a60b8f4/standings">View on Limitless</a>
<span class="inline-flex items-center justify-center w-7 h-7 rounded-full border text-[11px] font-bold shrink-0 text-yellow-400 border-yellow-600/40 bg-yellow-500/10">1</span>
<p class="text-sm font-semibold text-text-primary truncate">Miscell O</p>
<span class="hidden sm:block text-xs font-mono text-text-muted w-12 shrink-0">8-0-0</span>
<img alt="incineroar"/><img alt="charizard"/><img alt="toxapex"/>
<span class="inline-flex items-center justify-center w-7 h-7 rounded-full border text-[11px] font-bold shrink-0 text-slate-300 border-slate-500/40 bg-slate-400/10">2</span>
<p class="text-sm font-semibold text-text-primary truncate">jvvieree</p>
<span class="hidden sm:block text-xs font-mono text-text-muted w-12 shrink-0">6-2-0</span>
<img alt="charizard"/><img alt="pelipper"/>
"""

TOURNAMENT_BLOCK_MA = TOURNAMENT_BLOCK_MB.replace("Reg M-B", "Reg M-A")


def test_parse_tournament_block_mb():
    entry = _parse_tournament_block(TOURNAMENT_BLOCK_MB)
    assert entry is not None
    assert entry.name == "Neme Weekly Tour #66"
    assert entry.organizer == "IRGamers"
    assert entry.player_count == 21
    assert entry.source_url == "https://play.limitlesstcg.com/tournament/6a60b8f4/standings"
    assert len(entry.teams) == 2
    assert entry.teams[0].placement == 1
    assert entry.teams[0].player_name == "Miscell O"
    assert entry.teams[0].record == "8-0-0"
    assert entry.teams[0].pokemon_slugs == ["incineroar", "charizard", "toxapex"]
    assert entry.teams[1].pokemon_slugs == ["charizard", "pelipper"]


def test_parse_tournament_block_skips_ma():
    assert _parse_tournament_block(TOURNAMENT_BLOCK_MA) is None


def test_parse_tournament_block_missing_url_raises():
    broken = TOURNAMENT_BLOCK_MB.replace(
        '<a href="https://play.limitlesstcg.com/tournament/6a60b8f4/standings">View on Limitless</a>', ""
    )
    try:
        _parse_tournament_block(broken)
        assert False, "expected ChampionsMetaScrapeError"
    except ChampionsMetaScrapeError:
        pass


PIKALYTICS_TOP20_SAMPLE = (
    '<a class="tournament-top20-card tournament-top20-card-medal" data-name="Garchomp" aria-label="Rank 1 Garchomp">...</a>'
    '<a class="tournament-top20-card" data-name="Sinistcha" aria-label="Rank 2 Sinistcha">...</a>'
)


def test_pikalytics_top20_regex():
    assert _TOP20_RE.findall(PIKALYTICS_TOP20_SAMPLE) == ["Garchomp", "Sinistcha"]


FAKE_SPECIES_BY_SLUG = {"garchomp": 445, "ninetales-alola": 10103, "rotom-wash": 10092, "floette-eternal": 10071}
FAKE_DEFAULT_BY_SLUG = {"basculegion": 902, "maushold": 925, "pyroar": 668, "palafin": 964}


def test_resolve_species_id_direct_match():
    assert _resolve_species_id("garchomp", FAKE_SPECIES_BY_SLUG, FAKE_DEFAULT_BY_SLUG) == 445


def test_resolve_species_id_regional_prefix_reorder():
    assert _resolve_species_id("alolan-ninetales", FAKE_SPECIES_BY_SLUG, FAKE_DEFAULT_BY_SLUG) == 10103


def test_resolve_species_id_rotom_form_reorder():
    assert _resolve_species_id("wash-rotom", FAKE_SPECIES_BY_SLUG, FAKE_DEFAULT_BY_SLUG) == 10092


def test_resolve_species_id_override():
    assert _resolve_species_id("eternal-flower-floette", FAKE_SPECIES_BY_SLUG, FAKE_DEFAULT_BY_SLUG) == 10071


def test_resolve_species_id_default_form_fallback():
    assert _resolve_species_id("basculegion", FAKE_SPECIES_BY_SLUG, FAKE_DEFAULT_BY_SLUG) == 902


def test_resolve_species_id_unresolved():
    assert _resolve_species_id("totally-unknown-mon", FAKE_SPECIES_BY_SLUG, FAKE_DEFAULT_BY_SLUG) is None
