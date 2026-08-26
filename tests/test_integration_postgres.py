"""
tests/test_integration_postgres.py — Real PostgreSQL integration tests.

Auto-skipped unless DATABASE_URL is set in the environment AND points to
a reachable PostgreSQL instance.

Run with:
  cd backend
  DATABASE_URL=postgresql+asyncpg://... python -m pytest ../tests/test_integration_postgres.py -v -s
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.db.models import Base
from app.db.deps import get_db
from app.main import app

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Skip entire module if DATABASE_URL is not set or not PostgreSQL
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or "postgresql" not in DATABASE_URL,
    reason="Skipped: DATABASE_URL not set or not PostgreSQL. "
           "Set DATABASE_URL=postgresql+asyncpg://... to run.",
)


@pytest_asyncio.fixture(scope="module")
async def pg_engine():
    """Create tables in the real PostgreSQL DB, clean up after module."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # Verify connectivity
        await conn.execute(text("SELECT 1"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def pg_client(pg_engine):
    from app.api.routes.chat import _get_provider
    from app.api.routes.health import _get_provider as _health_provider
    from tests.conftest import MockLLMProvider

    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False, autoflush=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    mock = MockLLMProvider()
    app.dependency_overrides[_get_provider] = lambda: mock
    app.dependency_overrides[_health_provider] = lambda: mock
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pg_create_and_retrieve_session(pg_client):
    """Real DB: create a session and retrieve it."""
    create_resp = await pg_client.post("/api/v1/sessions")
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    get_resp = await pg_client.get(f"/api/v1/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_pg_chat_persists_messages(pg_client):
    """Real DB: chat messages are persisted."""
    s = await pg_client.post("/api/v1/sessions")
    sid = s.json()["session_id"]

    resp = await pg_client.post("/api/v1/chat", json={"message": "Hello PG", "session_id": sid})
    assert resp.status_code == 200

    msgs = (await pg_client.get(f"/api/v1/sessions/{sid}/messages")).json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_pg_session_isolation(pg_client):
    """Real DB: Session A and Session B have independent message histories."""
    sa = await pg_client.post("/api/v1/sessions")
    sb = await pg_client.post("/api/v1/sessions")
    sid_a = sa.json()["session_id"]
    sid_b = sb.json()["session_id"]

    await pg_client.post("/api/v1/chat", json={"message": "Session A question", "session_id": sid_a})
    await pg_client.post("/api/v1/chat", json={"message": "Session B question", "session_id": sid_b})

    msgs_a = (await pg_client.get(f"/api/v1/sessions/{sid_a}/messages")).json()["messages"]
    msgs_b = (await pg_client.get(f"/api/v1/sessions/{sid_b}/messages")).json()["messages"]

    content_a = " ".join(m["content"] for m in msgs_a)
    content_b = " ".join(m["content"] for m in msgs_b)

    assert "Session B" not in content_a, "Session B content leaked into Session A!"
    assert "Session A" not in content_b, "Session A content leaked into Session B!"
