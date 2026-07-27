"""study instrumentation tables

Revision ID: 0007_study_instrumentation
Revises: 0006_content_assembly
Create Date: 2026-07-02

DOC_08 §2, §8. Adds study_assignments, events, and llm_cache. Additive only.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_study_instrumentation"
down_revision: str | None = "0006_content_assembly"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_assignments",
        sa.Column(
            "participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("block_order", sa.CHAR(length=2), nullable=False),
        sa.Column("block_a_mode", sa.String(length=16), nullable=False),
        sa.Column("block_b_mode", sa.String(length=16), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "block_order IN ('AB','BA')", name="ck_assignment_block_order"
        ),
        sa.CheckConstraint(
            "block_a_mode IN ('personalized','fixed')", name="ck_assignment_a_mode"
        ),
        sa.CheckConstraint(
            "block_b_mode IN ('personalized','fixed')", name="ck_assignment_b_mode"
        ),
        sa.CheckConstraint(
            "block_a_mode <> block_b_mode", name="ck_assignment_both_modes"
        ),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id"),
            nullable=True,
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("idx_events_participant", "events", ["participant_id"])
    op.create_index("idx_events_type", "events", ["event_type"])
    op.create_index("idx_events_ts", "events", ["ts"])

    op.create_table(
        "llm_cache",
        sa.Column("prompt_hash", sa.CHAR(length=64), primary_key=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("llm_cache")
    op.drop_index("idx_events_ts", table_name="events")
    op.drop_index("idx_events_type", table_name="events")
    op.drop_index("idx_events_participant", table_name="events")
    op.drop_table("events")
    op.drop_table("study_assignments")
