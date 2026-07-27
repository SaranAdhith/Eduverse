"""Personalized mode — the experimental arm (DOC_05 §5).

Combines the BKT mastery vector, the prerequisite graph, and Claude reasoning to
pick the next topic. Eligibility is the graph frontier at the mastery threshold,
softened if the diagnostic was over-cautious, and falling back to fixed order if
nothing is eligible. When more than one topic is eligible, Claude chooses (and
explains); identical situations are cached so they never cost two Opus calls.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import anthropic
from app.config import get_settings
from app.logging import log_event
from app.modules.graph import service as graph_service
from app.modules.graph.service import Graph
from app.modules.mastery.params import params_for
from app.modules.planner import fixed, repo
from app.modules.planner.gate import MASTERY_THRESHOLD
from app.modules.planner.model import LearningPath
from app.modules.topics.model import Topic
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# DOC_05 §5.3: soften eligibility to prereqs each >= 0.6 when the strict frontier
# stalls, so an over-cautious diagnostic doesn't freeze the planner.
SOFT_PREREQ_THRESHOLD = 0.6

TOOL_NAME = "choose_next_topic"

PLANNER_SYSTEM = (
    "You are a curriculum planner for a Python learning agent. Given a student's "
    "current mastery vector and a set of candidate topics (all of whose "
    "prerequisites the student has already mastered), choose the single best next "
    "topic to teach. Prefer topics that (a) unlock the most downstream content, "
    "(b) connect cleanly to what the student recently mastered, (c) are not "
    "currently being avoided due to a single weak prerequisite. Return ONLY valid "
    "JSON."
)

PLANNER_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Choose the single best next topic to teach and explain why.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "next_topic_id": {"type": "string"},
            "reasoning": {"type": "string"},
        },
        "required": ["next_topic_id", "reasoning"],
        "additionalProperties": False,
    },
}

# Global decision cache keyed by (mastery_hash, candidate_set_hash) — DOC_05 §5.
_DECISION_CACHE: dict[tuple[str, str], tuple[str, str]] = {}


class PlannerChoice(BaseModel):
    next_topic_id: str
    reasoning: str


class PlannerParseError(Exception):
    """Raised when Claude's response has no valid choose_next_topic tool_use."""


def reset_cache() -> None:
    """Clear the next-topic decision cache (used by tests)."""
    _DECISION_CACHE.clear()


def _get_client() -> Any:
    """The Anthropic async client (indirection lets tests inject a fake).

    With no API key configured, falls back to the deterministic offline chooser so
    personalized planning degrades gracefully instead of crashing. Otherwise
    wrapped with the DOC_08 §8 replay cache for study reproducibility.
    """
    settings = get_settings()
    # Tests inject their own doubles; only degrade to offline outside tests.
    if not settings.anthropic_api_key and settings.env != "test":
        from app.offline_llm import OfflineAnthropic

        return OfflineAnthropic()
    client: Any = anthropic.AsyncAnthropic()
    if settings.llm_cache_enabled:
        from app.modules.study import llm_cache

        return llm_cache.wrap(client)
    return client


def _prereq_mastery(mastery: dict[str, float], topic_id: str) -> float:
    return mastery.get(topic_id, params_for(topic_id).p_init)


def _dependent_counts(graph: Graph) -> dict[str, int]:
    """topic_id -> how many topics transitively depend on it (unlock signal)."""
    counts: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for topic_id in graph.nodes:
        for ancestor in graph_service.transitive_prerequisites(graph, topic_id):
            counts[ancestor] = counts.get(ancestor, 0) + 1
    return counts


def _cache_key(mastery: dict[str, float], candidates: list[str]) -> tuple[str, str]:
    mastery_str = ";".join(f"{t}:{round(p, 3)}" for t, p in sorted(mastery.items()))
    candidate_str = ",".join(sorted(candidates))
    return (
        hashlib.sha1(mastery_str.encode()).hexdigest(),
        hashlib.sha1(candidate_str.encode()).hexdigest(),
    )


def _build_payload(
    graph: Graph,
    mastery: dict[str, float],
    candidates: list[str],
    recently_passed: list[str],
) -> dict[str, Any]:
    dependents = _dependent_counts(graph)
    candidate_payload = []
    for topic_id in candidates:
        node = graph.nodes[topic_id]
        direct_prereqs = graph.edges.get(topic_id, set())
        weakest = min(
            (_prereq_mastery(mastery, p) for p in direct_prereqs), default=1.0
        )
        candidate_payload.append(
            {
                "topic_id": topic_id,
                "name": node.name,
                "downstream_count": dependents.get(topic_id, 0),
                "weakest_prereq_mastery": round(weakest, 3),
                "tier": node.tier,
            }
        )
    return {
        "mastery_vector": {t: round(p, 3) for t, p in sorted(mastery.items())},
        "candidates": candidate_payload,
        "recently_passed": recently_passed,
    }


def _parse_response(response: Any) -> PlannerChoice:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == TOOL_NAME:
            return PlannerChoice.model_validate(block.input)
    raise PlannerParseError("no choose_next_topic tool_use block in response")


async def _call_claude(client: Any, payload: dict[str, Any]) -> tuple[str, str]:
    response = await client.messages.create(
        model=get_settings().anthropic_model_reasoning,
        max_tokens=512,
        system=PLANNER_SYSTEM,
        tools=[PLANNER_TOOL],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    choice = _parse_response(response)
    return choice.next_topic_id, choice.reasoning


async def _rank_candidates(
    graph: Graph,
    mastery: dict[str, float],
    candidates: list[str],
    recently_passed: list[str],
) -> tuple[str, str]:
    """Cached Claude call selecting one of several eligible candidates."""
    key = _cache_key(mastery, candidates)
    cached = _DECISION_CACHE.get(key)
    if cached is not None:
        log_event("planner_cache_hit", candidates=candidates, chosen=cached[0])
        return cached
    payload = _build_payload(graph, mastery, candidates, recently_passed)
    chosen_id, reasoning = await _call_claude(_get_client(), payload)
    if chosen_id not in candidates:
        # Defensive: never trust the model past the eligible set.
        chosen_id = candidates[0]
    _DECISION_CACHE[key] = (chosen_id, reasoning)
    log_event("planner_llm_call", candidates=candidates, chosen=chosen_id)
    return chosen_id, reasoning


async def next_topic(
    session: AsyncSession, path: LearningPath
) -> tuple[Topic | None, str | None]:
    graph = await graph_service.load_graph(session)
    allowed = fixed.block_core_topics(graph, path.block)
    restricted = fixed.restrict_graph(graph, allowed)
    mastery = await repo.mastery_map(session, path.participant_id)
    steps = await repo.steps_for(session, path.id)
    passed = {s.topic_id for s in steps if s.status == "passed"}

    mastered = {tid for tid, p in mastery.items() if p >= MASTERY_THRESHOLD}
    candidates = {t for t in graph_service.frontier(restricted, mastered) if t not in passed}

    unpassed = {tid for tid in restricted.nodes if tid not in passed}
    softened = False
    if not candidates and unpassed:
        candidates = {
            tid
            for tid in unpassed
            if all(
                _prereq_mastery(mastery, p) >= SOFT_PREREQ_THRESHOLD
                for p in restricted.edges.get(tid, set())
            )
        }
        softened = bool(candidates)

    if not candidates:
        log_event(
            "planner_fallback",
            path_id=str(path.id),
            block=path.block,
            reason="no eligible topic at 0.85 or 0.6 thresholds",
        )
        return await fixed.next_topic(session, path)

    if softened:
        log_event(
            "planner_frontier_softened",
            path_id=str(path.id),
            block=path.block,
            candidates=sorted(candidates),
        )

    ordered = sorted(candidates)
    if len(ordered) == 1:
        return graph.nodes[ordered[0]], "Only eligible topic given current mastery."

    recently_passed = [s.topic_id for s in steps if s.status == "passed"][-3:]
    chosen_id, reasoning = await _rank_candidates(graph, mastery, ordered, recently_passed)
    return graph.nodes[chosen_id], reasoning
