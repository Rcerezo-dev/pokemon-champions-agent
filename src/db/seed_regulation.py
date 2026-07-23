"""Fase 2: scrape the active Pokémon Champions Regulation Set and its legal
roster, cross-checking between Bulbapedia, Victory Road and Pokémon-Zone.

Usage: python -m src.db.seed_regulation
"""

from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from src.db.database import engine, init_db
from src.db.models import PokemonSpecies, RegulationLegalPokemon, RegulationSet
from src.scrapers import bulbapedia, pokemon_zone, victory_road
from src.scrapers.form_matching import match_entry


def _cross_check_regulation_metadata(detail: bulbapedia.RegulationDetail) -> str:
    """Compares Bulbapedia's regulation dates/mega flag against Victory
    Road's. Returns a note describing the result; raises nothing -- a
    mismatch is surfaced in the note and printed, not silently accepted."""
    try:
        summaries = victory_road.fetch_regulation_summaries()
    except victory_road.VictoryRoadScrapeError as e:
        return f"Victory Road cross-check failed: {e}"

    matches = [s for s in summaries if s.code == detail.code]
    if not matches:
        return f"Victory Road cross-check failed: no sentence found for code '{detail.code}'"
    vr = matches[0]

    end_month_ok = detail.end.strftime("%B") == vr.end_month
    end_day_ok = detail.end.day == vr.end_day
    end_year_ok = detail.end.year == vr.end_year
    mega_ok = detail.mega_allowed == vr.mega_allowed

    if end_month_ok and end_day_ok and end_year_ok and mega_ok:
        return "OK: end date and mega_allowed match Victory Road"
    return (
        f"MISMATCH vs Victory Road: end_date_ok={end_day_ok and end_month_ok and end_year_ok} "
        f"mega_allowed_ok={mega_ok} (bulbapedia mega_allowed={detail.mega_allowed}, "
        f"victory_road mega_allowed={vr.mega_allowed})"
    )


def main() -> None:
    init_db()
    now = datetime.now(timezone.utc)

    print("Fetching active regulation from Bulbapedia...")
    with httpx.Client() as client:
        detail = bulbapedia.fetch_active_regulation(client)
    print(f"  active regulation: {detail.code} ({detail.start.date()} -> {detail.end.date()})")
    print(f"  {len(detail.entries)} CPCard entries in roster")

    metadata_note = _cross_check_regulation_metadata(detail)
    print(f"  {metadata_note}")

    print("Fetching current roster from Pokémon-Zone (for cross-check)...")
    try:
        pz_slugs = pokemon_zone.fetch_current_roster_slugs()
        print(f"  {len(pz_slugs)} slugs found")
    except pokemon_zone.PokemonZoneScrapeError as e:
        print(f"  Pokémon-Zone cross-check unavailable: {e}")
        pz_slugs = set()

    with Session(engine) as session:
        species_rows = session.exec(select(PokemonSpecies)).all()
        species_by_name = {s.name: s.id for s in species_rows}
        default_species_by_name = {s.name: s.id for s in species_rows if s.is_default}
        species_by_id = {s.id: s.name for s in species_rows}

        reg = session.get(RegulationSet, detail.code) or RegulationSet(id=detail.code)
        reg.name = f"Regulation Set {detail.code}"
        reg.start_date = detail.start
        reg.end_date = detail.end
        reg.mega_allowed = detail.mega_allowed
        reg.notes = f"{detail.ruleset_text} | cross-check: {metadata_note}"
        reg.source = "bulbapedia"
        reg.retrieved_at = now
        session.add(reg)

        for row in session.exec(
            select(RegulationLegalPokemon).where(RegulationLegalPokemon.regulation_id == detail.code)
        ):
            session.delete(row)

        unresolved = []
        unverified = []
        verified_count = 0
        for entry in detail.entries:
            result = match_entry(entry, species_by_name, default_species_by_name, species_by_id, pz_slugs)
            if result.species_id is None:
                unresolved.append((entry, result.resolve_note))
                continue
            session.add(
                RegulationLegalPokemon(
                    regulation_id=detail.code,
                    pokemon_species_id=result.species_id,
                    source="bulbapedia+pokemon-zone" if pz_slugs else "bulbapedia",
                    retrieved_at=now,
                    verified=result.verified,
                    verification_note=result.verify_note,
                )
            )
            if result.verified:
                verified_count += 1
            else:
                unverified.append((entry, result.verify_note))

        session.commit()

    total = len(detail.entries)
    print(f"\nSeeded {total - len(unresolved)}/{total} roster entries for {detail.code}.")
    print(f"  verified (cross-checked against Pokémon-Zone): {verified_count}")
    print(f"  unverified (species resolved, no PZ cross-check match): {len(unverified)}")
    print(f"  unresolved (no matching PokeAPI species at all -- not stored): {len(unresolved)}")

    if unresolved:
        print("\nUnresolved entries:")
        for entry, note in unresolved:
            print(f"  - {entry.base_name} (dex {entry.dex_number}, ig={entry.ig_suffix}): {note}")

    if unverified:
        print(f"\nUnverified entries ({len(unverified)}), first 20:")
        for entry, note in unverified[:20]:
            print(f"  - {entry.base_name} (dex {entry.dex_number}, ig={entry.ig_suffix}): {note}")


if __name__ == "__main__":
    main()
