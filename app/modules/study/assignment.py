"""Block-and-mode assignment rotation (DOC_08 §1, §3).

The study is a within-subject crossover: two blocks (A, B) crossed with two modes
(personalized, fixed), counterbalanced. Crossing order (AB/BA) with the
first-block mode yields four cells; a sealed-envelope rotation hands successive
enrollees the next cell so the cells stay balanced at small N — never random
assignment, which imbalances cells when the cohort is tiny.

Mode is **not** user-selectable: ``mode_for`` is the authority the path endpoint
consults, and it must agree with the row stored here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.participants.model import Participant
from app.modules.study.model import StudyAssignment
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

Mode = Literal["personalized", "fixed"]

# Serialises "count assignments then insert the next cell" across concurrent
# enrollments so two participants can't be handed the same cell.
_ASSIGN_LOCK_KEY = 0x65647541  # 'eduA'


@dataclass(frozen=True)
class _Cell:
    block_order: str
    block_a_mode: Mode
    block_b_mode: Mode


# The four cells, in rotation order (DOC_08 §1). block_a_mode / block_b_mode are
# stored irrespective of order; the doc's worked example maps as follows:
#   P001 → AB, A=personalized  → a=personalized, b=fixed
#   P002 → AB, A=fixed         → a=fixed,        b=personalized
#   P003 → BA, B=personalized  → b=personalized, a=fixed
#   P004 → BA, B=fixed         → b=fixed,        a=personalized
_ROTATION: tuple[_Cell, ...] = (
    _Cell("AB", "personalized", "fixed"),
    _Cell("AB", "fixed", "personalized"),
    _Cell("BA", "fixed", "personalized"),
    _Cell("BA", "personalized", "fixed"),
)

CELL_COUNT = len(_ROTATION)


class AssignmentNotFoundError(Exception):
    """No study assignment exists for the participant."""


def cell_for_index(n: int) -> _Cell:
    """The rotation cell for the ``n``-th (0-based) enrollee."""
    return _ROTATION[n % CELL_COUNT]


async def get_assignment(
    session: AsyncSession, participant_id: object
) -> StudyAssignment | None:
    return await session.get(StudyAssignment, participant_id)


async def assign(session: AsyncSession, participant: Participant) -> StudyAssignment:
    """Assign (or return the existing) block order + mode for a participant.

    Idempotent per participant. The next cell is the current assignment count
    mod four; the participant's ``block_order`` is backfilled in the same
    transaction (DOC_08 §3).
    """
    existing = await get_assignment(session, participant.id)
    if existing is not None:
        return existing

    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ASSIGN_LOCK_KEY})
    count = await session.scalar(select(func.count()).select_from(StudyAssignment)) or 0
    cell = cell_for_index(count)

    assignment = StudyAssignment(
        participant_id=participant.id,
        block_order=cell.block_order,
        block_a_mode=cell.block_a_mode,
        block_b_mode=cell.block_b_mode,
    )
    session.add(assignment)
    participant.block_order = cell.block_order
    await session.flush()
    return assignment


async def mode_for(
    session: AsyncSession, participant_id: object, block: str
) -> Mode:
    """The assigned mode for a participant's block — the path endpoint's authority.

    Raises :class:`AssignmentNotFoundError` if the participant was never assigned.
    """
    assignment = await get_assignment(session, participant_id)
    if assignment is None:
        raise AssignmentNotFoundError(str(participant_id))
    mode = assignment.block_a_mode if block == "A" else assignment.block_b_mode
    return mode  # type: ignore[return-value]


def assignment_cell(assignment: StudyAssignment) -> int:
    """The 0-based rotation cell index a stored assignment corresponds to."""
    target = _Cell(
        assignment.block_order,
        assignment.block_a_mode,  # type: ignore[arg-type]
        assignment.block_b_mode,  # type: ignore[arg-type]
    )
    return _ROTATION.index(target)
