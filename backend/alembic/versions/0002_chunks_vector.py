"""
0002_chunks_vector.py — Enable pgvector + create transcript_chunks table.

Depends on: 0001_initial.py (sessions, messages tables).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable the pgvector extension (idempotent — safe on re-run)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "transcript_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chunk_id", sa.String(length=256), nullable=False),
        sa.Column("episode_id", sa.String(length=256), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("guest", sa.String(length=256), nullable=True),
        sa.Column("date", sa.String(length=32), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("youtube_url", sa.Text(), nullable=True),
        sa.Column("video_id", sa.String(length=64), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_timestamp", sa.String(length=16), nullable=True),
        sa.Column("end_timestamp", sa.String(length=16), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        # VECTOR(768) — nomic-embed-text dimension confirmed at runtime
        sa.Column("embedding", sa.Text(), nullable=True),  # overridden below for PG
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Replace dummy Text column with VECTOR(768) — runs only on PostgreSQL
    # (SQLite used in unit tests won't reach this migration)
    op.execute("ALTER TABLE transcript_chunks ALTER COLUMN embedding TYPE vector(768) USING NULL::vector(768)")

    # Unique index on chunk_id for idempotent upserts
    op.create_index(
        "ix_transcript_chunks_chunk_id",
        "transcript_chunks",
        ["chunk_id"],
        unique=True,
    )

    # Secondary index for filtering by episode
    op.create_index(
        "ix_transcript_chunks_episode_id",
        "transcript_chunks",
        ["episode_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transcript_chunks_episode_id", table_name="transcript_chunks")
    op.drop_index("ix_transcript_chunks_chunk_id", table_name="transcript_chunks")
    op.drop_table("transcript_chunks")
    # Leave the vector extension installed — removing it could break other things
