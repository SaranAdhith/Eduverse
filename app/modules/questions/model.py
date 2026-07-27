"""Question + choice ORM models (DOC_02 §1)."""
from __future__ import annotations

import uuid
from datetime import datetime

from app.models.base import Base
from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(
            "difficulty IN ('easy','medium','hard')", name="ck_question_difficulty"
        ),
        # Exactly one diagnostic question per order slot (partial unique index).
        Index(
            "uq_diagnostic_order",
            "diagnostic_order",
            unique=True,
            postgresql_where=text("is_diagnostic"),
        ),
        Index("idx_questions_topic", "topic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    topic_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("topics.id"), nullable=False
    )
    difficulty: Mapped[str] = mapped_column(String(8), nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    stem_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    is_diagnostic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    diagnostic_order: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'seed'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    choices: Mapped[list[Choice]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Choice.label",
    )


class Choice(Base):
    __tablename__ = "choices"
    __table_args__ = (
        CheckConstraint("label IN ('A','B','C','D')", name="ck_choice_label"),
        UniqueConstraint("question_id", "label", name="uq_choice_question_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)

    question: Mapped[Question] = relationship(back_populates="choices")
