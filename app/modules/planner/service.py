"""Planner service (DOC_05 §2, §8).

Owns path creation and advancement. Mode dispatch happens here: ``fixed`` vs
``personalized`` — every other component is mode-agnostic. Once a path exists,
its mode is locked (creation is idempotent per participant+block).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.logging import log_event
from app.modules.participants.model import Participant
from app.modules.planner import blocks, fixed, personalized, repo
from app.modules.planner.model import LearningPath, PathStep
from app.modules.topics.model import Topic
from sqlalchemy.ext.asyncio import AsyncSession

VALID_MODES = ("personalized", "fixed")


class PlannerError(Exception):
    """Base class for planner errors (mapped to HTTP by the router)."""


class InvalidBlockError(PlannerError):
    """The requested block is not a defined study block."""


class InvalidModeError(PlannerError):
    """The requested mode is not 'personalized' or 'fixed'."""


class PathNotFoundError(PlannerError):
    """No path exists for the requested participant/block."""


@dataclass
class PathProgress:
    path: LearningPath
    current_step: PathStep | None
    steps: list[PathStep]
    total_topics: int
    passed_count: int

    @property
    def completion_pct(self) -> float:
        if self.total_topics == 0:
            return 0.0
        return round(100.0 * self.passed_count / self.total_topics, 1)


async def create_path(
    session: AsyncSession, participant: Participant, *, block: str, mode: str
) -> tuple[LearningPath, PathStep | None]:
    """Create a path (or return the existing one) and its current step.

    Idempotent per (participant, block); the existing path's mode wins — once
    created, mode is locked (DOC_05 §8).
    """
    if block not in blocks.VALID_BLOCKS:
        raise InvalidBlockError(block)
    if mode not in VALID_MODES:
        raise InvalidModeError(mode)

    existing = await repo.get_path(session, participant.id, block)
    if existing is not None:
        step = await advance_path(session, existing)
        return existing, step

    path = await repo.create_path(session, participant.id, block, mode)
    log_event("path_created", path_id=str(path.id), block=block, mode=mode)
    step = await advance_path(session, path)
    await _warm_up_content(session, block)
    return path, step


async def _warm_up_content(session: AsyncSession, block: str) -> None:
    """Pre-generate the first few upcoming chunks to hide LLM latency (DOC_06 §9).

    Uses the block's deterministic fixed order as the warm-up set regardless of
    mode; it's a best-effort background task, not the authoritative plan.
    """
    from app.config import get_settings
    from app.modules.content import service as content_service
    from app.modules.graph import service as graph_service

    count = get_settings().content_pregeneration_count
    if count <= 0:
        return
    graph = await graph_service.load_graph(session)
    topic_ids = fixed.block_order(graph, block)[:count]
    content_service.schedule_pregeneration(topic_ids)


async def advance_path(
    session: AsyncSession, path: LearningPath
) -> PathStep | None:
    """Return the active step, planning the next topic if the last one passed.

    Idempotent: if the current step isn't passed, it is returned unchanged (no
    re-plan). Returns None when the block is complete.
    """
    steps = await repo.steps_for(session, path.id)
    if steps and steps[-1].status != "passed":
        return steps[-1]

    topic, reasoning = await _plan_next(session, path)
    if topic is None:
        if path.completed_at is None:
            path.completed_at = datetime.now(UTC)
            await session.flush()
            log_event("path_completed", path_id=str(path.id), block=path.block)
        return None

    # Invariant: we only plan when all existing steps are passed, so the planned
    # topic has no step yet. Guard against a duplicate regardless.
    for step in steps:
        if step.topic_id == topic.id:
            return step

    new_step = await repo.create_step(
        session,
        path_id=path.id,
        topic_id=topic.id,
        step_index=len(steps),
        status="in_progress",
        planner_reasoning=reasoning,
    )
    log_event(
        "path_step_unlocked",
        path_id=str(path.id),
        step_index=new_step.step_index,
        topic_id=topic.id,
        mode=path.mode,
        has_reasoning=reasoning is not None,
    )
    # Warm this topic's content the moment its step unlocks so the lesson is ready
    # by the time the learner opens it (pre-generation only covers the first few).
    from app.modules.content import service as content_service

    content_service.schedule_pregeneration([topic.id])
    return new_step


async def _plan_next(
    session: AsyncSession, path: LearningPath
) -> tuple[Topic | None, str | None]:
    if path.mode == "fixed":
        return await fixed.next_topic(session, path)
    return await personalized.next_topic(session, path)


async def get_progress(
    session: AsyncSession, participant: Participant, block: str
) -> PathProgress:
    """Current path state for GET /paths/current (DOC_05 §8)."""
    if block not in blocks.VALID_BLOCKS:
        raise InvalidBlockError(block)
    path = await repo.get_path(session, participant.id, block)
    if path is None:
        raise PathNotFoundError(block)

    steps = await repo.steps_for(session, path.id)
    passed_count = sum(1 for s in steps if s.status == "passed")
    # Active step: the last non-passed step, if any.
    current = steps[-1] if steps and steps[-1].status != "passed" else None
    total_topics = len(blocks.allowed_topics(block))
    return PathProgress(
        path=path,
        current_step=current,
        steps=steps,
        total_topics=total_topics,
        passed_count=passed_count,
    )
