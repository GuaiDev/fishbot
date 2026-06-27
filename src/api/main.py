"""FishBot FastAPI server.

Exposes the chat agent over HTTP for mobile and web clients.
Start with: uv run fishbot serve
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


def verify_api_key(x_api_key: str = Header(None)) -> None:
    """Verify admin API key for protected endpoints."""
    expected = os.environ.get("FISHBOT_API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def get_current_user(authorization: str = Header(None)) -> dict:
    """Extract and validate user from Authorization: Bearer <token> header."""
    from src.auth.auth import get_user_from_token
    from src.storage.database import get_db
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    user = get_user_from_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def get_current_user_or_apikey(
    authorization: str = Header(None),
    x_api_key: str = Header(None),
) -> dict:
    """Accept either Bearer token (users) or X-Api-Key (admin fallback for log.html)."""
    from src.auth.auth import get_user_from_token
    from src.storage.database import get_db
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
        db = get_db()
        user = get_user_from_token(db, token)
        if user:
            return user
    expected = os.environ.get("FISHBOT_API_KEY")
    if expected and x_api_key == expected:
        return {"id": 1, "username": "jason", "role": "admin", "daily_message_limit": 9999}
    raise HTTPException(status_code=401, detail="Not authenticated")


@asynccontextmanager
async def lifespan(app):
    from src.storage.database import ensure_schema, get_db
    db = get_db()
    ensure_schema(db)

    count = db.execute("SELECT COUNT(*) FROM map_segments").fetchone()[0]
    if count == 0:
        try:
            import json
            map_file = "data/processed/map_data.json"
            if os.path.exists(map_file):
                print("[startup] Importing map segments...")
                with open(map_file) as f:
                    data = json.load(f)
                rows = []
                for feat in data["features"]:
                    coords = feat["geometry"]["coordinates"]
                    p = feat["properties"]
                    rows.append({
                        "ogf_id": p["ogf_id"],
                        "lat": coords[1], "lng": coords[0],
                        "score_balanced": p.get("untapped_score_balanced"),
                        "score_easy": p.get("untapped_score_easy"),
                        "score_adventure": p.get("untapped_score_adventure"),
                        "habitat_score": p.get("habitat_score"),
                        "access_score": p.get("access_score"),
                        "stream_order": p.get("stream_order"),
                        "watercourse_name": p.get("watercourse_name"),
                        "nearest_named_stream": p.get("nearest_named_stream"),
                        "is_confluence": 1 if p.get("is_confluence_segment") else 0,
                        "connected_to_waterbody": 1 if p.get("connected_to_waterbody") else 0,
                        "observation_pressure": p.get("observation_pressure"),
                        "top1_species": p.get("top1_species"),
                        "top1_prob": p.get("top1_prob"),
                        "top2_species": p.get("top2_species"),
                        "top2_prob": p.get("top2_prob"),
                        "google_maps_url": p.get("google_maps_url"),
                        "swoop_url": p.get("swoop_url"),
                    })
                    if len(rows) >= 1000:
                        db["map_segments"].insert_all(rows, ignore=True)
                        db.conn.commit()
                        rows = []
                if rows:
                    db["map_segments"].insert_all(rows, ignore=True)
                    db.conn.commit()
                final = db.execute("SELECT COUNT(*) FROM map_segments").fetchone()[0]
                print(f"[startup] Imported {final:,} map segments.")
        except Exception as e:
            print(f"[startup] Map segment import failed: {e}")

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


@app.post("/auth/signup")
def signup(body: dict):
    """
    Redeem an invite code and create an account.
    Body: {"code": "A3KX9P2Q", "username": "jake", "display_name": "Jake"}
    Returns: {"token": "...", "user_id": N, "username": "..."}
    """
    from src.auth.auth import redeem_invite_code
    from src.storage.database import get_db
    code = body.get("code", "").strip()
    username = body.get("username", "").strip()
    display_name = body.get("display_name", "").strip()

    if not code or not username:
        raise HTTPException(status_code=400, detail="code and username are required")
    if len(username) < 2 or len(username) > 20:
        raise HTTPException(status_code=400, detail="Username must be 2-20 characters")
    if not username.isalnum():
        raise HTTPException(status_code=400, detail="Username must be letters and numbers only")

    db = get_db()
    result = redeem_invite_code(db, code, username, display_name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "token": result["token"],
        "user_id": result["user_id"],
        "username": username,
        "display_name": display_name or username,
    }


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    """Return current user info."""
    from src.auth.auth import check_rate_limit
    from src.storage.database import get_db
    db = get_db()
    usage = check_rate_limit(db, user["id"], user.get("daily_message_limit", 50))
    return {
        "user_id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name"),
        "role": user.get("role"),
        "usage_today": usage["used"],
        "daily_limit": usage["limit"],
    }


@app.post("/chat")
def chat(body: dict, user: dict = Depends(get_current_user)):
    """Send a message to FishBot. Body: {"messages": [{"role": "user", "content": "..."}]}"""
    from src.agent.chat import run_chat_api
    from src.auth.auth import check_rate_limit, increment_usage
    from src.storage.database import get_db

    db = get_db()
    limit = user.get("daily_message_limit", 50)
    usage = check_rate_limit(db, user["id"], limit)
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"Daily message limit reached ({limit} messages/day). Try again tomorrow.",
        )

    try:
        message = body.get("message", "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="'message' field is required")
        history = body.get("conversation_history", [])
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": message})
        session_id = body.get("session_id")
        result = run_chat_api(messages, session_id=session_id, user_id=user["id"])
        increment_usage(db, user["id"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/log-trip")
def log_trip(body: dict, user: dict = Depends(get_current_user_or_apikey)):
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

        result = log_session(parsed, db, user_id=user["id"])
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


@app.get("/sessions")
def get_sessions(user: dict = Depends(get_current_user)):
    """Return logged sessions for the current user."""
    from src.storage.database import get_db

    db = get_db()
    try:
        rows = list(db.execute("""
            SELECT
                s.id, s.date, s.date_approx, s.overall_notes,
                st.location_name, st.location_text,
                GROUP_CONCAT(DISTINCT je.value) as species_caught,
                sc.air_temp_c, sc.pressure_hpa, sc.anomaly_flag
            FROM sessions s
            LEFT JOIN stops st ON st.session_id = s.id
            LEFT JOIN json_each(st.species_caught) je ON 1=1
            LEFT JOIN session_conditions sc ON sc.session_id = s.id
            WHERE s.user_id = ?
            GROUP BY s.id
            ORDER BY s.id DESC
            LIMIT 50
        """, [user["id"]]).fetchall())

        sessions = []
        for r in rows:
            sessions.append({
                "id": r[0],
                "date": r[1] or r[2],
                "notes": r[3],
                "location": r[4] or r[5] or "Unknown location",
                "species_caught": [s.strip() for s in (r[6] or "").split(",") if s.strip()],
                "conditions": {
                    "air_temp_c": r[7],
                    "pressure_hpa": r[8],
                    "anomaly_flag": r[9],
                } if r[7] else None,
            })
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/log")
def log_page():
    """Serve the mobile trip logging page."""
    return FileResponse(os.path.join(_static_dir, "log.html"))


@app.post("/admin/bootstrap")
def bootstrap(body: dict, _: None = Depends(verify_api_key)):
    import traceback
    import secrets
    from datetime import datetime, timedelta
    from src.storage.database import get_db

    try:
        db = get_db()
        username = body.get("username", "jason")

        existing = list(db.execute("SELECT id FROM users WHERE id = 1").fetchall())

        if not existing:
            db.execute(
                "INSERT OR IGNORE INTO users (id, username, display_name, role, daily_message_limit) "
                "VALUES (1, ?, 'Jason', 'admin', 200)",
                [username],
            )
            db.conn.commit()

        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(days=90)).isoformat()
        db.execute(
            "INSERT INTO user_sessions (user_id, token, expires_at, last_used_at) VALUES (1, ?, ?, ?)",
            [token, expires, datetime.now().isoformat()],
        )
        db.conn.commit()

        return {"token": token, "user_id": 1, "username": username}

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.post("/admin/token")
def get_admin_token(_: None = Depends(verify_api_key)):
    """Generate a fresh admin token. Protected by API key only."""
    import secrets
    from datetime import datetime, timedelta
    from src.storage.database import get_db

    db = get_db()
    existing = list(db.execute("SELECT id, username FROM users WHERE id = 1").fetchall())
    if not existing:
        raise HTTPException(status_code=404, detail="Admin user not found. Run bootstrap first.")

    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=90)).isoformat()
    db.execute(
        "INSERT INTO user_sessions (user_id, token, expires_at, last_used_at) VALUES (1, ?, ?, ?)",
        [token, expires, datetime.now().isoformat()],
    )
    db.conn.commit()
    return {"token": token, "bearer": f"Bearer {token}"}


@app.post("/admin/invite")
def create_invite(body: dict, user: dict = Depends(get_current_user)):
    """Generate an invite code. Admin only."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    from src.auth.auth import generate_invite_code
    from src.storage.database import get_db
    db = get_db()
    note = body.get("note", "")
    code = generate_invite_code(db, created_by=user["id"], note=note)
    return {"code": code, "note": note}


@app.get("/admin/invites")
def list_invites(user: dict = Depends(get_current_user)):
    """List all invite codes. Admin only."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    from src.storage.database import get_db
    db = get_db()
    codes = list(db["invite_codes"].rows)
    return {"codes": codes}


@app.get("/admin/users")
def list_users(user: dict = Depends(get_current_user)):
    """List all users and their usage. Admin only."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    from src.storage.database import get_db
    db = get_db()
    users = list(db.execute("""
        SELECT u.id, u.username, u.display_name, u.role,
               u.created_at, u.last_seen_at,
               COALESCE(SUM(du.message_count), 0) as total_messages
        FROM users u
        LEFT JOIN daily_usage du ON du.user_id = u.id
        GROUP BY u.id
        ORDER BY u.id
    """).fetchall())
    return {"users": [
        {
            "id": r[0], "username": r[1], "display_name": r[2],
            "role": r[3], "created_at": r[4], "last_seen_at": r[5],
            "total_messages": r[6],
        }
        for r in users
    ]}


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


def _run_global_ingest(lat: float, lng: float, radius_km: float, label: str) -> None:
    """Background task: run iNat, GBIF, WSC, OSM, and SDM check for a location."""
    import json as _json
    import logging
    import os as _os

    _log = logging.getLogger(__name__)
    _log.info("Background ingest started: %s (%.4f, %.4f, %.0fkm)", label, lat, lng, radius_km)

    from src.services.gbif import fetch_and_store as gbif_fetch
    from src.services.observations import fetch_and_store as inat_fetch
    from src.services.osm import fetch_and_store as osm_fetch
    from src.services.stream_gauge import fetch_and_store as wsc_fetch
    from src.storage.database import ensure_schema, get_db

    db = get_db()
    ensure_schema(db)

    try:
        inat_fetch(lat, lng, radius_km=radius_km, days_back=90)
    except Exception as e:
        _log.error("iNat fetch failed for %s: %s", label, e)

    try:
        gbif_fetch(lat, lng, radius_km=radius_km)
    except Exception as e:
        _log.error("GBIF fetch failed for %s: %s", label, e)

    try:
        wsc_fetch(lat, lng, radius_km=radius_km)
    except Exception as e:
        _log.error("WSC fetch failed for %s: %s", label, e)

    try:
        osm_fetch(lat, lng)
    except Exception as e:
        _log.error("OSM fetch failed for %s: %s", label, e)

    # SDM retrain check — non-fatal if it errors
    try:
        import joblib as _joblib
        from src.services.species_mapping import COMMON_TO_SCIENTIFIC as _c2s

        model_dir = "data/processed/sdm_models"
        if _os.path.exists(model_dir):
            trip_counts: dict = {}
            for (sc_json,) in db.execute(
                "SELECT species_caught FROM stops WHERE was_productive = 1"
            ).fetchall():
                for common in _json.loads(sc_json or "[]"):
                    clean = common.lower().replace("(uncertain)", "").strip()
                    sci = _c2s.get(clean)
                    if sci:
                        trip_counts[sci] = trip_counts.get(sci, 0) + 1
            retrain_candidates = []
            for f in _os.listdir(model_dir):
                if not f.endswith(".joblib"):
                    continue
                b = _joblib.load(_os.path.join(model_dir, f))
                species = b.get("species")
                baseline = (b.get("n_inat", 0) or 0) + (b.get("n_gbif", 0) or 0)
                n_trip = b.get("n_trip_log", 0) or 0
                current = trip_counts.get(species, 0)
                if baseline > 0 and (current - n_trip) >= baseline * 0.20:
                    retrain_candidates.append(species)
            if retrain_candidates:
                _log.info("SDM retrain recommended for: %s", retrain_candidates)
    except Exception as e:
        _log.warning("SDM retrain check failed: %s", e)

    _log.info("Background ingest complete: %s", label)


@app.post("/ingest/data")
def ingest_data(
    body: dict,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_api_key),
):
    """Trigger global data ingest for a location (runs in background).

    Body: {
        "lat": float,
        "lng": float,
        "radius_km": float (optional, default 50),
        "label": str (optional, human-readable name for logging)
    }
    Runs iNaturalist, GBIF, WSC, and OSM data sources for the given location.
    Returns 202 immediately; ingest runs after the response is sent.
    Protected by X-Api-Key header.
    """
    lat = body.get("lat")
    lng = body.get("lng")
    radius_km = body.get("radius_km", 50.0)
    label = body.get("label", f"{lat},{lng}")

    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="lat and lng are required")

    background_tasks.add_task(_run_global_ingest, lat, lng, radius_km, label)

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "label": label,
            "message": "ingest started in background",
        },
    )


def _run_bc_ingest(lat: float, lng: float, radius_km: float, label: str) -> None:
    """Background task: run FWA, FISS, and BC EMS ingest for a BC location."""
    import logging
    _log = logging.getLogger(__name__)
    _log.info("BC background ingest started: %s (%.4f, %.4f, %.0fkm)", label, lat, lng, radius_km)
    try:
        from src.services.bc_ingest import ingest_bc_data
        from src.storage.database import ensure_schema, get_db
        db = get_db()
        ensure_schema(db)
        counts = ingest_bc_data(lat, lng, radius_km=radius_km)
        _log.info("BC background ingest complete: %s — %s", label, counts)
    except Exception as e:
        _log.error("BC background ingest failed for %s: %s", label, e)


@app.post("/ingest/data-bc")
def ingest_data_bc(
    body: dict,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_api_key),
):
    """Trigger BC-specific data ingest for a location (runs in background).

    Body: {
        "lat": float,
        "lng": float,
        "radius_km": float (optional, default 50),
        "label": str (optional, human-readable name for logging)
    }
    Runs FWA stream network, FISS fish observations, and BC EMS water quality.
    Returns 202 immediately; ingest runs after the response is sent.
    Global sources (iNat, GBIF, WSC, OSM) are handled by /ingest/data.
    Protected by X-Api-Key header.
    """
    lat = body.get("lat")
    lng = body.get("lng")
    radius_km = body.get("radius_km", 50.0)
    label = body.get("label", f"{lat},{lng}")

    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="lat and lng are required")

    background_tasks.add_task(_run_bc_ingest, lat, lng, radius_km, label)

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "label": label,
            "message": "ingest started in background",
        },
    )


@app.get("/map/segments")
def get_map_segments(
    north: float,
    south: float,
    east: float,
    west: float,
    mode: str = "balanced",
    limit: int = 300,
    user: dict = Depends(get_current_user),
):
    """Return stream segments within viewport bounds for explore mode."""
    from src.storage.database import get_db

    score_col = {
        "easy": "score_easy",
        "adventure": "score_adventure",
    }.get(mode, "score_balanced")

    db = get_db()
    rows = list(db.execute(f"""
        SELECT ogf_id, lat, lng, {score_col} as score,
               watercourse_name, nearest_named_stream,
               stream_order, top1_species, top1_prob,
               top2_species, top2_prob,
               is_confluence, connected_to_waterbody,
               google_maps_url, swoop_url,
               habitat_score, access_score
        FROM map_segments
        WHERE lat BETWEEN ? AND ?
          AND lng BETWEEN ? AND ?
          AND {score_col} IS NOT NULL
        ORDER BY {score_col} DESC
        LIMIT ?
    """, [south, north, west, east, limit]).fetchall())

    cols = [
        "ogf_id", "lat", "lng", "score", "watercourse_name",
        "nearest_named_stream", "stream_order", "top1_species", "top1_prob",
        "top2_species", "top2_prob", "is_confluence", "connected_to_waterbody",
        "google_maps_url", "swoop_url", "habitat_score", "access_score",
    ]
    return {
        "segments": [dict(zip(cols, r)) for r in rows],
        "count": len(rows),
        "mode": mode,
        "bounds": {"north": north, "south": south, "east": east, "west": west},
    }


@app.get("/map/my-stops")
def get_my_stops(user: dict = Depends(get_current_user)):
    """Return all of the user's logged stops with coordinates for personal map mode."""
    from src.storage.database import get_db
    import json

    db = get_db()
    rows = list(db.execute("""
        SELECT st.id, st.lat, st.lng, st.photo_lat, st.photo_lng,
               st.location_name, st.location_text,
               st.species_caught, st.was_productive,
               st.technique, st.gear,
               s.date, s.date_approx,
               sc.air_temp_c, sc.pressure_hpa, sc.anomaly_flag
        FROM stops st
        JOIN sessions s ON st.session_id = s.id
        LEFT JOIN session_conditions sc ON sc.session_id = s.id
        WHERE st.user_id = ?
          AND (st.lat IS NOT NULL OR st.photo_lat IS NOT NULL)
        ORDER BY s.id DESC
    """, [user["id"]]).fetchall())

    stops = []
    for r in rows:
        lat = r[3] if r[3] is not None else r[1]   # photo_lat preferred
        lng = r[4] if r[4] is not None else r[2]   # photo_lng preferred
        if not lat:
            continue
        species = json.loads(r[7] or "[]")
        stops.append({
            "stop_id": r[0],
            "lat": lat,
            "lng": lng,
            "location": r[5] or r[6] or "Unknown",
            "species": species,
            "productive": bool(r[8]),
            "technique": r[9],
            "gear": r[10],
            "date": r[11] or r[12] or "Unknown",
            "conditions": {
                "air_temp_c": r[13],
                "pressure_hpa": r[14],
                "anomaly_flag": r[15],
            } if r[13] else None,
        })

    return {"stops": stops, "count": len(stops)}


# Serve React web app from /app — mount last so API routes take priority
_web_dist = os.path.join(os.path.dirname(__file__), "../../web/dist")
if os.path.exists(_web_dist):
    app.mount("/app", StaticFiles(directory=_web_dist, html=True), name="webapp")
