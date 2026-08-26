"""
api/routes/health.py — Health check endpoints.

GET /health        — API process liveness
GET /health/llm    — LLM provider reachability
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.schemas.health import HealthResponse, LLMHealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def _get_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_llm_provider(settings)


@router.get("/health", response_model=HealthResponse, summary="API liveness check")
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """
    Returns 200 when the API process is alive.
    Does not check LLM or database — use /health/llm for that.
    """
    logger.info("Health check", extra={"component": "api"})
    return HealthResponse(
        status="ok",
        environment=settings.app_env,
    )


@router.get(
    "/health/llm",
    response_model=LLMHealthResponse,
    summary="LLM provider reachability check",
)
async def health_llm(
    provider: LLMProvider = Depends(_get_provider),
) -> LLMHealthResponse:
    """
    Verifies that the configured LLM provider is reachable.
    Returns provider name and model so the evaluator can confirm which
    provider is active without digging into configuration files.
    """
    logger.info(
        "LLM health check",
        extra={"component": "api", "provider": provider.provider_name},
    )
    status = await provider.check_health()
    return LLMHealthResponse(
        status="ok" if status.reachable else "error",
        provider=status.provider,
        model=status.model,
        reachable=status.reachable,
        detail=status.detail,
    )
