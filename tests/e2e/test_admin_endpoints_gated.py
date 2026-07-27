"""Admin gating + no-leak invariants (DOC_09 §2.6).

Every admin endpoint is 401 without ``X-Admin-Token`` and reachable with it; no
participant-facing endpoint leaks an answer key or a planner reasoning string.
"""
from __future__ import annotations

from typing import Any

import pytest
from app.config import get_settings
from httpx import AsyncClient

ADMIN_ENDPOINTS_NO_TOKEN = [
    ("POST", "/admin/export?participant_code=P001"),
    ("POST", "/admin/export-all"),
    ("POST", "/topics/T2.1/content/regenerate"),
    ("GET", "/topics/T2.1/content/preview"),
]


@pytest.fixture
def admin_token(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Configure a non-empty admin token (empty disables admin access entirely)."""
    monkeypatch.setenv("ADMIN_TOKEN", "e2e-admin-secret")
    get_settings.cache_clear()
    yield "e2e-admin-secret"
    get_settings.cache_clear()


async def test_admin_endpoints_require_token(
    client: AsyncClient, seeded: None, mock_anthropic: Any, ensure_content: Any
) -> None:
    await client.post("/enroll", json={"consent_given": True})
    await ensure_content("T2.1")

    for method, path in ADMIN_ENDPOINTS_NO_TOKEN:
        resp = await client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} was not gated"


async def test_admin_endpoints_reachable_with_token(
    client: AsyncClient,
    seeded: None,
    mock_anthropic: Any,
    ensure_content: Any,
    admin_token: str,
) -> None:
    await client.post("/enroll", json={"consent_given": True})
    await ensure_content("T2.1")
    headers = {"X-Admin-Token": admin_token}

    export = await client.post("/admin/export?participant_code=P001", headers=headers)
    assert export.status_code == 200
    assert export.headers["content-type"] == "application/gzip"

    export_all = await client.post("/admin/export-all", headers=headers)
    assert export_all.status_code == 200

    regen = await client.post("/topics/T2.1/content/regenerate", headers=headers)
    assert regen.status_code == 200

    preview = await client.get("/topics/T2.1/content/preview", headers=headers)
    assert preview.status_code == 200
    # The admin preview *does* include answer keys (that's its purpose).
    assert "is_correct" in preview.text


async def test_participant_endpoints_do_not_leak_keys_or_reasoning(
    client: AsyncClient, seeded: None, mock_anthropic: Any, ensure_content: Any
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    headers = {"X-Participant-Code": code}

    # Diagnostic items: choices without an is_correct flag.
    items = (await client.post("/diagnostic/start", headers=headers)).json()["items"]
    for item in items:
        for choice in item["choices"]:
            assert "is_correct" not in choice
        assert "explanation" not in item  # key withheld until an answer is posted

    # The lesson a participant reads: no quiz, no answer key, no planner reasoning,
    # no mode label.
    created = (
        await client.post("/paths", headers=headers, json={"block": "A"})
    ).json()
    step_id = created["current_step"]["id"]
    await ensure_content(created["current_step"]["topic_id"])
    content = await client.get(f"/steps/{step_id}/content", headers=headers)
    assert content.status_code == 200
    body = content.text.lower()
    assert "is_correct" not in body
    assert "reasoning" not in body
    assert "quiz" not in body
