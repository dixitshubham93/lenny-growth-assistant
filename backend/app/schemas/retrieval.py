"""
schemas/retrieval.py — Pydantic schemas for the /retrieve endpoint.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    """Body for POST /api/v1/retrieve."""
    query: str = Field(..., min_length=1, max_length=2000, description="Natural-language search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of chunks to return")


class RetrievedChunkSchema(BaseModel):
    """A single retrieved transcript chunk with full Phase 4 source metadata."""
    chunk_id: str
    episode_id: str
    title: str | None
    guest: str | None
    date: str | None
    source_file: str
    youtube_url: str | None
    video_id: str | None
    chunk_index: int
    start_timestamp: str | None
    end_timestamp: str | None
    word_count: int
    text: str
    cosine_distance: float = Field(description="0.0=identical, 2.0=maximally distant")


class RetrievalResponse(BaseModel):
    """Response for POST /api/v1/retrieve."""
    query: str
    top_k: int
    result_count: int
    results: list[RetrievedChunkSchema]
