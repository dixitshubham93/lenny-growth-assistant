"""
ingestion/parse.py — Transcript parser.

Parses a raw transcript.md file into a structured ParsedEpisode with:
  - YAML frontmatter metadata (guest, title, youtube_url, publish_date, ...)
  - Structured speaker turns: [{speaker, timestamp, text}]

Tolerates missing / malformed frontmatter — fields default to None.
Does NOT raise on malformed input; logs warnings instead.

Requires: PyYAML.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class SpeakerTurn:
    """One attributed utterance in the transcript."""
    speaker: str
    timestamp: str   # "HH:MM:SS"
    text: str        # raw text of the utterance, may be multi-paragraph


@dataclass
class ParsedEpisode:
    """
    Fully parsed episode.  All metadata fields are optional strings/ints
    so we never invent data when the frontmatter is absent.
    """
    episode_id: str                             # = slug
    source_file: str                            # "episodes/{slug}/transcript.md"
    raw_url: str                                # raw.githubusercontent.com URL
    sha: str                                    # blob SHA from Tree API

    # YAML frontmatter fields (None if absent)
    title: Optional[str] = None
    guest: Optional[str] = None
    publish_date: Optional[str] = None         # "YYYY-MM-DD"
    youtube_url: Optional[str] = None
    video_id: Optional[str] = None
    description: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration: Optional[str] = None
    view_count: Optional[int] = None
    channel: Optional[str] = None

    # Parsed body
    turns: list[SpeakerTurn] = field(default_factory=list)
    word_count: int = 0


# ── Regex for speaker-turn detection ──────────────────────────────────────────
# Matches lines like:  "Lenny (00:01:22):"  or  "Brian Chesky (00:00:00):"
# Also handles: "(00:03:38):" (no speaker name — brief continuation headers)
_SPEAKER_LINE_RE = re.compile(
    r"^(?P<speaker>[^\(\n]+?)\s*\((?P<ts>\d{2}:\d{2}:\d{2})\)\s*:\s*$",
    re.MULTILINE,
)
_NAKED_TS_LINE_RE = re.compile(
    r"^\((?P<ts>\d{2}:\d{2}:\d{2})\)\s*:\s*$",
    re.MULTILINE,
)


# ── Internal helpers ───────────────────────────────────────────────────────────
def _split_frontmatter(markdown: str) -> tuple[str, str]:
    """
    Split '---\\n...yaml...\\n---\\n...body...' into (yaml_block, body).
    Returns ('', full_markdown) if no frontmatter delimiters found.
    """
    if not markdown.startswith("---"):
        return "", markdown

    # Find the closing ---
    end = markdown.find("\n---", 3)
    if end == -1:
        return "", markdown

    yaml_block = markdown[3:end].strip()
    body = markdown[end + 4:].lstrip("\n")
    return yaml_block, body


def _parse_frontmatter(yaml_block: str) -> dict:
    """Parse YAML block; return empty dict on error."""
    if not yaml_block.strip():
        return {}
    try:
        result = yaml.safe_load(yaml_block)
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError as exc:
        logger.warning("YAML parse error in frontmatter: %s", exc)
        return {}


def _parse_turns(body: str) -> list[SpeakerTurn]:
    """
    Extract speaker turns from the transcript body.

    Handles two patterns:
      "Speaker Name (HH:MM:SS):\ntext..."           — named speaker
      "(HH:MM:SS):\ntext..."                         — unnamed continuation
    """
    if not body.strip():
        return []

    turns: list[SpeakerTurn] = []

    # Find all speaker-line positions (named turns)
    named_matches = list(_SPEAKER_LINE_RE.finditer(body))
    # Find naked timestamp positions
    naked_matches = list(_NAKED_TS_LINE_RE.finditer(body))

    if not named_matches and not naked_matches:
        # No turn markers at all — treat whole body as a single anonymous turn
        logger.debug("No speaker-turn markers found — using whole body as one turn")
        text = body.strip()
        if text:
            turns.append(SpeakerTurn(speaker="Unknown", timestamp="00:00:00", text=text))
        return turns

    # Merge named + naked markers, sort by position
    all_markers: list[tuple[int, str, str]] = []  # (start, speaker, timestamp)
    for m in named_matches:
        all_markers.append((m.start(), m.group("speaker").strip(), m.group("ts")))
    for m in naked_matches:
        # Inherit speaker from previous named turn
        all_markers.append((m.start(), "__INHERIT__", m.group("ts")))

    all_markers.sort(key=lambda x: x[0])

    prev_speaker = "Unknown"
    for i, (start, speaker, ts) in enumerate(all_markers):
        if speaker == "__INHERIT__":
            speaker = prev_speaker
        else:
            prev_speaker = speaker

        # Text = everything from end-of-this-marker-line to start of next marker
        line_end = body.find("\n", start)
        text_start = line_end + 1 if line_end != -1 else start
        text_end = all_markers[i + 1][0] if i + 1 < len(all_markers) else len(body)

        text = body[text_start:text_end].strip()
        if text:
            turns.append(SpeakerTurn(speaker=speaker, timestamp=ts, text=text))

    return turns


# ── Public API ─────────────────────────────────────────────────────────────────
_RAW_BASE = (
    "https://raw.githubusercontent.com/ChatPRD/lennys-podcast-transcripts/main"
)


def parse_transcript(slug: str, markdown: str, sha: str = "") -> ParsedEpisode:
    """
    Parse raw markdown into a ParsedEpisode.

    Args:
        slug:     Episode slug (folder name).
        markdown: Raw file contents.
        sha:      Blob SHA from Tree API (for manifest tracking).

    Returns:
        ParsedEpisode — fields are None where frontmatter data is absent.
    """
    source_file = f"episodes/{slug}/transcript.md"
    raw_url = f"{_RAW_BASE}/{source_file}"

    yaml_block, body = _split_frontmatter(markdown)
    meta = _parse_frontmatter(yaml_block)

    if not meta:
        logger.warning("No YAML frontmatter found for '%s'", slug)

    # Safe extraction — never raise on missing keys
    title = meta.get("title") or _extract_title_from_body(body, slug)
    guest = meta.get("guest")
    publish_date = str(meta["publish_date"]) if meta.get("publish_date") else None
    youtube_url = meta.get("youtube_url")
    video_id = meta.get("video_id")
    description = meta.get("description")
    duration_seconds = meta.get("duration_seconds")
    duration = meta.get("duration")
    view_count = meta.get("view_count")
    channel = meta.get("channel")

    turns = _parse_turns(body)
    all_text = " ".join(t.text for t in turns)
    word_count = len(all_text.split()) if all_text.strip() else 0

    return ParsedEpisode(
        episode_id=slug,
        source_file=source_file,
        raw_url=raw_url,
        sha=sha,
        title=title,
        guest=guest,
        publish_date=publish_date,
        youtube_url=youtube_url,
        video_id=video_id,
        description=description,
        duration_seconds=int(duration_seconds) if duration_seconds is not None else None,
        duration=str(duration) if duration else None,
        view_count=int(view_count) if view_count is not None else None,
        channel=channel,
        turns=turns,
        word_count=word_count,
    )


def _extract_title_from_body(body: str, slug: str) -> Optional[str]:
    """
    Fallback title extraction from '# Heading' if YAML frontmatter is absent.
    Returns None if no H1 found.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and len(stripped) > 2:
            return stripped[2:].strip()
    logger.debug("No H1 title found in body for '%s'", slug)
    return None


def episode_to_dict(ep: ParsedEpisode) -> dict:
    """Serialise ParsedEpisode to a JSON-safe dict (for on-disk storage)."""
    return {
        "episode_id": ep.episode_id,
        "source_file": ep.source_file,
        "raw_url": ep.raw_url,
        "sha": ep.sha,
        "title": ep.title,
        "guest": ep.guest,
        "publish_date": ep.publish_date,
        "youtube_url": ep.youtube_url,
        "video_id": ep.video_id,
        "description": ep.description,
        "duration_seconds": ep.duration_seconds,
        "duration": ep.duration,
        "view_count": ep.view_count,
        "channel": ep.channel,
        "word_count": ep.word_count,
        "turns": [
            {"speaker": t.speaker, "timestamp": t.timestamp, "text": t.text}
            for t in ep.turns
        ],
    }
