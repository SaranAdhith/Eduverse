"""Async test fixtures for the DOC_01 backend (test client + DB session).

Tests run against a real Postgres (they exercise ``gen_random_uuid()`` and
``pg_advisory_xact_lock``), using a dedicated ``*_test`` database that is
created and schema-initialised on demand.

Requires ``make db-up`` (or any Postgres reachable via DATABASE_URL). The DOC_00
data tests (``test_bkt`` etc.) are stdlib-only and ignore all of this.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# --- Point the app at a dedicated test database BEFORE importing it. ---
_BASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://eduverse:eduverse@localhost:5432/eduverse",
)
_TEST_DB = "eduverse_test"


def _with_db_name(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{db_name}"))


def _to_asyncpg_dsn(url: str) -> str:
    """asyncpg.connect wants a plain postgres:// DSN, not the +asyncpg driver."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


TEST_DATABASE_URL = _with_db_name(_BASE_URL, _TEST_DB)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENV"] = "test"

from app.config import get_settings  # noqa: E402
from app.db import dispose_engine, session_scope  # noqa: E402
from app.deps import get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.registry import Base  # noqa: E402

get_settings.cache_clear()

_schema_ready = False


async def _prepare_schema() -> None:
    """Create the test DB + extensions + tables once, then truncate per test."""
    global _schema_ready
    if not _schema_ready:
        admin = await asyncpg.connect(_to_asyncpg_dsn(_with_db_name(_BASE_URL, "postgres")))
        try:
            if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", _TEST_DB):
                await admin.execute(f'CREATE DATABASE "{_TEST_DB}"')
        finally:
            await admin.close()

        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        _schema_ready = True

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE events, study_assignments, llm_cache, "
            "chunk_quiz_items, content_chunks, "
            "gate_attempts, path_steps, learning_paths, "
            "responses, mastery, diagnostic_sessions, "
            "video_segments, video_resources, topic_video_coverage, "
            "choices, questions, topic_prerequisites, topics, "
            "participants RESTART IDENTITY CASCADE;"
        )
    await engine.dispose()
    # DOC_08 §4: drop any events buffered-but-unflushed by a prior test so they
    # don't leak into this test's freshly-truncated events table.
    from app.modules.study import events as study_events

    study_events.reset()


@pytest_asyncio.fixture(autouse=True)
async def _clean_db() -> AsyncIterator[None]:
    await _prepare_schema()
    yield
    # pytest-asyncio gives each test its own event loop; dispose the app's
    # cached global engine so the next test recreates it on its own loop.
    await dispose_engine()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A standalone session for assertions inside tests."""
    engine = create_async_engine(TEST_DATABASE_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded() -> AsyncIterator[None]:
    """Load the DOC_02 catalog (topics/prereqs/diagnostic bank) into the test DB."""
    from app.seeds.loader import seed

    engine = create_async_engine(TEST_DATABASE_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await seed(s)
        await s.commit()
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """httpx client wired to the ASGI app, using the test DB session."""
    app = create_app()

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async for s in session_scope():
            yield s

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
