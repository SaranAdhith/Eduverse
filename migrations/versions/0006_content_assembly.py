"""content assembly tables

Revision ID: 0006_content_assembly
Revises: 0005_path_planner
Create Date: 2026-07-02

DOC_06 §2. Adds content_chunks and chunk_quiz_items. Additive only.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_content_assembly"
down_revision: str | None = "0005_path_planner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "topic_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id"),
            nullable=False,
        ),
        sa.Column(
            "content_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "video_segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("video_segments.id"),
            nullable=True,
        ),
        sa.Column("lesson_markdown", sa.Text(), nullable=False),
        sa.Column(
            "fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "topic_id", "content_version", name="uq_chunk_topic_version"
        ),
    )

    op.create_table(
        "chunk_quiz_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("position BETWEEN 1 AND 10", name="ck_chunk_quiz_position"),
        sa.UniqueConstraint("chunk_id", "position", name="uq_chunk_quiz_position"),
        sa.UniqueConstraint("chunk_id", "question_id", name="uq_chunk_quiz_question"),
    )


def downgrade() -> None:
    op.drop_table("chunk_quiz_items")
    op.drop_table("content_chunks")
