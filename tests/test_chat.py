"""
tests/test_chat.py — Tests for the chat endpoint.

Uses the mock provider — no Ollama or Groq required.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_chat_returns_200(client_with_mock_provider: TestClient):
    """POST /api/v1/chat with a valid message must return 200 with answer."""
    resp = client_with_mock_provider.post(
        "/api/v1/chat",
        json={"message": "What is product-market fit?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert len(body["answer"]) > 0
    assert body["provider"] == "mock"
    assert "model" in body
    assert isinstance(body["sources"], list)


def test_chat_empty_message_returns_422(client_with_mock_provider: TestClient):
    """POST /api/v1/chat with an empty message must return 422 validation error."""
    resp = client_with_mock_provider.post(
        "/api/v1/chat",
        json={"message": ""},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "validation_error"


def test_chat_missing_message_returns_422(client_with_mock_provider: TestClient):
    """POST /api/v1/chat with no body must return 422."""
    resp = client_with_mock_provider.post("/api/v1/chat", json={})
    assert resp.status_code == 422


def test_chat_with_session_id(client_with_mock_provider: TestClient):
    """session_id is optional but should be echoed back in the response."""
    resp = client_with_mock_provider.post(
        "/api/v1/chat",
        json={"message": "Tell me about retention", "session_id": "sess-abc-123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "sess-abc-123"


def test_chat_with_custom_system_prompt(client_with_mock_provider: TestClient):
    """Custom system_prompt should be accepted without error."""
    resp = client_with_mock_provider.post(
        "/api/v1/chat",
        json={
            "message": "What is activation?",
            "system_prompt": "You are a concise assistant.",
        },
    )
    assert resp.status_code == 200
