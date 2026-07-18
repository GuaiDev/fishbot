"""Tests for the /fishdex aggregation service."""

import pytest

from src.models.species_range import SpeciesRange
from src.services.fishdex import get_fishdex_data
from src.storage.catches import insert_catch, update_personal_best_if_higher
from src.storage.database import get_db
from src.storage.species_ranges import upsert_species_ranges


def _session_and_stop(db, user_id=1):
    session_id = db["sessions"].insert({"date": "2026-06-01"}).last_pk
    stop_id = db["stops"].insert({
        "session_id": session_id,
        "location_text": "Bronte Creek",
        "species_caught": "[]",
    }).last_pk
    return session_id, stop_id


def test_no_catches_returns_empty_caught_species(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    data = get_fishdex_data(db, user_id=1, jurisdiction="CA-ON")
    assert data["caughtSpecies"] == []


def test_caught_species_aggregates_count_and_family(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)

    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="creek chub")
    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="creek chub")
    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="rock bass",
                 photo_url="/photos/rockbass.jpg")

    data = get_fishdex_data(db, user_id=1, jurisdiction="CA-ON")
    by_name = {c["commonName"]: c for c in data["caughtSpecies"]}

    assert by_name["Creek Chub"]["count"] == 2
    assert by_name["Creek Chub"]["family"] == "Cyprinidae"
    assert by_name["Creek Chub"]["isNewFind"] is False  # caught twice

    assert by_name["Rock Bass"]["count"] == 1
    assert by_name["Rock Bass"]["family"] == "Centrarchidae"
    assert by_name["Rock Bass"]["isNewFind"] is True  # caught once
    assert by_name["Rock Bass"]["representativePhotoUrl"] == "/photos/rockbass.jpg"


def test_catch_with_no_photo_has_none_representative_photo(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)
    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="smallmouth bass")

    data = get_fishdex_data(db, user_id=1, jurisdiction="CA-ON")
    assert data["caughtSpecies"][0]["representativePhotoUrl"] is None


def test_no_size_data_never_fabricates_personal_best(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)
    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="smallmouth bass")

    data = get_fishdex_data(db, user_id=1, jurisdiction="CA-ON")
    catch = data["caughtSpecies"][0]
    assert catch["isPersonalBest"] is False
    assert catch["maxLengthInches"] is None


def test_personal_best_from_stored_table_reported_in_inches(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)
    catch_id = insert_catch(
        db, stop_id=stop_id, session_id=session_id, user_id=1, species="smallmouth bass",
        biggest_size_cm=35.56,
    )
    update_personal_best_if_higher(
        db, user_id=1, species="smallmouth bass", size_cm=35.56, catch_id=catch_id
    )

    data = get_fishdex_data(db, user_id=1, jurisdiction="CA-ON")
    catch = data["caughtSpecies"][0]
    assert catch["isPersonalBest"] is True
    assert catch["maxLengthInches"] == pytest.approx(14.0, abs=0.01)


def test_region_pool_filters_by_jurisdiction_and_carries_family(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    upsert_species_ranges(db, [
        SpeciesRange(
            species="Smallmouth Bass", scientific_name="Micropterus dolomieu",
            native_to_ontario=True, native_to_great_lakes=True,
            general_range="Ontario", jurisdictions_present=["CA-ON"],
        ),
        SpeciesRange(
            species="Some BC Fish", scientific_name="Nonexistent fishium",
            native_to_ontario=False, native_to_great_lakes=False,
            general_range="BC", jurisdictions_present=["CA-BC"],
        ),
    ])

    data = get_fishdex_data(db, user_id=1, jurisdiction="CA-ON")
    pool_names = {s["commonName"] for s in data["regionSpeciesPool"]}
    assert "Smallmouth Bass" in pool_names
    assert "Some BC Fish" not in pool_names

    bass = next(s for s in data["regionSpeciesPool"] if s["commonName"] == "Smallmouth Bass")
    assert bass["family"] == "Centrarchidae"
    assert bass["familyCommonName"] == "Bass & Sunfish"


def test_caught_species_uses_canonical_capitalization_from_pool(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    upsert_species_ranges(db, [
        SpeciesRange(
            species="Smallmouth Bass", scientific_name="Micropterus dolomieu",
            native_to_ontario=True, native_to_great_lakes=True,
            general_range="Ontario", jurisdictions_present=["CA-ON"],
        ),
    ])
    session_id, stop_id = _session_and_stop(db)
    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="smallmouth bass")

    data = get_fishdex_data(db, user_id=1, jurisdiction="CA-ON")
    assert data["caughtSpecies"][0]["commonName"] == "Smallmouth Bass"
