"""High-level trip logging service.

Orchestrates: NL parsing → segment snapping → DB insert → insight generation.
"""

import logging
from collections import Counter
from datetime import datetime

from sqlite_utils.db import Database

from src.services.trip_parser import parse_trip_from_text
from src.storage.trips import get_parsed_trips, insert_parsed_trip

logger = logging.getLogger(__name__)


def log_trip(
    db: Database,
    text: str,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> dict:
    """Parse a natural-language trip description and persist it.

    Returns a summary dict with trip_id, parsed data, snap info, and a
    human-readable confirmation string.
    """
    parsed = parse_trip_from_text(text, user_lat=user_lat, user_lng=user_lng, db=db)

    if parsed.get("status") == "needs_location":
        return {
            "trip_id": None,
            "parsed": {},
            "segment_snapped": False,
            "segment_name": "",
            "insights_generated": 0,
            "confirmation": parsed["message"],
        }

    parsed["raw_text"] = text
    trip_id = insert_parsed_trip(db, parsed)

    ogf_id = parsed.get("ogf_id")
    seg_name = parsed.get("segment_watercourse_name")
    snapped = ogf_id is not None
    insights_generated = 0

    # Insert habitat/presence insights for caught species at a known segment
    if snapped and parsed.get("species_caught"):
        insights_generated = _maybe_insert_species_insights(db, parsed, ogf_id, seg_name)

    # Mark unproductive segments as seen-before (0.3× exploration penalty)
    if parsed.get("was_productive") is False and ogf_id:
        _penalise_segment(db, ogf_id)

    confirmation = _build_confirmation(parsed, trip_id, snapped, seg_name)

    return {
        "trip_id": trip_id,
        "parsed": parsed,
        "segment_snapped": snapped,
        "segment_name": seg_name or "",
        "insights_generated": insights_generated,
        "confirmation": confirmation,
    }


def get_trip_summary(db: Database) -> str:
    """Return a natural-language summary of all logged trips for agent context."""
    if "parsed_trips" not in db.table_names():
        return "No trips logged yet."

    trips = get_parsed_trips(db, limit=500)
    if not trips:
        return "No trips logged yet."

    n = len(trips)

    # Species counts
    caught_counter: Counter = Counter()
    waterbody_counter: Counter = Counter()
    productive_conditions: list[str] = []

    for t in trips:
        for sp in t.get("species_caught") or []:
            if sp:
                caught_counter[sp] += 1
        wb = t.get("waterbody_name") or t.get("location_description", "")
        if wb:
            waterbody_counter[wb] += 1
        if t.get("was_productive") and t.get("flow_trend"):
            productive_conditions.append(t["flow_trend"])

    parts = [f"You have logged {n} trip{'s' if n != 1 else ''}."]

    if caught_counter:
        top = caught_counter.most_common(3)
        sp_str = ", ".join(f"{sp} ({c} trip{'s' if c != 1 else ''})" for sp, c in top)
        parts.append(f"Most-caught species: {sp_str}.")
    else:
        parts.append("No fish caught yet in the log.")

    if waterbody_counter:
        top_wb = waterbody_counter.most_common(1)[0][0]
        parts.append(f"Most-visited water: {top_wb}.")

    if productive_conditions:
        flow_counts = Counter(productive_conditions)
        best_flow = flow_counts.most_common(1)[0][0]
        parts.append(f"Best conditions: flow {best_flow}.")

    # Recent trip date
    dates = [
        t.get("trip_date") or t.get("logged_at", "")[:10]
        for t in trips
        if t.get("trip_date") or t.get("logged_at")
    ]
    if dates:
        parts.append(f"Last logged: {max(dates)}.")

    return " ".join(parts)


# ── helpers ───────────────────────────────────────────────────────────────────


def _maybe_insert_species_insights(
    db: Database,
    parsed: dict,
    ogf_id: int,
    seg_name: str | None,
) -> int:
    """Generate one presence insight per caught species at the snapped segment."""
    from src.models.behavioral_insight import BehavioralInsight
    from src.storage.insights import insert_insight

    inserted = 0
    trip_date = parsed.get("date") or datetime.now().strftime("%Y-%m-%d")
    loc = seg_name or parsed.get("location_description", f"segment {ogf_id}")
    stream_order = parsed.get("segment_stream_order")
    order_note = f" (order-{stream_order} stream)" if stream_order else ""

    for species in parsed.get("species_caught") or []:
        if not species:
            continue
        habitat_notes = parsed.get("habitat_notes") or ""
        spot_type = parsed.get("spot_type") or ""
        context_parts = [p for p in [spot_type, habitat_notes] if p]
        condition_context = ", ".join(context_parts) if context_parts else "personal_trip_log"

        conclusion = (
            f"{species} confirmed caught at {loc}{order_note} on {trip_date} "
            f"(personal trip log, ogf_id={ogf_id})"
        )
        if parsed.get("water_clarity"):
            conclusion += f". Water clarity: {parsed['water_clarity']}"
        if parsed.get("water_level"):
            conclusion += f", level: {parsed['water_level']}"

        insight = BehavioralInsight(
            species=species,
            condition_type="habitat",
            condition_context=condition_context,
            conclusion=conclusion,
            confidence="high",
            source_type="trip_log",
            source_detail=f"personal trip log: {loc}, {trip_date}",
            evidence_count=1,
            jurisdiction="CA-ON",
        )
        try:
            insert_insight(db, insight)
            inserted += 1
        except Exception as e:
            logger.warning("Failed to insert insight for %s: %s", species, e)

    return inserted


def _penalise_segment(db: Database, ogf_id: int) -> None:
    """Add an unproductive segment to dismissed_segments for 0.3× exploration penalty."""
    try:
        db["dismissed_segments"].upsert(
            {
                "ogf_id": ogf_id,
                "dismissed_at": datetime.now().isoformat(),
                "reason": "unproductive_trip_log",
            },
            pk="ogf_id",
        )
    except Exception as e:
        logger.warning("Failed to penalise segment %s: %s", ogf_id, e)


def _build_confirmation(
    parsed: dict,
    trip_id: int,
    snapped: bool,
    seg_name: str | None,
) -> str:
    lines = [f"Trip #{trip_id} logged."]

    date_str = parsed.get("date") or "date unknown"
    loc = parsed.get("location_description") or "location unknown"
    lines.append(f"  Date: {date_str} — {loc}")

    caught = parsed.get("species_caught") or []
    observed = parsed.get("species_observed") or []
    if caught:
        lines.append(f"  Caught: {', '.join(caught)}")
    if observed and observed != caught:
        lines.append(f"  Observed: {', '.join(observed)}")
    if not caught and not observed:
        lines.append("  No species recorded.")

    cond_parts = []
    conds = parsed.get("conditions") or {}
    if conds.get("water_level"):
        cond_parts.append(f"water {conds['water_level']}")
    if conds.get("water_clarity"):
        cond_parts.append(conds["water_clarity"])
    if conds.get("flow_trend"):
        cond_parts.append(f"flow {conds['flow_trend']}")
    if cond_parts:
        lines.append(f"  Conditions: {', '.join(cond_parts)}")

    if snapped:
        dist = parsed.get("distance_to_segment_m")
        name = seg_name or f"segment {parsed.get('ogf_id')}"
        dist_str = f" ({int(dist)}m away)" if dist else ""
        lines.append(f"  Snapped to: {name}{dist_str}")
    else:
        lines.append("  No OHN segment found within 5km.")

    return "\n".join(lines)
