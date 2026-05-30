"""Storage layer for SDM presence-probability predictions."""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlite_utils.db import Database

_PARQUET_PATH = Path("data/processed/sdm_feature_matrix.parquet")
_KM_PER_DEGREE = 111.0


def upsert_predictions(
    db: Database,
    species: str,
    predictions: pd.Series,
    model_version: str = "2c-v1",
) -> None:
    """Store presence probabilities for all segments.

    predictions: Series indexed by ogf_id with probability values.
    Centroid coordinates are looked up from the feature matrix parquet for
    spatial query support.
    """
    fm = pd.read_parquet(_PARQUET_PATH, columns=["ogf_id", "centroid_lat", "centroid_lng"])
    centroids = fm.set_index("ogf_id")

    now = datetime.now().isoformat()
    rows = []
    for ogf_id, prob in predictions.items():
        if ogf_id not in centroids.index:
            continue
        rows.append(
            {
                "ogf_id": int(ogf_id),
                "species": species,
                "presence_probability": float(prob),
                "model_version": model_version,
                "predicted_at": now,
                "centroid_lat": float(centroids.loc[ogf_id, "centroid_lat"]),
                "centroid_lng": float(centroids.loc[ogf_id, "centroid_lng"]),
            }
        )

    # Batch upsert to avoid per-row overhead
    _ensure_table(db)
    db["sdm_predictions"].upsert_all(rows, pk=["ogf_id", "species"])


def query_predictions(
    db: Database,
    lat: float,
    lng: float,
    radius_km: float,
    species: str | None = None,
    min_probability: float = 0.3,
) -> list[dict[str, Any]]:
    """Return segments within radius with predictions above threshold, sorted by probability."""
    if "sdm_predictions" not in db.table_names():
        return []

    deg = radius_km / _KM_PER_DEGREE
    where = (
        "centroid_lat BETWEEN ? AND ? "
        "AND centroid_lng BETWEEN ? AND ? "
        "AND presence_probability >= ?"
    )
    params: list[Any] = [lat - deg, lat + deg, lng - deg, lng + deg, min_probability]

    if species is not None:
        where += " AND LOWER(species) = ?"
        params.append(species.lower())

    rows = list(
        db["sdm_predictions"].rows_where(where, params, order_by="presence_probability desc")
    )
    return rows


def _ensure_table(db: Database) -> None:
    if "sdm_predictions" not in db.table_names():
        db["sdm_predictions"].create(
            {
                "ogf_id": int,
                "species": str,
                "presence_probability": float,
                "model_version": str,
                "predicted_at": str,
                "centroid_lat": float,
                "centroid_lng": float,
            },
            pk=["ogf_id", "species"],
        )
        db["sdm_predictions"].create_index(
            ["species", "centroid_lat", "centroid_lng"],
            if_not_exists=True,
        )
