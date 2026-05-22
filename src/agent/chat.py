"""Interactive chat loop using the Anthropic SDK + rich for terminal I/O."""

import json
from typing import Any

from anthropic import Anthropic, APIError
from rich.console import Console

from src.agent.client import get_client, get_model
from src.agent.system_prompt import assemble, load_template
from src.jurisdictions.registry import get_jurisdiction
from src.storage.database import get_db
from src.storage.profile import load_profile
from src.storage.trips import recent_trips

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}


def run_chat() -> None:
    console = Console()

    try:
        client = get_client()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        return

    profile = load_profile()
    db = get_db()
    trips = recent_trips(db, limit=5)
    home = get_jurisdiction(profile.home_jurisdiction)
    system_prompt = assemble(load_template(), profile, trips, home)
    model = get_model()

    console.print(f"[dim]fishbot — {model} — type /exit to quit[/dim]")
    console.print()

    messages: list[dict] = []
    tools = _tools(profile)

    while True:
        try:
            user_input = console.input("[bold cyan]> [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print("[dim]bye[/dim]")
            return

        if not user_input:
            continue

        if user_input.lower() in EXIT_COMMANDS:
            console.print("[dim]bye[/dim]")
            return

        messages.append({"role": "user", "content": user_input})

        try:
            _agentic_loop(client, model, system_prompt, messages, tools, console)
        except APIError as e:
            console.print(f"[red]API error: {e}[/red]")
            messages.pop()
            continue
        except KeyboardInterrupt:
            console.print()
            console.print("[dim](interrupted)[/dim]")
            messages.pop()
            continue


def _agentic_loop(
    client: Anthropic,
    model: str,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    console: Console,
) -> None:
    """Stream a response, handle tool calls, loop until end_turn."""
    while True:
        content_blocks: list[Any] = []

        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            tools=tools,
        ) as stream:
            for text in stream.text_stream:
                console.print(text, end="", markup=False, highlight=False, soft_wrap=True)
            final_msg = stream.get_final_message()
            content_blocks = final_msg.content

        tool_use_blocks = [b for b in content_blocks if b.type == "tool_use"]

        if not tool_use_blocks:
            console.print()
            console.print()
            text = "".join(b.text for b in content_blocks if b.type == "text")
            messages.append({"role": "assistant", "content": text})
            return

        # Tool call detected — execute and continue the loop
        console.print()
        assistant_content = [_normalize_block(b) for b in content_blocks]
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results: list[dict] = []
        for block in tool_use_blocks:
            result = _execute_tool(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})


def _normalize_block(b: Any) -> dict:
    if b.type == "text":
        return {"type": "text", "text": b.text}
    if b.type == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    return {"type": b.type}


def _execute_tool(name: str, inputs: dict) -> str:
    if name == "get_recent_observations":
        from src.services.observations import query_for_agent

        return query_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
            days_back=inputs.get("days_back", 90),
            species_filter=inputs.get("species_filter"),
        )
    if name == "get_conditions":
        from src.services.weather import get_conditions_for_agent

        return get_conditions_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            when=inputs.get("when", "now"),
        )
    if name == "get_pressure_trend":
        from src.services.weather import get_pressure_trend_for_agent

        return get_pressure_trend_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
        )
    if name == "get_tactical_recommendation":
        from src.services.tactical import get_tactical_recommendation_for_agent

        return get_tactical_recommendation_for_agent(
            species=inputs.get("species"),
            lat=inputs.get("lat"),
            lng=inputs.get("lng"),
            water_clarity=inputs.get("water_clarity"),
            water_temp_c=inputs.get("water_temp_c"),
            time_of_day=inputs.get("time_of_day"),
            notes=inputs.get("notes"),
        )
    if name == "get_behavioral_insights":
        from src.services.insights import get_behavioral_insights_for_agent

        return get_behavioral_insights_for_agent(
            species=inputs["species"],
            condition_type=inputs.get("condition_type"),
        )
    if name == "record_behavioral_insight":
        from src.services.insights import record_behavioral_insight_for_agent

        return record_behavioral_insight_for_agent(
            species=inputs["species"],
            condition_type=inputs["condition_type"],
            condition_context=inputs["condition_context"],
            conclusion=inputs["conclusion"],
            confidence=inputs["confidence"],
            source_type=inputs["source_type"],
            source_detail=inputs["source_detail"],
            evidence_count=inputs["evidence_count"],
            jurisdiction=inputs.get("jurisdiction"),
        )
    if name == "get_gbif_observations":
        from src.services.gbif import query_for_agent as gbif_query_for_agent

        return gbif_query_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
            days_back=inputs.get("days_back"),
            species_filter=inputs.get("species_filter"),
        )
    if name == "get_oldest_gbif_record":
        from src.storage.gbif_observations import oldest_gbif_record

        record = oldest_gbif_record(get_db())
        if record is None:
            return json.dumps({"result": "No dated records in the database."})
        return json.dumps(
            {
                "species": record.species,
                "common_name": record.common_name,
                "observed_on": record.observed_on.isoformat() if record.observed_on else None,
                "basis_of_record": record.basis_of_record,
                "dataset_name": record.dataset_name,
                "jurisdiction": record.jurisdiction,
            }
        )
    if name == "get_stream_conditions":
        from src.services.stream_gauge import get_stream_conditions_for_agent

        return get_stream_conditions_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
        )
    return json.dumps({"error": f"Unknown tool: {name}"})


def _tools(profile: Any) -> list[dict]:
    home = profile.home_location
    lat_desc = f"Latitude (your home is {home.lat})" if home else "Latitude"
    lng_desc = f"Longitude (your home is {home.lng})" if home else "Longitude"

    return [
        {
            "name": "get_recent_observations",
            "description": (
                "Query locally-cached iNaturalist fish observation data. "
                "Use when the user asks what fish have been seen near a location, "
                "about recent sightings, species presence, or what's been observed nearby. "
                "Data is cached locally and may be up to 24 hours old."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": lat_desc,
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc,
                    },
                    "radius_km": {
                        "type": "number",
                        "description": "Search radius in kilometres. Default 50.",
                    },
                    "days_back": {
                        "type": "integer",
                        "description": "How many days of history to include. Default 90.",
                    },
                    "species_filter": {
                        "type": "string",
                        "description": (
                            "Optional species name to filter by "
                            "(scientific or common name, partial match)."
                        ),
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_conditions",
            "description": (
                "Get current or forecast weather conditions for a location. "
                "Use when the user asks about the weather, whether conditions are good "
                "for fishing, what it will be like this weekend, or needs "
                "temperature/wind/rain info for planning. "
                "Returns temperature, wind, precipitation, pressure, and a pressure trend note. "
                "Data is cached: 1 hour for current, 6 hours for forecasts."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": lat_desc,
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc,
                    },
                    "when": {
                        "type": "string",
                        "enum": ["now", "tomorrow", "in_3_days", "this_weekend"],
                        "description": "Which time window to return. Default 'now'.",
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_pressure_trend",
            "description": (
                "Get the barometric pressure trend for a location over the past 24-48 hours. "
                "Use when the user asks about pressure, barometric conditions, fish feeding "
                "activity, or whether 'now' is a tactically good time to fish. "
                "Returns trend (rising/steady/falling), numeric deltas, and a fishing note."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": lat_desc,
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc,
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_behavioral_insights",
            "description": (
                "Retrieve accumulated behavioral conclusions for a species "
                "from the persistent knowledge store. "
                "Returns stored insights about behavior, habitat preference, "
                "timing, and gear effectiveness. "
                "Call this before get_tactical_recommendation for any species "
                "— surface relevant insights in your response to ground "
                "recommendations in accumulated knowledge. "
                "Also call when the user asks what you know about a species, "
                "how a species behaves, or requests a behavioral or habitat summary."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "description": (
                            "Species to look up (common or scientific name, partial match)."
                        ),
                    },
                    "condition_type": {
                        "type": "string",
                        "enum": ["behavioral", "habitat", "temporal", "gear"],
                        "description": "Optional filter by conclusion category.",
                    },
                },
                "required": ["species"],
            },
        },
        {
            "name": "record_behavioral_insight",
            "description": (
                "Store a synthesized behavioral conclusion in the persistent knowledge store. "
                "Use after observing a clear pattern across multiple data points, "
                "after the user confirms something, or when a trip log or data source "
                "supports a concrete conclusion. "
                "Confidence must be 'low', 'medium', or 'high' — never 'unverified'. "
                "Do not record speculation or single-observation guesses. "
                "source_type options: agent_synthesis, tactical_rules, inat_pattern, "
                "mnrf_survey, reddit_pattern, trip_log, user_correction."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "description": "Species this conclusion applies to.",
                    },
                    "condition_type": {
                        "type": "string",
                        "enum": ["behavioral", "habitat", "temporal", "gear"],
                        "description": "Category of the conclusion.",
                    },
                    "condition_context": {
                        "type": "string",
                        "description": (
                            "Short label for the specific condition, e.g. 'post-cold-front', "
                            "'riffle-cobble', 'dusk-late-may', 'stained-water-chartreuse'."
                        ),
                    },
                    "conclusion": {
                        "type": "string",
                        "description": "The full natural-language conclusion statement.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": (
                            "Confidence level. Must not be 'unverified' "
                            "— only call this tool with concrete evidence."
                        ),
                    },
                    "source_type": {
                        "type": "string",
                        "enum": [
                            "agent_synthesis",
                            "tactical_rules",
                            "inat_pattern",
                            "mnrf_survey",
                            "reddit_pattern",
                            "trip_log",
                            "user_correction",
                        ],
                        "description": "Where this conclusion came from.",
                    },
                    "source_detail": {
                        "type": "string",
                        "description": (
                            "Free-text description of the specific evidence, "
                            "e.g. '47 iNaturalist observations May-June 2024-2026' "
                            "or 'personal trip log: 8 outings Credit River spring 2026'."
                        ),
                    },
                    "evidence_count": {
                        "type": "integer",
                        "description": "Number of data points supporting this conclusion.",
                    },
                    "jurisdiction": {
                        "type": "string",
                        "description": (
                            "ISO 3166-2 code if this conclusion is jurisdiction-specific "
                            "(e.g. 'CA-ON'). Omit if it applies globally."
                        ),
                    },
                },
                "required": [
                    "species",
                    "condition_type",
                    "condition_context",
                    "conclusion",
                    "confidence",
                    "source_type",
                    "source_detail",
                    "evidence_count",
                ],
            },
        },
        {
            "name": "get_gbif_observations",
            "description": (
                "Query locally-cached GBIF (Global Biodiversity Information Facility) occurrence "
                "data. GBIF aggregates museum specimens, academic surveys, government datasets, "
                "and citizen science globally — it goes further back in time than iNaturalist "
                "and covers rare species with sparse community observation coverage. "
                "Use when the user asks about historical species presence, rare or micro-target "
                "species, museum records, or wants a comprehensive picture combining citizen "
                "science with institutional data. "
                "Returns a unified view cross-referencing both GBIF and local iNaturalist records "
                "with source attribution per species. "
                "Omit days_back to retrieve all historical records including museum specimens."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": lat_desc,
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc,
                    },
                    "radius_km": {
                        "type": "number",
                        "description": "Search radius in kilometres. Default 50.",
                    },
                    "days_back": {
                        "type": "integer",
                        "description": (
                            "Limit to records from the last N days. "
                            "Omit entirely to retrieve all historical records "
                            "(recommended for museum specimens and rare species)."
                        ),
                    },
                    "species_filter": {
                        "type": "string",
                        "description": (
                            "Optional species name to filter by "
                            "(scientific or common name, partial match)."
                        ),
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_oldest_gbif_record",
            "description": (
                "Return the single oldest dated fish record in the local GBIF database. "
                "Use when the user asks about the oldest record, earliest observation, "
                "or how far back the database goes."
            ),
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "get_stream_conditions",
            "description": (
                "Returns current water level, flow rate (discharge), and trend for nearby "
                "Water Survey of Canada gauges. Includes a plain-English condition note "
                "('elevated and rising', 'normal and stable', etc.) and a tactical fishing note "
                "explaining what current conditions mean for where fish will be holding. "
                "Data refreshes hourly. Coverage: Canadian rivers only (WSC network). "
                "Call this whenever the user asks about river or stream conditions, water levels, "
                "flow, clarity, or whether a river is 'blown out'. "
                "For any river or stream fishing question, call this alongside or before "
                "get_tactical_recommendation — water level shapes every tactical decision for "
                "moving-water fishing."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": lat_desc,
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc,
                    },
                    "radius_km": {
                        "type": "number",
                        "description": "Search radius in kilometres. Default 50.",
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_tactical_recommendation",
            "description": (
                "Generate lure, bait, and technique recommendations based on current conditions. "
                "Automatically fetches weather and pressure trend if lat/lng are provided — "
                "do NOT call get_conditions or get_pressure_trend separately before calling this. "
                "Call this whenever the user asks: what should I throw, what's working, "
                "recommend a lure or rig or setup, or any gear/technique question. "
                "If the user does not specify a species, omit 'species' and the tool will "
                "read their profile — it will ask for clarification if the profile has "
                "multiple targets. Always quote the 'reasoning' field verbatim in your response."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "description": (
                            "Target species, e.g. 'smallmouth bass', 'brook trout', "
                            "'johnny darter'. Omit to read from user profile."
                        ),
                    },
                    "lat": {
                        "type": "number",
                        "description": lat_desc + " — enables auto-fetch of current conditions.",
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc + " — enables auto-fetch of current conditions.",
                    },
                    "water_clarity": {
                        "type": "string",
                        "enum": ["clear", "stained", "murky"],
                        "description": "Observed water clarity at the fishing location.",
                    },
                    "water_temp_c": {
                        "type": "number",
                        "description": (
                            "Observed water temperature in Celsius "
                            "(overrides auto-fetched value)."
                        ),
                    },
                    "time_of_day": {
                        "type": "string",
                        "enum": [
                            "dawn",
                            "morning",
                            "midday",
                            "afternoon",
                            "evening",
                            "dusk",
                            "night",
                        ],
                        "description": "Current or planned time of day for fishing.",
                    },
                    "notes": {
                        "type": "string",
                        "description": (
                            "Any extra context: recent rain, specific location type, etc."
                        ),
                    },
                },
                "required": [],
            },
        },
    ]
