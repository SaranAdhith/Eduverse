"""Mode determinism (DOC_09 §2.2).

Fixed mode must be byte-identical across participants given identical responses —
it is the control arm, so any drift is a bug. Personalized mode is only partially
deterministic: identical mastery + candidate set must hit the planner cache and
yield the same decision.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.graph import service as graph_service
from app.modules.participants import service as participants_service
from app.modules.participants.model import Participant
from app.modules.planner import fixed, personalized, service
from app.modules.planner import repo as planner_repo
from sqlalchemy.ext.asyncio import AsyncSession


async def _drive_fixed_sequence(
    session: AsyncSession, participant: Participant, block: str
) -> list[str]:
    """Create a fixed path and pass every step, returning the topic_id sequence."""
    path = await planner_repo.create_path(session, participant.id, block, "fixed")
    step = await service.advance_path(session, path)
    sequence: list[str] = []
    while step is not None:
        sequence.append(step.topic_id)
        step.status = "passed"
        step.passed_at = datetime.now(UTC)
        await session.flush()
        step = await service.advance_path(session, path)
    return sequence


async def test_fixed_mode_is_byte_identical_across_participants(
    session: AsyncSession, seeded: None
) -> None:
    p1 = await participants_service.enroll(session, consent_given=True)
    p2 = await participants_service.enroll(session, consent_given=True)

    seq1 = await _drive_fixed_sequence(session, p1, "A")
    seq2 = await _drive_fixed_sequence(session, p2, "A")

    assert seq1 == seq2
    # And it equals the block's canonical topological order (no hidden state).
    graph = await graph_service.load_graph(session)
    assert seq1 == fixed.block_order(graph, "A")

    # Ordered (step_index -> topic_id) rows match exactly across the two paths.
    steps1 = await planner_repo.steps_for(
        session, (await planner_repo.get_path(session, p1.id, "A")).id  # type: ignore[union-attr]
    )
    steps2 = await planner_repo.steps_for(
        session, (await planner_repo.get_path(session, p2.id, "A")).id  # type: ignore[union-attr]
    )
    assert [s.topic_id for s in steps1] == [s.topic_id for s in steps2]


async def test_personalized_decision_is_cached_and_stable(
    session: AsyncSession, seeded: None, mock_anthropic: Any
) -> None:
    personalized.reset_cache()

    p1 = await participants_service.enroll(session, consent_given=True)
    p2 = await participants_service.enroll(session, consent_given=True)

    # Identical mastery vectors -> identical candidate set -> identical cache key.
    mastery = {"T2.1": 0.9, "T2.2": 0.9}
    from app.modules.mastery import repo as mastery_repo

    for participant in (p1, p2):
        for topic_id, p in mastery.items():
            await mastery_repo.upsert_mastery(session, participant.id, topic_id, p)
    await session.flush()

    path1 = await planner_repo.create_path(session, p1.id, "A", "personalized")
    path2 = await planner_repo.create_path(session, p2.id, "A", "personalized")

    topic1, reasoning1 = await personalized.next_topic(session, path1)
    calls_after_first = len(mock_anthropic.calls)
    topic2, reasoning2 = await personalized.next_topic(session, path2)

    assert topic1 is not None and topic2 is not None
    assert topic1.id == topic2.id
    assert reasoning1 == reasoning2
    # Second identical decision was served from the cache — no extra LLM call.
    assert len(mock_anthropic.calls) == calls_after_first
