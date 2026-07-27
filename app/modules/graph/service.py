"""In-memory prerequisite graph + algorithms (DOC_02 §4).

Edges are adjacency from a topic to its *prerequisites*:
``edges[topic_id] == {prereq_id, ...}``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.modules.graph import repo
from app.modules.graph.errors import Cycle, GraphIntegrityError, TopicNotFoundError
from app.modules.topics.model import Topic
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class Graph:
    nodes: dict[str, Topic] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=dict)  # topic -> prereqs

    def sort_key(self, topic_id: str) -> tuple[int, int, str]:
        """Deterministic ordering key: (tier, display_order, id)."""
        node = self.nodes[topic_id]
        return (node.tier, node.display_order, node.id)

    def _require(self, topic_id: str) -> None:
        if topic_id not in self.nodes:
            raise TopicNotFoundError(topic_id)

    def core_subgraph(self) -> Graph:
        """A copy restricted to core topics and edges between core topics."""
        nodes = {tid: t for tid, t in self.nodes.items() if t.is_core}
        edges = {
            tid: {p for p in prereqs if p in nodes}
            for tid, prereqs in self.edges.items()
            if tid in nodes
        }
        return Graph(nodes=nodes, edges=edges)


async def load_graph(session: AsyncSession) -> Graph:
    """Build the in-memory graph from the topics tables."""
    topics = await repo.fetch_topics(session)
    edges: dict[str, set[str]] = {t.id: set() for t in topics}
    for topic_id, prereq_id in await repo.fetch_edges(session):
        edges.setdefault(topic_id, set()).add(prereq_id)
    return Graph(nodes={t.id: t for t in topics}, edges=edges)


def prerequisites(graph: Graph, topic_id: str) -> set[str]:
    """Direct prerequisites of a topic."""
    graph._require(topic_id)
    return set(graph.edges.get(topic_id, set()))


def transitive_prerequisites(graph: Graph, topic_id: str) -> set[str]:
    """Full ancestral closure of a topic's prerequisites (excludes the topic)."""
    graph._require(topic_id)
    seen: set[str] = set()
    queue = deque(graph.edges.get(topic_id, set()))
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(graph.edges.get(current, set()))
    return seen


def frontier(graph: Graph, mastered: set[str]) -> set[str]:
    """Topics not yet mastered whose every prerequisite is mastered."""
    return {
        tid
        for tid in graph.nodes
        if tid not in mastered and graph.edges.get(tid, set()) <= mastered
    }


def topological_order(graph: Graph, core_only: bool = True) -> list[str]:
    """Deterministic Kahn's algorithm; tie-break by (tier, display_order, id)."""
    g = graph.core_subgraph() if core_only else graph

    # in_degree = number of prerequisites still pending within the subgraph.
    in_degree = {tid: len(prereqs) for tid, prereqs in g.edges.items()}
    # dependents: prereq -> topics that require it.
    dependents: dict[str, set[str]] = {tid: set() for tid in g.nodes}
    for tid, prereqs in g.edges.items():
        for prereq in prereqs:
            dependents[prereq].add(tid)

    available = sorted(
        (tid for tid in g.nodes if in_degree.get(tid, 0) == 0),
        key=g.sort_key,
    )
    order: list[str] = []
    while available:
        current = available.pop(0)
        order.append(current)
        newly_ready = []
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                newly_ready.append(dependent)
        if newly_ready:
            available.extend(newly_ready)
            available.sort(key=g.sort_key)

    if len(order) != len(g.nodes):
        # A cycle prevented a full ordering.
        raise GraphIntegrityError(_find_cycles(g))
    return order


def validate_dag(graph: Graph) -> list[Cycle]:
    """Raise :class:`GraphIntegrityError` if the graph has a cycle; else []."""
    cycles = _find_cycles(graph)
    if cycles:
        raise GraphIntegrityError(cycles)
    return cycles


def _find_cycles(graph: Graph) -> list[Cycle]:
    """DFS back-edge detection. Returns up to one cycle path per component."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph.nodes, WHITE)
    cycles: list[Cycle] = []

    def visit(start: str) -> None:
        stack: list[tuple[str, bool]] = [(start, False)]
        path: list[str] = []
        while stack:
            node, processed = stack.pop()
            if processed:
                color[node] = BLACK
                path.pop()
                continue
            if color[node] != WHITE:
                continue
            color[node] = GREY
            path.append(node)
            stack.append((node, True))
            for prereq in sorted(graph.edges.get(node, set())):
                if color.get(prereq, BLACK) == GREY:
                    idx = path.index(prereq)
                    cycles.append([*path[idx:], prereq])
                elif color.get(prereq, BLACK) == WHITE:
                    stack.append((prereq, False))

    for node in graph.nodes:
        if color[node] == WHITE:
            visit(node)
    return cycles
