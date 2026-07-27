"""initial: extensions + participants table

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-30

DOC_01 §4–5. Creates the vector + pgcrypto extensions and the participants
table. Later phases add their own additive migrations and must not modify this
one's table (DOC_01 §4).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.create_table(
        "participants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "consent_given",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("block_order", sa.CHAR(length=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("code", name="uq_participants_code"),
    )
    op.create_index("idx_participants_code", "participants", ["code"])


def downgrade() -> None:
    op.drop_index("idx_participants_code", table_name="participants")
    op.drop_table("participants")
    # Extensions are intentionally left in place on downgrade (shared).
