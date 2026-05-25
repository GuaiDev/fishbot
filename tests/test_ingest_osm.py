"""Tests for OSM Overpass ingest module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _make_mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


# ── water features ────────────────────────────────────────────────────────────


def test_fetch_water_features_returns_all_three(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    assert len(features) == 3


def test_named_lake_parsed_correctly(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    lake = next(f for f in features if f.name == "Heart Lake")
    assert lake.feature_type == "lake"
    assert lake.osm_id == "node/1234567890"
    assert lake.lat == pytest.approx(43.7220)
    assert lake.lng == pytest.approx(-79.4800)


def test_river_centroid_from_way_geometry(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    river = next(f for f in features if f.name == "Humber River")
    assert river.feature_type == "river"
    assert river.osm_id == "way/2345678901"
    # average of 5 geometry points: lats 43.75/43.748/43.746/43.744/43.742 → 43.746
    assert river.lat == pytest.approx(43.7460, abs=0.0001)
    assert river.lng == pytest.approx(-79.5700, abs=0.0001)


def test_unnamed_pond_included_with_no_name(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    pond = next(f for f in features if f.feature_type == "pond")
    assert pond.name is None
    assert pond.osm_id == "way/3456789012"


def test_area_m2_computed_for_closed_polygon(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    pond = next(f for f in features if f.feature_type == "pond")
    assert pond.area_m2 is not None
    assert pond.area_m2 > 0


def test_area_m2_none_for_river_line(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    river = next(f for f in features if f.name == "Humber River")
    assert river.area_m2 is None


def test_area_m2_none_for_node(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    lake = next(f for f in features if f.name == "Heart Lake")
    assert lake.area_m2 is None


def test_osm_id_format(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    ids = {f.osm_id for f in features}
    assert "node/1234567890" in ids
    assert "way/2345678901" in ids
    assert "way/3456789012" in ids


def test_empty_response_returns_empty_list(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")

    with (
        patch("httpx.post", return_value=_make_mock_response({"elements": []})),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        features = osm.fetch_water_features(43.65, -79.38)

    assert features == []


# ── access points ─────────────────────────────────────────────────────────────


def test_fetch_access_points_returns_all_three(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_access.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        points = osm.fetch_access_points(43.65, -79.38)

    assert len(points) == 3


def test_boat_ramp_mapped_to_boat_launch(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_access.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        points = osm.fetch_access_points(43.65, -79.38)

    ramp = next(p for p in points if p.access_type == "boat_launch")
    assert ramp.name == "Etobicoke Creek Boat Launch"
    assert ramp.osm_id == "node/4567890123"


def test_fishing_spot_mapped_correctly(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_access.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        points = osm.fetch_access_points(43.65, -79.38)

    fishing = next(p for p in points if p.access_type == "fishing_spot")
    assert fishing.name == "Humber River Fishing Access"
    assert fishing.osm_id == "node/5678901234"


def test_park_centroid_from_way_geometry(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_access.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        points = osm.fetch_access_points(43.65, -79.38)

    park = next(p for p in points if p.access_type == "park")
    assert park.name == "Etienne Brule Park"
    assert park.osm_id == "way/6789012345"
    # average of 5 polygon vertices (last == first)
    assert park.lat == pytest.approx(43.6958, abs=0.0001)
    assert park.lng == pytest.approx(-79.4738, abs=0.0001)


# ── caching ───────────────────────────────────────────────────────────────────


def test_cache_hit_skips_http(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)) as mock_post,
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        osm.fetch_water_features(43.65, -79.38)
        osm.fetch_water_features(43.65, -79.38)  # second call → cache hit

    assert mock_post.call_count == 1


def test_cache_miss_writes_file(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_water.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)),
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        osm.fetch_water_features(43.65, -79.38)

    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1


def test_access_cache_hit_skips_http(tmp_path):
    import importlib

    osm = importlib.import_module("src.ingest.global.osm")
    fixture = _load_fixture("osm_access.json")

    with (
        patch("httpx.post", return_value=_make_mock_response(fixture)) as mock_post,
        patch("time.sleep"),
        patch.object(osm, "_CACHE_DIR", tmp_path),
    ):
        osm.fetch_access_points(43.65, -79.38)
        osm.fetch_access_points(43.65, -79.38)

    assert mock_post.call_count == 1
