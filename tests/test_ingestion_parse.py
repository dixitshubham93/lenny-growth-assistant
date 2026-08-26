"""
tests/test_ingestion_parse.py — Unit tests for ingestion/parse.py.

No network access; all tests use inline fixture strings.
"""
from __future__ import annotations

import pytest

from ingestion.parse import ParsedEpisode, SpeakerTurn, parse_transcript, episode_to_dict


# ── Fixtures ───────────────────────────────────────────────────────────────────
FULL_MARKDOWN = """\
---
guest: "Brian Chesky"
title: "Brian Chesky's new playbook"
publish_date: "2023-11-01"
youtube_url: "https://youtube.com/watch?v=abc"
video_id: "abc"
description: "CEO of Airbnb"
duration_seconds: 4200
duration: "1:10:00"
view_count: 500000
channel: "Lenny's Podcast"
---

Brian Chesky (00:00:00):
Way too many founders apologize for how they want to run the company.

Lenny (00:01:01):
Today my guest is Brian Chesky, CEO of Airbnb.

Brian Chesky (00:02:15):
We drove the product hard.
"""

NO_FRONTMATTER_MARKDOWN = """\
# My Episode Without Frontmatter

## Transcript

Lenny (00:00:00):
Opening statement.

Guest (00:01:00):
Response text.
"""

EMPTY_MARKDOWN = ""

MALFORMED_FRONTMATTER = """\
---
guest: [broken yaml: ]
---

Speaker (00:00:00):
Some text.
"""


# ── YAML frontmatter extraction ────────────────────────────────────────────────
def test_parse_extracts_title():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.title == "Brian Chesky's new playbook"


def test_parse_extracts_guest():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.guest == "Brian Chesky"


def test_parse_extracts_publish_date():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.publish_date == "2023-11-01"


def test_parse_extracts_youtube_url():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.youtube_url == "https://youtube.com/watch?v=abc"


def test_parse_extracts_video_id():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.video_id == "abc"


def test_parse_extracts_duration_seconds():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.duration_seconds == 4200


def test_parse_extracts_description():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert "Airbnb" in ep.description


def test_parse_source_file_correct():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.source_file == "episodes/brian-chesky/transcript.md"


def test_parse_episode_id_equals_slug():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.episode_id == "brian-chesky"


def test_parse_sha_preserved():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="mysha")
    assert ep.sha == "mysha"


# ── Speaker-turn extraction ────────────────────────────────────────────────────
def test_parse_extracts_correct_turn_count():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert len(ep.turns) == 3


def test_parse_first_turn_speaker():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.turns[0].speaker == "Brian Chesky"


def test_parse_first_turn_timestamp():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.turns[0].timestamp == "00:00:00"


def test_parse_first_turn_text_content():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert "founders apologize" in ep.turns[0].text


def test_parse_second_turn_speaker_and_timestamp():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.turns[1].speaker == "Lenny"
    assert ep.turns[1].timestamp == "00:01:01"


def test_parse_word_count_nonzero():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    assert ep.word_count > 0


# ── Graceful degradation ───────────────────────────────────────────────────────
def test_parse_no_frontmatter_does_not_raise():
    """Missing YAML frontmatter returns None fields but never raises."""
    ep = parse_transcript("no-frontmatter", NO_FRONTMATTER_MARKDOWN, sha="sha2")
    assert ep.guest is None
    assert ep.youtube_url is None
    assert ep.publish_date is None


def test_parse_no_frontmatter_extracts_title_from_h1():
    """When no YAML, title falls back to # H1 line."""
    ep = parse_transcript("no-frontmatter", NO_FRONTMATTER_MARKDOWN, sha="sha2")
    assert ep.title == "My Episode Without Frontmatter"


def test_parse_no_frontmatter_still_extracts_turns():
    """Speaker turns are still extracted even without YAML frontmatter."""
    ep = parse_transcript("no-frontmatter", NO_FRONTMATTER_MARKDOWN, sha="sha2")
    assert len(ep.turns) >= 1


def test_parse_empty_markdown_does_not_raise():
    """Empty string input returns a ParsedEpisode with zero turns."""
    ep = parse_transcript("empty", EMPTY_MARKDOWN, sha="sha3")
    assert ep.turns == []
    assert ep.word_count == 0


def test_parse_malformed_frontmatter_does_not_raise():
    """Malformed YAML returns None for frontmatter fields without raising."""
    ep = parse_transcript("malformed", MALFORMED_FRONTMATTER, sha="sha4")
    # Should not raise; turns may or may not be extracted depending on body
    assert isinstance(ep, ParsedEpisode)


# ── Serialisation ──────────────────────────────────────────────────────────────
def test_episode_to_dict_has_required_keys():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    d = episode_to_dict(ep)
    for key in ("episode_id", "title", "guest", "publish_date", "source_file",
                 "youtube_url", "video_id", "turns", "word_count", "sha"):
        assert key in d, f"Missing key: {key}"


def test_episode_to_dict_turns_serialised():
    ep = parse_transcript("brian-chesky", FULL_MARKDOWN, sha="sha1")
    d = episode_to_dict(ep)
    assert len(d["turns"]) == 3
    assert d["turns"][0]["speaker"] == "Brian Chesky"
    assert d["turns"][0]["timestamp"] == "00:00:00"
