"""Regression test for ingest_ab_stocking against the real DB schema.

Guards against the ingested_at bug: ab_ingest.py used to set r["ingested_at"]
before upserting into stocking_records, which has no such column and raised
sqlite3.OperationalError the moment this path was actually exercised (it
never had been, until this adapter was tested live).
"""

from sqlite_utils import Database

from src.storage.database import ensure_schema


def _make_db(tmp_path) -> Database:
    db = Database(tmp_path / "test.db")
    ensure_schema(db)
    return db


def test_ingest_ab_stocking_does_not_crash_on_real_schema(tmp_path, monkeypatch):
    from src.services import ab_ingest

    db = _make_db(tmp_path)
    monkeypatch.setattr(ab_ingest, "get_db", lambda: db)

    fake_rows = [
        {
            "record_id": "AB_2026_1",
            "waterbody_name": "Test Lake",
            "waterbody_code": None,
            "municipality": "Calgary",
            "county": None,
            "lat": 51.05,
            "lng": -114.07,
            "jurisdiction": "CA-AB",
            "species": "Rainbow Trout",
            "species_code": "RNTR",
            "year": 2026,
            "month": None,
            "quantity": 1000,
            "life_stage": "15cm 3N",
            "stocking_purpose": "before June 15th",
            "stocked_at": None,
        }
    ]
    monkeypatch.setattr(
        "src.ingest.jurisdictions.ca_ab.stocking.fetch_stocking_records",
        lambda: fake_rows,
    )

    n = ab_ingest.ingest_ab_stocking()

    assert n == 1
    stored = list(db["stocking_records"].rows)
    assert len(stored) == 1
    assert stored[0]["jurisdiction"] == "CA-AB"
