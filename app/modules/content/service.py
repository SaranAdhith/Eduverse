"""Content-assembly service (DOC_06 §7-§10).

Owns the read paths for the content/preview endpoints, admin regeneration, and
the fire-and-forget pre-generation that hides LLM latency when a path is created
(DOC_06 §9).
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import structlog
from app.db import session_scope
from app.logging import log_event
from app.modules.content import assembler, repo
from app.modules.content.model import ContentChunk
from app.modules.curation.model import VideoSegment
from app.modules.graph import service as graph_service
from app.modules.topics.model import Topic
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger("content")

# Keep references to background pre-generation tasks so they are not GC'd
# mid-flight (asyncio only holds weak references).
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


class ContentError(Exception):
    """Base class for content-service errors (mapped to HTTP by the router)."""


class ChunkNotFoundError(ContentError):
    """No chunk exists yet for the requested topic/step."""


@dataclass
class StepContent:
    chunk: ContentChunk
    topic: Topic
    prerequisite_ids: list[str]
    segment: VideoSegment | None


async def _resolve_step_topic(
    session: AsyncSession, step_id: uuid.UUID
) -> str | None:
    """The topic id for a path step, or None if the step doesn't exist."""
    from app.modules.planner import repo as planner_repo

    step = await planner_repo.get_step(session, step_id)
    return step.topic_id if step is not None else None


async def _load_step_content(
    session: AsyncSession, topic_id: str, chunk: ContentChunk
) -> StepContent:
    graph = await graph_service.load_graph(session)
    prerequisite_ids = sorted(graph.edges.get(topic_id, set()))
    topic = graph.nodes[topic_id]
    segment = (
        await repo.load_segment(session, chunk.video_segment_id)
        if chunk.video_segment_id is not None
        else None
    )
    return StepContent(
        chunk=chunk,
        topic=topic,
        prerequisite_ids=prerequisite_ids,
        segment=segment,
    )


async def get_step_content(
    session: AsyncSession, step_id: uuid.UUID
) -> StepContent:
    """Assembled chunk for a step's topic (DOC_06 §10). 404 if not assembled yet."""
    topic_id = await _resolve_step_topic(session, step_id)
    if topic_id is None:
        raise ChunkNotFoundError(f"step {step_id} not found")
    chunk = await repo.get_current_chunk(session, topic_id)
    if chunk is None:
        raise ChunkNotFoundError(f"no content chunk for step {step_id}")
    return await _load_step_content(session, topic_id, chunk)


async def get_preview(session: AsyncSession, topic_id: str) -> ContentChunk:
    """The current chunk for a topic (admin preview). 404 if not assembled."""
    chunk = await repo.get_current_chunk(session, topic_id)
    if chunk is None:
        raise ChunkNotFoundError(f"no content chunk for topic {topic_id}")
    return chunk


async def regenerate(session: AsyncSession, topic_id: str) -> ContentChunk:
    """Bump content_version and assemble a fresh chunk (DOC_06 §1, §10).

    Old participants keep the chunk they were served; new requests get the new
    version. Never overwrites in place.
    """
    chunk = await assembler.build(session, topic_id, force_new_version=True)
    log_event(
        "content_regenerated", topic_id=topic_id, content_version=chunk.content_version
    )
    return chunk


# --------------------------------------------------------------------------- #
# Pre-generation (DOC_06 §9)
# --------------------------------------------------------------------------- #
async def _pregenerate_one(topic_id: str) -> None:
    async for session in session_scope():
        await assembler.build(session, topic_id)


async def _pregenerate(topic_ids: list[str]) -> None:
    for topic_id in topic_ids:
        try:
            await _pregenerate_one(topic_id)
        except Exception as exc:  # noqa: BLE001 — warm-up is best-effort
            log.warning("pregeneration_failed", topic_id=topic_id, error=str(exc))
    log_event("content_pregeneration_complete", topics=len(topic_ids))


def schedule_pregeneration(topic_ids: list[str]) -> None:
    """Fire-and-forget warm-up of upcoming chunks (DOC_06 §9)."""
    if not topic_ids:
        return
    task = asyncio.create_task(_pregenerate(topic_ids))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def drain_pregeneration() -> None:
    """Await any in-flight pre-generation tasks (used by tests)."""
    tasks = list(_BACKGROUND_TASKS)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
