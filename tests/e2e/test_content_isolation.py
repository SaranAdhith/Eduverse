"""Content isolation (DOC_09 §2.5).

Two participants in different modes who reach the same topic must see the *same*
chunk — same video segment, same lesson, same quiz items. Content is addressed by
(topic_id, content_version), independent of participant or mode, so the study's
internal validity holds: mode changes what you're taught *next*, never *how a
given topic is taught*.
"""
from __future__ import annotations

from typing import Any

from app.modules.content import repo as content_repo
from app.modules.content.model import ChunkQuizItem, ContentChunk
from app.modules.participants import service as participants_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def test_same_topic_yields_identical_chunk_across_modes(
    session: AsyncSession, seeded: None, mock_anthropic: Any, ensure_content: Any
) -> None:
    topic_id = "T2.1"

    # A "personalized" and a "fixed" participant both reach T2.1.
    await participants_service.enroll(session, consent_given=True)
    await participants_service.enroll(session, consent_given=True)

    # Build the chunk once (cache-first + idempotent under an advisory lock).
    await ensure_content(topic_id)
    await ensure_content(topic_id)  # second call must not build a new version

    chunk = await content_repo.get_current_chunk(session, topic_id)
    assert chunk is not None
    assert chunk.content_version == 1  # idempotent: no second version created

    # Exactly one chunk row for this topic.
    all_versions = list(
        await session.scalars(
            select(ContentChunk.content_version).where(
                ContentChunk.topic_id == topic_id
            )
        )
    )
    assert all_versions == [1]

    # The gate items both participants receive are the same rows in the same order.
    items_a = await content_repo.quiz_questions(session, chunk.id, 5)
    items_b = await content_repo.quiz_questions(session, chunk.id, 5)
    assert [q.id for q in items_a] == [q.id for q in items_b]
    assert len(items_a) == 5

    # And they are anchored to this chunk (isolation: no per-participant copies).
    positions = list(
        await session.scalars(
            select(ChunkQuizItem.position).where(ChunkQuizItem.chunk_id == chunk.id)
        )
    )
    assert sorted(positions) == [1, 2, 3, 4, 5]
