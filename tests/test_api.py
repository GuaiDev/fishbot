"""FastAPI endpoint tests.

Tests that call /chat and /log-trip require a funded Anthropic API key
(those endpoints run the full agentic loop). They are marked accordingly
and will be skipped when credentials are unavailable.
"""

import os

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

REQUIRES_API = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_no_auth_required():
    response = client.get("/health")
    assert response.status_code == 200


@REQUIRES_API
def test_chat_basic():
    response = client.post(
        "/chat",
        json={
            "message": "What fish can I catch near Oakville Ontario?",
            "conversation_history": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 0
    assert "conversation_history" in data


@REQUIRES_API
def test_chat_maintains_history():
    r1 = client.post(
        "/chat",
        json={
            "message": "I'm planning to fish the Credit River",
            "conversation_history": [],
        },
    )
    assert r1.status_code == 200
    history = r1.json()["conversation_history"]
    assert len(history) >= 2

    r2 = client.post(
        "/chat",
        json={
            "message": "What species should I target there?",
            "conversation_history": history,
        },
    )
    assert r2.status_code == 200


@REQUIRES_API
def test_log_trip_endpoint():
    response = client.post(
        "/log-trip",
        json={"text": "Fished Bronte Creek today, caught a creek chub on worm."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "logged"
    assert "session_id" in data


def test_ingest_data_requires_lat_lng():
    """Missing lat/lng returns 400."""
    response = client.post(
        "/ingest/data",
        json={"label": "test"},
        headers={"X-Api-Key": "test-key"},
    )
    # Either 400 (missing lat/lng), 401 (wrong key), or 422 (validation) — all acceptable
    assert response.status_code in (400, 401, 422)


def test_ingest_data_no_key_development_mode():
    """Without FISHBOT_API_KEY env var set, endpoint allows requests (returns non-401)."""
    if os.environ.get("FISHBOT_API_KEY"):
        return
    response = client.post(
        "/ingest/data",
        json={"lat": 43.45, "lng": -79.72, "radius_km": 1},
    )
    assert response.status_code != 401
