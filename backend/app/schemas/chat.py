"""
schemas/chat.py — Request/response models for the chat endpoint.

Phase 3: session_id is now required. A session must be created via
POST /api/v1/sessions before sending a chat message.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for POST /api/v1/chat"""
    message: str = Field(..., min_length=1, max_length=8000, description="User message")
    session_id: str = Field(
        ...,
        description="Session ID from POST /api/v1/sessions (required)"
    )
    system_prompt: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional system prompt override"
    )


class ChatResponse(BaseModel):
    """Response from POST /api/v1/chat"""
    answer: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    sources: list = Field(
        default_factory=list,
        description="Transcript sources (populated in Phase 6 when RAG is wired)"
    )
    session_id: str | None = None
