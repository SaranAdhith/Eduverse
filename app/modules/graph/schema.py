"""Pydantic response models for the graph/topic endpoints (DOC_02 §5)."""
from __future__ import annotations

from pydantic import BaseModel


class TopicOut(BaseModel):
    id: str
    tier: int
    name: str
    slug: str
    description: str
    display_order: int
    is_core: bool
    prerequisites: list[str]


class TopicPage(BaseModel):
    items: list[TopicOut]
    total: int
    limit: int
    offset: int


class GraphNode(BaseModel):
    id: str
    tier: int
    name: str
    slug: str
    is_core: bool


class GraphOut(BaseModel):
    # edges[topic_id] = list of that topic's prerequisites.
    nodes: list[GraphNode]
    edges: dict[str, list[str]]
