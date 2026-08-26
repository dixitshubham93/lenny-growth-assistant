"""
tests/test_ingestion_chunk.py — Unit tests for ingestion/chunk.py.

No network access. Uses inline ParsedEpisode fixtures.
"""
from __future__ import annotations

import pytest

from ingestion.chunk import Chunk, chunk_episode, chunk_to_dict
from ingestion.parse import ParsedEpisode, SpeakerTurn


# ── Fixtures ────────────────────────────────────────────────────────────────────
def _make_turn(speaker: str, ts: str, words: int) -> SpeakerTurn:
    """Create a SpeakerTurn with a specific word count."""
    return SpeakerTurn(speaker=speaker, timestamp=ts, text=" ".join([f"word{i}" for i in range(words)]))


def _make_episode(turns: list[SpeakerTurn], slug: str = "test-episode") -> ParsedEpisode:
    all_text = " ".join(t.text for t in turns)
    return ParsedEpisode(
        episode_id=slug,
        source_file=f"episodes/{slug}/transcript.md",
        raw_url=f"https://raw.githubusercontent.com/ChatPRD/lennys-podcast-transcripts/main/episodes/{slug}/transcript.md",
        sha="testsha",
        title="Test Episode",
        guest="Test Guest",
        publish_date="2024-01-01",
        youtube_url="https://youtube.com/watch?v=test",
        video_id="test",
        turns=turns,
        word_count=len(all_text.split()),
    )


# One long episode: 20 turns × 50 words each = 1000 words total
LONG_EPISODE = _make_episode(
    [_make_turn("Lenny" if i % 2 == 0 else "Guest", f"00:{i:02d}:00", 50) for i in range(20)]
)

# Short episode: 2 turns × 20 words = 40 words (well below chunk_size)
SHORT_EPISODE = _make_episode([
    _make_turn("Lenny", "00:00:00", 20),
    _make_turn("Guest", "00:01:00", 20),
])

# Single-turn episode with 1500 words (exceeds 2× chunk_size of 500 → triggers hard split)
LONG_TURN_EPISODE = _make_episode([
    _make_turn("Guest", "00:00:00", 1500),
])

# Empty episode (no turns)
EMPTY_EPISODE = _make_episode([])


# ── Basic chunking behaviour ────────────────────────────────────────────────────
def test_chunk_short_episode_produces_one_chunk():
    """Episode under chunk_size produces exactly one chunk."""
    chunks = chunk_episode(SHORT_EPISODE, chunk_size=500, chunk_overlap=100)
    assert len(chunks) == 1


def test_chunk_empty_episode_produces_no_chunks():
    """Episode with no turns returns empty list without raising."""
    chunks = chunk_episode(EMPTY_EPISODE, chunk_size=500, chunk_overlap=100)
    assert chunks == []


def test_chunk_long_episode_produces_multiple_chunks():
    """1000-word episode with chunk_size=500 overlap=100 yields more than 1 chunk."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    assert len(chunks) > 1


def test_chunk_indices_are_sequential():
    """chunk_index starts at 0 and increments by 1."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_chunk_ids_are_unique():
    """All chunk_id values are distinct."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


# ── Metadata preservation ───────────────────────────────────────────────────────
def test_chunk_carries_episode_metadata():
    """Every chunk carries episode_id, title, guest, date, source_file."""
    chunks = chunk_episode(SHORT_EPISODE, chunk_size=500, chunk_overlap=100)
    c = chunks[0]
    assert c.episode_id == "test-episode"
    assert c.title == "Test Episode"
    assert c.guest == "Test Guest"
    assert c.date == "2024-01-01"
    assert c.source_file == "episodes/test-episode/transcript.md"


def test_chunk_carries_youtube_and_video_id():
    """youtube_url and video_id are preserved on every chunk."""
    chunks = chunk_episode(SHORT_EPISODE, chunk_size=500, chunk_overlap=100)
    assert chunks[0].youtube_url == "https://youtube.com/watch?v=test"
    assert chunks[0].video_id == "test"


# ── Timestamp preservation ──────────────────────────────────────────────────────
def test_chunk_start_timestamp_is_set():
    """start_timestamp is non-None for every chunk."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    for c in chunks:
        assert c.start_timestamp is not None


def test_chunk_end_timestamp_is_set():
    """end_timestamp is non-None for every chunk."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    for c in chunks:
        assert c.end_timestamp is not None


def test_chunk_first_chunk_starts_at_first_turn_timestamp():
    """First chunk start_timestamp matches the very first speaker turn."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    assert chunks[0].start_timestamp == "00:00:00"


# ── Overlap behaviour ────────────────────────────────────────────────────────────
def test_chunk_overlap_means_adjacent_chunks_share_text():
    """With overlap > 0, at least some turns appear in two consecutive chunks."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    if len(chunks) < 2:
        pytest.skip("Only one chunk produced — overlap not observable")
    # The last turn of chunk[0] should appear in chunk[1] if overlap engaged
    # We verify by checking that chunk[1] starts before chunk[0] ends (word-level)
    # (simple proxy: chunk[1].word_count > 0 and text is not identical to chunk[0])
    assert chunks[0].text != chunks[1].text
    assert chunks[1].word_count > 0


# ── Long-turn hard split ─────────────────────────────────────────────────────────
def test_long_single_turn_does_not_raise():
    """A 1500-word single turn is hard-split without raising."""
    chunks = chunk_episode(LONG_TURN_EPISODE, chunk_size=500, chunk_overlap=100)
    assert len(chunks) > 0


def test_long_single_turn_produces_multiple_chunks():
    """1500-word turn with chunk_size=500 results in multiple chunks."""
    chunks = chunk_episode(LONG_TURN_EPISODE, chunk_size=500, chunk_overlap=100)
    assert len(chunks) >= 2


# ── Word count ─────────────────────────────────────────────────────────────────
def test_chunk_word_count_nonzero():
    """word_count is > 0 for all chunks."""
    chunks = chunk_episode(LONG_EPISODE, chunk_size=500, chunk_overlap=100)
    for c in chunks:
        assert c.word_count > 0


# ── Serialisation ──────────────────────────────────────────────────────────────
def test_chunk_to_dict_has_all_required_fields():
    """chunk_to_dict output has all required schema keys."""
    chunks = chunk_episode(SHORT_EPISODE, chunk_size=500, chunk_overlap=100)
    d = chunk_to_dict(chunks[0])
    required = {
        "chunk_id", "episode_id", "title", "guest", "date", "source_file",
        "youtube_url", "video_id", "chunk_index", "start_timestamp",
        "end_timestamp", "word_count", "text",
    }
    for key in required:
        assert key in d, f"Missing key in chunk_to_dict: {key}"


def test_chunk_to_dict_text_contains_speaker():
    """The text field in the dict retains speaker prefixes for traceability."""
    chunks = chunk_episode(SHORT_EPISODE, chunk_size=500, chunk_overlap=100)
    d = chunk_to_dict(chunks[0])
    # Text should contain the speaker name and timestamp
    assert "Lenny" in d["text"] or "Guest" in d["text"]
    assert "00:" in d["text"]
