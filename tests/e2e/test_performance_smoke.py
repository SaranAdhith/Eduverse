"""Single-user performance smoke test (DOC_09 §5).

Not load testing — a single participant, timing the key endpoints to catch
*order-of-magnitude* regressions. The DOC_09 §5 production budgets are noted per
check; the asserted ceilings are deliberately looser (they run on a shared dev DB
with full request overhead) so the test flags a 10× regression, not jitter.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from app.modules.questions.model import Choice
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _min_ms(coro_factory: Any, runs: int = 3) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        await coro_factory()
        best = min(best, (time.perf_counter() - start) * 1000)
    return best


async def test_endpoint_latency_budgets(
    client: AsyncClient,
    session: AsyncSession,
    seeded: None,
    mock_anthropic: Any,
    ensure_content: Any,
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    headers = {"X-Participant-Code": code}

    # GET /diagnostic/items — budget 200ms p95; ceiling 1000ms.
    got = await _min_ms(lambda: client.get("/diagnostic/items", headers=headers))
    assert got < 1000, f"/diagnostic/items {got:.0f}ms"

    # POST /diagnostic/answer — budget 300ms (no LLM); ceiling 1500ms.
    start = (await client.post("/diagnostic/start", headers=headers)).json()
    first = start["items"][0]
    label = await session.scalar(
        select(Choice.label).where(
            Choice.question_id == uuid.UUID(first["id"]),
            Choice.is_correct.is_(True),
        )
    )
    t0 = time.perf_counter()
    answer = await client.post(
        "/diagnostic/answer",
        headers=headers,
        json={
            "session_id": start["session_id"],
            "question_id": first["id"],
            "selected_label": label,
            "response_ms": 100,
        },
    )
    answer_ms = (time.perf_counter() - t0) * 1000
    assert answer.status_code == 200
    assert answer_ms < 1500, f"/diagnostic/answer {answer_ms:.0f}ms"

    # POST /paths — budget 5s (pre-warms 3 chunks); ceiling 15s.
    t0 = time.perf_counter()
    created = await client.post("/paths", headers=headers, json={"block": "A"})
    paths_ms = (time.perf_counter() - t0) * 1000
    assert created.status_code == 201
    assert paths_ms < 15_000, f"/paths {paths_ms:.0f}ms"
    step = created.json()["current_step"]

    # GET /steps/{id}/content (cache hit) — budget 100ms; ceiling 1000ms.
    await ensure_content(step["topic_id"])
    content_ms = await _min_ms(
        lambda: client.get(f"/steps/{step['id']}/content", headers=headers)
    )
    assert content_ms < 1000, f"/steps/content {content_ms:.0f}ms"

    # Gate submission round-trip — budget 400ms; ceiling 2000ms.
    started = (
        await client.post(f"/steps/{step['id']}/gate/start", headers=headers)
    ).json()
    answers = []
    for item in started["items"]:
        correct = await session.scalar(
            select(Choice.label).where(
                Choice.question_id == uuid.UUID(item["id"]),
                Choice.is_correct.is_(True),
            )
        )
        answers.append({"question_id": item["id"], "selected_label": correct})
    t0 = time.perf_counter()
    submit = await client.post(
        f"/steps/{step['id']}/gate/submit", headers=headers, json={"answers": answers}
    )
    gate_ms = (time.perf_counter() - t0) * 1000
    assert submit.status_code == 200
    assert gate_ms < 2000, f"gate submit {gate_ms:.0f}ms"
