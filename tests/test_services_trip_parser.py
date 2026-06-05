"""Tests for trip_parser service.

Claude API calls are mocked via the anthropic client. Snap-to-segment is
tested via direct mock of snap_to_segment.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.trip_parser import parse_trip_from_text, snap_to_segment


def _mock_client(payload: dict) -> MagicMock:
    """Return a mock Anthropic client whose messages.create returns payload as JSON."""
    block = MagicMock()
    block.text = json.dumps(payload)
    msg = MagicMock()
    msg.content = [block]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def _api_payload(**overrides) -> dict:
    base = {
        "date": "2026-05-20",
        "location_description": "Bronte Creek near Burloak Drive",
        "waterbody_name": "Bronte Creek",
        "lat": 43.45,
        "lng": -79.70,
        "species_caught": ["Creek Chub", "White Sucker"],
        "species_observed": ["Rainbow Darter"],
        "species_targeted": "Creek Chub",
        "conditions": {
            "water_level": "low",
            "water_clarity": "clear",
            "water_temp_c": 14.5,
            "weather": "sunny",
            "flow_trend": "stable",
        },
        "habitat_notes": "riffle over cobble under a road bridge",
        "spot_type": "riffle",
        "fish_count": 5,
        "was_productive": True,
        "gear": "2lb tippet, size 14 nymph",
        "notes": "Best spot on the creek",
    }
    base.update(overrides)
    return base


@patch("src.services.trip_parser.snap_to_segment", return_value={"ogf_id": 12345, "distance_to_segment_m": 45.0, "segment_stream_order": 3, "segment_watercourse_name": "Bronte Creek"})
@patch("src.services.trip_parser.get_model", return_value="claude-sonnet-4-6")
@patch("src.services.trip_parser.get_client")
def test_parse_complete_trip(mock_get_client, mock_get_model, mock_snap):
    mock_get_client.return_value = _mock_client(_api_payload())

    result = parse_trip_from_text(
        "Fished Bronte Creek near Burloak this morning, caught creek chubs and suckers "
        "near a riffle under the bridge, water low and clear"
    )

    assert result["date"] == "2026-05-20"
    assert "Creek Chub" in result["species_caught"]
    assert result["conditions"]["water_level"] == "low"
    assert result["was_productive"] is True
    assert result["spot_type"] == "riffle"
    assert result["ogf_id"] == 12345
    assert result["segment_watercourse_name"] == "Bronte Creek"


@patch("src.services.trip_parser.snap_to_segment", return_value={})
@patch("src.services.trip_parser.get_model", return_value="claude-sonnet-4-6")
@patch("src.services.trip_parser.get_client")
def test_parse_minimal_trip(mock_get_client, mock_get_model, mock_snap):
    mock_get_client.return_value = _mock_client(
        _api_payload(
            date=None,
            species_caught=["Creek Chub"],
            species_observed=[],
            conditions={"water_level": None, "water_clarity": None, "water_temp_c": None, "weather": None, "flow_trend": None},
            habitat_notes=None,
            spot_type=None,
            fish_count=None,
            was_productive=True,
            gear=None,
            notes=None,
        )
    )

    result = parse_trip_from_text("fished Bronte Creek, caught chubs")
    assert result["waterbody_name"] == "Bronte Creek"
    assert "Creek Chub" in result["species_caught"]
    assert result["date"] is None


@patch("src.services.trip_parser.snap_to_segment", return_value={})
@patch("src.services.trip_parser.get_model", return_value="claude-sonnet-4-6")
@patch("src.services.trip_parser.get_client")
def test_parse_negative_trip(mock_get_client, mock_get_model, mock_snap):
    mock_get_client.return_value = _mock_client(
        _api_payload(
            species_caught=[],
            species_observed=[],
            conditions={"water_level": "high", "water_clarity": "turbid", "water_temp_c": None, "weather": "rainy", "flow_trend": "rising"},
            fish_count=0,
            was_productive=False,
            notes="blown out from rain",
        )
    )

    result = parse_trip_from_text("nothing at the Credit today, blown out")
    assert result["was_productive"] is False
    assert result["conditions"]["water_clarity"] == "turbid"
    assert result["fish_count"] == 0


@patch("src.services.trip_parser.get_model", return_value="claude-sonnet-4-6")
@patch("src.services.trip_parser.get_client")
def test_snap_to_segment_called_with_parsed_coords(mock_get_client, mock_get_model):
    """When Claude returns lat/lng, snap_to_segment is called with them."""
    mock_get_client.return_value = _mock_client(_api_payload())

    with patch("src.services.trip_parser.snap_to_segment") as mock_snap:
        mock_snap.return_value = {
            "ogf_id": 999,
            "distance_to_segment_m": 120.0,
            "segment_stream_order": 3,
            "segment_watercourse_name": "Bronte Creek",
        }
        result = parse_trip_from_text("fished Bronte Creek, caught chubs")

    mock_snap.assert_called_once_with(43.45, -79.70)
    assert result["ogf_id"] == 999
    assert result["distance_to_segment_m"] == 120.0
