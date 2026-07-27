"""Diagnostic delivery + mastery endpoints (DOC_04 §2.4).

Immediate correctness feedback is intentional: this is a placement test, not a
graded exam (DOC_04 §2.4).
"""
from __future__ import annotations

from app.deps import get_participant, get_session
from app.modules.mastery import repo, service
from app.modules.mastery.model import Mastery
from app.modules.mastery.schema import (
    AnswerRequest,
    AnswerResponse,
    MasteryEntry,
    MasteryVector,
    StartDiagnosticResponse,
)
from app.modules.participants.model import Participant
from app.modules.questions.model import Question
from app.modules.questions.schema import ChoiceOut, DiagnosticItemOut
from app.modules.topics.model import Topic
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter(tags=["mastery"])

# Service error -> HTTP status. Ordering violations surface as 422 (DOC_04 §6.5).
# 422 is a literal: Starlette has deprecated the ENTITY-spelled constant.
_HTTP_422 = 422
_ERROR_STATUS: dict[type[service.MasteryError], int] = {
    service.DiagnosticAlreadyCompletedError: status.HTTP_409_CONFLICT,
    service.DiagnosticNotStartedError: status.HTTP_409_CONFLICT,
    service.DiagnosticIncompleteError: status.HTTP_409_CONFLICT,
    service.SessionMismatchError: status.HTTP_403_FORBIDDEN,
    service.QuestionNotFoundError: status.HTTP_404_NOT_FOUND,
    service.NotADiagnosticItemError: _HTTP_422,
    service.InvalidChoiceError: _HTTP_422,
    service.OutOfOrderAnswerError: _HTTP_422,
}


def _http_error(exc: service.MasteryError) -> HTTPException:
    code = _ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=str(exc))


async def _fetch_items(session: AsyncSession) -> list[DiagnosticItemOut]:
    """The 25 placement items in order, without answer keys (DOC_02 §5)."""
    questions = list(
        await session.scalars(
            select(Question)
            .where(Question.is_diagnostic.is_(True))
            .order_by(Question.diagnostic_order)
            .options(selectinload(Question.choices))
        )
    )
    return [
        DiagnosticItemOut(
            id=q.id,
            order=q.diagnostic_order,  # always set for diagnostic questions
            topic_id=q.topic_id,
            difficulty=q.difficulty,
            stem=q.stem,
            stem_code=q.stem_code,
            choices=[ChoiceOut(label=c.label, text=c.text) for c in q.choices],
        )
        for q in questions
    ]


def _to_vector(
    participant: Participant, rows: list[tuple[Mastery, Topic]], *, completed: bool
) -> MasteryVector:
    return MasteryVector(
        participant_code=participant.code,
        completed=completed,
        entries=[
            MasteryEntry(
                topic_id=topic.id,
                topic_name=topic.name,
                tier=topic.tier,
                p_mastered=mastery.p_mastered,
                attempts=mastery.attempts,
            )
            for mastery, topic in rows
        ],
    )


@router.post("/diagnostic/start", response_model=StartDiagnosticResponse)
async def start_diagnostic(
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> StartDiagnosticResponse:
    try:
        diag = await service.start_diagnostic(session, participant)
    except service.MasteryError as exc:
        raise _http_error(exc) from exc
    return StartDiagnosticResponse(
        session_id=diag.id,
        items_answered=diag.items_answered,
        items=await _fetch_items(session),
    )


@router.post("/diagnostic/answer", response_model=AnswerResponse)
async def answer_diagnostic(
    body: AnswerRequest,
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> AnswerResponse:
    try:
        response, question, items_remaining = await service.answer_diagnostic(
            session,
            participant,
            session_id=body.session_id,
            question_id=body.question_id,
            selected_label=body.selected_label,
            response_ms=body.response_ms,
        )
    except service.MasteryError as exc:
        raise _http_error(exc) from exc
    # Reveal correctness + explanation immediately (placement test, not an exam).
    return AnswerResponse(
        is_correct=response.is_correct,
        explanation=question.explanation,
        items_remaining=items_remaining,
    )


@router.post("/diagnostic/complete", response_model=MasteryVector)
async def complete_diagnostic(
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> MasteryVector:
    try:
        await service.complete_diagnostic(session, participant)
    except service.MasteryError as exc:
        raise _http_error(exc) from exc
    rows = await service.get_mastery_vector(session, participant)
    return _to_vector(participant, rows, completed=True)


@router.get("/mastery", response_model=MasteryVector)
async def get_mastery(
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> MasteryVector:
    diag = await repo.get_diagnostic_session(session, participant.id)
    completed = diag is not None and diag.completed_at is not None
    rows = await service.get_mastery_vector(session, participant)
    return _to_vector(participant, rows, completed=completed)
