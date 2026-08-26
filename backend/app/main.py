"""
main.py — FastAPI application entry point.

Startup order:
  1. Configure structured logging
  2. Load and validate settings (fails fast on missing Groq key, etc.)
  3. Register exception handlers
  4. Mount routers
  5. Expose OpenAPI docs at /docs

Run with:
  cd backend
  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.errors.exceptions import (
    InvalidRequestError,
    LLMProviderError,
    LLMTimeoutError,
    ProviderConfigError,
    ProviderUnavailableError,
)
from app.errors.handlers import (
    handle_invalid_request,
    handle_llm_provider_error,
    handle_llm_timeout,
    handle_provider_config_error,
    handle_provider_unavailable,
    handle_unexpected_error,
    handle_validation_error,
)
from app.api.routes import health as health_router
from app.api.routes import chat as chat_router

# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Startup / shutdown hook.
    - Logging is configured first so all subsequent messages are structured.
    - Settings are validated; an invalid config (e.g. missing Groq key) raises
      before the server accepts any traffic.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    logger = logging.getLogger(__name__)
    logger.info(
        "Lenny Growth Assistant starting",
        extra={
            "component": "startup",
            "environment": settings.app_env,
            "llm_provider": settings.llm_provider,
            # Intentionally NOT logging API keys or secrets
        },
    )

    yield  # application is running

    logger.info("Lenny Growth Assistant shutting down", extra={"component": "shutdown"})


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Lenny Growth Assistant API",
        description=(
            "Conversational AI grounded in Lenny's Podcast transcripts. "
            "Phase 2: LLM provider foundation (RAG, sessions, and artifacts in later phases)."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers (order: most-specific first) ───────────────────────
    application.add_exception_handler(RequestValidationError, handle_validation_error)
    application.add_exception_handler(ProviderConfigError, handle_provider_config_error)
    application.add_exception_handler(ProviderUnavailableError, handle_provider_unavailable)
    application.add_exception_handler(LLMTimeoutError, handle_llm_timeout)
    application.add_exception_handler(LLMProviderError, handle_llm_provider_error)
    application.add_exception_handler(InvalidRequestError, handle_invalid_request)
    application.add_exception_handler(Exception, handle_unexpected_error)

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(health_router.router)
    application.include_router(chat_router.router)

    return application


app = create_app()
