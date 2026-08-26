"""
api/routes/sessions.py — Session management endpoints.

POST /api/v1/sessions                       — create session
GET  /api/v1/sessions/{session_id}          — get session info
GET  /api/v1/sessions/{session_id}/messages — list session messages
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud import create_session, get_messages, get_session
from app.db.deps import get_db
from app.errors.exceptions import SessionNotFoundError
from app.schemas.session import (
    MessageSchema,
    MessagesResponse,
    SessionCreateResponse,
    SessionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _session_to_schema(session) -> SessionResponse:
    return SessionResponse(
        session_id=str(session.id),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _message_to_schema(msg) -> MessageSchema:
    return MessageSchema(
        id=str(msg.id),
        session_id=str(msg.session_id),
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
        sources=msg.sources,
    )


@router.post(
    "",
    status_code=201,
    response_model=SessionCreateResponse,
    summary="Create a new chat session",
)
async def create_new_session(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SessionCreateResponse:
    """
    Creates a new isolated chat session.
    Returns the session_id to use in subsequent POST /api/v1/chat requests.
    """
    session = await create_session(db)
    logger.info(
        "New session created via API",
        extra={"component": "api", "session_id": str(session.id)},
    )
    response.headers["Location"] = f"/api/v1/sessions/{session.id}"
    return SessionCreateResponse(
        session_id=str(session.id),
        created_at=session.created_at,
    )


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get session information",
)
async def get_session_info(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Returns metadata for a given session. 404 if session does not exist."""
    session = await get_session(db, session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    return _session_to_schema(session)


@router.get(
    "/{session_id}/messages",
    response_model=MessagesResponse,
    summary="List all messages in a session",
)
async def list_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> MessagesResponse:
    """
    Returns all messages for a session in chronological order.
    404 if session does not exist.
    """
    session = await get_session(db, session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    messages = await get_messages(db, session_id, limit=1000)
    return MessagesResponse(
        session_id=session_id,
        messages=[_message_to_schema(m) for m in messages],
    )
