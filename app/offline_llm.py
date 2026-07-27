"""Offline LLM fallback — keyless graceful degradation.

When no ``ANTHROPIC_API_KEY`` is configured (local demos, CI, first-run), the
content assembler and personalized planner would otherwise call the real
Anthropic client and crash with an auth error. This module provides a drop-in
``OfflineAnthropic`` that synthesizes *deterministic, topic-specific* responses
in the exact shapes the parsers expect:

- lesson requests (plain text) → a valid markdown lesson (H2, a code block,
  within the word budget) built from the topic named in the prompt;
- ``record_quiz`` tool calls → five distinct items in the 1/3/1 difficulty mix;
- ``choose_next_topic`` tool calls → a sentinel the planner resolves to its
  first candidate (deterministic, no ranking).

The content is clearly templated — it exists so the platform is fully walkable
without a key, and is transparently replaced by real generations once a key is
set. Callers select it via ``_get_client`` when ``settings.anthropic_api_key`` is
empty.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

_TOPIC_RE = re.compile(r"Topic:\s*(\S+)\s+(.+)")
_DESC_RE = re.compile(r"Description:\s*(.+)")

_DIFFICULTY_PLAN = [
    ("easy", "recall what {name} means"),
    ("medium", "apply {name} to a short snippet"),
    ("medium", "predict the output when {name} is used"),
    ("medium", "pick the correct use of {name}"),
    ("hard", "trace a subtle edge case involving {name}"),
]


def _parse_topic(messages: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Best-effort (topic_id, name, description) from the prompt text."""
    text = "\n".join(
        m.get("content", "") for m in messages if isinstance(m.get("content"), str)
    )
    topic_id, name, description = "this topic", "this topic", ""
    if (m := _TOPIC_RE.search(text)) is not None:
        topic_id, name = m.group(1), m.group(2).strip()
    if (d := _DESC_RE.search(text)) is not None:
        description = d.group(1).strip()
    return topic_id, name, description


def _lesson_markdown(name: str, description: str, target_words: int) -> str:
    desc = description or f"{name} is a core Python concept."
    body = (
        f"## {name}\n\n"
        f"{desc} This lesson gives you a working understanding of {name} and "
        f"where it fits in your Python toolkit — enough to use it with intent "
        "rather than by imitation.\n\n"
        "### Why it matters\n\n"
        f"Most real programs lean on {name} constantly, so a shaky grasp here "
        "shows up as bugs everywhere else. Getting it solid now pays off across "
        "everything that builds on top of it.\n\n"
        "### The idea\n\n"
        f"Focus on two questions: *what* does {name} let you express, and *when* "
        "should you reach for it? Hold those in mind as you read the example — "
        "the goal is a mental model you can apply to a problem you haven't seen "
        "before, not a snippet you can only copy.\n\n"
        "### Example\n\n"
        "```python\n"
        "value = 1\n"
        "result = value + 1\n"
        "print(result)  # -> 2\n"
        "```\n\n"
        "Read it line by line and predict the output before you run it. Then "
        "change one thing — a value, an order, a call — and predict again. That "
        "loop of predict-then-check is where the real understanding forms.\n\n"
        "### Reading code carefully\n\n"
        "When you meet an unfamiliar snippet, resist the urge to skim. Name the "
        "type of every value, follow it as it changes line by line, and keep a "
        "running note of what you expect the state to be. The habit feels slow "
        "at first and then becomes automatic — and it is the single biggest "
        "difference between people who guess at code and people who read it.\n\n"
        "### Practice it\n\n"
        f"Rebuild the example from memory, then stretch it: apply {name} to a "
        "slightly bigger input, and try to make it fail on purpose so you learn "
        "its edges. Typing it out yourself, rather than re-reading, is what moves "
        "it from familiar to known. If you get stuck, shrink the problem until it "
        "is trivial, get that working, and grow it back one step at a time.\n\n"
        "### Common pitfalls\n\n"
        "- Reaching for it out of habit when a simpler tool would read better.\n"
        "- Trusting the output without tracing it — small assumptions hide bugs.\n"
        "- Skipping the edge cases: empty inputs, boundaries, and off-by-one.\n"
        "- Copying a pattern you don't understand and hoping it generalises.\n\n"
        "### Where this shows up\n\n"
        f"You will meet {name} again and again — in later lessons, in other "
        "people's code, and in the small utilities you write for yourself. "
        "Because it recurs so often, a little extra care here quietly removes a "
        "whole category of future confusion. That is why the path spends a full "
        "step on it rather than rushing past.\n\n"
        "### A mental model\n\n"
        f"Think of {name} as one dependable tool on your workbench. You don't "
        "need every detail memorised; you need to recognise the situations it is "
        "made for and reach for it with confidence when they appear. Everything "
        "else — the exact syntax, the rarer options — you can look up the moment "
        "you actually need it.\n\n"
        "### What's next\n\n"
        f"Once {name} feels comfortable, the gate quiz will check that you can "
        "apply it — not just recognise it. Before you continue, try to explain "
        "the idea in a single plain sentence; if you can teach it, you know it.\n\n"
    )
    # If still short of the (fallback) budget, extend with distinct prompts —
    # never one sentence on repeat — so the prose stays readable.
    pool = [
        f"Try writing a one-line comment that explains why {name} fits the "
        "example above.\n\n",
        "Say the idea out loud as if teaching a friend; the gaps you stumble on "
        "are exactly what to review.\n\n",
        f"Sketch a tiny second example of {name} on paper before you run "
        "anything — prediction first, verification second.\n\n",
        "List one situation where you would reach for this, and one where you "
        "deliberately would not.\n\n",
    ]
    i = 0
    while len(body.split()) < target_words:
        body += pool[i % len(pool)]
        i += 1
    return body


_LABELS = ("A", "B", "C", "D")


def _correct_label(name: str, i: int) -> str:
    """Spread the correct choice across A-D — varied per question and per topic
    (deterministic) so the answer key is never "always A"."""
    offset = sum(ord(c) for c in name) % 4
    # A fixed per-item pattern, shifted by the topic, hits all four labels.
    pattern = (0, 2, 3, 1, 2)
    return _LABELS[(pattern[i % len(pattern)] + offset) % 4]


def _quiz_items(name: str) -> dict[str, Any]:
    items = []
    for i, (difficulty, phrase_t) in enumerate(_DIFFICULTY_PLAN):
        phrase = phrase_t.format(name=name)
        correct = _correct_label(name, i)
        items.append(
            {
                "difficulty": difficulty,
                "stem": f"Question {i + 1}: which option best helps you {phrase}?",
                "stem_code": None,
                "choices": [
                    {
                        "label": lbl,
                        "text": f"Choice {lbl} for question {i + 1} about {name}",
                        "is_correct": lbl == correct,
                    }
                    for lbl in _LABELS
                ],
                "explanation": f"Choice {correct} is the intended answer for question {i + 1}.",
            }
        )
    return {"items": items}


def _text_block(text: str) -> Any:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _tool_block(name: str, payload: dict[str, Any]) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name=name, input=payload)]
    )


class _OfflineMessages:
    async def create(self, **kwargs: Any) -> Any:
        messages = kwargs.get("messages", [])
        tool_choice = kwargs.get("tool_choice") or {}
        tool = tool_choice.get("name") if isinstance(tool_choice, dict) else None

        if tool == "record_quiz":
            _id, name, _desc = _parse_topic(messages)
            return _tool_block("record_quiz", _quiz_items(name))
        if tool == "choose_next_topic":
            # The planner clamps an unknown id to its first candidate, so this
            # keeps offline planning deterministic without ranking.
            return _tool_block(
                "choose_next_topic",
                {
                    "next_topic_id": "__offline__",
                    "reasoning": "offline default: first eligible topic",
                },
            )
        # Lesson request. No video is seeded offline, so lessons use the fallback
        # budget (600-1000 words). Target just above the validator's lower bound
        # so the genuine sections fill it and the padding pool never fires.
        system = kwargs.get("system", "")
        target = 540 if "600-1000" in system else 250
        _id, name, description = _parse_topic(messages)
        return _text_block(_lesson_markdown(name, description, target))


class OfflineAnthropic:
    """Keyless drop-in for ``anthropic.AsyncAnthropic`` (see module docstring)."""

    def __init__(self) -> None:
        self.messages = _OfflineMessages()
