"""
api/routes/chat.py — Chat endpoint (Phase 6: agent-wired, RAG-grounded).

POST /api/v1/chat

Flow:
  1. Validate session_id — 422 if missing; 404 if session unknown
  2. Load session history (capped at CHAT_HISTORY_LIMIT)
  3. Persist user message immediately (survives LLM failures)
  4. Run AgentRunner — tool-calling loop (transcript_search / write_ship_30_essay)
  5. Persist assistant message WITH sources (JSONB)
  6. Return ChatResponse with sources, artifact, skill_used

Phase 2–5 behavior is fully preserved:
  - session handling unchanged
  - error propagation unchanged
  - existing fields (answer, provider, model, tokens, latency) unchanged
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.crud import create_message, get_messages, get_session
from app.db.deps import get_db
from app.errors.exceptions import SessionNotFoundError
from app.llm.base import LLMProvider, Message
from app.llm.factory import get_llm_provider
from app.schemas.chat import ChatResponse, SourceCitation
from app.services.agent import AgentRunner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])


def _get_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_llm_provider(settings)


@router.post("/chat", response_model=ChatResponse, summary="Send a message to the assistant")
async def chat(
    request_body: "ChatRequestBody",
    provider: LLMProvider = Depends(_get_provider),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """
    Session-aware, RAG-grounded chat endpoint.

    Phase 6 changes (non-breaking):
    - AgentRunner replaces the direct provider.complete() call
    - sources, artifact, skill_used are populated in the response
    - assistant message persisted with sources JSONB

    Phase 2–5 fields (answer, provider, model, tokens, latency, session_id)
    are fully preserved.
    """
    from app.schemas.chat import ChatRequest  # local import avoids circular reference
    request = request_body  # type: ChatRequest
    session_id = request.session_id

    # 1. Verify session exists
    session = await get_session(db, session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    # 2. Load conversation history
    history = await get_messages(db, session_id, limit=settings.chat_history_limit)

    # 3. Persist user message BEFORE calling the agent (survives agent failures)
    await create_message(db, session_id, role="user", content=request.message)
    await db.commit()

    # 4. Build LLM history context for agent
    llm_history = [Message(role=m.role, content=m.content) for m in history]

    logger.info(
        "Chat request — running agent",
        extra={
            "component": "api",
            "session_id": session_id,
            "provider": provider.provider_name,
            "agent_provider": settings.agent_provider,
            "history_turns": len(history),
        },
    )

    # 5. Run AgentRunner (tool-calling loop)
    runner = AgentRunner(db=db, settings=settings, provider=provider)
    result = await runner.run(message=request.message, history=llm_history)

    # 6. Persist assistant message with sources
    sources_for_db = [
        {
            "chunk_id": s.chunk_id,
            "episode_id": s.episode_id,
            "title": s.title,
            "guest": s.guest,
            "start_timestamp": s.start_timestamp,
            "end_timestamp": s.end_timestamp,
            "source_file": s.source_file,
            "youtube_url": s.youtube_url,
            "cosine_distance": s.cosine_distance,
        }
        for s in result.sources
    ]
    await create_message(
        db,
        session_id,
        role="assistant",
        content=result.answer,
        sources=sources_for_db,
    )

    logger.info(
        "Chat response sent",
        extra={
            "component": "api",
            "session_id": session_id,
            "provider": result.provider,
            "skill_used": result.skill_used,
            "sources_count": len(result.sources),
            "has_artifact": result.artifact is not None,
            "latency_ms": result.latency_ms,
        },
    )

    # 7. Build source citation Pydantic models
    source_citations = [
        SourceCitation(
            chunk_id=s.chunk_id,
            episode_id=s.episode_id,
            title=s.title,
            guest=s.guest,
            start_timestamp=s.start_timestamp,
            end_timestamp=s.end_timestamp,
            source_file=s.source_file,
            youtube_url=s.youtube_url,
            cosine_distance=s.cosine_distance,
        )
        for s in result.sources
    ]

    return ChatResponse(
        answer=result.answer,
        provider=result.provider or provider.provider_name,
        model=result.model or provider.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
        session_id=session_id,
        sources=source_citations,
        artifact=result.artifact,
        skill_used=result.skill_used,
        retrieval_count=len(result.sources),
    )


# ── Type alias to satisfy FastAPI body parsing ────────────────────────────────
# Import at module level for FastAPI's schema generation
from app.schemas.chat import ChatRequest as ChatRequestBody  # noqa: E402
