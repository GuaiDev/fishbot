"""OSM water features and access point CRUD via sqlite-utils."""

import json
from datetime import datetime
from typing import Any

from sqlite_utils.db import Database

from src.models.water_feature import AccessPoint, WaterFeature

_KM_PER_DEGREE = 111.0


def upsert_water_features(db: Database, features: list[WaterFeature]) -> None:
    rows = [_feature_to_row(f) for f in features]
    db["water_features"].upsert_all(rows, pk="osm_id")


def upsert_access_points(db: Database, points: list[AccessPoint]) -> None:
    rows = [_point_to_row(p) for p in points]
    db["access_points"].upsert_all(rows, pk="osm_id")


def query_water_features(
    db: Database,
    lat: float,
    lng: float,
    radius_km: float,
    feature_type: str | None = None,
) -> list[WaterFeature]:
    deg = radius_km / _KM_PER_DEGREE
    where = "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?"
    params: list[Any] = [lat - deg, lat + deg, lng - deg, lng + deg]

    if feature_type:
        where += " AND feature_type = ?"
        params.append(feature_type)

    rows = db["water_features"].rows_where(where, params)
    return [_row_to_feature(r) for r in rows]


def query_access_points(
    db: Database,
    lat: float,
    lng: float,
    radius_km: float,
    access_type: str | None = None,
) -> list[AccessPoint]:
    deg = radius_km / _KM_PER_DEGREE
    where = "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?"
    params: list[Any] = [lat - deg, lat + deg, lng - deg, lng + deg]

    if access_type:
        where += " AND access_type = ?"
        params.append(access_type)

    rows = db["access_points"].rows_where(where, params)
    return [_row_to_point(r) for r in rows]


def _feature_to_row(f: WaterFeature) -> dict[str, Any]:
    return {
        "osm_id": f.osm_id,
        "feature_type": f.feature_type,
        "name": f.name,
        "lat": f.lat,
        "lng": f.lng,
        "jurisdiction": f.jurisdiction,
        "area_m2": f.area_m2,
        "tags": json.dumps(f.tags),
        "fetched_at": f.fetched_at.isoformat(),
    }


def _row_to_feature(row: dict[str, Any]) -> WaterFeature:
    decoded = dict(row)
    decoded["tags"] = json.loads(row["tags"])
    decoded["fetched_at"] = datetime.fromisoformat(row["fetched_at"])
    return WaterFeature.model_validate(decoded)


def _point_to_row(p: AccessPoint) -> dict[str, Any]:
    return {
        "osm_id": p.osm_id,
        "access_type": p.access_type,
        "name": p.name,
        "lat": p.lat,
        "lng": p.lng,
        "jurisdiction": p.jurisdiction,
        "tags": json.dumps(p.tags),
        "fetched_at": p.fetched_at.isoformat(),
    }


def _row_to_point(row: dict[str, Any]) -> AccessPoint:
    decoded = dict(row)
    decoded["tags"] = json.loads(row["tags"])
    decoded["fetched_at"] = datetime.fromisoformat(row["fetched_at"])
    return AccessPoint.model_validate(decoded)
