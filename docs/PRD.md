# Product Requirements Document
## The Lenny Growth Assistant

**Version:** 0.1 — Discovery Draft  
**Status:** Phase 1b — Awaiting Architecture Finalisation  
**Source of Truth:** [docs/Assigment.md](./Assigment.md)  
**Last Updated:** 2026-08-26

---

## 1. Product Overview

The Lenny Growth Assistant is a conversational AI product built for product managers and early-stage founders. It transforms the body of knowledge in Lenny's Podcast transcripts into a practical, always-available thinking partner that helps practitioners solve real product, growth, and leadership problems.

The product is **not** a podcast search engine or audio player. It is an intelligent assistant that synthesises episode insights, grounds its answers in verifiable sources, and produces reusable written artifacts — enabling practitioners to move from insight to action faster.

---

## 2. Forward Deployment Discovery Brief

### 2.1 Primary Users

**User Type A — Product Manager (PM) at a software/technology company**
- Mid-level to senior; responsible for strategy, prioritisation, and delivery
- Consumes Lenny's Podcast content regularly but lacks time to re-listen episodes to extract specific insights
- Needs to make decisions quickly and justify them with practitioner evidence

**User Type B — Early-stage Startup Founder acting as Product/Growth lead**
- Wearing multiple hats; drives product and growth directly
- Values tactical, actionable frameworks from experienced practitioners
- Needs to generate written thinking artifacts (essays, strategy docs, growth plans) as a byproduct of thinking

### 2.2 User Jobs-to-Be-Done

Users are not trying to "search a podcast." They are trying to **solve a concrete problem**:

| Job | Example trigger |
|-----|----------------|
| Understand a growth concept | "How does activation work and what levers should I pull?" |
| Diagnose a product problem | "Our growth has stalled — what approaches have worked for others?" |
| Make a prioritisation call | "How should I think about sequencing these opportunities?" |
| Adopt a framework | "What's a practical product-market fit framework I can use this week?" |
| Improve a metric | "What retention strategies have worked for B2B SaaS at our stage?" |
| Structure a team or process | "How should I structure my product team as we scale?" |
| Produce a written artifact | "Turn this conversation into an essay I can share with my team" |

### 2.3 Pain Points

| Pain | Description |
|------|-------------|
| **Evidence desert** | Practitioners have opinions but no grounded, cited backing for decisions |
| **Podcast inaccessibility** | Key insights are buried in 1–3 hour audio episodes; re-listening is impractical |
| **Generic AI answers** | General-purpose LLMs produce plausible but ungrounded growth advice; no accountability to real practitioner experience |
| **Content creation friction** | Writing a well-structured essay or strategy doc from scratch is slow; users want to leverage the conversation they just had |
| **Institutional knowledge loss** | Insights from episodes are consumed then forgotten; no way to accumulate them in a searchable, conversational form |

### 2.4 Why Generic Chat/Search Is Insufficient

| Tool | Gap |
|------|-----|
| **Generic LLM (GPT-4, Claude)** | Gives confident but unverifiable growth advice; no grounding in Lenny's specific practitioner knowledge |
| **Podcast search (Listen Notes, etc.)** | Returns episode titles, not synthesised answers; user must still re-listen |
| **Full-episode transcript search** | Returns text snippets but requires the user to interpret, synthesise, and write themselves |
| **This product** | Returns synthesised, grounded answers with explicit citations, preserves conversation context, and generates ready-to-use written artifacts |

---

## 3. Product Goals

1. **Ground every answer** in Lenny's Podcast transcript evidence with traceable source citations.
2. **Preserve conversation context** so follow-up questions build on prior answers within a session.
3. **Produce reusable artifacts** (Markdown docs, HTML pages) rendered natively in the product.
4. **Make the Ship 30 for 30 skill explicit and reliable** — a well-defined, testable capability, not a prompt hack.
5. **Be operationally transparent** — the evaluator (and any client engineer) must be able to run, understand, and extend the system.
6. **Support flexible LLM configuration** — Ollama locally, Groq/cloud remotely, without code changes.

---

## 4. Non-Goals

| Non-Goal | Rationale |
|----------|-----------|
| Audio playback or episode browsing | Not a media player; knowledge is extracted at ingestion time |
| Real-time transcript ingestion | Transcripts are ingested as a batch; refresh is periodic, not live |
| Authentication / user accounts | Out of scope for this assignment |
| Multi-tenant or enterprise security | Out of scope for this assignment |
| Support for non-Lenny content sources | Assignment specifies Lenny's Podcast specifically |
| Social sharing or collaborative sessions | Out of scope for this assignment |
| Mobile-native application | Responsive web; not a native mobile app |
| Replacing Lenny's actual newsletter/podcast | Complementary tool, not a substitute |

---

## 5. Core User Journeys

### Journey 1 — Grounded Q&A

```
User opens the assistant
  → Starts a new session
  → Types a product/growth question
    → Backend retrieves relevant transcript chunks from the knowledge base
    → Agent synthesises a grounded answer using retrieved evidence
    → Response appears in chat with inline source citations (episode title + relevant section)
  → User reads the answer
```

**Success criteria:**
- Answer references at least one specific episode/transcript source
- Source is traceable (episode title, date or segment visible to user)
- Response is coherent and relevant to the question asked
- Appears within an acceptable latency window (see §6)

---

### Journey 2 — Follow-Up Question (Session Context)

```
User reads grounded answer (Journey 1)
  → Asks a follow-up question ("What about for B2B specifically?")
    → Agent uses current session message history + new retrieval
    → Answer builds on prior context without user re-stating the original question
  → Session continues until user ends or starts a new session
```

**Success criteria:**
- Follow-up answer is contextually coherent with the prior exchange
- Session message history is stored in PostgreSQL
- Starting a new session produces independent, fresh context

---

### Journey 3 — Ship 30 for 30 Essay Generation

```
User has a grounded answer in session (Journey 1 or 2)
  → User activates the Ship 30 skill (explicit toggle or command)
    → Agent routes to the Ship30 skill
    → Skill receives: grounded answer + retrieved transcript evidence + source metadata + session context
    → Skill applies Ship 30 writing principles (from skills/ship30/skill.md)
    → Generates ~1,250-word structured Markdown essay
  → Essay appears as an Artifact in the Artifact Viewer panel
  → User can copy, download, or continue the conversation
```

**Success criteria:**
- Essay is approximately 1,250 words
- Essay has a strong hook, clear narrative, skimmable formatting (headings, bullets, bold)
- Essay contains a specific actionable takeaway
- Every claim is grounded in transcript evidence
- Skill was explicitly routed to (not inferred from ambient context)

---

### Journey 4 — Artifact Generation

```
User wants a reusable document based on the conversation
  → User requests an artifact ("Create a product strategy doc for this" / "Generate a landing page")
    → Agent determines artifact type (Markdown or HTML/CSS)
    → Generates the artifact content
    → Artifact is stored in PostgreSQL, linked to the session
    → Artifact Viewer panel renders the result beside the chat
      → Markdown: rendered with sanitized markdown renderer
      → HTML: rendered inside a sandboxed iframe (see Security section)
  → User views the rendered artifact
```

**Success criteria:**
- Artifact renders correctly in the viewer panel
- HTML artifacts do not execute injected scripts
- Markdown artifacts display formatted output (not raw text)
- Artifact is associated with the originating session

---

## 6. Success Metrics

### Product Metrics

| Metric | Definition | Target (MVP) |
|--------|-----------|-------------|
| **Grounded answer rate** | % of responses that cite at least one specific episode source | ≥ 90% |
| **Session continuation rate** | % of sessions with ≥ 2 user turns (follow-up engagement) | ≥ 50% |
| **Artifact generation success rate** | % of artifact requests that produce a rendered artifact without error | ≥ 95% |
| **Ship 30 essay length compliance** | % of Ship 30 outputs within 1,000–1,500 words | ≥ 80% |

### Operational Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Local (Ollama) response latency** | End-to-end time for a grounded chat response | < 30 seconds p90 |
| **Cloud (Groq) response latency** | End-to-end time for a grounded chat response | < 15 seconds p90 |
| **Ingestion completeness** | % of `episodes/` files successfully parsed and indexed | 100% |
| **System startup time** | Time from `docker compose up` to healthy API on a fresh clone | < 5 minutes |
| **Uptime during demo** | API availability during evaluation session | 100% |

---

## 7. Assumptions

| # | Assumption | Impact if Wrong |
|---|-----------|-----------------|
| A1 | Transcripts in `ChatPRD/lennys-podcast-transcripts` `episodes/` are machine-readable text files | Ingestion pipeline design changes; may need OCR or format conversion |
| A2 | `qwen2.5:7b-instruct` via Ollama on a 16 GB RAM machine produces acceptable answer quality | May need to downgrade model or use cloud-only path for demo |
| A3 | `nomic-embed-text` via Ollama produces sufficient embedding quality for semantic retrieval | May need to switch to a cloud embedding API |
| A4 | RAG with top-k retrieval (not full-context loading) is sufficient for answering most questions | May need longer context or multi-hop retrieval strategies |
| A5 | The evaluator will run the demo locally on a compatible machine | Docker Compose documentation must be thorough; local model requirements must be clearly stated |
| A6 | Session context within a single conversation (not across sessions) is sufficient for the assignment scope | Cross-session memory is a non-goal for this submission |
| A7 | One cloud provider (Groq) is sufficient to satisfy "at least one cloud LLM" requirement | Assignment says "at least one" — Groq qualifies |
| A8 | The `episodes/` directory contains structured transcript data that can be chunked without heavy pre-processing | Confirmed as assumption; to be verified in Phase 4 |
| A9 | Ship 30 for 30 principles from the official source can be encoded in a prompt template | Alternative: the skill needs fine-tuning or few-shot examples beyond a template |

---

## 8. Scope

### In Scope (MVP)

- Grounded conversational Q&A over Lenny's Podcast transcripts
- Session context preservation within a conversation (multi-turn)
- Source citation in every grounded response
- Ship 30 for 30 essay generation skill (explicitly routed, principle-encoded)
- Markdown artifact generation and in-app viewer
- HTML/CSS artifact generation with sandboxed rendering
- Session and message persistence in PostgreSQL
- Ollama local path (`qwen2.5:7b-instruct`) as mandatory demo path
- Groq as initial cloud LLM provider (via abstraction)
- LLM provider toggle (env-driven)
- Docker Compose one-command startup
- Structured logging and resilience handling
- PRD, architecture.md, design.md, README, tests, agent transcripts

### Explicitly Out of Scope

| Feature | Why Excluded |
|---------|-------------|
| Authentication / login | Not required by assignment; adds complexity without evaluation benefit |
| Cross-session memory / user history | Adds complexity; within-session context is sufficient |
| Real-time transcript ingestion | Batch ingestion with documented refresh is sufficient |
| Audio playback or episode media | Assignment is transcript-based |
| Multi-user or team collaboration | Single-user demo scope |
| Mobile-native app | Responsive web is sufficient |
| Multiple simultaneous cloud providers with runtime switching | Provider is env-configured; runtime switching is not required |
| Prompt fine-tuning or RLHF | Out of scope for this submission |

---

## 9. Acceptance Criteria (Mapped to Assignment Requirements)

| Req | Acceptance Criterion | Verifiable How |
|-----|---------------------|---------------|
| R1 | FastAPI backend serves all API routes | `curl /health` returns 200; routes documented in architecture.md |
| R2 | Agent layer built with Anthropic Claude Agent SDK (or Pi Coding Agent) | Agent class uses SDK; traceable in code |
| R3 | PostgreSQL stores sessions, messages, timestamps, metadata | DB schema in architecture.md; verified by integration test |
| R4 | Demo runs end-to-end using Ollama locally | `docker compose up`; set `LLM_PROVIDER=ollama` in `.env`; full flow works |
| R5 | At least one cloud provider integrated and working | Set `LLM_PROVIDER=groq`; full flow works |
| R6 | Provider visible in UI or config; fallback documented | Provider shown in UI or API response; README documents fallback |
| R7 | Knowledge base built from Lenny's Podcast transcripts | `episodes/` directory from confirmed GitHub source is ingested |
| R8 | Every response cites the source episode | `sources` field populated in every message; rendered in UI |
| R9 | Follow-up questions maintain context | Second turn references prior answer contextually; verified by integration test |
| R10 | Assistant acknowledges insufficient evidence | Tested with an out-of-scope question; response is honest, not hallucinated |
| R11 | Ship 30 skill is explicitly routable, principle-encoded, and testable | Skill class exists in `skills/ship30/`; unit test validates routing and output shape |
| R12 | Assistant generates Markdown and HTML/CSS artifacts | Both types generated; verified by test |
| R13 | Artifact Viewer renders beside chat | Split-panel UI visible in demo video |
| R14 | HTML treated as untrusted; isolation documented | Sandboxed iframe used; CSP documented in design.md; security test passes |
| R15 | One-command startup | `docker compose up` starts full stack; evaluator can verify |
| R16 | `.env.example` with safe defaults; no secrets committed | Verified in repository |
| R17 | Structured logs for model/retrieval/DB/artifact failures | JSON log output confirmed during demo |
| R18 | Resilience for missing keys, unavailable Ollama, timeouts, empty retrieval, DB failure | Tested in Phase 11 |
| R19 | PRD complete | This document |
| R20 | design.md complete | `docs/design.md` |
| R21 | architecture.md complete | `docs/architecture.md` |
| R22 | Agent transcripts including failed attempts | `agent-transcripts/` directory populated |
| R23 | Automated tests + manual UI test plan | `tests/` directory; manual plan in README |
| R24 | 2–3 min demo video with camera; YouTube | Linked in README |

---

## 10. Risks and Trade-Offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **Hallucination** — LLM answers confidently without transcript support | Medium | High | RAG with explicit retrieval; require `sources` field; prompt instructs model to acknowledge insufficient evidence |
| **Local model quality** — `qwen2.5:7b-instruct` produces weak Ship 30 essays | Medium | Medium | Tested and validated locally; Groq path available as fallback for evaluator |
| **Retrieval quality** — Chunks don't surface the most relevant evidence | Medium | High | Evaluate chunk size/overlap strategy; test with representative questions; expose `/retrieve` debug endpoint |
| **Latency** — Local Ollama responses are too slow for evaluator | Medium | Medium | Set clear expectations in README; Groq path provides faster alternative |
| **Unsafe artifact rendering** — XSS via HTML artifact | Low | High | Sandboxed iframe with documented CSP; security test in Phase 8 |
| **Data leakage** — Secrets committed to repository | Low | High | `.env.example` pattern; `.gitignore` covers `.env`; GitHub secret scanning |
| **Ingestion failure** — Transcript format is inconsistent | Medium | Medium | Defensive parser with error logging; skip-and-log strategy for malformed files |
| **Docker Compose reproducibility** — Evaluator environment differences | Medium | Medium | Pin all image versions; document prerequisites explicitly; test on clean environment |
| **Ship 30 essay not ~1,250 words** — Model produces shorter or longer output | Medium | Low | Explicit word-count instruction in prompt; post-generation length validation |
| **Evaluator cannot run Ollama** | Low | High | Document system requirements clearly; Groq path as alternative |

### Key Trade-Offs

| Decision | Trade-Off |
|----------|-----------|
| RAG over full-context loading | Lower latency, lower cost, but may miss cross-episode synthesis; sufficient for MVP |
| Ollama local model over always-cloud | Privacy, zero cost, but quality and latency vary by hardware |
| ChromaDB (proposed) over pgvector | Simpler setup vs fewer moving parts; pgvector would reduce service count at cost of setup complexity |
| Sandboxed iframe over full DOM sanitization | Safer isolation; evaluator can understand the boundary clearly; slight UX trade-off (iframe constraints) |
| Single cloud provider (Groq) for MVP | Sufficient to satisfy assignment; abstraction enables future addition |

---

## 11. MVP Prioritisation

| Priority | Capability | Reason |
|----------|-----------|--------|
| P0 | Grounded Q&A (RAG + source citations) | Core product value; blocks everything else |
| P0 | Session persistence (PostgreSQL) | Assignment mandates it; required for context preservation |
| P0 | Ollama local path | Assignment mandates it for the demo |
| P1 | Follow-up context preservation | Core conversational value |
| P1 | Ship 30 for 30 skill | Explicit assignment requirement; differentiator |
| P1 | Artifact generation (Markdown + HTML) | Explicit assignment requirement |
| P1 | Artifact Viewer (in-app rendering) | Explicit assignment requirement |
| P2 | Groq cloud path | Required by assignment but secondary to local demo |
| P2 | Structured logs and resilience | Required for operational readiness |
| P2 | Docker Compose startup | Required for evaluator reproducibility |
| P3 | Frontend polish (loading states, accessibility) | Important for evaluation but not blocking |
| P3 | Automated tests | Required but can be layered in |

---

## 12. Implementation Plan

*(High-level phase sequence. Detailed tasks tracked in TASKS.md)*

| Phase | Deliverable | Depends On |
|-------|------------|-----------|
| 1 (done) | Repository scaffold, assignment source of truth | — |
| 1b (this) | PRD, architecture.md, design.md placeholder, decisions | Phase 1 |
| 2 | FastAPI skeleton, health endpoint, CORS, structured logging | Phase 1b approval |
| 3 | PostgreSQL models (Session, Message, Artifact), migrations | Phase 2 |
| 4 | Ingestion pipeline (fetch, parse, chunk, metadata) | Phase 3 |
| 5 | Embedding, vector store, retrieval service | Phase 4 |
| 6 | Agent layer, LLM router, Ollama + Groq providers, `/chat` endpoint | Phase 5 |
| 7 | Ship 30 skill implementation (principles, template, routing, tests) | Phase 6 |
| 8 | Artifact generation, Artifact Viewer, sandboxed iframe, CSP | Phase 6 |
| 9 | Frontend: split-panel UI, session sidebar, citation display, provider toggle | Phase 7 + 8 |
| 10 | Automated tests, manual UI test plan | Phase 9 |
| 11 | Observability, resilience, error handling | Phase 9 |
| 12 | Docker Compose, one-command startup, reproducibility verification | Phase 11 |
| 13 | Final documentation (README, PRD, architecture.md, design.md) | Phase 12 |
| 14 | Demo video, submission | Phase 13 |

---

## 13. Open Questions

| # | Question | Blocks |
|---|----------|--------|
| OQ1 | Vector store: ChromaDB (proposed) vs Qdrant vs pgvector — see architecture.md for analysis | Phase 5 |
| OQ2 | Ingestion fetch/refresh strategy: git clone/pull vs GitHub archive/API vs sparse checkout | Phase 4 |
| OQ3 | Chunk size and overlap for conversational podcast transcripts (speaker-turn vs fixed-size) | Phase 4/5 |
| OQ6 | Frontend: React + Vite SPA vs simpler approach | Phase 9 |
| OQ7 | Full CSP attribute set for sandboxed HTML iframe | Phase 8 |
| OQ8 | Ship 30 prompt template and few-shot examples (requires reading official source) | Phase 7 |

*OQ4 (cloud provider) → Resolved: Groq.*  
*OQ5 (Ollama model) → Resolved: `qwen2.5:7b-instruct`.*
