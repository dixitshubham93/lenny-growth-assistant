"""
tests/test_provider_factory.py — Tests for the LLM provider factory.

Covers:
  - Factory returns OllamaProvider when LLM_PROVIDER=ollama
  - Factory returns GroqProvider when LLM_PROVIDER=groq (with valid key)
  - Missing GROQ_API_KEY raises ProviderConfigError
  - Missing GROQ_MODEL raises ProviderConfigError
  - Unknown provider name raises ProviderConfigError
  - LLM provider error converts to structured API response (502)
  - LLM unavailable converts to structured API response (503)
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.errors.exceptions import LLMProviderError, ProviderConfigError, ProviderUnavailableError
from app.llm.factory import get_llm_provider
from app.llm.groq import GroqProvider
from app.llm.ollama import OllamaProvider


# ── Factory selection ─────────────────────────────────────────────────────────

def test_factory_returns_ollama_provider():
    """get_llm_provider with LLM_PROVIDER=ollama must return an OllamaProvider."""
    get_settings.cache_clear()
    settings = Settings(
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="qwen2.5:7b-instruct",
        app_env="development",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"
    assert provider.model == "qwen2.5:7b-instruct"


def test_factory_returns_groq_provider():
    """get_llm_provider with LLM_PROVIDER=groq must return a GroqProvider."""
    get_settings.cache_clear()
    settings = Settings(
        llm_provider="groq",
        groq_api_key="gsk_test_fake_key",
        groq_model="llama-3.3-70b-versatile",
        app_env="development",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, GroqProvider)
    assert provider.provider_name == "groq"
    assert provider.model == "llama-3.3-70b-versatile"


def test_factory_raises_on_unknown_provider():
    """An unknown LLM_PROVIDER value must raise ProviderConfigError."""
    get_settings.cache_clear()
    # Settings won't accept an invalid literal; test at factory level directly.
    # We patch settings to bypass the literal validation for this test.
    settings = Settings(
        llm_provider="ollama",   # pass literal validation
        app_env="development",
    )
    settings.llm_provider = "banana"  # type: ignore — simulate bad runtime value
    with pytest.raises(ProviderConfigError):
        get_llm_provider(settings)


# ── Groq missing credentials ──────────────────────────────────────────────────

def test_settings_raises_on_missing_groq_api_key():
    """
    Settings must raise ValidationError when LLM_PROVIDER=groq
    but GROQ_API_KEY is empty.
    """
    get_settings.cache_clear()
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            llm_provider="groq",
            groq_api_key="",           # missing key
            groq_model="llama-3.3-70b-versatile",
            app_env="development",
        )
    assert "GROQ_API_KEY" in str(exc_info.value)


def test_settings_raises_on_missing_groq_model():
    """
    Settings must raise ValidationError when LLM_PROVIDER=groq
    but GROQ_MODEL is empty.
    """
    get_settings.cache_clear()
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            llm_provider="groq",
            groq_api_key="gsk_test_fake_key",
            groq_model="",             # missing model
            app_env="development",
        )
    assert "GROQ_MODEL" in str(exc_info.value)


# ── API-level error conversion ────────────────────────────────────────────────

async def _raise_provider_error(messages, **_):
    raise LLMProviderError(provider="mock", detail="Backend exploded.")


async def _raise_unavailable(messages, **_):
    raise ProviderUnavailableError(provider="mock", detail="Mock offline.")


def test_llm_provider_error_returns_502(client_with_mock_provider):
    """
    If the LLM provider raises LLMProviderError during a chat request,
    the API must return HTTP 502 with a structured error body.
    """
    from app.api.routes.chat import _get_provider
    from app.llm.base import LLMResponse, Message, ProviderStatus
    from app.main import app

    class FailingProvider:
        provider_name = "mock"
        model = "mock"

        async def complete(self, messages, system_prompt="", **kwargs):
            raise LLMProviderError(provider="mock", detail="Simulated failure.")

        async def check_health(self):
            return ProviderStatus(provider="mock", model="mock", reachable=True)

    app.dependency_overrides[_get_provider] = lambda: FailingProvider()
    try:
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            resp = c.post("/api/v1/chat", json={"message": "Hello"})
        assert resp.status_code == 502
        body = resp.json()
        assert body["error"]["code"] == "llm_provider_error"
    finally:
        app.dependency_overrides.clear()


def test_provider_unavailable_returns_503(client_with_mock_provider):
    """
    If the LLM provider raises ProviderUnavailableError,
    the API must return HTTP 503.
    """
    from app.api.routes.chat import _get_provider
    from app.llm.base import ProviderStatus
    from app.main import app

    class UnavailableProvider:
        provider_name = "mock"
        model = "mock"

        async def complete(self, messages, system_prompt="", **kwargs):
            raise ProviderUnavailableError(provider="mock", detail="Service down.")

        async def check_health(self):
            return ProviderStatus(provider="mock", model="mock", reachable=False)

    app.dependency_overrides[_get_provider] = lambda: UnavailableProvider()
    try:
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            resp = c.post("/api/v1/chat", json={"message": "Hello"})
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "provider_unavailable"
    finally:
        app.dependency_overrides.clear()
