"""
tests/test_sessions.py — Unit tests for session API endpoints.

Uses an in-memory SQLite database (via aiosqlite) instead of PostgreSQL.
No running database server required.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.deps import get_db
from app.db.models import Base
from app.llm.base import LLMResponse, Message, ProviderStatus
from app.main import app

# ── SQLite in-memory engine ───────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


class _MockLLM:
    provider_name = "mock"
    model = "mock-model"

    async def complete(self, messages, system_prompt="", **_):
        last = next((m.content for m in reversed(messages) if m.role == "user"), "?")
        return LLMResponse(
            content=f"Mock: {last}", model=self.model, provider=self.provider_name,
            prompt_tokens=5, completion_tokens=5, latency_ms=1.0,
        )

    async def check_health(self):
        return ProviderStatus(provider=self.provider_name, model=self.model, reachable=True)


@pytest_asyncio.fixture()
async def db_engine():
    """Create a fresh in-memory SQLite engine per test with all tables."""
    engine = create_async_engine(SQLITE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def async_client(db_engine):
    """
    AsyncClient with:
    - Mock LLM provider injected
    - In-memory SQLite DB injected via get_db override
    """
    from app.api.routes.chat import _get_provider
    from app.api.routes.health import _get_provider as _health_provider

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    mock = _MockLLM()
    app.dependency_overrides[_get_provider] = lambda: mock
    app.dependency_overrides[_health_provider] = lambda: mock
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session_returns_201(async_client):
    """POST /api/v1/sessions creates a session and returns 201."""
    response = await async_client.post("/api/v1/sessions")
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert "created_at" in data
    assert len(data["session_id"]) == 36  # UUID format


@pytest.mark.asyncio
async def test_get_session_returns_200(async_client):
    """GET /api/v1/sessions/{id} returns session metadata."""
    create_resp = await async_client.post("/api/v1/sessions")
    session_id = create_resp.json()["session_id"]

    response = await async_client.get(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_unknown_session_returns_404(async_client):
    """GET /api/v1/sessions/{unknown_id} returns a 404 error."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await async_client.get(f"/api/v1/sessions/{fake_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "session_not_found"


@pytest.mark.asyncio
async def test_get_messages_returns_empty_list(async_client):
    """A new session has no messages."""
    create_resp = await async_client.post("/api/v1/sessions")
    session_id = create_resp.json()["session_id"]

    response = await async_client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_get_messages_unknown_session_returns_404(async_client):
    """GET messages for unknown session → 404."""
    fake_id = "00000000-0000-0000-0000-000000000001"
    response = await async_client.get(f"/api/v1/sessions/{fake_id}/messages")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "session_not_found"


@pytest.mark.asyncio
async def test_two_sessions_are_independent(async_client):
    """Two sessions exist independently and don't interfere."""
    resp_a = await async_client.post("/api/v1/sessions")
    resp_b = await async_client.post("/api/v1/sessions")
    id_a = resp_a.json()["session_id"]
    id_b = resp_b.json()["session_id"]
    assert id_a != id_b

    # Both should be retrievable
    assert (await async_client.get(f"/api/v1/sessions/{id_a}")).status_code == 200
    assert (await async_client.get(f"/api/v1/sessions/{id_b}")).status_code == 200
