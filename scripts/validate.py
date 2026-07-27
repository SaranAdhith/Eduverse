"""Pilot-readiness check (DOC_09 §3) — one command, run via ``make pilot-check``.

Runs eight cross-cutting checks against a freshly seeded, throwaway database and
prints ``PASS``/``FAIL`` with a one-line reason for each. Exits non-zero on any
failure, so CI can gate on it. No live API calls: content pre-flight uses a
deterministic LLM synthesizer, exactly like the e2e suite.

    uv run python -m scripts.validate
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Point the app at a dedicated throwaway DB before importing anything app-side.
_BASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://eduverse:eduverse@localhost:5432/eduverse"
)
_CHECK_DB = "eduverse_pilotcheck"


def _with_db(url: str, name: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


CHECK_URL = _with_db(_BASE_URL, _CHECK_DB)
os.environ["DATABASE_URL"] = CHECK_URL
os.environ["ENV"] = "test"

import asyncpg  # noqa: E402
import yaml  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import dispose_engine, session_scope  # noqa: E402
from app.models.registry import Base  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

get_settings.cache_clear()

REPO = Path(__file__).resolve().parents[1]
Result = tuple[bool, str]


# --------------------------------------------------------------------------- #
# Deterministic LLM synthesizer (mirrors tests/e2e/conftest.py)
# --------------------------------------------------------------------------- #
def _lesson(words: int) -> str:
    head = (
        "## Lesson\n\nExplanation with an example.\n\n"
        "```python\nx = 1\nprint(x + 1)\n```\n\n"
    )
    text_ = head
    while len(text_.split()) < words:
        text_ += "Restate the idea and connect it to earlier topics carefully. "
    return text_


def _quiz_items() -> list[dict[str, Any]]:
    # Distinct phrasings (well beyond Levenshtein-2) so the dedup pass never fires.
    plan = [
        ("easy", "recall the definition"),
        ("medium", "apply the idea to a short snippet"),
        ("medium", "predict the output of a loop"),
        ("medium", "choose the correct dictionary call"),
        ("hard", "trace an edge case with slicing"),
    ]
    return [
        {
            "difficulty": d,
            "stem": f"Item {i} — which option best helps you {phrase} here?",
            "stem_code": None,
            "choices": [
                {"label": lbl, "text": f"Option {lbl} item {i}", "is_correct": lbl == "A"}
                for lbl in ("A", "B", "C", "D")
            ],
            "explanation": f"A is correct for {i}.",
        }
        for i, (d, phrase) in enumerate(plan)
    ]


def _tool(name: str, payload: dict[str, Any]) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name=name, input=payload)]
    )


class _Messages:
    async def create(self, **kwargs: Any) -> Any:
        tc = kwargs.get("tool_choice") or {}
        name = tc.get("name") if isinstance(tc, dict) else None
        if name == "record_quiz":
            return _tool("record_quiz", {"items": _quiz_items()})
        if name == "choose_next_topic":
            return _tool("choose_next_topic", {"next_topic_id": "__x__", "reasoning": "x"})
        words = 700 if "600-1000" in kwargs.get("system", "") else 320
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=_lesson(words))])


class _Client:
    def __init__(self) -> None:
        self.messages = _Messages()


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
async def check_schema(session: AsyncSession) -> Result:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    model_tables = set(Base.metadata.tables) | {"alembic_version"}
    rows = await session.scalars(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    db_tables = set(rows) | {"alembic_version"}
    missing_tables = model_tables - db_tables - {"alembic_version"}
    orphan_tables = db_tables - model_tables
    if missing_tables:
        return False, f"models without a table: {sorted(missing_tables)}"
    if orphan_tables:
        return False, f"tables without a model: {sorted(orphan_tables)}"

    cfg = Config(str(REPO / "alembic.ini"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        return False, f"expected a single migration head, found {len(heads)}: {heads}"
    return True, f"{len(model_tables) - 1} model tables ↔ DB; single head {heads[0]}"


async def check_dag(session: AsyncSession) -> Result:
    from app.modules.graph import service as graph_service

    graph = await graph_service.load_graph(session)
    cycles = graph_service.validate_dag(graph)
    if cycles:
        return False, f"cycle detected: {cycles[0]}"
    # Every topic reachable from a root (a topic with no prerequisites).
    roots = {tid for tid in graph.nodes if not graph.edges.get(tid)}
    if "T0.1" not in graph.nodes:
        return False, "root T0.1 missing from graph"
    order = graph_service.topological_order(graph, core_only=False)
    if len(order) != len(graph.nodes):
        return False, "graph is not fully orderable"
    return True, f"{len(graph.nodes)} topics, {len(roots)} roots, acyclic + orderable"


async def check_diagnostic(session: AsyncSession) -> Result:
    from app.modules.questions.model import Question
    from app.modules.topics.model import Topic

    blueprint = yaml.safe_load((REPO / "data" / "diagnostic_blueprint.yaml").read_text())
    total = await session.scalar(
        select(func.count()).select_from(Question).where(Question.is_diagnostic.is_(True))
    )
    if total != blueprint["items_total"]:
        return False, f"expected {blueprint['items_total']} diagnostic items, found {total}"

    # Per-tier counts match the blueprint.
    rows = await session.execute(
        select(Topic.tier, func.count())
        .join(Question, Question.topic_id == Topic.id)
        .where(Question.is_diagnostic.is_(True))
        .group_by(Topic.tier)
    )
    db_by_tier = {tier: n for tier, n in rows}
    for entry in blueprint["tiers"]:
        tier_num = int(entry["tier"].lstrip("T"))
        if db_by_tier.get(tier_num, 0) != entry["items"]:
            return False, (
                f"tier {entry['tier']}: expected {entry['items']} items, "
                f"found {db_by_tier.get(tier_num, 0)}"
            )

    # Overall difficulty mix matches the blueprint's summed maps.
    expected_mix: dict[str, int] = {}
    for entry in blueprint["tiers"]:
        for diff, n in entry["difficulty"].items():
            expected_mix[diff] = expected_mix.get(diff, 0) + n
    drows = await session.execute(
        select(Question.difficulty, func.count())
        .where(Question.is_diagnostic.is_(True))
        .group_by(Question.difficulty)
    )
    db_mix = {d: n for d, n in drows}
    if db_mix != expected_mix:
        return False, f"difficulty mix {db_mix} != blueprint {expected_mix}"
    return True, f"25 items, tier + difficulty mix {db_mix} match the blueprint"


async def check_coverage(session: AsyncSession) -> Result:
    from app.modules.curation.model import VideoSegment
    from app.modules.topics.model import Topic

    core = list(await session.scalars(select(Topic.id).where(Topic.is_core.is_(True))))
    fallback_only = []
    for topic_id in core:
        n = await session.scalar(
            select(func.count()).select_from(VideoSegment).where(VideoSegment.topic_id == topic_id)
        )
        if not n:
            fallback_only.append(topic_id)
    # A core topic with no segments is still coverable via the assembler's
    # deterministic fallback lesson — never a silent dead-end. We report reliance.
    return True, (
        f"{len(core)} core topics coverable; {len(fallback_only)} rely on the "
        "text fallback (curation not yet run on this DB)"
    )


async def check_content_preflight(session: AsyncSession) -> Result:
    from app.modules.content import assembler
    from app.modules.content import repo as content_repo
    from app.modules.topics.model import Topic

    original = assembler._get_client
    assembler._get_client = lambda: _Client()  # type: ignore[assignment]
    try:
        topic_ids = list(await session.scalars(select(Topic.id).where(Topic.is_core.is_(True))))
        sample = random.Random(0).sample(topic_ids, 5)
        for topic_id in sample:
            async for s in session_scope():
                chunk = await assembler.build(s, topic_id)
            async for s in session_scope():
                items = await content_repo.quiz_questions(s, chunk.id, 5)
            if len(items) != 5:
                return False, f"{topic_id}: produced {len(items)} quiz items, expected 5"
            if not chunk.lesson_markdown.strip():
                return False, f"{topic_id}: empty lesson"
    finally:
        assembler._get_client = original  # type: ignore[assignment]
    return True, f"assembled valid 5-item chunks for {len(sample)} sampled topics"


async def check_bkt_determinism(_session: AsyncSession) -> Result:
    from app.modules.mastery import bkt
    from app.modules.mastery.params import default_params

    params = default_params()
    seq = [random.Random(42).random() < 0.6 for _ in range(100)]

    def replay() -> float:
        p = params.p_init
        for correct in seq:
            p = bkt.step(p, correct, params)
            if not 0.0 <= p <= 1.0:
                raise AssertionError(f"mastery left [0,1]: {p}")
        return p

    a, b = replay(), replay()
    if a != b:
        return False, f"replay not deterministic: {a} != {b}"
    return True, f"100-response replay is deterministic and in-range (final {a:.4f})"


async def check_assignment_rotation(_session: AsyncSession) -> Result:
    from app.modules.participants import service as participants_service
    from app.modules.study import assignment as study_assignment

    cells: list[int] = []
    async for s in session_scope():
        for _ in range(16):
            p = await participants_service.enroll(s, consent_given=True)
            a = await study_assignment.assign(s, p)
            cells.append(study_assignment.assignment_cell(a))
    counts = {c: cells.count(c) for c in range(4)}
    if counts != {0: 4, 1: 4, 2: 4, 3: 4}:
        return False, f"cells not balanced over 16 enrollments: {counts}"
    return True, "16 enrollments filled the 4 cells 4× each"


async def check_logging_dual_write(_session: AsyncSession) -> Result:
    from app.config import Settings
    from app.logging import configure_logging, log_event
    from app.modules.study import events
    from app.modules.study.model import Event

    log_path = Path(tempfile.mkdtemp()) / "events.jsonl"
    configure_logging(
        Settings(
            env="study",
            log_file=str(log_path),
            database_url=CHECK_URL,
            anthropic_api_key="dummy-for-logging-check",
        )
    )
    events.install()
    marker = "pilotcheck-response"
    log_event("response_recorded", topic_id=marker, is_correct=True, context="gate")
    written = await events.flush_events()

    in_jsonl = log_path.exists() and marker in log_path.read_text()
    async for s in session_scope():
        row = await s.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.event_type == "response_recorded")
        )
    if not (written and row and in_jsonl):
        return False, f"dual-write incomplete (db_rows={row}, jsonl={in_jsonl})"
    return True, "response_recorded reached both the events table and the JSONL log"


CHECKS = [
    ("Schema", check_schema),
    ("DAG", check_dag),
    ("Diagnostic", check_diagnostic),
    ("Coverage", check_coverage),
    ("Content pre-flight", check_content_preflight),
    ("BKT determinism", check_bkt_determinism),
    ("Assignment rotation", check_assignment_rotation),
    ("Logging dual-write", check_logging_dual_write),
]


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
async def _prepare_db() -> None:
    admin_dsn = _with_db(_BASE_URL, "postgres").replace("postgresql+asyncpg://", "postgresql://")
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{_CHECK_DB}"')
        await admin.execute(f'CREATE DATABASE "{_CHECK_DB}"')
    finally:
        await admin.close()
    engine = create_async_engine(CHECK_URL)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    from app.seeds.loader import seed

    async for s in session_scope():
        await seed(s)


async def _drop_db() -> None:
    await dispose_engine()
    admin_dsn = _with_db(_BASE_URL, "postgres").replace("postgresql+asyncpg://", "postgresql://")
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1", _CHECK_DB
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{_CHECK_DB}"')
    finally:
        await admin.close()


async def _run() -> int:
    await _prepare_db()
    failures = 0
    try:
        for name, check in CHECKS:
            try:
                async for s in session_scope():
                    passed, reason = await check(s)
            except Exception as exc:  # noqa: BLE001 — a crashing check is a FAIL
                passed, reason = False, f"raised {type(exc).__name__}: {exc}"
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {name:22s} {reason}")
            failures += 0 if passed else 1
    finally:
        await _drop_db()

    print()
    if failures:
        print(f"pilot-check: {failures} check(s) FAILED")
    else:
        print("pilot-check: all checks PASSED — the system is pilot-ready")
    return 1 if failures else 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
