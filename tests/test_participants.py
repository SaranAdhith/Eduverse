"""DOC_01 §8.4 acceptance tests for the identity API."""
from __future__ import annotations

import asyncio

from app.db import session_scope
from app.deps import get_participant, get_session
from app.modules.participants.model import Participant
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


async def test_enroll_then_resume_happy_path(client: AsyncClient) -> None:
    enroll = await client.post("/enroll", json={"consent_given": True})
    assert enroll.status_code == 201
    body = enroll.json()
    assert body["code"] == "P001"
    assert "id" in body
    # DOC_08 §3: block order is assigned at enrollment. P001 is the first cell.
    assert body["block_order"] == "AB"

    resume = await client.post("/resume", json={"code": "P001"})
    assert resume.status_code == 200
    resumed = resume.json()
    assert resumed["id"] == body["id"]
    assert resumed["code"] == "P001"
    assert resumed["block_order"] == "AB"  # assigned at enroll (DOC_08 §3)
    assert "enrolled_at" in resumed


async def test_enroll_requires_consent(client: AsyncClient) -> None:
    resp = await client.post("/enroll", json={"consent_given": False})
    assert resp.status_code == 400


async def test_codes_are_sequential(client: AsyncClient) -> None:
    codes = []
    for _ in range(3):
        resp = await client.post("/enroll", json={"consent_given": True})
        codes.append(resp.json()["code"])
    assert codes == ["P001", "P002", "P003"]


async def test_concurrent_enrolls_produce_distinct_codes(client: AsyncClient) -> None:
    """DOC_01 §8.4: concurrent enrolls must not collide on a code."""
    n = 10
    responses = await asyncio.gather(
        *(client.post("/enroll", json={"consent_given": True}) for _ in range(n))
    )
    assert all(r.status_code == 201 for r in responses)
    codes = {r.json()["code"] for r in responses}
    assert len(codes) == n
    assert codes == {f"P{i:03d}" for i in range(1, n + 1)}


async def test_resume_unknown_code_404(client: AsyncClient) -> None:
    resp = await client.post("/resume", json={"code": "P999"})
    assert resp.status_code == 404


async def test_persisted_row_has_consent(client: AsyncClient, session) -> None:  # type: ignore[no-untyped-def]
    await client.post("/enroll", json={"consent_given": True})
    from sqlalchemy import select

    row = await session.scalar(select(Participant).where(Participant.code == "P001"))
    assert row is not None
    assert row.consent_given is True
    assert row.consent_at is not None


# --- get_participant dependency: protected dummy endpoint (tests only). ---


def _protected_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(participant: Participant = Depends(get_participant)) -> dict[str, str]:
        return {"code": participant.code}

    async def _override_get_session():  # type: ignore[no-untyped-def]
        async for s in session_scope():
            yield s

    app.dependency_overrides[get_session] = _override_get_session
    return app


async def test_protected_endpoint_missing_header_401() -> None:
    transport = ASGITransport(app=_protected_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/protected")
    assert resp.status_code == 401


async def test_protected_endpoint_valid_header_ok(client: AsyncClient) -> None:
    # Enroll through the main client, then hit the protected app with the code.
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    transport = ASGITransport(app=_protected_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/protected", headers={"X-Participant-Code": code})
    assert resp.status_code == 200
    assert resp.json() == {"code": code}


async def test_protected_endpoint_invalid_header_401() -> None:
    transport = ASGITransport(app=_protected_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/protected", headers={"X-Participant-Code": "P404"})
    assert resp.status_code == 401
