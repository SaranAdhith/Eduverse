"""Mastery-engine ORM models (DOC_04 §1).

Three additive tables:

- ``responses``            — every answered item, with a BKT snapshot (prior +
  posterior) so DOC_08 can reconstruct the trajectory without re-running BKT.
- ``mastery``              — the current per-topic mastery vector.
- ``diagnostic_sessions``  — one placement session per participant.
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
    Index,
    Integer,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class Response(Base):
    __tablename__ = "responses"
    __table_args__ = (
        CheckConstraint(
            "context IN ('diagnostic','gate','review')", name="ck_response_context"
        ),
        CheckConstraint(
            "selected_label IN ('A','B','C','D')", name="ck_response_selected_label"
        ),
        Index("idx_responses_participant", "participant_id"),
        Index("idx_responses_topic", "topic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False
    )
    topic_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("topics.id"), nullable=False
    )
    context: Mapped[str] = mapped_column(String(16), nullable=False)
    selected_label: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # time-on-question, if the frontend supplies it
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # BKT snapshot at the moment of this response (before/after the update).
    prior_mastery: Mapped[float] = mapped_column(REAL, nullable=False)
    posterior_mastery: Mapped[float] = mapped_column(REAL, nullable=False)


class Mastery(Base):
    __tablename__ = "mastery"
    __table_args__ = (
        CheckConstraint("p_mastered BETWEEN 0 AND 1", name="ck_mastery_p_range"),
    )

    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("topics.id"), primary_key=True
    )
    p_mastered: Mapped[float] = mapped_column(REAL, nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DiagnosticSession(Base):
    __tablename__ = "diagnostic_sessions"
    __table_args__ = (
        # One diagnostic per participant.
        Index("uq_diagnostic_sessions_participant", "participant_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    items_answered: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
