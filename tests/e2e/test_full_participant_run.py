"""The single most important test: one participant, both blocks, both modes.

Full diagnostic, path creation with pre-generation, every gate including a
deliberate fail-then-pass, to block completion — asserting the DB + event state
at each seam (DOC_09 §2.1).
"""
from __future__ import annotations

import uuid
from typing import Any

from app.modules.content.model import ContentChunk
from app.modules.content.service import drain_pregeneration
from app.modules.graph import service as graph_service
from app.modules.mastery.model import Mastery
from app.modules.participants.model import Participant
from app.modules.planner import fixed
from app.modules.planner.gate import MASTERY_THRESHOLD
from app.modules.planner.model import LearningPath, PathStep
from app.modules.questions.model import Choice
from app.modules.study import events
from app.modules.study.model import Event, StudyAssignment
from app.modules.topics.model import Topic
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


# --------------------------------------------------------------------------- #
# Small DB helpers (the test knows answer keys; participants never see them)
# --------------------------------------------------------------------------- #
async def _pid(session: AsyncSession, code: str) -> uuid.UUID:
    pid = await session.scalar(select(Participant.id).where(Participant.code == code))
    assert pid is not None
    return pid


async def _correct_label(session: AsyncSession, question_id: str) -> str:
    label = await session.scalar(
        select(Choice.label).where(
            Choice.question_id == uuid.UUID(question_id), Choice.is_correct.is_(True)
        )
    )
    assert label is not None
    return label


async def _wrong_label(session: AsyncSession, question_id: str) -> str:
    label = await session.scalar(
        select(Choice.label)
        .where(
            Choice.question_id == uuid.UUID(question_id), Choice.is_correct.is_(False)
        )
        .limit(1)
    )
    assert label is not None
    return label


async def _event_types(session: AsyncSession, pid: uuid.UUID) -> list[str]:
    await events.flush_events()
    rows = await session.scalars(
        select(Event.event_type).where(Event.participant_id == pid)
    )
    return list(rows)


# --------------------------------------------------------------------------- #
# Flow drivers (via the real HTTP surface)
# --------------------------------------------------------------------------- #
async def _run_diagnostic(
    client: AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    start = (await client.post("/diagnostic/start", headers=headers)).json()
    session_id = start["session_id"]
    items = start["items"]
    assert len(items) == 25  # DOC_09 §3 diagnostic size

    # Answer every item *incorrectly* on purpose so no block topic starts above
    # the mastery threshold — every topic must then be genuinely learned.
    for item in items:
        wrong = await _wrong_label(session, item["id"])
        resp = await client.post(
            "/diagnostic/answer",
            headers=headers,
            json={
                "session_id": session_id,
                "question_id": item["id"],
                "selected_label": wrong,
                "response_ms": 1000,
            },
        )
        assert resp.status_code == 200
    done = await client.post("/diagnostic/complete", headers=headers)
    assert done.status_code == 200
    assert done.json()["completed"] is True


async def _gate_answers(
    session: AsyncSession, items: list[dict[str, Any]], *, correct: bool
) -> list[dict[str, Any]]:
    out = []
    for item in items:
        label = (
            await _correct_label(session, item["id"])
            if correct
            else await _wrong_label(session, item["id"])
        )
        out.append({"question_id": item["id"], "selected_label": label})
    return out


async def _attempt_gate(
    client: AsyncClient,
    session: AsyncSession,
    headers: dict[str, str],
    step_id: str,
    *,
    correct: bool,
) -> dict[str, Any]:
    start = (
        await client.post(f"/steps/{step_id}/gate/start", headers=headers)
    ).json()
    items = start["items"]
    assert len(items) == 5  # DOC_09 §2.1.4: a gate quiz has 5 items
    answers = await _gate_answers(session, items, correct=correct)
    result = (
        await client.post(
            f"/steps/{step_id}/gate/submit", headers=headers, json={"answers": answers}
        )
    ).json()
    return result


# --------------------------------------------------------------------------- #
# The test
# --------------------------------------------------------------------------- #
async def test_full_participant_run(
    client: AsyncClient,
    session: AsyncSession,
    seeded: None,
    mock_anthropic: Any,
    ensure_content: Any,
) -> None:
    # 1. Enrollment -> a study_assignments row.
    enroll = (await client.post("/enroll", json={"consent_given": True})).json()
    code = enroll["code"]
    headers = {"X-Participant-Code": code}
    pid = await _pid(session, code)
    assert await session.get(StudyAssignment, pid) is not None
    block_order = enroll["block_order"]
    assert block_order in ("AB", "BA")

    # 2. Diagnostic -> one mastery row per topic (DOC_00's "48" is 47 in the
    #    catalog; assert against the actual topic count, not the prose number).
    await _run_diagnostic(client, session, headers)
    topic_count = await session.scalar(select(func.count()).select_from(Topic))
    mastery_count = await session.scalar(
        select(func.count()).select_from(Mastery).where(Mastery.participant_id == pid)
    )
    assert mastery_count == topic_count

    types_after_diag = await _event_types(session, pid)
    assert "diagnostic_started" in types_after_diag
    assert "diagnostic_completed" in types_after_diag
    assert types_after_diag.count("response_recorded") == 25

    graph = await graph_service.load_graph(session)
    blocks = [block_order[0], block_order[1]]

    # 3-7. Each block in order, under its assigned mode.
    for block_index, block in enumerate(blocks):
        created = (
            await client.post("/paths", headers=headers, json={"block": block})
        ).json()
        path_id = created["path_id"]
        assert created["current_step"] is not None

        # 3. learning_paths row + first step in_progress.
        path = await session.get(LearningPath, uuid.UUID(path_id))
        assert path is not None
        first_step = await session.scalar(
            select(PathStep)
            .where(PathStep.path_id == path.id, PathStep.step_index == 0)
            .execution_options(populate_existing=True)
        )
        assert first_step is not None and first_step.status == "in_progress"

        # 3 (cont). Pre-generation warmed the first three chunks.
        await drain_pregeneration()
        order = fixed.block_order(graph, block)
        for topic_id in order[:3]:
            chunk = await session.scalar(
                select(ContentChunk).where(ContentChunk.topic_id == topic_id)
            )
            assert chunk is not None, f"pre-generation missed {topic_id}"

        # 4-7. Drive every step to passed.
        did_fail_once = False
        guard = 0
        while True:
            guard += 1
            assert guard < 60, "path did not converge"
            current = (
                await client.get(
                    "/paths/current", params={"block": block}, headers=headers
                )
            ).json()
            if current["completed"]:
                break
            step = current["current_step"]
            assert step is not None
            step_id = step["id"]
            topic_id = step["topic_id"]
            await ensure_content(topic_id)

            # 5. On the very first step of the run, fail once and assert the path
            #    does not advance and the same step is re-served.
            if block_index == 0 and not did_fail_once:
                did_fail_once = True
                failed = await _attempt_gate(
                    client, session, headers, step_id, correct=False
                )
                assert failed["passed"] is False
                again = (
                    await client.get(
                        "/paths/current", params={"block": block}, headers=headers
                    )
                ).json()
                assert again["current_step"]["id"] == step_id
                assert again["passed_count"] == current["passed_count"]

            # 6. Pass it.
            passed = await _attempt_gate(
                client, session, headers, step_id, correct=True
            )
            assert passed["passed"] is True
            assert passed["posterior_at_gate"] >= MASTERY_THRESHOLD

        # 7. Block complete -> completed_at set + path_completed event.
        await session.refresh(path)
        assert path.completed_at is not None

    # 8. Final consistency across both blocks. Drop identity-mapped rows first:
    # steps/paths were mutated on the client's connection, so this session's
    # cached copies (loaded as in_progress at creation) would otherwise be stale.
    session.expire_all()
    types_final = await _event_types(session, pid)
    assert types_final.count("path_created") == 2
    assert types_final.count("path_completed") == 2
    assert "gate_attempt_started" in types_final
    assert "gate_attempt_completed" in types_final

    paths = list(
        await session.scalars(
            select(LearningPath).where(LearningPath.participant_id == pid)
        )
    )
    assert len(paths) == 2
    assert all(p.completed_at is not None for p in paths)

    all_steps = list(
        await session.scalars(
            select(PathStep).where(PathStep.path_id.in_([p.id for p in paths]))
        )
    )
    assert all_steps
    not_passed = [(s.topic_id, s.status) for s in all_steps if s.status != "passed"]
    assert not not_passed, f"unpassed steps: {not_passed}"

    # Every block's full topic set became a passed step, and every passed topic
    # cleared the mastery threshold — the study's internal-validity invariant.
    mastery = dict(
        (
            await session.execute(
                select(Mastery.topic_id, Mastery.p_mastered).where(
                    Mastery.participant_id == pid
                )
            )
        ).all()
    )
    for p in paths:
        expected = set(fixed.block_order(graph, p.block))
        passed = {s.topic_id for s in all_steps if s.path_id == p.id}
        assert passed == expected
        for topic_id in passed:
            assert mastery[topic_id] >= MASTERY_THRESHOLD

    # No answer key, mode label, or planner reasoning leaked to the participant.
    leaked = await client.get("/mastery", headers=headers)
    assert "reasoning" not in leaked.text.lower()
