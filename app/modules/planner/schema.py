"""Pydantic in/out models for the planner + gate API (DOC_05 §8)."""
from __future__ import annotations

import uuid
from typing import Literal

from app.modules.questions.schema import ChoiceOut
from pydantic import BaseModel


class PathCreateRequest(BaseModel):
    block: Literal["A", "B"]
    # DOC_08 §3: mode is not user-selectable — it comes from the sealed study
    # assignment. If a client sends one it must match the assignment, else the
    # request is rejected. Optional so a well-behaved client can omit it entirely.
    mode: Literal["personalized", "fixed"] | None = None


class PathStepOut(BaseModel):
    id: uuid.UUID
    topic_id: str
    step_index: int
    status: str
    attempts: int
    planner_reasoning: str | None


class PathCreateResponse(BaseModel):
    path_id: uuid.UUID
    block: str
    mode: str
    current_step: PathStepOut | None


class PathCurrentResponse(BaseModel):
    path_id: uuid.UUID
    block: str
    mode: str
    completed: bool
    completion_pct: float
    passed_count: int
    total_topics: int
    current_step: PathStepOut | None
    steps: list[PathStepOut]


class AdvanceResponse(BaseModel):
    path_id: uuid.UUID
    completed: bool
    current_step: PathStepOut | None


class GateItemOut(BaseModel):
    id: uuid.UUID
    topic_id: str
    difficulty: str
    stem: str
    stem_code: str | None
    choices: list[ChoiceOut]


class GateStartResponse(BaseModel):
    attempt_id: uuid.UUID
    path_step_id: uuid.UUID
    topic_id: str
    items: list[GateItemOut]


class GateAnswerIn(BaseModel):
    question_id: uuid.UUID
    selected_label: Literal["A", "B", "C", "D"]
    response_ms: int | None = None


class GateSubmitRequest(BaseModel):
    answers: list[GateAnswerIn]


class GateResultResponse(BaseModel):
    passed: bool
    score: float
    posterior_at_gate: float
    step: PathStepOut
    next_step: PathStepOut | None
