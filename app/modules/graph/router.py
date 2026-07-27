"""Read-only topic/graph endpoints (DOC_02 §5)."""
from __future__ import annotations

from app.deps import get_session
from app.modules.graph import service
from app.modules.graph.schema import GraphNode, GraphOut, TopicOut, TopicPage
from app.modules.topics.model import Topic, TopicPrerequisite
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["graph"])


async def _prereq_map(
    session: AsyncSession, topic_ids: list[str] | None = None
) -> dict[str, list[str]]:
    """topic_id -> sorted list of its prerequisite ids."""
    stmt = select(TopicPrerequisite.topic_id, TopicPrerequisite.prereq_id)
    if topic_ids is not None:
        stmt = stmt.where(TopicPrerequisite.topic_id.in_(topic_ids))
    result = await session.execute(stmt)
    mapping: dict[str, list[str]] = {}
    for topic_id, prereq_id in result.all():
        mapping.setdefault(topic_id, []).append(prereq_id)
    for prereqs in mapping.values():
        prereqs.sort()
    return mapping


@router.get("/topics", response_model=TopicPage)
async def list_topics(
    session: AsyncSession = Depends(get_session),
    tier: int | None = Query(default=None, ge=0, le=8),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TopicPage:
    filters = [] if tier is None else [Topic.tier == tier]
    total = await session.scalar(
        select(func.count()).select_from(Topic).where(*filters)
    )
    rows = list(
        await session.scalars(
            select(Topic)
            .where(*filters)
            .order_by(Topic.tier, Topic.display_order, Topic.id)
            .limit(limit)
            .offset(offset)
        )
    )
    prereqs = await _prereq_map(session, [t.id for t in rows])
    items = [
        TopicOut(
            id=t.id,
            tier=t.tier,
            name=t.name,
            slug=t.slug,
            description=t.description,
            display_order=t.display_order,
            is_core=t.is_core,
            prerequisites=prereqs.get(t.id, []),
        )
        for t in rows
    ]
    return TopicPage(items=items, total=total or 0, limit=limit, offset=offset)


@router.get("/topics/{topic_id}", response_model=TopicOut)
async def get_topic(
    topic_id: str,
    session: AsyncSession = Depends(get_session),
) -> TopicOut:
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic not found")
    prereqs = await _prereq_map(session, [topic.id])
    return TopicOut(
        id=topic.id,
        tier=topic.tier,
        name=topic.name,
        slug=topic.slug,
        description=topic.description,
        display_order=topic.display_order,
        is_core=topic.is_core,
        prerequisites=prereqs.get(topic.id, []),
    )


@router.get("/graph", response_model=GraphOut)
async def get_graph(
    session: AsyncSession = Depends(get_session),
    is_core_only: bool = Query(default=False),
) -> GraphOut:
    graph = await service.load_graph(session)
    if is_core_only:
        graph = graph.core_subgraph()
    nodes = [
        GraphNode(id=t.id, tier=t.tier, name=t.name, slug=t.slug, is_core=t.is_core)
        for t in sorted(graph.nodes.values(), key=lambda t: (t.tier, t.display_order, t.id))
    ]
    edges = {tid: sorted(prereqs) for tid, prereqs in graph.edges.items()}
    return GraphOut(nodes=nodes, edges=edges)
