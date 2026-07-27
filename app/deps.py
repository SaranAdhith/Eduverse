"""FastAPI dependencies (DOC_01 §6).

- ``get_session`` yields a request-scoped async DB session.
- ``get_participant`` resolves the ``X-Participant-Code`` header to a row and
  raises 401 if missing/invalid. Every later phase's protected endpoint depends
  on it.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.modules.participants import service
from app.modules.participants.model import Participant


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session; commits on success, rolls back on error."""
    async for session in session_scope():
        yield session


async def get_participant(
    x_participant_code: str | None = Header(default=None, alias="X-Participant-Code"),
    session: AsyncSession = Depends(get_session),
) -> Participant:
    """Resolve the participant from the ``X-Participant-Code`` header (401 if bad)."""
    if not x_participant_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-Participant-Code header",
        )
    try:
        participant = await service.resume(session, code=x_participant_code)
    except service.ParticipantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid X-Participant-Code header",
        ) from exc
    # Bind for downstream structured logs in this request.
    structlog.contextvars.bind_contextvars(participant_code=participant.code)
    return participant
