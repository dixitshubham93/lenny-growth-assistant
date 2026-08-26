"""
core/logging.py — Structured JSON logging configuration.

Configures the Python standard logging system to emit JSON-structured
log records.  No bare print() calls should appear anywhere in the application.

Log fields emitted on every record:
  timestamp  — ISO-8601 UTC
  level      — INFO / WARNING / ERROR / DEBUG
  logger     — dotted module path
  message    — human-readable event description
  (additional fields attached via extra={} on each log call)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    # Fields from LogRecord that we promote to top-level JSON keys.
    _PROMOTE = {"request_id", "component", "event_detail", "latency_ms", "provider"}

    def format(self, record: logging.LogRecord) -> str:
        doc: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach any extra fields passed via logger.info("...", extra={...})
        for key in self._PROMOTE:
            val = record.__dict__.get(key)
            if val is not None:
                doc[key] = val

        # Attach exception info if present
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)

        return json.dumps(doc, default=str)


def configure_logging(level: str = "INFO") -> None:
    """
    Call once at application startup (in main.py lifespan).
    Replaces the root logger's handlers with a JSON formatter on stdout.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Silence noisy third-party loggers at WARNING unless debug mode
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(
            logging.DEBUG if numeric_level == logging.DEBUG else logging.WARNING
        )


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger.  Usage: logger = get_logger(__name__)"""
    return logging.getLogger(name)
