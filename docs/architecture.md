# Architecture Document
## The Lenny Growth Assistant

**Version:** 0.1 — Discovery Draft  
**Status:** Phase 1b — Proposed Architecture (pending finalisation of OQ1, OQ2, OQ3, OQ6, OQ7)  
**Source of Truth:** [docs/Assigment.md](./Assigment.md)  
**Last Updated:** 2026-08-26

---

## Terminology Reference

Before reading this document, align on these terms. They are used consistently throughout.

| Term | Definition |
|------|-----------|
| **LLM** | Language model that generates or reasons over supplied inputs (Ollama, Groq) |
| **Agent** | The orchestration layer that determines which capability/tool/skill to invoke and coordinates the interaction |
| **RAG** | Retrieval-Augmented Generation — retrieves relevant transcript evidence from the knowledge base before the LLM generates a response |
| **Tool** | A callable capability available to the agent at runtime (e.g., the retrieval tool) |
| **Skill** | A reusable, specialised behaviour with explicit inputs, outputs, instructions, and validation expectations (e.g., Ship30Skill) |
| **Knowledge base** | The processed and indexed transcript corpus stored in the vector store |

---

## 1. High-Level Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React + Vite)                    │
│                                                                     │
│  ┌────────────┐   ┌──────────────────┐   ┌──────────────────────┐  │
│  │ Session    │   │   Chat Panel     │   │  Artifact Viewer     │  │
│  │ Sidebar    │   │ (messages +      │   │  Markdown renderer   │  │
│  │            │   │  source cites)   │   │  Sandboxed iframe    │  │
│  └────────────┘   └──────────────────┘   └──────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │  HTTP (REST)
┌────────────────────────────▼────────────────────────────────────────┐
│                       FastAPI Backend                               │
│                                                                     │
│  /health   /sessions   /chat   /artifacts   /retrieve (dev only)   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                       Agent Layer                            │  │
│  │  Receives request → decides capability → calls tool/skill    │  │
│  │                                                              │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │  │
│  │  │  Retrieval  │  │   Ship30     │  │  Artifact         │  │  │
│  │  │  Tool       │  │   Skill      │  │  Generator        │  │  │
│  │  └─────────────┘  └──────────────┘  └───────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────┐        ┌─────────────────────────────────┐  │
│  │   LLM Router      │        │   PostgreSQL                    │  │
│  │   (env-driven)    │        │   Sessions, Messages, Artifacts │  │
│  └─────────┬─────────┘        └─────────────────────────────────┘  │
│            │                                                        │
│  ┌─────────▼──────────────────────────────┐                        │
│  │  LLM Provider Abstraction              │                        │
│  │  OllamaProvider | GroqProvider         │                        │
│  └────────────────────────────────────────┘                        │
└────────┬──────────────────────────┬────────────────────────────────┘
         │                          │
┌────────▼────────┐       ┌─────────▼──────────┐
│  Ollama         │       │  Groq API           │
│  (local)        │       │  (cloud)            │
│  qwen2.5:7b-    │       │  (model via env)    │
│  instruct       │       │                     │
└─────────────────┘       └─────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     Vector Store (PROPOSED: ChromaDB)               │
│              Queried at runtime by the Retrieval Tool               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│              Ingestion Pipeline (offline / scheduled)               │
│  GitHub repo → fetch episodes/ → parse → chunk → embed → index     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Frontend / Backend Boundary

| Concern | Responsibility |
|---------|---------------|
| Chat message display | Frontend |
| Session list and switching | Frontend |
| Artifact rendering (Markdown, HTML iframe) | Frontend |
| Source citation display | Frontend |
| Provider/model indicator | Frontend |
| All business logic | Backend (FastAPI) |
| Session and message storage | Backend → PostgreSQL |
| Retrieval from vector store | Backend |
| LLM calls | Backend → LLM providers |
| Artifact storage | Backend → PostgreSQL |

The frontend communicates exclusively via the FastAPI REST API. It holds no business logic and makes no direct calls to LLM providers, the vector store, or PostgreSQL.

---

## 3. FastAPI Responsibilities

FastAPI is the single backend entry point. It exposes the following routes:

| Route | Method | Purpose |
|-------|--------|---------|
| `/health` | GET | System health check (DB, vector store, LLM availability) |
| `/sessions` | POST | Create a new session |
| `/sessions/{id}` | GET | Retrieve session metadata |
| `/sessions/{id}/messages` | GET | Retrieve message history for a session |
| `/chat` | POST | Submit a user message, trigger agent, return response + sources |
| `/artifacts/{id}` | GET | Retrieve a stored artifact by ID |
| `/retrieve` | GET | *(Development only)* Debug retrieval for a query |

**Request/response contracts:**
- All requests and responses are JSON
- All errors return structured JSON with `error`, `code`, and `message` fields
- All routes validate input with Pydantic models
- Request IDs are propagated in headers for log correlation

---

## 4. Agent Layer Responsibilities

The agent is the orchestration centre. It does NOT generate content directly; it decides which capability to call and coordinates the result.

**Agent responsibilities:**
1. Receive a user message and session context
2. Classify the request (grounded Q&A / Ship30 essay / artifact generation)
3. Call the **Retrieval Tool** to fetch relevant transcript evidence
4. If the request is a Ship30 essay → call the **Ship30Skill**
5. If the request is an artifact → call the **Artifact Generator**
6. Otherwise → call the LLM with retrieved context + message history
7. Return a structured response: `{answer, sources, artifact?}`
8. Instruct the LLM to acknowledge when evidence is insufficient

**Implementation:** Anthropic Claude Agent SDK (leading choice; Pi Coding Agent is the alternative per the assignment). The SDK provides the tool-calling interface the agent uses to invoke retrieval, the Ship30 skill, and the artifact generator.

---

## 5. RAG / Retrieval Flow

```
User question
     │
     ▼
Embed the question using the embedding model
     │
     ▼
Query vector store (top-k most relevant chunks)
     │
     ▼
Return chunks with source metadata {episode_id, title, date, source_file, chunk_text}
     │
     ▼
Inject chunks + source metadata into LLM system prompt / context window
     │
     ▼
LLM synthesises answer grounded in the retrieved evidence
     │
     ▼
Response returned with sources[] field populated
```

**Retrieval parameters (to be validated in Phase 5):**
- `top_k`: 5–10 chunks (to be tuned with representative test questions)
- Similarity metric: cosine similarity
- Minimum similarity threshold to be determined; below threshold → "insufficient evidence" response

**Evidence insufficiency handling:**
If retrieval returns no chunks above the similarity threshold, the agent must respond with a transparent acknowledgement rather than generating an unsupported answer.

---

## 6. Knowledge Ingestion Flow

```
Upstream: https://github.com/ChatPRD/lennys-podcast-transcripts
           └── episodes/   (confirmed transcript data path)
                │
                ▼
  [OQ2: fetch strategy — git clone/pull, archive, or GitHub API]
                │
                ▼
        ingestion/fetch.py
        (saves raw files to ingestion/raw/)
                │
                ▼
        ingestion/parse.py
        Normalise → {episode_id, title, date, source_file, speaker_turns: [...]}
                │
                ▼
        ingestion/chunk.py
        Chunk by [OQ3: strategy] with overlap
        Each chunk carries: {episode_id, title, date, source_file, chunk_index, chunk_text}
                │
                ▼
        ingestion/embed.py (or backend service)
        Embed each chunk using [nomic-embed-text via Ollama — leading candidate]
                │
                ▼
        Upsert into vector store with full source metadata
```

**Refresh / update strategy (design intent):**
- The ingestion pipeline is idempotent: re-running it processes only new or changed episode files
- An episode is considered "changed" by comparing file hash or modification timestamp against the previously indexed record
- The CLI command `python -m ingestion.run --refresh` should detect and process only new episodes
- Detailed refresh procedure documented in `ingestion/README.md`

**Important constraints (from confirmed knowledge source):**
- GitHub is the upstream data source only; it is **never queried at runtime**
- Every indexed chunk retains: `episode_id`, `title`, `date`, `source_file`
- These metadata fields are the basis for source citation in responses

---

## 7. Vector Store — Options and Decision

### Option Analysis

| Criterion | ChromaDB | Qdrant | PostgreSQL + pgvector |
|-----------|---------|--------|-----------------------|
| Setup complexity | Low — file-persisted, no separate service | Medium — requires separate Docker container | Medium — PostgreSQL extension, same service |
| Operational overhead | Minimal | Moderate | Low (reuses existing Postgres) |
| Reproducibility | High — single file directory | High — Docker container | High — same compose service |
| Retrieval quality | Good — cosine, HNSW | Good — multiple index types | Good — exact or approximate |
| Evaluator familiarity | High — widely used in AI demos | Medium | Medium |
| Production-readiness | Demo/prototype scale | Production-ready | Production-ready |
| Additional service required | No | Yes | No (extension on existing Postgres) |

### Recommendation: ChromaDB (PROPOSED — not yet final)

**Rationale:** For a demo/evaluation context, ChromaDB provides the best combination of zero additional service requirements, high evaluator recognition, and adequate retrieval quality. It stores its index as a local directory, which is committed to the Docker Compose setup without an additional container.

**Alternative worth noting:** pgvector is attractive because it eliminates the vector store as a separate concern (one fewer service in docker-compose). However, it requires more initial setup and is less immediately familiar to evaluators of AI demos.

> **Decision status: PROPOSED — awaiting explicit finalisation.**  
> To finalise: confirm ChromaDB is acceptable, or switch to pgvector or Qdrant before Phase 5 begins.

---

## 8. LLM Provider Abstraction

The application must never hardcode a model name or provider-specific API call in business logic. All provider details live in configuration.

### Provider Protocol (interface)

```python
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        system_prompt: str,
        **kwargs
    ) -> LLMResponse: ...
```

### Concrete Providers

| Provider | Class | Config Keys |
|----------|-------|------------|
| Ollama | `OllamaProvider` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |
| Groq | `GroqProvider` | `GROQ_API_KEY`, `GROQ_MODEL` |

### Router

```
LLM_PROVIDER env var
       │
       ├── "ollama" → OllamaProvider(base_url, model)
       └── "groq"   → GroqProvider(api_key, model)
```

A third provider (e.g., Anthropic, OpenAI) can be added by implementing the `LLMProvider` protocol and updating the router — no changes to business logic required.

---

## 9. Ollama Local Path

**Confirmed local model:** `qwen2.5:7b-instruct`  
**Confirmed on:** 16 GB RAM laptop  
**Validated for:** grounded Q&A, ~1,250-word essay generation, HTML/CSS artifact generation  
**Configured via:** `OLLAMA_MODEL=qwen2.5:7b-instruct` in `.env`

**Embedding model:** `nomic-embed-text` (via Ollama — leading candidate)

The Ollama service runs as a Docker Compose service alongside the backend. The `OLLAMA_BASE_URL` environment variable points the `OllamaProvider` to this service.

Resilience: if Ollama is unavailable at startup or during a request, the system logs a structured error and returns a user-facing error message (does not silently fail or hallucinate).

---

## 10. Groq Cloud Path

**Provider:** Groq (free API tier available to developer)  
**Configured via:** `LLM_PROVIDER=groq`, `GROQ_API_KEY=...`, `GROQ_MODEL=<configurable>`  

Groq satisfies the assignment requirement for "at least one cloud LLM provider." The architecture abstraction means Anthropic or OpenAI can be added later without changing business logic.

**Fallback behaviour:** If Groq is selected but `GROQ_API_KEY` is missing or the API returns an error, the system:
1. Logs the error with structured context
2. Returns a user-facing error message
3. Does NOT silently fall back to Ollama without the user's knowledge (to avoid confusing the evaluator about which model is in use)

---

## 11. Session and Conversation Persistence

All session state is persisted in PostgreSQL. The application is stateless at the API layer; session continuity comes entirely from the database.

### Session Management Flow

```
POST /sessions
  → Create Session record (id, created_at, metadata)
  → Return session_id to frontend

POST /chat {session_id, message}
  → Retrieve prior Message records for session_id (message history)
  → Run agent with history + current message
  → Persist new Message record (role=user, content, created_at)
  → Persist agent response Message record (role=assistant, content, sources, created_at)
  → If artifact generated: persist Artifact record (session_id, type, content)
  → Return response to frontend
```

### Data Retention

Sessions and messages are retained for the lifetime of the database. No automatic expiry in MVP scope.

---

## 12. PostgreSQL Responsibilities

PostgreSQL is the sole persistent store for application state. The vector store holds only the knowledge index (not user data).

### Schema (Proposed)

**sessions**
```
id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
title         TEXT
created_at    TIMESTAMPTZ DEFAULT now()
updated_at    TIMESTAMPTZ DEFAULT now()
metadata      JSONB DEFAULT '{}'
```

**messages**
```
id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id    UUID REFERENCES sessions(id) ON DELETE CASCADE
role          TEXT CHECK (role IN ('user', 'assistant', 'system'))
content       TEXT NOT NULL
sources       JSONB DEFAULT '[]'   -- [{episode_id, title, date, source_file}]
created_at    TIMESTAMPTZ DEFAULT now()
```

**artifacts**
```
id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id    UUID REFERENCES sessions(id) ON DELETE CASCADE
type          TEXT CHECK (type IN ('markdown', 'html'))
content       TEXT NOT NULL
created_at    TIMESTAMPTZ DEFAULT now()
```

All migrations managed by Alembic. SQLAlchemy async (asyncpg driver) for all database access.

---

## 13. Ship 30 for 30 Skill Boundary

The Ship30 capability is a **Skill**, not a prompt fragment. It has an explicit boundary the agent routes to. The skill is not a microservice; it is a discrete, testable Python module.

### Skill Contract

**Input:**
```python
@dataclass
class Ship30Input:
    session_id: str
    grounded_answer: str          # Prior RAG answer in session
    retrieved_chunks: list[Chunk] # Original transcript evidence
    source_metadata: list[Source] # {episode_id, title, date, source_file}
    conversation_context: list[Message]
    user_intent: str              # The original user question
```

**Output:**
```python
@dataclass
class Ship30Output:
    essay_markdown: str           # ~1,250 words
    word_count: int               # For validation
    sources: list[Source]         # Cited sources within the essay
```

**Routing:** The agent routes to Ship30Skill when the user explicitly requests it (toggle in UI, or explicit command). The skill is **never inferred from ambient context**.

**Writing principles:** Encoded in `skills/ship30/skill.md` (not inline in application code). The prompt template in `skills/ship30/implementation/prompt_template.py` loads these principles at runtime.

**Validation:** The skill implementation must validate that output is within 1,000–1,500 words. If not, the skill logs a warning and the evaluator can inspect the output.

### Directory Layout

```
skills/ship30/
├── skill.md                      ← Principles + boundary contract (this is data/config)
└── implementation/
    ├── __init__.py
    ├── ship30_skill.py            ← Skill class
    ├── prompt_template.py         ← Loads principles from skill.md; builds the prompt
    └── tests/
        └── test_ship30.py         ← Validates routing, input/output shape, word count
```

---

## 14. Artifact Generation Flow

```
User requests an artifact (in chat)
         │
         ▼
Agent determines artifact type (Markdown or HTML/CSS)
         │
         ▼
Agent generates content (using LLM + retrieved context + session context)
         │
         ▼
Backend validates artifact type
         │
         ▼
Artifact persisted to PostgreSQL (artifacts table)
         │
         ▼
Artifact ID returned in API response
         │
         ▼
Frontend fetches artifact via GET /artifacts/{id}
         │
         ▼
Artifact Viewer renders:
   Markdown → react-markdown (sanitized)
   HTML     → sandboxed <iframe srcdoc> (see §15)
```

---

## 15. Artifact Security / Isolation

HTML artifacts are generated by an LLM and must be treated as **untrusted content**.

### Strategy: Sandboxed iframe with Content-Security-Policy

**HTML rendering:**
```html
<iframe
  srcdoc="{artifact_html}"
  sandbox="allow-same-origin"
  style="width: 100%; border: none;"
/>
```

The `sandbox` attribute without `allow-scripts` prevents JavaScript execution entirely. The artifact can contain HTML structure and CSS styling but cannot run scripts, access parent window globals, submit forms, or make network requests.

**Backend CSP header on artifact endpoints:**
```
Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:;
```

This restricts artifact content even further at the transport layer.

**What is permitted:**
- HTML structure and layout
- Inline CSS styling
- Data URIs for images

**What is blocked:**
- JavaScript execution (`<script>` tags, inline event handlers)
- Network requests from within the artifact
- Access to cookies, localStorage, or parent window
- Form submission

**Markdown rendering:**
- Uses `react-markdown` with `rehype-sanitize` plugin
- Strips dangerous HTML tags and attributes before rendering
- No raw HTML passthrough

**Security test (Phase 8):**  
A test must verify that a `<script>alert('xss')</script>` payload in an HTML artifact does not execute in the Artifact Viewer.

> **Decision status: PROPOSED — CSP attribute set is OQ7, to be finalised before Phase 8.**

---

## 16. Source Citation Model

Every assistant response carries a `sources` field. This field is populated from the retrieval results and stored in the `messages` table.

**Source schema:**
```json
{
  "episode_id": "ep-123",
  "title": "Episode Title",
  "date": "2024-01-15",
  "source_file": "episodes/ep-123.txt",
  "chunk_excerpt": "Relevant excerpt from the chunk..."
}
```

**In the UI:** Source citations are rendered below the assistant's response as linked references. Each citation shows the episode title and date. A `chunk_excerpt` may optionally be shown on hover or expansion.

**In Ship30 essays:** Source citations appear as inline references within the essay text and as a reference list at the end of the document.

---

## 17. Error / Resilience Strategy

| Failure Scenario | Handling Strategy |
|-----------------|------------------|
| Missing `OLLAMA_BASE_URL` or `GROQ_API_KEY` | Startup validation; `ValueError` with clear message; service refuses to start |
| Ollama service unavailable | `OllamaProvider` returns `LLMProviderError`; agent returns user-facing error message |
| LLM request timeout | Configurable timeout (`OLLAMA_TIMEOUT_SECONDS`, `GROQ_TIMEOUT_SECONDS`); retry once; return error if retry fails |
| Empty vector store retrieval | Agent detects empty results; responds: "I couldn't find relevant evidence for this question in Lenny's transcripts." |
| PostgreSQL connection failure | SQLAlchemy raises `OperationalError`; FastAPI exception handler returns 503 with structured error |
| Invalid request body | Pydantic validation returns 422 with field-level errors |
| Artifact generation failure | Agent returns error response; no artifact persisted; user sees friendly error |
| HTML artifact XSS attempt | Sandboxed iframe prevents execution; no application-level handling needed |

All failure paths produce structured JSON log entries with `request_id`, `component`, `error_type`, and `detail` fields.

---

## 18. Observability Strategy

**Structured logging:** All log output is JSON. No bare `print()` calls.

**Log fields (standard across all components):**
```json
{
  "timestamp": "ISO8601",
  "level": "INFO|WARNING|ERROR",
  "request_id": "uuid",
  "component": "agent|retrieval|llm|db|ingestion",
  "event": "description",
  "detail": {}
}
```

**Key logged events:**

| Component | Events Logged |
|-----------|--------------|
| FastAPI | All requests (method, path, status, latency) |
| Agent | Capability routing decision, skill invoked, LLM call |
| LLM Provider | Provider selected, model, token counts, latency, errors |
| Retrieval | Query, top-k results, similarity scores |
| PostgreSQL | Connection status, query errors |
| Ingestion | Files fetched, parsed, chunked, embedded, errors |
| Artifact | Type generated, size, rendering errors |

**Health endpoint (`/health`)** returns the status of: database connection, vector store availability, and LLM provider reachability.

---

## 19. Deployment Topology

```
docker compose up
         │
         ├── postgres (PostgreSQL 16)
         │     Port: 5432 (internal)
         │     Volume: postgres_data
         │
         ├── ollama (Ollama)
         │     Port: 11434 (internal, exposed for model pull)
         │     Volume: ollama_models
         │
         ├── backend (FastAPI via uvicorn)
         │     Port: 8000 (exposed to host)
         │     Depends on: postgres, ollama
         │     Env: LLM_PROVIDER, DATABASE_URL, GROQ_API_KEY, etc.
         │
         └── frontend (React + Vite, served via Nginx)
               Port: 3000 (exposed to host)
               Depends on: backend
```

**Startup sequence:**
1. `docker compose up` brings up postgres first (health-checked)
2. Ollama starts; backend waits for Ollama health (if `LLM_PROVIDER=ollama`)
3. Backend starts; runs Alembic migrations on startup
4. Frontend starts; proxies API calls to backend

**Ingestion is run separately** (not on app startup):
```bash
docker compose run --rm backend python -m ingestion.run
```

Or as a one-time setup step documented in the README.

**First-run setup checklist (in README):**
1. `cp .env.example .env` and fill in values
2. `docker compose up -d`
3. `docker compose exec ollama ollama pull qwen2.5:7b-instruct`
4. `docker compose exec ollama ollama pull nomic-embed-text`
5. `docker compose run --rm backend python -m ingestion.run`
6. Open `http://localhost:3000`

---

## 20. Security Considerations

| Concern | Approach |
|---------|---------|
| Secrets management | `.env` file; never committed; `.env.example` has safe defaults |
| HTML artifact XSS | Sandboxed iframe; `sandbox` attribute without `allow-scripts` |
| LLM prompt injection | Retrieval context is injected in a structured system prompt format that separates evidence from user input |
| API input validation | Pydantic models enforce schema; no raw string interpolation |
| Database | Parameterised queries via SQLAlchemy ORM; no raw SQL string interpolation |
| CORS | Explicit allowlist via `CORS_ORIGINS` env var |
| No authentication in scope | Noted as non-goal; document as assumption in README |
| Docker image pinning | All images pinned to specific versions in `docker-compose.yml` |

---

## Open Architecture Questions

| # | Question | Decision Status | Blocks |
|---|----------|----------------|--------|
| OQ1 | Vector store: ChromaDB (PROPOSED) vs pgvector vs Qdrant | PROPOSED — awaiting finalisation | Phase 5 |
| OQ2 | Ingestion fetch method: git clone/pull vs archive vs GitHub API | Open | Phase 4 |
| OQ3 | Chunk size and overlap (speaker-turn vs fixed-token) | Open | Phase 4/5 |
| OQ6 | Frontend: React + Vite (leading) vs alternative | Open | Phase 9 |
| OQ7 | Full `sandbox` attribute set for HTML iframe | Open | Phase 8 |
| OQ8 | Ship30 prompt template and few-shot examples | Open | Phase 7 |

*Resolved:*
- OQ4 → **Groq** as initial cloud LLM provider
- OQ5 → **`qwen2.5:7b-instruct`** via Ollama; **`nomic-embed-text`** for embeddings
