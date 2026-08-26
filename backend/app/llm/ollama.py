"""
llm/ollama.py — Ollama local LLM provider.

Calls the Ollama REST API directly via httpx (no third-party Ollama SDK).
Ollama's /api/chat endpoint is compatible with the OpenAI chat-completions
message format when using the "messages" key.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

from app.errors.exceptions import (
    LLMProviderError,
    LLMTimeoutError,
    ProviderUnavailableError,
)
from app.llm.base import LLMResponse, Message, ProviderStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OllamaProvider:
    """
    Concrete LLM provider backed by a locally-running Ollama instance.

    Talks to Ollama's /api/chat endpoint (streaming=False).
    The base URL and model name are read from config at construction time —
    never hardcoded here.
    """

    provider_name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 120.0) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    # ── Public API ────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[Message],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Send a list of messages to Ollama and return a structured response.
        Raises LLMProviderError, LLMTimeoutError, or ProviderUnavailableError.
        """
        payload = self._build_payload(messages, system_prompt, temperature, max_tokens)

        logger.info(
            "Calling Ollama",
            extra={"component": "llm", "provider": self.provider_name, "model": self.model},
        )

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                )
            response.raise_for_status()

        except httpx.TimeoutException as exc:
            logger.error(
                "Ollama request timed out",
                extra={"component": "llm", "provider": self.provider_name},
            )
            raise LLMTimeoutError(
                provider=self.provider_name,
                detail=f"Request to Ollama timed out after {self._timeout}s.",
            ) from exc

        except httpx.ConnectError as exc:
            logger.error(
                "Cannot reach Ollama — is it running?",
                extra={"component": "llm", "provider": self.provider_name},
            )
            raise ProviderUnavailableError(
                provider=self.provider_name,
                detail=(
                    f"Cannot connect to Ollama at {self._base_url}. "
                    "Ensure Ollama is running: `ollama serve`"
                ),
            ) from exc

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ollama returned HTTP error",
                extra={
                    "component": "llm",
                    "provider": self.provider_name,
                    "status_code": exc.response.status_code,
                },
            )
            raise LLMProviderError(
                provider=self.provider_name,
                detail=f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:200]}",
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        data = response.json()

        content = data.get("message", {}).get("content", "")
        usage = data.get("prompt_eval_count", 0), data.get("eval_count", 0)

        logger.info(
            "Ollama response received",
            extra={
                "component": "llm",
                "provider": self.provider_name,
                "latency_ms": round(latency_ms, 1),
                "prompt_tokens": usage[0],
                "completion_tokens": usage[1],
            },
        )

        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.provider_name,
            prompt_tokens=usage[0],
            completion_tokens=usage[1],
            latency_ms=round(latency_ms, 1),
        )

    async def check_health(self) -> ProviderStatus:
        """Ping Ollama's /api/tags endpoint to verify reachability."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
            resp.raise_for_status()
            return ProviderStatus(
                provider=self.provider_name,
                model=self.model,
                reachable=True,
                detail=f"Ollama is reachable at {self._base_url}",
            )
        except Exception as exc:
            return ProviderStatus(
                provider=self.provider_name,
                model=self.model,
                reachable=False,
                detail=f"Ollama unreachable: {exc}",
            )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[Message],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        chat_messages = []
        if system_prompt:
            chat_messages.append({"role": "system", "content": system_prompt})
        chat_messages.extend({"role": m.role, "content": m.content} for m in messages)

        return {
            "model": self.model,
            "messages": chat_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
