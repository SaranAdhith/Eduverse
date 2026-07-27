"""mastery engine tables

Revision ID: 0004_mastery_engine
Revises: 0003_video_curation
Create Date: 2026-07-01

DOC_04 §1. Adds responses, mastery, and diagnostic_sessions. Additive only —
does not touch prior phases' tables.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_mastery_engine"
down_revision: str | None = "0003_video_curation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "responses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id"),
            nullable=False,
        ),
        sa.Column("context", sa.String(length=16), nullable=False),
        sa.Column("selected_label", sa.CHAR(length=1), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("prior_mastery", sa.REAL(), nullable=False),
        sa.Column("posterior_mastery", sa.REAL(), nullable=False),
        sa.CheckConstraint(
            "context IN ('diagnostic','gate','review')", name="ck_response_context"
        ),
        sa.CheckConstraint(
            "selected_label IN ('A','B','C','D')", name="ck_response_selected_label"
        ),
    )
    op.create_index("idx_responses_participant", "responses", ["participant_id"])
    op.create_index("idx_responses_topic", "responses", ["topic_id"])

    op.create_table(
        "mastery",
        sa.Column(
            "participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "topic_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id"),
            primary_key=True,
        ),
        sa.Column("p_mastered", sa.REAL(), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("p_mastered BETWEEN 0 AND 1", name="ck_mastery_p_range"),
    )

    op.create_table(
        "diagnostic_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "items_answered",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "uq_diagnostic_sessions_participant",
        "diagnostic_sessions",
        ["participant_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_diagnostic_sessions_participant", table_name="diagnostic_sessions"
    )
    op.drop_table("diagnostic_sessions")
    op.drop_table("mastery")
    op.drop_index("idx_responses_topic", table_name="responses")
    op.drop_index("idx_responses_participant", table_name="responses")
    op.drop_table("responses")
