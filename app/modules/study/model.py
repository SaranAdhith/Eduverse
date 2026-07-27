"""Study-instrumentation ORM models (DOC_08 §2, §8).

Three additive tables:

- ``study_assignments`` — the per-participant block order + mode assignment that
  makes the within-subject crossover valid. One row per participant.
- ``events``            — the durable, replayable event stream (dual-written
  alongside the JSONL log, DOC_08 §4).
- ``llm_cache``         — cached Claude responses keyed by ``(model, prompt)`` so
  the study is reproducible and analysis can replay without new API calls (§8).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.models.base import Base
from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class StudyAssignment(Base):
    __tablename__ = "study_assignments"
    __table_args__ = (
        CheckConstraint("block_order IN ('AB','BA')", name="ck_assignment_block_order"),
        CheckConstraint(
            "block_a_mode IN ('personalized','fixed')", name="ck_assignment_a_mode"
        ),
        CheckConstraint(
            "block_b_mode IN ('personalized','fixed')", name="ck_assignment_b_mode"
        ),
        # Each participant must experience both modes (DOC_08 §2).
        CheckConstraint("block_a_mode <> block_b_mode", name="ck_assignment_both_modes"),
    )

    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    block_order: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    block_a_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    block_b_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_events_participant", "participant_id"),
        Index("idx_events_type", "event_type"),
        Index("idx_events_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    participant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class LLMCache(Base):
    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
