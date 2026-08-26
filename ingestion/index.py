"""
ingestion/index.py — Embed and upsert Phase 4 JSONL chunks into PostgreSQL.

CLI: python -m ingestion.index [--slug SLUG] [--limit N] [--force]

  --slug SLUG   Process only the named episode (e.g. 'brian-chesky').
                Can be passed once per run.  Omit to process all episodes.
  --limit N     Stop after processing at most N episodes (useful for testing).
  --force       Re-embed episodes that already have embeddings in the DB.
                Without --force, episodes with indexed_at already set are skipped.

Idempotency:
  Uses INSERT ... ON CONFLICT (chunk_id) DO UPDATE so re-running is safe.
  Without --force, the WHERE clause skips chunks that already have embeddings.

Reads:
  ingestion/processed/chunks/{slug}.jsonl  (Phase 4 output)
  DATABASE_URL, OLLAMA_BASE_URL, EMBEDDING_MODEL from .env or environment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env from repo root (one level up from ingestion/)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE)
    except ImportError:
        pass  # dotenv not installed — rely on environment variables

# Add backend/ to sys.path so we can import app.*
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import Settings

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ingestion.index")

# ── Embedding ──────────────────────────────────────────────────────────────

EXPECTED_DIM = 768


async def _embed(text: str, settings: Settings, client: httpx.AsyncClient) -> list[float]:
    """Embed text via Ollama. Returns list[float] of length 768."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
    resp = await client.post(
        url,
        json={"model": settings.embedding_model, "prompt": text},
        timeout=60.0,
    )
    resp.raise_for_status()
    vec: list[float] = resp.json().get("embedding", [])
    if len(vec) != EXPECTED_DIM:
        raise ValueError(f"Unexpected embedding dim {len(vec)} (expected {EXPECTED_DIM})")
    return vec


# ── Indexer ────────────────────────────────────────────────────────────────

async def _index_episode(
    slug: str,
    chunks_dir: Path,
    session_factory: async_sessionmaker,
    settings: Settings,
    force: bool,
) -> tuple[int, int, int]:
    """
    Embed and upsert all chunks from a single episode JSONL file.

    Returns (indexed, skipped, errors).
    """
    from app.db.models import TranscriptChunk  # noqa: F401 — used for __tablename__

    jsonl_path = chunks_dir / f"{slug}.jsonl"
    if not jsonl_path.exists():
        logger.warning("No JSONL found for slug '%s' at %s", slug, jsonl_path)
        return 0, 0, 0

    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        logger.warning("Empty JSONL for slug '%s'", slug)
        return 0, 0, 0

    chunks = [json.loads(line) for line in lines]
    indexed = skipped = errors = 0
    now = datetime.now(timezone.utc)

    async with httpx.AsyncClient() as client:
        async with session_factory() as db:
            for chunk in chunks:
                chunk_id = chunk["chunk_id"]
                try:
                    # Check if already indexed (unless --force)
                    if not force:
                        from sqlalchemy import text as sql_text
                        result = await db.execute(
                            sql_text(
                                "SELECT indexed_at FROM transcript_chunks "
                                "WHERE chunk_id = :cid AND embedding IS NOT NULL"
                            ),
                            {"cid": chunk_id},
                        )
                        row = result.fetchone()
                        if row is not None:
                            skipped += 1
                            continue

                    # Embed
                    vec = await _embed(chunk["text"], settings, client)
                    vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

                    # Upsert — idempotent via ON CONFLICT (chunk_id) DO UPDATE
                    stmt = (
                        pg_insert(TranscriptChunk.__table__)
                        .values(
                            chunk_id=chunk_id,
                            episode_id=chunk["episode_id"],
                            title=chunk.get("title"),
                            guest=chunk.get("guest"),
                            date=chunk.get("date"),
                            source_file=chunk["source_file"],
                            youtube_url=chunk.get("youtube_url"),
                            video_id=chunk.get("video_id"),
                            chunk_index=chunk["chunk_index"],
                            start_timestamp=chunk.get("start_timestamp"),
                            end_timestamp=chunk.get("end_timestamp"),
                            word_count=chunk.get("word_count", 0),
                            text=chunk["text"],
                            embedding=vec_literal,
                            indexed_at=now,
                        )
                        .on_conflict_do_update(
                            index_elements=["chunk_id"],
                            set_={
                                "embedding": vec_literal,
                                "indexed_at": now,
                            },
                        )
                    )
                    await db.execute(stmt)
                    indexed += 1

                    if indexed % 10 == 0:
                        logger.info(
                            "  %s: %d/%d indexed", slug, indexed, len(chunks)
                        )

                except Exception as exc:
                    logger.error("  Error on chunk %s: %s", chunk_id, exc)
                    errors += 1
                    continue

            await db.commit()

    return indexed, skipped, errors


async def _main(args: argparse.Namespace) -> None:
    settings = Settings()  # reads from environment / .env

    if not settings.database_url:
        logger.error("DATABASE_URL is not set. Cannot index without a database.")
        sys.exit(1)

    chunks_dir = _REPO_ROOT / "ingestion" / "processed" / "chunks"
    if not chunks_dir.exists():
        logger.error("Chunks directory not found: %s", chunks_dir)
        logger.error("Run `python -m ingestion.run` first to generate chunks.")
        sys.exit(1)

    # Determine slugs to process
    if args.slug:
        slugs = [args.slug]
    else:
        slugs = sorted(p.stem for p in chunks_dir.glob("*.jsonl"))

    if not slugs:
        logger.warning("No JSONL files found in %s", chunks_dir)
        return

    if args.limit:
        slugs = slugs[: args.limit]

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    logger.info(
        "Indexing %d episode(s) | force=%s | model=%s",
        len(slugs),
        args.force,
        settings.embedding_model,
    )

    total_indexed = total_skipped = total_errors = 0
    for slug in slugs:
        logger.info("Processing: %s", slug)
        n_idx, n_skip, n_err = await _index_episode(
            slug=slug,
            chunks_dir=chunks_dir,
            session_factory=session_factory,
            settings=settings,
            force=args.force,
        )
        logger.info(
            "  Done: indexed=%d skipped=%d errors=%d", n_idx, n_skip, n_err
        )
        total_indexed += n_idx
        total_skipped += n_skip
        total_errors += n_err

    await engine.dispose()

    logger.info(
        "Indexing complete: total_indexed=%d total_skipped=%d total_errors=%d",
        total_indexed,
        total_skipped,
        total_errors,
    )
    if total_errors:
        logger.warning("%d chunks failed to index.", total_errors)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed and upsert Phase 4 JSONL chunks into PostgreSQL/pgvector."
    )
    parser.add_argument(
        "--slug",
        metavar="SLUG",
        help=(
            "Process only this episode slug (e.g. 'brian-chesky'). "
            "Omit to process all episodes in ingestion/processed/chunks/."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Stop after indexing at most N episodes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed and overwrite chunks that already have embeddings.",
    )
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
