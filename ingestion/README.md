# Lenny Podcast — Transcript Ingestion Pipeline

Standalone Python module (`ingestion/`) that fetches, parses, and chunks transcript files from the upstream GitHub repository into structured JSONL ready for vector indexing.

**No FastAPI imports. Runs independently from the backend server.**

---

## Upstream Source

- Repository: [ChatPRD/lennys-podcast-transcripts](https://github.com/ChatPRD/lennys-podcast-transcripts)
- Pattern: `episodes/{episode-slug}/transcript.md`
- ~269 episodes (as of August 2026)

Each transcript file contains:
```markdown
---
guest: "Brian Chesky"
title: "Brian Chesky's new playbook"
publish_date: "2023-11-01"
youtube_url: "https://youtube.com/watch?v=..."
video_id: "..."
description: "..."
duration_seconds: 4200
duration: "1:10:00"
view_count: 500000
channel: "Lenny's Podcast"
---

Brian Chesky (00:00:00):
Way too many founders apologize...

Lenny (00:01:01):
Today my guest is Brian Chesky...
```

---

## Fetch Strategy

Uses a single **Git Tree API** call to discover all transcript paths and their blob SHAs:

```
GET /repos/ChatPRD/lennys-podcast-transcripts/git/trees/main?recursive=1
```

This returns all 269+ paths + SHAs in **one request**. Individual transcripts are then downloaded from `raw.githubusercontent.com` — only for episodes whose SHA differs from the local manifest.

**Incremental refresh**: subsequent runs skip unchanged episodes using the SHA-based manifest.

**Rate limits**:
- Without token: 60 requests/hr (unauthenticated)
- With `GITHUB_TOKEN`: 5,000 requests/hr

---

## Parsing Strategy

1. Split raw markdown on `---` delimiter → extract YAML frontmatter block
2. `yaml.safe_load()` frontmatter → structured metadata dict
3. Fallback gracefully when fields are absent (`.get()` — never raise)
4. Parse transcript body using speaker-turn regex:
   ```
   Speaker Name (HH:MM:SS):
   text...
   ```
5. Each turn stored as `{speaker, timestamp, text}` — timestamps and speaker identity preserved

---

## Chunking Strategy

**Fixed-word sliding window: 500 target words, 100-word overlap.**

- Snaps to speaker-turn boundaries within ±50 words of the target
- Falls back to hard split for turns exceeding 2× chunk_size
- Each chunk retains `start_timestamp` (first turn in window) and `end_timestamp` (last turn)
- Chunk text preserves speaker prefix + timestamp for downstream source citation

Configurable via env vars:
```
CHUNK_SIZE=500
CHUNK_OVERLAP=100
```

---

## Metadata Schema

### Episode JSON (`processed/episodes/{slug}.json`)
| Field | Source |
|-------|--------|
| `episode_id` | folder slug |
| `title` | YAML frontmatter |
| `guest` | YAML frontmatter |
| `publish_date` | YAML frontmatter |
| `youtube_url` | YAML frontmatter |
| `video_id` | YAML frontmatter |
| `description` | YAML frontmatter |
| `duration_seconds` | YAML frontmatter |
| `source_file` | `episodes/{slug}/transcript.md` |
| `raw_url` | constructed raw.githubusercontent.com URL |
| `sha` | Git Tree API blob SHA |
| `turns` | `[{speaker, timestamp, text}]` |
| `word_count` | computed |

### Chunk JSONL (`processed/chunks/{slug}.jsonl`, one object per line)
```json
{
  "chunk_id": "ada-chen-rekhi-000",
  "episode_id": "ada-chen-rekhi",
  "title": "Feeling stuck? ...",
  "guest": "Ada Chen Rekhi",
  "date": "2023-11-01",
  "source_file": "episodes/ada-chen-rekhi/transcript.md",
  "youtube_url": "https://youtube.com/watch?v=...",
  "video_id": "...",
  "chunk_index": 0,
  "start_timestamp": "00:00:00",
  "end_timestamp": "00:08:32",
  "word_count": 520,
  "text": "Ada Chen Rekhi (00:00:00):\nIt's a terrible..."
}
```

### Manifest (`processed/manifest.json`)
```json
{
  "updated_at": "2026-08-26T11:26:18Z",
  "episodes": {
    "ada-chen-rekhi": {
      "sha": "abc123...",
      "chunk_count": 22,
      "processed_at": "2026-08-26T11:26:18Z"
    }
  }
}
```

---

## Refresh Behavior

| Scenario | Behavior |
|----------|----------|
| First run | Fetches all episodes (SHA mismatch — nothing in manifest) |
| Upstream unchanged | Skips all (SHA match) |
| New episode added | Fetches new episode only |
| Episode updated upstream | Fetches + re-processes that episode only |
| `--force` flag | Re-downloads and re-processes regardless of SHA |

---

## CLI

Run from repo root:

```bash
# Fetch + process first 3 episodes (testing)
python -m ingestion.run --limit 3

# Process single episode
python -m ingestion.run --slug brian-chesky

# Force re-process even if SHA unchanged
python -m ingestion.run --slug brian-chesky --force

# Full run (all ~269 episodes)
python -m ingestion.run
```

Environment variables (optional — read from `.env`):
```
GITHUB_TOKEN=ghp_...       # raises rate limit to 5000/hr
CHUNK_SIZE=500             # target words per chunk
CHUNK_OVERLAP=100          # overlap words between chunks
LOG_LEVEL=INFO             # DEBUG for verbose output
```

---

## Output Location

```
ingestion/
  processed/            ← gitignored (generated runtime data)
    episodes/           ← {slug}.json per episode
    chunks/             ← {slug}.jsonl per episode
    manifest.json       ← SHA-based incremental refresh index
```

The `processed/` directory is **excluded from git** — regenerate with the CLI.

---

## Tests

```bash
# Run ingestion unit tests only (no network access)
python -m pytest tests/test_ingestion_fetch.py tests/test_ingestion_parse.py tests/test_ingestion_chunk.py -v

# Full suite including Phase 2/3 regression
python -m pytest tests/ --ignore=tests/test_integration_postgres.py --ignore=tests/test_integration_ollama.py -q
```
