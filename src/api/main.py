"""FishBot FastAPI server.

Exposes the chat agent over HTTP for mobile and web clients.
Start with: uv run fishbot serve
"""

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="FishBot API",
    description="Personal fishing intelligence platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
def log_trip(body: dict):
    """Log a fishing trip from natural language.

    Body: {"text": "natural language trip description"}
    """
    try:
        from src.services.trip_logger import log_session
        from src.services.trip_parser import parse_session_from_text
        from src.storage.database import get_db

        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="'text' field is required")

        db = get_db()
        parsed = parse_session_from_text(text, db)
        result = log_session(parsed, db)
        return {
            "status": "logged",
            "session_id": result["session_id"],
            "stops_logged": result["stops_logged"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
