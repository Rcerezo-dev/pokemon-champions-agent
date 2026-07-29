"""Fase 12: (re)build the semantic-search index for every Pokémon legal in
the active regulation -- one document + embedding per species, stored in
LanceDB (src/semantic/store.py). Full rebuild every run (not incremental):
the roster is at most a few hundred species, so re-embedding everything is
cheap and avoids tracking a staleness/diff mechanism for something this
small.

Requires Fase 2-4 already seeded (regulation, movepool, usage) and
GEMINI_API_KEY set. Run after the regular pipeline: see run_pipeline.py.

Usage: python -m src.db.seed_embeddings
"""

import json

from sqlmodel import Session, select

from src.db.active_regulation import get_active_regulation
from src.db.database import engine, init_db
from src.db.models import (
    Ability,
    Move,
    PokemonAbility,
    PokemonMovepool,
    PokemonSpecies,
    RegulationLegalMove,
    RegulationLegalPokemon,
    UsageStat,
)
from src.semantic import store
from src.semantic.documents import AbilityRef, SpeciesDocInput, build_document
from src.semantic.embeddings import embed_documents


def main() -> None:
    init_db()
    with Session(engine) as session:
        regulation = get_active_regulation(session)
        print(f"Building semantic index for regulation {regulation.id}...")

        legal_species = session.exec(
            select(PokemonSpecies)
            .join(RegulationLegalPokemon, RegulationLegalPokemon.pokemon_species_id == PokemonSpecies.id)
            .where(RegulationLegalPokemon.regulation_id == regulation.id)
        ).all()
        print(f"  {len(legal_species)} legal species")

        ability_by_id = {a.id: a for a in session.exec(select(Ability)).all()}
        move_by_id = {m.id: m for m in session.exec(select(Move)).all()}
        regulation_move_ids = {
            r.move_id for r in session.exec(select(RegulationLegalMove).where(RegulationLegalMove.regulation_id == regulation.id))
        }
        usage_by_species = {
            u.pokemon_species_id: u for u in session.exec(select(UsageStat).where(UsageStat.regulation_id == regulation.id))
        }

        doc_texts = []
        rows_meta = []
        for sp in legal_species:
            species_abilities = session.exec(select(PokemonAbility).where(PokemonAbility.pokemon_species_id == sp.id)).all()
            abilities = [
                AbilityRef(name=ability_by_id[pa.ability_id].name, effect_text=ability_by_id[pa.ability_id].effect_text, is_hidden=pa.is_hidden)
                for pa in species_abilities
                if pa.ability_id in ability_by_id
            ]
            movepool_ids = {
                r.move_id for r in session.exec(select(PokemonMovepool).where(PokemonMovepool.pokemon_species_id == sp.id))
            }
            legal_moves = [move_by_id[mid] for mid in (movepool_ids & regulation_move_ids) if mid in move_by_id]
            usage = usage_by_species.get(sp.id)

            doc_input = SpeciesDocInput(
                species=sp, base_stats=json.loads(sp.base_stats_json), abilities=abilities, legal_moves=legal_moves, usage=usage
            )
            doc_texts.append(build_document(doc_input))

            types = sp.types.split(",")
            rows_meta.append(
                {
                    "pokemon_species_id": sp.id,
                    "name": sp.name,
                    "type_primary": types[0],
                    "type_secondary": types[1] if len(types) > 1 else None,
                    "regulation_id": regulation.id,
                    "usage_pct": usage.usage_pct if usage else None,
                    "verified_usage": bool(usage.verified) if usage else False,
                }
            )

        print("Embedding documents via Gemini (gemini-embedding-001)...")
        vectors = embed_documents(doc_texts)

        rows = [
            {**meta, "doc_text": text, "vector": vector}
            for meta, text, vector in zip(rows_meta, doc_texts, vectors)
        ]
        store.rebuild_table(rows)
        print(f"Indexed {len(rows)} species into {store.DB_DIR}.")


if __name__ == "__main__":
    main()
