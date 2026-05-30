"""Tests for OHN hydro network ingest module."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
_TEST_CACHE_DIR = Path(__file__).parent.parent / "data" / "cache" / "test_tmp"
_HYDRO_HTTPX = "src.ingest.jurisdictions.ca_on.hydro_network.httpx.get"
_HYDRO_CACHE = "src.ingest.jurisdictions.ca_on.hydro_network._CACHE_DIR"


@pytest.fixture
def cache_dir():
    shutil.rmtree(_TEST_CACHE_DIR, ignore_errors=True)
    _TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yield _TEST_CACHE_DIR
    shutil.rmtree(_TEST_CACHE_DIR, ignore_errors=True)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _mock_response(data: dict) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


def _paged_side_effect(first_data: dict) -> list:
    """First HTTP call returns first_data; second returns empty to stop pagination."""
    return [_mock_response(first_data), _mock_response({"features": []})]


# ── watercourse fetching ──────────────────────────────────────────────────────


def test_fetch_watercourses_returns_all_segments(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    assert len(segments) == 4


def test_named_segment_parsed_correctly(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    named = [s for s in segments if s.name == "Bronte Creek"]
    assert len(named) == 2
    for s in named:
        assert s.flow_verified is True
        assert s.permanency == "Permanent"
        assert s.length_m == 2500.0
        assert s.jurisdiction == "CA-ON"


def test_unnamed_segment_has_none_name(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    unnamed = [s for s in segments if s.name is None]
    assert len(unnamed) == 2


def test_unverified_flow_segment(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    unverified = [s for s in segments if not s.flow_verified]
    assert len(unverified) == 1
    assert unverified[0].ogf_id == 10004


def test_start_end_nodes_rounded_to_5_decimal_places(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    # Seg1: start=(-79.5, 43.5), end=(-79.48, 43.51)
    seg1 = next(s for s in segments if s.ogf_id == 10001)
    assert seg1.start_node == "-79.5,43.5"
    assert seg1.end_node == "-79.48,43.51"


def test_geom_wkt_is_linestring(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    for seg in segments:
        assert seg.geom_wkt.startswith("LINESTRING")


def test_empty_response_returns_empty_list(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    empty = {"features": [], "exceededTransferLimit": False}
    with patch(_HYDRO_HTTPX, return_value=_mock_response(empty)), patch(_HYDRO_CACHE, cache_dir):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    assert segments == []


# ── barrier fetching ──────────────────────────────────────────────────────────


def test_fetch_barriers_returns_both_barriers(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_barriers

    fixture = _load_fixture("ohn_barriers_response.json")
    with patch(_HYDRO_HTTPX, return_value=_mock_response(fixture)), patch(_HYDRO_CACHE, cache_dir):
        barriers = fetch_barriers(43.5, -79.48, radius_km=10)

    assert len(barriers) == 2


def test_falls_barrier_parsed(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_barriers

    fixture = _load_fixture("ohn_barriers_response.json")
    with patch(_HYDRO_HTTPX, return_value=_mock_response(fixture)), patch(_HYDRO_CACHE, cache_dir):
        barriers = fetch_barriers(43.5, -79.48, radius_km=10)

    falls = next(b for b in barriers if b.barrier_type == "Falls")
    assert falls.ogf_id == 20001
    assert falls.geom_wkt.startswith("POINT")


def test_sea_lamprey_barrier_parsed(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_barriers

    fixture = _load_fixture("ohn_barriers_response.json")
    with patch(_HYDRO_HTTPX, return_value=_mock_response(fixture)), patch(_HYDRO_CACHE, cache_dir):
        barriers = fetch_barriers(43.5, -79.48, radius_km=10)

    slb = next(b for b in barriers if b.barrier_type == "Sea Lamprey Barrier")
    assert slb.ogf_id == 20002


def test_barrier_snaps_to_nearest_segment(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_barriers, fetch_watercourses

    wc_fixture = _load_fixture("ohn_watercourse_response.json")
    b_fixture = _load_fixture("ohn_barriers_response.json")

    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(wc_fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    with (
        patch(_HYDRO_HTTPX, return_value=_mock_response(b_fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        barriers = fetch_barriers(43.5, -79.48, radius_km=10, segments=segments)

    # Falls barrier at (-79.475, 43.5075) lies exactly on Seg3 (OGF_ID 10003)
    falls = next(b for b in barriers if b.barrier_type == "Falls")
    assert falls.nearest_segment_ogf_id == 10003
    assert falls.snap_distance_m is not None
    assert falls.snap_distance_m < 10.0  # essentially on the line

    # Sea Lamprey Barrier at (-79.47, 43.515) lies on Seg2 (OGF_ID 10002)
    slb = next(b for b in barriers if b.barrier_type == "Sea Lamprey Barrier")
    assert slb.nearest_segment_ogf_id == 10002


# ── geometry simplification ───────────────────────────────────────────────────


def test_segment_not_simplified_within_75km(cache_dir):
    """Segment close to home keeps LINESTRING WKT."""
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, side_effect=_paged_side_effect(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        # Home at 43.5, -79.48 — fixture segments are <2km away
        segments = fetch_watercourses(43.5, -79.48, radius_km=10)

    for seg in segments:
        assert seg.geom_wkt.startswith("LINESTRING"), (
            f"Segment {seg.ogf_id} should be LINESTRING when <75km from home"
        )


def test_segment_simplified_beyond_75km(cache_dir):
    """Segment far from home is stored as POINT (centroid) WKT."""
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    # Grid tiling makes many HTTP calls (one per sub-tile); use return_value so
    # any number of calls succeeds. OGF_IDs deduplicate across tiles, giving 4 segments.
    with (
        patch(_HYDRO_HTTPX, return_value=_mock_response(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        # Home in eastern Ontario (~450km from fixture segments near Toronto)
        segments = fetch_watercourses(46.5, -76.0, radius_km=500)

    assert len(segments) > 0
    for seg in segments:
        assert seg.geom_wkt.startswith("POINT"), (
            f"Segment {seg.ogf_id} should be simplified to POINT when >75km from home"
        )
        # start_node and end_node must still be set (topology preserved)
        assert seg.start_node
        assert seg.end_node


# ── tiled pagination ──────────────────────────────────────────────────────────


def test_tiling_triggered_on_exact_page_size(cache_dir):
    """When a tile returns exactly _PAGE_SIZE records, bbox is split into quadrants."""
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    # fixture has 4 features; patch _PAGE_SIZE to 4 so first page triggers tiling
    empty_response = _mock_response({"features": []})

    call_log: list[int] = []

    def counting_side_effect(*args, **kwargs):
        call_log.append(1)
        if len(call_log) == 1:
            return _mock_response(fixture)  # first call: full page (triggers tiling)
        return empty_response  # all subsequent calls: empty

    with (
        patch(_HYDRO_HTTPX, side_effect=counting_side_effect),
        patch(_HYDRO_CACHE, cache_dir),
        patch("src.ingest.jurisdictions.ca_on.hydro_network._PAGE_SIZE", 4),
    ):
        fetch_watercourses(43.5, -79.48, radius_km=10)

    # Without tiling: 2 calls (page 0 = 4 features, page 4 = empty).
    # With tiling triggered: 4 additional quadrant calls → total ≥ 6.
    assert len(call_log) >= 6, (
        f"Expected ≥6 HTTP calls when tiling is triggered, got {len(call_log)}"
    )


# ── caching ───────────────────────────────────────────────────────────────────


def test_cache_hit_skips_http(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    # Fixture has 4 features << _PAGE_SIZE, so pagination stops after 1 HTTP call.
    # The second fetch is a cache hit — no further HTTP calls.
    with (
        patch(_HYDRO_HTTPX, return_value=_mock_response(fixture)) as mock_get,
        patch(_HYDRO_CACHE, cache_dir),
    ):
        fetch_watercourses(43.5, -79.48, radius_km=10)
        fetch_watercourses(43.5, -79.48, radius_km=10)

    assert mock_get.call_count == 1


def test_cache_miss_writes_file(cache_dir):
    from src.ingest.jurisdictions.ca_on.hydro_network import fetch_watercourses

    fixture = _load_fixture("ohn_watercourse_response.json")
    with (
        patch(_HYDRO_HTTPX, return_value=_mock_response(fixture)),
        patch(_HYDRO_CACHE, cache_dir),
    ):
        fetch_watercourses(43.5, -79.48, radius_km=10)

    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1
