"""
tests/conftest.py — Shared pytest fixtures.

- Provides a TestClient for the FastAPI app with settings overrides.
- Provides a mock LLM provider so unit tests never need Ollama running.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.llm.base import LLMResponse, Message, ProviderStatus
from app.main import app


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


# ── Settings overrides ────────────────────────────────────────────────────────

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


# ── TestClient fixture ────────────────────────────────────────────────────────

@pytest.fixture()
def client_with_mock_provider():
    """
    TestClient with the mock LLM provider dependency-injected.
    Use this for all unit tests that don't need real LLM calls.
    """
    from app.api.routes.chat import _get_provider
    from app.api.routes.health import _get_provider as _health_get_provider

    mock = MockLLMProvider()
    app.dependency_overrides[_get_provider] = lambda: mock
    app.dependency_overrides[_health_get_provider] = lambda: mock

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    """Plain TestClient — provider resolved from real settings."""
    with TestClient(app) as c:
        yield c
