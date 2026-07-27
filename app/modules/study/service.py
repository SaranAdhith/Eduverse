"""Study service (DOC_08 §3, §5, §6).

Higher-level orchestration over :mod:`assignment`, :mod:`events`, and
:mod:`export`: enroll-time assignment, the mode-agreement check the path endpoint
relies on, and the client-telemetry events the backend can't observe itself.
"""
from __future__ import annotations

from app.logging import log_event
from app.modules.participants.model import Participant
from app.modules.study import assignment as assignment_mod
from app.modules.study.model import StudyAssignment
from sqlalchemy.ext.asyncio import AsyncSession


class ModeMismatchError(Exception):
    """A client-supplied path mode disagreed with the sealed assignment (§3)."""


async def assign_on_enroll(
    session: AsyncSession, participant: Participant
) -> StudyAssignment:
    """Assign block order + mode and emit ``participant_enrolled`` (DOC_08 §3)."""
    assignment = await assignment_mod.assign(session, participant)
    log_event(
        "participant_enrolled",
        participant_code=participant.code,
        participant_id=str(participant.id),
        block_order=assignment.block_order,
        assignment_cell=assignment_mod.assignment_cell(assignment),
    )
    return assignment


async def resolve_mode(
    session: AsyncSession,
    participant: Participant,
    block: str,
    requested_mode: str | None,
) -> assignment_mod.Mode:
    """Return the assigned mode for a block, rejecting a mismatched client mode.

    Mode is not user-selectable (DOC_08 §3): the assignment wins. A client that
    supplies a mode must supply the *correct* one, else the request is rejected.
    """
    mode = await assignment_mod.mode_for(session, participant.id, block)
    if requested_mode is not None and requested_mode != mode:
        raise ModeMismatchError(
            f"block {block} is assigned mode {mode!r}, not {requested_mode!r}"
        )
    return mode


def record_client_event(
    participant: Participant, event_type: str, payload: dict[str, object]
) -> None:
    """Log a frontend-sourced telemetry event (DOC_08 §5).

    Tagged ``source='client'`` so analysts can distinguish it from
    backend-observed events of the same type.
    """
    log_event(
        event_type,
        participant_code=participant.code,
        participant_id=str(participant.id),
        source="client",
        **payload,
    )
