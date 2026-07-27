"""Analysis export (DOC_08 §6).

Builds the tarball an analyst opens: per-participant CSVs (responses, mastery
trajectory, path steps, gate attempts), the raw event stream, and a column
dictionary. ``build_all`` aggregates every participant plus a top-level
``participants.csv`` with assignment info — the file the analyst opens first.
"""
from __future__ import annotations

import csv
import io
import json
import tarfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.modules.mastery.model import Response
from app.modules.participants.model import Participant
from app.modules.planner.model import GateAttempt, LearningPath, PathStep
from app.modules.study.model import Event, StudyAssignment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

README = """# Participant export

Column dictionary for this participant's analysis files (DOC_08 §6).

## participant.json
Enrollment + assignment metadata: code, enrolled_at, block_order, block_a_mode,
block_b_mode, assigned_at.

## responses.csv
Every scored answer (diagnostic and gate).
- created_at: when the answer was recorded
- context: diagnostic | gate | review
- topic_id, question_id, selected_label, is_correct, response_ms
- prior_mastery, posterior_mastery: BKT belief before/after this response

## mastery_trajectory.csv
Per-topic posterior over time, reconstructed from responses (one row per
response, in time order).
- ts, topic_id, context, prior_mastery, posterior_mastery

## path_steps.csv
One row per path step across both blocks.
- block, mode, topic_id, step_index, status, attempts, unlocked_at, passed_at

## gate_attempts.csv
Raw gate attempts.
- topic_id, attempt_id, started_at, completed_at, score, passed, posterior_at_gate

## events.jsonl
Full event stream for this participant (one JSON object per line).
"""


class ParticipantNotFoundError(Exception):
    """No participant with the requested code."""


def _csv(header: list[str], rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


@dataclass
class _ParticipantData:
    participant: Participant
    assignment: StudyAssignment | None
    responses: list[Response]
    paths: dict[Any, LearningPath]
    steps: list[PathStep]
    gate_attempts: list[GateAttempt]
    events: list[Event]


async def _load(session: AsyncSession, participant: Participant) -> _ParticipantData:
    assignment = await session.get(StudyAssignment, participant.id)
    responses = list(
        await session.scalars(
            select(Response)
            .where(Response.participant_id == participant.id)
            .order_by(Response.created_at, Response.id)
        )
    )
    paths = list(
        await session.scalars(
            select(LearningPath).where(LearningPath.participant_id == participant.id)
        )
    )
    path_by_id = {p.id: p for p in paths}
    steps = (
        list(
            await session.scalars(
                select(PathStep)
                .where(PathStep.path_id.in_([p.id for p in paths]))
                .order_by(PathStep.path_id, PathStep.step_index)
            )
        )
        if paths
        else []
    )
    step_ids = [s.id for s in steps]
    gate_attempts = list(
        await session.scalars(
            select(GateAttempt)
            .where(GateAttempt.path_step_id.in_(step_ids))
            .order_by(GateAttempt.started_at, GateAttempt.id)
        )
    ) if step_ids else []
    events = list(
        await session.scalars(
            select(Event)
            .where(Event.participant_id == participant.id)
            .order_by(Event.ts, Event.id)
        )
    )
    return _ParticipantData(
        participant=participant,
        assignment=assignment,
        responses=responses,
        paths=path_by_id,
        steps=steps,
        gate_attempts=gate_attempts,
        events=events,
    )


def _files_for(data: _ParticipantData) -> dict[str, bytes]:
    p = data.participant
    a = data.assignment
    participant_json = {
        "code": p.code,
        "id": str(p.id),
        "enrolled_at": _iso(p.enrolled_at),
        "block_order": p.block_order,
        "block_a_mode": a.block_a_mode if a else None,
        "block_b_mode": a.block_b_mode if a else None,
        "assigned_at": _iso(a.assigned_at) if a else None,
    }

    responses_csv = _csv(
        [
            "created_at", "context", "topic_id", "question_id", "selected_label",
            "is_correct", "response_ms", "prior_mastery", "posterior_mastery",
        ],
        [
            [
                _iso(r.created_at), r.context, r.topic_id, str(r.question_id),
                r.selected_label, r.is_correct, r.response_ms,
                r.prior_mastery, r.posterior_mastery,
            ]
            for r in data.responses
        ],
    )

    trajectory_csv = _csv(
        ["ts", "topic_id", "context", "prior_mastery", "posterior_mastery"],
        [
            [_iso(r.created_at), r.topic_id, r.context, r.prior_mastery, r.posterior_mastery]
            for r in data.responses
        ],
    )

    steps_csv = _csv(
        [
            "block", "mode", "topic_id", "step_index", "status", "attempts",
            "unlocked_at", "passed_at",
        ],
        [
            [
                data.paths[s.path_id].block, data.paths[s.path_id].mode, s.topic_id,
                s.step_index, s.status, s.attempts, _iso(s.unlocked_at), _iso(s.passed_at),
            ]
            for s in data.steps
        ],
    )

    gate_csv = _csv(
        [
            "topic_id", "attempt_id", "path_step_id", "started_at", "completed_at",
            "score", "passed", "posterior_at_gate",
        ],
        [
            [
                _step_topic(data, g.path_step_id), str(g.id), str(g.path_step_id),
                _iso(g.started_at), _iso(g.completed_at), g.score, g.passed, g.posterior_at_gate,
            ]
            for g in data.gate_attempts
        ],
    )

    events_jsonl = (
        "\n".join(
            json.dumps(
                {
                    "id": e.id,
                    "ts": _iso(e.ts),
                    "event_type": e.event_type,
                    "request_id": str(e.request_id) if e.request_id else None,
                    "payload": e.payload,
                }
            )
            for e in data.events
        )
        + ("\n" if data.events else "")
    ).encode("utf-8")

    return {
        "participant.json": json.dumps(participant_json, indent=2).encode("utf-8"),
        "responses.csv": responses_csv,
        "mastery_trajectory.csv": trajectory_csv,
        "path_steps.csv": steps_csv,
        "gate_attempts.csv": gate_csv,
        "events.jsonl": events_jsonl,
        "README.md": README.encode("utf-8"),
    }


def _step_topic(data: _ParticipantData, step_id: Any) -> str:
    for s in data.steps:
        if s.id == step_id:
            return s.topic_id
    return ""


def _add_files(tar: tarfile.TarFile, prefix: str, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        info = tarfile.TarInfo(name=f"{prefix}{name}")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))


async def build_participant(session: AsyncSession, code: str) -> bytes:
    """A gzip tarball for one participant (DOC_08 §6). Raises if code unknown."""
    participant = await session.scalar(
        select(Participant).where(Participant.code == code)
    )
    if participant is None:
        raise ParticipantNotFoundError(code)
    data = await _load(session, participant)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        _add_files(tar, f"{participant.code}/", _files_for(data))
    return buf.getvalue()


async def build_all(session: AsyncSession) -> bytes:
    """A gzip tarball of every participant plus a top-level participants.csv."""
    participants = list(
        await session.scalars(select(Participant).order_by(Participant.code))
    )
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        summary_rows: list[list[Any]] = []
        for participant in participants:
            data = await _load(session, participant)
            _add_files(tar, f"{participant.code}/", _files_for(data))
            a = data.assignment
            summary_rows.append(
                [
                    participant.code, str(participant.id), _iso(participant.enrolled_at),
                    participant.block_order,
                    a.block_a_mode if a else "", a.block_b_mode if a else "",
                    len(data.responses), len(data.steps),
                ]
            )
        participants_csv = _csv(
            [
                "code", "id", "enrolled_at", "block_order", "block_a_mode",
                "block_b_mode", "response_count", "step_count",
            ],
            summary_rows,
        )
        _add_files(tar, "", {"participants.csv": participants_csv})
    return buf.getvalue()
