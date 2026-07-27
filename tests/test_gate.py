"""DOC_05 §9 (gate) tests: mastery-threshold enforcement + path advancement.

All gate tests run fixed-mode paths (no Claude). Gate quiz items don't exist in
the seed bank (DOC_06 generates them), so each test inserts its own
non-diagnostic questions for the step's topic.
"""
from __future__ import annotations

import uuid

from app.modules.mastery import repo as mastery_repo
from app.modules.participants import service as participants_service
from app.modules.participants.model import Participant
from app.modules.planner import gate, service
from app.modules.planner import repo as planner_repo
from app.modules.questions.model import Choice, Question
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _enroll(session: AsyncSession) -> Participant:
    return await participants_service.enroll(session, consent_given=True)


async def _force_block_a_fixed(session: AsyncSession, code: str) -> None:
    """Force a via-API participant's block A onto fixed mode (Claude-free gate).

    DOC_08 §3 assigns mode server-side; the first enrollee's block A is
    personalized, which would invoke Claude. These gate tests care only about
    threshold enforcement, so we pin block A to fixed and commit for the client.
    """
    from app.modules.study.model import StudyAssignment

    pid = await session.scalar(select(Participant.id).where(Participant.code == code))
    assignment = await session.get(StudyAssignment, pid)
    assert assignment is not None
    assignment.block_a_mode = "fixed"
    assignment.block_b_mode = "personalized"
    await session.commit()


async def _make_gate_questions(
    session: AsyncSession, topic_id: str, n: int, *, correct: str = "A"
) -> list[uuid.UUID]:
    """Insert n non-diagnostic questions for a topic; return their ids."""
    ids: list[uuid.UUID] = []
    for i in range(n):
        question = Question(
            topic_id=topic_id,
            difficulty="easy",
            stem=f"gate item {topic_id} #{i}",
            explanation="because",
            is_diagnostic=False,
            source="test",
        )
        session.add(question)
        await session.flush()
        await session.refresh(question)
        for label in ("A", "B", "C", "D"):
            session.add(
                Choice(
                    question_id=question.id,
                    label=label,
                    text=f"choice {label}",
                    is_correct=(label == correct),
                )
            )
        ids.append(question.id)
    await session.flush()
    return ids


def _answers(ids: list[uuid.UUID], labels: list[str]) -> list[gate.GateAnswer]:
    return [
        gate.GateAnswer(question_id=qid, selected_label=label)
        for qid, label in zip(ids, labels, strict=True)
    ]


# --------------------------------------------------------------------------- #
# §9.1–§9.3
# --------------------------------------------------------------------------- #
async def test_gate_passes_from_moderate_prior(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    path, step = await service.create_path(
        session, participant, block="A", mode="fixed"
    )
    await mastery_repo.upsert_mastery(session, participant.id, step.topic_id, 0.6)
    ids = await _make_gate_questions(session, step.topic_id, 5, correct="A")

    attempt, items = await gate.start_attempt(session, step)
    assert len(items) == 5
    result = await gate.submit_attempt(
        session, participant, attempt, _answers(ids, ["A"] * 5)
    )

    assert result.passed is True
    assert result.score == 1.0
    assert result.posterior_at_gate >= gate.MASTERY_THRESHOLD
    assert step.status == "passed"
    assert result.next_step is not None  # path advanced


async def test_gate_fails_from_low_prior_and_increments_attempts(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    path, step = await service.create_path(
        session, participant, block="A", mode="fixed"
    )
    await mastery_repo.upsert_mastery(session, participant.id, step.topic_id, 0.5)
    ids = await _make_gate_questions(session, step.topic_id, 5, correct="A")

    attempt, _items = await gate.start_attempt(session, step)
    # 1 correct (A), 4 incorrect (B).
    result = await gate.submit_attempt(
        session, participant, attempt, _answers(ids, ["A", "B", "B", "B", "B"])
    )

    assert result.passed is False
    assert result.score == 0.2
    assert result.posterior_at_gate < gate.MASTERY_THRESHOLD
    assert step.status == "remediating"
    assert step.attempts == 1
    assert result.next_step is None  # did not advance


async def test_two_failed_gates_do_not_advance(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    path, step = await service.create_path(
        session, participant, block="A", mode="fixed"
    )
    await mastery_repo.upsert_mastery(session, participant.id, step.topic_id, 0.4)
    ids = await _make_gate_questions(session, step.topic_id, 5, correct="A")

    for _ in range(2):
        attempt, _items = await gate.start_attempt(session, step)
        result = await gate.submit_attempt(
            session, participant, attempt, _answers(ids, ["B"] * 5)
        )
        assert result.passed is False

    steps = await planner_repo.steps_for(session, path.id)
    assert len(steps) == 1  # never advanced past the failing step
    assert steps[0].attempts == 2
    assert steps[0].status == "remediating"


# --------------------------------------------------------------------------- #
# §9.4 — passing advances, reflected by GET /paths/current
# --------------------------------------------------------------------------- #
async def test_gate_pass_advances_via_api(
    client: AsyncClient, seeded: None, session: AsyncSession
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    headers = {"X-Participant-Code": code}
    await _force_block_a_fixed(session, code)

    created = (
        await client.post("/paths", headers=headers, json={"block": "A", "mode": "fixed"})
    ).json()
    step = created["current_step"]
    topic = step["topic_id"]

    # Seed a passing prior + gate items, committed so the client's sessions see them.
    pid = await session.scalar(select(Participant.id).where(Participant.code == code))
    await mastery_repo.upsert_mastery(session, pid, topic, 0.7)
    ids = await _make_gate_questions(session, topic, 5, correct="A")
    await session.commit()

    await client.post(f"/steps/{step['id']}/gate/start", headers=headers)
    submit = (
        await client.post(
            f"/steps/{step['id']}/gate/submit",
            headers=headers,
            json={"answers": [{"question_id": str(q), "selected_label": "A"} for q in ids]},
        )
    ).json()
    assert submit["passed"] is True
    assert submit["next_step"]["topic_id"] == "T2.2"  # next in block-A order

    current = (
        await client.get("/paths/current", params={"block": "A"}, headers=headers)
    ).json()
    assert current["current_step"]["topic_id"] == "T2.2"
    assert current["passed_count"] == 1
    assert current["completion_pct"] > 0.0


# --------------------------------------------------------------------------- #
# §9.5 — fixed-mode determinism across participants
# --------------------------------------------------------------------------- #
async def test_fixed_mode_identical_sequences_across_participants(
    session: AsyncSession, seeded: None
) -> None:
    from datetime import UTC, datetime

    sequences: list[list[str]] = []
    for _ in range(2):
        participant = await _enroll(session)
        path, step = await service.create_path(
            session, participant, block="A", mode="fixed"
        )
        sequence: list[str] = []
        while step is not None:
            sequence.append(step.topic_id)
            step.status = "passed"
            step.passed_at = datetime.now(UTC)
            await session.flush()
            step = await service.advance_path(session, path)
        sequences.append(sequence)

    assert sequences[0] == sequences[1]


async def test_gate_submit_requires_open_attempt(
    client: AsyncClient, seeded: None, session: AsyncSession
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    headers = {"X-Participant-Code": code}
    await _force_block_a_fixed(session, code)
    created = (
        await client.post("/paths", headers=headers, json={"block": "A", "mode": "fixed"})
    ).json()
    step_id = created["current_step"]["id"]

    # Submit without starting -> 409.
    resp = await client.post(
        f"/steps/{step_id}/gate/submit", headers=headers, json={"answers": []}
    )
    assert resp.status_code == 409


async def test_planner_endpoints_require_participant(client: AsyncClient) -> None:
    assert (await client.post("/paths", json={"block": "A", "mode": "fixed"})).status_code == 401
    assert (await client.get("/paths/current", params={"block": "A"})).status_code == 401
