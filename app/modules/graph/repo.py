"""Async DB queries backing the graph module (DOC_02 §4)."""
from __future__ import annotations

from app.modules.topics.model import Topic, TopicPrerequisite
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def fetch_topics(session: AsyncSession) -> list[Topic]:
    """All topics, ordered deterministically by (tier, display_order, id)."""
    result = await session.scalars(
        select(Topic).order_by(Topic.tier, Topic.display_order, Topic.id)
    )
    topics = list(result.all())
    # Detach so the returned objects (and any app-state cache) stay usable after
    # the session closes; only column attributes are accessed downstream.
    for topic in topics:
        session.expunge(topic)
    return topics


async def fetch_edges(session: AsyncSession) -> list[tuple[str, str]]:
    """All (topic_id, prereq_id) prerequisite edges."""
    result = await session.execute(
        select(TopicPrerequisite.topic_id, TopicPrerequisite.prereq_id)
    )
    return [(row.topic_id, row.prereq_id) for row in result.all()]
