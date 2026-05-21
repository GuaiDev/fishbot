"""Agent-facing service for behavioral insights."""

import json

from src.models.behavioral_insight import BehavioralInsight
from src.storage.database import get_db
from src.storage.insights import insert_insight, query_insights


def get_behavioral_insights_for_agent(
    species: str,
    condition_type: str | None = None,
) -> str:
    db = get_db()
    insights = query_insights(db, species=species, condition_type=condition_type, current_only=True)

    if not insights:
        msg = f"No behavioral insights stored for '{species}'"
        if condition_type:
            msg += f" with condition_type='{condition_type}'"
        return json.dumps(
            {"species": species, "condition_type": condition_type, "count": 0, "note": msg}
        )

    return json.dumps(
        {
            "species": species,
            "condition_type": condition_type,
            "count": len(insights),
            "insights": [
                {
                    "id": i.id,
                    "condition_type": i.condition_type,
                    "condition_context": i.condition_context,
                    "conclusion": i.conclusion,
                    "confidence": i.confidence,
                    "source_type": i.source_type,
                    "evidence_count": i.evidence_count,
                    "user_verified": i.user_verified,
                    "jurisdiction": i.jurisdiction,
                    "last_validated": i.last_validated.isoformat(),
                }
                for i in insights
            ],
        }
    )


def record_behavioral_insight_for_agent(
    species: str,
    condition_type: str,
    condition_context: str,
    conclusion: str,
    confidence: str,
    source_type: str,
    source_detail: str,
    evidence_count: int,
    jurisdiction: str | None = None,
) -> str:
    if confidence == "unverified":
        return json.dumps(
            {
                "error": (
                    "Cannot store unverified conclusions. "
                    "Set confidence to 'low', 'medium', or 'high' with supporting evidence."
                )
            }
        )

    insight = BehavioralInsight(
        species=species,
        condition_type=condition_type,  # type: ignore[arg-type]
        condition_context=condition_context,
        conclusion=conclusion,
        confidence=confidence,  # type: ignore[arg-type]
        source_type=source_type,  # type: ignore[arg-type]
        source_detail=source_detail,
        evidence_count=evidence_count,
        jurisdiction=jurisdiction,
    )

    db = get_db()
    insight_id = insert_insight(db, insight)

    return json.dumps(
        {
            "success": True,
            "insight_id": insight_id,
            "species": species,
            "condition_type": condition_type,
            "conclusion": conclusion,
            "confidence": confidence,
        }
    )
