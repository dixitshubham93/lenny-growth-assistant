"""
tests/test_integration_ollama.py — Manual/optional Ollama integration test.

Run ONLY when Ollama is locally available:
    cd backend
    pytest ../tests/test_integration_ollama.py -v -s --run-integration

Skipped automatically in CI / when Ollama is not running.
Do not add this file to the standard test run.
"""
from __future__ import annotations

import os

import httpx
import pytest


def _ollama_available() -> bool:
    """Best-effort check whether Ollama is running on localhost:11434."""
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


import asyncio

def _db_url_configured() -> bool:
    """Return True only if DATABASE_URL env var is set to a non-empty value."""
    import os
    url = os.environ.get("DATABASE_URL", "")
    return bool(url and "postgresql" in url)


# Skip if Ollama isn't running OR if DATABASE_URL isn't configured
pytestmark = pytest.mark.skipif(
    not _ollama_available() or not _db_url_configured(),
    reason=(
        "Skipped: requires Ollama on localhost:11434 AND "
        "DATABASE_URL=postgresql+asyncpg://... in environment."
    ),
)


@pytest.mark.asyncio
async def test_ollama_health_endpoint():
    """GET /health must return 200 with real Ollama running."""
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    from app.main import app

    get_settings.cache_clear()
    os.environ.setdefault("LLM_PROVIDER", "ollama")
    os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    with TestClient(app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ollama_llm_health_endpoint():
    """GET /health/llm must report provider=ollama and reachable=true."""
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    from app.main import app

    get_settings.cache_clear()
    with TestClient(app) as c:
        resp = c.get("/health/llm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "ollama"
    assert body["reachable"] is True


@pytest.mark.asyncio
async def test_ollama_chat_endpoint():
    """POST /api/v1/chat must return a non-empty answer from qwen2.5:7b-instruct."""
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    from app.main import app

    get_settings.cache_clear()
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/chat",
            json={"message": "In one sentence, what is product-market fit?"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["answer"]) > 10
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen2.5:7b-instruct"
    print(f"\n[Ollama] Answer: {body['answer'][:300]}")
    print(f"[Ollama] Latency: {body['latency_ms']}ms")
