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
    if name == "get_nearby_water":
        from src.services.osm import get_nearby_water_for_agent

        return get_nearby_water_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 25),
            feature_type=inputs.get("feature_type"),
            not_in_trip_log=inputs.get("not_in_trip_log", False),
        )
    if name == "get_access_points":
        from src.services.osm import get_access_points_for_agent

        return get_access_points_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 25),
            access_type=inputs.get("access_type"),
        )
    if name == "get_stocking_history":
        from src.services.stocking import get_stocking_for_agent

        return get_stocking_for_agent(
            waterbody_name=inputs.get("waterbody_name"),
            species=inputs.get("species"),
            lat=inputs.get("lat"),
            lng=inputs.get("lng"),
            radius_km=inputs.get("radius_km", 50),
            year_from=inputs.get("year_from"),
        )
    if name == "get_species_range":
        from src.services.species_ranges import get_species_range_for_agent

        return get_species_range_for_agent(
            species=inputs["species"],
            lat=inputs.get("lat"),
            lng=inputs.get("lng"),
        )
    if name == "get_sar_species":
        from src.services.species_ranges import get_sar_species_for_agent

        return get_sar_species_for_agent(inputs.get("jurisdiction", "CA-ON"))
    if name == "search_reddit_fishing":
        from src.services.reddit import search_reddit_for_agent

        return search_reddit_for_agent(
            query=inputs["query"],
            species=inputs.get("species"),
            jurisdiction=inputs.get("jurisdiction"),
            limit=inputs.get("limit", 10),
        )
    if name == "analyze_watershed":
        from src.services.hydrology import analyze_watershed_for_agent

        return analyze_watershed_for_agent(
            lat=inputs["lat"],
            lon=inputs["lon"],
            species=inputs.get("species"),
            radius_km=inputs.get("radius_km", 20.0),
        )
    if name == "find_connected_tributaries":
        from src.services.hydrology import find_connected_tributaries_for_agent

        return find_connected_tributaries_for_agent(
            watercourse_name=inputs["watercourse_name"],
            species=inputs.get("species"),
        )
    if name == "get_regulations":
        from src.services.regulations import get_regulations_for_agent

        return get_regulations_for_agent(
            zone=inputs.get("zone"),
            species=inputs.get("species"),
            lat=inputs.get("lat"),
            lng=inputs.get("lng"),
        )
    if name == "get_water_quality":
        from src.services.water_quality import get_water_quality_for_agent

        return get_water_quality_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
            date_from=inputs.get("date_from"),
            date_to=inputs.get("date_to"),
        )
    if name == "get_benthic_habitat":
        from src.services.benthic import get_benthic_habitat_for_agent

        return get_benthic_habitat_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
        )
    if name == "get_substrate":
        from src.services.geology import get_substrate_for_agent

        return get_substrate_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 10),
        )
    if name == "get_piscivore_activity":
        from src.services.ebird import get_piscivore_activity_for_agent

        return get_piscivore_activity_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
            days_back=inputs.get("days_back", 30),
        )
    if name == "get_stream_temperature":
        from src.services.stream_temperature import get_stream_temperature_for_agent

        return get_stream_temperature_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
        )
    if name == "get_species_habitat_predictions":
        from src.services.sdm_predictions import get_species_predictions_for_agent

        return get_species_predictions_for_agent(
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 25),
            species=inputs.get("species"),
            min_probability=inputs.get("min_probability", 0.5),
        )
    if name == "find_untapped_water":
        from src.services.untapped_potential import find_untapped_water_for_agent

        return find_untapped_water_for_agent(
            db=get_db(),
            lat=inputs["lat"],
            lng=inputs["lng"],
            radius_km=inputs.get("radius_km", 50),
            species=inputs.get("species"),
            min_stream_order=inputs.get("min_stream_order", 2),
            limit=inputs.get("limit", 10),
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
            "name": "get_nearby_water",
            "description": (
                "Query OSM geographic data for water bodies near a location. "
                "Use when the user asks what bodies of water are near a location, "
                "what is fishable in a region, or mentions a general area and wants to know "
                "what streams, lakes, rivers, or ponds exist there. "
                "Returns all named and unnamed water bodies — unnamed features are described "
                "with type and estimated size. An unnamed water body is not unimportant; "
                "it means OSM has mapped it but not tagged a name. "
                "Data is cached 30 days; OSM geographic data is stable."
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
                        "description": "Search radius in kilometres. Default 25.",
                    },
                    "feature_type": {
                        "type": "string",
                        "enum": [
                            "lake",
                            "river",
                            "stream",
                            "pond",
                            "reservoir",
                            "wetland",
                            "canal",
                            "ditch",
                            "drain",
                            "bay",
                        ],
                        "description": "Optional: restrict to a specific water body type.",
                    },
                    "not_in_trip_log": {
                        "type": "boolean",
                        "description": (
                            "If true, exclude water bodies whose name matches a location "
                            "already in your trip log. Use when the user asks for new water "
                            "or spots they haven't fished before."
                        ),
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_access_points",
            "description": (
                "Query OSM data for access points near a location. "
                "Use when the user asks where they can access water, find parking, "
                "launch a boat, reach a trail, or fish a specific area. "
                "Covers boat launches, parking areas, roadside layby pulloffs, "
                "trail heads, tagged fishing spots, parks, and conservation areas. "
                "Roadside laybys are how most stream anglers access water — "
                "they are as important as formal boat ramps. "
                "Data is cached 30 days."
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
                        "description": "Search radius in kilometres. Default 25.",
                    },
                    "access_type": {
                        "type": "string",
                        "enum": [
                            "boat_launch",
                            "parking",
                            "trail_head",
                            "fishing_spot",
                            "public_land",
                            "conservation_area",
                            "park",
                        ],
                        "description": "Optional: restrict to a specific access type.",
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_stocking_history",
            "description": (
                "Query MNRF government fish stocking records for Ontario water bodies. "
                "Use when the user asks about stocking, whether fish are wild or hatchery-raised, "
                "when a lake was last stocked, what species have been planted, or whether "
                "a fishery is put-and-take. Returns is_put_and_take and wild_population_likely "
                "flags and a plain-English stocking_note for each matching water body."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "waterbody_name": {
                        "type": "string",
                        "description": "Name of the water body to search (partial match).",
                    },
                    "species": {
                        "type": "string",
                        "description": "Filter by species name (partial match).",
                    },
                    "lat": {
                        "type": "number",
                        "description": lat_desc + " — for spatial search.",
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc + " — for spatial search.",
                    },
                    "radius_km": {
                        "type": "number",
                        "description": (
                            "Search radius in kilometres (default 50). Used with lat/lng."
                        ),
                    },
                    "year_from": {
                        "type": "integer",
                        "description": "Earliest stocking year to include.",
                    },
                },
                "required": [],
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
                            "Observed water temperature in Celsius (overrides auto-fetched value)."
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
        {
            "name": "get_species_range",
            "description": (
                "Check whether a species is native, introduced, at risk, or extirpated in Ontario. "
                "Returns range info, conservation status (federal SARA + provincial Ontario), "
                "habitat notes, and fishing guidance. "
                "Call when the user asks about a species' presence in Ontario, conservation "
                "status, whether they should target it, whether it's protected, or whether it's "
                "even found here. If lat/lng provided, also checks whether the location is within "
                "the species' documented range. If a species is Threatened or Endangered, "
                "sar_alert will be true — surface this prominently before any fishing discussion."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "description": "Species to look up (common name, partial match).",
                    },
                    "lat": {
                        "type": "number",
                        "description": lat_desc + " — for range plausibility check.",
                    },
                    "lng": {
                        "type": "number",
                        "description": lng_desc + " — for range plausibility check.",
                    },
                },
                "required": ["species"],
            },
        },
        {
            "name": "get_sar_species",
            "description": (
                "Returns all Species at Risk in a jurisdiction with their conservation status "
                "and handling guidance. "
                "Call when the user asks about protected species, what not to target, "
                "what species require special care or reporting in Ontario, or what species "
                "are threatened or endangered. Returns species sorted by severity "
                "(Endangered first, then Threatened, then Special Concern, then Extirpated)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "jurisdiction": {
                        "type": "string",
                        "description": (
                            "ISO 3166-2 jurisdiction code. Default 'CA-ON' for Ontario."
                        ),
                    },
                },
                "required": [],
            },
        },
        {
            "name": "search_reddit_fishing",
            "description": (
                "Search locally-cached Reddit fishing community posts for technique, gear, "
                "and local knowledge. Covers r/OntarioFishing, r/CanadianFishing, r/Fishing, "
                "r/FlyFishing, r/Microfishing. "
                "Use when the user asks what's working, community tips, local knowledge, "
                "technique reports for a species or location, or what other anglers say. "
                "IMPORTANT: Reddit data measures angler presence and activity, NOT fish abundance. "
                "Always distinguish 'anglers report catching X here' from 'X is abundant here'. "
                "A popular spot may be high-pressure, not high-quality. "
                "An unpopular spot may hold excellent fish that nobody talks about. "
                "Run `make ingest` to populate or refresh; posts may be days to weeks old."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query — species, location, technique, gear, or free text."
                        ),
                    },
                    "species": {
                        "type": "string",
                        "description": (
                            "Optional: filter to posts that mention this species name."
                        ),
                    },
                    "jurisdiction": {
                        "type": "string",
                        "description": ("Optional: filter by jurisdiction code, e.g. 'CA-ON'."),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max posts to return. Default 10.",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "analyze_watershed",
            "description": (
                "Check stream connectivity between a location and confirmed species observations "
                "using the Ontario Hydro Network graph. "
                "Use when the user asks whether a species could be present based on upstream or "
                "downstream confirmed sightings, what species are connected to a given reach, "
                "or whether a waterfall or barrier separates a confirmed observation from their "
                "fishing spot. "
                "Returns a connectivity sentence: e.g. 'Brook trout confirmed 2.3km upstream — "
                "stream connectivity is intact, no barriers detected.' "
                "Requires OHN data (run `make ingest`). "
                "Only covers the local bbox loaded at ingest."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": lat_desc,
                    },
                    "lon": {
                        "type": "number",
                        "description": lng_desc,
                    },
                    "species": {
                        "type": "string",
                        "description": (
                            "Optional species name to check connectivity for. "
                            "If omitted, checks the top 3 most-observed species nearby."
                        ),
                    },
                    "radius_km": {
                        "type": "number",
                        "description": (
                            "Radius (km) to search for confirmed observations. Default 20."
                        ),
                    },
                },
                "required": ["lat", "lon"],
            },
        },
        {
            "name": "find_connected_tributaries",
            "description": (
                "Find tributary streams that join a named watercourse, using the OHN stream graph. "
                "Use when the user asks what streams feed into a given river or creek, "
                "which tributaries are accessible to a particular species, "
                "or wants to explore the network branching off a main stem. "
                "Returns named tributaries and unnamed segment counts. "
                "Species filter applies barrier passability "
                "(e.g. a falls blocks non-jumping species). "
                "Requires OHN data (run `make ingest`)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "watercourse_name": {
                        "type": "string",
                        "description": (
                            "The official OHN name of the watercourse (e.g. 'Bronte Creek', "
                            "'Credit River'). Must match the OFFICIAL_NAME_LABEL field exactly "
                            "(case-insensitive)."
                        ),
                    },
                    "species": {
                        "type": "string",
                        "description": (
                            "Optional: filter tributaries by species passability. "
                            "Falls are impassable for all species. Rapids block small-bodied fish. "
                            "Sea Lamprey Barriers block lamprey only."
                        ),
                    },
                },
                "required": ["watercourse_name"],
            },
        },
        {
            "name": "get_regulations",
            "description": (
                "Look up Ontario fishing regulations for a specific Fisheries Management Zone (FMZ). "  # noqa: E501
                "Use when the user asks about seasons, size limits, possession limits, slot sizes, "
                "or whether a species can be kept in a particular zone. "
                "Ontario has 20 FMZs — regulations vary by zone and sometimes by specific waterbody. "  # noqa: E501
                "Provide 'zone' (integer 1-20) for precise lookup, or lat/lng for approximate detection. "  # noqa: E501
                "Optionally filter to a specific species to get targeted context. "
                "Always remind the user to verify against the current MNRF publication. "
                "Requires regulations data (run `make ingest` to populate)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "zone": {
                        "type": "integer",
                        "description": (
                            "Ontario Fisheries Management Zone number (1-20). "
                            "Preferred over lat/lng — provide this when the user knows their zone."
                        ),
                    },
                    "species": {
                        "type": "string",
                        "description": (
                            "Optional species name (e.g. 'walleye', 'largemouth bass', 'brook trout'). "  # noqa: E501
                            "Narrows the returned text to sections mentioning that species."
                        ),
                    },
                    "lat": {
                        "type": "number",
                        "description": "Latitude for approximate zone detection (used only if zone is omitted).",  # noqa: E501
                    },
                    "lng": {
                        "type": "number",
                        "description": "Longitude for approximate zone detection (used only if zone is omitted).",  # noqa: E501
                    },
                },
                "required": [],
            },
        },
        {
            "name": "get_water_quality",
            "description": (
                "Query PWQMN (Provincial Water Quality Monitoring Network) water quality data "
                "for streams and rivers near a location. "
                "Returns DO, pH, temperature, and conductivity stats with a habitat_assessment "
                "block that lists species constraints (ruling_out) based on measured parameters. "
                "Use this tool when the user asks about water quality, habitat suitability, "
                "which species could plausibly live in a given stream, whether a stream is "
                "too warm or acidic for trout, or any DO/pH/temperature question. "
                "IMPORTANT: Parameters here are HABITAT CONSTRAINTS, not presence indicators — "
                "a site passing all thresholds is habitable, not confirmed occupied. "
                "Use ruling_out entries to filter species predictions; do not use these readings "
                "to confirm a species is present. "
                "Requires water quality data (run `make ingest` to populate). "
                "Coverage: Ontario stream monitoring stations (strongest in southern Ontario)."
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
                    "date_from": {
                        "type": "string",
                        "description": (
                            "Optional start date (ISO format YYYY-MM-DD) to filter readings. "
                            "Omit for all available history."
                        ),
                    },
                    "date_to": {
                        "type": "string",
                        "description": (
                            "Optional end date (ISO format YYYY-MM-DD) to filter readings."
                        ),
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_benthic_habitat",
            "description": (
                "Query CABIN (Canadian Aquatic Biomonitoring Network) benthic macroinvertebrate "
                "data for streams near a location. "
                "Returns EPT (Ephemeroptera, Plecoptera, Trichoptera) proportion and richness "
                "per site, with a habitat_assessment interpreting what the benthic community "
                "implies for fish species plausibility. "
                "EPT taxa are clean-water indicators: high EPT proportion = good substrate and "
                "oxygen; low EPT = degraded or impaired habitat. "
                "Use this tool when the user asks about stream health, substrate quality, "
                "whether a stream could support sensitive species (darters, brook trout, "
                "redhorse, lampreys), or what the benthic community tells us about a stream. "
                "IMPORTANT: High EPT proportion means the habitat is suitable — it does NOT "
                "confirm the species is present. Always combine with iNaturalist/GBIF data. "
                "Requires CABIN data (run `make ingest` to populate). "
                "Coverage: Ontario streams with historical CABIN sampling (strongest in "
                "southern Ontario watersheds)."
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
            "name": "get_substrate",
            "description": (
                "Query Ontario surficial geology (MRD 128) substrate type at a location. "
                "Returns the dominant substrate class (coarse/fine/bedrock/organic/mixed) "
                "at the point plus a summary of nearby units and a habitat note explaining "
                "what the surface geology implies for stream bed character and species "
                "plausibility. "
                "Use this tool when the user asks about substrate, stream bed type, "
                "gravel vs. silt, whether a stream likely has clean gravel for spawning, "
                "or habitat suitability for substrate-sensitive species "
                "(redhorse, darters, madtoms, lampreys). "
                "IMPORTANT: Substrate class reflects surface geology, not confirmed "
                "channel substrate. "
                "Glaciofluvial (coarse) units are the strongest predictor of "
                "gravel/cobble beds. "
                "Combine with CABIN benthic EPT data for stronger habitat inference. "
                "Coverage: southern Ontario only (roughly south of 46°N). "
                "Requires geology data (run `make ingest` to populate)."
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
                        "description": (
                            "Radius in km for nearby units summary. Default 10. "
                            "Keep small (5–20) — geology units are dense within a tile."
                        ),
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_piscivore_activity",
            "description": (
                "Returns recent eBird observations of fish-eating birds "
                "(osprey, great blue heron, belted kingfisher, common merganser, "
                "double-crested cormorant) near a location. "
                "These birds are independent biological indicators of fish presence — "
                "they don't hunt where fish aren't there. "
                "Osprey and Common Merganser are the strongest signals: "
                "both are active pursuit predators that only hunt where fish are "
                "abundant and catchable. Heron and kingfisher are strong secondary "
                "signals for shallow-water fish. Cormorant indicates productive habitat "
                "but also targets invertebrates. "
                "Proactive use: when the user asks about fish presence, whether a water "
                "body holds fish, or wants biological confirmation of habitat quality — "
                "call this alongside get_recent_observations and get_gbif_observations "
                "to cross-validate from an independent data source. "
                "Always cite eBird.org as the source and note the observation date. "
                "Requires eBird data (run `make ingest` to populate). "
                "Data from eBird.org (Cornell Lab of Ornithology)."
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
                        "description": "Search radius in kilometres. Default 50, max 50.",
                    },
                    "days_back": {
                        "type": "integer",
                        "description": "Days of history to include. Default 30, max 30.",
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_stream_temperature",
            "description": (
                "Returns historical thermal regime from HYDAT daily temperature records — "
                "whether streams in this area are coldwater, coolwater, or warmwater, "
                "and what species that implies. "
                "Coldwater (<18°C summer mean) supports brook trout, lake trout, and salmonids. "
                "Coolwater (18–23°C) supports walleye, pike, bass; marginal for salmonids. "
                "Warmwater (>23°C) supports bass, catfish, carp, sunfish; too warm for salmonids. "
                "Data comes from decades of WSC/ECCC hydrometric station monitoring — "
                "a historical baseline, not a real-time reading. "
                "Use alongside get_water_quality: HYDAT provides the long-term thermal regime; "
                "PWQMN provides recent spot temperature measurements. "
                "If not loaded, returns a setup message (requires one-time make ingest-hydat)."
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
            "name": "find_untapped_water",
            "description": (
                "Returns stream segments ranked by untapped potential: "
                "high predicted habitat suitability × low angler observation pressure × good access. "  # noqa: E501
                "This is the primary exploration tool — use it when the user asks for new water to explore, "  # noqa: E501
                "untapped spots, places that haven't been fished, or where to find solitude. "
                "Each result includes habitat_score (RF model prediction — NOT confirmed presence), "  # noqa: E501
                "observation_pressure (iNat+GBIF report density — high = popular, not necessarily better), "  # noqa: E501
                "and access_score (road proximity, park type, tagged access points). "
                "IMPORTANT: Always note that habitat_score is model-predicted suitability, not confirmed presence. "  # noqa: E501
                "After returning results, pair with get_recent_observations on the top 2-3 candidates "  # noqa: E501
                "to check if any confirmed sightings exist nearby. "
                "Requires `make compute-untapped` to have been run first."
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
                    "species": {
                        "type": "string",
                        "description": (
                            "Optional: filter habitat score to a specific species. "
                            "Accepts common name (e.g. 'Creek Chub') or scientific name. "
                            "Omit to use average across all modelled species."
                        ),
                    },
                    "min_stream_order": {
                        "type": "integer",
                        "description": (
                            "Minimum Strahler stream order to include. Default 2 "
                            "(filters out first-order trickles). Use 1 for microfishing targets."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of top segments to return. Default 10.",
                    },
                },
                "required": ["lat", "lng"],
            },
        },
        {
            "name": "get_species_habitat_predictions",
            "description": (
                "Returns RF model predictions of species presence probability based on "
                "habitat features (substrate, thermal regime, water quality, EPT community, "
                "stream connectivity). "
                "Available for 8 species: Creek Chub, Pumpkinseed, Yellow Perch, "
                "Brown Bullhead, White Sucker, Brook Stickleback, Rainbow Darter, Rock Bass. "
                "Probabilities reflect habitat suitability — not confirmed presence. "
                "Always note this framing to the user. "
                "Requires `make train-sdm` to have been run first; returns a setup message "
                "if predictions are not yet generated."
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
                        "description": "Search radius in kilometres. Default 25.",
                    },
                    "species": {
                        "type": "string",
                        "description": (
                            "Filter to a single species. "
                            "Accepts common name (e.g. 'Creek Chub') or "
                            "scientific name (e.g. 'Semotilus atromaculatus'). "
                            "Omit to return all modelled species."
                        ),
                    },
                    "min_probability": {
                        "type": "number",
                        "description": "Minimum presence probability threshold. Default 0.5.",
                    },
                },
                "required": ["lat", "lng"],
            },
        },
    ]
