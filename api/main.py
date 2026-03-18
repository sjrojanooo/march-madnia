from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.agents import (
    experts_available,
    get_agent_list,
    get_bracket_context,
    handle_chat,
    handle_rate_bracket,
)
from api.auth import get_current_user_id
from api.config import Settings
from api.db import get_supabase_client
from api.models import (
    AgentChatRequest,
    AgentInfo,
    AgentRateBracketRequest,
    AgentRateBracketResponse,
    ChatHistoryUpdate,
    UserBracketCreate,
    UserBracketResponse,
    UserBracketUpdate,
)

logger = logging.getLogger(__name__)
settings = Settings()


# ---------------------------------------------------------------------------
# Lifespan — load data files and Anthropic client once at startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    """Load bracket predictions and expert picks into app.state on startup."""
    # Bracket predictions
    if settings.bracket_predictions_path.exists():
        with open(settings.bracket_predictions_path) as f:
            app.state.bracket_data = json.load(f)
        logger.info("Loaded bracket predictions from %s", settings.bracket_predictions_path)
    else:
        app.state.bracket_data = {}
        logger.warning(
            "Bracket predictions not found at %s — /bracket will return empty.",
            settings.bracket_predictions_path,
        )

    # Expert picks
    if settings.expert_picks_path.exists():
        with open(settings.expert_picks_path) as f:
            app.state.expert_data = json.load(f)
        logger.info("Loaded expert picks from %s", settings.expert_picks_path)
    else:
        app.state.expert_data = {}
        logger.warning(
            "Expert picks not found at %s — /experts will return empty.",
            settings.expert_picks_path,
        )

    # Anthropic client (lazy — only created if key is set)
    if settings.anthropic_api_key:
        from anthropic import AsyncAnthropic

        app.state.anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        logger.info("Anthropic client initialized.")
    else:
        app.state.anthropic_client = None
        logger.warning(
            "ANTHROPIC_API_KEY not set — agent chat and rate-bracket endpoints disabled."
        )

    # Try Supabase connection
    sb = get_supabase_client()
    if sb:
        app.state.supabase = sb
        logger.info("Supabase client available — DB-backed endpoints enabled.")
    else:
        app.state.supabase = None
        logger.info("Supabase not configured — using JSON file fallback.")

    yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="March Madness Predictor API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — ["*"] is dev-only; restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: require Anthropic client
# ---------------------------------------------------------------------------
def _require_anthropic(request: Request) -> Any:
    """Return the Anthropic client or raise 503 if not configured."""
    client = request.app.state.anthropic_client
    if client is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "anthropic_unavailable",
                "message": "ANTHROPIC_API_KEY is not configured. Set it in .env to enable agent endpoints.",
            },
        )
    return client


def _require_experts() -> None:
    """Raise 503 if expert_analysts module is not available (Phase 3 dependency)."""
    if not experts_available():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "experts_unavailable",
                "message": (
                    "Expert analysts module (src.agents.expert_analysts) is not available. "
                    "This is created in Phase 3 of the project plan."
                ),
            },
        )


def _validate_expert_id(expert_id: str) -> None:
    """Raise 404 if expert_id is not in the known persona list."""
    agent_ids = {a["expert_id"] for a in get_agent_list()}
    if expert_id not in agent_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "expert_not_found",
                "message": f"Expert '{expert_id}' not found. Use GET /agents for available experts.",
            },
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/bracket")
async def get_bracket(request: Request) -> dict:
    """Return the full bracket predictions data."""
    return request.app.state.bracket_data


@app.get("/experts")
async def get_experts(request: Request) -> dict | list:
    """Return the expert picks data."""
    return request.app.state.expert_data


@app.get("/agents", response_model=list[AgentInfo])
async def list_agents() -> list[dict[str, str]]:
    """Return the list of available AI expert analyst agents."""
    _require_experts()
    return get_agent_list()


@app.post("/agents/{expert_id}/chat")
async def agent_chat(
    expert_id: str,
    body: AgentChatRequest,
    request: Request,
) -> StreamingResponse:
    """Stream a chat response from an expert analyst agent (SSE)."""
    _require_experts()
    _validate_expert_id(expert_id)
    client = _require_anthropic(request)

    bracket_context = get_bracket_context(
        request.app.state.bracket_data,
        request.app.state.expert_data,
    )

    async def event_generator():  # noqa: ANN202
        try:
            async for chunk in handle_chat(
                expert_id=expert_id,
                message=body.message,
                conversation_history=body.conversation_history,
                bracket_context=bracket_context,
                client=client,
            ):
                yield chunk
        except asyncio.CancelledError:
            logger.info("Client disconnected from SSE stream for expert %s", expert_id)
            return
        except Exception:
            logger.exception("Error in agent chat stream for expert %s", expert_id)
            error_payload = json.dumps({"chunk": "", "done": True, "error": "Internal error"})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/agents/{expert_id}/rate-bracket", response_model=AgentRateBracketResponse)
async def agent_rate_bracket(
    expert_id: str,
    body: AgentRateBracketRequest,
    request: Request,
) -> AgentRateBracketResponse:
    """Get an expert analyst's rating and suggestions for a user bracket."""
    _require_experts()
    _validate_expert_id(expert_id)
    client = _require_anthropic(request)

    bracket_context = get_bracket_context(
        request.app.state.bracket_data,
        request.app.state.expert_data,
    )

    try:
        return await handle_rate_bracket(
            expert_id=expert_id,
            user_bracket=body.user_bracket,
            bracket_context=bracket_context,
            client=client,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "rate_bracket_failed", "message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.exception("Error rating bracket for expert %s", expert_id)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "An unexpected error occurred."},
        ) from exc


# ---------------------------------------------------------------------------
# User Bracket endpoints (auth required)
# ---------------------------------------------------------------------------
@app.get("/user/brackets", response_model=list[UserBracketResponse])
async def list_user_brackets(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """List all brackets for the authenticated user."""
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    result = sb.table("user_brackets").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return result.data


@app.post("/user/brackets", response_model=UserBracketResponse, status_code=201)
async def create_user_bracket(
    body: UserBracketCreate,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new bracket for the authenticated user."""
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    result = sb.table("user_brackets").insert({
        "user_id": user_id,
        "picks": body.picks,
        "name": body.name,
    }).execute()
    return result.data[0]


@app.put("/user/brackets/{bracket_id}", response_model=UserBracketResponse)
async def update_user_bracket(
    bracket_id: str,
    body: UserBracketUpdate,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Update a bracket owned by the authenticated user."""
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    updates = {}
    if body.picks is not None:
        updates["picks"] = body.picks
    if body.name is not None:
        updates["name"] = body.name
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    updates["updated_at"] = "now()"
    result = (
        sb.table("user_brackets")
        .update(updates)
        .eq("id", bracket_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Bracket not found.")
    return result.data[0]


@app.delete("/user/brackets/{bracket_id}", status_code=204)
async def delete_user_bracket(
    bracket_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a bracket owned by the authenticated user."""
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    result = (
        sb.table("user_brackets")
        .delete()
        .eq("id", bracket_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Bracket not found.")


@app.get("/user/brackets/{bracket_id}/ratings")
async def get_bracket_ratings(
    bracket_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Get all ratings for a specific bracket."""
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    result = (
        sb.table("bracket_ratings")
        .select("*")
        .eq("bracket_id", bracket_id)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data


@app.post("/user/chat-history/{expert_id}")
async def save_chat_history(
    expert_id: str,
    body: ChatHistoryUpdate,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Save or update chat history for a user+expert pair."""
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    result = (
        sb.table("chat_history")
        .upsert({
            "user_id": user_id,
            "expert_id": expert_id,
            "messages": body.messages,
            "updated_at": "now()",
        }, on_conflict="user_id,expert_id")
        .execute()
    )
    return result.data[0] if result.data else {"status": "saved"}


@app.get("/user/chat-history/{expert_id}")
async def get_chat_history(
    expert_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Get chat history for a user+expert pair."""
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    result = (
        sb.table("chat_history")
        .select("*")
        .eq("user_id", user_id)
        .eq("expert_id", expert_id)
        .execute()
    )
    return result.data[0] if result.data else {"messages": []}
