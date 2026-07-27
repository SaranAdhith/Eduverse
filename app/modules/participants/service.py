"""Participant enrollment / resume logic (DOC_01 §6).

Sequential code generation is serialized with a transaction-scoped Postgres
advisory lock so that concurrent ``enroll()`` calls cannot compute the same next
code. The UNIQUE constraint on ``participants.code`` is the final backstop.
"""
from __future__ import annotations

from app.modules.participants.model import Participant
from sqlalchemy import Integer, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Arbitrary fixed key identifying the "allocate next participant code" critical
# section for pg_advisory_xact_lock.
_ENROLL_LOCK_KEY = 0x65647576  # 'eduv'


class ConsentRequiredError(Exception):
    """Raised when enrollment is attempted without consent (DOC_01 §6)."""


class ParticipantNotFoundError(Exception):
    """Raised when a code does not resolve to a participant."""


def _format_code(seq: int) -> str:
    return f"P{seq:03d}"


async def enroll(session: AsyncSession, *, consent_given: bool) -> Participant:
    """Enroll a new participant, allocating the next sequential code.

    Raises :class:`ConsentRequiredError` if consent is not given.
    """
    if not consent_given:
        raise ConsentRequiredError("consent_given must be true to enroll")

    # Serialize the read-max-then-insert across concurrent transactions.
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ENROLL_LOCK_KEY})

    max_seq = await session.scalar(
        select(func.max(func.cast(func.substring(Participant.code, 2), Integer)))
    )
    next_seq = (max_seq or 0) + 1

    participant = Participant(
        code=_format_code(next_seq),
        consent_given=True,
        consent_at=func.now(),
    )
    session.add(participant)
    await session.flush()
    await session.refresh(participant)
    return participant


async def resume(session: AsyncSession, *, code: str) -> Participant:
    """Look up a participant by code, or raise :class:`ParticipantNotFoundError`."""
    participant = await session.scalar(
        select(Participant).where(Participant.code == code)
    )
    if participant is None:
        raise ParticipantNotFoundError(code)
    return participant
