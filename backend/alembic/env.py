"""
alembic/env.py — Async-compatible Alembic environment configuration.

Uses DATABASE_URL from the environment (or .env file) via the app Settings.
Supports autogenerate from SQLAlchemy ORM models.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make sure `app` package is importable when running alembic from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import ORM Base so Alembic can autogenerate migrations
from app.db.models import Base  # noqa: E402

# ── Alembic Config ─────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    """Read DATABASE_URL from env, overriding alembic.ini placeholder."""
    # Try app Settings first (reads from .env)
    try:
        from app.core.config import get_settings
        url = get_settings().database_url
        if url:
            return url
    except Exception:
        pass
    # Fallback to raw env var
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Set it in your .env file before running alembic."
        )
    return url


# ── Offline mode ────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online async mode ────────────────────────────────────────────────────────

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against a live PostgreSQL connection (async)."""
    url = _get_url()
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = url  # override ini placeholder

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
