"""Tests for Ontario MRD 128 surficial geology ingest. No live downloads."""

from pathlib import Path

import pytest

from src.ingest.jurisdictions.ca_on.geology import _classify_substrate, _parse_tile
from src.models.geology_unit import GeologyUnit

FIXTURE = Path(__file__).parent / "fixtures" / "mrd128_tile_sample.kmz"
_TILE_ID = "-83.5_42_-83_42.5"


# --- Unit: substrate classification ---


def test_classify_substrate_coarse_7():
    assert _classify_substrate("7") == "coarse"


def test_classify_substrate_coarse_6a():
    assert _classify_substrate("6a") == "coarse"


def test_classify_substrate_coarse_9c():
    assert _classify_substrate("9c") == "coarse"


def test_classify_substrate_fine_8a():
    assert _classify_substrate("8a") == "fine"


def test_classify_substrate_fine_8b():
    assert _classify_substrate("8b") == "fine"


def test_classify_substrate_bedrock_1():
    assert _classify_substrate("1") == "bedrock"


def test_classify_substrate_bedrock_3():
    assert _classify_substrate("3") == "bedrock"


def test_classify_substrate_organic_20():
    assert _classify_substrate("20") == "organic"


def test_classify_substrate_skip_manmade():
    assert _classify_substrate("21") is None


def test_classify_substrate_mixed_5d():
    assert _classify_substrate("5d") == "mixed"


def test_classify_substrate_unknown_defaults_mixed():
    assert _classify_substrate("99") == "mixed"


# --- Integration: fixture tile parsing ---


@pytest.fixture(scope="module")
def parsed_units() -> list[GeologyUnit]:
    assert FIXTURE.exists(), f"Fixture missing: {FIXTURE}"
    return _parse_tile(FIXTURE, _TILE_ID)


def test_parse_tile_returns_units(parsed_units):
    assert len(parsed_units) > 0


def test_parse_tile_unit_codes(parsed_units):
    codes = {u.unit_code for u in parsed_units}
    # Expected codes from this tile (21 is skipped)
    assert "8a" in codes
    assert "9c" in codes
    assert "20" in codes
    assert "5d" in codes
    # Man-made (21) must be excluded
    assert "21" not in codes


def test_parse_tile_centroids_present(parsed_units):
    for u in parsed_units:
        assert u.centroid_lat != 0.0
        assert u.centroid_lng != 0.0


def test_parse_tile_centroids_in_tile_bbox(parsed_units):
    # All centroids should be within the tile's geographic extent (SW Ontario)
    for u in parsed_units:
        assert 40.0 <= u.centroid_lat <= 46.0
        assert -86.0 <= u.centroid_lng <= -75.0


def test_parse_tile_bbox_valid(parsed_units):
    for u in parsed_units:
        assert u.bbox_minx < u.bbox_maxx, f"bbox_minx >= bbox_maxx for {u.unit_id}"
        assert u.bbox_miny < u.bbox_maxy, f"bbox_miny >= bbox_maxy for {u.unit_id}"


def test_parse_tile_substrate_classes_valid(parsed_units):
    valid = {"coarse", "fine", "bedrock", "organic", "mixed"}
    for u in parsed_units:
        assert u.substrate_class in valid, f"Unexpected class {u.substrate_class!r}"


def test_parse_tile_jurisdiction(parsed_units):
    for u in parsed_units:
        assert u.jurisdiction == "CA-ON"


def test_parse_tile_tile_id(parsed_units):
    for u in parsed_units:
        assert u.tile_id == _TILE_ID


# --- Unit: GeologyUnit model ---


def test_geology_unit_model_valid():
    u = GeologyUnit(
        unit_id="test_0000",
        tile_id="test",
        unit_code="7",
        unit_name="Glaciofluvial deposits",
        substrate_class="coarse",
        centroid_lat=43.5,
        centroid_lng=-79.5,
        bbox_minx=-79.6,
        bbox_miny=43.4,
        bbox_maxx=-79.4,
        bbox_maxy=43.6,
    )
    assert u.jurisdiction == "CA-ON"
    assert u.substrate_class == "coarse"


def test_geology_unit_optional_material():
    u = GeologyUnit(
        unit_id="test_0001",
        tile_id="test",
        unit_code="8a",
        unit_name="Fine-textured glaciolacustrine deposits",
        primary_material=None,
        substrate_class="fine",
        centroid_lat=43.5,
        centroid_lng=-79.5,
        bbox_minx=-79.6,
        bbox_miny=43.4,
        bbox_maxx=-79.4,
        bbox_maxy=43.6,
    )
    assert u.primary_material is None
