"""Fase 6 is one of the two phases CLAUDE.md marks as critical (mandatory
tests) -- uses a hermetic in-memory DB with hand-picked fixture data instead
of the real local DB, so every rule can be tested against an exact,
unchanging scenario rather than today's live scrape results.
"""

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from src.db.models import (
    Ability,
    Item,
    Move,
    Nature,
    PokemonMovepool,
    PokemonSpecies,
    RegulationLegalItem,
    RegulationLegalMove,
    RegulationLegalPokemon,
    RegulationSet,
)
from src.validation.team_validator import SP_PER_STAT_CAP, SP_TOTAL_CAP, TeamMember, validate_team

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(RegulationSet(id="TEST", name="Test Reg", start_date=NOW, end_date=NOW, mega_allowed=True, notes="", source="x", retrieved_at=NOW))

        charizard = PokemonSpecies(id=6, name="charizard", types="fire,flying", base_stats_json="{}")
        blastoise = PokemonSpecies(id=9, name="blastoise", types="water", base_stats_json="{}")
        venusaur = PokemonSpecies(id=3, name="venusaur", types="grass,poison", base_stats_json="{}")
        pikachu = PokemonSpecies(id=25, name="pikachu", types="electric", base_stats_json="{}")  # not in legal roster
        s.add_all([charizard, blastoise, venusaur, pikachu])

        flamethrower = Move(id=1, name="flamethrower", type="fire", category="special", power=90, accuracy=100, pp=15, effect_text="")
        surf = Move(id=2, name="surf", type="water", category="special", power=90, accuracy=100, pp=15, effect_text="")
        hydro_pump = Move(id=3, name="hydro-pump", type="water", category="special", power=110, accuracy=80, pp=5, effect_text="")  # in movepool, banned this reg
        thunderbolt = Move(id=4, name="thunderbolt", type="electric", category="special", power=90, accuracy=100, pp=15, effect_text="")  # not in anyone's movepool
        razor_leaf = Move(id=5, name="razor-leaf", type="grass", category="physical", power=55, accuracy=95, pp=25, effect_text="")
        s.add_all([flamethrower, surf, hydro_pump, thunderbolt, razor_leaf])

        life_orb = Item(id=1, name="life-orb", category="held-items", effect_text="")
        leftovers = Item(id=2, name="leftovers", category="held-items", effect_text="")  # not legal this reg
        s.add_all([life_orb, leftovers])

        s.add(Ability(id=1, name="blaze", effect_text=""))
        s.add(Nature(id=1, name="adamant", boosted_stat="attack", lowered_stat="special-attack"))

        s.add(RegulationLegalPokemon(regulation_id="TEST", pokemon_species_id=6, source="x", retrieved_at=NOW, verified=True))
        s.add(RegulationLegalPokemon(regulation_id="TEST", pokemon_species_id=9, source="x", retrieved_at=NOW, verified=True))
        s.add(RegulationLegalPokemon(regulation_id="TEST", pokemon_species_id=3, source="x", retrieved_at=NOW, verified=True))

        s.add(PokemonMovepool(pokemon_species_id=6, move_id=1, source="x", retrieved_at=NOW))
        s.add(PokemonMovepool(pokemon_species_id=9, move_id=2, source="x", retrieved_at=NOW))
        s.add(PokemonMovepool(pokemon_species_id=9, move_id=3, source="x", retrieved_at=NOW))
        s.add(PokemonMovepool(pokemon_species_id=3, move_id=5, source="x", retrieved_at=NOW))

        s.add(RegulationLegalMove(regulation_id="TEST", move_id=1, source="x", retrieved_at=NOW, verified=True))
        s.add(RegulationLegalMove(regulation_id="TEST", move_id=2, source="x", retrieved_at=NOW, verified=True))
        s.add(RegulationLegalMove(regulation_id="TEST", move_id=5, source="x", retrieved_at=NOW, verified=True))
        # move_id=3 (hydro-pump) intentionally NOT legal this regulation, despite being in blastoise's movepool

        s.add(RegulationLegalItem(regulation_id="TEST", item_id=1, source="x", retrieved_at=NOW, verified=True))
        # item_id=2 (leftovers) intentionally not legal this regulation

        s.commit()
        yield s


def _reg(session):
    return session.get(RegulationSet, "TEST")


def _valid_charizard():
    return TeamMember(species="charizard", item="life-orb", ability="blaze", nature="adamant", sp_spread={"attack": 32, "speed": 32, "hp": 2}, moves=["flamethrower"])


def _valid_blastoise(item=None):
    return TeamMember(species="blastoise", item=item, moves=["surf"])


def _codes(result):
    return {i.code for i in result.issues}


def test_valid_singles_team_passes(session):
    members = [_valid_charizard(), _valid_blastoise(), TeamMember(species="venusaur", moves=["razor-leaf"])]
    result = validate_team(session, _reg(session), "singles", members)
    assert result.valid is True
    assert result.issues == []


def test_team_size_too_small(session):
    result = validate_team(session, _reg(session), "singles", [_valid_charizard(), _valid_blastoise()])
    assert "team_size" in _codes(result)


def test_team_size_within_bounds_no_size_issue(session):
    members = [_valid_charizard(), _valid_blastoise(), TeamMember(species="blastoise", moves=["surf"])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "team_size" not in _codes(result)  # 3 members is within singles' 3-6 bound
    assert "duplicate_species" in _codes(result)  # but blastoise is repeated


def test_duplicate_species(session):
    members = [_valid_charizard(), TeamMember(species="charizard", moves=["flamethrower"]), _valid_blastoise()]
    result = validate_team(session, _reg(session), "singles", members)
    assert "duplicate_species" in _codes(result)


def test_duplicate_item(session):
    members = [_valid_charizard(), _valid_blastoise(item="life-orb"), TeamMember(species="pikachu", item="life-orb", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "duplicate_item" in _codes(result)


def test_illegal_species_not_in_roster(session):
    members = [_valid_charizard(), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "illegal_species" in _codes(result)


def test_unknown_species(session):
    members = [_valid_charizard(), _valid_blastoise(), TeamMember(species="mewtwo-doesnt-exist", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "unknown_species" in _codes(result)


def test_illegal_item(session):
    members = [_valid_charizard(), _valid_blastoise(item="leftovers"), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "illegal_item" in _codes(result)


def test_unknown_move(session):
    members = [_valid_charizard(), TeamMember(species="blastoise", moves=["hyper-beam-not-a-real-move"]), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "unknown_move" in _codes(result)


def test_move_not_in_movepool(session):
    # thunderbolt exists as a Move row but isn't in charizard's movepool
    members = [TeamMember(species="charizard", moves=["thunderbolt"]), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "move_not_in_movepool" in _codes(result)


def test_illegal_move_banned_this_regulation(session):
    # hydro-pump is in blastoise's movepool but not RegulationLegalMove for TEST
    members = [_valid_charizard(), TeamMember(species="blastoise", moves=["hydro-pump"]), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "illegal_move" in _codes(result)


def test_sp_over_stat_cap(session):
    members = [
        TeamMember(species="charizard", moves=["flamethrower"], sp_spread={"attack": SP_PER_STAT_CAP + 1}),
        _valid_blastoise(),
        TeamMember(species="pikachu", moves=[]),
    ]
    result = validate_team(session, _reg(session), "singles", members)
    assert "sp_over_stat_cap" in _codes(result)


def test_sp_over_total_cap(session):
    members = [
        TeamMember(species="charizard", moves=["flamethrower"], sp_spread={"attack": 30, "speed": 30, "hp": 10}),
        _valid_blastoise(),
        TeamMember(species="pikachu", moves=[]),
    ]
    result = validate_team(session, _reg(session), "singles", members)
    assert "sp_over_total_cap" in _codes(result)
    assert sum([30, 30, 10]) == SP_TOTAL_CAP + 4  # sanity: this fixture really does exceed the cap


def test_sp_negative(session):
    members = [TeamMember(species="charizard", moves=["flamethrower"], sp_spread={"attack": -5}), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "sp_negative" in _codes(result)


def test_unknown_stat_name(session):
    members = [TeamMember(species="charizard", moves=["flamethrower"], sp_spread={"defence": 10}), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "unknown_stat" in _codes(result)


def test_too_many_moves(session):
    members = [
        TeamMember(species="charizard", moves=["flamethrower", "flamethrower2", "flamethrower3", "flamethrower4", "flamethrower5"]),
        _valid_blastoise(),
        TeamMember(species="pikachu", moves=[]),
    ]
    result = validate_team(session, _reg(session), "singles", members)
    assert "too_many_moves" in _codes(result)


def test_duplicate_move_within_pokemon(session):
    members = [TeamMember(species="charizard", moves=["flamethrower", "flamethrower"]), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "duplicate_move" in _codes(result)


def test_no_moves(session):
    members = [TeamMember(species="charizard", moves=[]), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "no_moves" in _codes(result)


def test_unknown_ability(session):
    members = [TeamMember(species="charizard", moves=["flamethrower"], ability="totally-fake-ability"), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "unknown_ability" in _codes(result)


def test_unknown_nature(session):
    members = [TeamMember(species="charizard", moves=["flamethrower"], nature="totally-fake-nature"), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    result = validate_team(session, _reg(session), "singles", members)
    assert "unknown_nature" in _codes(result)


def test_unknown_format(session):
    result = validate_team(session, _reg(session), "triples", [_valid_charizard()])
    assert result.valid is False
    assert "unknown_format" in _codes(result)


def test_doubles_bounds_differ_from_singles(session):
    members = [_valid_charizard(), _valid_blastoise(), TeamMember(species="pikachu", moves=[])]
    singles_result = validate_team(session, _reg(session), "singles", members)
    doubles_result = validate_team(session, _reg(session), "doubles", members)
    assert "team_size" not in _codes(singles_result)  # 3 is valid for singles (3-6)
    assert "team_size" in _codes(doubles_result)  # 3 is too few for doubles (4-6)
