"""Gate-quiz generation (DOC_06 §6).

Claude writes the 5-item gate quiz for a chunk via strict tool-use structured
output. Items are validated (schema, difficulty mix 1/3/1, exactly one correct
choice) and de-duplicated: any stem within Levenshtein-2 of an earlier one has
that item regenerated. Items conform to the DOC_02 seed-item shape so they can
be stored as ordinary ``questions`` rows.
"""
from __future__ import annotations

from typing import Any

import structlog
from app.modules.curation.model import VideoSegment
from app.modules.topics.model import Topic
from pydantic import BaseModel, ValidationError, field_validator, model_validator

log = structlog.get_logger("content.quiz")

# DOC_06 §6: 5 items with a fixed difficulty mix.
QUIZ_ITEM_COUNT = 5
REQUIRED_MIX: dict[str, int] = {"easy": 1, "medium": 3, "hard": 1}

# DOC_06 §6: stems within this edit distance count as near-duplicates.
LEVENSHTEIN_DUP_THRESHOLD = 2

_MAX_BATCH_ATTEMPTS = 2
_MAX_DEDUP_ROUNDS = 3
_CHOICE_LABELS = ("A", "B", "C", "D")

TOOL_NAME = "record_quiz"

QUIZ_SYSTEM = (
    "You write gate-quiz items for a Python adaptive-learning agent, based on a "
    "lesson the student just studied. Requirements:\n"
    "- Difficulty mix per quiz: 1 easy (recall), 3 medium (application), 1 hard "
    "(code tracing or edge case).\n"
    "- Each item has a stem, an optional stem_code code block, exactly 4 choices "
    "labelled A-D with exactly one correct, and an explanation.\n"
    "- Distractors must be plausible: common misconceptions, off-by-one errors, "
    "wrong operator precedence. Reviewer-quality distractors are the difference "
    "between a real gate and a vocabulary check.\n"
    "- No item may reference the video or lesson itself (never 'as the speaker "
    "said'); items must stand alone.\n"
    "- Do not repeat stems. Return your answer only by calling the record_quiz "
    "tool."
)

_CHOICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": list(_CHOICE_LABELS)},
        "text": {"type": "string"},
        "is_correct": {"type": "boolean"},
    },
    "required": ["label", "text", "is_correct"],
    "additionalProperties": False,
}

_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
        "stem": {"type": "string"},
        "stem_code": {"type": ["string", "null"]},
        "choices": {"type": "array", "items": _CHOICE_SCHEMA},
        "explanation": {"type": "string"},
    },
    "required": ["difficulty", "stem", "stem_code", "choices", "explanation"],
    "additionalProperties": False,
}

QUIZ_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Record the generated gate-quiz items.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"items": {"type": "array", "items": _ITEM_SCHEMA}},
        "required": ["items"],
        "additionalProperties": False,
    },
}


class GeneratedChoice(BaseModel):
    label: str
    text: str
    is_correct: bool

    @field_validator("label")
    @classmethod
    def _known_label(cls, label: str) -> str:
        if label not in _CHOICE_LABELS:
            raise ValueError(f"unknown choice label {label!r}")
        return label


class GeneratedQuestion(BaseModel):
    difficulty: str
    stem: str
    stem_code: str | None = None
    choices: list[GeneratedChoice]
    explanation: str

    @field_validator("difficulty")
    @classmethod
    def _known_difficulty(cls, difficulty: str) -> str:
        if difficulty not in REQUIRED_MIX:
            raise ValueError(f"unknown difficulty {difficulty!r}")
        return difficulty

    @model_validator(mode="after")
    def _well_formed_choices(self) -> GeneratedQuestion:
        labels = [c.label for c in self.choices]
        if sorted(labels) != list(_CHOICE_LABELS):
            raise ValueError(f"choices must be labelled A-D exactly once: {labels}")
        n_correct = sum(c.is_correct for c in self.choices)
        if n_correct != 1:
            raise ValueError(f"exactly one correct choice required, found {n_correct}")
        return self


class QuizResponse(BaseModel):
    items: list[GeneratedQuestion]


class QuizParseError(Exception):
    """Raised when a Claude response cannot be parsed into a QuizResponse."""


class QuizGenerationError(Exception):
    """Raised when a valid quiz could not be produced after all retries."""


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _normalize_stem(stem: str) -> str:
    return " ".join(stem.lower().split())


def duplicate_positions(items: list[GeneratedQuestion]) -> list[int]:
    """Indices of items whose stem is a near-duplicate of an earlier one."""
    dups: list[int] = []
    seen: list[str] = []
    for idx, item in enumerate(items):
        norm = _normalize_stem(item.stem)
        if any(_levenshtein(norm, prior) <= LEVENSHTEIN_DUP_THRESHOLD for prior in seen):
            dups.append(idx)
        else:
            seen.append(norm)
    return dups


def check_mix(items: list[GeneratedQuestion]) -> bool:
    counts: dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    for item in items:
        counts[item.difficulty] += 1
    return counts == REQUIRED_MIX


def _parse(response: Any) -> QuizResponse:
    tool_input: Any = None
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == TOOL_NAME:
            tool_input = block.input
            break
    if tool_input is None:
        raise QuizParseError("no record_quiz tool_use block in response")
    try:
        return QuizResponse.model_validate(tool_input)
    except ValidationError as exc:
        raise QuizParseError(str(exc)) from exc


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
def _build_prompt(topic: Topic, lesson_markdown: str) -> str:
    return (
        f"Topic: {topic.id} {topic.name}\n\n"
        f"Lesson the student just studied:\n{lesson_markdown}\n\n"
        f"Write exactly {QUIZ_ITEM_COUNT} gate-quiz items (1 easy, 3 medium, "
        "1 hard) testing genuine understanding of this topic."
    )


def _regenerate_prompt(topic: Topic, difficulty: str, avoid_stems: list[str]) -> str:
    avoid = "\n".join(f"- {s}" for s in avoid_stems)
    return (
        f"Topic: {topic.id} {topic.name}\n\n"
        f"Write exactly 1 {difficulty} gate-quiz item testing this topic. It "
        f"must be clearly distinct from these existing stems:\n{avoid}"
    )


async def _call(
    client: Any, *, prompt: str, model: str, retry_note: str | None
) -> QuizResponse | None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    if retry_note is not None:
        messages.append({"role": "user", "content": retry_note})
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=QUIZ_SYSTEM,
        tools=[QUIZ_TOOL],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=messages,
    )
    try:
        return _parse(response)
    except QuizParseError as exc:
        log.warning("quiz_parse_failed", error=str(exc))
        return None


async def _generate_batch(
    client: Any, *, topic: Topic, lesson_markdown: str, model: str
) -> list[GeneratedQuestion]:
    """Call Claude for a full quiz; retry once on any schema/mix failure."""
    prompt = _build_prompt(topic, lesson_markdown)
    for attempt in range(_MAX_BATCH_ATTEMPTS):
        note = None if attempt == 0 else (
            "Your previous quiz was invalid. Call record_quiz with exactly "
            f"{QUIZ_ITEM_COUNT} items in a 1 easy / 3 medium / 1 hard mix, each "
            "with 4 choices A-D and exactly one correct."
        )
        parsed = await _call(client, prompt=prompt, model=model, retry_note=note)
        if parsed is None:
            continue
        if len(parsed.items) == QUIZ_ITEM_COUNT and check_mix(parsed.items):
            return parsed.items
        log.warning(
            "quiz_shape_invalid",
            attempt=attempt,
            count=len(parsed.items),
            mix_ok=check_mix(parsed.items),
        )
    raise QuizGenerationError("could not produce a valid 5-item quiz")


async def _regenerate_one(
    client: Any, *, topic: Topic, difficulty: str, avoid_stems: list[str], model: str
) -> GeneratedQuestion | None:
    prompt = _regenerate_prompt(topic, difficulty, avoid_stems)
    parsed = await _call(client, prompt=prompt, model=model, retry_note=None)
    if parsed is None or not parsed.items:
        return None
    return parsed.items[0]


async def _dedup(
    client: Any,
    items: list[GeneratedQuestion],
    *,
    topic: Topic,
    model: str,
) -> list[GeneratedQuestion]:
    """Regenerate any near-duplicate item until the quiz has distinct stems."""
    for _ in range(_MAX_DEDUP_ROUNDS):
        dups = duplicate_positions(items)
        if not dups:
            return items
        for pos in dups:
            avoid = [it.stem for i, it in enumerate(items) if i != pos]
            log.warning("quiz_duplicate_stem", position=pos, stem=items[pos].stem)
            replacement = await _regenerate_one(
                client,
                topic=topic,
                difficulty=items[pos].difficulty,
                avoid_stems=avoid,
                model=model,
            )
            if replacement is not None:
                items[pos] = replacement
    if duplicate_positions(items):
        raise QuizGenerationError("could not eliminate near-duplicate stems")
    return items


async def generate(
    client: Any,
    *,
    topic: Topic,
    lesson_markdown: str,
    video_segment: VideoSegment | None,
    model: str,
) -> list[GeneratedQuestion]:
    """Generate the 5-item gate quiz for a chunk (DOC_06 §6).

    ``video_segment`` is accepted for signature parity with the spec; quiz items
    must stand alone and never reference the video, so it is not used in the
    prompt.
    """
    items = await _generate_batch(
        client, topic=topic, lesson_markdown=lesson_markdown, model=model
    )
    return await _dedup(client, items, topic=topic, model=model)
