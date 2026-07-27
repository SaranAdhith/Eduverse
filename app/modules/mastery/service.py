"""Mastery service (DOC_04 §2.3, §3, §4).

Orchestrates the diagnostic: session lifecycle, response recording, the BKT
update, and the DOC_00 §4 tier-propagation rule. All BKT math is delegated to
:mod:`app.modules.mastery.bkt` — the single source of truth.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.logging import log_event
from app.modules.mastery import bkt, repo
from app.modules.mastery.model import DiagnosticSession, Mastery, Response
from app.modules.mastery.params import params_for
from app.modules.participants.model import Participant
from app.modules.questions.model import Question
from app.modules.topics.model import Topic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# The diagnostic is exactly the questions flagged ``is_diagnostic`` (DOC_02),
# served in ``diagnostic_order`` 1..N. Computed from the DB, not hard-coded.
CONTEXT_DIAGNOSTIC = "diagnostic"


class MasteryError(Exception):
    """Base class for mastery-service errors (mapped to HTTP by the router)."""


class DiagnosticAlreadyCompletedError(MasteryError):
    """Start/answer attempted on an already-completed diagnostic."""


class DiagnosticNotStartedError(MasteryError):
    """Answer/complete attempted before the diagnostic was started."""


class SessionMismatchError(MasteryError):
    """The supplied session id does not belong to this participant."""


class QuestionNotFoundError(MasteryError):
    """The question id does not resolve to a question."""


class NotADiagnosticItemError(MasteryError):
    """The question is not part of the diagnostic set."""


class InvalidChoiceError(MasteryError):
    """The selected label is not one of the question's choices."""


class OutOfOrderAnswerError(MasteryError):
    """The answered item is not the next expected diagnostic item."""


class DiagnosticIncompleteError(MasteryError):
    """Complete attempted before all diagnostic items were answered."""


async def diagnostic_item_count(session: AsyncSession) -> int:
    """How many items the diagnostic has (25 in the seeded study bank)."""
    total = await session.scalar(
        select(func.count()).select_from(Question).where(Question.is_diagnostic.is_(True))
    )
    return total or 0


# --------------------------------------------------------------------------- #
# Session lifecycle
# --------------------------------------------------------------------------- #
async def start_diagnostic(
    session: AsyncSession, participant: Participant
) -> DiagnosticSession:
    """Create the participant's diagnostic session, or resume an in-progress one.

    Rejects if the participant has already completed the diagnostic (DOC_04 §2.4).
    """
    existing = await repo.get_diagnostic_session(session, participant.id)
    if existing is not None:
        if existing.completed_at is not None:
            raise DiagnosticAlreadyCompletedError(participant.code)
        return existing
    diag = await repo.create_diagnostic_session(session, participant.id)
    log_event(
        "diagnostic_started",
        participant_code=participant.code,
        session_id=str(diag.id),
    )
    return diag


async def _load_session(
    session: AsyncSession, participant: Participant, session_id: uuid.UUID
) -> DiagnosticSession:
    diag = await repo.get_diagnostic_session(session, participant.id)
    if diag is None:
        raise DiagnosticNotStartedError(participant.code)
    if diag.id != session_id:
        raise SessionMismatchError(str(session_id))
    return diag


# --------------------------------------------------------------------------- #
# Response recording + BKT (DOC_04 §2.3)
# --------------------------------------------------------------------------- #
async def record_response(
    session: AsyncSession,
    participant: Participant,
    *,
    question_id: uuid.UUID,
    selected_label: str,
    response_ms: int | None,
    context: str,
) -> Response:
    """Score one answer, run the BKT step, and persist the response + mastery.

    Fetches the current ``p_mastered`` (defaulting to ``p_init`` on cold start),
    snapshots it as ``prior_mastery``, computes ``posterior_mastery`` via
    ``bkt.step``, writes the ``responses`` row with both snapshots, and upserts
    ``mastery``.
    """
    question = await repo.get_question(session, question_id)
    if question is None:
        raise QuestionNotFoundError(str(question_id))

    choice = next((c for c in question.choices if c.label == selected_label), None)
    if choice is None:
        raise InvalidChoiceError(selected_label)
    is_correct = choice.is_correct

    topic_id = question.topic_id
    params = params_for(topic_id)
    prior = await repo.get_p_mastered(session, participant.id, topic_id)
    if prior is None:
        prior = params.p_init
    posterior = bkt.step(prior, is_correct, params)

    response = await repo.insert_response(
        session,
        participant_id=participant.id,
        question_id=question_id,
        topic_id=topic_id,
        context=context,
        selected_label=selected_label,
        is_correct=is_correct,
        response_ms=response_ms,
        prior_mastery=prior,
        posterior_mastery=posterior,
    )
    await repo.upsert_mastery(session, participant.id, topic_id, posterior)

    log_event(
        "response_recorded",
        participant_code=participant.code,
        question_id=str(question_id),
        topic_id=topic_id,
        context=context,
        selected_label=selected_label,
        is_correct=is_correct,
        prior=prior,
        posterior=posterior,
        response_ms=response_ms,
    )
    return response


async def apply_diagnostic_tier_update(
    session: AsyncSession, participant: Participant, response: Response
) -> list[Topic]:
    """Propagate a diagnostic response to every *other* topic in its tier.

    DOC_00 §4: at diagnostic time the anchor stands in for its whole tier, so the
    same ``bkt.step`` is applied to each sibling topic's belief. Only mastery is
    modified — no extra ``responses`` rows are written; provenance for the
    propagated updates lives in the event log (DOC_04 §2.3).
    """
    if response.context != CONTEXT_DIAGNOSTIC:
        return []

    anchor = await session.get(Topic, response.topic_id)
    if anchor is None:  # pragma: no cover — FK guarantees the topic exists
        return []

    updated: list[Topic] = []
    for topic in await repo.topics_in_tier(session, anchor.tier):
        if topic.id == response.topic_id:
            continue  # the direct response already updated the anchor
        params = params_for(topic.id)
        prior = await repo.get_p_mastered(session, participant.id, topic.id)
        if prior is None:
            prior = params.p_init
        posterior = bkt.step(prior, response.is_correct, params)
        await repo.upsert_mastery(session, participant.id, topic.id, posterior)
        log_event(
            "mastery_propagated",
            participant_code=participant.code,
            anchor_topic_id=response.topic_id,
            topic_id=topic.id,
            tier=anchor.tier,
            context=CONTEXT_DIAGNOSTIC,
            is_correct=response.is_correct,
            prior=prior,
            posterior=posterior,
        )
        updated.append(topic)
    return updated


# --------------------------------------------------------------------------- #
# Answer orchestration (DOC_04 §2.4, §3)
# --------------------------------------------------------------------------- #
async def answer_diagnostic(
    session: AsyncSession,
    participant: Participant,
    *,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    selected_label: str,
    response_ms: int | None,
) -> tuple[Response, Question, int]:
    """Validate ordering, record the response, propagate tier updates.

    Returns ``(response, question, items_remaining)``. Ordering is a controlled
    variable: items must be answered in ``diagnostic_order`` with no skipping
    (DOC_04 §3).
    """
    diag = await _load_session(session, participant, session_id)
    if diag.completed_at is not None:
        raise DiagnosticAlreadyCompletedError(participant.code)

    question = await repo.get_question(session, question_id)
    if question is None:
        raise QuestionNotFoundError(str(question_id))
    if not question.is_diagnostic or question.diagnostic_order is None:
        raise NotADiagnosticItemError(str(question_id))

    # No skipping: the answered item must be exactly the next one in order.
    expected_order = diag.items_answered + 1
    if question.diagnostic_order != expected_order:
        raise OutOfOrderAnswerError(
            f"expected diagnostic_order {expected_order}, "
            f"got {question.diagnostic_order}"
        )

    response = await record_response(
        session,
        participant,
        question_id=question_id,
        selected_label=selected_label,
        response_ms=response_ms,
        context=CONTEXT_DIAGNOSTIC,
    )
    await apply_diagnostic_tier_update(session, participant, response)

    diag.items_answered += 1
    await session.flush()

    total = await diagnostic_item_count(session)
    items_remaining = total - diag.items_answered
    return response, question, items_remaining


async def complete_diagnostic(
    session: AsyncSession, participant: Participant
) -> DiagnosticSession:
    """Finalize the diagnostic once all items are answered (DOC_04 §2.4)."""
    diag = await repo.get_diagnostic_session(session, participant.id)
    if diag is None:
        raise DiagnosticNotStartedError(participant.code)
    if diag.completed_at is not None:
        return diag  # idempotent

    total = await diagnostic_item_count(session)
    if diag.items_answered < total:
        raise DiagnosticIncompleteError(
            f"answered {diag.items_answered}/{total} items"
        )

    await materialize_mastery_floor(session, participant.id)
    diag.completed_at = datetime.now(UTC)
    await session.flush()
    log_event(
        "diagnostic_completed",
        participant_code=participant.code,
        session_id=str(diag.id),
        items_answered=diag.items_answered,
    )
    return diag


# --------------------------------------------------------------------------- #
# Cold-start floor (DOC_04 §4)
# --------------------------------------------------------------------------- #
async def materialize_mastery_floor(
    session: AsyncSession, participant_id: uuid.UUID
) -> int:
    """Ensure every topic has a mastery row, inserting ``p_init`` for untouched ones.

    Makes mastery queries downstream join-safe. Returns the number of rows added.
    """
    existing = await repo.existing_mastery_topic_ids(session, participant_id)
    missing = [
        (topic.id, params_for(topic.id).p_init)
        for topic in await repo.all_topics(session)
        if topic.id not in existing
    ]
    await repo.insert_missing_mastery(session, participant_id, missing)
    return len(missing)


async def get_mastery_vector(
    session: AsyncSession, participant: Participant
) -> list[tuple[Mastery, Topic]]:
    """The participant's mastery rows joined with topic metadata, sorted."""
    return await repo.mastery_vector(session, participant.id)
