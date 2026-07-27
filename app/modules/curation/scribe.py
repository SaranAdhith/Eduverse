"""Scribe: transcript -> topic-mapped sub-topic segments via Claude (DOC_03 §4.2).

Uses the SDK's strict tool-use structured-output mechanism (not text + regex).
Responses are validated with pydantic and business-filtered; a response that
fails to parse is retried once, then the video is skipped.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, ValidationError

log = structlog.get_logger("scribe")

# DOC_03 §4.2 validation bounds.
SEGMENT_MIN_SECONDS = 30
SEGMENT_MAX_SECONDS = 15 * 60
MIN_CONFIDENCE = 0.5

TOOL_NAME = "record_segments"

SCRIBE_SYSTEM = (
    "You are a curriculum mapper. Given a Python tutorial transcript with "
    "timestamps, identify segments that map cleanly to topics from the provided "
    "list. Do not invent topics. If a span covers no listed topic, omit it. "
    "Return your answer only by calling the record_segments tool."
)

_SEGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topic_id": {"type": "string"},
        "sub_topic_label": {"type": "string"},
        "start_seconds": {"type": "integer"},
        "end_seconds": {"type": "integer"},
        "transcript_excerpt": {"type": "string"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": [
        "topic_id",
        "sub_topic_label",
        "start_seconds",
        "end_seconds",
        "transcript_excerpt",
        "confidence",
        "reasoning",
    ],
    "additionalProperties": False,
}

SEGMENTS_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Record the sub-topic segments identified in the transcript.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"segments": {"type": "array", "items": _SEGMENT_SCHEMA}},
        "required": ["segments"],
        "additionalProperties": False,
    },
}


class ScribeSegment(BaseModel):
    topic_id: str
    sub_topic_label: str
    start_seconds: int
    end_seconds: int
    transcript_excerpt: str
    confidence: float
    reasoning: str


class ScribeResponse(BaseModel):
    segments: list[ScribeSegment]


class ScribeParseError(Exception):
    """Raised when a Claude response cannot be parsed into ScribeResponse."""


def _build_user_prompt(transcript: str, topics_context: str) -> str:
    return f"Topics list (map only to these):\n{topics_context}\n\nTranscript:\n{transcript}\n"


def parse_response(response: Any) -> ScribeResponse:
    """Extract + validate the tool_use payload; raise ScribeParseError on failure."""
    tool_input: Any = None
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == TOOL_NAME:
            tool_input = block.input
            break
    if tool_input is None:
        raise ScribeParseError("no record_segments tool_use block in response")
    try:
        return ScribeResponse.model_validate(tool_input)
    except ValidationError as exc:
        raise ScribeParseError(str(exc)) from exc


def filter_segments(response: ScribeResponse, allowed_topic_ids: set[str]) -> list[ScribeSegment]:
    """Drop segments with unknown topic, bad duration, or low confidence (DOC_03 §4.2)."""
    kept: list[ScribeSegment] = []
    for seg in response.segments:
        duration = seg.end_seconds - seg.start_seconds
        if seg.topic_id not in allowed_topic_ids:
            continue
        if duration < SEGMENT_MIN_SECONDS or duration > SEGMENT_MAX_SECONDS:
            continue
        if seg.confidence < MIN_CONFIDENCE:
            continue
        kept.append(seg)
    return kept


async def call_scribe(
    client: Any,
    *,
    transcript: str,
    topics_context: str,
    model: str,
    max_tokens: int = 8192,
) -> ScribeResponse | None:
    """Call Claude, retry once on a parse failure, then give up (return None)."""
    base_messages = [{"role": "user", "content": _build_user_prompt(transcript, topics_context)}]
    for attempt in range(2):
        messages = list(base_messages)
        if attempt == 1:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response could not be parsed. Call the "
                        "record_segments tool with valid arguments only."
                    ),
                }
            )
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SCRIBE_SYSTEM,
            tools=[SEGMENTS_TOOL],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=messages,
        )
        try:
            return parse_response(response)
        except ScribeParseError as exc:
            log.warning("scribe_parse_failed", attempt=attempt, error=str(exc))
    return None


async def segment_transcript(
    client: Any,
    *,
    transcript: str,
    topics_context: str,
    allowed_topic_ids: set[str],
    model: str,
    max_tokens: int = 8192,
) -> list[ScribeSegment]:
    """Full Scribe step: call Claude then validate/filter. [] if unparseable."""
    response = await call_scribe(
        client,
        transcript=transcript,
        topics_context=topics_context,
        model=model,
        max_tokens=max_tokens,
    )
    if response is None:
        return []
    return filter_segments(response, allowed_topic_ids)
