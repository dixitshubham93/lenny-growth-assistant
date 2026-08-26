"""
tests/test_health.py — Tests for health endpoints.

All tests use the mock provider — no Ollama required.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_returns_200(client_with_mock_provider: TestClient):
    """GET /health must return HTTP 200 with status='ok'."""
    resp = client_with_mock_provider.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "environment" in body


def test_health_llm_returns_200_with_mock(client_with_mock_provider: TestClient):
    """GET /health/llm must return HTTP 200 and report the provider as reachable."""
    resp = client_with_mock_provider.get("/health/llm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["provider"] == "mock"
    assert body["status"] == "ok"
