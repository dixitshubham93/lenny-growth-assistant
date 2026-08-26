"""
tests/test_retrieval.py — Unit tests for the /api/v1/retrieve endpoint
and the retrieval service.

Mocks:
  - embed_text: returns a deterministic fake vector
  - DB: injects in-memory rows via SQLAlchemy mock / monkeypatch

No PostgreSQL or Ollama required.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.errors.exceptions import EmbeddingError
from app.services.embedding import EXPECTED_DIM

# ── Shared helpers ─────────────────────────────────────────────────────────────

FAKE_VEC = [0.1] * EXPECTED_DIM


def _fake_chunk_row(**overrides):
    """Return a mapping that looks like a DB row from transcript_chunks."""
    base = {
        "chunk_id": "ada-chen-rekhi-000",
        "episode_id": "ada-chen-rekhi",
        "title": "Feeling stuck? | Ada Chen Rekhi",
        "guest": "Ada Chen Rekhi",
        "date": "2023-11-01",
        "source_file": "episodes/ada-chen-rekhi/transcript.md",
        "youtube_url": "https://youtube.com/watch?v=test",
        "video_id": "test",
        "chunk_index": 0,
        "start_timestamp": "00:00:00",
        "end_timestamp": "00:04:30",
        "word_count": 512,
        "text": "Ada Chen Rekhi (00:00:00):\nIt's a terrible...",
        "cosine_distance": 0.12,
    }
    base.update(overrides)
    return base


# ── Service-level tests (no HTTP, no real DB) ─────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_returns_chunks_ordered_by_cosine_distance():
    """retrieve_chunks should return a sorted list of RetrievedChunk dataclasses."""
    from app.services.retrieval import retrieve_chunks
    from app.core.config import Settings

    settings = Settings.model_construct(
        ollama_base_url="http://localhost:11434",
        embedding_model="nomic-embed-text",
    )

    # Two rows with different distances
    row1 = _fake_chunk_row(chunk_id="ep-000", cosine_distance=0.10)
    row2 = _fake_chunk_row(chunk_id="ep-001", cosine_distance=0.25)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [row1, row2]
    mock_db.execute.return_value = mock_result

    with patch("app.services.retrieval.embed_text", return_value=FAKE_VEC):
        chunks = await retrieve_chunks("how to build a product", mock_db, settings, top_k=2)

    assert len(chunks) == 2
    assert chunks[0].chunk_id == "ep-000"
    assert chunks[0].cosine_distance == pytest.approx(0.10)
    assert chunks[1].cosine_distance == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_chunks():
    """retrieve_chunks should return [] gracefully when no chunks are indexed."""
    from app.services.retrieval import retrieve_chunks
    from app.core.config import Settings

    settings = Settings.model_construct(
        ollama_base_url="http://localhost:11434",
        embedding_model="nomic-embed-text",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    with patch("app.services.retrieval.embed_text", return_value=FAKE_VEC):
        chunks = await retrieve_chunks("anything", mock_db, settings, top_k=5)

    assert chunks == []


@pytest.mark.asyncio
async def test_retrieve_preserves_all_metadata_fields():
    """Every Phase 4 metadata field must survive retrieval."""
    from app.services.retrieval import retrieve_chunks
    from app.core.config import Settings

    settings = Settings.model_construct(
        ollama_base_url="http://localhost:11434",
        embedding_model="nomic-embed-text",
    )

    row = _fake_chunk_row()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [row]
    mock_db.execute.return_value = mock_result

    with patch("app.services.retrieval.embed_text", return_value=FAKE_VEC):
        chunks = await retrieve_chunks("test", mock_db, settings, top_k=1)

    c = chunks[0]
    assert c.episode_id == "ada-chen-rekhi"
    assert c.source_file == "episodes/ada-chen-rekhi/transcript.md"
    assert c.youtube_url == "https://youtube.com/watch?v=test"
    assert c.start_timestamp == "00:00:00"
    assert c.end_timestamp == "00:04:30"
    assert c.guest == "Ada Chen Rekhi"
    assert c.date == "2023-11-01"
    assert c.word_count == 512


# ── Endpoint-level tests (via async_client) ─────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_endpoint_returns_200_with_empty_results(async_client):
    """POST /api/v1/retrieve → 200 with empty results when no chunks indexed."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    with (
        patch("app.services.retrieval.embed_text", return_value=FAKE_VEC),
        patch("app.api.routes.retrieve.retrieve_chunks", return_value=[]),
    ):
        resp = await async_client.post(
            "/api/v1/retrieve",
            json={"query": "product growth", "top_k": 5},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_count"] == 0
    assert data["results"] == []
    assert data["query"] == "product growth"
    assert data["top_k"] == 5


@pytest.mark.asyncio
async def test_retrieve_endpoint_returns_503_on_embedding_error(async_client):
    """POST /api/v1/retrieve → 503 when Ollama embedding fails."""
    with patch(
        "app.api.routes.retrieve.retrieve_chunks",
        side_effect=EmbeddingError("timeout", model="nomic-embed-text"),
    ):
        resp = await async_client.post(
            "/api/v1/retrieve",
            json={"query": "product growth", "top_k": 5},
        )

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "embedding_error"


@pytest.mark.asyncio
async def test_retrieve_endpoint_validates_query_length(async_client):
    """POST /api/v1/retrieve → 422 for empty query string."""
    resp = await async_client.post(
        "/api/v1/retrieve",
        json={"query": "", "top_k": 5},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_endpoint_respects_top_k(async_client):
    """top_k in request body is passed through to the service."""
    from app.services.retrieval import RetrievedChunk

    fake_chunks = [
        RetrievedChunk(
            chunk_id=f"ep-{i:03d}",
            episode_id="test",
            title=None,
            guest=None,
            date=None,
            source_file="episodes/test/transcript.md",
            youtube_url=None,
            video_id=None,
            chunk_index=i,
            start_timestamp=None,
            end_timestamp=None,
            word_count=100,
            text="sample text",
            cosine_distance=0.1 * i,
        )
        for i in range(3)
    ]

    with patch("app.api.routes.retrieve.retrieve_chunks", return_value=fake_chunks):
        resp = await async_client.post(
            "/api/v1/retrieve",
            json={"query": "test", "top_k": 3},
        )

    assert resp.status_code == 200
    assert resp.json()["result_count"] == 3
    assert len(resp.json()["results"]) == 3

@pytest.mark.asyncio
async def test_retrieve_filters_high_cosine_distance():
    """Chunks with distance > settings.rag_max_distance should be filtered out."""
    from app.services.retrieval import retrieve_chunks
    from app.core.config import Settings

    settings = Settings.model_construct(
        ollama_base_url="http://localhost:11434",
        embedding_model="nomic-embed-text",
        rag_max_distance=0.60,
    )

    # 0.40 -> keep, 0.55 -> keep, 0.65 -> drop
    row1 = _fake_chunk_row(chunk_id="ep-000", cosine_distance=0.40)
    row2 = _fake_chunk_row(chunk_id="ep-001", cosine_distance=0.55)
    row3 = _fake_chunk_row(chunk_id="ep-002", cosine_distance=0.65)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [row1, row2, row3]
    mock_db.execute.return_value = mock_result

    with patch("app.services.retrieval.embed_text", return_value=FAKE_VEC):
        chunks = await retrieve_chunks("irrelevant query", mock_db, settings, top_k=5)

    assert len(chunks) == 2
    assert chunks[0].chunk_id == "ep-000"
    assert chunks[1].chunk_id == "ep-001"
