"""video curation pipeline tables

Revision ID: 0003_video_curation
Revises: 0002_knowledge_graph
Create Date: 2026-07-01

DOC_03 §2. Adds video_resources, video_segments (with a pgvector embedding +
hnsw index), and topic_video_coverage. Additive only.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.config import get_settings
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0003_video_curation"
down_revision: str | None = "0002_knowledge_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBED_DIM = get_settings().embedding_dim


def upgrade() -> None:
    op.create_table(
        "video_resources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("video_id", sa.String(length=20), nullable=False),
        sa.Column("channel_id", sa.String(length=40), nullable=False),
        sa.Column("channel_title", sa.String(length=160), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_captions", sa.Boolean(), nullable=False),
        sa.Column("caption_lang", sa.String(length=10), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("video_id", name="uq_video_resources_video_id"),
    )

    op.create_table(
        "video_segments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("video_resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id"),
            nullable=False,
        ),
        sa.Column("start_seconds", sa.Integer(), nullable=False),
        sa.Column("end_seconds", sa.Integer(), nullable=False),
        sa.Column("sub_topic_label", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_EMBED_DIM), nullable=True),
        sa.Column("quality_score", sa.REAL(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("end_seconds > start_seconds", name="ck_segment_span"),
    )
    op.create_index("idx_segments_topic", "video_segments", ["topic_id"])
    op.create_index("idx_segments_video", "video_segments", ["video_id"])
    op.create_index(
        "idx_segments_embedding",
        "video_segments",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "topic_video_coverage",
        sa.Column(
            "topic_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id"),
            primary_key=True,
        ),
        sa.Column(
            "segment_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_curated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )


def downgrade() -> None:
    op.drop_table("topic_video_coverage")
    op.drop_index("idx_segments_embedding", table_name="video_segments")
    op.drop_index("idx_segments_video", table_name="video_segments")
    op.drop_index("idx_segments_topic", table_name="video_segments")
    op.drop_table("video_segments")
    op.drop_table("video_resources")
