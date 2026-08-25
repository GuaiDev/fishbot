"""Tests for the iNaturalist ingest module. No real API calls — uses a fixture."""

import importlib
import json
import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# "global" is a Python keyword — use importlib to reach the module
_inat = importlib.import_module("src.ingest.global.inaturalist")
fetch_observations = _inat.fetch_observations
_cached_get = _inat._cached_get


FIXTURE = Path(__file__).parent / "fixtures" / "inaturalist_response.json"


def _fixture_data() -> dict:
    return json.loads(FIXTURE.read_text())


def _mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


@pytest.fixture()
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache" / "inaturalist"


def test_fetch_returns_observations(tmp_path: Path):
    cache = tmp_path / "cache" / "inaturalist"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.inaturalist._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        observations = fetch_observations(lat=43.65, lng=-79.38, radius_km=50, days_back=90)

    assert len(observations) == 2
    species = {o.species for o in observations}
    assert "Cottus cognatus" in species
    assert "Etheostoma caeruleum" in species


def test_geoprivacy_fields_parsed(tmp_path: Path):
    cache = tmp_path / "cache" / "inaturalist"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.inaturalist._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        observations = fetch_observations(lat=43.65, lng=-79.38, radius_km=50, days_back=90)

    by_species = {o.species: o for o in observations}
    open_obs = by_species["Cottus cognatus"]
    assert open_obs.geoprivacy == "open"
    assert open_obs.is_obscured is False
    assert open_obs.obscuration_radius_km is None

    obscured_obs = by_species["Etheostoma caeruleum"]
    assert obscured_obs.geoprivacy == "obscured"
    assert obscured_obs.is_obscured is True
    assert obscured_obs.obscuration_radius_km == 22.0


def test_jurisdiction_tagged_correctly(tmp_path: Path):
    cache = tmp_path / "cache" / "inaturalist"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.inaturalist._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        observations = fetch_observations(lat=43.65, lng=-79.38, radius_km=50, days_back=90)

    by_species = {o.species: o for o in observations}
    # Ontario observation correctly tagged
    assert by_species["Cottus cognatus"].jurisdiction == "CA-ON"
    # Phase 1 known limitation: southern Michigan (42.3°N, -83.2°W) falls inside
    # Ontario's bounding box, so it gets tagged CA-ON instead of US-MI.
    # Accurate geo tagging is deferred to a later phase.
    assert by_species["Etheostoma caeruleum"].jurisdiction == "CA-ON"


def test_cache_hit_skips_http(tmp_path: Path):
    cache = tmp_path / "cache" / "inaturalist"
    cache.mkdir(parents=True)
    fixture = _fixture_data()

    # Pre-populate cache with a fresh file
    params = {
        "taxon_id": 47178,
        "lat": 43.65,
        "lng": -79.38,
        "radius": 50,
        "d1": None,  # will differ in real call; we test _cached_get directly
        "order_by": "observed_on",
        "order": "desc",
        "per_page": 200,
        "page": 1,
    }
    import hashlib

    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = cache / f"{key}.json"
    cache_file.write_text(json.dumps(fixture))

    with (
        patch("src.ingest.global.inaturalist._CACHE_DIR", cache),
        patch("httpx.get") as mock_http,
    ):
        result = _cached_get(params)

    mock_http.assert_not_called()
    assert result["total_results"] == 2


def test_cache_miss_writes_file(tmp_path: Path):
    cache = tmp_path / "cache" / "inaturalist"
    fixture = _fixture_data()
    params = {"taxon_id": 47178, "lat": 1.0, "lng": 1.0, "page": 1}

    with (
        patch("src.ingest.global.inaturalist._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        _cached_get(params)

    import hashlib

    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = cache / f"{key}.json"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text())["total_results"] == 2


def test_stale_cache_triggers_refetch(tmp_path: Path):
    cache = tmp_path / "cache" / "inaturalist"
    cache.mkdir(parents=True)
    fixture = _fixture_data()
    params = {"taxon_id": 47178, "lat": 2.0, "lng": 2.0, "page": 1}

    import hashlib

    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = cache / f"{key}.json"
    cache_file.write_text(json.dumps(fixture))

    # Back-date the file to 25 hours ago
    old_time = time.time() - (25 * 3600)
    import os

    os.utime(cache_file, (old_time, old_time))

    with (
        patch("src.ingest.global.inaturalist._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)) as mock_http,
    ):
        _cached_get(params)

    mock_http.assert_called_once()


# ── licensing and attribution ─────────────────────────────────────────────────

_parse_observation = _inat._parse_observation


def _raw_observation(**overrides):
    base = {
        "id": 244537642,
        "location": "43.5474,-80.1973",
        "observed_on": "2022-05-23",
        "quality_grade": "research",
        "license_code": "cc-by-nc",
        "uri": "https://www.inaturalist.org/observations/244537642",
        "taxon": {"id": 121066, "name": "Etheostoma microperca"},
        "user": {"login": "sgowing2", "id": 8592734},
        "photos": [{"url": "https://x/photo.jpg", "license_code": "cc0"}],
    }
    base.update(overrides)
    return base


def test_parse_captures_record_and_photo_licence_separately():
    """iNaturalist licenses the record and its photos independently."""
    obs = _parse_observation(_raw_observation())
    assert obs.license_code == "cc-by-nc"
    assert obs.photo_license_code == "cc0"


def test_parse_captures_stable_attribution():
    obs = _parse_observation(_raw_observation())
    assert obs.observer == "sgowing2"
    assert obs.observer_id == 8592734
    assert obs.uri.endswith("/observations/244537642")


def test_absent_licence_stays_none_and_is_not_defaulted():
    """A missing license_code means all-rights-reserved, the most restrictive
    case. Defaulting it to anything permissive would invent a grant."""
    obs = _parse_observation(_raw_observation(license_code=None, photos=[]))
    assert obs.license_code is None
    assert obs.photo_license_code is None


# ── undated records must not sink the whole fetch ─────────────────────────────

_observed_date = _inat._observed_date


def test_undated_record_yields_none_not_typeerror():
    """iNaturalist leaves observed_on null on undated records."""
    assert _observed_date(_raw_observation(observed_on=None)) is None


def test_partial_date_yields_none_not_valueerror():
    """Some records carry only a year, or a year-month, which is not ISO."""
    assert _observed_date(_raw_observation(observed_on="2022")) is None
    assert _observed_date(_raw_observation(observed_on="2022-05")) is None


def test_one_undated_record_does_not_discard_the_others(monkeypatch):
    """The regression this guards.

    A bare date.fromisoformat() inside the parse comprehension raised
    TypeError on the first undated record, discarding every other record
    fetched for that location. Five of sixteen sites in a western ingest
    returned nothing at all because of one dateless observation each.
    """
    page = {
        "total_results": 3,
        "results": [
            _raw_observation(id=1),
            _raw_observation(id=2, observed_on=None),  # the poison pill
            _raw_observation(id=3),
        ],
    }
    monkeypatch.setattr(_inat, "_cached_get", lambda params: page)

    observations = _inat.fetch_observations(43.5, -80.1, radius_km=10, days_back=None)

    assert [o.observation_id for o in observations] == [1, 3]


def test_record_without_coordinates_is_dropped_not_parsed(monkeypatch):
    page = {
        "total_results": 2,
        "results": [
            _raw_observation(id=1),
            _raw_observation(id=2, location=None),
        ],
    }
    monkeypatch.setattr(_inat, "_cached_get", lambda params: page)

    observations = _inat.fetch_observations(43.5, -80.1, radius_km=10, days_back=None)

    assert [o.observation_id for o in observations] == [1]


def test_drops_are_counted_in_the_log_not_swallowed(monkeypatch, caplog):
    """A drop nobody counts reads exactly like water nobody surveyed."""
    page = {
        "total_results": 2,
        "results": [_raw_observation(id=1), _raw_observation(id=2, observed_on=None)],
    }
    monkeypatch.setattr(_inat, "_cached_get", lambda params: page)

    with caplog.at_level(logging.WARNING):
        _inat.fetch_observations(43.5, -80.1, radius_km=10, days_back=None)

    assert "dropped 1 of 2" in caplog.text
    assert "observed_on" in caplog.text
