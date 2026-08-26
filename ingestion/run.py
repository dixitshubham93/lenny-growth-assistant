"""
ingestion/run.py — CLI entrypoint for the Lenny transcript ingestion pipeline.

Usage:
  python -m ingestion.run [--limit N] [--force] [--slug SLUG]

Examples:
  python -m ingestion.run --limit 3
  python -m ingestion.run --slug brian-chesky
  python -m ingestion.run --slug brian-chesky --force
  python -m ingestion.run           # full run (all episodes)

Environment variables (optional, read from .env):
  GITHUB_TOKEN    — raises GitHub API rate limit from 60 to 5000/hr
  CHUNK_SIZE      — target words per chunk (default: 500)
  CHUNK_OVERLAP   — overlap words between chunks (default: 100)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup: allow running as `python -m ingestion.run` from repo root ──
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load .env if python-dotenv is available (best-effort)
try:
    from dotenv import load_dotenv
    _env_path = _REPO_ROOT / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
        logging.getLogger(__name__).debug("Loaded .env from %s", _env_path)
except ImportError:
    pass

from ingestion.chunk import chunk_episode, chunk_to_dict
from ingestion.fetch import (
    fetch_changed_episodes,
    fetch_episode_tree,
    load_manifest,
    save_manifest,
    slug_from_path,
)
from ingestion.parse import episode_to_dict, parse_transcript

# ── Directories ────────────────────────────────────────────────────────────────
_PROCESSED_DIR = _REPO_ROOT / "ingestion" / "processed"
_EPISODES_DIR = _PROCESSED_DIR / "episodes"
_CHUNKS_DIR = _PROCESSED_DIR / "chunks"
_MANIFEST_PATH = _PROCESSED_DIR / "manifest.json"


# ── Logging setup ─────────────────────────────────────────────────────────────
def _configure_logging() -> None:
    level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


logger = logging.getLogger("ingestion.run")


# ── Helpers ────────────────────────────────────────────────────────────────────
def _ensure_dirs() -> None:
    for d in (_EPISODES_DIR, _CHUNKS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _write_episode_json(slug: str, data: dict) -> None:
    path = _EPISODES_DIR / f"{slug}.json"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _write_chunks_jsonl(slug: str, chunks: list[dict]) -> None:
    path = _CHUNKS_DIR / f"{slug}.jsonl"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    tmp.replace(path)


# ── Main pipeline ─────────────────────────────────────────────────────────────
def run(
    limit: int | None = None,
    force: bool = False,
    slug_filter: str | None = None,
) -> None:
    _ensure_dirs()

    github_token: str | None = os.environ.get("GITHUB_TOKEN") or None
    chunk_size: int = int(os.environ.get("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.environ.get("CHUNK_OVERLAP", "100"))

    if github_token:
        logger.info("GitHub token provided — rate limit: 5000 req/hr")
    else:
        logger.info("No GITHUB_TOKEN — rate limit: 60 req/hr (unauthenticated)")

    # ── Step 1: Discover all episodes via single Tree API call ─────────────────
    logger.info("=== Step 1: Discovering episodes via Git Tree API ===")
    try:
        tree_entries = fetch_episode_tree(token=github_token)
    except Exception as exc:
        logger.error("Failed to fetch repository tree: %s", exc)
        sys.exit(1)

    logger.info("Discovered %d transcript files", len(tree_entries))

    # Apply --limit
    if limit is not None:
        tree_entries = tree_entries[:limit]
        logger.info("--limit %d: processing first %d episodes", limit, len(tree_entries))

    # ── Step 2: Load manifest and find changed episodes ────────────────────────
    logger.info("=== Step 2: Comparing SHAs with local manifest ===")
    manifest = load_manifest(_MANIFEST_PATH)
    existing = manifest.get("episodes", {})
    total = len(tree_entries)
    would_skip = sum(
        1 for e in tree_entries
        if not force
        and (slug_filter is None or slug_from_path(e.path) == slug_filter)
        and existing.get(slug_from_path(e.path), {}).get("sha") == e.sha
    )
    logger.info(
        "%d total | %d unchanged (would skip) | %d to fetch",
        total, would_skip, total - would_skip,
    )

    # ── Step 3: Fetch changed transcripts ─────────────────────────────────────
    logger.info("=== Step 3: Fetching changed transcripts ===")
    fetch_results = fetch_changed_episodes(
        manifest=manifest,
        tree_entries=tree_entries,
        token=github_token,
        force=force,
        slug_filter=slug_filter,
    )

    n_fetched = sum(1 for r in fetch_results if r.ok)
    n_skipped = sum(1 for r in fetch_results if r.skipped)
    n_failed = sum(1 for r in fetch_results if r.error)
    logger.info("Fetched: %d | Skipped: %d | Failed: %d", n_fetched, n_skipped, n_failed)

    # ── Step 4: Parse + chunk each fetched episode ─────────────────────────────
    logger.info("=== Step 4: Parsing and chunking episodes ===")
    n_parsed = 0
    n_chunk_total = 0
    n_parse_errors = 0
    episodes_meta = manifest.setdefault("episodes", {})

    for result in fetch_results:
        if result.skipped:
            continue
        if result.error:
            logger.warning("Skipping '%s' — fetch error: %s", result.slug, result.error)
            continue

        try:
            parsed = parse_transcript(
                slug=result.slug,
                markdown=result.markdown,
                sha=result.sha,
            )
        except Exception as exc:
            logger.error("Parse error for '%s': %s", result.slug, exc)
            n_parse_errors += 1
            continue

        try:
            chunks = chunk_episode(parsed, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        except Exception as exc:
            logger.error("Chunk error for '%s': %s", result.slug, exc)
            n_parse_errors += 1
            continue

        # Write outputs
        episode_data = episode_to_dict(parsed)
        _write_episode_json(result.slug, episode_data)

        chunk_dicts = [chunk_to_dict(c) for c in chunks]
        _write_chunks_jsonl(result.slug, chunk_dicts)

        # Update manifest entry
        episodes_meta[result.slug] = {
            "sha": result.sha,
            "chunk_count": len(chunks),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Processed '%s' — %d turns → %d chunks (chunk_size=%d, overlap=%d)",
            result.slug, len(parsed.turns), len(chunks), chunk_size, chunk_overlap,
        )
        n_parsed += 1
        n_chunk_total += len(chunks)

    # ── Step 5: Save manifest ─────────────────────────────────────────────────
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["total_episodes_in_manifest"] = len(episodes_meta)
    save_manifest(manifest, _MANIFEST_PATH)

    # ── Final summary ─────────────────────────────────────────────────────────
    logger.info("=== Pipeline complete ===")
    logger.info(
        "Discovered: %d | Skipped: %d | Fetched: %d | Parsed: %d | "
        "Parse errors: %d | Fetch errors: %d | Total chunks: %d",
        total, n_skipped, n_fetched, n_parsed,
        n_parse_errors, n_failed, n_chunk_total,
    )
    logger.info("Manifest: %s", _MANIFEST_PATH)
    logger.info("Episodes: %s", _EPISODES_DIR)
    logger.info("Chunks:   %s", _CHUNKS_DIR)


# ── CLI ───────────────────────────────────────────────────────────────────────
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ingestion.run",
        description="Lenny Podcast Transcript Ingestion Pipeline",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process only the first N episodes (useful for testing).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download and re-process even if SHA is unchanged.",
    )
    parser.add_argument(
        "--slug", type=str, default=None,
        help="Process only this episode slug (e.g. brian-chesky).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    _configure_logging()
    args = _parse_args()
    run(limit=args.limit, force=args.force, slug_filter=args.slug)
