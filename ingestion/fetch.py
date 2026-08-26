"""
ingestion/fetch.py — GitHub transcript fetcher.

Strategy:
  1. Single Git Tree API call (recursive) to discover all episode paths + SHAs.
  2. Load local manifest — skip episodes whose SHA is unchanged.
  3. Download changed transcripts via raw.githubusercontent.com.
  4. Return FetchResult objects; never raise on per-episode failure.

No FastAPI imports. Requires: httpx.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
REPO_OWNER = "ChatPRD"
REPO_NAME = "lennys-podcast-transcripts"
REPO_BRANCH = "main"

TREE_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
    f"/git/trees/{REPO_BRANCH}?recursive=1"
)
RAW_BASE_URL = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"
)
GITHUB_API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

REQUEST_TIMEOUT = 30.0  # seconds per request
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # seconds; doubled each retry


# ── Data classes ───────────────────────────────────────────────────────────────
@dataclass
class TreeEntry:
    """One file entry from the Git Tree API response."""
    path: str   # e.g. "episodes/brian-chesky/transcript.md"
    sha: str    # blob SHA used for change detection


@dataclass
class FetchResult:
    """Outcome of fetching one episode transcript."""
    slug: str
    sha: str
    markdown: str = ""
    skipped: bool = False      # SHA unchanged — not re-downloaded
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.skipped


# ── Internal helpers ───────────────────────────────────────────────────────────
def _auth_headers(token: Optional[str]) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_with_retry(
    url: str,
    headers: dict[str, str],
    timeout: float = REQUEST_TIMEOUT,
) -> httpx.Response:
    """GET with exponential back-off on 429; raises on other errors."""
    delay = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        except httpx.TimeoutException as exc:
            if attempt == MAX_RETRIES:
                raise
            logger.warning("Timeout on attempt %d/%d for %s — retrying", attempt, MAX_RETRIES, url)
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", delay))
            logger.warning(
                "Rate limited (429) on attempt %d/%d — waiting %.1fs",
                attempt, MAX_RETRIES, retry_after,
            )
            time.sleep(retry_after)
            delay = max(delay * 2, retry_after)
            continue

        return resp

    raise RuntimeError(f"Exhausted {MAX_RETRIES} retries for {url}")


# ── Public API ─────────────────────────────────────────────────────────────────
def fetch_episode_tree(token: Optional[str] = None) -> list[TreeEntry]:
    """
    Fetch the full repository file tree in a single API call.
    Returns only entries matching 'episodes/*/transcript.md'.

    Raises httpx.HTTPError or RuntimeError if the tree cannot be loaded.
    """
    headers = _auth_headers(token)
    logger.info("Fetching repository tree from %s", TREE_API_URL)

    resp = _get_with_retry(TREE_API_URL, headers)

    if resp.status_code == 403:
        raise PermissionError(
            f"GitHub API returned 403 Forbidden. "
            f"Set GITHUB_TOKEN to raise the rate limit. URL: {TREE_API_URL}"
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Git Tree API returned HTTP {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()
    tree = data.get("tree", [])

    entries = [
        TreeEntry(path=item["path"], sha=item["sha"])
        for item in tree
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and item.get("path", "").startswith("episodes/")
        and item["path"].endswith("/transcript.md")
    ]

    logger.info("Discovered %d transcript files in repository tree", len(entries))
    return entries


def slug_from_path(path: str) -> str:
    """Extract episode slug from 'episodes/{slug}/transcript.md'."""
    parts = path.split("/")
    return parts[1] if len(parts) >= 3 else path


def download_transcript(slug: str, token: Optional[str] = None) -> str:
    """
    Download raw transcript markdown for *slug*.
    Returns raw text. Raises on 404 / timeout / network error.
    """
    url = f"{RAW_BASE_URL}/episodes/{slug}/transcript.md"
    headers = _auth_headers(token)
    logger.debug("Downloading transcript for '%s'", slug)

    resp = _get_with_retry(url, headers)

    if resp.status_code == 404:
        raise FileNotFoundError(f"transcript.md not found for slug '{slug}' (404)")
    if resp.status_code == 403:
        raise PermissionError(f"GitHub 403 for '{slug}' — check GITHUB_TOKEN")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} fetching '{slug}': {resp.text[:200]}")

    return resp.text


# ── Manifest helpers ───────────────────────────────────────────────────────────
def load_manifest(manifest_path: Path) -> dict:
    """
    Load the SHA manifest.  Returns an empty dict if the file does not exist.
    Schema: {"episodes": {"slug": {"sha": "...", "chunk_count": N}}}
    """
    if not manifest_path.exists():
        return {"episodes": {}}
    try:
        with manifest_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read manifest (%s) — starting fresh: %s", manifest_path, exc)
        return {"episodes": {}}


def save_manifest(manifest: dict, manifest_path: Path) -> None:
    """Persist the manifest to disk (atomic write via temp file)."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    tmp.replace(manifest_path)
    logger.debug("Manifest saved to %s", manifest_path)


# ── High-level batch fetcher ───────────────────────────────────────────────────
def fetch_changed_episodes(
    manifest: dict,
    tree_entries: list[TreeEntry],
    token: Optional[str] = None,
    force: bool = False,
    slug_filter: Optional[str] = None,
) -> list[FetchResult]:
    """
    Compare tree_entries against manifest; download only changed episodes.

    Args:
        manifest:     Current manifest dict (mutated in place on success).
        tree_entries: Tree data from fetch_episode_tree().
        token:        Optional GitHub API token.
        force:        Re-download even if SHA matches.
        slug_filter:  If set, process only this slug.

    Returns:
        List of FetchResult — one per episode in tree_entries.
    """
    existing: dict = manifest.setdefault("episodes", {})
    results: list[FetchResult] = []

    for entry in tree_entries:
        slug = slug_from_path(entry.path)

        if slug_filter is not None and slug != slug_filter:
            continue

        cached = existing.get(slug, {})
        if not force and cached.get("sha") == entry.sha:
            logger.debug("Skipping '%s' — SHA unchanged", slug)
            results.append(FetchResult(slug=slug, sha=entry.sha, skipped=True))
            continue

        try:
            markdown = download_transcript(slug, token=token)
            results.append(FetchResult(slug=slug, sha=entry.sha, markdown=markdown))
            logger.info("Fetched '%s' (%d chars)", slug, len(markdown))
        except FileNotFoundError as exc:
            logger.warning("404 for '%s': %s", slug, exc)
            results.append(FetchResult(slug=slug, sha=entry.sha, error=str(exc)))
        except PermissionError as exc:
            logger.error("403 for '%s': %s", slug, exc)
            results.append(FetchResult(slug=slug, sha=entry.sha, error=str(exc)))
        except (httpx.TimeoutException, RuntimeError) as exc:
            logger.error("Fetch error for '%s': %s", slug, exc)
            results.append(FetchResult(slug=slug, sha=entry.sha, error=str(exc)))

    return results
