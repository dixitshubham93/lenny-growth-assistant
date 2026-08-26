"""
api/routes/chat.py — Chat endpoint.

POST /api/v1/chat

Phase 2: wires request → LLM provider abstraction → response.
No RAG retrieval yet (Phase 6).
No session persistence yet (Phase 3).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
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
) -> ChatResponse:
    """
    Phase 2 chat endpoint.

    Accepts a user message and returns the LLM's response.
    Sources and session context will be populated in Phase 6 (RAG + agent).

    The LLM provider is determined by LLM_PROVIDER env var:
      - ollama  → local Ollama (default; required for demo)
      - groq    → Groq cloud API
    """
    logger.info(
        "Chat request received",
        extra={
            "component": "api",
            "provider": provider.provider_name,
            "session_id": request.session_id,
        },
    )

    system_prompt = request.system_prompt or _DEFAULT_SYSTEM_PROMPT
    messages = [Message(role="user", content=request.message)]

    llm_response = await provider.complete(
        messages=messages,
        system_prompt=system_prompt,
    )

    logger.info(
        "Chat response sent",
        extra={
            "component": "api",
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
        sources=[],           # populated in Phase 6
        session_id=request.session_id,
    )
