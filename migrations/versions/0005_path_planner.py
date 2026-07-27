"""path planner & mastery gate tables

Revision ID: 0005_path_planner
Revises: 0004_mastery_engine
Create Date: 2026-07-01

DOC_05 §1. Adds learning_paths, path_steps, and gate_attempts. Additive only.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_path_planner"
down_revision: str | None = "0004_mastery_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_paths",
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
        sa.Column("block", sa.CHAR(length=1), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("block IN ('A','B')", name="ck_path_block"),
        sa.CheckConstraint(
            "mode IN ('personalized','fixed')", name="ck_path_mode"
        ),
        sa.UniqueConstraint(
            "participant_id", "block", name="uq_path_participant_block"
        ),
    )

    op.create_table(
        "path_steps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "path_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_paths.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id"),
            nullable=False,
        ),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "unlocked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("passed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("planner_reasoning", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','passed','remediating')",
            name="ck_step_status",
        ),
        sa.UniqueConstraint("path_id", "step_index", name="uq_step_path_index"),
        sa.UniqueConstraint("path_id", "topic_id", name="uq_step_path_topic"),
    )

    op.create_table(
        "gate_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "path_step_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("path_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.REAL(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("posterior_at_gate", sa.REAL(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("gate_attempts")
    op.drop_table("path_steps")
    op.drop_table("learning_paths")
