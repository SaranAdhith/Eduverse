"""Planner + gate endpoints (DOC_05 §8).

Mode and block come from the path, never the request — once a path is created,
its mode is locked.
"""
from __future__ import annotations

import uuid

from app.deps import get_participant, get_session
from app.modules.participants.model import Participant
from app.modules.planner import gate, repo, service
from app.modules.planner.model import LearningPath, PathStep
from app.modules.planner.schema import (
    AdvanceResponse,
    GateItemOut,
    GateResultResponse,
    GateStartResponse,
    GateSubmitRequest,
    PathCreateRequest,
    PathCreateResponse,
    PathCurrentResponse,
    PathStepOut,
)
from app.modules.questions.model import Question
from app.modules.questions.schema import ChoiceOut
from app.modules.study import assignment as study_assignment
from app.modules.study import service as study_service
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["planner"])

_PLANNER_ERROR_STATUS: dict[type[service.PlannerError], int] = {
    service.InvalidBlockError: 422,
    service.InvalidModeError: 422,
    service.PathNotFoundError: status.HTTP_404_NOT_FOUND,
}

_GATE_ERROR_STATUS: dict[type[gate.GateError], int] = {
    gate.AttemptNotFoundError: status.HTTP_404_NOT_FOUND,
    gate.AttemptAlreadyCompletedError: status.HTTP_409_CONFLICT,
}


def _step_out(step: PathStep) -> PathStepOut:
    return PathStepOut(
        id=step.id,
        topic_id=step.topic_id,
        step_index=step.step_index,
        status=step.status,
        attempts=step.attempts,
        planner_reasoning=step.planner_reasoning,
    )


def _gate_item_out(q: Question) -> GateItemOut:
    return GateItemOut(
        id=q.id,
        topic_id=q.topic_id,
        difficulty=q.difficulty,
        stem=q.stem,
        stem_code=q.stem_code,
        choices=[ChoiceOut(label=c.label, text=c.text) for c in q.choices],
    )


async def _owned_path(
    session: AsyncSession, participant: Participant, path_id: uuid.UUID
) -> LearningPath:
    path = await repo.get_path_by_id(session, path_id)
    if path is None or path.participant_id != participant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="path not found")
    return path


async def _owned_step(
    session: AsyncSession, participant: Participant, step_id: uuid.UUID
) -> PathStep:
    step = await repo.get_step(session, step_id)
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="step not found")
    # Authorize via the owning path.
    await _owned_path(session, participant, step.path_id)
    return step


@router.post("/paths", response_model=PathCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_path(
    body: PathCreateRequest,
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> PathCreateResponse:
    # DOC_08 §3: the mode is the sealed assignment's, not the client's. Reject a
    # client mode that disagrees; derive it when the client omits it.
    try:
        mode = await study_service.resolve_mode(
            session, participant, body.block, body.mode
        )
    except study_assignment.AssignmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="participant has no study assignment",
        ) from exc
    except study_service.ModeMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    try:
        path, step = await service.create_path(
            session, participant, block=body.block, mode=mode
        )
    except service.PlannerError as exc:
        raise _planner_http_error(exc) from exc
    return PathCreateResponse(
        path_id=path.id,
        block=path.block,
        mode=path.mode,
        current_step=_step_out(step) if step else None,
    )


@router.get("/paths/current", response_model=PathCurrentResponse)
async def current_path(
    block: str = Query(..., min_length=1, max_length=1),
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> PathCurrentResponse:
    try:
        progress = await service.get_progress(session, participant, block)
    except service.PlannerError as exc:
        raise _planner_http_error(exc) from exc
    return PathCurrentResponse(
        path_id=progress.path.id,
        block=progress.path.block,
        mode=progress.path.mode,
        completed=progress.path.completed_at is not None,
        completion_pct=progress.completion_pct,
        passed_count=progress.passed_count,
        total_topics=progress.total_topics,
        current_step=_step_out(progress.current_step) if progress.current_step else None,
        steps=[_step_out(s) for s in progress.steps],
    )


@router.post("/paths/{path_id}/advance", response_model=AdvanceResponse)
async def advance_path(
    path_id: uuid.UUID,
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> AdvanceResponse:
    path = await _owned_path(session, participant, path_id)
    step = await service.advance_path(session, path)
    return AdvanceResponse(
        path_id=path.id,
        completed=path.completed_at is not None,
        current_step=_step_out(step) if step else None,
    )


@router.post("/steps/{step_id}/gate/start", response_model=GateStartResponse)
async def start_gate(
    step_id: uuid.UUID,
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> GateStartResponse:
    step = await _owned_step(session, participant, step_id)
    if step.status == "passed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="step already passed"
        )
    attempt, items = await gate.start_attempt(session, step)
    return GateStartResponse(
        attempt_id=attempt.id,
        path_step_id=step.id,
        topic_id=step.topic_id,
        items=[_gate_item_out(q) for q in items],
    )


@router.post("/steps/{step_id}/gate/submit", response_model=GateResultResponse)
async def submit_gate(
    step_id: uuid.UUID,
    body: GateSubmitRequest,
    participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> GateResultResponse:
    step = await _owned_step(session, participant, step_id)
    attempt = await repo.latest_open_attempt(session, step.id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no open gate attempt; call gate/start first",
        )
    answers = [
        gate.GateAnswer(
            question_id=a.question_id,
            selected_label=a.selected_label,
            response_ms=a.response_ms,
        )
        for a in body.answers
    ]
    try:
        result = await gate.submit_attempt(session, participant, attempt, answers)
    except gate.GateError as exc:
        raise _gate_http_error(exc) from exc
    return GateResultResponse(
        passed=result.passed,
        score=result.score,
        posterior_at_gate=result.posterior_at_gate,
        step=_step_out(result.step),
        next_step=_step_out(result.next_step) if result.next_step else None,
    )


def _planner_http_error(exc: service.PlannerError) -> HTTPException:
    code = _PLANNER_ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=str(exc))


def _gate_http_error(exc: gate.GateError) -> HTTPException:
    code = _GATE_ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=str(exc))
