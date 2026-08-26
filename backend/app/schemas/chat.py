"""
schemas/chat.py — Request/response models for the chat endpoint.

Phase 3: session_id is now required.
Phase 6: sources, artifact, skill_used added to ChatResponse (all optional with defaults).
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


class SourceCitation(BaseModel):
    """A single transcript source citation returned by the agent."""
    chunk_id: str
    episode_id: str
    title: str | None = None
    guest: str | None = None
    start_timestamp: str | None = None
    end_timestamp: str | None = None
    source_file: str
    youtube_url: str | None = None
    cosine_distance: float = 0.0


class ChatResponse(BaseModel):
    """Response from POST /api/v1/chat"""
    # ── Existing fields (Phase 2/3 — unchanged) ───────────────────────────────
    answer: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    session_id: str | None = None

    # ── Phase 6 additions (all optional with safe defaults) ───────────────────
    sources: list[SourceCitation] = Field(
        default_factory=list,
        description="Transcript chunks used to ground this answer"
    )
    artifact: str | None = Field(
        default=None,
        description="Generated Markdown artifact (e.g. Ship 30 essay)"
    )
    skill_used: str | None = Field(
        default=None,
        description="Agent skill invoked: 'grounded_qa' | 'ship30' | None"
    )
    retrieval_count: int = Field(
        default=0,
        description="Number of transcript chunks retrieved"
    )
