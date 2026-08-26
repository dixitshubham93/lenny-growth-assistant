"""
llm/base.py — LLM provider interface (Protocol + data types).

Application code depends ONLY on these abstractions.
Concrete providers (Ollama, Groq) are never imported outside the llm/ package.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Message:
    """A single chat message exchanged with the LLM."""
    role: str          # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMResponse:
    """Structured response returned by every provider."""
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    # Future: sources list will be added in Phase 6 (RAG)


@dataclass
class ProviderStatus:
    """Result of a provider health/reachability check."""
    provider: str
    model: str
    reachable: bool
    detail: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    """
    Protocol that every concrete LLM provider must satisfy.

    Application code calls get_llm_provider(settings) and then uses
    this interface — it never branches on provider name in business logic.
    """

    provider_name: str   # "ollama" | "groq"
    model: str           # resolved model name (from config, never hardcoded)

    async def complete(
        self,
        messages: list[Message],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Send messages to the LLM and return a structured response."""
        ...

    async def check_health(self) -> ProviderStatus:
        """
        Lightweight reachability check for the /health/llm endpoint.
        Must not raise; always return a ProviderStatus.
        """
        ...
