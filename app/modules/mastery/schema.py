"""Pydantic in/out models for the mastery API (DOC_04 §2.4)."""
from __future__ import annotations

import uuid
from typing import Literal

from app.modules.questions.schema import DiagnosticItemOut
from pydantic import BaseModel


class StartDiagnosticResponse(BaseModel):
    """The session id served alongside the ordered diagnostic items."""

    session_id: uuid.UUID
    items_answered: int
    items: list[DiagnosticItemOut]


class AnswerRequest(BaseModel):
    session_id: uuid.UUID
    question_id: uuid.UUID
    selected_label: Literal["A", "B", "C", "D"]
    response_ms: int | None = None


class AnswerResponse(BaseModel):
    is_correct: bool
    explanation: str
    items_remaining: int


class MasteryEntry(BaseModel):
    topic_id: str
    topic_name: str
    tier: int
    p_mastered: float
    attempts: int


class MasteryVector(BaseModel):
    """Stable, sorted per-topic mastery vector for the frontend dashboard."""

    participant_code: str
    completed: bool
    entries: list[MasteryEntry]
