"""Weather service — bridges the ingest module to the agent."""

import importlib
import json
from datetime import date, timedelta

_weather = importlib.import_module("src.ingest.global.weather")

_FISHING_NOTES = {
    "falling": (
        "Pressure is falling — fish are often actively feeding ahead of a weather system. "
        "Good time to be on the water."
    ),
    "rising": (
        "Pressure is rising post-front — fish activity may be suppressed. "
        "Expect slower fishing until pressure stabilizes."
    ),
    "steady": (
        "Pressure is steady — expect baseline feeding activity. "
        "No strong pressure-based advantage or disadvantage."
    ),
}


def get_conditions_for_agent(lat: float, lng: float, when: str = "now") -> str:
    if when == "now":
        conditions = _weather.get_current_conditions(lat, lng)
        trend = _weather.compute_pressure_trend(lat, lng)
        return json.dumps({
            "when": "now",
            "jurisdiction": conditions.jurisdiction,
            "time": conditions.time.isoformat(),
            "temperature_c": conditions.temperature_c,
            "humidity_pct": conditions.humidity_pct,
            "precipitation_mm": conditions.precipitation_mm,
            "wind_speed_kmh": conditions.wind_speed_kmh,
            "pressure_hpa": conditions.pressure_hpa,
            "cloud_cover_pct": conditions.cloud_cover_pct,
            "weather_code": conditions.weather_code,
            "pressure_trend": trend.trend,
            "pressure_note": _FISHING_NOTES[trend.trend],
        })

    forecast = _weather.get_forecast(lat, lng, days=10)

    if when == "tomorrow":
        return _forecast_day_json(forecast.days[1], forecast.jurisdiction, "tomorrow")

    if when == "in_3_days":
        return _forecast_day_json(forecast.days[3], forecast.jurisdiction, "in 3 days")

    if when == "this_weekend":
        today = date.today()
        # days until Saturday (weekday 5); if today is Saturday, next Saturday
        days_to_sat = (5 - today.weekday()) % 7
        if days_to_sat == 0:
            days_to_sat = 7
        sat = today + timedelta(days=days_to_sat)
        sun = sat + timedelta(days=1)
        weekend_days = [d for d in forecast.days if d.date in (sat, sun)]
        return json.dumps({
            "when": "this_weekend",
            "jurisdiction": forecast.jurisdiction,
            "days": [
                {
                    "date": d.date.isoformat(),
                    "temp_max_c": d.temp_max_c,
                    "temp_min_c": d.temp_min_c,
                    "precipitation_sum_mm": d.precipitation_sum_mm,
                    "wind_speed_max_kmh": d.wind_speed_max_kmh,
                    "weather_code": d.weather_code,
                }
                for d in weekend_days
            ],
        })

    return json.dumps({"error": f"Unknown 'when' value: {when!r}"})


def get_pressure_trend_for_agent(lat: float, lng: float) -> str:
    trend = _weather.compute_pressure_trend(lat, lng)
    return json.dumps({
        "trend": trend.trend,
        "current_hpa": trend.current_hpa,
        "delta_24h_hpa": trend.delta_24h_hpa,
        "delta_48h_hpa": trend.delta_48h_hpa,
        "jurisdiction": trend.jurisdiction,
        "fishing_note": _FISHING_NOTES[trend.trend],
    })


def _forecast_day_json(day, jurisdiction: str, label: str) -> str:
    return json.dumps({
        "when": label,
        "jurisdiction": jurisdiction,
        "date": day.date.isoformat(),
        "temp_max_c": day.temp_max_c,
        "temp_min_c": day.temp_min_c,
        "precipitation_sum_mm": day.precipitation_sum_mm,
        "wind_speed_max_kmh": day.wind_speed_max_kmh,
        "weather_code": day.weather_code,
    })
