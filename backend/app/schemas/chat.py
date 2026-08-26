"""
schemas/chat.py — Request/response models for the chat endpoint.

Kept minimal for Phase 2.  RAG sources and session_id will be added in
Phase 6 when the full agent layer is wired up.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for POST /api/v1/chat"""
    message: str = Field(..., min_length=1, max_length=8000, description="User message")
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for context continuity (Phase 3+)"
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
