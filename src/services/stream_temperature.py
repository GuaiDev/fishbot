"""Stream temperature service — bridges HYDAT extraction to the agent."""

import json
from collections import Counter

from src.storage.database import get_db
from src.storage.stream_temperature import is_data_loaded, query_temperature_summaries

_NOT_LOADED = json.dumps(
    {
        "available": False,
        "note": (
            "Stream temperature data not loaded — "
            "run make ingest-hydat once to enable this feature."
        ),
    }
)


def get_stream_temperature_for_agent(
    lat: float, lng: float, radius_km: float = 50
) -> str:
    """Return JSON with thermal regime summary for streams near lat/lng."""
    db = get_db()

    if not is_data_loaded(db):
        return _NOT_LOADED

    summaries = query_temperature_summaries(db, lat, lng, radius_km)
    if not summaries:
        return json.dumps(
            {
                "available": True,
                "stations": [],
                "note": f"No HYDAT temperature stations found within {radius_km:.0f}km.",
            }
        )

    regimes = [s.thermal_regime for s in summaries if s.thermal_regime != "unknown"]
    area_regime = Counter(regimes).most_common(1)[0][0] if regimes else "unknown"

    return json.dumps(
        {
            "available": True,
            "area_thermal_regime": area_regime,
            "stations": [
                {
                    "station_id": s.station_id,
                    "station_name": s.station_name,
                    "lat": s.lat,
                    "lng": s.lng,
                    "thermal_regime": s.thermal_regime,
                    "summer_mean_c": s.summer_mean_c,
                    "summer_max_c": s.summer_max_c,
                    "years_of_data": s.years_of_data,
                    "species_notes": s.species_notes,
                }
                for s in summaries
            ],
        }
    )
