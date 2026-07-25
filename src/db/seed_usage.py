"""Fase 4: real-tournament usage stats and notable teams for the active
regulation, from ChampionsMeta (primary, cites Limitless TCG as its source)
cross-checked against Pikalytics' top-20 list (secondary, independent).

Requires Fase 2's regulation to already be seeded (`seed_regulation`).

Usage: python -m src.db.seed_usage
"""

import json
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlmodel import Session, select

from src.db.active_regulation import get_active_regulation
from src.db.database import engine, init_db
from src.db.models import NotableTeam, PokemonSpecies, UsageStat
from src.scrapers import championsmeta, pikalytics
from src.scrapers.form_matching import slugify

# ChampionsMeta puts region/form descriptors *before* the species name
# ("Alolan-Ninetales", "Wash-Rotom"); PokeAPI puts them after
# ("ninetales-alola", "rotom-wash"). Found by running against live data.
_REGIONAL_PREFIX_TO_SUFFIX = {"alolan": "alola", "galarian": "galar", "hisuian": "hisui", "paldean": "paldea"}
_ROTOM_FORMS = {"heat", "wash", "frost", "fan", "mow"}
_SLUG_OVERRIDES = {"eternal-flower-floette": "floette-eternal"}


def _resolve_species_id(slug: str, species_by_slug: dict[str, int], default_species_by_slug: dict[str, int]) -> Optional[int]:
    slug = _SLUG_OVERRIDES.get(slug, slug)
    if slug in species_by_slug:
        return species_by_slug[slug]
    parts = slug.split("-", 1)
    if len(parts) == 2:
        prefix, rest = parts
        if prefix in _REGIONAL_PREFIX_TO_SUFFIX:
            candidate = species_by_slug.get(f"{rest}-{_REGIONAL_PREFIX_TO_SUFFIX[prefix]}")
            if candidate is not None:
                return candidate
        if prefix in _ROTOM_FORMS and rest == "rotom":
            candidate = species_by_slug.get(f"rotom-{prefix}")
            if candidate is not None:
                return candidate
    # Default-form fallback: species whose *default* PokeAPI form is itself
    # suffixed (e.g. slug='basculegion' but PokeAPI's default is
    # 'basculegion-male', no bare 'basculegion' exists) -- same class of
    # issue as Fase 3's Aegislash/Gourgeist handling.
    return default_species_by_slug.get(slug)


def main() -> None:
    init_db()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        regulation = get_active_regulation(session)
        print(f"Active regulation: {regulation.id}")
        all_species = session.exec(select(PokemonSpecies)).all()
        species_by_slug = {slugify(s.name): s.id for s in all_species}
        default_species_by_slug = {s.name.split("-", 1)[0]: s.id for s in all_species if s.is_default}

        print("Fetching usage rankings from ChampionsMeta...")
        with httpx.Client() as client:
            usage_entries = championsmeta.fetch_usage_rankings(regulation.id, client)
        print(f"  {len(usage_entries)} ranked entries")

        print("Fetching Top 20 from Pikalytics (for cross-check)...")
        try:
            with httpx.Client() as client:
                top20_names = pikalytics.fetch_top20_names(client)
            print(f"  {len(top20_names)} names")
        except pikalytics.PikalyticsScrapeError as e:
            print(f"  Pikalytics cross-check unavailable: {e}")
            top20_names = []
        top20_species_ids = {
            sid
            for n in top20_names
            if (sid := _resolve_species_id(slugify(n), species_by_slug, default_species_by_slug)) is not None
        }

        for row in session.exec(select(UsageStat).where(UsageStat.regulation_id == regulation.id)):
            session.delete(row)

        resolved = 0
        verified = 0
        unresolved: list[str] = []
        for entry in usage_entries:
            species_id = _resolve_species_id(slugify(entry.slug), species_by_slug, default_species_by_slug)
            if species_id is None:
                unresolved.append(entry.name)
                continue
            is_verified = species_id in top20_species_ids
            session.add(
                UsageStat(
                    regulation_id=regulation.id,
                    pokemon_species_id=species_id,
                    usage_pct=entry.usage_pct,
                    source="championsmeta+pikalytics" if is_verified else "championsmeta",
                    retrieved_at=now,
                    verified=is_verified,
                    verification_note="in Pikalytics' Top 20" if is_verified else "not cross-checked (outside Pikalytics' Top 20 or unavailable)",
                )
            )
            resolved += 1
            if is_verified:
                verified += 1
        session.commit()

        print(f"\nUsage stats: {resolved}/{len(usage_entries)} resolved to a species ({verified} verified against Pikalytics)")
        if unresolved:
            print(f"  unresolved: {unresolved}")

        print("\nFetching recent tournament results from ChampionsMeta...")
        with httpx.Client() as client:
            tournaments = championsmeta.fetch_recent_tournaments(client)
        print(f"  {len(tournaments)} tournaments for {regulation.id}")

        for row in session.exec(select(NotableTeam).where(NotableTeam.regulation_id == regulation.id)):
            session.delete(row)

        team_count = 0
        team_unresolved: set[str] = set()
        for tournament in tournaments:
            for team in tournament.teams:
                species_ids = []
                for slug in team.pokemon_slugs:
                    sid = _resolve_species_id(slugify(slug), species_by_slug, default_species_by_slug)
                    if sid is None:
                        team_unresolved.add(slug)
                    species_ids.append({"slug": slug, "pokemon_species_id": sid})
                session.add(
                    NotableTeam(
                        regulation_id=regulation.id,
                        name=f"{team.player_name} @ {tournament.name}",
                        source_event=tournament.organizer,
                        placement=team.placement,
                        team_json=json.dumps({"player": team.player_name, "record": team.record, "pokemon": species_ids}),
                        source_url=tournament.source_url,
                        source="championsmeta",
                        retrieved_at=now,
                    )
                )
                team_count += 1
        session.commit()

        print(f"\nNotable teams stored: {team_count}")
        if team_unresolved:
            print(f"  {len(team_unresolved)} Pokémon slugs with no matching species (kept in team_json, no id): {sorted(team_unresolved)}")


if __name__ == "__main__":
    main()
