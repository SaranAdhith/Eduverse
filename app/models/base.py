"""Declarative base + shared mixins (DOC_01 §2)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` server-managed timestamps.

    The ``participants`` table tracks its own ``enrolled_at`` (DOC_01 §5) and
    does not use this mixin; it exists for later phases' tables.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
