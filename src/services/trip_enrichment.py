"""
Trip enrichment service.
After a session is logged, matches stops against behavioral insights,
identifies condition gaps, and prepares follow-up questions.
"""
import json
from datetime import datetime

from sqlite_utils import Database

from src.models.behavioral_insight import BehavioralInsight
from src.storage.insights import check_conflicts, get_insight, refine_insight

# How many confirmations needed to escalate confidence
CONFIRMATIONS_TO_ESCALATE = {
    "low": 2,     # 2 confirmations → medium
    "medium": 4,  # 4 confirmations → high
    "high": 999,  # already at max
}

# How many contradictions to trigger refinement
CONTRADICTIONS_TO_REFINE = 2


def get_season(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "fall"


def match_insights_to_stop(db: Database, stop: dict) -> list:
    """Find behavioral insights that match this stop.

    Matches on: species caught + location proximity + season.
    Returns list of matching insight dicts.
    """
    species_list = json.loads(stop.get("species_caught") or "[]")
    lat = stop.get("lat")
    lng = stop.get("lng")

    session_id = stop.get("session_id")
    season = None
    if session_id is not None:
        try:
            session_rows = list(db["sessions"].rows_where("id = ?", [session_id]))
            if session_rows:
                date_str = session_rows[0].get("date")
                if date_str:
                    month = datetime.fromisoformat(date_str).month
                    season = get_season(month)
        except Exception:
            pass

    matched = []
    for species in species_list:
        clean_species = species.replace("(uncertain)", "").strip()
        conflicts = check_conflicts(
            db, clean_species,
            lat=lat, lng=lng,
            condition_season=season,
            radius_km=1.0,
        )
        for insight in conflicts:
            matched.append({
                "insight": insight,
                "species": clean_species,
                "season": season,
            })

    return matched


def identify_condition_gaps(stop: dict, insight: BehavioralInsight) -> list[str]:
    """Compare what we know about this stop against what the insight cares about.

    Returns a list of condition fields we're missing that would be useful.
    """
    gaps = []
    conclusion_lower = (insight.conclusion or "").lower()

    weather_keywords = ["rain", "overcast", "sunny", "cloud", "storm", "front", "pressure"]
    if any(kw in conclusion_lower for kw in weather_keywords):
        if not stop.get("weather_notes"):
            gaps.append("weather")

    technique_keywords = ["cut bait", "worm", "corn", "lure", "jig", "rig", "packbait"]
    if any(kw in conclusion_lower for kw in technique_keywords):
        if not stop.get("technique") and not stop.get("gear"):
            gaps.append("technique")

    water_keywords = ["high water", "low water", "clear", "turbid", "flood", "flow"]
    if any(kw in conclusion_lower for kw in water_keywords):
        if not stop.get("water_level") and not stop.get("water_clarity"):
            gaps.append("water_conditions")

    time_keywords = ["dawn", "dusk", "midday", "morning", "evening", "night"]
    if any(kw in conclusion_lower for kw in time_keywords):
        notes_lower = (stop.get("notes") or "").lower()
        if not any(kw in notes_lower for kw in time_keywords):
            gaps.append("time_of_day")

    return gaps


def build_followup_question(
    stop: dict,
    insight: BehavioralInsight,
    gaps: list[str],
    was_productive: bool,
) -> str | None:
    """Build one focused follow-up question based on the most important gap.

    Returns None if no question is needed.
    """
    if not gaps:
        return None

    location = stop.get("location_name") or stop.get("location_text") or "that spot"
    species = insight.species

    if "weather" in gaps:
        if was_productive:
            return (
                f"You caught {species} at {location} — what were conditions like? "
                f"Overcast or sunny? Any recent rain before the trip?"
            )
        else:
            return (
                f"You blanked for {species} at {location} — what was the weather like? "
                f"Was it sunny and stable, or had there been rain recently?"
            )

    if "technique" in gaps:
        if was_productive:
            return (
                f"Nice catch at {location} — what were you using for {species}? "
                f"Bait, lure, or rig?"
            )
        else:
            return f"No {species} at {location} this time — what technique were you using?"

    if "water_conditions" in gaps:
        return (
            f"What were water conditions like at {location}? "
            f"High/low/normal flow, and clear or turbid?"
        )

    if "time_of_day" in gaps:
        return f"What time of day were you fishing {location} for {species}?"

    return None


def update_insight_confidence(
    db: Database,
    insight: BehavioralInsight,
    was_productive: bool,
    stop: dict,
    client,
) -> BehavioralInsight:
    """Update insight confidence based on whether the trip confirmed or contradicted it."""
    current_confidence = insight.confidence
    evidence_count = insight.evidence_count or 0

    if was_productive:
        new_evidence = evidence_count + 1
        threshold = CONFIRMATIONS_TO_ESCALATE.get(current_confidence, 999)

        if new_evidence >= threshold:
            new_confidence = {
                "low": "medium",
                "medium": "high",
                "high": "high",
            }.get(current_confidence, current_confidence)
        else:
            new_confidence = current_confidence

        db["behavioral_insights"].update(insight.id, {
            "evidence_count": new_evidence,
            "confidence": new_confidence,
            "last_validated": datetime.now().isoformat(),
        })
        return get_insight(db, insight.id)

    else:
        current_detail = insight.source_detail or ""
        contradiction_count = current_detail.count("[contradicted")

        if contradiction_count + 1 >= CONTRADICTIONS_TO_REFINE:
            new_conclusion = _synthesize_nuanced_conclusion(insight, stop, client)
            new_insight = BehavioralInsight(
                species=insight.species,
                condition_type=insight.condition_type,
                condition_context=insight.condition_context,
                conclusion=new_conclusion,
                recommendation=insight.recommendation,
                confidence="low",
                source_type="agent_synthesis",
                source_detail=f"Refined after {contradiction_count + 1} contradictions",
                evidence_count=0,
                lat=insight.lat,
                lng=insight.lng,
                location_name=insight.location_name,
                condition_season=insight.condition_season,
                jurisdiction=insight.jurisdiction,
            )
            new_id = refine_insight(db, insight.id, new_insight)
            return get_insight(db, new_id)
        else:
            contradiction_note = f" [contradicted {datetime.now().date()}]"
            db["behavioral_insights"].update(insight.id, {
                "source_detail": current_detail + contradiction_note,
            })
            return get_insight(db, insight.id)


def _synthesize_nuanced_conclusion(
    insight: BehavioralInsight,
    contradicting_stop: dict,
    client,
) -> str:
    """Use Haiku to synthesize a more nuanced conclusion after contradictions."""
    if client is None:
        return insight.conclusion + " (contradicted — conditions may matter)"

    prompt = (
        f"A fishing insight has been contradicted by a recent trip. "
        f"Write a more nuanced 2-3 sentence conclusion that acknowledges both "
        f"the original finding and the contradiction.\n\n"
        f"Original insight: {insight.conclusion}\n"
        f"Contradicting trip: {json.dumps(contradicting_stop, default=str)}\n\n"
        f"Write ONLY the revised conclusion, no preamble."
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def enrich_session(
    db: Database,
    session_id: int,
    client,
) -> list[dict]:
    """Main entry point. Called after a session is logged.

    Returns a list of follow-up questions (max 1 — the most important overall).
    """
    stops = list(db["stops"].rows_where("session_id = ?", [session_id]))

    if not stops:
        return []

    questions = []

    for stop in stops:
        was_productive = bool(stop.get("was_productive"))
        matched = match_insights_to_stop(db, stop)

        for match in matched:
            insight = match["insight"]
            update_insight_confidence(db, insight, was_productive, stop, client)

            gaps = identify_condition_gaps(stop, insight)
            question = build_followup_question(stop, insight, gaps, was_productive)
            if question:
                questions.append({
                    "question": question,
                    "insight_id": insight.id,
                    "stop_id": stop.get("id"),
                    "species": match["species"],
                })

    # Prioritise follow-up questions about unproductive stops at known spots
    questions.sort(key=lambda q: (
        0 if "blanked" in q["question"].lower() or "no " in q["question"].lower() else 1
    ))

    return questions[:1]
