"""
api/routes/chat.py — Chat endpoint (Phase 3: session-aware).

POST /api/v1/chat

Flow:
  1. Validate session_id is provided (Pydantic — 422 if missing)
  2. Verify session exists in DB (404 if not)
  3. Load session history (capped at CHAT_HISTORY_LIMIT)
  4. Persist user message (before calling LLM)
  5. Build LLM context: history + new user message
  6. Call LLM provider
  7a. On LLM success: persist assistant message, return response
  7b. On LLM failure: do NOT delete user message; raise structured error
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
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

_DEFAULT_SYSTEM_PROMPT = (
    "You are the Lenny Growth Assistant, an expert on product management, "
    "growth strategy, and startup building. "
    "Answer clearly and concisely based on your knowledge. "
    "In later versions your answers will be grounded in Lenny's Podcast transcripts."
)


def _get_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_llm_provider(settings)


@router.post("/chat", response_model=ChatResponse, summary="Send a message to the assistant")
async def chat(
    request: ChatRequest,
    provider: LLMProvider = Depends(_get_provider),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """
    Session-aware chat endpoint.

    Requires a valid session_id (create one via POST /api/v1/sessions).
    Loads that session's history as LLM context.
    Persists both user message and assistant response.
    If the LLM call fails, the user message is NOT deleted — it stays in history.
    """
    session_id = request.session_id  # required by schema

    # 1. Verify session exists
    session = await get_session(db, session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    # 2. Load conversation history (capped at CHAT_HISTORY_LIMIT)
    history = await get_messages(db, session_id, limit=settings.chat_history_limit)

    # 3. Persist user message NOW — commit immediately so it survives an LLM failure.
    #    We use an explicit flush+commit here rather than relying on the get_db teardown
    #    because the outer session would be rolled back on LLM exception.
    await create_message(db, session_id, role="user", content=request.message)
    await db.commit()   # ← commits user msg; get_db teardown will see nothing extra to commit

    # 4. Build LLM messages: history + new user turn
    llm_messages = [Message(role=m.role, content=m.content) for m in history]
    llm_messages.append(Message(role="user", content=request.message))

    system_prompt = request.system_prompt or _DEFAULT_SYSTEM_PROMPT

    logger.info(
        "Chat request — calling LLM",
        extra={
            "component": "api",
            "session_id": session_id,
            "provider": provider.provider_name,
            "history_turns": len(history),
        },
    )

    # 5. Call the LLM.  Any LLM exception propagates — user message already committed.
    llm_response = await provider.complete(
        messages=llm_messages,
        system_prompt=system_prompt,
    )

    # 6. Persist assistant response (only on success)
    await create_message(db, session_id, role="assistant", content=llm_response.content)

    logger.info(
        "Chat response sent",
        extra={
            "component": "api",
            "session_id": session_id,
            "provider": provider.provider_name,
            "latency_ms": llm_response.latency_ms,
        },
    )

    return ChatResponse(
        answer=llm_response.content,
        provider=llm_response.provider,
        model=llm_response.model,
        prompt_tokens=llm_response.prompt_tokens,
        completion_tokens=llm_response.completion_tokens,
        latency_ms=llm_response.latency_ms,
        sources=[],
        session_id=session_id,
    )
