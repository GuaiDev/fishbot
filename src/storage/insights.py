"""Behavioral insights CRUD via sqlite-utils."""

from datetime import datetime
from typing import Any

from sqlite_utils.db import Database

from src.models.behavioral_insight import BehavioralInsight


def insert_insight(db: Database, insight: BehavioralInsight) -> int:
    row = _to_row(insight)
    row.pop("id", None)
    return db["behavioral_insights"].insert(row).last_pk  # type: ignore[return-value]


def refine_insight(db: Database, prior_id: int, new_insight: BehavioralInsight) -> int:
    prior = get_insight(db, prior_id)
    if prior is None:
        raise ValueError(f"No insight with id={prior_id}")
    db["behavioral_insights"].update(prior_id, {"is_current": 0})
    new_insight.version = prior.version + 1
    new_insight.is_current = True
    new_id = insert_insight(db, new_insight)
    contradict_insight(db, old_id=prior_id, new_id=new_id)
    return new_id


def get_insight(db: Database, insight_id: int) -> BehavioralInsight | None:
    rows = list(db["behavioral_insights"].rows_where("id = ?", [insight_id]))
    if not rows:
        return None
    return _row_to_insight(rows[0])


def query_insights(
    db: Database,
    species: str,
    condition_type: str | None = None,
    current_only: bool = True,
) -> list[BehavioralInsight]:
    where = "LOWER(species) LIKE ?"
    params: list[Any] = [f"%{species.lower()}%"]

    if condition_type:
        where += " AND condition_type = ?"
        params.append(condition_type)

    if current_only:
        where += " AND is_current = 1"

    rows = db["behavioral_insights"].rows_where(where, params, order_by="created_at desc")
    return [_row_to_insight(r) for r in rows]


def mark_user_verified(db: Database, insight_id: int) -> None:
    db["behavioral_insights"].update(insight_id, {"user_verified": 1})


def contradict_insight(db: Database, old_id: int, new_id: int) -> None:
    db["behavioral_insights"].update(old_id, {"contradicted_by": new_id})


def _to_row(insight: BehavioralInsight) -> dict[str, Any]:
    return {
        "id": insight.id,
        "species": insight.species,
        "condition_type": insight.condition_type,
        "condition_context": insight.condition_context,
        "conclusion": insight.conclusion,
        "confidence": insight.confidence,
        "source_type": insight.source_type,
        "source_detail": insight.source_detail,
        "evidence_count": insight.evidence_count,
        "version": insight.version,
        "is_current": 1 if insight.is_current else 0,
        "contradicted_by": insight.contradicted_by,
        "user_verified": 1 if insight.user_verified else 0,
        "jurisdiction": insight.jurisdiction,
        "last_validated": insight.last_validated.isoformat(),
        "created_at": insight.created_at.isoformat(),
    }


def _row_to_insight(row: dict[str, Any]) -> BehavioralInsight:
    d = dict(row)
    d["is_current"] = bool(d["is_current"])
    d["user_verified"] = bool(d["user_verified"])
    d["last_validated"] = datetime.fromisoformat(d["last_validated"])
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    return BehavioralInsight.model_validate(d)
