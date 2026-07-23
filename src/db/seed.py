"""Fase 1: seed the local DB with static reference data from PokeAPI
(types, base stats, abilities, moves, natures). Idempotent -- re-running
just re-upserts from the (locally cached) PokeAPI responses.

Usage: python -m src.db.seed
"""

import asyncio
import json

from sqlmodel import Session, select

from src.db.database import engine, init_db
from src.db.models import Ability, Move, Nature, PokemonSpecies, TypeChart
from src.db.pokeapi_client import fetch_json, fetch_list, fetch_many, new_client

NON_STANDARD_TYPES = {"unknown", "shadow"}


def _english_effect(entries: list[dict]) -> str:
    for entry in entries:
        if entry["language"]["name"] == "en":
            return entry.get("short_effect") or entry.get("effect") or ""
    return ""


async def seed_types(client, session: Session) -> None:
    listing = await fetch_list(client, "type")
    urls = [t["url"] for t in listing]
    details = await fetch_many(client, urls)
    types = [d for d in details if d["name"] not in NON_STANDARD_TYPES]
    type_names = {d["name"] for d in types}

    # clear existing chart so re-seeding doesn't duplicate rows
    for row in session.exec(select(TypeChart)).all():
        session.delete(row)

    for atk in types:
        relations = atk["damage_relations"]
        multiplier = {name: 1.0 for name in type_names}
        for entry in relations["double_damage_to"]:
            multiplier[entry["name"]] = 2.0
        for entry in relations["half_damage_to"]:
            multiplier[entry["name"]] = 0.5
        for entry in relations["no_damage_to"]:
            multiplier[entry["name"]] = 0.0
        for defending_type, mult in multiplier.items():
            session.add(
                TypeChart(attacking_type=atk["name"], defending_type=defending_type, multiplier=mult)
            )
    session.commit()
    print(f"  type_chart: {len(types) * len(types)} pairs across {len(types)} types")


async def seed_natures(client, session: Session) -> None:
    listing = await fetch_list(client, "nature")
    urls = [n["url"] for n in listing]
    details = await fetch_many(client, urls)
    for i, d in enumerate(details, start=1):
        boosted = d["increased_stat"]["name"] if d["increased_stat"] else None
        lowered = d["decreased_stat"]["name"] if d["decreased_stat"] else None
        existing = session.get(Nature, i)
        nature = existing or Nature(id=i)
        nature.name = d["name"]
        nature.boosted_stat = boosted
        nature.lowered_stat = lowered
        session.add(nature)
    session.commit()
    print(f"  natures: {len(details)}")


async def seed_abilities(client, session: Session) -> None:
    listing = await fetch_list(client, "ability")
    urls = [a["url"] for a in listing]
    details = await fetch_many(client, urls)
    for d in details:
        existing = session.get(Ability, d["id"])
        ability = existing or Ability(id=d["id"])
        ability.name = d["name"]
        ability.effect_text = _english_effect(d["effect_entries"])
        session.add(ability)
    session.commit()
    print(f"  abilities: {len(details)}")


async def seed_moves(client, session: Session) -> None:
    listing = await fetch_list(client, "move")
    urls = [m["url"] for m in listing]
    details = await fetch_many(client, urls)
    for d in details:
        existing = session.get(Move, d["id"])
        move = existing or Move(id=d["id"])
        move.name = d["name"]
        move.type = d["type"]["name"]
        move.category = d["damage_class"]["name"] if d["damage_class"] else "status"
        move.power = d["power"]
        move.accuracy = d["accuracy"]
        move.pp = d["pp"]
        move.effect_text = _english_effect(d["effect_entries"])
        session.add(move)
    session.commit()
    print(f"  moves: {len(details)}")


async def seed_species(client, session: Session) -> None:
    listing = await fetch_list(client, "pokemon")
    urls = [p["url"] for p in listing]
    details = await fetch_many(client, urls)
    for d in details:
        types = [t["type"]["name"] for t in sorted(d["types"], key=lambda t: t["slot"])]
        stats = {s["stat"]["name"]: s["base_stat"] for s in d["stats"]}
        existing = session.get(PokemonSpecies, d["id"])
        species = existing or PokemonSpecies(id=d["id"])
        species.name = d["name"]
        species.types = ",".join(types)
        species.base_stats_json = json.dumps(stats)
        species.is_default = d["is_default"]
        session.add(species)
    session.commit()
    print(f"  species: {len(details)}")


async def main() -> None:
    init_db()
    async with new_client() as client:
        with Session(engine) as session:
            print("Seeding from PokeAPI (cached under data/raw/pokeapi/)...")
            await seed_types(client, session)
            await seed_natures(client, session)
            await seed_abilities(client, session)
            await seed_moves(client, session)
            await seed_species(client, session)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
