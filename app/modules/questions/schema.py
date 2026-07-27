"""Diagnostic item response models (DOC_02 §5).

Deliberately omits ``is_correct`` (and the post-answer ``explanation``) so the
placement test never ships answer keys to the client. DOC_04 owns scoring.
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel


class ChoiceOut(BaseModel):
    label: str
    text: str


class DiagnosticItemOut(BaseModel):
    # The question id is exposed (not an answer key) so DOC_04's answer endpoint
    # can reference the item; is_correct/explanation are still withheld.
    id: uuid.UUID
    order: int
    topic_id: str
    difficulty: str
    stem: str
    stem_code: str | None
    choices: list[ChoiceOut]
