"""
errors/exceptions.py — Application-specific exception hierarchy.

All exceptions carry enough context to produce a useful structured error
response without exposing secrets or raw stack traces.
"""
from __future__ import annotations


class LennyBaseError(Exception):
    """Root exception for all application errors."""

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(detail)


# ── LLM / Provider errors ─────────────────────────────────────────────────────

class LLMProviderError(LennyBaseError):
    """
    The provider returned an error response (e.g. HTTP 4xx/5xx from Ollama,
    APIStatusError from Groq).
    """

    def __init__(self, provider: str, detail: str = "") -> None:
        self.provider = provider
        super().__init__(detail)


class LLMTimeoutError(LLMProviderError):
    """The LLM request exceeded the configured timeout."""


class ProviderUnavailableError(LLMProviderError):
    """
    The provider endpoint cannot be reached at all
    (e.g. Ollama not running, network down).
    """


class ProviderConfigError(LennyBaseError):
    """
    Provider is misconfigured (unknown provider name, missing API key, etc.).
    Raised at startup or factory instantiation — not during a live request.
    """

    def __init__(self, provider: str, detail: str = "") -> None:
        self.provider = provider
        super().__init__(detail)


# ── Request / validation errors ───────────────────────────────────────────────

class InvalidRequestError(LennyBaseError):
    """The client sent a request that cannot be processed."""
