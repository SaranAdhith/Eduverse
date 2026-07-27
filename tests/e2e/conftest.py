"""End-to-end test infrastructure (DOC_09 §6).

These tests exercise the *seams* between phases against the real test DB. No live
API calls are made: ``mock_anthropic`` replaces the Anthropic client at both
injection points (content assembler + personalized planner) with a deterministic
synthesizer that produces valid lessons, valid 5-item quizzes, and planner
choices. This is the practical stand-in for the recorded ``llm_cache.json``
fixture named in DOC_09 §6 — it needs no key and never drifts.

The per-session DB, migration/seed, and HTTP client come from the parent
``tests/conftest.py`` (``client``, ``session``, ``seeded``); this file only adds
the LLM/YouTube doubles and content helpers.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from app.db import session_scope

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# --------------------------------------------------------------------------- #
# Deterministic Anthropic double
# --------------------------------------------------------------------------- #
def _lesson_markdown(words: int) -> str:
    """A structurally valid lesson: starts at H2, has a code block, ~``words``."""
    head = (
        "## Understanding this topic\n\n"
        "This lesson explains the concept and shows it in a minimal example. "
        "Read the example, then reproduce it before moving on.\n\n"
        "```python\n"
        "value = 1\n"
        "result = value + 1\n"
        "print(result)\n"
        "```\n\n"
    )
    filler = (
        "Restate the key idea in your own words and predict what comes next as "
        "you study this material carefully and connect it to earlier topics. "
    )
    text = head
    while len(text.split()) < words:
        text += filler
    return text


def _quiz_items() -> list[dict[str, Any]]:
    """Five distinct items in the required 1 easy / 3 medium / 1 hard mix."""
    plan = [
        ("easy", "recall the definition"),
        ("medium", "apply the idea to a short snippet"),
        ("medium", "predict the output of a loop"),
        ("medium", "choose the correct call for a dictionary"),
        ("hard", "trace an edge case with slicing"),
    ]
    items: list[dict[str, Any]] = []
    for i, (difficulty, phrase) in enumerate(plan):
        # Distinct stems (well beyond Levenshtein-2) so dedup never fires.
        stem = f"Item {i} — which option best helps you {phrase} here?"
        choices = [
            {"label": lbl, "text": f"Option {lbl} for item {i}", "is_correct": lbl == "A"}
            for lbl in ("A", "B", "C", "D")
        ]
        items.append(
            {
                "difficulty": difficulty,
                "stem": stem,
                "stem_code": None,
                "choices": choices,
                "explanation": f"Option A is correct for item {i}.",
            }
        )
    return items


def _text_response(text: str) -> Any:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _tool_response(name: str, payload: dict[str, Any]) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name=name, input=payload)]
    )


class RecordingMessages:
    """A ``messages`` stand-in that records prompts and synthesizes responses."""

    def __init__(self, calls: list[dict[str, Any]]):
        self._calls = calls

    async def create(self, **kwargs: Any) -> Any:
        self._calls.append(kwargs)
        tool_choice = kwargs.get("tool_choice") or {}
        tool_name = tool_choice.get("name") if isinstance(tool_choice, dict) else None

        if tool_name == "record_quiz":
            return _tool_response("record_quiz", {"items": _quiz_items()})
        if tool_name == "choose_next_topic":
            # The planner defends against an unknown id by taking candidates[0],
            # so returning a sentinel keeps selection deterministic (sorted-first).
            return _tool_response(
                "choose_next_topic",
                {"next_topic_id": "__mock__", "reasoning": "mock planner rationale"},
            )
        # Otherwise it's a lesson request; size to the budget in the system prompt.
        system = kwargs.get("system", "")
        words = 700 if "600-1000" in system else 320
        return _text_response(_lesson_markdown(words))


class MockAnthropic:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.messages = RecordingMessages(self.calls)


@pytest.fixture
def mock_anthropic(monkeypatch: pytest.MonkeyPatch) -> MockAnthropic:
    """Replace the Anthropic client at both injection points (§6)."""
    from app.modules.content import assembler
    from app.modules.planner import personalized

    fake = MockAnthropic()
    monkeypatch.setattr(assembler, "_get_client", lambda: fake)
    monkeypatch.setattr(personalized, "_get_client", lambda: fake)
    return fake


# --------------------------------------------------------------------------- #
# Recorded YouTube double (§6) — curation isn't driven by the e2e flow, but the
# fixture exists so a curation seam test can serve recorded responses.
# --------------------------------------------------------------------------- #
@pytest.fixture
def mock_youtube() -> dict[str, Any]:
    path = FIXTURES / "youtube_responses.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


# --------------------------------------------------------------------------- #
# Content helper: build (and commit) a chunk for a topic, mirroring the
# pre-generation path. Content has no on-unlock HTTP trigger, so the driver warms
# each step's topic explicitly (as a study operator's content warmer would).
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
def ensure_content() -> Any:
    from app.modules.content import assembler

    async def _ensure(topic_id: str) -> None:
        async for s in session_scope():
            await assembler.build(s, topic_id)

    return _ensure
