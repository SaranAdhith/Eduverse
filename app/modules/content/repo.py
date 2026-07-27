"""Async DB queries backing content assembly (DOC_06)."""
from __future__ import annotations

import uuid

from app.modules.content.model import ChunkQuizItem, ContentChunk
from app.modules.content.quiz import GeneratedQuestion
from app.modules.curation.model import VideoResource, VideoSegment
from app.modules.questions.model import Choice, Question
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


async def current_version(session: AsyncSession, topic_id: str) -> int:
    """The highest content_version for a topic, or 1 if none exists yet."""
    latest = await session.scalar(
        select(func.max(ContentChunk.content_version)).where(
            ContentChunk.topic_id == topic_id
        )
    )
    return int(latest) if latest is not None else 1


async def get_chunk(
    session: AsyncSession, topic_id: str, content_version: int
) -> ContentChunk | None:
    chunk: ContentChunk | None = await session.scalar(
        select(ContentChunk).where(
            ContentChunk.topic_id == topic_id,
            ContentChunk.content_version == content_version,
        )
    )
    return chunk


async def get_current_chunk(
    session: AsyncSession, topic_id: str
) -> ContentChunk | None:
    """The chunk for a topic's current content_version, if assembled."""
    version = await current_version(session, topic_id)
    return await get_chunk(session, topic_id, version)


async def load_segment(
    session: AsyncSession, segment_id: uuid.UUID
) -> VideoSegment | None:
    """A segment with its parent video (for the deep-link)."""
    segment: VideoSegment | None = await session.scalar(
        select(VideoSegment)
        .where(VideoSegment.id == segment_id)
        .options(selectinload(VideoSegment.video))
    )
    return segment


async def quiz_questions(
    session: AsyncSession, chunk_id: uuid.UUID, limit: int
) -> list[Question]:
    """A chunk's quiz questions (with choices), ordered by position."""
    result = await session.scalars(
        select(Question)
        .join(ChunkQuizItem, ChunkQuizItem.question_id == Question.id)
        .where(ChunkQuizItem.chunk_id == chunk_id)
        .order_by(ChunkQuizItem.position)
        .limit(limit)
        .options(selectinload(Question.choices))
    )
    return list(result.all())


async def quiz_items_with_questions(
    session: AsyncSession, chunk_id: uuid.UUID
) -> list[tuple[int, Question]]:
    """(position, question-with-choices) pairs for a chunk, ordered by position."""
    result = await session.execute(
        select(ChunkQuizItem.position, Question)
        .join(Question, Question.id == ChunkQuizItem.question_id)
        .where(ChunkQuizItem.chunk_id == chunk_id)
        .order_by(ChunkQuizItem.position)
        .options(selectinload(Question.choices))
    )
    return [(position, question) for position, question in result.all()]


async def acquire_topic_lock(session: AsyncSession, topic_id: str) -> None:
    """Serialize chunk assembly for a topic within the transaction (DOC_06 §7)."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(topic_id)))
    )


async def create_chunk(
    session: AsyncSession,
    *,
    topic_id: str,
    content_version: int,
    video_segment_id: uuid.UUID | None,
    lesson_markdown: str,
    fallback: bool,
    quiz_items: list[GeneratedQuestion],
) -> ContentChunk:
    """Persist a chunk, its generated questions, and their quiz-item links.

    Generated questions are ordinary ``questions`` rows (``source='generated'``)
    so gate responses flow through the mastery pipeline unchanged (DOC_06 §2).
    """
    chunk = ContentChunk(
        topic_id=topic_id,
        content_version=content_version,
        video_segment_id=video_segment_id,
        lesson_markdown=lesson_markdown,
        fallback=fallback,
    )
    session.add(chunk)
    await session.flush()

    for position, item in enumerate(quiz_items, start=1):
        question = Question(
            topic_id=topic_id,
            difficulty=item.difficulty,
            stem=item.stem,
            stem_code=item.stem_code,
            explanation=item.explanation,
            is_diagnostic=False,
            source="generated",
        )
        session.add(question)
        await session.flush()
        for choice in item.choices:
            session.add(
                Choice(
                    question_id=question.id,
                    label=choice.label,
                    text=choice.text,
                    is_correct=choice.is_correct,
                )
            )
        session.add(
            ChunkQuizItem(
                chunk_id=chunk.id, question_id=question.id, position=position
            )
        )

    await session.flush()
    return chunk


async def video_ids_for_segments(
    session: AsyncSession, segment_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Map segment id -> channel id for recent-channel variety (DOC_06 §4.3)."""
    if not segment_ids:
        return {}
    result = await session.execute(
        select(VideoSegment.id, VideoResource.channel_id)
        .join(VideoResource, VideoResource.id == VideoSegment.video_id)
        .where(VideoSegment.id.in_(segment_ids))
    )
    return {seg_id: channel_id for seg_id, channel_id in result.all()}
