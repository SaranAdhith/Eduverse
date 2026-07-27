"""Study endpoints (DOC_08 §5, §6).

- ``POST /events/chunk_view`` / ``POST /events/idle`` — frontend telemetry the
  backend can't observe itself.
- ``POST /admin/export``      — per-participant analysis tarball.
- ``POST /admin/export-all``  — aggregated tarball (analyst's entry point).

Admin endpoints reuse the DOC_06 ``X-Admin-Token`` guard.
"""
from __future__ import annotations

from app.deps import get_participant, get_session
from app.modules.content.router import require_admin
from app.modules.participants.model import Participant
from app.modules.study import export, service
from app.modules.study.schema import ChunkViewEvent, EventAck, IdleEvent
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["study"])


@router.post("/events/chunk_view", response_model=EventAck)
async def chunk_view(
    body: ChunkViewEvent,
    participant: Participant = Depends(get_participant),
) -> EventAck:
    service.record_client_event(
        participant,
        "chunk_viewed",
        {
            "step_id": str(body.step_id),
            "video_seconds_watched": body.video_seconds_watched,
            "phase": body.phase,
        },
    )
    return EventAck()


@router.post("/events/idle", response_model=EventAck)
async def idle(
    body: IdleEvent,
    participant: Participant = Depends(get_participant),
) -> EventAck:
    service.record_client_event(
        participant,
        "idle",
        {
            "step_id": str(body.step_id) if body.step_id else None,
            "idle_seconds": body.idle_seconds,
        },
    )
    return EventAck()


@router.post("/admin/export")
async def export_participant(
    participant_code: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
    _admin: None = Depends(require_admin),
) -> Response:
    try:
        tarball = await export.build_participant(session, participant_code)
    except export.ParticipantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from exc
    return Response(
        content=tarball,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{participant_code}.tar.gz"'
        },
    )


@router.post("/admin/export-all")
async def export_all(
    session: AsyncSession = Depends(get_session),
    _admin: None = Depends(require_admin),
) -> Response:
    tarball = await export.build_all(session)
    return Response(
        content=tarball,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="export-all.tar.gz"'},
    )
