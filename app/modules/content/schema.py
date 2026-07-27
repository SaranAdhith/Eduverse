"""Content-assembly API schemas (DOC_06 §10).

``StepContentResponse`` is the learner-facing chunk: video deep-link + lesson +
topic context, and deliberately *no* quiz items or answer keys — the gate serves
those separately (DOC_06 §8). ``PreviewResponse`` is the admin-only view that
*does* include answer keys for content review.
"""
from __future__ import annotations

import uuid

from app.modules.questions.schema import ChoiceOut
from pydantic import BaseModel


class VideoDeepLink(BaseModel):
    video_id: str
    embed_url: str
    start_seconds: int
    end_seconds: int
    title: str
    channel_title: str
    sub_topic_label: str


class TopicContext(BaseModel):
    topic_id: str
    name: str
    description: str
    prerequisite_ids: list[str]


class StepContentResponse(BaseModel):
    chunk_id: uuid.UUID
    topic: TopicContext
    fallback: bool
    lesson_markdown: str
    video: VideoDeepLink | None


class PreviewChoiceOut(ChoiceOut):
    is_correct: bool


class PreviewQuizItem(BaseModel):
    position: int
    question_id: uuid.UUID
    difficulty: str
    stem: str
    stem_code: str | None
    explanation: str
    choices: list[PreviewChoiceOut]


class PreviewResponse(BaseModel):
    chunk_id: uuid.UUID
    topic_id: str
    content_version: int
    fallback: bool
    lesson_markdown: str
    quiz_items: list[PreviewQuizItem]
