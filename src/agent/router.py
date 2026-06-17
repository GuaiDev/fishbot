"""
Message router. Classifies each user message into one of three modes and routes
to the cheapest path that can answer it well.

Modes:
- reflex:    generic fishing knowledge (knots, basic rigs, general tactics).
             Cheap model, no tools, brief answer.
- synthesis: location/ecology questions requiring cross-dataset reasoning
             ("why is this spot good", "where else like this", "what connects here").
             Full pipeline OR cached synthesis.
- memory:    questions about the user's own history/patterns
             ("what did I catch here", "what's worked for me").
             Cheap, queries logs.

On uncertainty, ERR TOWARD SYNTHESIS — a too-cheap flat answer is worse than
spending slightly more. A flat generic answer is the main failure mode to avoid.
"""
import json

from src.agent.client import get_client

HAIKU = "claude-haiku-4-5-20251001"

ROUTER_SYSTEM = """You are a message classifier for a fishing intelligence app.
Classify the user's message into exactly one mode. Respond with ONLY a JSON object,
no other text.

Modes:
- "reflex": Generic fishing knowledge that any fishing expert would know without
  needing local data. Knots, basic rig setups, general species behaviour, gear
  questions, line/tackle advice. These need no databases.
- "synthesis": Questions about WHY a specific place fishes a certain way, WHERE to
  find similar/new spots, what watersheds/geology/habitat connect to a location, or
  spot discovery. These require cross-referencing local geographic and ecological data.
- "memory": Questions about the user's OWN fishing history, past trips, personal
  patterns, or what has worked for them specifically.

Rules:
- If a message could be either reflex or synthesis, choose "synthesis".
- If a message references a specific named/coordinate location and asks anything
  analytical about it, choose "synthesis".
- If genuinely ambiguous, choose "synthesis".
- A simple greeting or thanks is "reflex".

Also extract:
- "leading_question": if the message is "reflex" but the user might benefit from a
  synthesis feature, write ONE short leading question offering it (e.g. "Want me to
  find spots near you with similar habitat?"). Otherwise null.

Output format:
{"mode": "reflex|synthesis|memory", "leading_question": "string or null", "confidence": 0.0-1.0}
"""

REFLEX_SYSTEM = """You are a knowledgeable fishing assistant answering a quick,
general question. The user wants a fast, direct answer from general fishing knowledge.

Rules:
- Answer in 2-4 sentences. No headers, no tables, no bullet lists.
- Be specific and practical, like an experienced angler talking to a friend.
- Do NOT pad with caveats or extra context they didn't ask for.
- This is general knowledge — answer it well and briefly.
"""


def classify_message(message: str, conversation_context: str = "") -> dict:
    """
    Classify a single user message. Returns dict with mode, leading_question, confidence.
    Falls back to 'synthesis' on any error (err toward quality).
    """
    try:
        client = get_client()
        prompt = message
        if conversation_context:
            prompt = f"Recent context: {conversation_context[:500]}\n\nMessage: {message}"

        resp = client.messages.create(
            model=HAIKU,
            max_tokens=150,
            system=ROUTER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)

        if result.get("mode") not in ("reflex", "synthesis", "memory"):
            result["mode"] = "synthesis"
        return {
            "mode": result.get("mode", "synthesis"),
            "leading_question": result.get("leading_question"),
            "confidence": result.get("confidence", 0.5),
            "router_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
        }
    except Exception as e:
        return {
            "mode": "synthesis",
            "leading_question": None,
            "confidence": 0.0,
            "router_tokens": 0,
            "error": str(e),
        }


def extract_location_from_message(message: str) -> dict:
    """
    Extract location information from a synthesis-mode message.
    Returns dict with lat, lng, location_name (all nullable).
    Uses Haiku — cheap and fast.
    Falls back to empty dict on any error.
    """
    try:
        client = get_client()
        resp = client.messages.create(
            model=HAIKU,
            max_tokens=100,
            system="""Extract location from a fishing question. Return ONLY JSON, no other text.
If the message mentions coordinates, a named place, or a specific water body: extract it.
If no specific location: return nulls.
Output: {"lat": number or null, "lng": number or null, "location_name": "string or null"}
Examples:
"Why does Willoway Park hold catfish?" → {"lat": null, "lng": null, "location_name": "Willoway Park"}
"What's at 42.917, -79.774?" → {"lat": 42.917, "lng": -79.774, "location_name": null}
"What bait for bass?" → {"lat": null, "lng": null, "location_name": null}
"Credit River near Streetsville" → {"lat": null, "lng": null, "location_name": "Credit River Streetsville"}""",
            messages=[{"role": "user", "content": message}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return {
            "lat": result.get("lat"),
            "lng": result.get("lng"),
            "location_name": result.get("location_name"),
            "extraction_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
        }
    except Exception:
        return {"lat": None, "lng": None, "location_name": None, "extraction_tokens": 0}


def handle_reflex(message: str, leading_question: str | None = None) -> dict:
    """
    Answer a reflex (generic knowledge) question with a cheap model, no tools.
    Optionally append a leading question to surface synthesis features.
    """
    client = get_client()
    resp = client.messages.create(
        model=HAIKU,
        max_tokens=400,
        system=REFLEX_SYSTEM,
        messages=[{"role": "user", "content": message}],
    )
    reply = "".join(b.text for b in resp.content if b.type == "text").strip()

    if leading_question:
        reply = reply + "\n\n" + leading_question

    return {
        "reply": reply,
        "mode": "reflex",
        "tokens": resp.usage.input_tokens + resp.usage.output_tokens,
    }
