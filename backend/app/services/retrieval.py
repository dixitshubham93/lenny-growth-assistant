"""
services/retrieval.py — Cosine similarity search over transcript_chunks.

Uses pgvector's <=> (cosine distance) operator for exact nearest-neighbour search.
No ANN index (IVFFlat/HNSW) at Phase 5 — exact search is correct for ~269 episodes.

Returns empty list when no chunks are indexed (graceful degradation —
callers receive an empty context, LLM answers without grounding).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.embedding import embed_text

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved transcript chunk with all Phase 4 source metadata."""
    chunk_id: str
    episode_id: str
    title: str | None
    guest: str | None
    date: str | None
    source_file: str
    youtube_url: str | None
    video_id: str | None
    chunk_index: int
    start_timestamp: str | None
    end_timestamp: str | None
    word_count: int
    text: str
    # 0.0 = identical, 2.0 = maximally distant (cosine distance, not similarity)
    cosine_distance: float


async def retrieve_chunks(
    query: str,
    db: AsyncSession,
    settings: Settings,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """
    Embed the query and return the top_k most similar transcript chunks.

    SQL generated (pgvector cosine distance operator <=>):
        SELECT *, embedding <=> :vec AS cosine_distance
        FROM transcript_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> :vec
        LIMIT :k

    Returns empty list when:
    - No chunks are indexed yet (graceful degradation)
    - EmbeddingError propagates upward to caller (not caught here)
    """
    query_vec = await embed_text(query, settings)

    # Format as pgvector literal: '[0.1, 0.2, ...]'
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"

    sql = text(
        """
        SELECT
            chunk_id, episode_id, title, guest, date,
            source_file, youtube_url, video_id,
            chunk_index, start_timestamp, end_timestamp,
            word_count, text,
            embedding <=> CAST(:vec AS vector) AS cosine_distance
        FROM transcript_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :k
        """
    )

    result = await db.execute(sql, {"vec": vec_literal, "k": top_k})
    rows = result.mappings().all()

    if not rows:
        logger.debug("retrieve_chunks: no indexed chunks found for query")
        return []

    chunks = [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            episode_id=row["episode_id"],
            title=row["title"],
            guest=row["guest"],
            date=row["date"],
            source_file=row["source_file"],
            youtube_url=row["youtube_url"],
            video_id=row["video_id"],
            chunk_index=row["chunk_index"],
            start_timestamp=row["start_timestamp"],
            end_timestamp=row["end_timestamp"],
            word_count=row["word_count"],
            text=row["text"],
            cosine_distance=float(row["cosine_distance"]),
        )
        for row in rows
        if float(row["cosine_distance"]) <= settings.rag_max_distance
    ]

    logger.debug(
        "retrieve_chunks: returned %d chunks, top cosine_distance=%.4f",
        len(chunks),
        chunks[0].cosine_distance if chunks else 0.0,
    )
    return chunks
