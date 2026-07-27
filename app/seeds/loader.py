"""Idempotent seed loader CLI (DOC_02 §3).

    python -m app.seeds.loader seed    # validate YAML, then upsert in one txn
    python -m app.seeds.loader clear   # truncate catalog tables (dev only)

Every YAML file is pydantic-validated *before* the DB is touched, the whole
load runs in a single transaction, and ``validate_dag`` aborts the load if the
resulting graph is not acyclic.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import Literal

import structlog
import yaml
from pydantic import BaseModel, TypeAdapter, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_scope
from app.modules.graph import service as graph_service
from app.modules.questions.model import Choice, Question
from app.modules.topics.model import Topic, TopicPrerequisite

SEEDS_DIR = Path(__file__).parent

# Choice labels in position order; the correct answer is shuffled across these.
_DIAGNOSTIC_LABELS = ("A", "B", "C", "D")
log = structlog.get_logger("seed")


class SeedValidationError(Exception):
    """Raised when seed YAML fails validation; message names the offending row."""


# --------------------------------------------------------------------------- #
# Pydantic schemas — one per YAML file (DOC_02 §3.1)
# --------------------------------------------------------------------------- #
class TopicIn(BaseModel):
    id: str
    tier: int
    name: str
    slug: str
    description: str
    display_order: int
    is_core: bool = True


class PrereqIn(BaseModel):
    topic: str
    requires: list[str]


class ChoiceIn(BaseModel):
    label: Literal["A", "B", "C", "D"]
    text: str
    correct: bool


class ItemIn(BaseModel):
    order: int
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    stem: str
    stem_code: str | None = None
    choices: list[ChoiceIn]
    explanation: str

    @field_validator("choices")
    @classmethod
    def _exactly_one_correct(cls, choices: list[ChoiceIn]) -> list[ChoiceIn]:
        labels = [c.label for c in choices]
        if len(set(labels)) != len(labels):
            raise ValueError(f"duplicate choice labels: {labels}")
        n_correct = sum(c.correct for c in choices)
        if n_correct != 1:
            raise ValueError(f"exactly one correct choice required, found {n_correct}")
        return choices


def _read_yaml(name: str) -> object:
    path = SEEDS_DIR / name
    if not path.exists():
        raise SeedValidationError(f"missing seed file: {path}")
    return yaml.safe_load(path.read_text())


def load_and_validate() -> tuple[list[TopicIn], list[PrereqIn], list[ItemIn]]:
    """Parse + validate all seed files and cross-check references (DOC_02 §3)."""
    try:
        topics = TypeAdapter(list[TopicIn]).validate_python(_read_yaml("topics.yaml"))
        prereqs = TypeAdapter(list[PrereqIn]).validate_python(
            _read_yaml("prerequisites.yaml")
        )
        items = TypeAdapter(list[ItemIn]).validate_python(
            _read_yaml("diagnostic_items.yaml")
        )
    except Exception as exc:  # pydantic ValidationError et al.
        raise SeedValidationError(str(exc)) from exc

    topic_ids = {t.id for t in topics}

    # Unique topic ids and slugs.
    _check_unique([t.id for t in topics], "topics.yaml", "id")
    _check_unique([t.slug for t in topics], "topics.yaml", "slug")

    # Every prerequisite reference must exist (DOC_02 §3.6).
    for p in prereqs:
        if p.topic not in topic_ids:
            raise SeedValidationError(
                f"prerequisites.yaml: unknown topic '{p.topic}'"
            )
        for req in p.requires:
            if req not in topic_ids:
                raise SeedValidationError(
                    f"prerequisites.yaml: topic '{p.topic}' requires unknown "
                    f"topic '{req}'"
                )
            if req == p.topic:
                raise SeedValidationError(
                    f"prerequisites.yaml: topic '{p.topic}' lists itself as a "
                    f"prerequisite"
                )

    # Diagnostic items: unique 1..N orders, real topics.
    _check_unique(
        [i.order for i in items], "diagnostic_items.yaml", "order"
    )
    for item in items:
        if item.topic not in topic_ids:
            raise SeedValidationError(
                f"diagnostic_items.yaml: item order {item.order} maps to unknown "
                f"topic '{item.topic}'"
            )

    return topics, prereqs, items


def _check_unique(values: list[object], filename: str, field: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise SeedValidationError(
                f"{filename}: duplicate {field} '{value}'"
            )
        seen.add(value)


# --------------------------------------------------------------------------- #
# Upserts (DOC_02 §3.2–§3.5) — all inside one transaction
# --------------------------------------------------------------------------- #
async def _upsert_topics(session: AsyncSession, topics: list[TopicIn]) -> None:
    for t in topics:
        await session.merge(
            Topic(
                id=t.id,
                tier=t.tier,
                name=t.name,
                slug=t.slug,
                description=t.description.strip(),
                display_order=t.display_order,
                is_core=t.is_core,
            )
        )


async def _upsert_prerequisites(
    session: AsyncSession, prereqs: list[PrereqIn]
) -> None:
    for p in prereqs:
        for req in p.requires:
            await session.merge(
                TopicPrerequisite(topic_id=p.topic, prereq_id=req)
            )


async def _upsert_diagnostic_items(
    session: AsyncSession, items: list[ItemIn]
) -> None:
    for item in items:
        # Idempotent by diagnostic_order (globally unique among diagnostic items).
        question = await session.scalar(
            select(Question).where(Question.diagnostic_order == item.order)
        )
        if question is None:
            question = Question(diagnostic_order=item.order, is_diagnostic=True)
            session.add(question)
        question.topic_id = item.topic
        question.difficulty = item.difficulty
        question.stem = item.stem.strip()
        question.stem_code = item.stem_code.rstrip() if item.stem_code else None
        question.explanation = item.explanation.strip()
        question.is_diagnostic = True
        question.source = "seed"
        await session.flush()

        # The YAML authors the correct choice first (label A). Deterministically
        # permute which text lands on which label, seeded by the item order, so
        # the correct answer is spread across A-D instead of always being A —
        # stable across seed runs, still exactly one correct per item.
        payloads = [(ch.text, ch.correct) for ch in item.choices]
        random.Random(item.order).shuffle(payloads)
        for label, (text, correct) in zip(_DIAGNOSTIC_LABELS, payloads, strict=False):
            choice = await session.scalar(
                select(Choice).where(
                    Choice.question_id == question.id, Choice.label == label
                )
            )
            if choice is None:
                choice = Choice(question_id=question.id, label=label)
                session.add(choice)
            choice.text = text
            choice.is_correct = correct


async def seed(session: AsyncSession) -> dict[str, int]:
    """Validate + load all seed data, aborting on a graph cycle. Returns counts."""
    topics, prereqs, items = load_and_validate()

    # Flush between steps so FK targets (topics) exist before dependents
    # (prerequisites, questions) are inserted — the session has autoflush off.
    await _upsert_topics(session, topics)
    await session.flush()
    await _upsert_prerequisites(session, prereqs)
    await _upsert_diagnostic_items(session, items)
    await session.flush()

    # DOC_02 §4: the DAG must be valid on every load; abort (rollback) otherwise.
    graph = await graph_service.load_graph(session)
    graph_service.validate_dag(graph)

    return {
        "topics": len(topics),
        "prerequisites": sum(len(p.requires) for p in prereqs),
        "diagnostic_items": len(items),
    }


async def clear(session: AsyncSession) -> None:
    """Truncate the catalog tables. Blocked in ENV=study (DOC_02 §3)."""
    if get_settings().env == "study":
        raise RuntimeError("seed-clear is blocked when ENV=study")
    await session.execute(
        text(
            "TRUNCATE choices, questions, topic_prerequisites, topics "
            "RESTART IDENTITY CASCADE"
        )
    )


async def _run(command: str) -> None:
    async for session in session_scope():
        if command == "seed":
            counts = await seed(session)
            log.info("seed_complete", **counts)
            print(f"seeded: {counts}")
        elif command == "clear":
            await clear(session)
            log.info("seed_cleared")
            print("catalog tables truncated")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eduverse seed loader (DOC_02)")
    parser.add_argument("command", choices=["seed", "clear"])
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.command))
    except Exception as exc:  # noqa: BLE001 — surface any load failure cleanly
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
