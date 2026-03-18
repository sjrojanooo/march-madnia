from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from api.models import AgentRateBracketResponse, BracketSuggestion

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import from src.agents.expert_analysts (Phase 3 dependency).
# If the module doesn't exist yet, we expose stubs that return 503-style
# errors so the rest of the API still boots.
# ---------------------------------------------------------------------------
_EXPERTS_AVAILABLE = False
_stream_chat = None
_rate_bracket = None
_BracketContext = None
_EXPERT_PERSONAS: dict[str, Any] = {}

try:
    from src.agents.expert_analysts import (
        EXPERT_PERSONAS as _EXPERT_PERSONAS,
    )
    from src.agents.expert_analysts import (
        BracketContext as _BracketContext,
    )
    from src.agents.expert_analysts import (
        rate_bracket as _rate_bracket,
    )
    from src.agents.expert_analysts import (
        stream_chat as _stream_chat,
    )

    _EXPERTS_AVAILABLE = True
except ImportError:
    logger.warning(
        "src.agents.expert_analysts not found — agent endpoints will return 503. "
        "This module is created in Phase 3."
    )


def experts_available() -> bool:
    """Return True if the expert_analysts module was successfully imported."""
    return _EXPERTS_AVAILABLE


async def handle_chat(
    expert_id: str,
    message: str,
    conversation_history: list[dict[str, str]],
    bracket_context: Any,
    client: AsyncAnthropic,
) -> AsyncIterator[str]:
    """Yield SSE-formatted chunks from expert chat."""
    if _stream_chat is None:
        yield f"data: {json.dumps({'chunk': 'Expert analysts module not available.', 'done': True})}\n\n"
        return

    async for chunk in _stream_chat(
        expert_id, message, conversation_history, bracket_context, client
    ):
        yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"
    yield f"data: {json.dumps({'chunk': '', 'done': True})}\n\n"


async def handle_rate_bracket(
    expert_id: str,
    user_bracket: dict[str, str],
    bracket_context: Any,
    client: AsyncAnthropic,
) -> AgentRateBracketResponse:
    """Get bracket rating from expert persona."""
    if _rate_bracket is None:
        msg = "Expert analysts module not available."
        raise RuntimeError(msg)

    result = await _rate_bracket(expert_id, user_bracket, bracket_context, client)
    return AgentRateBracketResponse(
        expert_id=expert_id,
        rating=result.rating,
        overall_assessment=result.assessment,
        suggestions=[BracketSuggestion(**s) for s in result.suggestions],
    )


def get_bracket_context(bracket_data: Any, expert_data: Any) -> Any:
    """Build a BracketContext from app state, or return None if unavailable."""
    if _BracketContext is None:
        return None
    return _BracketContext(bracket_data=bracket_data, expert_data=expert_data)


def get_agent_list() -> list[dict[str, str]]:
    """Return list of available expert agents."""
    return [
        {
            "expert_id": eid,
            "expert_name": p["name"],
            "source": p["source"],
            "style_summary": p["style_summary"],
        }
        for eid, p in _EXPERT_PERSONAS.items()
    ]
