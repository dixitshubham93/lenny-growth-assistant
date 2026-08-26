"""
tests/test_integration_pgvector.py — Integration tests for pgvector retrieval.

Requires:
  - DATABASE_URL set AND pointing to a PostgreSQL db with pgvector extension
  - OLLAMA_BASE_URL set AND Ollama running with nomic-embed-text

These tests are automatically skipped in CI if either service is unavailable.
"""
from __future__ import annotations

import json
import os

import pytest
import pytest_asyncio

# Skip entire module if DATABASE_URL is not a PostgreSQL URL
_DB_URL = os.getenv("DATABASE_URL", "")
_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "")


def _has_postgres() -> bool:
    return "postgresql" in _DB_URL or "asyncpg" in _DB_URL


def _has_ollama() -> bool:
    return bool(_OLLAMA_URL)


pytestmark = pytest.mark.skipif(
    not (_has_postgres() and _has_ollama()),
    reason="DATABASE_URL (PostgreSQL) and OLLAMA_BASE_URL both required for pgvector integration tests",
)


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_index_and_retrieve_roundtrip():
    """
    Index a single synthetic chunk, then retrieve it by a semantically similar query.
    Verifies: embed → upsert → cosine search returns the chunk.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import Settings
    from app.services.embedding import embed_text
    from app.services.retrieval import retrieve_chunks

    settings = Settings()
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    test_chunk_id = "integration-test-chunk-000"
    test_text = "Lenny Rachitsky discusses product-market fit strategies for early-stage startups."

    # Embed the test text
    vec = await embed_text(test_text, settings)
    assert len(vec) == 768, f"Expected 768-dim vector, got {len(vec)}"

    vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    from sqlalchemy import text as sql_text
    from datetime import datetime, timezone

    # Upsert test chunk
    async with factory() as db:
        await db.execute(
            sql_text(
                """
                INSERT INTO transcript_chunks
                  (chunk_id, episode_id, source_file, chunk_index, word_count, text, embedding, indexed_at)
                VALUES
                  (:chunk_id, :episode_id, :source_file, :chunk_index, :word_count,
                   :text, CAST(:embedding AS vector), :indexed_at)
                ON CONFLICT (chunk_id) DO UPDATE SET
                  embedding = CAST(EXCLUDED.embedding AS vector),
                  indexed_at = EXCLUDED.indexed_at
                """
            ),
            {
                "chunk_id": test_chunk_id,
                "episode_id": "integration-test",
                "source_file": "episodes/integration-test/transcript.md",
                "chunk_index": 0,
                "word_count": len(test_text.split()),
                "text": test_text,
                "embedding": vec_literal,
                "indexed_at": datetime.now(timezone.utc),
            },
        )
        await db.commit()

    # Retrieve with a semantically related query
    async with factory() as db:
        results = await retrieve_chunks(
            query="startup product market fit",
            db=db,
            settings=settings,
            top_k=5,
        )

    await engine.dispose()

    assert results, "Expected at least one result"
    chunk_ids = [r.chunk_id for r in results]
    assert test_chunk_id in chunk_ids, f"Test chunk not found in results: {chunk_ids}"
    assert results[0].cosine_distance >= 0.0


@pytest.mark.asyncio
async def test_idempotent_indexing():
    """
    Running the same upsert twice must not create a duplicate row.
    Verifies ON CONFLICT (chunk_id) DO UPDATE behaviour.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import text as sql_text
    from app.core.config import Settings
    from app.services.embedding import embed_text
    from datetime import datetime, timezone

    settings = Settings()
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    test_chunk_id = "integration-idempotency-chunk-000"
    test_text = "Testing idempotent upsert for pgvector Phase 5."

    vec = await embed_text(test_text, settings)
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    upsert_sql = sql_text(
        """
        INSERT INTO transcript_chunks
          (chunk_id, episode_id, source_file, chunk_index, word_count, text, embedding, indexed_at)
        VALUES
          (:chunk_id, :episode_id, :source_file, :chunk_index, :word_count,
           :text, CAST(:embedding AS vector), :indexed_at)
        ON CONFLICT (chunk_id) DO UPDATE SET
          embedding = CAST(EXCLUDED.embedding AS vector),
          indexed_at = EXCLUDED.indexed_at
        """
    )
    params = {
        "chunk_id": test_chunk_id,
        "episode_id": "integration-test",
        "source_file": "episodes/integration-test/transcript.md",
        "chunk_index": 0,
        "word_count": 10,
        "text": test_text,
        "embedding": vec_literal,
        "indexed_at": datetime.now(timezone.utc),
    }

    async with factory() as db:
        await db.execute(upsert_sql, params)
        await db.commit()

    # Run it again — must not duplicate
    async with factory() as db:
        await db.execute(upsert_sql, params)
        await db.commit()

    # Count rows with this chunk_id — must be exactly 1
    async with factory() as db:
        result = await db.execute(
            sql_text("SELECT COUNT(*) FROM transcript_chunks WHERE chunk_id = :cid"),
            {"cid": test_chunk_id},
        )
        count = result.scalar()

    await engine.dispose()
    assert count == 1, f"Expected 1 row, got {count} (idempotency failed)"
