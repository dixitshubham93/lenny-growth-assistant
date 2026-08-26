"""
schemas/health.py — Request/response models for health endpoints.
"""
from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str          # "ok" | "degraded" | "error"
    version: str = "0.1.0"
    environment: str     # "development" | "production"


class LLMHealthResponse(BaseModel):
    status: str          # "ok" | "error"
    provider: str
    model: str
    reachable: bool
    detail: str = ""
