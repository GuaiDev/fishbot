"""FishBot FastAPI server.

Exposes the chat agent over HTTP for mobile and web clients.
Start with: uv run fishbot serve
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


def verify_api_key(x_api_key: str = Header(None)) -> None:
    """Verify admin API key for protected endpoints."""
    expected = os.environ.get("FISHBOT_API_KEY")
    if not expected:
        # No key configured — development mode, allow all
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app):
    from src.storage.database import ensure_schema, get_db
    db = get_db()
    ensure_schema(db)
    yield


app = FastAPI(
    title="FishBot API",
    description="Personal fishing intelligence platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (mobile log page)
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


def _hour_to_time_of_day(hour: int) -> str:
    if hour < 6: return "night"
    if hour < 9: return "dawn"
    if hour < 12: return "morning"
    if hour < 14: return "midday"
    if hour < 17: return "afternoon"
    if hour < 20: return "evening"
    return "night"


# --- Request / Response models ---


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[list[ChatMessage]] = []
    user_id: Optional[str] = "default"


class ChatResponse(BaseModel):
    reply: str
    conversation_history: list[ChatMessage]
    tool_calls_made: Optional[list[str]] = []


# --- Endpoints ---


@app.get("/health")
def health():
    return {"status": "ok", "service": "fishbot"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Send a message to FishBot and get a response.

    Pass conversation_history from the previous response to maintain context.
    Only user/assistant text turns are tracked in history — intermediate tool
    calls are handled server-side and not exposed to the client.
    """
    try:
        from src.agent.chat import run_chat_api

        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in (request.conversation_history or [])
        ]
        messages.append({"role": "user", "content": request.message})

        result = run_chat_api(messages)

        # Return only user/assistant text turns — strip intermediate tool messages
        clean_history = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in result["messages"]
            if isinstance(m["content"], str)
        ]

        return ChatResponse(
            reply=result["reply"],
            conversation_history=clean_history,
            tool_calls_made=result["tool_calls"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/log-trip")
def log_trip(body: dict, _: None = Depends(verify_api_key)):
    """Log a fishing trip from natural language, with optional photo metadata.

    Body: {
        "text": "natural language trip description",
        "photo_lat": float (optional, from EXIF),
        "photo_lng": float (optional, from EXIF),
        "photo_taken_at": "ISO timestamp" (optional, from EXIF),
        "photo_url": "string" (optional)
    }
    Photo GPS overrides text-parsed location for the primary stop.
    """
    try:
        from src.services.trip_logger import log_session
        from src.services.trip_parser import parse_session_from_text
        from src.storage.database import ensure_schema, get_db

        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="'text' field is required")

        photo_lat = body.get("photo_lat")
        photo_lng = body.get("photo_lng")
        photo_taken_at = body.get("photo_taken_at")
        photo_url = body.get("photo_url")

        db = get_db()
        ensure_schema(db)
        parsed = parse_session_from_text(text, db)

        # Inject photo metadata into the first stop
        if parsed.get("stops") and (photo_lat is not None or photo_taken_at):
            first_stop = parsed["stops"][0]

            if photo_lat is not None and photo_lng is not None:
                first_stop["photo_lat"] = photo_lat
                first_stop["photo_lng"] = photo_lng
                if not first_stop.get("lat"):
                    first_stop["lat"] = photo_lat
                    first_stop["lng"] = photo_lng
                    first_stop["location_method"] = "photo_exif"
                    first_stop["location_confidence"] = 0.95

            if photo_taken_at:
                first_stop["photo_taken_at"] = photo_taken_at
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(photo_taken_at.replace("Z", "+00:00"))
                    first_stop["hour_of_day"] = dt.hour
                    first_stop["time_of_day"] = _hour_to_time_of_day(dt.hour)
                    if not parsed.get("date"):
                        parsed["date"] = dt.date().isoformat()
                except Exception:
                    pass

            if photo_url:
                first_stop["photo_url"] = photo_url

        result = log_session(parsed, db)
        return {
            "status": "logged",
            "session_id": result["session_id"],
            "stops_logged": result["stops_logged"],
            "location_method": parsed["stops"][0].get("location_method") if parsed.get("stops") else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/log")
def log_page():
    """Serve the mobile trip logging page."""
    return FileResponse(os.path.join(_static_dir, "log.html"))


@app.post("/ingest")
def ingest(body: dict):
    """Ingest YouTube content for a search query.

    Body: {"query": "channel catfish Grand River", "max_videos": 10}
    Admin/personal use — add auth before making public.
    """
    try:
        from src.ingest.community.youtube_ingest import ingest_query
        from src.storage.database import get_db

        query = body.get("query", "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="'query' field is required")

        max_videos = body.get("max_videos", 10)
        db = get_db()
        result = ingest_query(query, db, max_videos=max_videos)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/data")
def ingest_data(body: dict, _: None = Depends(verify_api_key)):
    """Trigger full data ingest for a location.

    Body: {
        "lat": float,
        "lng": float,
        "radius_km": float (optional, default 50),
        "label": str (optional, human-readable name for logging)
    }
    Runs iNaturalist, GBIF, WSC, and OSM data sources for the given location.
    Protected by X-Api-Key header.
    """
    try:
        from src.services.gbif import fetch_and_store as gbif_fetch
        from src.services.observations import fetch_and_store as inat_fetch
        from src.services.osm import fetch_and_store as osm_fetch
        from src.services.stream_gauge import fetch_and_store as wsc_fetch
        from src.storage.database import ensure_schema, get_db

        lat = body.get("lat")
        lng = body.get("lng")
        radius_km = body.get("radius_km", 50.0)
        label = body.get("label", f"{lat},{lng}")

        if lat is None or lng is None:
            raise HTTPException(status_code=400, detail="lat and lng are required")

        db = get_db()
        ensure_schema(db)

        results = {}

        try:
            n = inat_fetch(lat, lng, radius_km=radius_km, days_back=90)
            results["inat_observations"] = n
        except Exception as e:
            results["inat_error"] = str(e)

        try:
            n = gbif_fetch(lat, lng, radius_km=radius_km)
            results["gbif_records"] = n
        except Exception as e:
            results["gbif_error"] = str(e)

        try:
            n = wsc_fetch(lat, lng, radius_km=radius_km)
            results["wsc_stations"] = n
        except Exception as e:
            results["wsc_error"] = str(e)

        try:
            osm_water, osm_access = osm_fetch(lat, lng)
            results["osm_water_features"] = osm_water
            results["osm_access_points"] = osm_access
        except Exception as e:
            results["osm_error"] = str(e)

        results["label"] = label
        results["lat"] = lat
        results["lng"] = lng
        results["radius_km"] = radius_km
        results["status"] = "ok"
        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
