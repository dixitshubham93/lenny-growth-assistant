"""
db/engine.py — Async SQLAlchemy engine and session factory.

The engine is created lazily from DATABASE_URL (env var).
Production: postgresql+asyncpg://...
Tests:      sqlite+aiosqlite:////:memory:  (via dependency override)
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_database_url() -> str:
    settings = get_settings()
    if not settings.database_url:
        raise ValueError(
            "DATABASE_URL is not configured. "
            "Set it in your .env file: "
            "DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lenny_db"
        )
    return settings.database_url


def get_engine() -> AsyncEngine:
    """Return the singleton async engine, creating it if needed."""
    global _engine
    if _engine is None:
        url = _get_database_url()
        logger.info(
            "Creating database engine",
            extra={"component": "db"},
        )
        _engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,   # detect stale connections
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


def override_engine(engine: AsyncEngine) -> None:
    """
    Replace the global engine — used in tests to inject a SQLite engine.
    Also resets the session factory so it picks up the new engine.
    """
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )
