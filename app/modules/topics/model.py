"""Topic + prerequisite ORM models (DOC_02 §1)."""
from __future__ import annotations

from app.models.base import Base
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # 'T0.1', 'T6.3'
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0..8
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_core: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("true")
    )

    # Prerequisites of this topic (edges topic -> prereq).
    prerequisite_links: Mapped[list[TopicPrerequisite]] = relationship(
        back_populates="topic",
        foreign_keys="TopicPrerequisite.topic_id",
        cascade="all, delete-orphan",
    )


class TopicPrerequisite(Base):
    __tablename__ = "topic_prerequisites"
    __table_args__ = (
        CheckConstraint("topic_id <> prereq_id", name="ck_prereq_not_self"),
    )

    topic_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    prereq_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )

    topic: Mapped[Topic] = relationship(
        back_populates="prerequisite_links", foreign_keys=[topic_id]
    )
