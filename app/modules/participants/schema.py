"""Pydantic in/out models for the identity API (DOC_01 §6)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EnrollRequest(BaseModel):
    consent_given: bool


class EnrollResponse(BaseModel):
    code: str
    id: uuid.UUID
    # The participant's assigned block order (DOC_08 §3); mode stays hidden.
    block_order: str | None = None


class ResumeRequest(BaseModel):
    code: str


class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    enrolled_at: datetime
    block_order: str | None = None
