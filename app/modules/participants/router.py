"""Identity endpoints: POST /enroll, POST /resume (DOC_01 §6)."""
from __future__ import annotations

from app.deps import get_session
from app.modules.participants import service
from app.modules.participants.schema import (
    EnrollRequest,
    EnrollResponse,
    ParticipantOut,
    ResumeRequest,
)
from app.modules.study import service as study_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["participants"])


@router.post("/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED)
async def enroll(
    body: EnrollRequest,
    session: AsyncSession = Depends(get_session),
) -> EnrollResponse:
    try:
        participant = await service.enroll(session, consent_given=body.consent_given)
    except service.ConsentRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    # DOC_08 §3: assign block order + mode immediately (also emits the enrolled
    # event with assignment info). Mode is never user-selectable.
    assignment = await study_service.assign_on_enroll(session, participant)
    return EnrollResponse(
        code=participant.code,
        id=participant.id,
        block_order=assignment.block_order,
    )


@router.post("/resume", response_model=ParticipantOut)
async def resume(
    body: ResumeRequest,
    session: AsyncSession = Depends(get_session),
) -> ParticipantOut:
    try:
        participant = await service.resume(session, code=body.code)
    except service.ParticipantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from exc
    return ParticipantOut.model_validate(participant)
