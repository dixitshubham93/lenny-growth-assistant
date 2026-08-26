"""
tests/test_ingestion_fetch.py — Unit tests for ingestion/fetch.py.

All tests mock HTTP; no real network access required.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ingestion.fetch import (
    FetchResult,
    TreeEntry,
    download_transcript,
    fetch_changed_episodes,
    fetch_episode_tree,
    load_manifest,
    save_manifest,
    slug_from_path,
)


# ── Helpers ────────────────────────────────────────────────────────────────────
FAKE_TREE_RESPONSE = {
    "tree": [
        {"type": "blob", "path": "episodes/brian-chesky/transcript.md", "sha": "abc001"},
        {"type": "blob", "path": "episodes/ada-chen-rekhi/transcript.md", "sha": "abc002"},
        {"type": "blob", "path": "episodes/brian-chesky/README.md", "sha": "abc003"},   # excluded
        {"type": "tree", "path": "episodes/other-dir", "sha": "abc004"},               # excluded
        {"type": "blob", "path": "README.md", "sha": "abc005"},                        # excluded
    ]
}

FAKE_MARKDOWN = """\
---
guest: "Brian Chesky"
title: "Brian Chesky's new playbook"
publish_date: "2023-11-01"
youtube_url: "https://youtube.com/watch?v=test"
video_id: "test"
---

Brian Chesky (00:00:00):
Way too many founders apologize.

Lenny (00:01:01):
Today my guest is Brian Chesky.
"""


def _make_response(status: int, body: str | dict) -> httpx.Response:
    if isinstance(body, dict):
        content = json.dumps(body).encode()
        headers = {"content-type": "application/json"}
    else:
        content = body.encode()
        headers = {"content-type": "text/plain"}
    return httpx.Response(status_code=status, content=content, headers=headers)


# ── fetch_episode_tree ─────────────────────────────────────────────────────────
def test_tree_api_filters_transcript_paths():
    """Tree API response is filtered to only episodes/*/transcript.md blobs."""
    with patch("ingestion.fetch._get_with_retry") as mock_get:
        mock_get.return_value = _make_response(200, FAKE_TREE_RESPONSE)
        entries = fetch_episode_tree(token=None)

    assert len(entries) == 2
    paths = {e.path for e in entries}
    assert "episodes/brian-chesky/transcript.md" in paths
    assert "episodes/ada-chen-rekhi/transcript.md" in paths
    # Non-transcript blobs excluded
    assert all(e.path.endswith("transcript.md") for e in entries)


def test_tree_api_returns_correct_shas():
    """TreeEntry objects carry the correct SHA from the API response."""
    with patch("ingestion.fetch._get_with_retry") as mock_get:
        mock_get.return_value = _make_response(200, FAKE_TREE_RESPONSE)
        entries = fetch_episode_tree(token=None)

    sha_map = {slug_from_path(e.path): e.sha for e in entries}
    assert sha_map["brian-chesky"] == "abc001"
    assert sha_map["ada-chen-rekhi"] == "abc002"


def test_tree_api_raises_on_403():
    """403 response raises PermissionError (not swallowed)."""
    with patch("ingestion.fetch._get_with_retry") as mock_get:
        mock_get.return_value = _make_response(403, "Forbidden")
        with pytest.raises(PermissionError, match="403"):
            fetch_episode_tree(token=None)


def test_tree_api_raises_on_non_200():
    """Non-200/403/429 raises RuntimeError with status code in message."""
    with patch("ingestion.fetch._get_with_retry") as mock_get:
        mock_get.return_value = _make_response(500, "Internal Server Error")
        with pytest.raises(RuntimeError, match="500"):
            fetch_episode_tree(token=None)


# ── manifest_skips_unchanged ───────────────────────────────────────────────────
def test_manifest_skips_unchanged_sha(tmp_path):
    """Episodes whose SHA matches the manifest are returned as skipped=True."""
    manifest = {
        "episodes": {
            "brian-chesky": {"sha": "abc001", "chunk_count": 10},
        }
    }
    entries = [TreeEntry(path="episodes/brian-chesky/transcript.md", sha="abc001")]

    with patch("ingestion.fetch.download_transcript") as mock_dl:
        results = fetch_changed_episodes(manifest=manifest, tree_entries=entries, force=False)

    mock_dl.assert_not_called()
    assert len(results) == 1
    assert results[0].skipped is True
    assert results[0].ok is False


def test_manifest_fetches_when_sha_differs(tmp_path):
    """Episodes with a different SHA in manifest are downloaded."""
    manifest = {
        "episodes": {
            "brian-chesky": {"sha": "OLD_SHA", "chunk_count": 5},
        }
    }
    entries = [TreeEntry(path="episodes/brian-chesky/transcript.md", sha="NEW_SHA")]

    with patch("ingestion.fetch.download_transcript", return_value=FAKE_MARKDOWN) as mock_dl:
        results = fetch_changed_episodes(manifest=manifest, tree_entries=entries, force=False)

    mock_dl.assert_called_once_with("brian-chesky", token=None)
    assert results[0].ok is True
    assert results[0].markdown == FAKE_MARKDOWN


# ── download_transcript ────────────────────────────────────────────────────────
def test_download_transcript_returns_text():
    """Successful 200 response returns markdown text."""
    with patch("ingestion.fetch._get_with_retry") as mock_get:
        mock_get.return_value = _make_response(200, FAKE_MARKDOWN)
        text = download_transcript("brian-chesky", token=None)
    assert "Brian Chesky" in text
    assert "00:00:00" in text


def test_download_transcript_raises_on_404():
    """404 raises FileNotFoundError with slug name in message."""
    with patch("ingestion.fetch._get_with_retry") as mock_get:
        mock_get.return_value = _make_response(404, "Not Found")
        with pytest.raises(FileNotFoundError, match="brian-chesky"):
            download_transcript("brian-chesky", token=None)


def test_download_transcript_raises_on_timeout():
    """TimeoutException propagates from download_transcript."""
    with patch("ingestion.fetch._get_with_retry") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("timed out")
        with pytest.raises(httpx.TimeoutException):
            download_transcript("brian-chesky", token=None)


def test_fetch_changed_captures_404_as_error():
    """404 during batch fetch is captured as FetchResult.error (pipeline continues)."""
    manifest: dict = {"episodes": {}}
    entries = [TreeEntry(path="episodes/missing-episode/transcript.md", sha="sha-x")]

    with patch("ingestion.fetch.download_transcript", side_effect=FileNotFoundError("404")):
        results = fetch_changed_episodes(manifest=manifest, tree_entries=entries)

    assert results[0].error is not None
    assert results[0].ok is False
    assert results[0].skipped is False


# ── manifest load/save ─────────────────────────────────────────────────────────
def test_load_manifest_returns_empty_on_missing(tmp_path):
    """load_manifest returns {'episodes': {}} when file does not exist."""
    result = load_manifest(tmp_path / "manifest.json")
    assert result == {"episodes": {}}


def test_save_and_load_manifest_roundtrip(tmp_path):
    """Saved manifest is loaded back correctly."""
    data = {"episodes": {"brian-chesky": {"sha": "x", "chunk_count": 5}}}
    path = tmp_path / "manifest.json"
    save_manifest(data, path)
    loaded = load_manifest(path)
    assert loaded["episodes"]["brian-chesky"]["sha"] == "x"
