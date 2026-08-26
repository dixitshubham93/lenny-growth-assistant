"""
schemas/session.py — Request/response models for session endpoints.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SessionCreateResponse(BaseModel):
    """Response for POST /api/v1/sessions"""
    session_id: str
    created_at: datetime


class SessionResponse(BaseModel):
    """Response for GET /api/v1/sessions/{session_id}"""
    session_id: str
    created_at: datetime
    updated_at: datetime


class MessageSchema(BaseModel):
    """A single persisted message."""
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    sources: list | None = None


class MessagesResponse(BaseModel):
    """Response for GET /api/v1/sessions/{session_id}/messages"""
    session_id: str
    messages: list[MessageSchema]
