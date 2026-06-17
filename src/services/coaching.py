"""
On-demand coaching service.
Diagnoses why a user is struggling with a species, spot, or technique
by cross-referencing trip logs, behavioral insights, habitat data,
and community knowledge.
"""
import json

from sqlite_utils import Database

from src.agent.client import get_client

HAIKU = "claude-haiku-4-5-20251001"

_STOP_COLS = [
    "id", "location_name", "location_text", "species_caught",
    "party_species_caught", "was_productive", "technique",
    "gear", "water_level", "water_clarity", "weather_notes",
    "notes", "date", "date_approx",
]

_LOC_STOP_COLS = [
    "id", "location_name", "location_text", "species_caught",
    "was_productive", "technique", "gear", "water_level",
    "water_clarity", "weather_notes", "notes", "date", "date_approx",
]


def get_species_coaching(
    db: Database,
    species: str,
    specific_question: str | None = None,
) -> str:
    """Analyze the user's logged history with a species and identify gaps,
    patterns, and specific improvement opportunities."""
    rows = db.execute("""
        SELECT st.id, st.location_name, st.location_text, st.species_caught,
               st.party_species_caught, st.was_productive, st.technique,
               st.gear, st.water_level, st.water_clarity, st.weather_notes,
               st.notes, s.date, s.date_approx
        FROM stops st
        JOIN sessions s ON st.session_id = s.id
    """).fetchall()

    all_stops = [dict(zip(_STOP_COLS, r)) for r in rows]

    species_lower = species.lower()
    caught_stops = []
    blank_stops = []

    for stop in all_stops:
        caught = json.loads(stop["species_caught"] or "[]")
        party_caught = json.loads(stop["party_species_caught"] or "[]")
        productive = bool(stop["was_productive"])

        species_in_catch = any(species_lower in s.lower() for s in caught)
        species_in_party = any(species_lower in s.lower() for s in party_caught)

        if species_in_catch:
            caught_stops.append(stop)
        elif not productive and not species_in_party:
            blank_stops.append(stop)

    insights = db.execute("""
        SELECT condition_type, condition_context, conclusion, confidence,
               recommendation, condition_season, location_name
        FROM behavioral_insights
        WHERE LOWER(species) LIKE ? AND is_current = 1
        ORDER BY confidence DESC, created_at DESC
    """, [f"%{species_lower}%"]).fetchall()

    context_parts = []

    if caught_stops:
        context_parts.append(f"SUCCESSFUL CATCHES ({len(caught_stops)} stops):")
        for s in caught_stops:
            loc = s["location_name"] or s["location_text"] or "unknown"
            date = s["date"] or s["date_approx"] or "undated"
            tech = s["technique"] or "unrecorded"
            gear = s["gear"] or "unrecorded"
            conditions = []
            if s["water_level"]: conditions.append(s["water_level"] + " water")
            if s["water_clarity"]: conditions.append(s["water_clarity"])
            if s["weather_notes"]: conditions.append(s["weather_notes"])
            cond_str = ", ".join(conditions) or "unrecorded"
            context_parts.append(
                f"  - {loc} ({date}): technique={tech}, gear={gear}, "
                f"conditions={cond_str}"
            )
            if s["notes"]:
                context_parts.append(f"    notes: {s['notes'][:200]}")
    else:
        context_parts.append(f"SUCCESSFUL CATCHES: None logged for {species}")

    if insights:
        context_parts.append(f"\nSTORED INSIGHTS ({len(insights)}):")
        for ins in insights:
            context_parts.append(f"  - [{ins[3]} confidence] {ins[2][:200]}")
            if ins[4]:
                context_parts.append(f"    recommendation: {ins[4]}")

    context_parts.append(f"\nTOTAL BLANK STOPS IN LOG: {len(blank_stops)}")
    context_parts.append(
        "(Note: blank stops may or may not have been targeting this species "
        "— species targeting is not always recorded)"
    )

    context = "\n".join(context_parts)
    question = specific_question or f"What should I do differently to catch more {species}?"

    prompt = f"""You are a personal fishing coach analyzing a user's logged fishing data.
The user is asking: "{question}"

Here is their complete logged history relevant to {species}:

{context}

Based ONLY on this logged data (do not invent sessions or patterns not shown above),
provide a specific, actionable coaching response. Be honest about data limitations.

Structure your response as:
1. What the data shows (patterns in successful catches if any)
2. What's missing or unclear from the log
3. Specific things to try differently, grounded in the data
4. One concrete experiment to run on the next trip

If there are no logged catches, say so directly and focus on what the habitat
data and stored insights suggest. Do not pretend there are patterns when the
log is empty.

Keep the response concise — 150-250 words. No generic fishing tips that aren't
grounded in this specific user's data."""

    client = get_client()
    resp = client.messages.create(
        model=HAIKU,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def get_location_coaching(
    db: Database,
    location_query: str,
    specific_question: str | None = None,
) -> str:
    """Analyze the user's history at a specific location and identify
    what's working, what isn't, and what to try differently."""
    rows = db.execute("""
        SELECT st.id, st.location_name, st.location_text, st.species_caught,
               st.was_productive, st.technique, st.gear, st.water_level,
               st.water_clarity, st.weather_notes, st.notes,
               s.date, s.date_approx
        FROM stops st
        JOIN sessions s ON st.session_id = s.id
        WHERE LOWER(st.location_name) LIKE ?
           OR LOWER(st.location_text) LIKE ?
    """, [f"%{location_query.lower()}%", f"%{location_query.lower()}%"]).fetchall()

    if not rows:
        return f"No logged trips found at '{location_query}'. Log a session there first."

    all_stops = [dict(zip(_LOC_STOP_COLS, r)) for r in rows]
    productive = [s for s in all_stops if s["was_productive"]]
    unproductive = [s for s in all_stops if not s["was_productive"]]

    context_parts = [
        f"LOCATION: {location_query}",
        f"Total visits: {len(all_stops)} ({len(productive)} productive, "
        f"{len(unproductive)} blank)",
        "",
    ]

    for stop in all_stops:
        date = stop["date"] or stop["date_approx"] or "undated"
        caught = json.loads(stop["species_caught"] or "[]")
        species_str = ", ".join(caught) if caught else "nothing"
        tech = stop["technique"] or "unrecorded"
        conditions = []
        if stop["water_level"]: conditions.append(stop["water_level"] + " water")
        if stop["water_clarity"]: conditions.append(stop["water_clarity"])
        if stop["weather_notes"]: conditions.append(stop["weather_notes"])
        cond_str = ", ".join(conditions) or "unrecorded"
        context_parts.append(
            f"  {date}: caught {species_str} | tech={tech} | {cond_str}"
        )
        if stop["notes"]:
            context_parts.append(f"    {stop['notes'][:150]}")

    context = "\n".join(context_parts)
    question = specific_question or f"What should I do differently at {location_query}?"

    prompt = f"""You are a personal fishing coach analyzing a user's logged fishing data.
The user is asking: "{question}"

Their complete logged history at this location:
{context}

Based ONLY on this data, provide specific coaching. Be honest about what the
data does and doesn't show. If patterns exist (conditions that correlated with
success/failure, techniques that worked), highlight them. If the log is too
sparse for patterns, say so.

Structure: what worked, what didn't, one specific thing to try next visit.
Keep it to 150-200 words. No generic tips not grounded in this data."""

    client = get_client()
    resp = client.messages.create(
        model=HAIKU,
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
