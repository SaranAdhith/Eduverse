"""Bridging-lesson generation (DOC_06 §5).

Claude writes the markdown lesson that frames (with-video) or fully teaches
(fallback) a topic. Output is validated — valid markdown, at least one code
block, within the word budget ±10% — retried once with a clarifying note, then
falls back to a deterministic template skeleton so the assembler always gets a
lesson.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog
from app.logging import log_event
from app.modules.curation.model import VideoSegment
from app.modules.topics.model import Topic

log = structlog.get_logger("content.lesson")

# DOC_06 §5 word budgets.
WITH_VIDEO_MIN_WORDS = 250
WITH_VIDEO_MAX_WORDS = 400
FALLBACK_MIN_WORDS = 600
FALLBACK_MAX_WORDS = 1000
WORD_BUDGET_TOLERANCE = 0.10

_CODE_FENCE = re.compile(r"```")
_H1 = re.compile(r"^#\s", re.MULTILINE)

WITH_VIDEO_SYSTEM = (
    "You write companion lessons for a Python adaptive-learning agent. A short "
    "video segment is about to be shown. Write a 250-400 word markdown lesson "
    "that:\n"
    "1. Frames the topic and motivates it (2-3 sentences).\n"
    "2. Lists 2-4 concrete things to watch for during the video.\n"
    "3. After the video, synthesizes the key points and connects them to what "
    "the student already knows (prerequisite topics provided).\n"
    "4. Closes with a sentence on why this matters for what comes next.\n\n"
    "Use sentence case. Use code blocks for any code. Do not invent facts about "
    "the video that you cannot read; describe what to expect generically. Do "
    "not include H1 - start at H2."
)

FALLBACK_SYSTEM = (
    "You write standalone lessons for a Python adaptive-learning agent. No video "
    "is available, so this lesson is the primary teaching artifact. Write a "
    "600-1000 word markdown lesson covering: the concept, a worked example with "
    "code, common pitfalls, and a transition to the next topic.\n\n"
    "Use sentence case. Use code blocks for all code. Do not include H1 - start "
    "at H2."
)


@dataclass(frozen=True)
class LessonSpec:
    """The validated word budget + system prompt for a lesson variant."""

    system: str
    min_words: int
    max_words: int


def _spec(has_video: bool) -> LessonSpec:
    if has_video:
        return LessonSpec(WITH_VIDEO_SYSTEM, WITH_VIDEO_MIN_WORDS, WITH_VIDEO_MAX_WORDS)
    return LessonSpec(FALLBACK_SYSTEM, FALLBACK_MIN_WORDS, FALLBACK_MAX_WORDS)


class LessonValidationError(Exception):
    """Raised when generated lesson markdown fails a structural/budget check."""


def word_count(markdown: str) -> int:
    return len(markdown.split())


def validate_lesson(markdown: str, spec: LessonSpec) -> None:
    """Enforce DOC_06 §5: valid non-empty markdown, a code block, budget ±10%."""
    if not markdown.strip():
        raise LessonValidationError("empty lesson")
    if _H1.search(markdown):
        raise LessonValidationError("lesson must start at H2, not H1")
    if len(_CODE_FENCE.findall(markdown)) < 2:
        raise LessonValidationError("lesson must contain at least one code block")
    lower = int(spec.min_words * (1 - WORD_BUDGET_TOLERANCE))
    upper = int(spec.max_words * (1 + WORD_BUDGET_TOLERANCE))
    words = word_count(markdown)
    if not lower <= words <= upper:
        raise LessonValidationError(
            f"word count {words} outside budget [{lower}, {upper}]"
        )


def _prereq_context(prerequisite_topics: list[Topic]) -> str:
    if not prerequisite_topics:
        return "(none — this is a foundational topic)"
    return "\n".join(f"- {t.id} {t.name}" for t in prerequisite_topics)


def _build_prompt(
    topic: Topic, video_segment: VideoSegment | None, prerequisite_topics: list[Topic]
) -> str:
    lines = [
        f"Topic: {topic.id} {topic.name}",
        f"Description: {' '.join((topic.description or '').split())}",
        f"Prerequisite topics the student has already mastered:\n"
        f"{_prereq_context(prerequisite_topics)}",
    ]
    if video_segment is not None:
        lines.append(
            "A video segment titled "
            f"\"{video_segment.sub_topic_label}\" will be shown "
            f"({video_segment.end_seconds - video_segment.start_seconds}s). Frame "
            "it generically; do not invent its exact contents."
        )
    return "\n\n".join(lines)


def _extract_text(response: Any) -> str:
    parts = [
        getattr(block, "text", "")
        for block in getattr(response, "content", []) or []
        if getattr(block, "type", None) == "text"
    ]
    return "".join(parts).strip()


def _template_skeleton(
    topic: Topic, video_segment: VideoSegment | None, spec: LessonSpec
) -> str:
    """Deterministic, always-valid lesson used when Claude output can't pass.

    Padded to the low end of the word budget so it clears validation downstream;
    logged as a degraded artifact by the caller.
    """
    desc = " ".join((topic.description or "").split()) or topic.name
    intro = (
        f"## {topic.name}\n\n"
        f"This lesson introduces {topic.name}. {desc} "
    )
    body = (
        "The example below shows the idea in a minimal, self-contained form. "
        "Read it carefully, then reproduce it yourself before moving on.\n\n"
        "```python\n"
        "# A minimal illustration of the concept.\n"
        f"# Topic: {topic.id} {topic.name}\n"
        "value = 1\n"
        "result = value + 1\n"
        "print(result)\n"
        "```\n\n"
    )
    if video_segment is not None:
        body += (
            "As you watch the accompanying video, note how each idea builds on "
            "the last, and connect it back to what you already know. "
        )
    # Pad with a neutral study prompt until we reach the lower budget bound so
    # the skeleton itself is a valid lesson.
    filler_sentence = (
        "Take a moment to restate the key idea in your own words and predict "
        "what comes next. "
    )
    text = intro + body
    lower = int(spec.min_words * (1 - WORD_BUDGET_TOLERANCE))
    while word_count(text) < lower:
        text += filler_sentence
    return text


async def _call_claude(client: Any, *, system: str, prompt: str, model: str) -> str:
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_text(response)


async def generate(
    client: Any,
    *,
    topic: Topic,
    video_segment: VideoSegment | None,
    prerequisite_topics: list[Topic],
    model: str,
) -> str:
    """Generate + validate a lesson; retry once, then template-skeleton fallback."""
    spec = _spec(video_segment is not None)
    prompt = _build_prompt(topic, video_segment, prerequisite_topics)

    for attempt in range(2):
        attempt_prompt = prompt
        if attempt == 1:
            attempt_prompt = (
                f"{prompt}\n\nYour previous lesson failed validation. It must be "
                f"valid markdown starting at H2, contain at least one ```code``` "
                f"block, and be {spec.min_words}-{spec.max_words} words."
            )
        markdown = await _call_claude(
            client, system=spec.system, prompt=attempt_prompt, model=model
        )
        try:
            validate_lesson(markdown, spec)
            return markdown
        except LessonValidationError as exc:
            log.warning("lesson_validation_failed", attempt=attempt, error=str(exc))

    log_event(
        "lesson_generation_failed",
        topic_id=topic.id,
        fallback=video_segment is None,
    )
    return _template_skeleton(topic, video_segment, spec)
