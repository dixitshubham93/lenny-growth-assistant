"""
ingestion/chunk.py — Sliding-window episode chunker.

Strategy:
  - Slide over ParsedEpisode.turns using word count as the unit.
  - Target: CHUNK_SIZE words (default 500), overlap: CHUNK_OVERLAP words (default 100).
  - Snap to speaker-turn boundaries within ±SNAP_TOLERANCE words of target.
  - Hard-split single turns that exceed 2× chunk_size.
  - Every chunk carries full source metadata + start_timestamp / end_timestamp.

No FastAPI imports. No heavy tokeniser — uses plain whitespace word count.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ingestion.parse import ParsedEpisode, SpeakerTurn

logger = logging.getLogger(__name__)

SNAP_TOLERANCE = 50   # words either side of chunk boundary to snap to turn edge


# ── Data class ─────────────────────────────────────────────────────────────────
@dataclass
class Chunk:
    chunk_id: str               # "{episode_id}-{chunk_index:03d}"
    episode_id: str
    title: Optional[str]
    guest: Optional[str]
    date: Optional[str]         # publish_date from frontmatter
    source_file: str
    youtube_url: Optional[str]
    video_id: Optional[str]
    chunk_index: int
    start_timestamp: Optional[str]  # "HH:MM:SS" from first turn in window
    end_timestamp: Optional[str]    # "HH:MM:SS" from last turn in window
    word_count: int
    text: str                   # retains "Speaker (ts):\ntext" prefixes


# ── Internal helpers ───────────────────────────────────────────────────────────
def _word_count(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def _turn_text(turn: SpeakerTurn) -> str:
    """Text representation that retains speaker + timestamp for traceability."""
    return f"{turn.speaker} ({turn.timestamp}):\n{turn.text}"


def _hard_split_turn(
    turn: SpeakerTurn,
    chunk_size: int,
) -> list[SpeakerTurn]:
    """
    Split an over-long single turn into smaller pseudo-turns.
    Preserves speaker and timestamp; only the first sub-turn has the real ts.
    """
    words = turn.text.split()
    parts: list[SpeakerTurn] = []
    idx = 0
    part_num = 0
    while idx < len(words):
        chunk_words = words[idx: idx + chunk_size]
        parts.append(
            SpeakerTurn(
                speaker=turn.speaker,
                timestamp=turn.timestamp if part_num == 0 else "continued",
                text=" ".join(chunk_words),
            )
        )
        idx += chunk_size
        part_num += 1
    return parts


def _flatten_turns(turns: list[SpeakerTurn], chunk_size: int) -> list[SpeakerTurn]:
    """
    Flatten turns list: hard-split any turn whose word count > 2 × chunk_size.
    """
    flat: list[SpeakerTurn] = []
    max_turn_words = chunk_size * 2
    for turn in turns:
        wc = _word_count(turn.text)
        if wc > max_turn_words:
            logger.debug(
                "Hard-splitting long turn (%d words) by '%s'", wc, turn.speaker
            )
            flat.extend(_hard_split_turn(turn, chunk_size))
        else:
            flat.append(turn)
    return flat


# ── Public API ─────────────────────────────────────────────────────────────────
def chunk_episode(
    parsed: ParsedEpisode,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> list[Chunk]:
    """
    Chunk a ParsedEpisode into overlapping Chunk objects.

    Algorithm:
      1. Flatten turns (hard-split over-long turns).
      2. Maintain a sliding window of turns; emit a chunk when accumulated
         words ≥ chunk_size (with ±SNAP_TOLERANCE snap to turn boundaries).
      3. After emitting, rewind by chunk_overlap words worth of turns.
    """
    if not parsed.turns:
        logger.warning("Episode '%s' has no turns — skipping chunking", parsed.episode_id)
        return []

    flat_turns = _flatten_turns(parsed.turns, chunk_size)

    chunks: list[Chunk] = []
    chunk_index = 0
    window_start = 0   # index into flat_turns

    while window_start < len(flat_turns):
        window: list[SpeakerTurn] = []
        accumulated = 0
        i = window_start

        # Accumulate turns until we reach chunk_size ± SNAP_TOLERANCE
        while i < len(flat_turns):
            turn_words = _word_count(flat_turns[i].text)
            window.append(flat_turns[i])
            accumulated += turn_words
            i += 1

            # Snap boundary: stop at or after chunk_size, at a turn edge
            if accumulated >= chunk_size - SNAP_TOLERANCE:
                if accumulated >= chunk_size or i == len(flat_turns):
                    break   # at/past target, snap here

        if not window:
            break

        text = "\n\n".join(_turn_text(t) for t in window)
        wc = _word_count(text)

        chunk = Chunk(
            chunk_id=f"{parsed.episode_id}-{chunk_index:03d}",
            episode_id=parsed.episode_id,
            title=parsed.title,
            guest=parsed.guest,
            date=parsed.publish_date,
            source_file=parsed.source_file,
            youtube_url=parsed.youtube_url,
            video_id=parsed.video_id,
            chunk_index=chunk_index,
            start_timestamp=window[0].timestamp,
            end_timestamp=window[-1].timestamp,
            word_count=wc,
            text=text,
        )
        chunks.append(chunk)
        chunk_index += 1

        # Determine how many turns to rewind for overlap
        if i >= len(flat_turns):
            break  # consumed all turns

        # Calculate overlap by walking back enough turns to cover chunk_overlap words
        overlap_words = 0
        rewind = i
        while rewind > window_start + 1 and overlap_words < chunk_overlap:
            rewind -= 1
            overlap_words += _word_count(flat_turns[rewind].text)

        window_start = rewind

    return chunks


def chunk_to_dict(chunk: Chunk) -> dict:
    """Serialise a Chunk to a JSON-safe dict (for JSONL output)."""
    return {
        "chunk_id": chunk.chunk_id,
        "episode_id": chunk.episode_id,
        "title": chunk.title,
        "guest": chunk.guest,
        "date": chunk.date,
        "source_file": chunk.source_file,
        "youtube_url": chunk.youtube_url,
        "video_id": chunk.video_id,
        "chunk_index": chunk.chunk_index,
        "start_timestamp": chunk.start_timestamp,
        "end_timestamp": chunk.end_timestamp,
        "word_count": chunk.word_count,
        "text": chunk.text,
    }
