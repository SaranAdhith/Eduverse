"""Content-assembly ORM models (DOC_06 §2).

Two additive tables:

- ``content_chunks``    — one reproducible learning chunk per
  ``(topic_id, content_version)``: the chosen video segment, the Claude-written
  bridging lesson, and a ``fallback`` flag for no-video topics.
- ``chunk_quiz_items``  — the ordered 5 gate questions of a chunk. The questions
  themselves are real ``questions`` rows (``source='generated'``) so responses
  flow through the same pipes as diagnostic responses (DOC_06 §2).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.models.base import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ContentChunk(Base):
    __tablename__ = "content_chunks"
    __table_args__ = (
        UniqueConstraint("topic_id", "content_version", name="uq_chunk_topic_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    topic_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("topics.id"), nullable=False
    )
    content_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    # NULL for fallback-only topics (no curated video).
    video_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_segments.id"), nullable=True
    )
    lesson_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    quiz_items: Mapped[list[ChunkQuizItem]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
        order_by="ChunkQuizItem.position",
    )


class ChunkQuizItem(Base):
    __tablename__ = "chunk_quiz_items"
    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 10", name="ck_chunk_quiz_position"),
        UniqueConstraint("chunk_id", "position", name="uq_chunk_quiz_position"),
        UniqueConstraint("chunk_id", "question_id", name="uq_chunk_quiz_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    chunk: Mapped[ContentChunk] = relationship(back_populates="quiz_items")
