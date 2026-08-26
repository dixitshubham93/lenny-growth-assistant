"""
db/crud.py — Database CRUD operations.

All functions accept an AsyncSession and perform a single logical operation.
They do NOT manage transactions — the caller (route or dependency) owns the transaction.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session

logger = logging.getLogger(__name__)


# ── Sessions ──────────────────────────────────────────────────────────────────

async def create_session(db: AsyncSession, metadata: dict | None = None) -> Session:
    """Insert a new session row and return it."""
    session = Session(metadata_=metadata or {})
    db.add(session)
    await db.flush()   # assign id without committing
    await db.refresh(session)
    logger.info(
        "Session created",
        extra={"component": "db", "session_id": str(session.id)},
    )
    return session


async def get_session(db: AsyncSession, session_id: str | uuid.UUID) -> Session | None:
    """Fetch a session by ID.  Returns None if not found."""
    try:
        sid = uuid.UUID(str(session_id))
    except ValueError:
        return None
    result = await db.execute(select(Session).where(Session.id == sid))
    return result.scalar_one_or_none()


async def delete_session(db: AsyncSession, session_id: str | uuid.UUID) -> bool:
    """Delete a session by ID. Returns True if deleted, False if not found."""
    session = await get_session(db, session_id)
    if session is None:
        return False
    await db.delete(session)
    await db.flush()
    logger.info("Session deleted", extra={"component": "db", "session_id": str(session.id)})
    return True


# ── Messages ──────────────────────────────────────────────────────────────────

async def create_message(
    db: AsyncSession,
    session_id: str | uuid.UUID,
    role: str,
    content: str,
    sources: list[dict] | None = None,
) -> Message:
    """Insert a message and update the parent session's updated_at."""
    sid = uuid.UUID(str(session_id))
    now = datetime.now(timezone.utc)

    message = Message(session_id=sid, role=role, content=content, sources=sources or [])
    db.add(message)

    # Touch session.updated_at without loading the whole object
    await db.execute(
        update(Session)
        .where(Session.id == sid)
        .values(updated_at=now)
    )

    await db.flush()
    await db.refresh(message)
    logger.info(
        "Message persisted",
        extra={
            "component": "db",
            "session_id": str(sid),
            "role": role,
            "message_id": str(message.id),
            "sources_count": len(sources or []),
        },
    )
    return message


async def get_messages(
    db: AsyncSession,
    session_id: str | uuid.UUID,
    limit: int = 20,
) -> list[Message]:
    """
    Return the most recent `limit` messages for a session in chronological order.

    Strategy: fetch the LAST `limit` rows ordered DESC, then reverse.
    This keeps context window bounded while preserving message order.
    """
    sid = uuid.UUID(str(session_id))
    result = await db.execute(
        select(Message)
        .where(Message.session_id == sid)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    # Return in chronological (oldest-first) order
    return list(reversed(rows))
