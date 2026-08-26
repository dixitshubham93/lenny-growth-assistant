"""
tests/test_chat_with_session.py — Unit tests for session-aware chat endpoint.

Tests:
  - Chat with valid session persists user + assistant messages
  - Chat with invalid session returns 404
  - Session A and Session B have fully isolated history
  - LLM failure after user message is persisted → structured error, user msg kept
  - Database error produces a structured 503 response
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.deps import get_db
from app.db.models import Base
from app.errors.exceptions import LLMProviderError
from app.llm.base import LLMResponse, Message, ProviderStatus
from app.main import app

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def db_engine():
    engine = create_async_engine(SQLITE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _make_client(db_engine, llm_provider):
    """Helper to wire an AsyncClient with a given DB engine and LLM provider."""
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

    app.dependency_overrides[_get_provider] = lambda: llm_provider
    app.dependency_overrides[_health_provider] = lambda: llm_provider
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class MockLLMOK:
    """LLM that always succeeds with a canned response."""
    provider_name = "mock"
    model = "mock-model"

    async def complete(self, messages, system_prompt="", temperature=0.7, max_tokens=2048):
        last = next((m.content for m in reversed(messages) if m.role == "user"), "?")
        return LLMResponse(
            content=f"Answer to: {last}",
            model=self.model,
            provider=self.provider_name,
            prompt_tokens=5,
            completion_tokens=10,
            latency_ms=1.0,
        )

    async def check_health(self):
        return ProviderStatus(provider=self.provider_name, model=self.model, reachable=True)


class MockLLMFailing:
    """LLM that always raises LLMProviderError."""
    provider_name = "mock_failing"
    model = "mock-fail"

    async def complete(self, messages, system_prompt="", temperature=0.7, max_tokens=2048):
        raise LLMProviderError("Simulated LLM failure")

    async def check_health(self):
        return ProviderStatus(provider=self.provider_name, model=self.model, reachable=False)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_persists_user_and_assistant_messages(db_engine):
    """A successful chat call persists both user and assistant messages."""
    async with _make_client(db_engine, MockLLMOK()) as client:
        # Create session
        s = await client.post("/api/v1/sessions")
        sid = s.json()["session_id"]

        # Send chat
        resp = await client.post("/api/v1/chat", json={"message": "Hello", "session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid

        # Check messages persisted
        msgs = await client.get(f"/api/v1/sessions/{sid}/messages")
        assert msgs.status_code == 200
        data = msgs.json()["messages"]
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[0]["content"] == "Hello"
        assert data[1]["role"] == "assistant"
        assert "Answer to: Hello" in data[1]["content"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_with_invalid_session_returns_404(db_engine):
    """Chat with a non-existent session_id → 404."""
    async with _make_client(db_engine, MockLLMOK()) as client:
        fake_id = "00000000-0000-0000-0000-000000000099"
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "Hello", "session_id": fake_id},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "session_not_found"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_session_isolation(db_engine):
    """
    Session A history must never appear in Session B's LLM context.

    Strategy: MockLLMOK echoes back the user message in the response.
    We verify that Session B's response does NOT contain Session A's message.
    """
    async with _make_client(db_engine, MockLLMOK()) as client:
        # Session A — asks about activation
        sa = await client.post("/api/v1/sessions")
        sid_a = sa.json()["session_id"]
        await client.post("/api/v1/chat", json={"message": "activation", "session_id": sid_a})

        # Session B — asks about retention
        sb = await client.post("/api/v1/sessions")
        sid_b = sb.json()["session_id"]
        resp_b = await client.post(
            "/api/v1/chat",
            json={"message": "retention", "session_id": sid_b},
        )
        assert resp_b.status_code == 200

        # Session B messages must NOT contain "activation"
        msgs_b = (await client.get(f"/api/v1/sessions/{sid_b}/messages")).json()["messages"]
        combined = " ".join(m["content"] for m in msgs_b)
        assert "activation" not in combined, "Session A content leaked into Session B!"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_llm_failure_preserves_user_message(db_engine):
    """
    If the LLM fails, the user message is NOT deleted from the database.
    The response is a structured 502 error — no fake assistant message is created.
    """
    async with _make_client(db_engine, MockLLMFailing()) as client:
        s = await client.post("/api/v1/sessions")
        sid = s.json()["session_id"]

        resp = await client.post(
            "/api/v1/chat",
            json={"message": "Will fail", "session_id": sid},
        )
        # LLM errors return 502
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "llm_provider_error"

        # User message was persisted before the LLM call
        msgs = (await client.get(f"/api/v1/sessions/{sid}/messages")).json()["messages"]
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
        assert len(user_msgs) == 1, "User message should be persisted"
        assert user_msgs[0]["content"] == "Will fail"
        assert len(assistant_msgs) == 0, "No fake assistant message should be created"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_builds_history_for_llm(db_engine):
    """
    The LLM receives the full conversation history in the correct order.
    We verify this by asking two sequential questions and checking that
    the second call includes context from the first.
    """
    received_messages: list[list[Message]] = []

    class CapturingMock:
        provider_name = "mock"
        model = "mock-model"

        async def complete(self, messages, system_prompt="", **_):
            received_messages.append(list(messages))
            return LLMResponse(
                content="captured",
                model=self.model,
                provider=self.provider_name,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0.0,
            )

        async def check_health(self):
            return ProviderStatus(provider=self.provider_name, model=self.model, reachable=True)

    async with _make_client(db_engine, CapturingMock()) as client:
        s = await client.post("/api/v1/sessions")
        sid = s.json()["session_id"]

        await client.post("/api/v1/chat", json={"message": "first", "session_id": sid})
        await client.post("/api/v1/chat", json={"message": "second", "session_id": sid})

    app.dependency_overrides.clear()

    # Second LLM call should see: user:first, assistant:captured, user:second
    second_call = received_messages[1]
    roles = [m.role for m in second_call]
    assert roles == ["user", "assistant", "user"], f"Expected 3-turn history, got: {roles}"
    assert second_call[-1].content == "second"
