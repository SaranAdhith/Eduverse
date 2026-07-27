"""DOC_08 §9 (study instrumentation) + §10 acceptance tests.

Assignment rotation, mode agreement, event dual-write, export tarball, the
analysis loader round-trip, and the LLM replay cache. Runs against real Postgres
(the events table, JSONB payloads, and the assignment advisory lock all need it).
"""
from __future__ import annotations

import io
import sys
import tarfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app.db import session_scope
from app.modules.participants import service as participants_service
from app.modules.participants.model import Participant
from app.modules.study import assignment, events, export, llm_cache, service
from app.modules.study.model import Event
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# analysis/lib is a sibling package outside app/; add the repo root's analysis
# dir to the path so the loader round-trip (§9.5) can import it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from lib import load as analysis_load  # noqa: E402


async def _enroll(session: AsyncSession) -> Participant:
    p = await participants_service.enroll(session, consent_given=True)
    await service.assign_on_enroll(session, p)
    return p


# --------------------------------------------------------------------------- #
# §9.1 — the rotation fills all four cells before any repeats
# --------------------------------------------------------------------------- #
async def test_four_enrollments_fill_four_cells(session: AsyncSession) -> None:
    participants = [await _enroll(session) for _ in range(4)]
    cells = []
    for p in participants:
        a = await assignment.get_assignment(session, p.id)
        assert a is not None
        cells.append(assignment.assignment_cell(a))
    assert sorted(cells) == [0, 1, 2, 3]  # each cell exactly once

    # Both modes experienced by every participant, block_order backfilled.
    for p in participants:
        a = await assignment.get_assignment(session, p.id)
        assert a is not None
        assert a.block_a_mode != a.block_b_mode
        assert p.block_order == a.block_order

    # A fifth enrollee cycles back to cell 0.
    fifth = await _enroll(session)
    a5 = await assignment.get_assignment(session, fifth.id)
    assert a5 is not None
    assert assignment.assignment_cell(a5) == 0


async def test_assign_is_idempotent(session: AsyncSession) -> None:
    p = await participants_service.enroll(session, consent_given=True)
    first = await assignment.assign(session, p)
    again = await assignment.assign(session, p)
    assert (first.block_order, first.block_a_mode) == (again.block_order, again.block_a_mode)
    count = await session.scalar(select(func.count()).select_from(assignment.StudyAssignment))
    assert count == 1


# --------------------------------------------------------------------------- #
# §9.2 — mode_for agrees with the assignment; mismatched POST /paths rejected
# --------------------------------------------------------------------------- #
async def test_mode_for_agrees_with_assignment(session: AsyncSession) -> None:
    p = await _enroll(session)
    a = await assignment.get_assignment(session, p.id)
    assert a is not None
    assert await assignment.mode_for(session, p.id, "A") == a.block_a_mode
    assert await assignment.mode_for(session, p.id, "B") == a.block_b_mode


async def test_resolve_mode_rejects_mismatch(session: AsyncSession) -> None:
    p = await _enroll(session)
    assigned = await assignment.mode_for(session, p.id, "A")
    wrong = "fixed" if assigned == "personalized" else "personalized"
    with pytest.raises(service.ModeMismatchError):
        await service.resolve_mode(session, p, "A", wrong)
    # The correct mode (and omission) are accepted.
    assert await service.resolve_mode(session, p, "A", assigned) == assigned
    assert await service.resolve_mode(session, p, "A", None) == assigned


class _FakePlannerMessages:
    async def create(self, **kwargs: Any) -> Any:
        block = SimpleNamespace(
            type="tool_use",
            name="choose_next_topic",
            input={"next_topic_id": "T2.1", "reasoning": "mock"},
        )
        return SimpleNamespace(content=[block])


class _FakePlannerClient:
    def __init__(self) -> None:
        self.messages = _FakePlannerMessages()


async def test_paths_endpoint_rejects_mismatched_mode(
    client: Any, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Personalized mode (P001 → A=personalized) would call Claude; mock it.
    from app.modules.planner import personalized

    monkeypatch.setattr(personalized, "_get_client", lambda: _FakePlannerClient())

    enroll = await client.post("/enroll", json={"consent_given": True})
    assert enroll.status_code == 201
    code = enroll.json()["code"]
    await events.flush_events()

    async for s in session_scope():
        p = await participants_service.resume(s, code=code)
        assigned = await assignment.mode_for(s, p.id, "A")
    wrong = "fixed" if assigned == "personalized" else "personalized"

    headers = {"X-Participant-Code": code}
    bad = await client.post("/paths", json={"block": "A", "mode": wrong}, headers=headers)
    assert bad.status_code == 409

    ok = await client.post("/paths", json={"block": "A"}, headers=headers)
    assert ok.status_code == 201
    assert ok.json()["mode"] == assigned


# --------------------------------------------------------------------------- #
# §9.3 — events table populates on every log_event; JSONL also receives the line
# --------------------------------------------------------------------------- #
async def test_events_dual_write(session: AsyncSession) -> None:
    p = await _enroll(session)  # emits participant_enrolled
    from app.logging import log_event

    log_event("diagnostic_started", participant_code=p.code, session_id=str(uuid.uuid4()))
    # Commit so the write-behind flush (separate connection) can resolve the code.
    await session.commit()
    written = await events.flush_events()
    assert written >= 2

    rows = list(
        await session.scalars(
            select(Event).where(Event.event_type == "participant_enrolled")
        )
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.participant_id == p.id
    assert row.payload["block_order"] in ("AB", "BA")
    assert "assignment_cell" in row.payload

    started = list(
        await session.scalars(
            select(Event).where(Event.event_type == "diagnostic_started")
        )
    )
    assert len(started) == 1


async def test_events_survive_buffer_reset(session: AsyncSession) -> None:
    from app.logging import log_event

    log_event("idle", participant_code="P999")
    events.reset()  # drop before flush -> nothing written
    written = await events.flush_events()
    assert written == 0


# --------------------------------------------------------------------------- #
# §9.4 — export produces a valid tarball for a participant with synthetic data
# §9.5 — analysis/lib/load.py round-trips the tarball into tables
# --------------------------------------------------------------------------- #
async def test_export_tarball_is_valid_and_round_trips(session: AsyncSession) -> None:
    from app.modules.mastery import repo as mastery_repo
    from app.modules.questions.model import Question
    from app.modules.topics.model import Topic

    p = await _enroll(session)
    # responses FK -> questions -> topics: seed the single topic + question used.
    session.add(
        Topic(
            id="T2.1",
            tier=2,
            name="Lists",
            slug="lists",
            description="List basics",
            display_order=1,
            is_core=True,
        )
    )
    await session.flush()
    q = Question(
        topic_id="T2.1",
        difficulty="medium",
        stem="stub",
        explanation="because",
        is_diagnostic=False,
        source="generated",
    )
    session.add(q)
    await session.flush()

    await mastery_repo.insert_response(
        session,
        participant_id=p.id,
        question_id=q.id,
        topic_id="T2.1",
        context="diagnostic",
        selected_label="A",
        is_correct=True,
        response_ms=1200,
        prior_mastery=0.3,
        posterior_mastery=0.6,
    )
    from app.logging import log_event

    log_event("diagnostic_started", participant_code=p.code)
    await session.commit()
    await events.flush_events()

    async for s in session_scope():
        tarball = await export.build_participant(s, p.code)

    # Valid gzip tarball with the documented members.
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        names = {m.name for m in tar.getmembers()}
    assert f"{p.code}/participant.json" in names
    assert f"{p.code}/responses.csv" in names
    assert f"{p.code}/events.jsonl" in names

    # §9.5: the analysis loader round-trips it.
    parsed = analysis_load.read_tarball(tarball)
    assert set(parsed.participants) == {p.code}
    pe = parsed.participants[p.code]
    assert pe.participant["code"] == p.code
    assert len(pe.tables["responses"]) == 1
    assert pe.tables["responses"][0]["topic_id"] == "T2.1"
    assert any(e["event_type"] == "diagnostic_started" for e in pe.events)


async def test_export_unknown_participant_raises(session: AsyncSession) -> None:
    async for s in session_scope():
        with pytest.raises(export.ParticipantNotFoundError):
            await export.build_participant(s, "P404")


# --------------------------------------------------------------------------- #
# §9.6 — LLM cache: same prompt twice -> second call doesn't hit the API
# --------------------------------------------------------------------------- #
class _CountingMessages:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        block = SimpleNamespace(type="text", text="hello")
        return SimpleNamespace(content=[block])


class _CountingClient:
    def __init__(self) -> None:
        self.messages = _CountingMessages()


async def test_llm_cache_serves_second_call(session: AsyncSession) -> None:
    inner = _CountingClient()
    client = llm_cache.wrap(inner)
    prompt = {
        "model": "claude-opus-4-7",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "ping"}],
    }

    first = await client.messages.create(**prompt)
    assert inner.messages.calls == 1
    assert first.content[0].text == "hello"

    second = await client.messages.create(**prompt)
    assert inner.messages.calls == 1  # served from cache, no new API call
    assert second.content[0].text == "hello"

    # A different prompt does hit the API.
    await client.messages.create(
        model="claude-opus-4-7",
        max_tokens=64,
        messages=[{"role": "user", "content": "different"}],
    )
    assert inner.messages.calls == 2
