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
        max_tokens=2000,
    )
    return response.content, citations


async def _execute_create_artifact(
    content: str,
    format: str = "markdown",
) -> str:
    """
    Framework-independent artifact creation capability.

    Security model:
    - Generated HTML is treated as UNTRUSTED.
    - The frontend renders it inside an iframe with sandbox="allow-same-origin".
    - Scripts (allow-scripts) are NOT granted → any <script> tag is inert.
    - Navigation (allow-top-navigation) is NOT granted.
    - Forms (allow-forms) are NOT granted.
    - The iframe cannot access the parent's DOM, localStorage, or sessionStorage.

    format: 'markdown' | 'html'
    - 'html': if content is already a complete HTML document (starts with <!DOCTYPE or <html),
              pass through unchanged. Otherwise convert Markdown to a polished HTML document.
    - 'markdown': return content unchanged (rendered by the frontend with marked.js).
    """
    import re

    fmt = format.lower().strip()

    if fmt != "html":
        # Markdown passthrough — frontend renders with marked.js
        return content

    stripped = content.strip()
    if stripped.lower().startswith("<!doctype") or stripped.lower().startswith("<html"):
        # Already a complete HTML document — pass through unchanged
        return content

    # ── Markdown → polished HTML conversion (no external dependencies) ────────
    def _md_to_html(md: str) -> str:
        lines = md.splitlines()
        out: list[str] = []
        in_ul = False

        def flush_list():
            nonlocal in_ul
            if in_ul:
                out.append("</ul>")
                in_ul = False

        def inline(text: str) -> str:
            """Apply bold, italic, and inline-code formatting."""
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
            text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
            text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
            return text

        for line in lines:
            s = line.strip()
            if s.startswith("### "):
                flush_list()
                out.append(f"<h3>{inline(s[4:])}</h3>")
            elif s.startswith("## "):
                flush_list()
                out.append(f"<h2>{inline(s[3:])}</h2>")
            elif s.startswith("# "):
                flush_list()
                out.append(f"<h1>{inline(s[2:])}</h1>")
            elif re.match(r"^[-*]\s", s):
                if not in_ul:
                    out.append("<ul>")
                    in_ul = True
                out.append(f"<li>{inline(s[2:])}</li>")
            elif re.match(r"^-{3,}$|^\*{3,}$", s):
                flush_list()
                out.append("<hr>")
            elif s == "":
                flush_list()
                out.append("")
            else:
                flush_list()
                out.append(f"<p>{inline(s)}</p>")

        flush_list()
        return "\n".join(out)

    body_html = _md_to_html(stripped)

    # Detect a title from the first H1 or H2, falling back to "Artifact"
    title_match = re.search(r"^#+ (.+)", stripped, re.MULTILINE)
    doc_title = title_match.group(1) if title_match else "Artifact"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{doc_title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 16px;
    line-height: 1.8;
    color: #1a1a2e;
    background: #fafaf9;
    padding: 40px 32px;
    max-width: 680px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 1.85rem;
    font-weight: 800;
    color: #0f0f23;
    margin: 0 0 20px;
    line-height: 1.2;
    padding-bottom: 14px;
    border-bottom: 3px solid #6c63ff;
  }}
  h2 {{
    font-size: 1.05rem;
    font-weight: 700;
    color: #2d2d5e;
    margin: 28px 0 8px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-family: system-ui, -apple-system, sans-serif;
  }}
  h3 {{
    font-size: 1rem;
    font-weight: 700;
    color: #2d2d5e;
    margin: 20px 0 6px;
    font-family: system-ui, -apple-system, sans-serif;
  }}
  p {{ margin: 0 0 14px; color: #2a2a3e; }}
  ul, ol {{ margin: 0 0 14px 24px; }}
  li {{ margin-bottom: 6px; color: #2a2a3e; }}
  strong {{ color: #2d2d5e; font-weight: 700; }}
  em {{ color: #444; }}
  code {{
    background: #eee;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
    font-size: 0.88em;
  }}
  hr {{
    border: none;
    border-top: 1px solid #ddd;
    margin: 28px 0;
  }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""



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
                "grounded in Lenny's Podcast transcripts. "
                "Returns essay TEXT only — does NOT create an artifact or open the Artifact Viewer. "
                "Use create_artifact separately only if the user EXPLICITLY asks to generate an artifact."
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
    {
        "type": "function",
        "function": {
            "name": "create_artifact",
            "description": (
                "Create a rendered artifact (Markdown or HTML) from provided content and display it in the Artifact Viewer. "
                "Only invoke this when the user EXPLICITLY asks to create an artifact, render content, or generate HTML. "
                "Do NOT call this automatically after write_ship_30_essay unless the user asked for an artifact."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The content to render as an artifact."},
                    "format": {
                        "type": "string",
                        "description": "Output format: 'markdown' (default) or 'html'.",
                        "enum": ["markdown", "html"],
                    },
                },
                "required": ["content"],
            },
        },
    },
]

_GROUNDED_SYSTEM_PROMPT = (
    "You are the Lenny Growth Assistant — an expert on product management and growth strategy, "
    "grounded exclusively in Lenny's Podcast transcripts.\n\n"
    "SKILL ROUTING RULES (follow exactly):\n"
    "1. ALWAYS call transcript_search before answering product/growth questions.\n"
    "2. ONLY cite facts that were returned by transcript_search. Do not answer from general world knowledge.\n"
    "3. If the transcript_search returns no results, or if the results are irrelevant/insufficient, you MUST explicitly state that there is insufficient transcript evidence to answer.\n"
    "4. If the user asks for a Ship 30 for 30 essay, call write_ship_30_essay. This returns essay TEXT only — do NOT also call create_artifact unless the user explicitly asks for an artifact.\n"
    "5. ONLY call create_artifact if the user EXPLICITLY asks to 'create an artifact', 'render as HTML', 'make an artifact', or similar. Never call it automatically after write_ship_30_essay.\n"
    "6. If the user asks for BOTH a Ship 30 essay AND an artifact, call write_ship_30_essay first, then create_artifact with that essay content.\n"
    "7. Never fabricate any episode, guest, timestamp, quote, or source details."
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
            """Write a ~1,250-word Ship 30 for 30 essay grounded in Lenny's transcripts. Returns essay text only."""
            nonlocal skill_used, collected_artifact
            essay, citations = await _execute_write_ship_30_essay(topic, db, settings, provider)
            collected_sources.extend(citations)
            skill_used = "ship30"
            collected_artifact = await _execute_create_artifact(essay, "html")
            return "Ship 30 essay generated and displayed in the artifact viewer."

        @tool
        async def create_artifact(content: str, format: str = "markdown") -> str:
            """Create a rendered Markdown or HTML artifact from the provided content."""
            nonlocal collected_artifact, skill_used
            artifact_content = await _execute_create_artifact(content, format)
            collected_artifact = artifact_content
            if skill_used is None:
                skill_used = "artifact"
            return "Artifact created successfully."

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
                tools=[transcript_search, write_ship_30_essay, create_artifact],
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
        last_generated_essay: str = ""
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
                if not answer or not answer.strip():
                    if last_generated_essay:
                        answer = last_generated_essay
                    else:
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
            # Sort tool calls so write_ship_30_essay executes before create_artifact
            tool_calls.sort(key=lambda tc: 0 if tc.get("function", {}).get("name") == "write_ship_30_essay" else 1)

            # Execute each requested tool
            for tc in tool_calls:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                fn_args = fn.get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        # Sometimes Ollama outputs unescaped newlines causing JSON decode to fail
                        fn_args = json.loads(fn_args.replace('\n', '\\n'))
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
                    skill_used = "ship30"
                    last_generated_essay = essay
                    
                    # Auto-promote full essays to polished HTML Artifacts
                    collected_artifact = await _execute_create_artifact(essay, "html")
                    
                    tool_result = "Ship 30 essay generated and displayed in the artifact viewer."

                elif fn_name == "create_artifact":
                    # Guardrail 1: Prevent LLM auto-triggering if user didn't ask for an artifact
                    user_wants_artifact = any(kw in message.lower() for kw in ["artifact", "html", "render", "viewer"])
                    if not user_wants_artifact:
                        logger.info("Ignoring hallucinated create_artifact call")
                        tool_result = "Ignored: User did not request an artifact."
                        messages.append({"role": "tool", "content": tool_result})
                        continue

                    content = fn_args.get("content", "")
                    
                    # Guardrail 2: If LLM failed to pass content (JSON error or omitted), fall back
                    if not content or len(content) < 20:
                        if last_generated_essay:
                            content = last_generated_essay
                        else:
                            # Fallback to the last substantial assistant message
                            for m in reversed(history):
                                if m.role == "assistant" and len(m.content) > 50:
                                    content = m.content
                                    break

                    fmt = fn_args.get("format", "html") if user_wants_artifact else "markdown"
                    artifact_content = await _execute_create_artifact(content, fmt)
                    collected_artifact = artifact_content
                    if skill_used is None:
                        skill_used = "artifact"
                    tool_result = "Artifact created successfully."

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
