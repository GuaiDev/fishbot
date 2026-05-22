"""Tests for the GBIF ingest module. No real API calls — uses a fixture."""

import hashlib
import importlib
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# "global" is a Python keyword — use importlib to reach the module
_gbif = importlib.import_module("src.ingest.global.gbif")
fetch_gbif_observations = _gbif.fetch_gbif_observations
_cached_get = _gbif._cached_get

FIXTURE = Path(__file__).parent / "fixtures" / "gbif_response.json"


def _fixture_data() -> dict:
    return json.loads(FIXTURE.read_text())


def _mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def test_fetch_returns_observations(tmp_path: Path):
    cache = tmp_path / "cache" / "gbif"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        observations = fetch_gbif_observations(lat=43.65, lng=-79.38, radius_km=50)

    # Mock returns the same 3-record fixture for every orderKey query; total = 3 × num_orders
    assert len(observations) == 3 * len(_gbif._FISH_ORDER_KEYS)
    species = {o.species for o in observations}
    assert "Moxostoma duquesnii" in species
    assert "Percina caprodes" in species
    assert "Etheostoma caeruleum" in species


def test_null_date_handling(tmp_path: Path):
    cache = tmp_path / "cache" / "gbif"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        observations = fetch_gbif_observations(lat=43.65, lng=-79.38, radius_km=50)

    by_species = {o.species: o for o in observations}
    specimen = by_species["Percina caprodes"]
    assert specimen.observed_on is None
    assert specimen.basis_of_record == "PRESERVED_SPECIMEN"


def test_datetime_date_parsed(tmp_path: Path):
    """eventDate with full ISO datetime (e.g. "2024-05-22T00:00:00") parses to date only."""
    cache = tmp_path / "cache" / "gbif"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        observations = fetch_gbif_observations(lat=43.65, lng=-79.38, radius_km=50)

    by_species = {o.species: o for o in observations}
    from datetime import date

    assert by_species["Etheostoma caeruleum"].observed_on == date(2024, 5, 22)


def test_jurisdiction_tagged(tmp_path: Path):
    cache = tmp_path / "cache" / "gbif"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        observations = fetch_gbif_observations(lat=43.65, lng=-79.38, radius_km=50)

    for obs in observations:
        assert obs.jurisdiction == "CA-ON"


def test_basis_of_record_excludes_human_observation(tmp_path: Path):
    """basisOfRecord sent as a list (repeated params); HUMAN_OBSERVATION absent."""
    cache = tmp_path / "cache" / "gbif"
    fixture = _fixture_data()

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)) as mock_http,
    ):
        fetch_gbif_observations(lat=43.65, lng=-79.38, radius_km=50)

    _, kwargs = mock_http.call_args
    sent_params = kwargs["params"]
    if isinstance(sent_params, dict):
        basis = sent_params["basisOfRecord"]
    else:
        basis = [v for k, v in sent_params if k == "basisOfRecord"]
    assert isinstance(basis, list)
    assert "HUMAN_OBSERVATION" not in basis
    assert "PRESERVED_SPECIMEN" in basis
    assert "MATERIAL_SAMPLE" in basis


def test_cache_hit_skips_http(tmp_path: Path):
    cache = tmp_path / "cache" / "gbif"
    cache.mkdir(parents=True)
    fixture = _fixture_data()

    params = {"taxonKey": 186, "decimalLatitude": "43.0,44.0", "offset": 0}
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = cache / f"{key}.json"
    cache_file.write_text(json.dumps(fixture))

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get") as mock_http,
    ):
        result = _cached_get(params)

    mock_http.assert_not_called()
    assert result["count"] == 3


def test_cache_miss_writes_file(tmp_path: Path):
    cache = tmp_path / "cache" / "gbif"
    fixture = _fixture_data()
    params = {"taxonKey": 186, "decimalLatitude": "42.0,43.0", "offset": 0}

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        _cached_get(params)

    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = cache / f"{key}.json"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text())["count"] == 3


def test_stale_cache_triggers_refetch(tmp_path: Path):
    cache = tmp_path / "cache" / "gbif"
    cache.mkdir(parents=True)
    fixture = _fixture_data()
    params = {"taxonKey": 186, "decimalLatitude": "41.0,42.0", "offset": 0}

    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = cache / f"{key}.json"
    cache_file.write_text(json.dumps(fixture))

    old_time = time.time() - (25 * 3600)
    os.utime(cache_file, (old_time, old_time))

    with (
        patch("src.ingest.global.gbif._CACHE_DIR", cache),
        patch("httpx.get", return_value=_mock_response(fixture)) as mock_http,
    ):
        _cached_get(params)

    mock_http.assert_called_once()
