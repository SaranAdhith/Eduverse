"""Cross-phase graph/catalog consistency (DOC_09 §2.3).

These invariants span DOC_02 (graph), DOC_00 (diagnostic blueprint), and DOC_03
(video coverage) — no single phase's unit tests can assert them because they
each own only one side of the seam.
"""
from __future__ import annotations

from app.modules.curation.model import TopicVideoCoverage, VideoSegment
from app.modules.graph import service as graph_service
from app.modules.questions.model import Question
from app.modules.topics.model import Topic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def _diagnostic_tiers(session: AsyncSession) -> set[int]:
    rows = await session.execute(
        select(Topic.tier)
        .join(Question, Question.topic_id == Topic.id)
        .where(Question.is_diagnostic.is_(True))
        .distinct()
    )
    return {tier for (tier,) in rows}


async def test_every_topic_tier_is_anchored_or_intentionally_not(
    session: AsyncSession, seeded: None
) -> None:
    diagnostic_tiers = await _diagnostic_tiers(session)
    topics = list(await session.scalars(select(Topic)))
    assert topics
    for topic in topics:
        # A topic is placed either by a diagnostic anchor in its tier, or its
        # tier is intentionally unprobed (DOC_00 §2) — which only happens for
        # non-core scope-cut tiers (e.g. T7 async).
        anchored = topic.tier in diagnostic_tiers
        assert anchored or not topic.is_core, (
            f"core topic {topic.id} sits in unanchored tier {topic.tier}"
        )


async def test_core_topics_only_depend_on_core_topics(
    session: AsyncSession, seeded: None
) -> None:
    graph = await graph_service.load_graph(session)
    for topic_id, node in graph.nodes.items():
        if not node.is_core:
            continue
        for prereq_id in graph.edges.get(topic_id, set()):
            prereq = graph.nodes[prereq_id]
            assert prereq.is_core, (
                f"core topic {topic_id} depends on non-core prerequisite {prereq_id}"
            )


async def test_graph_is_an_acyclic_connected_dag(
    session: AsyncSession, seeded: None
) -> None:
    graph = await graph_service.load_graph(session)
    # No cycles anywhere.
    assert graph_service.validate_dag(graph) == []
    # A full topological order exists over the core subgraph (Kahn completes).
    order = graph_service.topological_order(graph, core_only=True)
    assert len(order) == len(graph.core_subgraph().nodes)


async def test_covered_topics_have_segments(
    session: AsyncSession, seeded: None
) -> None:
    covered = list(
        await session.scalars(
            select(TopicVideoCoverage.topic_id).where(
                TopicVideoCoverage.status == "covered"
            )
        )
    )
    for topic_id in covered:
        n = await session.scalar(
            select(func.count())
            .select_from(VideoSegment)
            .where(VideoSegment.topic_id == topic_id)
        )
        assert n and n > 0, f"topic {topic_id} marked covered but has no segments"
