"""Tests for synthesis cache routing — location extraction and cache store/retrieve."""

import json
import pytest
import sqlite_utils

from src.services.synthesis_cache import get_cached_synthesis, store_synthesis


# ── db fixture ────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_conn(tmp_path):
    db = sqlite_utils.Database(tmp_path / "test.db")
    db.execute("""
        CREATE TABLE IF NOT EXISTS segment_synthesis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT UNIQUE NOT NULL,
            lat REAL,
            lng REAL,
            location_name TEXT,
            synthesis TEXT NOT NULL,
            data_sources TEXT,
            computed_at TEXT,
            hit_count INTEGER DEFAULT 0
        )
    """)
    return db


# ── location extraction tests (live Haiku calls) ──────────────────────────────


def test_location_extraction_with_name():
    from src.agent.router import extract_location_from_message

    result = extract_location_from_message(
        "Why does Willoway Park on the Grand River hold channel catfish during midday heat?"
    )
    assert isinstance(result, dict)
    assert "lat" in result
    assert "location_name" in result
    if result["location_name"]:
        assert (
            "willoway" in result["location_name"].lower()
            or "park" in result["location_name"].lower()
        )


def test_location_extraction_with_coords():
    from src.agent.router import extract_location_from_message

    result = extract_location_from_message(
        "What's the habitat like at 42.917, -79.774?"
    )
    assert isinstance(result, dict)
    assert "lat" in result


def test_location_extraction_no_location():
    from src.agent.router import extract_location_from_message

    result = extract_location_from_message("What bait should I use for bass?")
    assert isinstance(result, dict)
    assert "lat" in result
    assert "location_name" in result


# ── cache store / retrieve tests (no network calls) ───────────────────────────


def test_store_and_retrieve_synthesis(db_conn):
    store_synthesis(
        db_conn,
        synthesis="Willoway Park has marshy OHN tributaries that concentrate catfish.",
        lat=42.917,
        lng=-79.774,
        location_name="Willoway Park",
    )
    result = get_cached_synthesis(db_conn, lat=42.917, lng=-79.774)
    assert result is not None
    assert result["cache_hit"] is True
    assert "catfish" in result["synthesis"]


def test_cache_miss_returns_none(db_conn):
    result = get_cached_synthesis(db_conn, lat=43.5, lng=-80.5,
                                  location_name="Nowhere Creek")
    assert result is None


def test_cache_hit_increments_count(db_conn):
    store_synthesis(
        db_conn,
        synthesis="Test synthesis content.",
        location_name="Test Location",
    )
    # First hit
    get_cached_synthesis(db_conn, location_name="Test Location")
    row = db_conn.execute(
        "SELECT hit_count FROM segment_synthesis WHERE location_name = ?",
        ["Test Location"],
    ).fetchone()
    assert row[0] == 1

    # Second hit
    get_cached_synthesis(db_conn, location_name="Test Location")
    row = db_conn.execute(
        "SELECT hit_count FROM segment_synthesis WHERE location_name = ?",
        ["Test Location"],
    ).fetchone()
    assert row[0] == 2


def test_nearby_coord_hits_cache(db_conn):
    """A query ~50m away from a cached entry should still hit via radius search."""
    store_synthesis(
        db_conn,
        synthesis="Spotted close to Byng Island.",
        lat=43.000,
        lng=-80.000,
    )
    # 0.001 degree ≈ 100m — within default 150m radius
    result = get_cached_synthesis(db_conn, lat=43.001, lng=-80.001)
    assert result is not None
    assert result["cache_hit"] is True
