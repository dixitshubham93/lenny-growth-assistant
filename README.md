# Lenny Growth Assistant

> **Status: Phase 3 Complete — PostgreSQL Persistence Layer Live**

This repository is being built incrementally as a take-home assignment for a
Forward Deployed Engineer role. The codebase is scaffolded but application
features are not yet implemented.

## What this will be

A conversational AI growth assistant grounded in **Lenny's Podcast** transcripts.
Users will be able to ask growth, product, and marketing questions and receive
answers that cite specific episode sources. The assistant will also include a
dedicated **Ship 30 for 30** writing-skills mode and will produce rich
Markdown / HTML artifacts rendered in a secure in-app viewer.

## Planned Stack

| Layer | Technology | Status |
|-------|-----------|--------|
| Backend API | FastAPI (Python 3.11+) | Confirmed |
| Agent SDK | Anthropic Claude Agent SDK | Confirmed (primary) |
| Local LLM | Ollama — `qwen2.5:7b-instruct` | Validated on 16 GB RAM |
| Cloud LLM | Groq (provider abstraction; swappable) | Confirmed |
| Embedding model | `nomic-embed-text` via Ollama | Leading candidate |
| Database | PostgreSQL (sessions, messages, artifacts) | Confirmed |
| Vector store | ChromaDB (PROPOSED — see architecture.md) | Pending final decision |
| Frontend | React + Vite (leading candidate) | Pending final decision |
| Containerisation | Docker Compose | Confirmed |

## Repository layout

```
lenny-growth-assistant/
├── backend/            # FastAPI application (Phase 2+)
├── frontend/           # React + Vite UI (Phase 9+)
├── ingestion/          # Transcript fetch, parse, chunk, embed pipeline (Phase 4+)
├── tests/              # Unit & integration tests (Phase 10+)
├── docs/               # PRD, architecture.md, design.md, Assignment source of truth
├── skills/             # Explicit agent skills
│   └── ship30/         # Ship 30 for 30 writing skill (Phase 7+)
├── agent-transcripts/  # Agent reasoning traces & evaluation logs (committed after review)
├── .env.example        # Environment variable template — SAFE TO COMMIT
├── .gitignore
├── PROJECT_CONTEXT.md  # Persistent project memory
├── TASKS.md            # Phase-by-phase progress tracker
└── README.md           # This file
```

## Getting started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Tested on 3.10.9 |
| Ollama | Latest | Required for local/demo run |
| PostgreSQL | 13+ | Required for Phase 3+ persistence |

**Ollama model setup (one-time):**
```bash
ollama pull qwen2.5:7b-instruct   # LLM — required for demo
ollama pull nomic-embed-text       # Embedding model — required for Phase 5+
```

**PostgreSQL setup (one-time):**
```bash
createdb lenny_db   # Or via psql: CREATE DATABASE lenny_db;
```

### Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Configure environment

```bash
cp .env.example .env
# Edit .env:
#   LLM_PROVIDER=ollama          (default — no key needed)
#   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lenny_db
```

### Run database migrations (Phase 3+)

```bash
cd backend
alembic upgrade head
```

### Start the API server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

API is now available at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

### Select LLM provider

Set `LLM_PROVIDER` in your `.env` file:

| Value | Provider | Requires |
|-------|----------|---------|
| `ollama` (default) | Local Ollama | Ollama running + model pulled |
| `groq` | Groq cloud API | `GROQ_API_KEY` + `GROQ_MODEL` set |

The app will refuse to start with a clear error message if Groq is selected
but `GROQ_API_KEY` or `GROQ_MODEL` is missing.

### Example API requests

**Health check:**
```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0","environment":"development"}
```

**LLM provider status:**
```bash
curl http://localhost:8000/health/llm
# {"status":"ok","provider":"ollama","model":"qwen2.5:7b-instruct","reachable":true,...}
```

**Create a session:**
```bash
curl -X POST http://localhost:8000/api/v1/sessions
# {"session_id":"<uuid>","created_at":"..."}
```

**Chat (session-aware):**
```bash
SESSION=$(curl -s -X POST http://localhost:8000/api/v1/sessions | python -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What is product-market fit?\", \"session_id\": \"$SESSION\"}"
```

**Get session messages:**
```bash
curl http://localhost:8000/api/v1/sessions/$SESSION/messages
```

### Running tests

**All unit tests (no Ollama or PostgreSQL required):**
```bash
cd backend
python -m pytest ../tests/ --ignore=../tests/test_integration_postgres.py -v
# Expected: 26 passed, 3 skipped
```

**Integration tests (requires Ollama running + DATABASE_URL set):**
```bash
cd backend
python -m pytest ../tests/test_integration_ollama.py ../tests/test_integration_postgres.py -v -s
```


## Progress

See [TASKS.md](./TASKS.md) for the full phase breakdown and current status.

## Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) | Persistent project memory / checkpoint | Active |
| [TASKS.md](./TASKS.md) | Phase-by-phase progress tracker | Active |
| [docs/PRD.md](./docs/PRD.md) | Product Requirements Document | Complete (Phase 1b) |
| [docs/architecture.md](./docs/architecture.md) | System architecture | Complete (Phase 1b) |
| [docs/design.md](./docs/design.md) | UI/UX design decisions | Discovery placeholder (Phase 1b) |
| [docs/Assigment.md](./docs/Assigment.md) | Assignment source of truth (immutable) | Reference only |

---

## Repository Hygiene

This project follows strict hygiene rules to protect secrets and maintain a
clean, evaluator-friendly commit history.

### What is ignored (not committed)

| Category | Examples |
|----------|---------|
| Secrets & env files | `.env`, `.env.*` (all variants) |
| Python runtime | `__pycache__/`, `*.pyc`, `.venv/`, `dist/`, `build/` |
| Test artefacts | `.pytest_cache/`, `.coverage`, `htmlcov/` |
| Frontend build output | `node_modules/`, `frontend/dist/`, `frontend/build/` |
| Local database files | `*.sqlite`, `*.db` |
| Vector store data | `chroma_db/`, `qdrant_storage/`, `*.faiss`, `*.pkl` |
| Ingestion raw/processed data | `ingestion/raw/`, `ingestion/processed/` |
| Logs | `logs/`, `*.log` |
| Docker local overrides | `docker-compose.override.yml` |
| IDE / OS metadata | `.vscode/`, `.idea/`, `.DS_Store`, `Thumbs.db` |

See [.gitignore](./.gitignore) for the full rule set with category comments.

### What MUST be committed

| What | Why |
|------|-----|
| All source code | Core deliverable |
| `tests/` | Required by assignment |
| `docs/` (PRD, architecture, design) | Required deliverables |
| `skills/` | Ship30 skill boundary and principles |
| `ingestion/` scripts | Required; data files are excluded |
| Database migrations (`alembic/`) | Required for reproducibility |
| `.env.example` | Safe template; required by assignment |
| `docker-compose.yml` | Required for one-command startup |
| `agent-transcripts/` | Required deliverable (see sanitization below) |
| `PROJECT_CONTEXT.md` / `TASKS.md` | Project memory and tracking |

### How secrets are handled

1. **Never commit `.env`** — it is ignored by `.gitignore`.
2. **`.env.example` is the only committed env file.** It contains only safe placeholder values and documentation. No real credentials, API keys, passwords, or tokens.
3. All secret values are passed at runtime via environment variables loaded from `.env`.
4. Before every commit, verify with `git status` and `git diff --cached` that no `.env` file or secret file is staged.
5. If a secret is accidentally committed, treat it as compromised immediately: rotate the credential, then remove it from history using `git filter-repo` or BFG Repo Cleaner.

### How agent transcripts are sanitized before committing

Agent transcripts in `agent-transcripts/` record the agent's reasoning, tool calls, and outputs. They are a required assignment deliverable but may contain sensitive information.

**Before committing any transcript file:**

1. Open the transcript file and search for:
   - API keys, tokens, passwords, credentials
   - Database connection strings with passwords
   - Personal data or private file paths
   - Any value that looks like a secret (starts with `sk-`, `gsk_`, `Bearer`, etc.)
2. Replace any found value with a placeholder:
   ```
   [REDACTED — API key removed before commit]
   ```
3. Verify no sensitive path or username leaks remain.
4. Only then stage and commit the file.

Transcripts should include real agent reasoning, tool calls, failed attempts, and corrections — just without secrets.

### Commit hygiene checklist

Run this check before every meaningful commit:

```bash
# 1. Review what will be staged
git status
git diff --cached

# 2. Confirm no .env or secret files are staged
git diff --cached --name-only | grep -E '\.env$|\.key$|\.pem$|secret'

# 3. Confirm no vector store or generated data is staged
git diff --cached --name-only | grep -E 'chroma_db|qdrant_storage|ingestion/raw|ingestion/processed'

# 4. Confirm required docs are present
ls docs/PRD.md docs/architecture.md docs/design.md
```

---

*Last updated: 2026-08-26 — Phase 2 (FastAPI + LLM provider foundation) complete. 17 unit tests passing. Ollama integration verified.*
