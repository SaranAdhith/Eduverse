"""Loading and querying the curriculum knowledge graph (DOC_00 section 1).

`Curriculum` holds the topic DAG and exposes the graph operations the path
planner relies on: topological ordering, prerequisite checks, and "what is the
student unlocked to study next" given a mastery vector.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import yaml

from .models import Tier, Topic


class CurriculumError(ValueError):
    """Raised when the curriculum data is structurally invalid."""


class Curriculum:
    def __init__(self, topics: list[Topic], tiers: dict[str, Tier]):
        self.topics: dict[str, Topic] = {t.id: t for t in topics}
        self.tiers: dict[str, Tier] = tiers
        if len(self.topics) != len(topics):
            raise CurriculumError("duplicate topic IDs in curriculum")

    # --- construction -----------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> Curriculum:
        data = yaml.safe_load(Path(path).read_text())
        tiers = {
            tid: Tier(id=tid, name=meta["name"])
            for tid, meta in data.get("tiers", {}).items()
        }
        topics = [
            Topic(
                id=row["id"],
                tier=row["tier"],
                name=row["name"],
                prerequisites=tuple(row.get("prerequisites") or ()),
                core=bool(row.get("core", True)),
            )
            for row in data.get("topics", [])
        ]
        return cls(topics, tiers)

    # --- queries ----------------------------------------------------------
    def __len__(self) -> int:
        return len(self.topics)

    def __contains__(self, topic_id: str) -> bool:
        return topic_id in self.topics

    def __getitem__(self, topic_id: str) -> Topic:
        return self.topics[topic_id]

    def topics_in_tier(self, tier: str) -> list[Topic]:
        return [t for t in self.topics.values() if t.tier == tier]

    def core_topics(self) -> list[Topic]:
        return [t for t in self.topics.values() if t.core]

    def missing_prerequisites(self) -> dict[str, list[str]]:
        """Topic ID -> prereq IDs that reference a topic not in the graph."""
        out: dict[str, list[str]] = {}
        for t in self.topics.values():
            dangling = [p for p in t.prerequisites if p not in self.topics]
            if dangling:
                out[t.id] = dangling
        return out

    def find_cycle(self) -> list[str] | None:
        """Return one prerequisite cycle as a list of IDs, or None if acyclic.

        DFS with a recursion stack; the returned list is the cycle slice of the
        path that closed back on itself.
        """
        WHITE, GREY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in self.topics}

        def visit(node: str, path: list[str]) -> list[str] | None:
            color[node] = GREY
            path.append(node)
            for nxt in self.topics[node].prerequisites:
                if nxt not in self.topics:
                    continue  # dangling prereqs are reported separately
                if color[nxt] == GREY:
                    return path[path.index(nxt):] + [nxt]
                if color[nxt] == WHITE:
                    found = visit(nxt, path)
                    if found:
                        return found
            color[node] = BLACK
            path.pop()
            return None

        for tid in self.topics:
            if color[tid] == WHITE:
                cycle = visit(tid, [])
                if cycle:
                    return cycle
        return None

    def topological_order(self) -> list[str]:
        """Kahn's algorithm over the prerequisite DAG (a valid 'fixed' sequence).

        Ties are broken by topic ID so the order is deterministic, which the
        study's fixed-condition path planner depends on (DOC_00 sections 5 & 7).
        """
        indeg = {tid: 0 for tid in self.topics}
        children: dict[str, list[str]] = {tid: [] for tid in self.topics}
        for t in self.topics.values():
            for p in t.prerequisites:
                if p not in self.topics:
                    raise CurriculumError(
                        f"topic {t.id} depends on unknown prerequisite {p}"
                    )
                indeg[t.id] += 1
                children[p].append(t.id)

        ready = deque(sorted(tid for tid, d in indeg.items() if d == 0))
        order: list[str] = []
        while ready:
            node = ready.popleft()
            order.append(node)
            for child in sorted(children[node]):
                indeg[child] -= 1
                if indeg[child] == 0:
                    ready.append(child)
        if len(order) != len(self.topics):
            raise CurriculumError("curriculum contains a prerequisite cycle")
        return order

    def available_topics(self, mastered: set[str]) -> list[str]:
        """Topics not yet mastered whose prerequisites are all mastered.

        This is the frontier the path planner chooses from. In personalized mode
        the LLM reasons over this set; in fixed mode it is walked in topo order.
        """
        out = []
        for t in self.topics.values():
            if t.id in mastered:
                continue
            if all(p in mastered for p in t.prerequisites):
                out.append(t.id)
        return sorted(out)
