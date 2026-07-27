"""Async DB queries backing the mastery module (DOC_04 §2.3)."""
from __future__ import annotations

import uuid

from app.modules.mastery.model import DiagnosticSession, Mastery, Response
from app.modules.questions.model import Question
from app.modules.topics.model import Topic
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


# --- diagnostic sessions --------------------------------------------------- #
async def get_diagnostic_session(
    session: AsyncSession, participant_id: uuid.UUID
) -> DiagnosticSession | None:
    row: DiagnosticSession | None = await session.scalar(
        select(DiagnosticSession).where(
            DiagnosticSession.participant_id == participant_id
        )
    )
    return row


async def create_diagnostic_session(
    session: AsyncSession, participant_id: uuid.UUID
) -> DiagnosticSession:
    row = DiagnosticSession(participant_id=participant_id)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


# --- questions ------------------------------------------------------------- #
async def get_question(
    session: AsyncSession, question_id: uuid.UUID
) -> Question | None:
    """Load a question with its choices (needed to score the answer)."""
    question: Question | None = await session.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.choices))
    )
    return question


# --- mastery vector -------------------------------------------------------- #
async def get_p_mastered(
    session: AsyncSession, participant_id: uuid.UUID, topic_id: str
) -> float | None:
    """Current mastery probability for a topic, or ``None`` if no row yet.

    A Core scalar read (not an ORM entity) so it always reflects the latest
    value written this transaction — the update path issues raw upserts, and we
    must not read a stale identity-mapped instance back when many topics are
    updated within one session.
    """
    p_mastered: float | None = await session.scalar(
        select(Mastery.p_mastered).where(
            Mastery.participant_id == participant_id, Mastery.topic_id == topic_id
        )
    )
    return p_mastered


async def upsert_mastery(
    session: AsyncSession,
    participant_id: uuid.UUID,
    topic_id: str,
    p_mastered: float,
) -> None:
    """Set a topic's mastery and bump its attempt counter (one BKT update)."""
    stmt = pg_insert(Mastery).values(
        participant_id=participant_id,
        topic_id=topic_id,
        p_mastered=p_mastered,
        attempts=1,
        last_updated_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Mastery.participant_id, Mastery.topic_id],
        set_={
            "p_mastered": p_mastered,
            "attempts": Mastery.attempts + 1,
            "last_updated_at": func.now(),
        },
    )
    await session.execute(stmt)


async def insert_missing_mastery(
    session: AsyncSession,
    participant_id: uuid.UUID,
    rows: list[tuple[str, float]],
) -> None:
    """Insert (topic_id, p_init) floor rows, leaving any existing rows untouched."""
    if not rows:
        return
    stmt = pg_insert(Mastery).values(
        [
            {
                "participant_id": participant_id,
                "topic_id": topic_id,
                "p_mastered": p_init,
                "attempts": 0,
            }
            for topic_id, p_init in rows
        ]
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[Mastery.participant_id, Mastery.topic_id]
    )
    await session.execute(stmt)


async def mastery_vector(
    session: AsyncSession, participant_id: uuid.UUID
) -> list[tuple[Mastery, Topic]]:
    """The participant's mastery rows joined with topic metadata, sorted."""
    result = await session.execute(
        select(Mastery, Topic)
        .join(Topic, Topic.id == Mastery.topic_id)
        .where(Mastery.participant_id == participant_id)
        .order_by(Topic.tier, Topic.display_order, Topic.id)
        # Refresh any identity-mapped rows so the vector reflects this txn's writes.
        .execution_options(populate_existing=True)
    )
    return [(m, t) for m, t in result.all()]


async def existing_mastery_topic_ids(
    session: AsyncSession, participant_id: uuid.UUID
) -> set[str]:
    result = await session.scalars(
        select(Mastery.topic_id).where(Mastery.participant_id == participant_id)
    )
    return set(result.all())


# --- topics ---------------------------------------------------------------- #
async def topics_in_tier(session: AsyncSession, tier: int) -> list[Topic]:
    result = await session.scalars(
        select(Topic).where(Topic.tier == tier).order_by(Topic.display_order, Topic.id)
    )
    return list(result.all())


async def all_topics(session: AsyncSession) -> list[Topic]:
    result = await session.scalars(
        select(Topic).order_by(Topic.tier, Topic.display_order, Topic.id)
    )
    return list(result.all())


# --- responses ------------------------------------------------------------- #
async def insert_response(
    session: AsyncSession,
    *,
    participant_id: uuid.UUID,
    question_id: uuid.UUID,
    topic_id: str,
    context: str,
    selected_label: str,
    is_correct: bool,
    response_ms: int | None,
    prior_mastery: float,
    posterior_mastery: float,
) -> Response:
    response = Response(
        participant_id=participant_id,
        question_id=question_id,
        topic_id=topic_id,
        context=context,
        selected_label=selected_label,
        is_correct=is_correct,
        response_ms=response_ms,
        prior_mastery=prior_mastery,
        posterior_mastery=posterior_mastery,
    )
    session.add(response)
    await session.flush()
    await session.refresh(response)
    return response
