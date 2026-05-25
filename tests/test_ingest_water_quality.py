"""Tests for PWQMN water quality ingest. No live downloads — uses fixture CSVs."""

import logging
import tempfile
from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from src.ingest.jurisdictions.ca_on import water_quality as wq_mod
from src.ingest.jurisdictions.ca_on.water_quality import parse_field_data
from src.models.water_quality_reading import WaterQualityReading

FIXTURE_FIELD = Path(__file__).parent / "fixtures" / "pwqmn_field_data_sample.csv"
FIXTURE_STATIONS = Path(__file__).parent / "fixtures" / "pwqmn_stations_sample.csv"


def _stations_from_fixture() -> dict:
    """Load station lookup from the test fixture (bypasses HTTP)."""
    import csv

    stations = {}
    with FIXTURE_STATIONS.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = row["STATION"].strip()
            name = row["NAME"].strip() or None
            lat = float(row["LATITUDE"]) if row["LATITUDE"].strip() else None
            lng = float(row["LONGITUDE"]) if row["LONGITUDE"].strip() else None
            stations[sid] = (name, lat, lng)
    return stations


def test_parse_fixture_record_count():
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    # 10 rows in fixture; row 9 has only turbidity (non-null) — still kept
    assert len(records) == 10


def test_sampled_at_parsed_correctly():
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    r = next(r for r in records if r.record_id == "2024_50001")
    assert r.sampled_at == date(2024, 6, 15)


def test_record_id_includes_year_and_field_id():
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    ids = {r.record_id for r in records}
    assert "2024_50001" in ids
    assert "2024_60004" in ids


def test_station_id_zero_padded():
    """10-digit station code '3007700702' should be padded to '03007700702'."""
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    r = next(r for r in records if r.record_id == "2024_50001")
    assert r.station_id == "03007700702"


def test_station_lookup_applied():
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    r = next(r for r in records if r.record_id == "2024_50001")
    assert r.station_name == "Aurora Creek"
    assert r.lat == pytest.approx(44.02220026)
    assert r.lng == pytest.approx(-79.47285473)


def test_11digit_station_not_padded():
    """11-digit station code '08002201602' should not be altered."""
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    r = next(r for r in records if r.record_id == "2024_50003")
    assert r.station_id == "08002201602"
    assert r.station_name == "Ausable River"


def test_null_parameters_parsed():
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    # record 50005: conductivity and turbidity are empty
    r = next(r for r in records if r.record_id == "2024_50005")
    assert r.conductivity_us_cm is None
    assert r.turbidity_fnu is None
    assert r.do_mgl == pytest.approx(2.8)


def test_jurisdiction_always_ca_on():
    stations = _stations_from_fixture()
    records = parse_field_data(FIXTURE_FIELD, stations)
    assert all(r.jurisdiction == "CA-ON" for r in records)


def test_ph_validator_rejects_out_of_range():
    with pytest.raises(ValidationError):
        WaterQualityReading(
            record_id="x",
            station_id="TEST",
            jurisdiction="CA-ON",
            sampled_at=date(2024, 1, 1),
            ph=15.0,
        )


def test_do_validator_rejects_negative():
    with pytest.raises(ValidationError):
        WaterQualityReading(
            record_id="x",
            station_id="TEST",
            jurisdiction="CA-ON",
            sampled_at=date(2024, 1, 1),
            do_mgl=-1.0,
        )


def test_temp_validator_rejects_out_of_range():
    with pytest.raises(ValidationError):
        WaterQualityReading(
            record_id="x",
            station_id="TEST",
            jurisdiction="CA-ON",
            sampled_at=date(2024, 1, 1),
            temp_c=50.0,
        )


def test_skip_row_with_all_null_params(caplog):
    """A row where every parameter is blank is skipped with a warning."""
    header = (
        "YEAR,Profile_Name,Lab_Workorder_ID,Field_ID,Lab_Sample_ID,"
        "Collection_Site,Collection_Date,Collection_Time,"
        "Specific_Conductance_uS_cm_1,Water_Temperature_C,"
        "Dissolved_Oxygen_mgl,Field_PH,Turb_FNU,Comments"
    )
    row = "2024,Test,99,99999,99001,3007700702,06/01/2024,09:00:00,,,,,,"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        tmp.write(header + "\n" + row + "\n")
        tmp_path = Path(tmp.name)

    stations = _stations_from_fixture()
    with caplog.at_level(logging.WARNING):
        records = parse_field_data(tmp_path, stations)

    assert len(records) == 0
    assert any("null" in msg.lower() or "skip" in msg.lower() for msg in caplog.messages)
    tmp_path.unlink()


def test_space_separated_schema_parsed():
    """Test the 2021-2022 schema with space-separated column names."""
    header = (
        "Year,Conservation Authority,Collection Site,Lab Workorder ID,"
        "Collection Date,Collection Time,Lab Sample ID,"
        "Specific Conductance uS cm 1,Water Temperature C,"
        "Dissolved Oxygen mgl,Field PH,Turb FNU,Field Data Remark"
    )
    row = (
        "2021, Ausable Bayfield,08002201602,1262,04/20/2021,"
        "8:00:00,1262001,542,8.6,10.26,9.48,6.94,"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        tmp.write(header + "\n" + row + "\n")
        tmp_path = Path(tmp.name)

    stations = _stations_from_fixture()
    records = parse_field_data(tmp_path, stations)
    tmp_path.unlink()

    assert len(records) == 1
    r = records[0]
    assert r.record_id == "2021_1262_1262001"
    assert r.station_id == "08002201602"
    assert r.sampled_at == date(2021, 4, 20)
    assert r.temp_c == pytest.approx(8.6)
    assert r.do_mgl == pytest.approx(10.26)


def test_download_stations_skips_if_fresh(tmp_path, monkeypatch):
    """Fresh stations file (< 30 days) should not trigger an HTTP download."""
    fresh_file = tmp_path / "pwqmn_stations.csv"
    fresh_file.write_text("placeholder")

    monkeypatch.setattr(wq_mod, "_STATIONS_PATH", fresh_file)

    called = []

    def fake_stream(*args, **kwargs):
        called.append(True)
        raise AssertionError("should not make HTTP request for fresh file")

    monkeypatch.setattr(httpx, "stream", fake_stream)

    result = wq_mod.download_stations()
    assert result == fresh_file
    assert not called
