"""Content-assembly endpoints (DOC_06 §10).

- ``GET  /steps/{id}/content``            — learner-facing chunk (no quiz keys).
- ``POST /topics/{id}/content/regenerate``— admin: bump version + rebuild.
- ``GET  /topics/{id}/content/preview``   — admin: chunk + quiz *with* keys.

Admin endpoints require the ``X-Admin-Token`` header to match ``ADMIN_TOKEN``.
"""
from __future__ import annotations

import uuid

from app.config import get_settings
from app.deps import get_participant, get_session
from app.modules.content import repo, service
from app.modules.content.model import ContentChunk
from app.modules.content.schema import (
    PreviewChoiceOut,
    PreviewQuizItem,
    PreviewResponse,
    StepContentResponse,
    TopicContext,
    VideoDeepLink,
)
from app.modules.content.service import StepContent
from app.modules.participants.model import Participant
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["content"])


def _embed_url(video_id: str, start: int, end: int) -> str:
    return f"https://www.youtube.com/embed/{video_id}?start={start}&end={end}"


def _step_content_out(content: StepContent) -> StepContentResponse:
    video: VideoDeepLink | None = None
    seg = content.segment
    if seg is not None and seg.video is not None:
        video = VideoDeepLink(
            video_id=seg.video.video_id,
            embed_url=_embed_url(seg.video.video_id, seg.start_seconds, seg.end_seconds),
            start_seconds=seg.start_seconds,
            end_seconds=seg.end_seconds,
            title=seg.video.title,
            channel_title=seg.video.channel_title,
            sub_topic_label=seg.sub_topic_label,
        )
    return StepContentResponse(
        chunk_id=content.chunk.id,
        topic=TopicContext(
            topic_id=content.topic.id,
            name=content.topic.name,
            description=content.topic.description,
            prerequisite_ids=content.prerequisite_ids,
        ),
        fallback=content.chunk.fallback,
        lesson_markdown=content.chunk.lesson_markdown,
        video=video,
    )


async def require_admin(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Guard admin endpoints with the configured admin token (DOC_06 §10)."""
    expected = get_settings().admin_token
    if not expected or x_admin_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
        )


@router.get("/steps/{step_id}/content", response_model=StepContentResponse)
async def step_content(
    step_id: uuid.UUID,
    _participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> StepContentResponse:
    try:
        content = await service.get_step_content(session, step_id)
    except service.ChunkNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _step_content_out(content)


@router.post("/topics/{topic_id}/content/regenerate", response_model=PreviewResponse)
async def regenerate_content(
    topic_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: None = Depends(require_admin),
) -> PreviewResponse:
    chunk = await service.regenerate(session, topic_id)
    return await _preview_out(session, chunk)


@router.get("/topics/{topic_id}/content/preview", response_model=PreviewResponse)
async def preview_content(
    topic_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: None = Depends(require_admin),
) -> PreviewResponse:
    try:
        chunk = await service.get_preview(session, topic_id)
    except service.ChunkNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return await _preview_out(session, chunk)


async def _preview_out(session: AsyncSession, chunk: ContentChunk) -> PreviewResponse:
    """Admin view — includes answer keys for content review (DOC_06 §10)."""
    items = [
        PreviewQuizItem(
            position=position,
            question_id=q.id,
            difficulty=q.difficulty,
            stem=q.stem,
            stem_code=q.stem_code,
            explanation=q.explanation,
            choices=[
                PreviewChoiceOut(label=c.label, text=c.text, is_correct=c.is_correct)
                for c in q.choices
            ],
        )
        for position, q in await repo.quiz_items_with_questions(session, chunk.id)
    ]
    return PreviewResponse(
        chunk_id=chunk.id,
        topic_id=chunk.topic_id,
        content_version=chunk.content_version,
        fallback=chunk.fallback,
        lesson_markdown=chunk.lesson_markdown,
        quiz_items=items,
    )
