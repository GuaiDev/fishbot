"""HYDAT stream temperature extraction.

Downloads the ECCC/WSC National Water Data Archive (HYDAT) SQLite, extracts
Ontario daily temperature records for stations near the target location,
stores summaries in the app DB, then deletes the bulk HYDAT file.

Run once via: make ingest-hydat
"""

import math
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import httpx

from src.models.stream_temperature import StreamTemperatureReading, StreamTemperatureSummary
from src.storage.database import get_db
from src.storage.stream_temperature import (
    upsert_temperature_readings,
    upsert_temperature_summaries,
)

_INDEX_URL = "https://collaboration.cmc.ec.gc.ca/cmc/hydrometrics/www/"
_USER_AGENT = "fishbot/1.0 (personal fishing assistant; contact jasonkang.jt23@gmail.com)"
_KM_PER_DEGREE = 111.0

# Explicit SELECT for the 31 MAX and MIN columns — avoids reliance on column order.
_MAX_SEL = ", ".join(f"MAX{d}" for d in range(1, 32))
_MIN_SEL = ", ".join(f"MIN{d}" for d in range(1, 32))
_TEMP_QUERY = (
    f"SELECT YEAR, MONTH, NO_DATES, {_MAX_SEL}, {_MIN_SEL} "
    f"FROM DLY_TEMPERATURES WHERE STATION_NUMBER = ? ORDER BY YEAR, MONTH"
)
# Row layout: [0]=YEAR [1]=MONTH [2]=NO_DATES [3..33]=MAX1..31 [34..64]=MIN1..31

_SPECIES_NOTES: dict[str, str] = {
    "coldwater": (
        "Summer temps support brook trout, lake trout, and other salmonids. "
        "Darters and sensitive cyprinids plausible."
    ),
    "coolwater": (
        "Suitable for walleye, pike, bass. "
        "Marginal for salmonids — check for cold groundwater refugia."
    ),
    "warmwater": (
        "Carp, catfish, bass, sunfish. Too warm for sustained salmonid presence."
    ),
    "unknown": "Insufficient temperature data to classify thermal regime.",
}


def download_and_extract(lat: float, lng: float, radius_km: float = 100) -> int:
    """Download HYDAT zip, extract Ontario temperature data near lat/lng, clean up.

    Returns the number of station summaries stored in the app DB.
    """
    url = _find_hydat_url()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        zip_path = tmp_path / "hydat.zip"

        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=600,
            follow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            with zip_path.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=65_536):
                    fh.write(chunk)

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_path)

        candidates = (
            list(tmp_path.glob("Hydat_sqlite3_*.db"))
            + list(tmp_path.glob("*.db"))
            + list(tmp_path.glob("*.sqlite3"))
        )
        if not candidates:
            raise RuntimeError("No SQLite file found inside HYDAT zip.")

        hydat_path = candidates[0]
        conn = sqlite3.connect(str(hydat_path))
        try:
            readings, summaries = _extract_from_hydat(conn, lat, lng, radius_km)
        finally:
            conn.close()

    if not summaries:
        return 0

    app_db = get_db()
    upsert_temperature_readings(app_db, readings)
    upsert_temperature_summaries(app_db, summaries)
    return len(summaries)


def _find_hydat_url() -> str:
    resp = httpx.get(
        _INDEX_URL, headers={"User-Agent": _USER_AGENT}, timeout=30, follow_redirects=True
    )
    resp.raise_for_status()
    dates = re.findall(r"Hydat_sqlite3_(\d{8})\.zip", resp.text)
    if not dates:
        raise RuntimeError("Could not locate Hydat_sqlite3_*.zip on ECCC index page.")
    latest = sorted(dates)[-1]
    return f"{_INDEX_URL}Hydat_sqlite3_{latest}.zip"


def _extract_from_hydat(
    conn: sqlite3.Connection, lat: float, lng: float, radius_km: float
) -> tuple[list[StreamTemperatureReading], list[StreamTemperatureSummary]]:
    """Pure extraction: reads HYDAT conn, returns (readings, summaries). No DB writes."""
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "DLY_TEMPERATURES" not in tables or "STATIONS" not in tables:
        return [], []

    deg = radius_km / _KM_PER_DEGREE
    stations = conn.execute(
        """
        SELECT s.STATION_NUMBER, s.STATION_NAME, s.LATITUDE, s.LONGITUDE
        FROM STATIONS s
        INNER JOIN (SELECT DISTINCT STATION_NUMBER FROM DLY_TEMPERATURES) t
            ON s.STATION_NUMBER = t.STATION_NUMBER
        WHERE s.PROV_TERR_STATE_LOC = 'ON'
          AND s.LATITUDE  BETWEEN ? AND ?
          AND s.LONGITUDE BETWEEN ? AND ?
        """,
        (lat - deg, lat + deg, lng - deg, lng + deg),
    ).fetchall()

    all_readings: list[StreamTemperatureReading] = []
    all_summaries: list[StreamTemperatureSummary] = []

    for station_id, station_name, s_lat, s_lng in stations:
        if s_lat is None or s_lng is None:
            continue
        if _haversine_km(lat, lng, float(s_lat), float(s_lng)) > radius_km:
            continue

        rows = conn.execute(_TEMP_QUERY, (station_id,)).fetchall()
        if not rows:
            continue

        readings: list[StreamTemperatureReading] = []
        for row in rows:
            mean_c, max_c, min_c, days = _compute_monthly_stats(row)
            if days == 0:
                continue
            readings.append(
                StreamTemperatureReading(
                    station_id=station_id,
                    station_name=station_name,
                    lat=float(s_lat),
                    lng=float(s_lng),
                    jurisdiction="CA-ON",
                    year=row[0],
                    month=row[1],
                    mean_temp_c=mean_c,
                    max_temp_c=max_c,
                    min_temp_c=min_c,
                    days_measured=days,
                )
            )

        if not readings:
            continue

        all_readings.extend(readings)

        summer = [r for r in readings if r.month in (7, 8) and r.mean_temp_c is not None]
        summer_means = [r.mean_temp_c for r in summer]
        summer_maxes = [r.max_temp_c for r in summer if r.max_temp_c is not None]

        n_means = len(summer_means)
        n_maxes = len(summer_maxes)
        # Require at least 3 summer-month readings (≥1.5 years of Jul+Aug) before classifying.
        summer_mean_c = round(sum(summer_means) / n_means, 2) if n_means >= 3 else None
        summer_max_c = round(sum(summer_maxes) / n_maxes, 2) if n_maxes >= 3 else None

        years_of_data = len({r.year for r in readings})
        regime = _classify_regime(summer_mean_c)

        all_summaries.append(
            StreamTemperatureSummary(
                station_id=station_id,
                station_name=station_name,
                lat=float(s_lat),
                lng=float(s_lng),
                jurisdiction="CA-ON",
                summer_mean_c=summer_mean_c,
                summer_max_c=summer_max_c,
                thermal_regime=regime,
                years_of_data=years_of_data,
                species_notes=_species_notes(regime),
            )
        )

    return all_readings, all_summaries


def _compute_monthly_stats(
    row: tuple,
) -> tuple[float | None, float | None, float | None, int]:
    """Extract monthly mean/max/min and day count from a DLY_TEMPERATURES row.

    Row layout (from _TEMP_QUERY):
      [0]=YEAR [1]=MONTH [2]=NO_DATES [3..33]=MAX1..31 [34..64]=MIN1..31
    """
    daily_means: list[float] = []
    daily_maxes: list[float] = []
    daily_mins: list[float] = []

    for d in range(1, 32):
        mx = row[2 + d]   # MAX_d: row[3] for d=1, row[33] for d=31
        mn = row[33 + d]  # MIN_d: row[34] for d=1, row[64] for d=31
        if mx is not None and mn is not None:
            daily_means.append((mx + mn) / 2.0)
            daily_maxes.append(mx)
            daily_mins.append(mn)

    count = len(daily_means)
    if count == 0:
        return None, None, None, 0

    return (
        round(sum(daily_means) / count, 2),
        round(max(daily_maxes), 2),
        round(min(daily_mins), 2),
        count,
    )


def _classify_regime(summer_mean_c: float | None) -> str:
    if summer_mean_c is None:
        return "unknown"
    if summer_mean_c < 18.0:
        return "coldwater"
    if summer_mean_c <= 23.0:
        return "coolwater"
    return "warmwater"


def _species_notes(regime: str) -> str:
    return _SPECIES_NOTES.get(regime, _SPECIES_NOTES["unknown"])


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
