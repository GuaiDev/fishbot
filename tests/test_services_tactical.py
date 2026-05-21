"""Tests for the tactical recommender rule engine.

All tests are offline — no live API calls, no production database.
Weather functions and DB are mocked throughout.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.tactical import get_tactical_recommendation_for_agent

# ── Fixtures / helpers ────────────────────────────────────────────────────────


def _conditions_json(
    temp_c: float = 18.0, trend: str = "steady", jurisdiction: str = "CA-ON"
) -> str:
    return json.dumps(
        {
            "temperature_c": temp_c,
            "pressure_trend": trend,
            "jurisdiction": jurisdiction,
        }
    )


def _pressure_json(trend: str = "steady") -> str:
    return json.dumps({"trend": trend, "current_hpa": 1013.0, "delta_24h_hpa": 0.0})


def _call(
    species: str | None = None,
    *,
    temp_c: float | None = None,
    clarity: str | None = None,
    trend: str | None = None,
    time_of_day: str | None = None,
    month: int = 10,  # October = fall by default
) -> dict:
    """Call the service with DB mocked out, no live weather calls."""
    with (
        patch("src.services.tactical.get_db") as mock_db,
        patch("src.services.tactical.insert_recommendation", return_value=1),
    ):
        mock_db.return_value = MagicMock()
        result = get_tactical_recommendation_for_agent(
            species=species,
            water_temp_c=temp_c,
            water_clarity=clarity,
            time_of_day=time_of_day,
            _month=month,
        )
    data = json.loads(result)
    # Inject a fake pressure trend for assertions when trend was specified
    # (we're not auto-fetching via lat/lng in these tests)
    if trend is not None and data.get("recommendations"):
        # re-run with the trend baked in via mocked weather fetch
        pass
    return data


def _call_with_weather(
    species: str,
    *,
    temp_c: float = 18.0,
    trend: str = "steady",
    clarity: str | None = None,
    time_of_day: str | None = None,
    month: int = 10,
) -> dict:
    """Call the service with mocked weather (auto-fetch path via lat/lng)."""
    with (
        patch("src.services.tactical.get_db") as mock_db,
        patch("src.services.tactical.insert_recommendation", return_value=1),
        patch(
            "src.services.weather.get_conditions_for_agent",
            return_value=_conditions_json(temp_c, trend),
        ),
        patch(
            "src.services.weather.get_pressure_trend_for_agent", return_value=_pressure_json(trend)
        ),
    ):
        mock_db.return_value = MagicMock()
        result = get_tactical_recommendation_for_agent(
            species=species,
            lat=43.7,
            lng=-79.4,
            water_clarity=clarity,
            time_of_day=time_of_day,
            _month=month,
        )
    return json.loads(result)


# ── Species resolution ────────────────────────────────────────────────────────


def test_no_species_single_target_uses_profile():
    mock_profile = MagicMock()
    mock_profile.target_species = ["brook trout"]
    with (
        patch("src.services.tactical.get_db") as mock_db,
        patch("src.services.tactical.insert_recommendation", return_value=1),
        patch("src.storage.profile.load_profile", return_value=mock_profile),
    ):
        mock_db.return_value = MagicMock()
        result = json.loads(get_tactical_recommendation_for_agent(_month=5))
    assert result.get("species") == "brook trout"
    assert "recommendations" in result


def test_no_species_multiple_targets_asks_clarification():
    mock_profile = MagicMock()
    mock_profile.target_species = ["smallmouth bass", "brook trout", "walleye"]
    with (
        patch("src.services.tactical.get_db"),
        patch("src.storage.profile.load_profile", return_value=mock_profile),
    ):
        result = json.loads(get_tactical_recommendation_for_agent(_month=5))
    assert result.get("clarification_needed") is True
    assert set(result["options"]) == {"smallmouth bass", "brook trout", "walleye"}
    assert "smallmouth bass" in result["message"]


def test_no_species_empty_profile_returns_error():
    mock_profile = MagicMock()
    mock_profile.target_species = []
    with (
        patch("src.services.tactical.get_db"),
        patch("src.storage.profile.load_profile", return_value=mock_profile),
    ):
        result = json.loads(get_tactical_recommendation_for_agent(_month=5))
    assert "error" in result


# ── Microfishing ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "species",
    [
        "johnny darter",
        "rainbow darter",
        "tessellated darter",
        "longnose dace",
        "northern madtom",
        "central stonecat",
        "logperch",
        "common shiner",
        "creek chub",
        "brook lamprey",
        "sculpin",
        "fathead minnow",
    ],
)
def test_microfishing_species_get_ultralight_rig(species):
    data = _call(species=species, month=6)
    assert "recommendations" in data
    primary = data["recommendations"][0]
    assert "20-26" in primary["size_range"], f"{species}: expected size 20-26 hook"
    assert "ultralight" in primary["lure_type"].lower()
    assert primary["retrieve_speed"] == "slow"
    assert "0-2 ft" in primary["target_depth_range"]
    assert primary["reasoning"].strip() != ""


def test_microfishing_reasoning_mentions_hook_size():
    data = _call(species="johnny darter", month=5)
    reasoning = data["recommendations"][0]["reasoning"]
    assert "20-26" in reasoning or "size 20" in reasoning


def test_microfishing_reasoning_mentions_natural_bait():
    data = _call(species="longnose dace", month=6)
    reasoning = data["recommendations"][0]["reasoning"]
    assert any(bait in reasoning.lower() for bait in ("waxworm", "maggot", "nightcrawler"))


# ── Temperature rules ─────────────────────────────────────────────────────────


def test_cold_water_forces_slow_retrieve():
    data = _call(species="brook trout", temp_c=1.0, month=2)
    assert data["recommendations"][0]["retrieve_speed"] == "slow"


def test_optimal_temp_gives_medium_baseline():
    # 20°C is optimal for bass; no pressure modifier
    data = _call(species="smallmouth bass", temp_c=20.0, month=10)
    assert data["recommendations"][0]["retrieve_speed"] == "medium"


def test_cold_water_reasoning_mentions_temperature():
    data = _call(species="walleye", temp_c=1.5, month=1)
    reasoning = data["recommendations"][0]["reasoning"]
    assert "1°C" in reasoning or "frigid" in reasoning or "lethargic" in reasoning


def test_warm_water_forces_slow_retrieve():
    # 31°C is above bass warm limit (30°C)
    data = _call(species="smallmouth bass", temp_c=31.0, month=7)
    assert data["recommendations"][0]["retrieve_speed"] == "slow"


def test_catfish_cold_threshold_is_higher():
    # Catfish cold limit is 15°C — 14°C should show lethargic/slow
    data = _call(species="channel catfish", temp_c=14.0, month=10)
    assert data["recommendations"][0]["retrieve_speed"] == "slow"


# ── Stained / murky water → high-visibility colors ───────────────────────────


def test_stained_water_gives_chartreuse():
    data = _call(species="smallmouth bass", clarity="stained", temp_c=20.0, month=10)
    color = data["recommendations"][0]["color"].lower()
    assert "chartreuse" in color


def test_murky_water_gives_dark_color():
    data = _call(species="pike", clarity="murky", temp_c=18.0, month=9)
    color = data["recommendations"][0]["color"].lower()
    assert "black" in color or "dark" in color


def test_clear_water_gives_natural_color():
    data = _call(species="brook trout", clarity="clear", temp_c=12.0, month=8)
    color = data["recommendations"][0]["color"].lower()
    assert "natural" in color or "silver" in color or "green pumpkin" in color or "smoke" in color


def test_stained_water_reasoning_mentions_visibility():
    data = _call(species="walleye", clarity="stained", month=10)
    reasoning = data["recommendations"][0]["reasoning"]
    assert (
        "stained" in reasoning.lower()
        or "visibility" in reasoning.lower()
        or "contrast" in reasoning.lower()
    )


def test_murky_water_technique_mentions_vibration():
    data = _call(species="pike", clarity="murky", month=9)
    technique = data["recommendations"][0]["technique"].lower()
    assert "vibration" in technique or "rattle" in technique or "scent" in technique


# ── Pressure trend → retrieve speed ──────────────────────────────────────────


def test_falling_pressure_increases_speed():
    # Active bass (medium base), falling pressure → fast
    data = _call_with_weather("smallmouth bass", temp_c=20.0, trend="falling", month=10)
    assert data["recommendations"][0]["retrieve_speed"] == "fast"


def test_rising_pressure_decreases_speed():
    # Active bass (medium base), rising pressure → slow
    data = _call_with_weather("smallmouth bass", temp_c=20.0, trend="rising", month=10)
    assert data["recommendations"][0]["retrieve_speed"] == "slow"


def test_steady_pressure_no_speed_change():
    data = _call_with_weather("smallmouth bass", temp_c=20.0, trend="steady", month=10)
    assert data["recommendations"][0]["retrieve_speed"] == "medium"


def test_falling_pressure_reasoning_mentions_feeding_window():
    data = _call_with_weather("walleye", temp_c=16.0, trend="falling", month=9)
    reasoning = data["recommendations"][0]["reasoning"]
    assert (
        "falling" in reasoning.lower()
        or "feeding window" in reasoning.lower()
        or "front" in reasoning.lower()
    )


def test_rising_pressure_reasoning_mentions_suppression():
    data = _call_with_weather("bass", temp_c=20.0, trend="rising", month=10)
    reasoning = data["recommendations"][0]["reasoning"]
    assert "rising" in reasoning.lower() or "suppress" in reasoning.lower()


# ── Dawn / dusk topwater ──────────────────────────────────────────────────────


def test_dawn_gives_shallow_depth():
    data = _call(species="smallmouth bass", time_of_day="dawn", month=8)
    depth = data["recommendations"][0]["target_depth_range"]
    assert "0-" in depth  # starts at surface


def test_dusk_gives_shallow_depth():
    data = _call(species="pike", time_of_day="dusk", month=9)
    depth = data["recommendations"][0]["target_depth_range"]
    assert "0-" in depth


def test_dawn_active_bass_summer_returns_topwater():
    data = _call(species="smallmouth bass", time_of_day="dawn", temp_c=22.0, month=8)
    lure = data["recommendations"][0]["lure_type"].lower()
    assert "topwater" in lure or "popper" in lure or "buzzbait" in lure


def test_midday_gives_deep_depth():
    data = _call(species="walleye", time_of_day="midday", month=7)
    depth = data["recommendations"][0]["target_depth_range"]
    # Should be at least 8 ft deep
    low = int(depth.split("-")[0].replace(" ft", "").strip())
    assert low >= 8


# ── Season rules ──────────────────────────────────────────────────────────────


def test_spawn_season_reasoning_has_ethics_caveat():
    # May = spawn
    data = _call(species="smallmouth bass", month=5)
    reasoning = data["recommendations"][0]["reasoning"]
    assert (
        "ethical" in reasoning.lower()
        or "catch-and-release" in reasoning.lower()
        or "bed" in reasoning.lower()
    )


def test_fall_season_reasoning_mentions_bulk():
    data = _call(species="smallmouth bass", month=10)
    reasoning = data["recommendations"][0]["reasoning"]
    assert (
        "bulking" in reasoning.lower()
        or "winter" in reasoning.lower()
        or "fall" in reasoning.lower()
    )


def test_winter_gives_deep_depth_by_default():
    data = _call(species="walleye", month=1)
    depth = data["recommendations"][0]["target_depth_range"]
    low = int(depth.split("-")[0].strip().split()[0])
    assert low >= 8


# ── Reasoning field ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "species,month,temp_c,clarity",
    [
        ("smallmouth bass", 10, 18.0, "stained"),
        ("brook trout", 5, 10.0, "clear"),
        ("walleye", 1, 3.0, None),
        ("pike", 9, 20.0, "murky"),
        ("channel catfish", 7, 25.0, None),
        ("bluegill", 6, 22.0, "clear"),
        ("johnny darter", 5, 14.0, None),
        ("carp", 8, 23.0, None),
        ("yellow perch", 3, 6.0, None),
    ],
)
def test_reasoning_never_empty(species, month, temp_c, clarity):
    data = _call(species=species, month=month, temp_c=temp_c, clarity=clarity)
    for rec in data.get("recommendations", []):
        assert rec["reasoning"].strip() != "", f"reasoning empty for {species}"


# ── Confidence ────────────────────────────────────────────────────────────────


def test_species_only_gives_low_confidence():
    data = _call(species="unknown mystery fish", month=6)
    assert data["recommendations"][0]["confidence"] == "low"


def test_known_species_bumps_confidence():
    data = _call(species="smallmouth bass", month=10)
    assert data["recommendations"][0]["confidence"] in ("medium", "high")


def test_high_confidence_requires_multiple_conditions():
    data = _call_with_weather(
        "smallmouth bass",
        temp_c=20.0,
        trend="falling",
        clarity="stained",
        time_of_day="morning",
        month=10,
    )
    assert data["recommendations"][0]["confidence"] == "high"


# ── Result structure ──────────────────────────────────────────────────────────


def test_standard_species_returns_two_recommendations():
    data = _call(species="smallmouth bass", month=9)
    assert len(data["recommendations"]) == 2


def test_microfishing_returns_one_recommendation():
    data = _call(species="johnny darter", month=6)
    assert len(data["recommendations"]) == 1


def test_secondary_confidence_not_higher_than_primary():
    data = _call(species="walleye", temp_c=18.0, clarity="stained", month=9)
    tiers = {"low": 0, "medium": 1, "high": 2}
    primary = tiers[data["recommendations"][0]["confidence"]]
    secondary = tiers[data["recommendations"][1]["confidence"]]
    assert secondary <= primary


def test_conditions_used_in_output():
    data = _call(species="bass", temp_c=15.0, clarity="murky", month=10)
    cond = data["conditions_used"]
    assert cond["water_temp_c"] == 15.0
    assert cond["water_clarity"] == "murky"
    assert cond["season"] == "fall"


def test_recommendation_id_present():
    data = _call(species="pike", month=9)
    assert "recommendation_id" in data
