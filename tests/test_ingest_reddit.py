"""Tests for Reddit community ingest module. No real API calls — uses a fixture."""

import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.ingest.community.reddit import _cached_get, fetch_subreddit_posts

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_response.json"


def _fixture_data() -> dict:
    return json.loads(FIXTURE.read_text())


def _mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def test_fetch_returns_posts(tmp_path: Path):
    with (
        patch("src.ingest.community.reddit._CACHE_DIR", tmp_path / "cache"),
        patch("httpx.get", return_value=_mock_response(_fixture_data())),
    ):
        posts = fetch_subreddit_posts("OntarioFishing", listing="hot", limit=10)

    # stickied/mod post is excluded; only 2 real posts remain
    assert len(posts) == 2


def test_stickied_post_excluded(tmp_path: Path):
    with (
        patch("src.ingest.community.reddit._CACHE_DIR", tmp_path / "cache"),
        patch("httpx.get", return_value=_mock_response(_fixture_data())),
    ):
        posts = fetch_subreddit_posts("OntarioFishing")

    post_ids = {p.post_id for p in posts}
    assert "xabc03" not in post_ids


def test_species_extraction(tmp_path: Path):
    with (
        patch("src.ingest.community.reddit._CACHE_DIR", tmp_path / "cache"),
        patch("httpx.get", return_value=_mock_response(_fixture_data())),
    ):
        posts = fetch_subreddit_posts("OntarioFishing")

    by_id = {p.post_id: p for p in posts}
    assert "smallmouth bass" in by_id["xabc01"].extracted_species
    assert "walleye" in by_id["xabc01"].extracted_species
    assert "redhorse" in by_id["xabc02"].extracted_species


def test_generic_bass_removed_when_specific_present(tmp_path: Path):
    with (
        patch("src.ingest.community.reddit._CACHE_DIR", tmp_path / "cache"),
        patch("httpx.get", return_value=_mock_response(_fixture_data())),
    ):
        posts = fetch_subreddit_posts("OntarioFishing")

    by_id = {p.post_id: p for p in posts}
    # "smallmouth bass" is present so generic "bass" should be stripped
    assert "bass" not in by_id["xabc01"].extracted_species


def test_location_extraction(tmp_path: Path):
    with (
        patch("src.ingest.community.reddit._CACHE_DIR", tmp_path / "cache"),
        patch("httpx.get", return_value=_mock_response(_fixture_data())),
    ):
        posts = fetch_subreddit_posts("OntarioFishing")

    by_id = {p.post_id: p for p in posts}
    assert "grand river" in by_id["xabc01"].extracted_locations
    assert "caledonia" in by_id["xabc01"].extracted_locations
    assert "credit river" in by_id["xabc02"].extracted_locations


def test_ontario_jurisdiction_tagged(tmp_path: Path):
    with (
        patch("src.ingest.community.reddit._CACHE_DIR", tmp_path / "cache"),
        patch("httpx.get", return_value=_mock_response(_fixture_data())),
    ):
        posts = fetch_subreddit_posts("OntarioFishing")

    for post in posts:
        assert post.jurisdiction == "CA-ON"


def test_cache_hit_skips_http(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    fixture = _fixture_data()

    url = "https://www.reddit.com/r/OntarioFishing/hot.json"
    params = {"limit": 100}
    cache_key = hashlib.sha256(
        json.dumps({"url": url, "params": params}, sort_keys=True).encode()
    ).hexdigest()[:16]
    (cache_dir / f"{cache_key}.json").write_text(json.dumps(fixture))

    with (
        patch("src.ingest.community.reddit._CACHE_DIR", cache_dir),
        patch("httpx.get") as mock_http,
    ):
        _cached_get(url, params)

    mock_http.assert_not_called()


def test_cache_miss_writes_file(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    fixture = _fixture_data()
    url = "https://www.reddit.com/r/OntarioFishing/hot.json"
    params = {"limit": 100}

    with (
        patch("src.ingest.community.reddit._CACHE_DIR", cache_dir),
        patch("httpx.get", return_value=_mock_response(fixture)),
    ):
        _cached_get(url, params)

    cache_key = hashlib.sha256(
        json.dumps({"url": url, "params": params}, sort_keys=True).encode()
    ).hexdigest()[:16]
    assert (cache_dir / f"{cache_key}.json").exists()


def test_stale_cache_refetches(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    fixture = _fixture_data()

    url = "https://www.reddit.com/r/OntarioFishing/hot.json"
    params = {"limit": 100}
    cache_key = hashlib.sha256(
        json.dumps({"url": url, "params": params}, sort_keys=True).encode()
    ).hexdigest()[:16]
    cache_file = cache_dir / f"{cache_key}.json"
    cache_file.write_text(json.dumps(fixture))
    old_time = time.time() - (25 * 3600)
    os.utime(cache_file, (old_time, old_time))

    with (
        patch("src.ingest.community.reddit._CACHE_DIR", cache_dir),
        patch("httpx.get", return_value=_mock_response(fixture)) as mock_http,
    ):
        _cached_get(url, params)

    mock_http.assert_called_once()
