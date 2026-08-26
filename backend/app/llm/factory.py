"""
llm/factory.py — Provider factory.

Single entry point for obtaining an LLM provider instance.
Application code calls get_llm_provider(settings) and receives an object
that satisfies the LLMProvider Protocol — never a concrete class reference.
"""
from __future__ import annotations

import logging

from app.core.config import Settings
from app.errors.exceptions import ProviderConfigError
from app.llm.base import LLMProvider
from app.llm.groq import GroqProvider
from app.llm.ollama import OllamaProvider

logger = logging.getLogger(__name__)


def get_llm_provider(settings: Settings) -> LLMProvider:
    """
    Instantiate and return the configured LLM provider.

    Selection is based solely on settings.llm_provider (the LLM_PROVIDER
    env var).  No provider-specific logic leaks outside this function.

    Raises:
        ProviderConfigError — if the provider name is unknown.
        ValueError          — if Groq is selected with missing credentials
                              (this is also caught at settings-load time, but
                              the factory validates again as a safety net).
    """
    provider_name = settings.llm_provider
    logger.info(
        "Initialising LLM provider",
        extra={"component": "factory", "provider": provider_name},
    )

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

    if provider_name == "groq":
        # Double-check; Settings validator should already have caught this.
        if not settings.groq_api_key:
            raise ProviderConfigError(
                provider="groq",
                detail=(
                    "GROQ_API_KEY is not set. "
                    "Add it to your .env file or switch LLM_PROVIDER=ollama."
                ),
            )
        if not settings.groq_model:
            raise ProviderConfigError(
                provider="groq",
                detail=(
                    "GROQ_MODEL is not set. "
                    "Add it to your .env file (e.g. GROQ_MODEL=llama-3.3-70b-versatile)."
                ),
            )
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            timeout_seconds=settings.groq_timeout_seconds,
        )

    raise ProviderConfigError(
        provider=provider_name,
        detail=(
            f"Unknown LLM_PROVIDER '{provider_name}'. "
            "Valid values: 'ollama', 'groq'."
        ),
    )
