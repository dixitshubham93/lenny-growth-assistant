# TASKS.md — Lenny Growth Assistant Progress Tracker
<!-- Update this file as tasks are completed. Mark items [x] when done, [/] when in-progress, [ ] when pending. -->
<!-- SOURCE OF TRUTH: docs/Assigment.md — resolve any conflict in its favour. -->

---

## Phase 1 — Foundation ✅ COMPLETE

- [x] Create repository root directory `lenny-growth-assistant/`
- [x] Create subdirectories: `backend/`, `frontend/`, `ingestion/`, `tests/`, `docs/`, `agent-transcripts/`, `skills/`
- [x] Create `.gitignore`
- [x] Create `.env.example` with all anticipated environment variables
- [x] Create `README.md` (project overview, planned stack, directory layout)
- [x] Create `PROJECT_CONTEXT.md` (persistent project memory)
- [x] Create `TASKS.md` (this file)
- [x] Add `docs/Assigment.md` as immutable source of truth
- [x] Create `skills/ship30/skill.md` placeholder with architecture intent
- [x] Create `skills/ship30/implementation/` placeholder directory

---

## Phase 1b — Product Discovery & Architecture Review ✅ COMPLETE

> All required discovery documents produced. Remaining open decisions (OQ1, OQ2, OQ3, OQ6, OQ7, OQ8) are explicitly tracked.
> Phase 2 is unblocked once the user reviews and approves PRD + architecture.md.

### PRD (`docs/PRD.md`)

- [x] Identify primary user and user role
- [x] Define user job-to-be-done
- [x] Define pain/problem statement
- [x] Define at least one measurable success metric
- [x] Record key assumptions
- [x] Define scope: what is included
- [x] Define scope: what is explicitly excluded and why
- [x] Map primary user flows (grounded Q&A, follow-up, Ship 30 generation, artifact view)
- [x] Write acceptance criteria for each core flow (mapped to R1–R24)
- [x] Identify risks (hallucination, latency, cost, local-model quality, data leakage, unsafe artifact rendering)
- [x] Document technical and product trade-offs
- [x] Write MVP prioritisation
- [x] Write implementation plan

### Architecture Review (`docs/architecture.md`)

- [x] Analyse and propose vector store: ChromaDB PROPOSED (OQ1 pending finalisation)
- [x] Document ingestion pipeline and data flow
- [x] Document transcript fetch and refresh strategy design (OQ2 fetch method pending finalisation)
- [x] Document chunking design intent (OQ3 pending finalisation)
- [x] Confirm cloud LLM provider: Groq (OQ4 resolved)
- [x] Confirm Ollama model: qwen2.5:7b-instruct (OQ5 resolved)
- [x] Confirm frontend framework candidate: React + Vite (OQ6 pending finalisation)
- [x] Document artifact isolation strategy: sandboxed iframe without allow-scripts (OQ7 CSP detail pending)
- [x] Document Ship30 skill boundary and input/output contract
- [x] Document DB schema (Session, Message, Artifact tables)
- [x] Document API endpoint contracts
- [x] Document agent routing and capability model
- [x] Document LLM provider abstraction (OllamaProvider + GroqProvider)
- [x] Document resilience strategy
- [x] Document observability strategy
- [x] Document deployment topology (Docker Compose)

### Design (`docs/design.md`)

- [x] Define confirmed UI/UX principles
- [x] Define information architecture outline
- [x] Describe key interaction states (outline)
- [x] Document artifact viewer security constraints (confirmed)
- [x] Note responsive and accessibility intent
- [ ] Detailed UI/UX design — deferred to Phase 9

### Remaining open decisions (not blocking Phase 2)

- [ ] OQ1: Confirm ChromaDB or switch to pgvector/Qdrant (blocks Phase 5)
- [ ] OQ2: Confirm ingestion fetch method — git clone/pull vs archive vs API (blocks Phase 4)
- [ ] OQ3: Confirm chunking strategy — speaker-turn vs fixed-token (blocks Phase 4/5)
- [ ] OQ6: Confirm frontend framework — React + Vite (blocks Phase 9)
- [ ] OQ7: Finalise full sandbox + CSP policy for HTML artifact iframe (blocks Phase 8)
- [ ] OQ8: Research Ship 30 official source; formalise writing principles (blocks Phase 7)

---

## Phase 2 — Backend / API
> **Unblocked once Phase 1b documents are approved by user.**

- [ ] Initialise Python project in `backend/` (`pyproject.toml` or `requirements.txt`)
- [ ] Create FastAPI application entry point (`backend/app/main.py`)
- [ ] Add `/health` endpoint returning JSON status
- [ ] Define project folder structure:
  - [ ] `backend/app/routers/`
  - [ ] `backend/app/models/`
  - [ ] `backend/app/services/`
  - [ ] `backend/app/core/` (config, logging, exceptions)
- [ ] Implement CORS middleware
- [ ] Implement structured JSON logging (`structlog` or `python-json-logger`)
- [ ] Add `LLMProvider` abstract protocol / base class (no concrete implementation yet)
- [ ] Add Pydantic settings class reading from `.env` (provider and model from env only)
- [ ] Verify app starts with `uvicorn`

---

## Phase 3 — PostgreSQL Persistence
> **Blocked until Phase 2 is complete.**

- [ ] Add SQLAlchemy (async) + asyncpg to dependencies
- [ ] Define database engine and session factory (`backend/app/core/database.py`)
- [ ] Create ORM models:
  - [ ] `Session` (id, title, created_at, updated_at, metadata JSONB)
  - [ ] `Message` (id, session_id FK, role, content, sources JSONB, created_at)
  - [ ] `Artifact` (id, session_id FK, type, content, created_at)
- [ ] Create Alembic migration environment
- [ ] Write initial migration (create all tables)
- [ ] Add CRUD service layer (`sessions`, `messages`, `artifacts`)
- [ ] Add API routers: `POST /sessions`, `GET /sessions/{id}`, `GET /sessions/{id}/messages`
- [ ] Write unit tests for CRUD operations
- [ ] Verify with a running PostgreSQL instance

---

## Phase 4 — Transcript Ingestion
> **Blocked until ingestion fetch/refresh strategy (OQ2) is resolved in Phase 1b.**
> Confirmed upstream source: https://github.com/ChatPRD/lennys-podcast-transcripts — `episodes/` directory.

- [ ] Resolve OQ2: Choose ingestion fetch method (git clone/pull, GitHub archive, GitHub API) and document refresh strategy
- [ ] Write `ingestion/fetch.py` — reproducibly fetch `episodes/` from the upstream GitHub repo using the chosen method
- [ ] Write `ingestion/parse.py` — normalise raw content to structured JSON `{episode_id, title, date, file_path, speaker_turns: [...]}`
- [ ] Write `ingestion/chunk.py` — split transcripts with configurable size/overlap (strategy from OQ3); every chunk retains full source metadata (episode_id, title, date, source_file)
- [ ] Store chunked output as JSONL in `ingestion/processed/`
- [ ] Document refresh/update strategy: how new upstream episodes are detected and re-ingested
- [ ] Write `ingestion/README.md` documenting the full pipeline and refresh workflow
- [ ] Add CLI entrypoint (`python -m ingestion.run`)
- [ ] Write tests for parser and chunker (including source metadata retention)

---

## Phase 5 — Vector Retrieval / RAG
> **Blocked until vector store decision (OQ1) is finalised. ChromaDB is currently PROPOSED.**
> **Embedding model candidate: nomic-embed-text via Ollama.**

- [ ] Finalise vector store choice (OQ1): ChromaDB PROPOSED — confirm or select pgvector/Qdrant
- [ ] Add chosen vector store to dependencies
- [ ] Choose and configure embedding model (OQ2-adjacent)
- [ ] Write `backend/app/services/embedding.py` — embed chunks and upsert
- [ ] Write `backend/app/services/retrieval.py` — semantic search returning top-k chunks with source metadata
- [ ] Expose `/retrieve` debug endpoint (development only)
- [ ] Write integration test: query returns results with source citations
- [ ] Document embedding model choice and chunk strategy in `docs/architecture.md`

---

## Phase 6 — Agent Layer
> **Blocked until Phase 5 complete. Cloud LLM: Groq (confirmed). Local LLM: qwen2.5:7b-instruct (confirmed).**

- [ ] Add Anthropic SDK (or chosen SDK) to dependencies
- [ ] Implement `AnthropicProvider` (or chosen provider) as concrete `LLMProvider`
- [ ] Implement `OllamaProvider` as concrete `LLMProvider`
- [ ] Write `LLMRouter` — selects provider and model from env vars only
- [ ] Implement agent orchestration (`backend/app/services/agent.py`):
  - [ ] Build system prompt with retrieved context and source citations
  - [ ] Maintain message history per session
  - [ ] Return structured response with `answer`, `sources`, `artifact` fields
  - [ ] Route to Ship 30 skill when requested
- [ ] Add `POST /chat` endpoint wiring session, retrieval, agent, and persistence
- [ ] Make provider toggle visible in UI or API response
- [ ] Document fallback behaviour for unavailable provider
- [ ] Record first real agent transcript (including failures) to `agent-transcripts/`
- [ ] Write integration tests for chat flow (mocked LLM)

---

## Phase 7 — Ship 30 for 30 Skill
> **Blocked until Ship 30 prompt template (OQ8) is researched and formalised. Official source must be read first.**

- [ ] Research Ship 30 for 30 writing framework; read linked source
- [ ] Formalise writing principles in `skills/ship30/skill.md`
- [ ] Design prompt template with explicit principles (not an unstructured one-off prompt)
- [ ] Implement `Ship30Skill` class in `skills/ship30/implementation/ship30_skill.py`
- [ ] Implement prompt template in `skills/ship30/implementation/prompt_template.py`
- [ ] Wire skill activation to agent routing (`skill: "ship30" | null` param)
- [ ] Verify output: ~1,250 words, hook, narrative, skimmable formatting, grounded claims
- [ ] Add unit tests for skill routing and output shape
- [ ] Save sample Ship 30 agent transcripts to `agent-transcripts/`

---

## Phase 8 — Artifact Generation and Secure Viewer
> **Blocked until full CSP/sandbox policy (OQ7) is finalised. Sandboxed iframe strategy is confirmed; exact attribute set is OQ7.**

- [ ] Define artifact generation contract in agent response schema
- [ ] Persist generated artifacts to `Artifact` table
- [ ] Add `GET /artifacts/{id}` endpoint
- [ ] Implement Artifact Viewer component:
  - [ ] Markdown: render with `react-markdown` + sanitized plugins
  - [ ] HTML: render inside sandboxed `<iframe srcdoc>` with documented CSP
- [ ] Set `Content-Security-Policy` response header on artifact endpoints
- [ ] Write security test: injected `<script>` in HTML artifact must not execute
- [ ] Document isolation strategy in `docs/design.md` (what is permitted, blocked, and why)

---

## Phase 9 — Frontend Polish
> **Blocked until frontend framework (OQ6) is confirmed. React + Vite is leading candidate.**

- [ ] Scaffold frontend project (framework TBD from OQ6)
- [ ] Implement split-panel layout: chat panel + artifact viewer panel
- [ ] Implement session sidebar (list, create, switch sessions)
- [ ] Implement chat input with follow-up context preserved
- [ ] Implement source citation display (episode title, relevant segment)
- [ ] Implement Ship 30 skill toggle
- [ ] Implement Artifact Viewer (Markdown + HTML modes)
- [ ] Display active LLM provider / model in UI
- [ ] Add loading states and error handling
- [ ] Ensure responsive layout (desktop primary)
- [ ] Accessibility pass (keyboard nav, ARIA labels)

---

## Phase 10 — Testing

- [ ] Unit tests: LLM router, skill injection, chunker, parser
- [ ] Integration tests: chat flow, session CRUD, artifact creation
- [ ] End-to-end test: full chat round-trip (Ollama mock)
- [ ] Security test: HTML artifact sandboxing (no script execution)
- [ ] Achieve >80% coverage on backend services
- [ ] Write manual UI test plan
- [ ] Add `pytest` config and CI-friendly test runner script

---

## Phase 11 — Observability / Resilience

- [ ] Implement structured logging across all services
- [ ] Add request ID propagation (middleware)
- [ ] Implement LLM provider retry logic with exponential back-off
- [ ] Add timeout handling for Ollama and Anthropic calls
- [ ] Handle missing API keys gracefully (startup validation + clear error message)
- [ ] Handle Ollama unavailable gracefully (fallback to cloud or user-facing error)
- [ ] Handle empty retrieval results gracefully (acknowledge to user)
- [ ] Handle DB connection failure gracefully
- [ ] Document resilience patterns in `docs/architecture.md`

---

## Phase 12 — Docker / Deployment

- [ ] Write `backend/Dockerfile`
- [ ] Write `frontend/Dockerfile`
- [ ] Write `docker-compose.yml` (postgres, ollama, backend, frontend)
- [ ] Add `docker-compose.override.yml.example` for local dev overrides
- [ ] Verify full stack starts with `docker compose up`
- [ ] Document startup procedure in `README.md`
- [ ] Add environment variable validation on startup
- [ ] Verify a fresh clone + documented steps reproduces the running system

---

## Phase 13 — Documentation

- [ ] Finalise `docs/PRD.md` (all fields from Phase 1b complete)
- [ ] Finalise `docs/architecture.md` (DB schema, API, components, ingestion/retrieval, agent routing, security, deployment)
- [ ] Finalise `docs/design.md` (UI/UX, IA, interaction states, responsive, accessibility, artifact security)
- [ ] Expand `README.md`: architecture overview, prerequisites, installation, env vars, model setup, run commands, tests, troubleshooting
- [ ] Add `ingestion/README.md` (how to run ingestion pipeline)
- [ ] Ensure `PROJECT_CONTEXT.md` reflects final state

---

## Phase 14 — Demo / Submission

- [ ] Record 2–3 min demo video (camera on): problem, product, local Ollama demo, one trade-off explained
- [ ] Upload video to YouTube
- [ ] Collect 3+ representative agent transcripts in `agent-transcripts/` (including failed attempts, secrets removed)
- [ ] Final review against all R1–R24 requirements in `docs/Assigment.md`
- [ ] Verify fresh clone + documented steps reproduce the system
- [ ] Tag release `v1.0.0`
- [ ] Submit via https://forms.gle/LgotDHNVxW1mbzNE7

---

*Last updated: 2026-08-26 — Phase 1b (product discovery + architecture) COMPLETE. Remaining open decisions: OQ1, OQ2, OQ3, OQ6, OQ7, OQ8. Phase 2 unblocked once user approves documents.*
