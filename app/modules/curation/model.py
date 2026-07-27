"""Curation ORM models (DOC_03 §2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.config import get_settings
from app.models.base import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

_EMBED_DIM = get_settings().embedding_dim


class VideoResource(Base):
    __tablename__ = "video_resources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    video_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    channel_title: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    view_count: Mapped[int | None] = mapped_column(nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    has_captions: Mapped[bool] = mapped_column(nullable=False)
    caption_lang: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    segments: Mapped[list[VideoSegment]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class VideoSegment(Base):
    __tablename__ = "video_segments"
    __table_args__ = (
        CheckConstraint("end_seconds > start_seconds", name="ck_segment_span"),
        Index("idx_segments_topic", "topic_id"),
        Index("idx_segments_video", "video_id"),
        Index(
            "idx_segments_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[str] = mapped_column(String(8), ForeignKey("topics.id"), nullable=False)
    start_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    end_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    sub_topic_label: Mapped[str] = mapped_column(Text, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBED_DIM), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    video: Mapped[VideoResource] = relationship(back_populates="segments")


class TopicVideoCoverage(Base):
    __tablename__ = "topic_video_coverage"

    topic_id: Mapped[str] = mapped_column(String(8), ForeignKey("topics.id"), primary_key=True)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_curated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # pending | covered | no_content
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
