"""
db/deps.py — FastAPI database session dependency.

Usage in routes:
    async def my_route(db: AsyncSession = Depends(get_db)):
        ...

The session is committed on clean exit and rolled back on exception.
Tests override this dependency to inject an in-memory SQLite session.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session_factory
from app.errors.exceptions import DatabaseError

logger = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a single AsyncSession per request.
    Commits on clean exit, rolls back on any exception.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.error(
                "Database error during request",
                extra={"component": "db"},
                exc_info=True,
            )
            raise DatabaseError(detail="A database error occurred. Please try again.") from exc
        except Exception:
            await session.rollback()
            raise
