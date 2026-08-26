"""
tests/test_chat.py — Tests for the chat endpoint (Phase 3: session-aware).

Uses async TestClient with in-memory SQLite (no PostgreSQL / Ollama required).
All chat requests must include a session_id obtained from POST /api/v1/sessions.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_chat_returns_200(async_client):
    """POST /api/v1/chat with a valid session must return 200 with answer."""
    # Create a session first
    sess = await async_client.post("/api/v1/sessions")
    assert sess.status_code == 201
    sid = sess.json()["session_id"]

    resp = await async_client.post(
        "/api/v1/chat",
        json={"message": "What is product-market fit?", "session_id": sid},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert len(body["answer"]) > 0
    assert body["provider"] == "mock"
    assert "model" in body
    assert isinstance(body["sources"], list)
    assert body["session_id"] == sid


@pytest.mark.asyncio
async def test_chat_empty_message_returns_422(async_client):
    """POST /api/v1/chat with an empty message returns 422 validation error."""
    # We need a valid session even for validation tests (422 happens before DB access)
    sess = await async_client.post("/api/v1/sessions")
    sid = sess.json()["session_id"]

    resp = await async_client.post(
        "/api/v1/chat",
        json={"message": "", "session_id": sid},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_chat_missing_message_returns_422(async_client):
    """POST /api/v1/chat with no message field returns 422."""
    sess = await async_client.post("/api/v1/sessions")
    sid = sess.json()["session_id"]

    resp = await async_client.post("/api/v1/chat", json={"session_id": sid})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_missing_session_id_returns_422(async_client):
    """POST /api/v1/chat without session_id (now required) returns 422."""
    resp = await async_client.post(
        "/api/v1/chat",
        json={"message": "Tell me about retention"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_with_custom_system_prompt(async_client):
    """Custom system_prompt is accepted without error."""
    sess = await async_client.post("/api/v1/sessions")
    sid = sess.json()["session_id"]

    resp = await async_client.post(
        "/api/v1/chat",
        json={
            "message": "What is activation?",
            "session_id": sid,
            "system_prompt": "You are a concise assistant.",
        },
    )
    assert resp.status_code == 200
    assert "answer" in resp.json()


@pytest.mark.asyncio
async def test_chat_invalid_session_returns_404(async_client):
    """POST /api/v1/chat with a non-existent session_id returns 404."""
    resp = await async_client.post(
        "/api/v1/chat",
        json={"message": "Hello", "session_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "session_not_found"
