"""Async DB queries backing the planner + gate (DOC_05)."""
from __future__ import annotations

import uuid

from app.modules.mastery.model import Mastery
from app.modules.planner.model import GateAttempt, LearningPath, PathStep
from app.modules.questions.model import Question
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


# --- learning paths -------------------------------------------------------- #
async def get_path(
    session: AsyncSession, participant_id: uuid.UUID, block: str
) -> LearningPath | None:
    path: LearningPath | None = await session.scalar(
        select(LearningPath).where(
            LearningPath.participant_id == participant_id,
            LearningPath.block == block,
        )
    )
    return path


async def get_path_by_id(
    session: AsyncSession, path_id: uuid.UUID
) -> LearningPath | None:
    return await session.get(LearningPath, path_id)


async def create_path(
    session: AsyncSession, participant_id: uuid.UUID, block: str, mode: str
) -> LearningPath:
    path = LearningPath(participant_id=participant_id, block=block, mode=mode)
    session.add(path)
    await session.flush()
    await session.refresh(path)
    return path


# --- path steps ------------------------------------------------------------ #
async def steps_for(session: AsyncSession, path_id: uuid.UUID) -> list[PathStep]:
    result = await session.scalars(
        select(PathStep)
        .where(PathStep.path_id == path_id)
        .order_by(PathStep.step_index)
    )
    return list(result.all())


async def passed_topic_ids(session: AsyncSession, path_id: uuid.UUID) -> set[str]:
    result = await session.scalars(
        select(PathStep.topic_id).where(
            PathStep.path_id == path_id, PathStep.status == "passed"
        )
    )
    return set(result.all())


async def get_step(session: AsyncSession, step_id: uuid.UUID) -> PathStep | None:
    return await session.get(PathStep, step_id)


async def create_step(
    session: AsyncSession,
    *,
    path_id: uuid.UUID,
    topic_id: str,
    step_index: int,
    status: str,
    planner_reasoning: str | None,
) -> PathStep:
    step = PathStep(
        path_id=path_id,
        topic_id=topic_id,
        step_index=step_index,
        status=status,
        planner_reasoning=planner_reasoning,
    )
    session.add(step)
    await session.flush()
    await session.refresh(step)
    return step


# --- mastery (read-only view for the planner) ------------------------------ #
async def mastery_map(
    session: AsyncSession, participant_id: uuid.UUID
) -> dict[str, float]:
    """topic_id -> p_mastered for a participant (Core read, no ORM entities)."""
    result = await session.execute(
        select(Mastery.topic_id, Mastery.p_mastered).where(
            Mastery.participant_id == participant_id
        )
    )
    return {topic_id: p for topic_id, p in result.all()}


# --- gate attempts + items ------------------------------------------------- #
async def create_attempt(
    session: AsyncSession, path_step_id: uuid.UUID
) -> GateAttempt:
    attempt = GateAttempt(path_step_id=path_step_id)
    session.add(attempt)
    await session.flush()
    await session.refresh(attempt)
    return attempt


async def get_attempt(
    session: AsyncSession, attempt_id: uuid.UUID
) -> GateAttempt | None:
    return await session.get(GateAttempt, attempt_id)


async def latest_open_attempt(
    session: AsyncSession, path_step_id: uuid.UUID
) -> GateAttempt | None:
    """The most recent not-yet-submitted attempt for a step, if any."""
    attempt: GateAttempt | None = await session.scalar(
        select(GateAttempt)
        .where(
            GateAttempt.path_step_id == path_step_id,
            GateAttempt.completed_at.is_(None),
        )
        .order_by(GateAttempt.started_at.desc())
        .limit(1)
    )
    return attempt


async def gate_items(
    session: AsyncSession, topic_id: str, limit: int
) -> list[Question]:
    """The gate quiz for a topic (DOC_06 §8).

    Prefers the assembled chunk's ``chunk_quiz_items`` (ordered by position). Falls
    back to any non-diagnostic questions for the topic when no chunk exists yet,
    so gate tests can seed their own items without an assembled chunk.
    """
    from app.modules.content import repo as content_repo

    chunk = await content_repo.get_current_chunk(session, topic_id)
    if chunk is not None:
        items = await content_repo.quiz_questions(session, chunk.id, limit)
        if items:
            return items

    result = await session.scalars(
        select(Question)
        .where(Question.topic_id == topic_id, Question.is_diagnostic.is_(False))
        .order_by(Question.created_at, Question.id)
        .limit(limit)
        .options(selectinload(Question.choices))
    )
    return list(result.all())
