"""Pydantic models for the study API (DOC_08 §5, §6)."""
from __future__ import annotations

import uuid

from pydantic import BaseModel


class AssignmentOut(BaseModel):
    participant_id: uuid.UUID
    block_order: str
    block_a_mode: str
    block_b_mode: str


class ChunkViewEvent(BaseModel):
    step_id: uuid.UUID
    video_seconds_watched: float | None = None
    phase: str | None = None  # 'load' | 'unload' | 'video_end'


class IdleEvent(BaseModel):
    step_id: uuid.UUID | None = None
    idle_seconds: float | None = None


class EventAck(BaseModel):
    ok: bool = True
