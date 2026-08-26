"""
api/routes/retrieve.py — POST /api/v1/retrieve

Debug / RAG endpoint: embeds the query, runs cosine similarity search, and
returns the top-k transcript chunks with full source metadata.

Behaviour:
- Returns 200 with empty results list when no chunks are indexed (graceful degradation).
- Propagates EmbeddingError → caught by handle_embedding_error → 503.
- Development endpoint; useful for RAG context verification and grounding.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.db.deps import get_db
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse, RetrievedChunkSchema
from app.services.retrieval import retrieve_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["retrieve"])


@router.post("/retrieve", response_model=RetrievalResponse)
async def post_retrieve(
    body: RetrievalRequest,
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RetrievalResponse:
    """
    Embed the query and return the top-k most similar transcript chunks.

    Results are ordered by cosine distance (ascending — most similar first).
    Returns an empty results list when the vector index has no chunks yet.
    """
    logger.info(
        "Retrieve request",
        extra={"component": "retrieve", "top_k": body.top_k, "query_len": len(body.query)},
    )

    chunks = await retrieve_chunks(
        query=body.query,
        db=db,
        settings=settings,
        top_k=body.top_k,
    )

    results = [
        RetrievedChunkSchema(
            chunk_id=c.chunk_id,
            episode_id=c.episode_id,
            title=c.title,
            guest=c.guest,
            date=c.date,
            source_file=c.source_file,
            youtube_url=c.youtube_url,
            video_id=c.video_id,
            chunk_index=c.chunk_index,
            start_timestamp=c.start_timestamp,
            end_timestamp=c.end_timestamp,
            word_count=c.word_count,
            text=c.text,
            cosine_distance=c.cosine_distance,
        )
        for c in chunks
    ]

    logger.info(
        "Retrieve response",
        extra={"component": "retrieve", "result_count": len(results)},
    )

    return RetrievalResponse(
        query=body.query,
        top_k=body.top_k,
        result_count=len(results),
        results=results,
    )
