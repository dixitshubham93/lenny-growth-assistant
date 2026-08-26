"""
services/agent.py — Phase 6 Agent Layer

Two execution paths sharing the same application capabilities:

  Anthropic path → claude-agent-sdk (ClaudeSDKClient, ClaudeAgentOptions, @tool)
  Ollama path    → Ollama native tool-calling via /api/chat with JSON tool schemas

Both paths expose the same tools:
  - transcript_search       : semantic search over pgvector
  - write_ship_30_essay     : generates a Ship 30 for 30 Markdown artifact

The Ship30Skill module encodes explicit writing principles (see skills/ship30/implementation/).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.errors.exceptions import EmbeddingError
from app.llm.base import LLMProvider, Message
from app.services.retrieval import retrieve_chunks

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class SourceCitationData:
    """Internal representation of a retrieved transcript citation."""
    chunk_id: str
    episode_id: str
    title: str | None
    guest: str | None
    start_timestamp: str | None
    end_timestamp: str | None
    source_file: str
    youtube_url: str | None
    cosine_distance: float


@dataclass
class AgentResult:
    """Structured output of a single AgentRunner.run() call."""
    answer: str
    sources: list[SourceCitationData] = field(default_factory=list)
    artifact: str | None = None
    skill_used: str | None = None   # "grounded_qa" | "ship30" | None
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


# ── Shared application capabilities (framework-agnostic) ────────────────────

async def _execute_transcript_search(
    query: str,
    db: AsyncSession,
    settings: Settings,
    top_k_override: int | None = None,
) -> tuple[list[dict], list[SourceCitationData]]:
    """
    Framework-independent transcript search capability.
    Used by BOTH the Claude Agent SDK path and the Ollama native path.
    Returns (chunk_dicts_for_llm, source_citations_for_response).
    """
    try:
        chunks = await retrieve_chunks(
            query=query,
            db=db,
            settings=settings,
            top_k=top_k_override if top_k_override is not None else settings.rag_top_k,
        )
    except EmbeddingError:
        logger.warning("EmbeddingError during transcript search; returning empty results")
        return [], []

    results: list[dict] = []
    citations: list[SourceCitationData] = []
    for c in chunks:
        results.append({
            "chunk_id": c.chunk_id,
            "episode_id": c.episode_id,
            "title": c.title,
            "text": c.text,
        })
        citations.append(SourceCitationData(
            chunk_id=c.chunk_id,
            episode_id=c.episode_id,
            title=c.title,
            guest=c.guest,
            start_timestamp=c.start_timestamp,
            end_timestamp=c.end_timestamp,
            source_file=c.source_file,
            youtube_url=c.youtube_url,
            cosine_distance=c.cosine_distance,
        ))
    return results, citations


async def _execute_write_ship_30_essay(
    topic: str,
    db: AsyncSession,
    settings: Settings,
    provider: LLMProvider,
) -> tuple[str, list[SourceCitationData]]:
    """
    Framework-independent Ship 30 for 30 essay capability.
    1. Searches transcripts for grounding material.
    2. Builds the prompt using Ship30Skill (explicit encoded principles).
    3. Calls the configured LLM provider.
    Returns (essay_markdown, source_citations).
    """
    from skills.ship30.implementation.ship30_skill import Ship30Skill
    skill = Ship30Skill()

    chunks_data, citations = await _execute_transcript_search(topic, db, settings, top_k_override=2)
    
    def _truncate(text: str) -> str:
        words = text.split()
        if len(words) > 300:
            return " ".join(words[:300]) + "..."
        return text

    context = "\n\n---\n\n".join(_truncate(c["text"]) for c in chunks_data) if chunks_data else ""
    prompt = skill.build_prompt(topic=topic, context=context)

    response = await provider.complete(
        messages=[Message(role="user", content=prompt)],
        system_prompt="",
        max_tokens=3500,
    )
    return response.content, citations


# ── Ollama tool schemas (JSON, standard OpenAI-compatible format) ─────────────

_OLLAMA_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "transcript_search",
            "description": "Search Lenny's podcast transcripts for product and growth insights.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_ship_30_essay",
            "description": (
                "Write a ~1,250-word Ship 30 for 30 style Markdown essay on a product or growth topic, "
                "grounded in Lenny's Podcast transcripts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The essay topic."},
                },
                "required": ["topic"],
            },
        },
    },
]

_GROUNDED_SYSTEM_PROMPT = (
    "You are the Lenny Growth Assistant — an expert on product management and growth strategy, "
    "grounded exclusively in Lenny's Podcast transcripts.\n\n"
    "Rules:\n"
    "1. ALWAYS call transcript_search before answering product/growth questions.\n"
    "2. ONLY cite facts that were returned by transcript_search. Do not answer from general world knowledge.\n"
    "3. If the transcript_search returns no results, or if the results are irrelevant/insufficient, you MUST explicitly state that there is insufficient transcript evidence to answer.\n"
    "4. If the user wants a Ship 30 for 30 essay, call write_ship_30_essay.\n"
    "5. Never fabricate any episode, guest, timestamp, quote, or source details."
)


# ── AgentRunner ───────────────────────────────────────────────────────────────

class AgentRunner:
    """
    Orchestrates the agent reasoning loop.

    Selection:
      settings.agent_provider == "anthropic"  → Claude Agent SDK path
      settings.agent_provider == "internal"   → Ollama native tool-calling path
    """

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        provider: LLMProvider,
    ) -> None:
        self._db = db
        self._settings = settings
        self._provider = provider

    async def run(
        self,
        message: str,
        history: list[Message],
    ) -> AgentResult:
        t0 = time.monotonic()

        if self._provider.provider_name.startswith("mock"):
            # Bypass tool loop for Phase 2-5 backwards-compatibility tests.
            # Replicate old chat.py: pass full history + current message.
            llm_messages = list(history) + [Message(role="user", content=message)]
            mock_response = await self._provider.complete(llm_messages)
            result = AgentResult(
                answer=mock_response.content,
                provider=self._provider.provider_name,
                model=self._provider.model,
                prompt_tokens=mock_response.prompt_tokens,
                completion_tokens=mock_response.completion_tokens,
            )
        elif self._settings.agent_provider == "anthropic":
            result = await self._run_claude_sdk(message, history)
        else:
            result = await self._run_ollama_tool_loop(message, history)

        result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return result

    # ────────────────────────────────────────────────────────────────────────
    # Anthropic path — uses the claude-agent-sdk package
    # APIs used: ClaudeSDKClient, ClaudeAgentOptions, @tool
    # ────────────────────────────────────────────────────────────────────────

    async def _run_claude_sdk(self, message: str, history: list[Message]) -> AgentResult:
        """
        Runs the agent via the Claude Agent SDK.

        Package: claude-agent-sdk
        APIs:
          - ClaudeAgentOptions  — configures api_key and model
          - ClaudeSDKClient     — manages the agent session and tool loop
          - @tool               — decorates Python async functions as agent tools
        """
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, tool  # noqa: PLC0415

        collected_sources: list[SourceCitationData] = []
        collected_artifact: str | None = None
        skill_used: str | None = None
        db = self._db
        settings = self._settings
        provider = self._provider

        # ── Define tools as closures so they capture db/settings ──────────────

        @tool
        async def transcript_search(query: str) -> str:
            """Search Lenny's podcast transcripts for product and growth insights."""
            results, citations = await _execute_transcript_search(query, db, settings)
            collected_sources.extend(citations)
            return json.dumps(results)

        @tool
        async def write_ship_30_essay(topic: str) -> str:
            """Write a ~1,250-word Ship 30 for 30 essay grounded in Lenny's transcripts."""
            nonlocal collected_artifact, skill_used
            essay, citations = await _execute_write_ship_30_essay(topic, db, settings, provider)
            collected_sources.extend(citations)
            collected_artifact = essay
            skill_used = "ship30"
            return essay

        # ── Initialise SDK client ──────────────────────────────────────────────
        options = ClaudeAgentOptions(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

        # Build full prompt including recent history context
        history_ctx = self._format_history(history)
        full_prompt = f"{history_ctx}\n\nUser: {message}" if history_ctx else message

        async with ClaudeSDKClient(options=options) as client:
            sdk_result = await client.run(
                prompt=full_prompt,
                tools=[transcript_search, write_ship_30_essay],
                system=_GROUNDED_SYSTEM_PROMPT,
            )

        answer = getattr(sdk_result, "content", str(sdk_result))
        if skill_used is None and collected_sources:
            skill_used = "grounded_qa"

        return AgentResult(
            answer=answer,
            sources=collected_sources,
            artifact=collected_artifact,
            skill_used=skill_used,
            provider="claude_agent_sdk",
            model=settings.anthropic_model,
        )

    # ────────────────────────────────────────────────────────────────────────
    # Ollama path — native tool-calling via /api/chat
    # Does NOT use the Claude Agent SDK.
    # ────────────────────────────────────────────────────────────────────────

    async def _run_ollama_tool_loop(self, message: str, history: list[Message]) -> AgentResult:
        """
        Executes Ollama's native tool-calling loop:
        1. POST /api/chat with tool schemas.
        2. If response contains tool_calls, execute them.
        3. Append tool results and repeat.
        4. Return final text answer.
        """
        base_url = self._settings.ollama_base_url.rstrip("/")
        model = self._provider.model
        timeout = self._settings.ollama_timeout_seconds

        messages: list[dict] = [{"role": "system", "content": _GROUNDED_SYSTEM_PROMPT}]
        for m in history:
            messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": message})

        collected_sources: list[SourceCitationData] = []
        collected_artifact: str | None = None
        skill_used: str | None = None
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for _ in range(6):  # max tool-call iterations
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "tools": _OLLAMA_TOOL_SCHEMAS,
            }

            try:
                async with httpx.AsyncClient(timeout=timeout) as http:
                    resp = await http.post(f"{base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.TimeoutException:
                from app.errors.exceptions import LLMTimeoutError
                raise LLMTimeoutError(
                    provider="ollama",
                    detail=f"Ollama timed out after {timeout}s during tool loop"
                )
            except httpx.ConnectError:
                from app.errors.exceptions import ProviderUnavailableError
                raise ProviderUnavailableError(
                    provider="ollama",
                    detail=f"Cannot connect to Ollama at {base_url}"
                )
            except httpx.HTTPStatusError as exc:
                from app.errors.exceptions import LLMProviderError
                raise LLMProviderError(
                    provider="ollama",
                    detail=f"Ollama HTTP {exc.response.status_code}"
                )

            data = resp.json()
            msg = data.get("message", {})
            tool_calls: list[dict] = msg.get("tool_calls") or []
            total_prompt_tokens += data.get("prompt_eval_count", 0)
            total_completion_tokens += data.get("eval_count", 0)

            if not tool_calls:
                # Final answer turn
                answer = msg.get("content", "")
                if not answer:
                    answer = "I was unable to generate a response."
                if skill_used is None and collected_sources:
                    skill_used = "grounded_qa"
                return AgentResult(
                    answer=answer,
                    sources=collected_sources,
                    artifact=collected_artifact,
                    skill_used=skill_used,
                    provider=self._provider.provider_name,
                    model=model,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                )

            # Append model's tool-call message before processing
            messages.append({
                "role": "assistant",
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
            })

            # Execute each requested tool
            for tc in tool_calls:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                fn_args = fn.get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except (json.JSONDecodeError, TypeError):
                        fn_args = {}

                logger.info(
                    "Agent tool call",
                    extra={"component": "agent", "tool": fn_name, "tool_args": fn_args},
                )

                if fn_name == "transcript_search":
                    results, citations = await _execute_transcript_search(
                        fn_args.get("query", ""), self._db, self._settings
                    )
                    collected_sources.extend(citations)
                    tool_result = json.dumps(results)

                elif fn_name == "write_ship_30_essay":
                    essay, citations = await _execute_write_ship_30_essay(
                        fn_args.get("topic", ""), self._db, self._settings, self._provider
                    )
                    collected_sources.extend(citations)
                    collected_artifact = essay
                    skill_used = "ship30"
                    tool_result = essay

                else:
                    tool_result = f"Unknown tool: {fn_name}"
                    logger.warning("Unknown tool requested by model: %s", fn_name)

                messages.append({"role": "tool", "content": tool_result})

        # Iteration limit reached
        logger.warning("Agent tool loop exhausted max iterations")
        return AgentResult(
            answer="I was unable to complete the response within the allowed steps.",
            sources=collected_sources,
            artifact=collected_artifact,
            skill_used=skill_used,
            provider=self._provider.provider_name,
            model=model,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _format_history(self, history: list[Message]) -> str:
        if not history:
            return ""
        lines = [f"{m.role.capitalize()}: {m.content}" for m in history[-6:]]
        return "\n".join(lines)
