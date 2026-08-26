"""
llm/groq.py — Groq cloud LLM provider.

Uses the official groq Python SDK.
The model name and API key are always read from config — never hardcoded.
"""
from __future__ import annotations

import logging
import time

from groq import AsyncGroq, APIConnectionError, APIStatusError, APITimeoutError

from app.errors.exceptions import (
    LLMProviderError,
    LLMTimeoutError,
    ProviderUnavailableError,
)
from app.llm.base import LLMResponse, Message, ProviderStatus

logger = logging.getLogger(__name__)


class GroqProvider:
    """
    Concrete LLM provider backed by the Groq cloud API.

    API key and model name are injected from Settings at construction —
    never hardcoded in this class.
    """

    provider_name = "groq"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        # NOTE: we deliberately do NOT log the api_key here.
        self.model = model
        self._timeout = timeout_seconds
        self._client = AsyncGroq(api_key=api_key, timeout=timeout_seconds)

    # ── Public API ────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[Message],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Send messages to Groq and return a structured response.
        Raises LLMProviderError, LLMTimeoutError, or ProviderUnavailableError.
        """
        chat_messages = self._build_messages(messages, system_prompt)

        logger.info(
            "Calling Groq",
            extra={"component": "llm", "provider": self.provider_name, "model": self.model},
        )

        t0 = time.monotonic()
        try:
            completion = await self._client.chat.completions.create(
                model=self.model,
                messages=chat_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        except APITimeoutError as exc:
            logger.error(
                "Groq request timed out",
                extra={"component": "llm", "provider": self.provider_name},
            )
            raise LLMTimeoutError(
                provider=self.provider_name,
                detail=f"Groq API timed out after {self._timeout}s.",
            ) from exc

        except APIConnectionError as exc:
            logger.error(
                "Groq connection error",
                extra={"component": "llm", "provider": self.provider_name},
            )
            raise ProviderUnavailableError(
                provider=self.provider_name,
                detail="Could not connect to Groq API. Check network connectivity.",
            ) from exc

        except APIStatusError as exc:
            logger.error(
                "Groq API status error",
                extra={
                    "component": "llm",
                    "provider": self.provider_name,
                    "status_code": exc.status_code,
                    # Do NOT log exc.body — may contain key echoes
                },
            )
            raise LLMProviderError(
                provider=self.provider_name,
                detail=f"Groq API error {exc.status_code}: {exc.message}",
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        choice = completion.choices[0]
        usage = completion.usage

        logger.info(
            "Groq response received",
            extra={
                "component": "llm",
                "provider": self.provider_name,
                "latency_ms": round(latency_ms, 1),
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
            },
        )

        return LLMResponse(
            content=choice.message.content or "",
            model=self.model,
            provider=self.provider_name,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=round(latency_ms, 1),
        )

    async def check_health(self) -> ProviderStatus:
        """
        Verify Groq reachability by listing available models.
        Uses a short timeout so the health endpoint stays responsive.
        """
        try:
            models = await self._client.models.list()
            model_ids = [m.id for m in models.data]
            if self.model in model_ids:
                detail = f"Groq reachable; model '{self.model}' is available."
            else:
                detail = (
                    f"Groq reachable but model '{self.model}' not found in available models. "
                    f"Available: {model_ids[:5]}"
                )
            return ProviderStatus(
                provider=self.provider_name,
                model=self.model,
                reachable=True,
                detail=detail,
            )
        except Exception as exc:
            return ProviderStatus(
                provider=self.provider_name,
                model=self.model,
                reachable=False,
                detail=f"Groq unreachable: {exc}",
            )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_messages(messages: list[Message], system_prompt: str) -> list[dict]:
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend({"role": m.role, "content": m.content} for m in messages)
        return result
