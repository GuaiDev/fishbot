"""Tests for DataStream water quality ingest — no live downloads (no API key held).

Query construction is verified against the DataStream public OpenAPI schema
and README (https://github.com/datastreamapp/api-docs) rather than a live
call. These tests lock in the confirmed-correct field names/filter syntax so
a future edit can't silently reintroduce the Id/ID, LatitudeE7, or
geo.intersects bugs found while reviewing this adapter.
"""

import httpx

from src.ingest.jurisdictions.ca_national import datastream_water_quality as ds


def test_no_api_key_returns_empty_list_with_warning(monkeypatch):
    monkeypatch.delenv("DATASTREAM_API_KEY", raising=False)
    assert ds.fetch_water_quality_readings(50.0, -97.0) == []


def test_no_api_key_does_not_make_http_request(monkeypatch):
    monkeypatch.delenv("DATASTREAM_API_KEY", raising=False)
    called = []
    monkeypatch.setattr(httpx, "get", lambda *a, **k: called.append(True))
    ds.fetch_water_quality_readings(50.0, -97.0)
    assert not called


def test_locations_query_uses_plain_numeric_range_filter(monkeypatch, tmp_path):
    """Not geo.intersects/geography'POLYGON(...)' — no evidence that syntax
    is supported; the documented bounding-box example is a plain range filter.
    """
    monkeypatch.setattr(ds, "_CACHE_DIR", tmp_path)
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers

        class FakeResp:
            status_code = 200
            text = ""

            def raise_for_status(self):
                pass

            def json(self):
                return {"value": []}

        return FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    ds._fetch_locations(50.0, -97.0, 50.0, "fake-key")

    assert captured["url"] == ds._LOCATIONS_URL
    filt = captured["params"]["$filter"]
    assert "geo.intersects" not in filt
    assert "geography" not in filt
    assert "Longitude gt" in filt and "Longitude lt" in filt
    assert "Latitude gt" in filt and "Latitude lt" in filt
    assert captured["headers"]["x-api-key"] == "fake-key"


def test_locations_select_uses_id_not_lowercase_id(monkeypatch, tmp_path):
    """Locations.ID (string station code) is the field that actually joins to
    Records.MonitoringLocationID — Locations.Id is a different field."""
    monkeypatch.setattr(ds, "_CACHE_DIR", tmp_path)
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["select"] = params["$select"]

        class FakeResp:
            status_code = 200
            text = ""

            def raise_for_status(self):
                pass

            def json(self):
                return {"value": []}

        return FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    ds._fetch_locations(50.0, -97.0, 50.0, "fake-key")

    fields = captured["select"].split(",")
    assert "ID" in fields
    assert "LatitudeE7" not in fields
    assert "LongitudeE7" not in fields
    assert "Latitude" in fields
    assert "Longitude" in fields


def test_parse_locations_uses_id_field_and_plain_lat_lng(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "_CACHE_DIR", tmp_path)

    def fake_get(url, params=None, headers=None, timeout=None):
        class FakeResp:
            status_code = 200
            text = ""

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "value": [
                        {
                            "Id": 99999,  # internal field — must NOT be used as station id
                            "ID": "ABC123",
                            "Name": "Sample Location A",
                            "Latitude": 51.01,
                            "Longitude": -97.14,
                        }
                    ]
                }

        return FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    stations = ds._fetch_locations(50.0, -97.0, 50.0, "fake-key")

    assert len(stations) == 1
    assert stations[0]["id"] == "ABC123"
    assert stations[0]["lat"] == 51.01
    assert stations[0]["lng"] == -97.14


def test_records_query_has_no_orderby(monkeypatch, tmp_path):
    """$orderby is commented out (not supported) in the API docs."""
    monkeypatch.setattr(ds, "_CACHE_DIR", tmp_path)
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params

        class FakeResp:
            status_code = 200
            text = ""

            def raise_for_status(self):
                pass

            def json(self):
                return {"value": []}

        return FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    ds._fetch_records("ABC123", "fake-key")

    assert "$orderby" not in captured["params"]
    assert captured["params"]["$filter"] == "MonitoringLocationID eq 'ABC123'"


def test_parse_records_matches_characteristic_name_case_insensitively():
    """Docs' own examples show inconsistent casing ("Temperature, water" vs
    a guessed "Temperature, Water") — matching must not be case-sensitive."""
    station = {"id": "ABC123", "name": "Test Station", "lat": 50.0, "lng": -97.0}
    raw = [
        {
            "ActivityStartDate": "2026-06-01",
            "CharacteristicName": "Temperature, Water",
            "ResultValue": 18.5,
        },
        {"ActivityStartDate": "2026-06-01", "CharacteristicName": "PH", "ResultValue": 7.2},
    ]
    rows = ds._parse_records(station, raw)
    assert len(rows) == 1
    assert rows[0]["temp_c"] == 18.5
    assert rows[0]["ph"] == 7.2


def test_parse_records_skips_dissolved_oxygen_saturation():
    station = {"id": "ABC123", "name": "Test Station", "lat": 50.0, "lng": -97.0}
    raw = [
        {
            "ActivityStartDate": "2026-06-01",
            "CharacteristicName": "Dissolved oxygen saturation",
            "ResultValue": 97,
        },
    ]
    rows = ds._parse_records(station, raw)
    assert len(rows) == 0


def test_parse_records_groups_by_station_and_date():
    station = {"id": "ABC123", "name": "Test Station", "lat": 50.0, "lng": -97.0}
    raw = [
        {"ActivityStartDate": "2026-06-01", "CharacteristicName": "pH", "ResultValue": 7.2},
        {
            "ActivityStartDate": "2026-06-01",
            "CharacteristicName": "Dissolved Oxygen",
            "ResultValue": 9.1,
        },
        {"ActivityStartDate": "2026-06-15", "CharacteristicName": "pH", "ResultValue": 7.4},
    ]
    rows = ds._parse_records(station, raw)
    assert len(rows) == 2
    by_date = {r["sampled_at"]: r for r in rows}
    assert by_date["2026-06-01"]["ph"] == 7.2
    assert by_date["2026-06-01"]["do_mgl"] == 9.1
    assert by_date["2026-06-15"]["ph"] == 7.4


def test_parse_records_jurisdiction_derived_from_coords():
    """Manitoba coordinates must not resolve to UNKNOWN (regression guard for
    the missing-bounding-box bug fixed in src/jurisdictions/geo.py)."""
    station = {"id": "ABC123", "name": "Winnipeg Station", "lat": 49.90, "lng": -97.14}
    raw = [{"ActivityStartDate": "2026-06-01", "CharacteristicName": "pH", "ResultValue": 7.2}]
    rows = ds._parse_records(station, raw)
    assert rows[0]["jurisdiction"] == "CA-MB"


def test_bbox_returns_expected_order():
    min_lon, min_lat, max_lon, max_lat = ds._bbox(50.0, -97.0, 50.0)
    assert min_lon < -97.0 < max_lon
    assert min_lat < 50.0 < max_lat
