"""Fase 3: legal items/moves for the active regulation, plus per-species
movepool, cross-checking MetaVGC (primary, per-regulation snapshot) against
Serebii (live catalog).

Requires Fase 2's regulation + roster to already be seeded (`seed_regulation`).

Usage: python -m src.db.seed_movepool
"""

import re
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from src.db.active_regulation import get_active_regulation
from src.db.database import engine, init_db
from src.db.models import (
    Item,
    Move,
    PokemonMovepool,
    PokemonSpecies,
    RegulationLegalItem,
    RegulationLegalMove,
    RegulationLegalPokemon,
)
from src.scrapers import metavgc, serebii_champions
from src.scrapers.form_matching import IG_ALIAS, slugify

_KNOWN_FORM_SUFFIXES = sorted(
    # These species' *default* PokeAPI form is itself suffixed (no bare base
    # name exists), unlike most species -- found by running against the live
    # M-B roster and fixing each 404 as it showed up (Serebii has one page
    # per species, not per form).
    set(IG_ALIAS.values())
    | {"male", "shield", "blade", "average", "midday", "disguised", "full-belly", "zero", "family-of-four"},
    key=len,
    reverse=True,
)

# Serebii-specific slug irregularities that don't follow any general rule
# (a literal '.' instead of '-'), found the same way as the suffixes above.
_SEREBII_SLUG_OVERRIDES = {"mr-rime": "mr.rime"}


def _match_slug(name: str) -> str:
    """Normalizes a display name to the slug convention Move/Item rows use
    (PokeAPI's), handling quirks slugify() alone doesn't: apostrophe-elision
    ("King's Rock" -> "kings-rock") and camelCase concatenation
    ("BrightPowder" -> "bright-powder"), both seen on Serebii/MetaVGC."""
    name = name.replace("'", "")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return slugify(name)


def _base_slug_for_serebii(species_name: str) -> str:
    """Strip a known regional/mega/cosmetic-form suffix to recover the base
    species slug Serebii's per-Pokémon page uses -- Serebii doesn't have
    separate pages per form (confirmed: Charizard's single page covers base
    + Mega X/Y stat blocks)."""
    for suffix in _KNOWN_FORM_SUFFIXES:
        if species_name.endswith(f"-{suffix}"):
            species_name = species_name[: -(len(suffix) + 1)]
            break
    return _SEREBII_SLUG_OVERRIDES.get(species_name, species_name)


def _seed_flat_legal_set(
    session: Session,
    regulation_id: str,
    metavgc_names: list[str],
    serebii_names: set[str],
    catalog_by_slug: dict[str, int],
    row_cls,
    fk_field: str,
    now: datetime,
) -> tuple[int, int, list[str]]:
    """Matches MetaVGC's flat name list against our static catalog (Move or
    Item, keyed by slugify(name)) and against Serebii's live catalog for
    verification. Returns (verified_count, unverified_count, unresolved_names)."""
    serebii_slugs = {_match_slug(n) for n in serebii_names}
    verified = 0
    unverified = 0
    unresolved: list[str] = []
    for name in metavgc_names:
        slug = _match_slug(name)
        catalog_id = catalog_by_slug.get(slug)
        if catalog_id is None:
            unresolved.append(name)
            continue
        is_verified = slug in serebii_slugs
        kwargs = {
            "regulation_id": regulation_id,
            fk_field: catalog_id,
            "source": "metavgc+serebii" if is_verified else "metavgc",
            "retrieved_at": now,
            "verified": is_verified,
            "verification_note": "matched Serebii live catalog" if is_verified else "not found in Serebii's live catalog",
        }
        session.add(row_cls(**kwargs))
        if is_verified:
            verified += 1
        else:
            unverified += 1
    return verified, unverified, unresolved


def main() -> None:
    init_db()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        regulation = get_active_regulation(session)
        print(f"Active regulation: {regulation.id}")

        print("Fetching legal items/moves snapshot from MetaVGC...")
        with httpx.Client() as client:
            snapshot = metavgc.fetch_regulation_snapshot(regulation.id, client)
        print(f"  {len(snapshot.legal_pokemon)} legal Pokémon, {len(snapshot.allowed_items)} items, {len(snapshot.allowed_moves)} moves (published {snapshot.published})")

        print("Fetching live move/item catalogs from Serebii (for cross-check)...")
        with httpx.Client() as client:
            serebii_moves = serebii_champions.fetch_moves_catalog(client)
            serebii_items = serebii_champions.fetch_items_catalog(client)
        print(f"  {len(serebii_moves)} moves, {len(serebii_items)} items in Serebii's live catalog")

        moves_by_slug = {_match_slug(m.name): m.id for m in session.exec(select(Move)).all()}
        items_by_slug = {_match_slug(i.name): i.id for i in session.exec(select(Item)).all()}

        for row in session.exec(select(RegulationLegalMove).where(RegulationLegalMove.regulation_id == regulation.id)):
            session.delete(row)
        for row in session.exec(select(RegulationLegalItem).where(RegulationLegalItem.regulation_id == regulation.id)):
            session.delete(row)
        session.commit()

        moves_verified, moves_unverified, moves_unresolved = _seed_flat_legal_set(
            session, regulation.id, snapshot.allowed_moves, serebii_moves, moves_by_slug, RegulationLegalMove, "move_id", now
        )
        items_verified, items_unverified, items_unresolved = _seed_flat_legal_set(
            session, regulation.id, snapshot.allowed_items, serebii_items, items_by_slug, RegulationLegalItem, "item_id", now
        )
        session.commit()

        print(f"\nMoves: {moves_verified} verified, {moves_unverified} unverified, {len(moves_unresolved)} unresolved (no matching Move row)")
        if moves_unresolved:
            print(f"  unresolved: {moves_unresolved}")
        print(f"Items: {items_verified} verified, {items_unverified} unverified, {len(items_unresolved)} unresolved (no matching Item row)")
        if items_unresolved:
            print(f"  unresolved: {items_unresolved}")

        print("\nFetching per-species movepool from Serebii...")
        legal_rows = session.exec(
            select(RegulationLegalPokemon).where(RegulationLegalPokemon.regulation_id == regulation.id)
        ).all()
        species_by_id = {s.id: s for s in session.exec(select(PokemonSpecies)).all()}

        slug_to_species_ids: dict[str, list[int]] = {}
        for row in legal_rows:
            species = species_by_id[row.pokemon_species_id]
            base_slug = _base_slug_for_serebii(species.name)
            slug_to_species_ids.setdefault(base_slug, []).append(species.id)

        for row in session.exec(select(PokemonMovepool)).all():
            session.delete(row)
        session.commit()

        movepool_ok = 0
        movepool_failed: list[tuple[str, str]] = []
        movepool_unmatched_moves: set[str] = set()
        with httpx.Client() as client:
            for i, (base_slug, species_ids) in enumerate(sorted(slug_to_species_ids.items()), start=1):
                try:
                    move_names = serebii_champions.fetch_species_movepool(base_slug, client)
                except serebii_champions.SerebiiChampionsScrapeError as e:
                    movepool_failed.append((base_slug, str(e)))
                    continue
                move_ids = []
                for move_name in move_names:
                    move_id = moves_by_slug.get(_match_slug(move_name))
                    if move_id is None:
                        movepool_unmatched_moves.add(move_name)
                        continue
                    move_ids.append(move_id)
                for species_id in species_ids:
                    for move_id in move_ids:
                        session.add(
                            PokemonMovepool(
                                pokemon_species_id=species_id,
                                move_id=move_id,
                                source="serebii",
                                retrieved_at=now,
                            )
                        )
                movepool_ok += 1
                if i % 25 == 0:
                    session.commit()
                    print(f"  ...{i}/{len(slug_to_species_ids)} species slugs processed")
        session.commit()

        print(f"\nMovepool fetched for {movepool_ok}/{len(slug_to_species_ids)} species slugs.")
        if movepool_failed:
            print(f"  failed ({len(movepool_failed)}):")
            for slug, note in movepool_failed:
                print(f"    - {slug}: {note}")
        if movepool_unmatched_moves:
            print(f"  {len(movepool_unmatched_moves)} move names on Serebii had no matching Move row (not stored): {sorted(movepool_unmatched_moves)[:20]}")


if __name__ == "__main__":
    main()
