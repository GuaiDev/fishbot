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
            text = "".join(
                b.text for b in content_blocks if b.type == "text"
            )
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
    ]
