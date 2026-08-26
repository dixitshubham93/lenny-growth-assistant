"""
tests/conftest.py — Shared pytest fixtures.

- MockLLMProvider: deterministic mock, no network calls.
- db_engine: in-memory SQLite engine for tests.
- async_client: AsyncClient with mock LLM + SQLite DB (use for chat + session tests).
- client_with_mock_provider: sync TestClient with mock LLM + SQLite DB (health tests).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.db.deps import get_db
from app.db.models import Base
from app.llm.base import LLMResponse, Message, ProviderStatus
from app.main import app

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


# ── Mock provider ─────────────────────────────────────────────────────────────

class MockLLMProvider:
    """
    Deterministic mock that satisfies the LLMProvider Protocol.
    Never makes network calls.
    """

    provider_name = "mock"
    model = "mock-model"

    async def complete(
        self,
        messages: list[Message],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        last_user_message = next(
            (m.content for m in reversed(messages) if m.role == "user"), "?"
        )
        return LLMResponse(
            content=f"Mock response to: {last_user_message}",
            model=self.model,
            provider=self.provider_name,
            prompt_tokens=10,
            completion_tokens=20,
            latency_ms=1.0,
        )

    async def check_health(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider_name,
            model=self.model,
            reachable=True,
            detail="Mock provider is always reachable.",
        )


# ── Settings helpers ──────────────────────────────────────────────────────────

def make_ollama_settings(**overrides) -> Settings:
    """Return a Settings instance configured for Ollama (no real key needed)."""
    get_settings.cache_clear()
    return Settings(
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="qwen2.5:7b-instruct",
        app_env="development",
        **overrides,
    )


def make_groq_settings(**overrides) -> Settings:
    """Return a Settings instance configured for Groq with a fake key."""
    get_settings.cache_clear()
    return Settings(
        llm_provider="groq",
        groq_api_key="gsk_test_fake_key_for_unit_tests",
        groq_model="llama-3.3-70b-versatile",
        app_env="development",
        **overrides,
    )


# ── DB override helper ────────────────────────────────────────────────────────

def _make_db_override(engine):
    """Return an async generator function that yields an in-memory SQLite session."""
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return override_get_db


# ── Async fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def db_engine():
    """In-memory SQLite engine: creates all tables, tears down after each test."""
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
    AsyncClient with MockLLMProvider + in-memory SQLite via get_db override.
    Use this for ALL chat and session tests.
    """
    from app.api.routes.chat import _get_provider
    from app.api.routes.health import _get_provider as _health_get_provider

    mock = MockLLMProvider()
    app.dependency_overrides[_get_provider] = lambda: mock
    app.dependency_overrides[_health_get_provider] = lambda: mock
    app.dependency_overrides[get_db] = _make_db_override(db_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── Sync fixture (health tests only) ─────────────────────────────────────────

@pytest.fixture()
def client_with_mock_provider():
    """
    Sync TestClient with MockLLMProvider + in-memory SQLite DB override.
    Suitable for health endpoint tests (no session creation needed).
    """
    import asyncio
    from app.api.routes.chat import _get_provider
    from app.api.routes.health import _get_provider as _health_get_provider
    from fastapi.testclient import TestClient

    async def _setup():
        engine = create_async_engine(SQLITE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return engine

    async def _teardown(engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    engine = asyncio.get_event_loop().run_until_complete(_setup())
    mock = MockLLMProvider()
    app.dependency_overrides[_get_provider] = lambda: mock
    app.dependency_overrides[_health_get_provider] = lambda: mock
    app.dependency_overrides[get_db] = _make_db_override(engine)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    asyncio.get_event_loop().run_until_complete(_teardown(engine))


@pytest.fixture()
def client():
    """Plain TestClient — provider resolved from real settings."""
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
