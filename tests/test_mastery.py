"""DOC_04 §6–§7 tests: mastery-module BKT, the diagnostic service, and the API.

The DOC lists the pure-BKT tests under ``tests/test_bkt.py``, but that file
already holds the DOC_00 ``eduverse.bkt`` tests; the app module's BKT
(``app.modules.mastery.bkt``) is a separate implementation, so its tests live
here alongside the service/endpoint tests.

The DB-backed tests need Postgres (see tests/conftest.py). The pure-math tests
are stdlib-only.
"""
from __future__ import annotations

import pytest
from app.modules.mastery import service
from app.modules.mastery.bkt import BKTParams, posterior, step
from app.modules.mastery.model import Mastery, Response
from app.modules.mastery.params import default_params
from app.modules.participants import service as participants_service
from app.modules.participants.model import Participant
from app.modules.questions.model import Question
from app.modules.topics.model import Topic
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

DEFAULTS = BKTParams()


# =========================================================================== #
# 1. Pure BKT math (DOC_04 §6, no DB)
# =========================================================================== #
def test_posterior_correct_closed_form() -> None:
    # defaults slip=0.10, guess=0.25: 0.5*0.9 / (0.5*0.9 + 0.5*0.25) = 0.45/0.575
    assert posterior(0.5, True, DEFAULTS) == pytest.approx(0.45 / 0.575, abs=1e-6)


def test_posterior_incorrect_closed_form() -> None:
    # 0.5*0.10 / (0.5*0.10 + 0.5*0.75) = 0.05/0.425
    assert posterior(0.5, False, DEFAULTS) == pytest.approx(0.05 / 0.425, abs=1e-6)


def test_step_is_monotonic_in_prior() -> None:
    priors = [i / 100 for i in range(1, 100)]
    corr = [step(p, True, DEFAULTS) for p in priors]
    incorr = [step(p, False, DEFAULTS) for p in priors]
    assert all(a < b for a, b in zip(corr, corr[1:], strict=False))
    assert all(a < b for a, b in zip(incorr, incorr[1:], strict=False))


def test_posterior_bounds_and_direction() -> None:
    # Sanity invariant under defaults: bounded in [0,1], and correct raises /
    # incorrect lowers the belief.
    for p in [i / 1000 for i in range(1, 1000)]:
        for correct in (True, False):
            post = posterior(p, correct, DEFAULTS)
            assert 0.0 <= post <= 1.0
            if correct:
                assert post >= p - 1e-12
            else:
                assert post <= p + 1e-12


def test_two_correct_beats_one() -> None:
    one = step(DEFAULTS.p_init, True, DEFAULTS)
    two = step(one, True, DEFAULTS)
    assert two > one


def test_step_returns_prior_on_degenerate_denominator() -> None:
    # A prior of 0 with an incorrect answer keeps den > 0, but a fully certain
    # correct/incorrect edge should never blow up.
    assert 0.0 <= step(0.0, False, DEFAULTS) <= 1.0
    assert 0.0 <= step(1.0, True, DEFAULTS) <= 1.0


# =========================================================================== #
# Helpers for the DB-backed tests
# =========================================================================== #
async def _enroll(session: AsyncSession) -> Participant:
    participant = await participants_service.enroll(session, consent_given=True)
    await session.commit()
    return participant


async def _diag_questions(session: AsyncSession) -> list[Question]:
    return list(
        await session.scalars(
            select(Question)
            .where(Question.is_diagnostic.is_(True))
            .order_by(Question.diagnostic_order)
            .options(selectinload(Question.choices))
        )
    )


def _correct_label(q: Question) -> str:
    return next(c.label for c in q.choices if c.is_correct)


async def _run_full_diagnostic(
    session: AsyncSession, participant: Participant, *, complete: bool
) -> None:
    diag = await service.start_diagnostic(session, participant)
    for q in await _diag_questions(session):
        await service.answer_diagnostic(
            session,
            participant,
            session_id=diag.id,
            question_id=q.id,
            selected_label=_correct_label(q),
            response_ms=1200,
        )
    if complete:
        await service.complete_diagnostic(session, participant)


async def _count(session: AsyncSession, model: type, **filters: object) -> int:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return await session.scalar(stmt) or 0


# =========================================================================== #
# 2. Mastery service (DOC_04 §6)
# =========================================================================== #
async def test_first_response_creates_one_row_per_tier_topic(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    q1 = (await _diag_questions(session))[0]  # order 1 -> T0.2, tier 0
    diag = await service.start_diagnostic(session, participant)
    await service.answer_diagnostic(
        session,
        participant,
        session_id=diag.id,
        question_id=q1.id,
        selected_label=_correct_label(q1),
        response_ms=None,
    )

    topic = await session.get(Topic, q1.topic_id)
    tier_topic_count = await _count(session, Topic, tier=topic.tier)
    mastery_count = await _count(session, Mastery, participant_id=participant.id)
    assert mastery_count == tier_topic_count  # anchor + tier-propagated siblings


async def test_full_diagnostic_covers_every_probed_tier(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    questions = await _diag_questions(session)
    await _run_full_diagnostic(session, participant, complete=False)

    probed_tiers = {(await session.get(Topic, q.topic_id)).tier for q in questions}
    mastered = set(
        await session.scalars(
            select(Mastery.topic_id).where(Mastery.participant_id == participant.id)
        )
    )
    for tier in probed_tiers:
        tier_topics = set(
            await session.scalars(select(Topic.id).where(Topic.tier == tier))
        )
        assert tier_topics <= mastered

    # T7 (async) is deliberately not probed -> absent until the floor runs.
    tier7 = set(await session.scalars(select(Topic.id).where(Topic.tier == 7)))
    assert tier7 and tier7.isdisjoint(mastered)


async def test_materialize_floor_fills_untouched_topics(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    await _run_full_diagnostic(session, participant, complete=False)

    added = await service.materialize_mastery_floor(session, participant.id)
    assert added > 0

    total_topics = await _count(session, Topic)
    assert await _count(session, Mastery, participant_id=participant.id) == total_topics

    p_init = default_params().p_init
    floored = list(
        await session.scalars(
            select(Mastery.p_mastered)
            .join(Topic, Topic.id == Mastery.topic_id)
            .where(Mastery.participant_id == participant.id, Topic.tier == 7)
        )
    )
    assert floored and all(abs(v - p_init) < 1e-6 for v in floored)


async def test_rerunning_diagnostic_is_blocked(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    await _run_full_diagnostic(session, participant, complete=True)
    with pytest.raises(service.DiagnosticAlreadyCompletedError):
        await service.start_diagnostic(session, participant)


async def test_out_of_order_answer_rejected(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    q2 = (await _diag_questions(session))[1]  # order 2, skipping order 1
    diag = await service.start_diagnostic(session, participant)
    with pytest.raises(service.OutOfOrderAnswerError):
        await service.answer_diagnostic(
            session,
            participant,
            session_id=diag.id,
            question_id=q2.id,
            selected_label=_correct_label(q2),
            response_ms=None,
        )


async def test_complete_before_finishing_is_rejected(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    await service.start_diagnostic(session, participant)
    with pytest.raises(service.DiagnosticIncompleteError):
        await service.complete_diagnostic(session, participant)


async def test_events_emitted_for_response_and_propagation(
    session: AsyncSession, seeded: None
) -> None:
    from structlog.testing import capture_logs

    participant = await _enroll(session)
    q1 = (await _diag_questions(session))[0]  # tier 0 (5 topics)
    diag = await service.start_diagnostic(session, participant)
    with capture_logs() as logs:
        await service.answer_diagnostic(
            session,
            participant,
            session_id=diag.id,
            question_id=q1.id,
            selected_label=_correct_label(q1),
            response_ms=4123,
        )

    recorded = [e for e in logs if e.get("event_type") == "response_recorded"]
    propagated = [e for e in logs if e.get("event_type") == "mastery_propagated"]
    assert len(recorded) == 1
    for field in (
        "participant_code",
        "question_id",
        "topic_id",
        "context",
        "selected_label",
        "is_correct",
        "prior",
        "posterior",
        "response_ms",
    ):
        assert field in recorded[0]
    # tier 0 has 5 topics -> 4 propagated updates (anchor excluded).
    assert len(propagated) == 4


# =========================================================================== #
# 3. Acceptance criteria via the API (DOC_04 §7)
# =========================================================================== #
async def test_diagnostic_end_to_end(
    client: AsyncClient, seeded: None, session: AsyncSession
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    headers = {"X-Participant-Code": code}

    start = await client.post("/diagnostic/start", headers=headers)
    assert start.status_code == 200
    started = start.json()
    session_id = started["session_id"]
    items = started["items"]
    assert started["items_answered"] == 0
    assert len(items) == 25
    assert [i["order"] for i in items] == list(range(1, 26))

    correct = {str(q.id): _correct_label(q) for q in await _diag_questions(session)}

    remaining = None
    for item in items:
        answer = await client.post(
            "/diagnostic/answer",
            headers=headers,
            json={
                "session_id": session_id,
                "question_id": item["id"],
                "selected_label": correct[item["id"]],
                "response_ms": 1500,
            },
        )
        assert answer.status_code == 200, answer.text
        payload = answer.json()
        assert payload["is_correct"] is True
        assert payload["explanation"]  # immediate feedback
        remaining = payload["items_remaining"]
    assert remaining == 0

    complete = await client.post("/diagnostic/complete", headers=headers)
    assert complete.status_code == 200
    vector = complete.json()
    assert vector["completed"] is True

    # Acceptance §7.1: a full mastery vector, one row per topic. DOC prose says
    # 48; the seeded catalog is 47 (DOC_02 made the topic table canonical).
    total_topics = await _count(session, Topic)
    assert len(vector["entries"]) == total_topics

    # §7.2: GET /mastery is stable and sorted.
    m1 = (await client.get("/mastery", headers=headers)).json()
    m2 = (await client.get("/mastery", headers=headers)).json()
    assert m1 == m2
    tiers = [e["tier"] for e in m1["entries"]]
    assert tiers == sorted(tiers)
    assert [e["topic_id"] for e in m1["entries"]] == [
        e["topic_id"] for e in vector["entries"]
    ]

    # §7.3: anchor topics move measurably off the prior.
    p_init = default_params().p_init
    by_topic = {e["topic_id"]: e for e in vector["entries"]}
    for anchor in ("T0.2", "T0.3", "T2.4", "T3.5", "T5.3", "T6.3"):
        assert abs(by_topic[anchor]["p_mastered"] - p_init) > 1e-6

    # §7.4: every response row carries prior/posterior provenance.
    pid = await session.scalar(select(Participant.id).where(Participant.code == code))
    responses = list(
        await session.scalars(select(Response).where(Response.participant_id == pid))
    )
    assert len(responses) == 25
    assert all(r.context == "diagnostic" for r in responses)
    assert all(
        r.prior_mastery is not None and r.posterior_mastery is not None
        for r in responses
    )


async def test_start_rejected_after_completion(
    client: AsyncClient, seeded: None, session: AsyncSession
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    headers = {"X-Participant-Code": code}

    start = (await client.post("/diagnostic/start", headers=headers)).json()
    correct = {str(q.id): _correct_label(q) for q in await _diag_questions(session)}
    for item in start["items"]:
        await client.post(
            "/diagnostic/answer",
            headers=headers,
            json={
                "session_id": start["session_id"],
                "question_id": item["id"],
                "selected_label": correct[item["id"]],
            },
        )
    assert (await client.post("/diagnostic/complete", headers=headers)).status_code == 200

    blocked = await client.post("/diagnostic/start", headers=headers)
    assert blocked.status_code == 409


async def test_answer_out_of_order_returns_422(
    client: AsyncClient, seeded: None, session: AsyncSession
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    headers = {"X-Participant-Code": code}
    start = (await client.post("/diagnostic/start", headers=headers)).json()
    second = next(i for i in start["items"] if i["order"] == 2)
    resp = await client.post(
        "/diagnostic/answer",
        headers=headers,
        json={
            "session_id": start["session_id"],
            "question_id": second["id"],
            "selected_label": "A",
        },
    )
    assert resp.status_code == 422


async def test_diagnostic_endpoints_require_participant(client: AsyncClient) -> None:
    assert (await client.post("/diagnostic/start")).status_code == 401
    assert (await client.get("/mastery")).status_code == 401
