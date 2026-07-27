"""Fixed mode — the deterministic control arm (DOC_05 §4).

No mastery vector, no LLM. Pure topological traversal of the block's core
topics: the first not-yet-passed topic in ``topological_order`` is next. Same
participant, same block -> same sequence, every time.
"""
from __future__ import annotations

from app.modules.graph import service as graph_service
from app.modules.graph.service import Graph
from app.modules.planner import blocks, repo
from app.modules.planner.model import LearningPath
from app.modules.topics.model import Topic
from sqlalchemy.ext.asyncio import AsyncSession


def block_core_topics(graph: Graph, block: str) -> set[str]:
    """The block's topic ids that are present and core (DOC_05 §4, §6)."""
    allowed = blocks.allowed_topics(block)
    return {
        tid
        for tid in allowed
        if tid in graph.nodes and graph.nodes[tid].is_core
    }


def restrict_graph(graph: Graph, allowed: set[str]) -> Graph:
    """A subgraph over ``allowed`` topics, dropping edges to out-of-block prereqs.

    Out-of-block prerequisites are treated as pre-mastered (DOC_05 §6), so they
    are simply removed from the edge sets rather than blocking the topic.
    """
    nodes = {tid: node for tid, node in graph.nodes.items() if tid in allowed}
    edges = {
        tid: {p for p in graph.edges.get(tid, set()) if p in allowed} for tid in nodes
    }
    return Graph(nodes=nodes, edges=edges)


def block_order(graph: Graph, block: str) -> list[str]:
    """Deterministic topological order of the block's core topics."""
    restricted = restrict_graph(graph, block_core_topics(graph, block))
    return graph_service.topological_order(restricted, core_only=False)


async def next_topic(
    session: AsyncSession, path: LearningPath
) -> tuple[Topic | None, str | None]:
    """First not-yet-passed topic in the block's topological order (or None)."""
    graph = await graph_service.load_graph(session)
    order = block_order(graph, path.block)
    passed = await repo.passed_topic_ids(session, path.id)
    for topic_id in order:
        if topic_id not in passed:
            return graph.nodes[topic_id], None
    return None, None  # every block topic is passed -> path complete
