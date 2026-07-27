"""Mastery gate (DOC_05 §3, §7).

Owns the canonical mastery threshold and the gate-attempt lifecycle. A gate
scores a short quiz for a step's topic, feeds every answer through the BKT
update (``context='gate'``), and passes the step iff the resulting posterior
clears the threshold.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.logging import log_event
from app.modules.mastery import repo as mastery_repo
from app.modules.mastery import service as mastery_service
from app.modules.mastery.params import params_for
from app.modules.participants.model import Participant
from app.modules.planner import repo
from app.modules.planner.model import GateAttempt, PathStep
from app.modules.questions.model import Question
from sqlalchemy.ext.asyncio import AsyncSession

# DOC_05 §3: the posterior a topic must reach for its gate to pass. Defined once
# here and imported everywhere it is needed (personalized planner, gate).
# 0.85 — Corbett & Anderson's 0.95 is too tight given default-parameter noise.
MASTERY_THRESHOLD = 0.85

# DOC_05 §7: a gate quiz is 5 items (DOC_06 generates them).
GATE_ITEM_COUNT = 5


@dataclass(frozen=True)
class GateAnswer:
    question_id: uuid.UUID
    selected_label: str
    response_ms: int | None = None


@dataclass
class GateResult:
    passed: bool
    score: float
    posterior_at_gate: float
    step: PathStep
    next_step: PathStep | None  # the newly unlocked step, if this gate passed


class GateError(Exception):
    """Base class for gate errors (mapped to HTTP by the router)."""


class AttemptNotFoundError(GateError):
    """The gate attempt id does not resolve."""


class AttemptAlreadyCompletedError(GateError):
    """The gate attempt has already been submitted."""


async def start_attempt(
    session: AsyncSession, step: PathStep
) -> tuple[GateAttempt, list[Question]]:
    """Open a gate attempt for a step and return its quiz items."""
    if step.status in ("pending", "remediating"):
        step.status = "in_progress"
    attempt = await repo.create_attempt(session, step.id)
    items = await repo.gate_items(session, step.topic_id, GATE_ITEM_COUNT)
    log_event(
        "gate_attempt_started",
        path_step_id=str(step.id),
        topic_id=step.topic_id,
        attempt_id=str(attempt.id),
        item_count=len(items),
    )
    return attempt, items


async def submit_attempt(
    session: AsyncSession,
    participant: Participant,
    attempt: GateAttempt,
    answers: list[GateAnswer],
) -> GateResult:
    """Score a gate attempt, update mastery, and pass/fail the step (DOC_05 §7)."""
    if attempt.completed_at is not None:
        raise AttemptAlreadyCompletedError(str(attempt.id))

    step = await repo.get_step(session, attempt.path_step_id)
    if step is None:  # pragma: no cover — FK guarantees the step exists
        raise AttemptNotFoundError(str(attempt.path_step_id))

    # BKT updates response-by-response, exactly as the diagnostic does.
    correct = 0
    for answer in answers:
        response = await mastery_service.record_response(
            session,
            participant,
            question_id=answer.question_id,
            selected_label=answer.selected_label,
            response_ms=answer.response_ms,
            context="gate",
        )
        if response.is_correct:
            correct += 1

    total = len(answers)
    score = correct / total if total else 0.0

    posterior = await mastery_repo.get_p_mastered(session, participant.id, step.topic_id)
    if posterior is None:
        posterior = params_for(step.topic_id).p_init
    passed = posterior >= MASTERY_THRESHOLD

    now = datetime.now(UTC)
    attempt.score = score
    attempt.passed = passed
    attempt.posterior_at_gate = posterior
    attempt.completed_at = now

    next_step: PathStep | None = None
    if passed:
        step.status = "passed"
        step.passed_at = now
        await session.flush()
        # Advance the path — plan the next topic (lazy import breaks the cycle
        # planner.service -> planner.personalized -> planner.gate).
        from app.modules.planner import service as planner_service

        path = await repo.get_path_by_id(session, step.path_id)
        if path is not None:
            next_step = await planner_service.advance_path(session, path)
    else:
        step.status = "remediating"
        step.attempts += 1
        await session.flush()

    log_event(
        "gate_attempt_completed",
        participant_code=participant.code,
        path_step_id=str(step.id),
        topic_id=step.topic_id,
        attempt_id=str(attempt.id),
        score=score,
        passed=passed,
        posterior_at_gate=posterior,
        attempts=step.attempts,
    )
    return GateResult(
        passed=passed,
        score=score,
        posterior_at_gate=posterior,
        step=step,
        next_step=next_step,
    )
