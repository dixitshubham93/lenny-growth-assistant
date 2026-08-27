# Lenny Growth Assistant

A conversational AI growth assistant grounded in **Lenny's Podcast** transcripts. 
This is a full-stack, containerized application with an integrated multi-modal agent, 
Retrieval-Augmented Generation (RAG) using `pgvector`, and an interactive UI featuring an artifact viewer.

## Ì∫Ä Quick Start Guide (Clone & Run)

Follow these exact steps to run the application end-to-end from a completely fresh clone.

### 1. Prerequisites
- **Git**
- **Docker & Docker Compose**
- **Python 3.10+** (for running ingestion scripts on your host machine)
- **Ollama** installed on your host machine (https://ollama.com)
  > *Note: Ollama intentionally runs on your host machine rather than inside Docker to natively leverage local GPU/Silicon acceleration without complex container passthrough configurations.*

### 2. Clone the Repository
```bash
git clone https://github.com/your-username/lenny-growth-assistant.git
cd lenny-growth-assistant
```

### 3. Configure the Environment
Copy the example environment file:
```bash
cp .env.example .env
```
Ensure the `.env` settings are correctly configured for local execution. The default `.env.example` provides safe placeholder values that work perfectly for this demo out-of-the-box.

### 4. Pull Local LLM Models (Ollama)
Pull the required LLM and Embedding models on your host machine:
```bash
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
```

### 5. Start Ollama
Ensure the Ollama API is running on your host machine:
```bash
ollama serve
```
*(If Ollama is already running via a system tray app, you can skip this).*

### 6. Start the Application
Boot the full stack via Docker Compose:
```bash
docker compose up -d --build
```
This starts:
1. `postgres` (port 5433 on host)
2. `backend` (port 8000 on host)
3. `frontend` (port 3000 on host)

### 7. Initialization & Migrations
The database migrations (`alembic upgrade head`) are **automatically run** by the backend container upon startup. You do not need to run migrations manually. Visit **http://localhost:3000** to see it running!

---

## ÌøóÔ∏è Architecture Flowchart

```mermaid
graph TD
    User([User]) -->|Chat / Requests| UI(Frontend UI<br/>Vanilla JS/HTML)
    UI -->|JSON HTTP| API(FastAPI Backend)
    
    API --> Agent[Agent Runner<br/>Tool Calling Loop]
    Agent -->|1. Needs Information?| RAG[Retrieval Tool]
    Agent -->|2. Needs Essay?| Ship30[Ship 30 Skill]
    Agent -->|3. Needs HTML View?| Artifact[Artifact Creator]
    
    RAG -->|Queries Vector| DB[(PostgreSQL pgvector)]
    Ship30 -->|Queries Vector| DB
    
    Agent -->|Generates JSON| Ollama((Local Ollama<br/>qwen2.5 / llama3))
    
    classDef main fill:#2b3440,stroke:#fff,stroke-width:2px,color:#fff;
    classDef agent fill:#6c63ff,stroke:#fff,stroke-width:2px,color:#fff;
    classDef db fill:#0064a5,stroke:#fff,stroke-width:2px,color:#fff;
    
    class API,UI,Ollama main;
    class Agent,RAG,Ship30,Artifact agent;
    class DB db;
```

---

## ‚öôÔ∏è Architecture Highlights
- **Backend:** FastAPI + SQLAlchemy + Alembic
- **Database:** PostgreSQL 16 + `pgvector`
- **Agent Layer:** Anthropic Claude Agent SDK for production, custom tool loop for local Ollama
- **Frontend:** Pure HTML/CSS/JS (no build step, high portability)
- **Deployment:** Docker Compose (backend + db + frontend) with host-based Ollama

---

## Ì≥ä Data Pipeline

The repository contains raw transcripts that must be chunked and indexed into the vector database.

### Phase 4: Transcript Ingestion
This script parses the raw Markdown transcripts and chunks them intelligently.
Run this on your host machine:
```bash
pip install -r backend/requirements.txt
python -m ingestion.run --limit 3
```
*(Note: `--limit 3` processes only 3 episodes for the demo. Omit it to process all episodes).*
**Output:** Generates chunked `.jsonl` files in `ingestion/processed/chunks/`.

### Phase 5: Vector Indexing
This script embeds the downloaded chunks using `nomic-embed-text` and stores them in PostgreSQL.

Because you are running this from your **Host**, the script must connect to PostgreSQL via port `5433` (the port exposed by Docker Compose). Make sure you have exported the correct connection string:
```bash
export DATABASE_URL="postgresql+asyncpg://lenny:changeme@localhost:5433/lenny_db"
export OLLAMA_BASE_URL="http://localhost:11434"
export EMBEDDING_MODEL="nomic-embed-text"

python -m ingestion.index --limit 3
```

### Verify Data
Verify the embeddings exist inside PostgreSQL:
```bash
docker compose exec postgres psql -U lenny -d lenny_db -c "SELECT COUNT(*) FROM transcript_chunks;"
```

---

## Ì∑™ Testing the APIs Directly

Before using the UI, test if retrieval works natively:
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query":"product market fit", "top_k":3}' \
  http://localhost:8000/api/v1/retrieve
```

---

## ‚úÖ Test Suite

To run the automated tests against Phases 2-6:
```bash
pip install pytest httpx pytest-asyncio
python -m pytest tests/ -q
```

---

## ‚ö†Ô∏è Troubleshooting

- **PostgreSQL Authentication Failed:** If running commands on the host fail with password errors, explicitly pass `DATABASE_URL=postgresql+asyncpg://lenny:changeme@localhost:5433/lenny_db`.
- **Ollama Unavailable / Timed Out:** Ensure `ollama serve` is running. If embedding indexing fails with an HTTP timeout, it means Ollama is taking too long to load the embedding model to RAM. Keep Ollama running and simply run the script again.
- **Frontend Blank Page:** Ensure `docker compose` is fully spun up, and port 3000 is not blocked.

## Ìª°Ô∏è Artifact Security
LLM-generated artifacts are strictly sandboxed.
Generated HTML is isolated within an `<iframe>` utilizing the HTML5 `sandbox="allow-same-origin"` attribute. All JavaScript execution, external form submission, and parent DOM access are explicitly blocked by the browser. Pure Markdown is parsed via `marked.js` in a safe text node boundary.

---

## Ì≥∏ Screenshots & Workflow

### 1. Grounded RAG 
The assistant retrieves context directly from Lenny's transcripts to answer questions accurately.
![RAG Q&A](assets/first_question.png)

### 2. Follow-Up Questions & Source Citations
Follow up questions maintain conversation history. Exact citations retrieved from the Vector Database are displayed beneath the chat as interactive chips.
![Source Citations](assets/follow_up.png)

### 3. Artifact Generation (Ship 30 for 30 Skill)
When generating long-form content, the agent automatically deploys the **Artifact Viewer**, rendering HTML safely in a sandboxed, tabbed interface (Preview / Source Code).
![Artifact generation](assets/artifact_view.png)

