"""Graph errors (DOC_02 §4)."""
from __future__ import annotations

# A cycle is the ordered list of topic ids that close a loop, e.g.
# ['T0.1', 'T0.2', 'T0.1'].
Cycle = list[str]


class GraphError(Exception):
    """Base class for graph errors."""


class GraphIntegrityError(GraphError):
    """Raised when the prerequisite graph is not a DAG (contains a cycle)."""

    def __init__(self, cycles: list[Cycle]) -> None:
        self.cycles = cycles
        joined = "; ".join(" -> ".join(c) for c in cycles)
        super().__init__(f"prerequisite graph contains cycle(s): {joined}")


class TopicNotFoundError(GraphError):
    """Raised when a topic id is not present in the graph."""
