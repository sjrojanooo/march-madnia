from __future__ import annotations

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    expert_id: str
    expert_name: str
    source: str
    style_summary: str


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[dict[str, str]] = Field(default_factory=list, max_length=50)


class AgentRateBracketRequest(BaseModel):
    user_bracket: dict[str, str]  # game_slot -> team_slug


class BracketSuggestion(BaseModel):
    game_slot: str
    current_pick: str
    suggested_pick: str
    reasoning: str


class AgentRateBracketResponse(BaseModel):
    expert_id: str
    rating: int = Field(..., ge=1, le=10)
    overall_assessment: str
    suggestions: list[BracketSuggestion]


class UserBracketCreate(BaseModel):
    picks: dict[str, str]  # game_slot -> team_slug
    name: str = Field(default="My Bracket", max_length=100)


class UserBracketUpdate(BaseModel):
    picks: dict[str, str] | None = None
    name: str | None = Field(default=None, max_length=100)


class UserBracketResponse(BaseModel):
    id: str
    user_id: str
    season: int
    picks: dict[str, str]
    name: str
    created_at: str
    updated_at: str


class ChatHistoryUpdate(BaseModel):
    messages: list[dict[str, str]] = Field(..., max_length=100)  # [{role: "user"|"assistant", content: "..."}]


class AuthRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=6, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
