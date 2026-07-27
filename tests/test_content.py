"""DOC_06 §11 content-assembly tests — fully offline (mocked Claude).

The assembler is exercised against real Postgres (it uses ``pg_advisory_xact_lock``
and the ``content_chunks`` unique constraint); every Claude call is faked via
``assembler._get_client`` so no network call is made.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.modules.content import assembler, quiz, repo
from app.modules.content import service as content_service
from app.modules.content.model import ChunkQuizItem, ContentChunk
from app.modules.curation.model import VideoResource, VideoSegment
from app.modules.participants import service as participants_service
from app.modules.planner import repo as planner_repo
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

TOPIC = "T2.1"


# --------------------------------------------------------------------------- #
# Fake Claude
# --------------------------------------------------------------------------- #
def _make_lesson(min_words: int) -> str:
    md = (
        "## Understanding the topic\n\n"
        "This lesson frames the concept and shows a minimal example.\n\n"
        "```python\n"
        "value = [1, 2, 3]\n"
        "print(len(value))\n"
        "```\n\n"
    )
    sentence = "We connect this idea to what you already know and what comes next. "
    while len(md.split()) < min_words:
        md += sentence
    return md


def _default_lesson(system: str, _call: int) -> str:
    # FALLBACK_SYSTEM starts with "You write standalone lessons"; it needs the
    # longer 600-1000 word budget.
    if "standalone" in system:
        return _make_lesson(650)
    return _make_lesson(300)


def _choices(correct: str = "A") -> list[dict[str, Any]]:
    return [
        {"label": label, "text": f"choice {label}", "is_correct": label == correct}
        for label in ("A", "B", "C", "D")
    ]


def _valid_items() -> list[dict[str, Any]]:
    stems = [
        ("easy", "What is the core idea here?"),
        ("medium", "How do you apply the first pattern?"),
        ("medium", "Which output does the second snippet produce?"),
        ("medium", "When would the third approach fail?"),
        ("hard", "Trace the final code and give its result."),
    ]
    return [
        {
            "difficulty": diff,
            "stem": stem,
            "stem_code": None,
            "choices": _choices(),
            "explanation": "because that is how it works",
        }
        for diff, stem in stems
    ]


def _default_quiz(_call: int) -> list[dict[str, Any]]:
    return _valid_items()


class _FakeMessages:
    def __init__(self, lesson_fn: Any, quiz_fn: Any) -> None:
        self._lesson_fn = lesson_fn
        self._quiz_fn = quiz_fn
        self.lesson_calls = 0
        self.quiz_calls = 0

    async def create(self, **kwargs: Any) -> Any:
        if "tools" in kwargs:
            items = self._quiz_fn(self.quiz_calls)
            self.quiz_calls += 1
            block = SimpleNamespace(
                type="tool_use", name="record_quiz", input={"items": items}
            )
            return SimpleNamespace(content=[block])
        text = self._lesson_fn(kwargs.get("system", ""), self.lesson_calls)
        self.lesson_calls += 1
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self, *, lesson_fn: Any = _default_lesson, quiz_fn: Any = _default_quiz):
        self.messages = _FakeMessages(lesson_fn, quiz_fn)


@pytest.fixture
def fake_claude(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    fake = FakeClient()
    monkeypatch.setattr(assembler, "_get_client", lambda: fake)
    return fake


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _seed_video(session: AsyncSession, topic_id: str) -> VideoSegment:
    video = VideoResource(
        video_id="dQw4w9WgXcQ",
        channel_id="UC_test",
        channel_title="Test Channel",
        title="A great Python tutorial",
        duration_seconds=1200,
        has_captions=True,
    )
    session.add(video)
    await session.flush()
    segment = VideoSegment(
        video_id=video.id,
        topic_id=topic_id,
        start_seconds=60,
        end_seconds=60 + 6 * 60,  # 6 minutes -> in the sweet spot
        sub_topic_label="the key sub-topic",
        transcript="hello world transcript",
        quality_score=0.9,
    )
    session.add(segment)
    await session.flush()
    return segment


async def _chunk_count(session: AsyncSession, topic_id: str) -> int:
    total = await session.scalar(
        select(func.count()).select_from(ContentChunk).where(
            ContentChunk.topic_id == topic_id
        )
    )
    return total or 0


# --------------------------------------------------------------------------- #
# §11.1 — idempotent build
# --------------------------------------------------------------------------- #
async def test_build_is_idempotent(
    session: AsyncSession, seeded: None, fake_claude: FakeClient
) -> None:
    first = await assembler.build(session, TOPIC)
    second = await assembler.build(session, TOPIC)

    assert first.id == second.id
    assert await _chunk_count(session, TOPIC) == 1
    # Second call served from cache — no extra Claude calls.
    assert fake_claude.messages.lesson_calls == 1
    assert fake_claude.messages.quiz_calls == 1


# --------------------------------------------------------------------------- #
# §11.2 — invalid lesson retries then falls back to a template skeleton
# --------------------------------------------------------------------------- #
async def test_invalid_lesson_falls_back_to_template(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from structlog.testing import capture_logs

    # Lesson output has no code block and is too short -> fails validation twice.
    fake = FakeClient(lesson_fn=lambda _system, _call: "just a sentence, no code")
    monkeypatch.setattr(assembler, "_get_client", lambda: fake)

    with capture_logs() as logs:
        chunk = await assembler.build(session, TOPIC)

    assert chunk is not None
    assert "```" in chunk.lesson_markdown  # template skeleton has a code block
    assert fake.messages.lesson_calls == 2  # retried once before falling back
    assert any(e.get("event_type") == "lesson_generation_failed" for e in logs)
    assert await _chunk_count(session, TOPIC) == 1


# --------------------------------------------------------------------------- #
# §11.3 — fallback topic (no video) gets fallback=true, no segment, longer lesson
# --------------------------------------------------------------------------- #
async def test_fallback_topic_has_no_video_and_longer_lesson(
    session: AsyncSession, seeded: None, fake_claude: FakeClient
) -> None:
    # No video segments seeded for TOPIC -> fallback path.
    chunk = await assembler.build(session, TOPIC)

    assert chunk.fallback is True
    assert chunk.video_segment_id is None
    # Fallback lesson uses the 600-1000 word budget: much longer than with-video.
    assert len(chunk.lesson_markdown.split()) > 400


async def test_with_video_chunk_links_segment(
    session: AsyncSession, seeded: None, fake_claude: FakeClient
) -> None:
    segment = await _seed_video(session, TOPIC)
    chunk = await assembler.build(session, TOPIC)

    assert chunk.fallback is False
    assert chunk.video_segment_id == segment.id
    # With-video lesson is the shorter framing variant.
    assert len(chunk.lesson_markdown.split()) <= 440


# --------------------------------------------------------------------------- #
# §11.4 — quiz shape: 5 items, one link each, one correct each, 1/3/1 mix
# --------------------------------------------------------------------------- #
async def test_quiz_items_are_well_formed(
    session: AsyncSession, seeded: None, fake_claude: FakeClient
) -> None:
    chunk = await assembler.build(session, TOPIC)

    links = list(
        await session.scalars(
            select(ChunkQuizItem)
            .where(ChunkQuizItem.chunk_id == chunk.id)
            .order_by(ChunkQuizItem.position)
        )
    )
    assert len(links) == 5
    assert [link.position for link in links] == [1, 2, 3, 4, 5]

    questions = await repo.quiz_questions(session, chunk.id, limit=10)
    assert len(questions) == 5
    mix: dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    for q in questions:
        assert q.source == "generated"
        assert q.is_diagnostic is False
        assert sum(1 for c in q.choices if c.is_correct) == 1
        assert len(q.choices) == 4
        mix[q.difficulty] += 1
    assert mix == {"easy": 1, "medium": 3, "hard": 1}


# --------------------------------------------------------------------------- #
# §11.5 — near-duplicate stems trigger regeneration of the affected item
# --------------------------------------------------------------------------- #
async def test_near_duplicate_stem_is_regenerated(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def quiz_fn(call: int) -> list[dict[str, Any]]:
        if call == 0:
            items = _valid_items()
            # Make item 3's stem a Levenshtein-1 near-dup of item 2's stem.
            items[2]["stem"] = items[1]["stem"] + "?"
            return items
        # Regeneration request -> a single distinct replacement (same difficulty).
        return [
            {
                "difficulty": "medium",
                "stem": "A completely different fresh question about lists.",
                "stem_code": None,
                "choices": _choices(),
                "explanation": "distinct item",
            }
        ]

    fake = FakeClient(quiz_fn=quiz_fn)
    monkeypatch.setattr(assembler, "_get_client", lambda: fake)

    chunk = await assembler.build(session, TOPIC)
    questions = await repo.quiz_questions(session, chunk.id, limit=10)

    stems = [quiz._normalize_stem(q.stem) for q in questions]
    assert len(set(stems)) == 5  # no near-duplicates survived
    assert fake.messages.quiz_calls == 2  # batch + one regeneration call


# --------------------------------------------------------------------------- #
# §11.6 — GET /steps/{id}/content never leaks answer keys
# --------------------------------------------------------------------------- #
async def test_step_content_endpoint_hides_answer_keys(
    client: AsyncClient,
    seeded: None,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeClient()
    monkeypatch.setattr(assembler, "_get_client", lambda: fake)

    participant = await participants_service.enroll(session, consent_given=True)
    path = await planner_repo.create_path(session, participant.id, "A", "fixed")
    step = await planner_repo.create_step(
        session,
        path_id=path.id,
        topic_id=TOPIC,
        step_index=0,
        status="in_progress",
        planner_reasoning=None,
    )
    await _seed_video(session, TOPIC)
    await assembler.build(session, TOPIC)
    await session.commit()

    resp = await client.get(
        f"/steps/{step.id}/content", headers={"X-Participant-Code": participant.code}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "is_correct" not in resp.text
    assert body["video"]["embed_url"].startswith(
        "https://www.youtube.com/embed/dQw4w9WgXcQ"
    )
    assert "start=" in body["video"]["embed_url"] and "end=" in body["video"]["embed_url"]
    assert body["lesson_markdown"]
    assert body["fallback"] is False


async def test_step_content_404_before_assembly(
    client: AsyncClient, seeded: None, session: AsyncSession
) -> None:
    participant = await participants_service.enroll(session, consent_given=True)
    path = await planner_repo.create_path(session, participant.id, "A", "fixed")
    step = await planner_repo.create_step(
        session,
        path_id=path.id,
        topic_id=TOPIC,
        step_index=0,
        status="in_progress",
        planner_reasoning=None,
    )
    await session.commit()

    resp = await client.get(
        f"/steps/{step.id}/content", headers={"X-Participant-Code": participant.code}
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# §11.7 — creating a path pre-generates the first 3 chunks
# --------------------------------------------------------------------------- #
async def test_path_creation_pregenerates_chunks(
    session: AsyncSession, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.planner import service as planner_service

    fake = FakeClient()
    monkeypatch.setattr(assembler, "_get_client", lambda: fake)

    participant = await participants_service.enroll(session, consent_given=True)
    await session.commit()

    await planner_service.create_path(session, participant, block="A", mode="fixed")
    await content_service.drain_pregeneration()

    total = await session.scalar(select(func.count()).select_from(ContentChunk))
    assert total == 3


# --------------------------------------------------------------------------- #
# §12 acceptance — regenerate bumps the version; the gate reads chunk items
# --------------------------------------------------------------------------- #
async def test_regenerate_bumps_version_without_overwriting(
    session: AsyncSession, seeded: None, fake_claude: FakeClient
) -> None:
    first = await assembler.build(session, TOPIC)
    assert first.content_version == 1

    second = await content_service.regenerate(session, TOPIC)
    assert second.content_version == 2
    assert second.id != first.id
    assert await _chunk_count(session, TOPIC) == 2
    # get_current_chunk resolves to the newest version.
    current = await repo.get_current_chunk(session, TOPIC)
    assert current is not None and current.content_version == 2


async def test_gate_reads_chunk_quiz_items(
    session: AsyncSession, seeded: None, fake_claude: FakeClient
) -> None:
    chunk = await assembler.build(session, TOPIC)
    generated_ids = {
        link.question_id
        for link in await session.scalars(
            select(ChunkQuizItem).where(ChunkQuizItem.chunk_id == chunk.id)
        )
    }

    items = await planner_repo.gate_items(session, TOPIC, 5)
    assert len(items) == 5
    assert {q.id for q in items} == generated_ids


async def test_admin_preview_includes_answer_keys(
    client: AsyncClient,
    seeded: None,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.content.router.get_settings", _admin_settings)
    fake = FakeClient()
    monkeypatch.setattr(assembler, "_get_client", lambda: fake)
    await assembler.build(session, TOPIC)
    await session.commit()

    # Without the token -> 401.
    unauth = await client.get(f"/topics/{TOPIC}/content/preview")
    assert unauth.status_code == 401

    resp = await client.get(
        f"/topics/{TOPIC}/content/preview", headers={"X-Admin-Token": "s3cret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["quiz_items"]) == 5
    for item in body["quiz_items"]:
        assert sum(1 for c in item["choices"] if c["is_correct"]) == 1


def _admin_settings() -> Any:
    from app.config import Settings

    return Settings(admin_token="s3cret")
