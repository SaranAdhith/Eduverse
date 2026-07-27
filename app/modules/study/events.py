"""Event taxonomy + dual-write to the ``events`` table (DOC_08 §4).

Every ``log_event`` call already emits a JSONL line (DOC_01's structlog). This
module registers a sink that also buffers the event and writes it — batched, in
a write-behind background task every 500ms — to the durable ``events`` table, so
neither store losing a line loses the data.

The taxonomy below names every event fired across the codebase and its key
payload fields (DOC_08 §4). It is documentation-as-code: a ``TypedDict`` per
family whose keys mirror the columns an analyst reconstructs the study from.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict

import structlog
from app.db import session_scope
from app.logging import register_event_sink
from app.modules.participants.model import Participant
from app.modules.study.model import Event
from sqlalchemy import select

log = structlog.get_logger("study.events")

# Write-behind batching interval (DOC_08 §4).
FLUSH_INTERVAL_SECONDS = 0.5


# --------------------------------------------------------------------------- #
# Event taxonomy (DOC_08 §4) — one TypedDict per event family.
# --------------------------------------------------------------------------- #
class ParticipantEnrolled(TypedDict):
    block_order: str
    assignment_cell: int


class ResponseRecorded(TypedDict):
    question_id: str
    topic_id: str
    context: str
    selected_label: str
    is_correct: bool
    prior: float
    posterior: float
    response_ms: int | None


class PlannerDecision(TypedDict):
    path_id: str
    candidates: list[str]
    chosen_topic: str
    reasoning: str | None
    used_llm: bool


class GateAttemptCompleted(TypedDict):
    attempt_id: str
    score: float
    passed: bool
    posterior_at_gate: float


class ContentGenerated(TypedDict):
    topic_id: str
    content_version: int
    fallback: bool
    latency_ms: int | None


# The canonical set of event types used across the codebase (DOC_08 §4). Kept as
# a frozenset so tests and analysts can assert completeness; the DB stores
# whatever ``event_type`` string is emitted regardless.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "participant_enrolled",
        "diagnostic_started",
        "response_recorded",
        "diagnostic_completed",
        "mastery_propagated",
        "path_created",
        "planner_decision",
        "planner_llm_call",
        "planner_cache_hit",
        "planner_fallback",
        "planner_frontier_softened",
        "path_step_unlocked",
        "chunk_viewed",
        "idle",
        "gate_attempt_started",
        "gate_attempt_completed",
        "step_passed",
        "path_completed",
        "content_generated",
        "content_chunk_assembled",
        "content_regenerated",
        "content_pregeneration_complete",
        "lesson_generation_failed",
        "curation_run_finished",
    }
)


# --------------------------------------------------------------------------- #
# Write-behind buffer
# --------------------------------------------------------------------------- #
@dataclass
class _Pending:
    event_type: str
    ts: datetime
    participant_code: str | None
    participant_id: uuid.UUID | None
    request_id: uuid.UUID | None
    payload: dict[str, Any]


_BUFFER: list[_Pending] = []
_installed = False
_flusher: asyncio.Task[None] | None = None


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _sink(event_type: str, fields: dict[str, Any]) -> None:
    """Synchronous sink registered with ``app.logging`` — buffers one event."""
    ctx = structlog.contextvars.get_contextvars()
    # JSON round-trip so non-serialisable values (UUID, datetime) survive JSONB.
    payload = json.loads(json.dumps(fields, default=str))
    _BUFFER.append(
        _Pending(
            event_type=event_type,
            ts=datetime.now(UTC),
            participant_code=fields.get("participant_code") or ctx.get("participant_code"),
            participant_id=_coerce_uuid(fields.get("participant_id")),
            request_id=_coerce_uuid(ctx.get("request_id")),
            payload=payload,
        )
    )


def install() -> None:
    """Register the DB sink (idempotent). Called on package import + app startup."""
    global _installed
    if _installed:
        return
    register_event_sink(_sink)
    _installed = True


def reset() -> None:
    """Drop any buffered-but-unflushed events (used between tests)."""
    _BUFFER.clear()


# --------------------------------------------------------------------------- #
# Flush (DOC_08 §4)
# --------------------------------------------------------------------------- #
async def _resolve_participant_ids(
    session: Any, codes: set[str]
) -> dict[str, uuid.UUID]:
    if not codes:
        return {}
    rows = await session.execute(
        select(Participant.code, Participant.id).where(Participant.code.in_(codes))
    )
    return {code: pid for code, pid in rows.all()}


async def flush_events() -> int:
    """Write buffered events to the ``events`` table. Returns the count written."""
    if not _BUFFER:
        return 0
    pending = _BUFFER[:]
    del _BUFFER[: len(pending)]

    codes = {p.participant_code for p in pending if p.participant_code and not p.participant_id}
    async for session in session_scope():
        code_to_id = await _resolve_participant_ids(session, codes)
        session.add_all(
            [
                Event(
                    ts=p.ts,
                    participant_id=p.participant_id or code_to_id.get(p.participant_code or ""),
                    request_id=p.request_id,
                    event_type=p.event_type,
                    payload=p.payload,
                )
                for p in pending
            ]
        )
    return len(pending)


async def _flush_loop() -> None:  # pragma: no cover — timing loop
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
        try:
            await flush_events()
        except Exception as exc:  # noqa: BLE001 — the loop must survive a bad batch
            log.warning("event_flush_failed", error=str(exc))


def start_flusher() -> None:
    """Start the write-behind flush loop (app startup)."""
    global _flusher
    if _flusher is None or _flusher.done():
        _flusher = asyncio.create_task(_flush_loop())


async def stop_flusher() -> None:
    """Cancel the flush loop and drain the buffer (app shutdown)."""
    global _flusher
    if _flusher is not None:
        _flusher.cancel()
        _flusher = None
    await flush_events()
