"""DOC_05 §9 (planner) + §10 acceptance tests.

Fixed mode is exercised against real Postgres; personalized mode mocks Claude
(via ``personalized._get_client``) so no network call is made — the tests assert
the planner's candidate logic, not the model.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.modules.graph import service as graph_service
from app.modules.mastery import repo as mastery_repo
from app.modules.participants import service as participants_service
from app.modules.participants.model import Participant
from app.modules.planner import blocks, fixed, personalized, service
from app.modules.planner import repo as planner_repo
from sqlalchemy.ext.asyncio import AsyncSession

BLOCK_A_ROOTS = {"T2.1", "T2.2", "T3.1"}  # no in-block prerequisites (see §6)


@pytest.fixture(autouse=True)
def _reset_planner_cache() -> Any:
    personalized.reset_cache()
    yield
    personalized.reset_cache()


# --------------------------------------------------------------------------- #
# Test doubles for Claude
# --------------------------------------------------------------------------- #
class _FakeMessages:
    def __init__(self, choice: dict[str, str]):
        self._choice = choice
        self.calls = 0

    async def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        block = SimpleNamespace(
            type="tool_use", name="choose_next_topic", input=self._choice
        )
        return SimpleNamespace(content=[block])


class _FakeAnthropic:
    def __init__(self, next_topic_id: str, reasoning: str = "mock rationale"):
        self.messages = _FakeMessages(
            {"next_topic_id": next_topic_id, "reasoning": reasoning}
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _enroll(session: AsyncSession) -> Participant:
    return await participants_service.enroll(session, consent_given=True)


async def _set_mastery(
    session: AsyncSession, participant_id: Any, values: dict[str, float]
) -> None:
    for topic_id, p in values.items():
        await mastery_repo.upsert_mastery(session, participant_id, topic_id, p)


async def _drive_to_completion(
    session: AsyncSession, path: Any, first_step: Any
) -> list[str]:
    """Pass every step in turn and collect the topic sequence (fixed mode)."""
    sequence: list[str] = []
    step = first_step
    while step is not None:
        sequence.append(step.topic_id)
        step.status = "passed"
        step.passed_at = datetime.now(UTC)
        await session.flush()
        step = await service.advance_path(session, path)
    return sequence


# --------------------------------------------------------------------------- #
# Fixed mode (§9.1, §9.2)
# --------------------------------------------------------------------------- #
async def test_fixed_mode_follows_block_topological_order(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    path, step = await service.create_path(
        session, participant, block="A", mode="fixed"
    )
    graph = await graph_service.load_graph(session)
    order = fixed.block_order(graph, "A")

    assert step is not None and step.topic_id == order[0]
    sequence = await _drive_to_completion(session, path, step)
    assert sequence == order  # exact topological order, filtered to block A


async def test_fixed_mode_is_deterministic(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    path = await planner_repo.create_path(session, participant.id, "A", "fixed")
    results = set()
    for _ in range(100):
        topic, reasoning = await fixed.next_topic(session, path)
        assert reasoning is None
        assert topic is not None
        results.add(topic.id)
    assert len(results) == 1  # identical state -> identical output


# --------------------------------------------------------------------------- #
# Personalized mode (§9.3–§9.6)
# --------------------------------------------------------------------------- #
async def test_personalized_defers_to_claude_not_greedy_mastery(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # All three roots eligible; T2.1 has the highest posterior, but Claude picks
    # T2.2 — the planner must return Claude's choice, not the greedy max.
    monkeypatch.setattr(personalized, "_get_client", lambda: _FakeAnthropic("T2.2"))
    participant = await _enroll(session)
    await _set_mastery(
        session, participant.id, {"T2.1": 0.80, "T2.2": 0.50, "T3.1": 0.70}
    )
    path = await planner_repo.create_path(session, participant.id, "A", "personalized")

    topic, reasoning = await personalized.next_topic(session, path)
    assert topic is not None and topic.id == "T2.2"
    assert topic.id in BLOCK_A_ROOTS
    assert reasoning == "mock rationale"


async def test_personalized_never_returns_topic_with_unmastered_prereq(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Master T2.2 & T2.4 but not T2.5, so T2.6 (needs all three) is NOT eligible.
    # Even when Claude asks for T2.6, the planner refuses it.
    monkeypatch.setattr(personalized, "_get_client", lambda: _FakeAnthropic("T2.6"))
    participant = await _enroll(session)
    await _set_mastery(session, participant.id, {"T2.2": 0.90, "T2.4": 0.90})
    path = await planner_repo.create_path(session, participant.id, "A", "personalized")

    topic, _reasoning = await personalized.next_topic(session, path)
    assert topic is not None
    assert topic.id != "T2.6"  # unmastered direct prereq (T2.5) -> never chosen

    # Whatever is returned, its in-block direct prereqs are all mastered (>=0.85).
    graph = await graph_service.load_graph(session)
    allowed = fixed.block_core_topics(graph, "A")
    mastery = await planner_repo.mastery_map(session, participant.id)
    for prereq in graph.edges.get(topic.id, set()):
        if prereq in allowed:
            assert mastery.get(prereq, 0.0) >= personalized.MASTERY_THRESHOLD


async def test_personalized_softens_frontier_and_logs(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from structlog.testing import capture_logs

    monkeypatch.setattr(personalized, "_get_client", lambda: _FakeAnthropic("T2.3"))
    participant = await _enroll(session)
    # Every block-A topic sits at 0.7: >= the 0.6 soft threshold but < 0.85, so
    # the strict frontier is empty once the roots are marked passed.
    await _set_mastery(
        session, participant.id, dict.fromkeys(blocks.allowed_topics("A"), 0.7)
    )
    path = await planner_repo.create_path(session, participant.id, "A", "personalized")
    for i, root in enumerate(sorted(BLOCK_A_ROOTS)):
        await planner_repo.create_step(
            session,
            path_id=path.id,
            topic_id=root,
            step_index=i,
            status="passed",
            planner_reasoning=None,
        )

    with capture_logs() as logs:
        topic, _reasoning = await personalized.next_topic(session, path)

    assert topic is not None
    assert any(e.get("event_type") == "planner_frontier_softened" for e in logs)


async def test_personalized_falls_back_to_fixed_when_nothing_eligible(
    session: AsyncSession, seeded: None
) -> None:
    from structlog.testing import capture_logs

    participant = await _enroll(session)
    # No mastery at all and roots passed -> neither strict nor soft frontier has
    # a candidate (soft needs prereqs >= 0.6; defaults are 0.30) -> fixed order.
    path = await planner_repo.create_path(session, participant.id, "A", "personalized")
    for i, root in enumerate(sorted(BLOCK_A_ROOTS)):
        await planner_repo.create_step(
            session,
            path_id=path.id,
            topic_id=root,
            step_index=i,
            status="passed",
            planner_reasoning=None,
        )

    with capture_logs() as logs:
        topic, _reasoning = await personalized.next_topic(session, path)

    assert topic is not None
    assert topic.id not in BLOCK_A_ROOTS  # roots already passed
    assert any(e.get("event_type") == "planner_fallback" for e in logs)


async def test_planner_never_leaves_its_block(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    path, step = await service.create_path(
        session, participant, block="B", mode="fixed"
    )
    allowed = blocks.allowed_topics("B")
    sequence = await _drive_to_completion(session, path, step)

    assert set(sequence) <= set(allowed)
    assert len(sequence) == len(allowed)  # block B is 12 core topics


# --------------------------------------------------------------------------- #
# Acceptance (§10.2, §10.3, §10.4)
# --------------------------------------------------------------------------- #
async def test_fixed_sequence_independent_of_mastery(
    session: AsyncSession, seeded: None
) -> None:
    # §10.2: fixed mode ignores mastery entirely.
    p1 = await _enroll(session)
    path1, step1 = await service.create_path(session, p1, block="A", mode="fixed")
    seq_no_mastery = await _drive_to_completion(session, path1, step1)

    p2 = await _enroll(session)
    await _set_mastery(session, p2.id, {"T3.1": 0.99, "T6.3": 0.99, "T2.2": 0.99})
    path2, step2 = await service.create_path(session, p2, block="A", mode="fixed")
    seq_with_mastery = await _drive_to_completion(session, path2, step2)

    assert seq_no_mastery == seq_with_mastery


async def test_reasoning_populated_for_personalized_empty_for_fixed(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # §10.3
    monkeypatch.setattr(personalized, "_get_client", lambda: _FakeAnthropic("T2.2"))
    p1 = await _enroll(session)
    _, personalized_step = await service.create_path(
        session, p1, block="A", mode="personalized"
    )
    assert personalized_step is not None and personalized_step.planner_reasoning

    p2 = await _enroll(session)
    _, fixed_step = await service.create_path(session, p2, block="A", mode="fixed")
    assert fixed_step is not None and fixed_step.planner_reasoning is None


async def test_planner_caches_claude_decisions(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # §10.4: identical state must not cost two Opus calls.
    fake = _FakeAnthropic("T2.2")
    monkeypatch.setattr(personalized, "_get_client", lambda: fake)
    participant = await _enroll(session)
    path = await planner_repo.create_path(session, participant.id, "A", "personalized")

    first, _r1 = await personalized.next_topic(session, path)
    second, _r2 = await personalized.next_topic(session, path)
    assert first is not None and second is not None
    assert first.id == second.id == "T2.2"
    assert fake.messages.calls == 1  # second call served from cache


async def test_create_path_is_idempotent_and_mode_locked(
    session: AsyncSession, seeded: None
) -> None:
    participant = await _enroll(session)
    path1, step1 = await service.create_path(
        session, participant, block="A", mode="fixed"
    )
    # Re-create with a different requested mode -> existing (fixed) path wins.
    path2, step2 = await service.create_path(
        session, participant, block="A", mode="personalized"
    )
    assert path1.id == path2.id
    assert path2.mode == "fixed"
    assert step1 is not None and step2 is not None and step1.id == step2.id
