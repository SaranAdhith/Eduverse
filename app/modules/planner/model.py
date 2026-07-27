"""Planner ORM models (DOC_05 §1).

Three additive tables:

- ``learning_paths``  — one path per participant *per block* (the study runs two
  blocks per participant under different modes, DOC_00 §5).
- ``path_steps``      — the ordered topics of a path, each gated by mastery.
- ``gate_attempts``   — every gate quiz attempt, with score + posterior snapshot.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.models.base import Base
from sqlalchemy import (
    CHAR,
    REAL,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class LearningPath(Base):
    __tablename__ = "learning_paths"
    __table_args__ = (
        CheckConstraint("block IN ('A','B')", name="ck_path_block"),
        CheckConstraint(
            "mode IN ('personalized','fixed')", name="ck_path_mode"
        ),
        UniqueConstraint("participant_id", "block", name="uq_path_participant_block"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    block: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    steps: Mapped[list[PathStep]] = relationship(
        back_populates="path", cascade="all, delete-orphan", order_by="PathStep.step_index"
    )


class PathStep(Base):
    __tablename__ = "path_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_progress','passed','remediating')",
            name="ck_step_status",
        ),
        UniqueConstraint("path_id", "step_index", name="uq_step_path_index"),
        UniqueConstraint("path_id", "topic_id", name="uq_step_path_topic"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    path_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("topics.id"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    passed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    # Claude's rationale for personalized mode; NULL/empty for fixed mode.
    planner_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    path: Mapped[LearningPath] = relationship(back_populates="steps")


class GateAttempt(Base):
    __tablename__ = "gate_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    path_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("path_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    posterior_at_gate: Mapped[float | None] = mapped_column(REAL, nullable=True)
