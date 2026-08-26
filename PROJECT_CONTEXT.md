# PROJECT_CONTEXT.md — Lenny Growth Assistant
<!-- Persistent project memory. Update this file at the end of every coding session. -->
<!-- SOURCE OF TRUTH: docs/Assigment.md is the immutable assignment spec. Never reinterpret it here. -->

---

## 1. Project Goal

Build a **Lenny Growth Assistant** — a conversational AI that answers
product-growth, marketing, and writing questions grounded in the Lenny's
Podcast transcript knowledge base. The assistant must cite episode sources,
preserve multi-turn session context, generate rich Markdown/HTML artifacts,
and expose a polished in-app viewer for those artifacts.

Delivered as a take-home assignment for a **Forward Deployed Engineer** role.
Due date: **25/08/26 EOD**.

---

## 2. Source of Truth

> `docs/Assigment.md` is the **immutable** source of truth for the Oogway Labs
> take-home assignment. Requirements listed below are a faithful index of that
> document, NOT a restatement. Any conflict between this file and
> `docs/Assigment.md` is resolved in favour of `docs/Assigment.md`.

---

## 3. Assignment Requirements (indexed from docs/Assigment.md)

| # | Requirement | Section |
|---|-------------|---------|
| R1 | Backend API using FastAPI | §3.1 |
| R2 | Agent layer using Anthropic Claude Agent SDK or Pi Coding Agent | §3.1 |
| R3 | PostgreSQL persists sessions, conversations, timestamps, user metadata | §3.1 |
| R4 | Ollama mandatory for local/demo run | §3.2 |
| R5 | At least one cloud LLM provider (e.g. Anthropic, OpenAI) | §3.2 |
| R6 | LLM provider toggle visible in UI or config; fallback documented | §3.2 |
| R7 | Knowledge base = Lenny's Podcast/Newsletter transcripts | §3.3 |
| R8 | Answers grounded in transcripts; sources cited | §3.3, §4.1 |
| R9 | Follow-up questions preserve session context | §4.1 |
| R10 | Acknowledge when material does not support an answer | §4.1 |
| R11 | Dedicated Ship 30 for 30 skill with explicit writing principles encoded | §4.2 |
| R12 | Artifact generation: Markdown or HTML/CSS | §4.3 |
| R13 | In-app Artifact Viewer rendering beside chat | §4.3 |
| R14 | Generated HTML treated as untrusted; isolation/sanitization strategy documented | §4.3 |
| R15 | One-command startup (Docker Compose or equivalent) | §5 |
| R16 | .env.example with safe defaults; no committed secrets | §5 |
| R17 | Structured logs; observability for model/retrieval/DB/artifact failures | §5 |
| R18 | Resilience: missing keys, Ollama unavailable, timeouts, empty retrieval, DB failure | §5 |
| R19 | PRD covering: user, problem, success metric, assumptions, scope, flows, acceptance criteria, risks, plan | §6 |
| R20 | design.md: UI/UX principles, IA, interaction states, responsive, accessibility, decisions | §6 |
| R21 | architecture.md: DB schema, API, components, ingestion/retrieval, agent routing, security, deployment | §6 |
| R22 | Agent transcripts including failed attempts | §6 |
| R23 | Automated tests (API, retrieval, routing, persistence) + manual UI test plan | §6 |
| R24 | 2–3 min demo video (camera on); YouTube upload | §6 |

---

## 4. Mandatory Technology Constraints

| Concern | Technology | Notes |
|---------|-----------|-------|
| API framework | **FastAPI** | Async-first; Python 3.11+ |
| Agent SDK | **Anthropic Claude Agent SDK** | Primary choice; Pi Coding Agent is alternative per assignment |
| Local LLM | **Ollama** | Mandatory for demo run |
| Local LLM model | **qwen2.5:7b-instruct** | Validated on 16 GB RAM; configurable via `OLLAMA_MODEL` |
| Local embedding model | **nomic-embed-text** (via Ollama) | Leading candidate; configurable |
| Cloud LLM | **Groq** | Free API; satisfies assignment requirement for ≥1 cloud provider |
| Cloud LLM model | **Configuration-driven** | `GROQ_MODEL` env var; never hardcoded |
| Database | **PostgreSQL** | Supabase or Railway permitted per assignment |
| Vector store | **ChromaDB (PROPOSED)** | Leading candidate; see §7 decision table |
| Frontend | React + Vite | Leading candidate; not yet finalised (OQ6) |
| Containerisation | **Docker Compose** | Required for one-command startup |

**LLM configuration pattern (env-driven, no hardcoded model names):**
```
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b-instruct   # configurable
OLLAMA_BASE_URL=http://ollama:11434

# OR

LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=<configurable>           # never hardcoded
```

**Explicitly excluded** (do not add without explicit instruction):
Redis, Kafka, Elasticsearch, Celery, LangChain, LangGraph, authentication/JWT.

---

## 5. Knowledge Source — CONFIRMED

**Upstream repository:** https://github.com/ChatPRD/lennys-podcast-transcripts

**Transcript data path:** `episodes/` directory within that repository.

### Architecture pipeline

```
Upstream GitHub repository  (https://github.com/ChatPRD/lennys-podcast-transcripts)
        ↓
episodes/  (raw transcript files)
        ↓
Ingestion pipeline  (fetch/load — fetch strategy is OQ2)
        ↓
Parse / normalise  (structured JSON: episode_id, title, date, speaker_turns)
        ↓
Chunk  (strategy is OQ3)
        ↓
Embed  (model is OQ2-adjacent)
        ↓
Vector store  (selection is OQ1)
        ↓
RAG retrieval
        ↓
Grounded assistant response (with source citations)
```

### Important constraints

- GitHub is the **upstream data source**, NOT the runtime database.
- The application must **never query GitHub for live user requests**.
- The ingestion pipeline fetches transcripts once (and on refresh), builds the vector index, and the app queries only the vector store at runtime.
- Every indexed chunk must retain **source metadata** tracing it back to the originating episode/transcript file (episode ID, title, date, file path).
- The ingestion design must include a **documented refresh/update strategy** for when new episodes are added upstream.

---

## 6. Architecture Assumptions (working, not finalised)

- **Monorepo layout**: `backend/`, `frontend/`, `ingestion/`, `tests/`, `docs/`,
  `agent-transcripts/`, `skills/`.
- **Backend**: Single FastAPI app with routers per domain (chat, sessions, artifacts, skills).
- **LLM routing**: Thin `LLMProvider` protocol; provider and model selected at runtime from env.
  No model version locked in code.
- **Sessions**: `Session (id, created_at, metadata)` → `Message (id, session_id, role, content, sources, created_at)`.
- **Artifacts**: Stored as text blobs in Postgres with `type` (markdown|html) and `session_id` FK.
- **Artifact viewer**: Sandboxed `<iframe srcdoc>` for HTML; `react-markdown` for Markdown.
  Exact CSP policy is an open question (see §8).
- **Ship 30 for 30 skill**: Has an explicit skill/tool boundary the agent routes to.
  Writing principles are encoded in `skills/ship30/skill.md`, NOT inline in application code.
  Not a microservice; testable and maintainable as a discrete module.
  See `skills/ship30/` for the placeholder architecture.

---

## 7. Architecture Decisions

### FINAL DECISIONS
*(Confirmed; do not revisit without explicit user instruction)*

| Decision | Rationale |
|----------|-----------|
| FastAPI as backend framework | Assignment mandates it (R1) |
| PostgreSQL for persistence | Assignment mandates it (R3) |
| Ollama as local/demo LLM | Assignment mandates it (R4) |
| `qwen2.5:7b-instruct` as the initial local model | Validated on 16 GB RAM; confirmed by direct testing |
| Groq as initial cloud LLM provider | Free API; satisfies "at least one cloud provider" requirement |
| LLM provider and model name must be configuration-driven; never hardcoded | User directive |
| Ship 30 skill must have an explicit agent-routable tool/skill boundary | Assignment §4.2 + user directive |
| Ship 30 writing principles encoded in `skills/ship30/skill.md`, not inline | User directive — testable, maintainable, separate |
| Agent transcripts must include failed attempts | Assignment §6 |
| HTML artifacts rendered in sandboxed iframe (sandbox without allow-scripts) | Confirmed isolation strategy; blocks JS execution |

### CANDIDATE DECISIONS
*(Leading options; require deliberate review before finalising)*

| Decision | Status | Notes |
|----------|--------|-------|
| **Vector store: ChromaDB** | PROPOSED | See architecture.md §7 for evaluation vs pgvector, Qdrant |
| **Frontend: React + Vite** | Leading candidate | Not yet finalised (OQ6) |
| **Embedding model: nomic-embed-text** | Leading candidate | Via Ollama; local-first; configurable |

### OPEN QUESTIONS
*(Must be resolved before implementation of the affected phase begins)*

| # | Question | Blocks |
|---|----------|--------|
| OQ1 | Confirm ChromaDB (PROPOSED) or select pgvector/Qdrant | Phase 5 |
| OQ2 | Ingestion fetch strategy: git clone/pull, GitHub archive, or GitHub API? Refresh strategy? | Phase 4 |
| OQ3 | Chunk size and overlap for conversational podcast transcripts (speaker-turn vs fixed-token)? | Phase 4/5 |
| OQ6 | Frontend framework: React + Vite confirmed or alternative? | Phase 9 |
| OQ7 | Full `sandbox` attribute set and CSP header for HTML artifact iframe | Phase 8 |
| OQ8 | Ship 30 prompt template and few-shot examples (requires reading official source) | Phase 7 |

*Resolved:*
- OQ4 → **Groq** as initial cloud LLM provider (Phase 6)
- OQ5 → **`qwen2.5:7b-instruct`** (Ollama); **`nomic-embed-text`** for embeddings

---

## 8. Current Implementation Status

| Area | Status |
|------|--------|
| Repository initialization | COMPLETE |
| `docs/Assigment.md` added as source of truth | COMPLETE |
| `skills/ship30/` placeholder created | COMPLETE |
| Knowledge source confirmed (GitHub repo + `episodes/` path) | COMPLETE |
| Local model validated (`qwen2.5:7b-instruct` on 16 GB RAM) | COMPLETE |
| Cloud provider selected (Groq) | COMPLETE |
| `docs/PRD.md` — product discovery document | COMPLETE |
| `docs/architecture.md` — system architecture | COMPLETE |
| `docs/design.md` — discovery-level placeholder | COMPLETE |
| FastAPI app skeleton (`backend/app/main.py`) | COMPLETE |
| Pydantic settings / env-driven config (`app/core/config.py`) | COMPLETE |
| Structured JSON logging (`app/core/logging.py`) | COMPLETE |
| `LLMProvider` Protocol + data types (`app/llm/base.py`) | COMPLETE |
| `OllamaProvider` (`app/llm/ollama.py`) | COMPLETE |
| `GroqProvider` (`app/llm/groq.py`) | COMPLETE |
| `get_llm_provider()` factory (`app/llm/factory.py`) | COMPLETE |
| `GET /health` and `GET /health/llm` endpoints | COMPLETE |
| `POST /api/v1/chat` endpoint (session-aware) | COMPLETE |
| Structured error responses (exceptions + handlers) | COMPLETE |
| Async SQLAlchemy engine + session factory (`app/db/`) | COMPLETE |
| ORM models: `Session`, `Message` (`app/db/models.py`) | COMPLETE |
| CRUD service (`app/db/crud.py`) | COMPLETE |
| Sessions API: `POST/GET /api/v1/sessions` | COMPLETE |
| Alembic migration environment + `0001_initial.py` | COMPLETE |
| `DATABASE_URL`, `CHAT_HISTORY_LIMIT` config + `.env.example` | COMPLETE |
| 26 unit tests passing; 3 integration tests auto-skip | COMPLETE |
| `ingestion/fetch.py` — Git Tree API, SHA manifest, retry on 429 | COMPLETE |
| `ingestion/parse.py` — YAML frontmatter + speaker-turn regex, `ParsedEpisode` | COMPLETE |
| `ingestion/chunk.py` — 500-word sliding window, turn snapping, timestamps | COMPLETE |
| `ingestion/run.py` — CLI `--limit`/`--force`/`--slug`, structured logs | COMPLETE |
| `ingestion/README.md` — pipeline docs, schema, refresh strategy | COMPLETE |
| 51 new ingestion tests (12 fetch, 23 parse, 18 chunk); 77 total passing | COMPLETE |
| `pytest.ini` at repo root — `pythonpath=backend .` | COMPLETE |
| `github_token`, `chunk_size`, `chunk_overlap` added to `config.py` | COMPLETE |
| `PyYAML>=6.0` added to `requirements.txt` | COMPLETE |
| Vector store decision (ChromaDB PROPOSED) | PROPOSED — awaiting finalisation |
| Frontend framework decision (React + Vite) | CANDIDATE — awaiting finalisation |
| Ship 30 skill design (principles, prompt, boundary) | PENDING — Phase 7 |
| Artifact security (full CSP policy OQ7) | PENDING — Phase 8 |
| Phase 5+ (RAG, Vector Embedding) | PENDING |

---

## 9. Known Unknowns / Open Issues

- **Transcript fetch & refresh strategy** (OQ2): GitHub repo confirmed; fetch method (git clone/pull, archive, GitHub API) and refresh strategy TBD before Phase 4.
- **Vector store** (OQ1): ChromaDB PROPOSED; finalise before Phase 5. See architecture.md §7.
- **Chunking strategy** (OQ3): Speaker-turn vs fixed-token chunking for conversational podcast transcripts TBD before Phase 4/5.
- **Frontend framework** (OQ6): React + Vite leading; finalise before Phase 9.
- **Artifact viewer CSP** (OQ7): Sandbox attribute set and CSP headers to be fully specified before Phase 8.
- **Ship 30 prompt template** (OQ8): Official source must be read and principles formalised before Phase 7.

*Resolved unknowns:*
- OQ4 → Groq as cloud provider
- OQ5 → `qwen2.5:7b-instruct` (Ollama); `nomic-embed-text` (embedding)
- **OQ2 → Git Tree API + `raw.githubusercontent.com` + SHA-based manifest** (Phase 4 complete)
- **OQ3 → Fixed-word sliding window: 500 target words, 100-word overlap, speaker-turn snapping** (Phase 4 complete)

---

## 10. Current State

**Phase 4 (Transcript Ingestion) complete.**

Ingestion pipeline runs from repo root:
```bash
python -m ingestion.run --limit 3   # test run (3 episodes)
python -m ingestion.run             # full run (~269 episodes)
```

Verified output (3-episode run):
- `ingestion/processed/episodes/{slug}.json` — YAML frontmatter + 162 speaker turns
- `ingestion/processed/chunks/{slug}.jsonl` — 22 chunks, avg 709 words, all 13 metadata fields
- `ingestion/processed/manifest.json` — SHA index; refresh run correctly skips unchanged episodes
- `--force` flag force-refreshes a single episode regardless of SHA

Key implementation decisions:
- **Fetch**: Single Git Tree API call (not N per-episode Contents API calls); raw URL download
- **Parse**: `yaml.safe_load()` for frontmatter; regex `Speaker (HH:MM:SS):` for turns; no field raises on absence
- **Chunk**: 500-word sliding window; snaps to speaker-turn boundary ±50 words; hard-splits turns > 1000 words
- **Timestamps**: `start_timestamp`/`end_timestamp` from first/last turn in each chunk window
- **Source tracing**: Every chunk carries `episode_id`, `source_file`, `guest`, `date`, `youtube_url`, `video_id`
- **Path fix**: Root-level `pytest.ini` with `pythonpath=backend .` enables both `from app.*` and `from ingestion.*`
- 77 total unit tests pass (26 Phase 2/3 + 51 Phase 4 ingestion)

---

## 11. Current Next Step

**Phase 5 — Vector Indexing & RAG.**

Phase 4 JSONL output is ready for embedding:
```
ingestion/processed/chunks/*.jsonl
→ embeddings (nomic-embed-text via Ollama)
→ vector store (ChromaDB — OQ1 pending finalisation)
→ RAG retrieval endpoint
```

**Open decisions for Phase 5:**
1. OQ1: ChromaDB vs pgvector vs Qdrant (must resolve before Phase 5 starts)

---

## 12. Rules for Future Coding Agents

1. **Read this file first** before writing any code. It is the persistent project memory.
2. **Read `docs/Assigment.md`** — it is the immutable source of truth. Any ambiguity resolves in its favour.
3. **Update sections 7, 8, 9, 10** at the end of every coding session.
4. **Do not start Phase 2** or write any application code until product discovery and architecture review are complete.
5. **Do not add new infrastructure** (Redis, Kafka, Celery, etc.) without explicit user instruction.
6. **Do not implement authentication** until explicitly requested.
7. **Do not skip phases**; complete and verify each phase before moving to the next.
8. **LLM provider and model names must be configuration-driven** (env vars only). Never hardcode a model version in application code.
9. **All secrets go in `.env`**, never committed. Use `.env.example` as the template.
10. **Tests must be written** alongside each phase's implementation, not deferred.
11. **Structured logs** from Phase 2 onwards; never use bare `print()`.
12. **HTML artifacts are untrusted**: always sandbox iframes; document the isolation strategy before implementing.
13. **Cite sources in every RAG answer**: the `Message` model must carry a `sources` field.
14. **Keep `agent-transcripts/`** up to date with real reasoning traces, including failed attempts.
15. **Ship 30 skill must be routed to explicitly** by the agent, not inferred. Principles live in `skills/ship30/skill.md`.
16. **Vector store is NOT finalised**. Do not install or commit to ChromaDB (or any other) until OQ1 is resolved.
