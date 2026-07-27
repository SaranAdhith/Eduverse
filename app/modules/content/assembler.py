"""Chunk assembler (DOC_06 §7): the orchestrator.

``build`` is the single entry point. It is cache-first and idempotent: a chunk
that already exists for ``(topic_id, current_content_version)`` is returned
untouched, and concurrent builds for the same topic are serialized by a Postgres
advisory lock so exactly one chunk is ever produced.
"""
from __future__ import annotations

from typing import Any

import anthropic
from app.config import get_settings
from app.logging import log_event
from app.modules.content import lesson, quiz, repo, select_video
from app.modules.content.model import ContentChunk
from app.modules.graph import service as graph_service
from app.modules.topics.model import Topic
from sqlalchemy.ext.asyncio import AsyncSession


def _get_client() -> Any:
    """The Anthropic async client (indirection lets tests inject a fake).

    With no API key configured, falls back to the deterministic offline
    synthesizer so the platform is fully walkable keyless. Otherwise wrapped with
    the DOC_08 §8 replay cache so identical prompts are served from ``llm_cache``.
    """
    settings = get_settings()
    # Tests inject their own doubles and rely on keyless pre-generation no-op'ing,
    # so the offline synthesizer is only used outside the test environment.
    if not settings.anthropic_api_key and settings.env != "test":
        from app.offline_llm import OfflineAnthropic

        return OfflineAnthropic()
    client: Any = anthropic.AsyncAnthropic()
    if settings.llm_cache_enabled:
        from app.modules.study import llm_cache

        return llm_cache.wrap(client)
    return client


async def _prerequisite_topics(session: AsyncSession, topic_id: str) -> list[Topic]:
    graph = await graph_service.load_graph(session)
    prereq_ids = graph.edges.get(topic_id, set())
    return [graph.nodes[p] for p in sorted(prereq_ids) if p in graph.nodes]


async def build(
    session: AsyncSession, topic_id: str, *, force_new_version: bool = False
) -> ContentChunk:
    """Return the cached chunk for a topic, or assemble and persist a new one.

    With ``force_new_version`` (admin regeneration, DOC_06 §1/§10), a fresh chunk
    is built at ``current_version + 1`` instead of returning the cached one — old
    participants keep what they had, new requests get the new version.
    """
    version = await repo.current_version(session, topic_id)
    existing = await repo.get_chunk(session, topic_id, version)

    # DOC_06 §7.1: cache before anything else.
    if existing is not None and not force_new_version:
        return existing

    target_version = version + 1 if (existing is not None and force_new_version) else version

    # DOC_06 §7: serialize concurrent builds; re-check the cache once locked so a
    # racing builder that already committed wins and we never double-generate.
    await repo.acquire_topic_lock(session, topic_id)
    locked = await repo.get_chunk(session, topic_id, target_version)
    if locked is not None:
        return locked

    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise ValueError(f"unknown topic {topic_id!r}")

    client = _get_client()
    settings = get_settings()
    segment = await select_video.choose(session, topic_id)
    prerequisite_topics = await _prerequisite_topics(session, topic_id)
    fallback = segment is None

    lesson_model = (
        settings.anthropic_model_reasoning if fallback else settings.anthropic_model_fast
    )
    lesson_markdown = await lesson.generate(
        client,
        topic=topic,
        video_segment=segment,
        prerequisite_topics=prerequisite_topics,
        model=lesson_model,
    )
    quiz_items = await quiz.generate(
        client,
        topic=topic,
        lesson_markdown=lesson_markdown,
        video_segment=segment,
        model=settings.anthropic_model_fast,
    )

    chunk = await repo.create_chunk(
        session,
        topic_id=topic_id,
        content_version=target_version,
        video_segment_id=segment.id if segment is not None else None,
        lesson_markdown=lesson_markdown,
        fallback=fallback,
        quiz_items=quiz_items,
    )
    log_event(
        "content_chunk_assembled",
        topic_id=topic_id,
        content_version=target_version,
        fallback=fallback,
        video_segment_id=str(segment.id) if segment is not None else None,
        quiz_item_count=len(quiz_items),
    )
    return chunk
