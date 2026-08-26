"""
errors/handlers.py — FastAPI exception handlers.

Registered in main.py via app.add_exception_handler().
Converts application exceptions into structured JSON error responses.
Never exposes API keys, full stack traces, or internal configuration.
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors.exceptions import (
    InvalidRequestError,
    LLMProviderError,
    LLMTimeoutError,
    LennyBaseError,
    ProviderConfigError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)


# ── Helper ────────────────────────────────────────────────────────────────────

def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI/Pydantic request body validation failure → 422."""
    logger.warning(
        "Request validation failed",
        extra={"component": "api", "path": request.url.path},
    )
    return _error_response(
        422,
        "validation_error",
        f"Invalid request: {exc.errors()[0].get('msg', 'check request body')}",
    )


async def handle_provider_config_error(
    request: Request, exc: ProviderConfigError
) -> JSONResponse:
    """Provider misconfiguration (missing key, unknown provider) → 503."""
    logger.error(
        "Provider configuration error",
        extra={"component": "llm", "provider": exc.provider, "detail": exc.detail},
    )
    return _error_response(503, "provider_config_error", exc.detail)


async def handle_provider_unavailable(
    request: Request, exc: ProviderUnavailableError
) -> JSONResponse:
    """Cannot reach the LLM provider → 503."""
    logger.error(
        "LLM provider unavailable",
        extra={"component": "llm", "provider": exc.provider},
    )
    return _error_response(503, "provider_unavailable", exc.detail)


async def handle_llm_timeout(
    request: Request, exc: LLMTimeoutError
) -> JSONResponse:
    """LLM request timed out → 504."""
    logger.error(
        "LLM request timed out",
        extra={"component": "llm", "provider": exc.provider},
    )
    return _error_response(504, "llm_timeout", exc.detail)


async def handle_llm_provider_error(
    request: Request, exc: LLMProviderError
) -> JSONResponse:
    """Generic LLM provider error (catch-all for provider subclasses) → 502."""
    logger.error(
        "LLM provider error",
        extra={"component": "llm", "provider": exc.provider, "detail": exc.detail},
    )
    return _error_response(502, "llm_provider_error", exc.detail)


async def handle_invalid_request(
    request: Request, exc: InvalidRequestError
) -> JSONResponse:
    """Application-level bad request → 400."""
    logger.warning(
        "Invalid request",
        extra={"component": "api", "detail": exc.detail},
    )
    return _error_response(400, "invalid_request", exc.detail)


async def handle_unexpected_error(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for unhandled exceptions → 500. Never exposes internals."""
    logger.error(
        "Unexpected server error",
        extra={"component": "api", "path": request.url.path},
        exc_info=True,
    )
    return _error_response(
        500,
        "internal_error",
        "An unexpected error occurred. Please try again or contact support.",
    )
