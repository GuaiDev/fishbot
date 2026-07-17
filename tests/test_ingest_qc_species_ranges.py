"""Tests for QC MELCCFP species ranges ingest — no live downloads.

Covers the bugs found testing this adapter live for the first time:
- wrong GeoJSON property names (NOM_COMMUN_FR/NOM_SCIENTIFIQUE don't exist;
  real fields are NOM_FRANCA/NOM_ANGLA/NOM_SCIENT) caused every row to be
  silently skipped (0 records extracted from a real 118-feature file).
- the source CRS is EPSG:32198 (NAD83 / Quebec Lambert), a projected metre
  CRS, not WGS84 — centroids must be reprojected or they look like
  coordinates but are nonsense (390200, -812965).
- MultiPolygon coordinates are nested one level deeper than Polygon; reusing
  the Polygon indexing path corrupts the centroid instead of raising.
"""

from src.ingest.jurisdictions.ca_qc.species_ranges import (
    _build_transformer,
    _centroid,
    _parse_geojson,
)

_POLYGON_FEATURE = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[-766586.65, 386001.66], [-769377.87, 389668.90], [-772255.50, 393175.64]]
        ],
    },
    "properties": {
        "NOM_FRANCA": "achigan à grande bouche",
        "NOM_ANGLA": "Largemouth Bass",
        "NOM_SCIENT": "Micropterus salmoides",
        "FAMILLE": "Centrarchidae",
    },
}

_MULTIPOLYGON_FEATURE = {
    "type": "Feature",
    "geometry": {
        "type": "MultiPolygon",
        "coordinates": [
            [[[-766586.65, 386001.66], [-769377.87, 389668.90], [-772255.50, 393175.64]]],
            [[[-700000.0, 400000.0], [-701000.0, 401000.0], [-702000.0, 402000.0]]],
        ],
    },
    "properties": {
        "NOM_FRANCA": "doré jaune",
        "NOM_ANGLA": "Walleye",
        "NOM_SCIENT": "Sander vitreus",
        "FAMILLE": "Percidae",
    },
}

_SAMPLE_DATA = {
    "type": "FeatureCollection",
    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32198"}},
    "features": [_POLYGON_FEATURE, _MULTIPOLYGON_FEATURE],
}


def test_parse_extracts_all_features():
    rows = _parse_geojson(_SAMPLE_DATA)
    assert len(rows) == 2


def test_parse_uses_english_common_name():
    rows = {r["scientific_name"]: r for r in _parse_geojson(_SAMPLE_DATA)}
    assert rows["Micropterus salmoides"]["species"] == "Largemouth Bass"
    assert rows["Sander vitreus"]["species"] == "Walleye"


def test_parse_no_fabricated_cosewic_status():
    """This GeoJSON has no conservation-status field at all — must be None,
    not a fabricated/guessed value."""
    rows = _parse_geojson(_SAMPLE_DATA)
    assert all(r["sara_status"] is None and r["cosewic_status"] is None for r in rows)


def test_parse_family_captured_in_habitat_notes():
    rows = {r["scientific_name"]: r for r in _parse_geojson(_SAMPLE_DATA)}
    assert "Centrarchidae" in rows["Micropterus salmoides"]["habitat_notes"]


def test_centroid_reprojects_to_plausible_quebec_coordinates():
    rows = _parse_geojson(_SAMPLE_DATA)
    for r in rows:
        # "Quebec — centroid (lat, lng)"
        import re

        m = re.search(r"\(([-\d.]+), ([-\d.]+)\)", r["general_range"])
        assert m is not None
        lat, lng = float(m.group(1)), float(m.group(2))
        assert 44 <= lat <= 63
        assert -80 <= lng <= -55


def test_multipolygon_centroid_does_not_crash_or_corrupt():
    """A pre-fix version indexed MultiPolygon the same way as Polygon, taking
    a ring's worth of coordinate pairs as if each were a single point."""
    to_wgs84 = _build_transformer(_SAMPLE_DATA)
    lat, lng = _centroid(_MULTIPOLYGON_FEATURE["geometry"], to_wgs84)
    assert lat is not None and lng is not None
    assert 44 <= lat <= 63
    assert -80 <= lng <= -55


def test_build_transformer_returns_none_for_wgs84():
    data = {"crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::4326"}}}
    assert _build_transformer(data) is None


def test_build_transformer_returns_none_when_no_crs_declared():
    # GeoJSON spec default is WGS84 when crs is absent.
    assert _build_transformer({}) is None


def test_parse_skips_duplicate_species():
    data = {
        "type": "FeatureCollection",
        "crs": _SAMPLE_DATA["crs"],
        "features": [_POLYGON_FEATURE, _POLYGON_FEATURE],
    }
    rows = _parse_geojson(data)
    assert len(rows) == 1


def test_parse_empty_features_returns_empty_list():
    assert _parse_geojson({"features": []}) == []
