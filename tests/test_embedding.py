"""
tests/test_embedding.py — Unit tests for app.services.embedding.

All HTTP calls are mocked with pytest-httpx or pytest monkeypatch.
No Ollama or network access required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import Settings
from app.errors.exceptions import EmbeddingError
from app.services.embedding import EXPECTED_DIM, embed_text, embed_batch

# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_SETTINGS = Settings.model_construct(
    ollama_base_url="http://localhost:11434",
    embedding_model="nomic-embed-text",
)

FAKE_VECTOR = [0.1] * EXPECTED_DIM


def _make_mock_response(vector: list[float] | None = None, status_code: int = 200):
    """Build a mock httpx.Response."""
    import httpx

    body = {"embedding": vector or FAKE_VECTOR}
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embed_text_returns_correct_length():
    """embed_text should return a list of EXPECTED_DIM floats."""
    with patch("app.services.embedding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = _make_mock_response(FAKE_VECTOR)

        result = await embed_text("test query", FAKE_SETTINGS)

    assert isinstance(result, list)
    assert len(result) == EXPECTED_DIM
    assert all(isinstance(v, float) for v in result)


@pytest.mark.asyncio
async def test_embed_text_raises_on_timeout():
    """Timeouts should raise EmbeddingError, not propagate raw httpx errors."""
    import httpx

    with patch("app.services.embedding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(EmbeddingError) as exc_info:
            await embed_text("test", FAKE_SETTINGS)

    assert "timeout" in exc_info.value.detail.lower()
    assert exc_info.value.model == "nomic-embed-text"


@pytest.mark.asyncio
async def test_embed_text_raises_on_http_500():
    """HTTP 500 from Ollama should raise EmbeddingError."""
    import httpx

    with patch("app.services.embedding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = _make_mock_response(status_code=500)

        with pytest.raises(EmbeddingError) as exc_info:
            await embed_text("test", FAKE_SETTINGS)

    assert "500" in exc_info.value.detail


@pytest.mark.asyncio
async def test_embed_text_raises_on_wrong_dimension():
    """Unexpected embedding dimension should raise EmbeddingError with clear message."""
    wrong_dim_vector = [0.1] * 384  # wrong dimension

    with patch("app.services.embedding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = _make_mock_response(wrong_dim_vector)

        with pytest.raises(EmbeddingError) as exc_info:
            await embed_text("test", FAKE_SETTINGS)

    assert "384" in exc_info.value.detail  # actual dim mentioned
    assert "768" in exc_info.value.detail  # expected dim mentioned


@pytest.mark.asyncio
async def test_embed_batch_calls_embed_for_each_item():
    """embed_batch should call embed_text for every item in the list."""
    texts = ["first", "second", "third"]

    with patch("app.services.embedding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = _make_mock_response(FAKE_VECTOR)

        results = await embed_batch(texts, FAKE_SETTINGS)

    assert len(results) == len(texts)
    assert all(len(r) == EXPECTED_DIM for r in results)
    # One POST per text
    assert mock_client.post.call_count == len(texts)


@pytest.mark.asyncio
async def test_embed_text_raises_on_empty_embedding():
    """Empty embedding list in Ollama response should raise EmbeddingError."""
    import httpx

    # Build a real-looking Response with status 200 but empty embedding
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"embedding": []}
    mock_resp.raise_for_status.return_value = None  # 200 — does NOT raise

    with patch("app.services.embedding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp

        with pytest.raises(EmbeddingError) as exc_info:
            await embed_text("test", FAKE_SETTINGS)

    assert "empty" in exc_info.value.detail.lower()
