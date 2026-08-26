"""
db/models.py — SQLAlchemy ORM models.

Tables: sessions, messages, transcript_chunks.
Schema is designed for extensibility:
  - messages.sources (JSONB) is empty now; Phase 6 populates it with RAG citations.
  - sessions.metadata_ (JSONB) accepts arbitrary user context.
  - transcript_chunks stores Phase 4 JSONL data + pgvector embedding.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector as PgVector
    _PGVECTOR_AVAILABLE = True
except ImportError:  # pragma: no cover
    PgVector = None  # type: ignore[assignment]
    _PGVECTOR_AVAILABLE = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Session(Base):
    """
    A chat session — container for an ordered list of messages.
    Each session is fully isolated: LLM context is drawn only from its own messages.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    # Extensible metadata: agent persona, user locale, etc.
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """
    A single turn in a session conversation.
    role: 'user' | 'assistant' | 'system'
    sources: reserved for Phase 6 RAG citations — empty list until then.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # sources populated in Phase 6; empty list for now
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    session: Mapped["Session"] = relationship("Session", back_populates="messages")


class TranscriptChunk(Base):
    """
    A vector-indexed chunk from a Lenny's Podcast transcript.

    chunk_id is the idempotent key (e.g. 'brian-chesky-000') — sourced directly
    from Phase 4 JSONL output.  Upserting on chunk_id is safe to repeat.

    embedding is VECTOR(768) — nomic-embed-text output dimension.
    Exact cosine similarity search: ORDER BY embedding <=> query_vec.
    """

    __tablename__ = "transcript_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Idempotent key (unique across all chunks) ──────────────────────────────
    chunk_id: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True, index=True
    )

    # ── Source-tracing metadata (Phase 4 schema) ───────────────────────────────
    episode_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    guest: Mapped[str | None] = mapped_column(String(256), nullable=True)
    date: Mapped[str | None] = mapped_column(String(32), nullable=True)       # "YYYY-MM-DD"
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_timestamp: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "HH:MM:SS"
    end_timestamp: Mapped[str | None] = mapped_column(String(16), nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Vector embedding ───────────────────────────────────────────────────────
    # VECTOR(768) when pgvector is available; falls back to Text for SQLite tests
    if _PGVECTOR_AVAILABLE:
        embedding: Mapped[list[float] | None] = mapped_column(
            PgVector(768), nullable=True
        )
    else:  # pragma: no cover
        embedding = mapped_column(Text, nullable=True)

    # ── Bookkeeping ────────────────────────────────────────────────────────────
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
