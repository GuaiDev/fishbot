"""Tests for eBird piscivore ingest. No live API calls."""

import importlib
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "ebird_response.json"

# Load the ingest module via importlib (src/ingest/global/ can't be imported normally)
_ebird = importlib.import_module("src.ingest.global.ebird")
_parse_response = _ebird._parse_response
_cache_key = _ebird._cache_key
fetch_piscivore_observations = _ebird.fetch_piscivore_observations


# --- Fixture loading ---


@pytest.fixture()
def fixture_data() -> list[dict]:
    return json.loads(FIXTURE.read_text())


# --- Parsing ---


def test_parse_response_returns_three_observations(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    assert len(obs) == 3


def test_parse_response_obs_ids_unique(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    ids = [o.obs_id for o in obs]
    assert len(ids) == len(set(ids))


def test_parse_response_obs_id_composite(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    for o in obs:
        assert "_" in o.obs_id
        assert o.species_code in o.obs_id


def test_parse_response_null_howmany_accepted(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    null_obs = [o for o in obs if o.how_many is None]
    assert len(null_obs) == 1  # third fixture record has null howMany


def test_parse_response_howmany_parsed(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    counted = [o for o in obs if o.how_many is not None]
    assert any(o.how_many == 2 for o in counted)
    assert any(o.how_many == 1 for o in counted)


def test_parse_response_significance_populated(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    for o in obs:
        assert o.piscivore_significance
        assert "fish" in o.piscivore_significance.lower()


def test_parse_response_grbher3_significance(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    assert all("shallow" in o.piscivore_significance.lower() for o in obs)


def test_parse_response_dates_parsed(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    for o in obs:
        assert isinstance(o.observed_on, date)


def test_parse_response_coords(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    for o in obs:
        assert 40.0 <= o.lat <= 50.0
        assert -85.0 <= o.lng <= -70.0


def test_parse_response_location_name(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    names = {o.location_name for o in obs}
    assert "Toronto Harbour" in names
    assert "Humber River at Old Mill" in names


def test_parse_response_private_location_has_name(fixture_data):
    obs = _parse_response(fixture_data, "grbher3")
    private = [o for o in obs if o.location_name == "Personal Location"]
    assert len(private) == 1


# --- Missing API key ---


def test_missing_api_key_returns_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("EBIRD_API_KEY", raising=False)
    result = fetch_piscivore_observations(43.7, -79.4)
    assert result == []


def test_empty_api_key_returns_empty(monkeypatch):
    monkeypatch.setenv("EBIRD_API_KEY", "")
    result = fetch_piscivore_observations(43.7, -79.4)
    assert result == []


# --- Cache ---


def test_cache_key_deterministic():
    k1 = _cache_key("grbher3", 43.7, -79.4, 50, 30, "2026-05-25")
    k2 = _cache_key("grbher3", 43.7, -79.4, 50, 30, "2026-05-25")
    assert k1 == k2


def test_cache_key_differs_by_species():
    k1 = _cache_key("grbher3", 43.7, -79.4, 50, 30, "2026-05-25")
    k2 = _cache_key("osprey1", 43.7, -79.4, 50, 30, "2026-05-25")
    assert k1 != k2


def test_cache_key_differs_by_date():
    k1 = _cache_key("grbher3", 43.7, -79.4, 50, 30, "2026-05-25")
    k2 = _cache_key("grbher3", 43.7, -79.4, 50, 30, "2026-05-24")
    assert k1 != k2


def test_cache_hit_skips_http(tmp_path, monkeypatch, fixture_data):
    """A warm cache should not trigger any HTTP call."""
    monkeypatch.setenv("EBIRD_API_KEY", "test_key_xyz")
    monkeypatch.setattr(_ebird, "_CACHE_DIR", tmp_path / "ebird_cache")
    cache_dir = tmp_path / "ebird_cache"
    cache_dir.mkdir()

    today = date.today().isoformat()
    key = _cache_key("grbher3", 43.7, -79.4, 50, 30, today)
    cache_file = cache_dir / f"{key}.json"
    cache_file.write_text(json.dumps(fixture_data))
    # Touch to ensure it's fresh (mtime = now)
    cache_file.touch()

    with patch("httpx.get") as mock_get:
        # Only grbher3 will hit cache; the other 4 will fail.
        # Patch them to raise to avoid real network — we only test that grbher3 skips HTTP.
        mock_get.side_effect = Exception("Should not call HTTP for cached species")

        # Patch the remaining 4 species to return empty list quickly
        original_cached_get = _ebird._cached_get

        def patched_cached_get(api_key, species_code, lat, lng, dist, back, today_str):
            if species_code == "grbher3":
                return original_cached_get(api_key, species_code, lat, lng, dist, back, today_str)
            return []  # Return empty for non-cached species

        monkeypatch.setattr(_ebird, "_cached_get", patched_cached_get)

        result = fetch_piscivore_observations(43.7, -79.4, radius_km=50, days_back=30)

    # Should have got 3 grbher3 observations from cache
    grbher = [o for o in result if o.species_code == "grbher3"]
    assert len(grbher) == 3
    mock_get.assert_not_called()


# --- Significance mapping completeness ---


def test_all_species_have_significance():
    for code in _ebird.PISCIVORE_CODES:
        sig = _ebird._SIGNIFICANCE.get(code)
        assert sig, f"No significance entry for {code}"
        assert "fish" in sig.lower(), f"Significance for {code} doesn't mention fish"
