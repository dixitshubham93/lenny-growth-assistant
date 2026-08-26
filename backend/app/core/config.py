"""
core/config.py — Application configuration.

All configuration is read from environment variables (or a .env file).
No model names, API keys, or provider choices are hardcoded here.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object.  Loaded once at startup via get_settings().
    All values come from environment variables or the .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    secret_key: str = "change-this-to-a-random-secret"
    cors_origins: str = "http://localhost:3000"

    # ── LLM provider routing ─────────────────────────────────────────────────
    llm_provider: Literal["ollama", "groq"] = "ollama"

    # ── Ollama ───────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_timeout_seconds: float = 120.0

    # ── Groq ─────────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = ""
    groq_timeout_seconds: float = 30.0

    # ── Embeddings ───────────────────────────────────────────────────────────
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"

    # ── PostgreSQL (Phase 3) — required for session persistence ──────────────
    database_url: str = ""

    # ── Chat context window ──────────────────────────────────────────────────
    chat_history_limit: int = 20  # prior messages passed to LLM per request

    # ── Phase 4: Ingestion pipeline ──────────────────────────────────────────
    # Optional GitHub token — raises rate limit from 60 to 5000 req/hr
    github_token: str | None = None
    # Sliding-window chunker settings (word counts, not token counts)
    chunk_size: int = 500
    chunk_overlap: int = 100

    # ── Derived helpers ──────────────────────────────────────────────────────

    @property
    def cors_origins_list(self) -> list[str]:
        """Split comma-separated CORS_ORIGINS into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def validate_groq_config(self) -> "Settings":
        """
        Fail fast at startup if Groq is selected but no API key is provided.
        Prevents confusing runtime errors after the app has started.
        """
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError(
                "LLM_PROVIDER is set to 'groq' but GROQ_API_KEY is missing or empty. "
                "Set GROQ_API_KEY in your .env file or switch LLM_PROVIDER to 'ollama'."
            )
        if self.llm_provider == "groq" and not self.groq_model:
            raise ValueError(
                "LLM_PROVIDER is set to 'groq' but GROQ_MODEL is missing or empty. "
                "Set GROQ_MODEL in your .env file (e.g. GROQ_MODEL=llama-3.3-70b-versatile)."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.
    Cached so environment is read exactly once at startup.
    Call get_settings.cache_clear() in tests that need fresh config.
    """
    return Settings()
