"""knowledge graph & question bank

Revision ID: 0002_knowledge_graph
Revises: 0001_initial
Create Date: 2026-07-01

DOC_02 §1. Adds topics, topic_prerequisites, questions, choices. Additive only —
does not touch DOC_01's participants table.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_knowledge_graph"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.String(length=8), primary_key=True),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column(
            "is_core", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.UniqueConstraint("slug", name="uq_topics_slug"),
    )

    op.create_table(
        "topic_prerequisites",
        sa.Column(
            "topic_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "prereq_id",
            sa.String(length=8),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.CheckConstraint("topic_id <> prereq_id", name="ck_prereq_not_self"),
    )
    op.create_index("idx_prereq_lookup", "topic_prerequisites", ["topic_id"])
    op.create_index("idx_prereq_reverse", "topic_prerequisites", ["prereq_id"])

    op.create_table(
        "questions",
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
        sa.Column("difficulty", sa.String(length=8), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("stem_code", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "is_diagnostic",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("diagnostic_order", sa.SmallInteger(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'seed'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "difficulty IN ('easy','medium','hard')", name="ck_question_difficulty"
        ),
    )
    op.create_index(
        "uq_diagnostic_order",
        "questions",
        ["diagnostic_order"],
        unique=True,
        postgresql_where=sa.text("is_diagnostic"),
    )
    op.create_index("idx_questions_topic", "questions", ["topic_id"])

    op.create_table(
        "choices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.CHAR(length=1), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.CheckConstraint("label IN ('A','B','C','D')", name="ck_choice_label"),
        sa.UniqueConstraint("question_id", "label", name="uq_choice_question_label"),
    )


def downgrade() -> None:
    op.drop_table("choices")
    op.drop_index("idx_questions_topic", table_name="questions")
    op.drop_index("uq_diagnostic_order", table_name="questions")
    op.drop_table("questions")
    op.drop_index("idx_prereq_reverse", table_name="topic_prerequisites")
    op.drop_index("idx_prereq_lookup", table_name="topic_prerequisites")
    op.drop_table("topic_prerequisites")
    op.drop_table("topics")
