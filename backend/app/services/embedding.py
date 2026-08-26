"""
services/embedding.py — Embed text via Ollama nomic-embed-text.

Produces VECTOR(768) compatible float lists.
Raises EmbeddingError on any failure (timeout, HTTP error, unexpected shape).
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import Settings
from app.errors.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

# Confirmed dimension at Phase 5 start via live curl to Ollama API
EXPECTED_DIM = 768


async def embed_text(text: str, settings: Settings) -> list[float]:
    """
    Embed a single text string using the configured Ollama embedding model.

    Returns a list of floats with length == EXPECTED_DIM (768).
    Raises EmbeddingError on timeout, HTTP error, or unexpected dimension.
    """
    model = settings.embedding_model
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise EmbeddingError(
            detail=f"Embedding timeout after 30s (model={model})",
            model=model,
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise EmbeddingError(
            detail=f"Embedding HTTP {exc.response.status_code} (model={model})",
            model=model,
        ) from exc
    except httpx.RequestError as exc:
        raise EmbeddingError(
            detail=f"Embedding request error: {exc} (model={model})",
            model=model,
        ) from exc

    data = resp.json()
    embedding: list[float] = data.get("embedding", [])

    if not embedding:
        raise EmbeddingError(
            detail=f"Ollama returned empty embedding (model={model})",
            model=model,
        )
    if len(embedding) != EXPECTED_DIM:
        raise EmbeddingError(
            detail=(
                f"Unexpected embedding dimension {len(embedding)} "
                f"(expected {EXPECTED_DIM}, model={model})"
            ),
            model=model,
        )

    logger.debug(
        "Embedded text",
        extra={"model": model, "input_len": len(text), "dim": len(embedding)},
    )
    return embedding


async def embed_batch(texts: list[str], settings: Settings) -> list[list[float]]:
    """
    Embed a list of texts sequentially.

    Ollama does not support batched embedding in a single request;
    each text makes one HTTP call.

    Returns list of float vectors in the same order as input.
    Raises EmbeddingError on the first failure.
    """
    results: list[list[float]] = []
    for i, text in enumerate(texts):
        logger.debug("Embedding batch item %d/%d", i + 1, len(texts))
        vec = await embed_text(text, settings)
        results.append(vec)
    return results
