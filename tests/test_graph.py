"""DOC_02 §6 tests: knowledge graph, loader, and diagnostic bank."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml
from app.modules.graph import service
from app.modules.graph.errors import GraphIntegrityError
from app.modules.questions.model import Choice, Question
from app.modules.topics.model import Topic
from app.seeds.loader import SeedValidationError, load_and_validate, seed
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

BLUEPRINT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "diagnostic_blueprint.yaml"
)

# Expected transitive closure of T6.3 (Decorators), computed from DOC_00 §1.
T63_ANCESTORS = {"T3.1", "T3.4", "T3.6", "T1.1", "T1.2", "T0.3", "T0.2", "T0.1"}


# --------------------------------------------------------------------------- #
# 1. Loader idempotency
# --------------------------------------------------------------------------- #
async def test_loader_is_idempotent(session: AsyncSession, seeded: None) -> None:
    # `seeded` already loaded once; load again and assert no duplication.
    await seed(session)
    await session.commit()

    n_topics = await session.scalar(select(func.count()).select_from(Topic))
    n_questions = await session.scalar(select(func.count()).select_from(Question))
    n_choices = await session.scalar(select(func.count()).select_from(Choice))

    assert n_topics == 47
    assert n_questions == 25
    assert n_choices == 100  # 25 items * 4 choices


# --------------------------------------------------------------------------- #
# 2. Cycle detection
# --------------------------------------------------------------------------- #
async def test_cycle_injection_raises(session: AsyncSession, seeded: None) -> None:
    graph = await service.load_graph(session)
    # Inject T0.1 -> T0.2 -> T0.1 (T0.2 -> T0.1 already exists).
    graph.edges["T0.1"].add("T0.2")

    with pytest.raises(GraphIntegrityError):
        service.validate_dag(graph)
    with pytest.raises(GraphIntegrityError):
        service.topological_order(graph, core_only=False)


# --------------------------------------------------------------------------- #
# 3. Transitive prerequisites
# --------------------------------------------------------------------------- #
async def test_transitive_prerequisites(session: AsyncSession, seeded: None) -> None:
    graph = await service.load_graph(session)
    assert service.prerequisites(graph, "T6.3") == {"T3.1", "T3.4", "T3.6"}
    assert service.transitive_prerequisites(graph, "T6.3") == T63_ANCESTORS


# --------------------------------------------------------------------------- #
# 4. Frontier from empty mastery
# --------------------------------------------------------------------------- #
async def test_frontier_empty_mastery(session: AsyncSession, seeded: None) -> None:
    graph = await service.load_graph(session)
    assert service.frontier(graph, set()) == {"T0.1"}


# --------------------------------------------------------------------------- #
# 5. Deterministic topological order
# --------------------------------------------------------------------------- #
async def test_topological_order_deterministic(
    session: AsyncSession, seeded: None
) -> None:
    graph = await service.load_graph(session)
    order1 = service.topological_order(graph, core_only=True)
    order2 = service.topological_order(graph, core_only=True)
    assert order1 == order2
    assert order1[0] == "T0.1"

    # Every prerequisite precedes its dependent.
    position = {tid: i for i, tid in enumerate(order1)}
    for tid in order1:
        for prereq in graph.edges[tid]:
            assert position[prereq] < position[tid]


# --------------------------------------------------------------------------- #
# 6. Diagnostic bank shape + blueprint conformance
# --------------------------------------------------------------------------- #
async def test_diagnostic_bank_conforms_to_blueprint(
    session: AsyncSession, seeded: None
) -> None:
    questions = list(
        await session.scalars(
            select(Question).where(Question.is_diagnostic.is_(True))
        )
    )
    assert len(questions) == 25

    orders = sorted(q.diagnostic_order for q in questions)
    assert orders == list(range(1, 26))  # 1..25 each exactly once

    topic_tier = dict(
        (await session.execute(select(Topic.id, Topic.tier))).all()
    )

    for q in questions:
        assert q.topic_id in topic_tier  # maps to a real topic
        choices = list(
            await session.scalars(select(Choice).where(Choice.question_id == q.id))
        )
        assert sum(c.is_correct for c in choices) == 1  # exactly one correct

    # Tier/difficulty mix must match DOC_00 §2.
    blueprint = yaml.safe_load(BLUEPRINT_PATH.read_text())
    expected_items = {f"T{b['tier'][1:]}": b["items"] for b in blueprint["tiers"]}
    expected_diff: Counter[tuple[str, str]] = Counter()
    for b in blueprint["tiers"]:
        tier_key = f"T{b['tier'][1:]}"
        for diff, count in b["difficulty"].items():
            expected_diff[(tier_key, diff)] = count

    actual_items: Counter[str] = Counter()
    actual_diff: Counter[tuple[str, str]] = Counter()
    for q in questions:
        tier_key = f"T{topic_tier[q.topic_id]}"
        actual_items[tier_key] += 1
        actual_diff[(tier_key, q.difficulty)] += 1

    assert dict(actual_items) == expected_items
    assert actual_diff == expected_diff


# --------------------------------------------------------------------------- #
# 7. Endpoint: /diagnostic/items never leaks answer keys
# --------------------------------------------------------------------------- #
async def test_diagnostic_items_endpoint_hides_answers(
    client: AsyncClient, seeded: None
) -> None:
    code = (await client.post("/enroll", json={"consent_given": True})).json()["code"]
    resp = await client.get(
        "/diagnostic/items", headers={"X-Participant-Code": code}
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 25
    assert [i["order"] for i in items] == list(range(1, 26))
    for item in items:
        for choice in item["choices"]:
            assert set(choice.keys()) == {"label", "text"}  # no is_correct
        assert "explanation" not in item


async def test_diagnostic_items_requires_participant(
    client: AsyncClient, seeded: None
) -> None:
    resp = await client.get("/diagnostic/items")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Graph endpoints (DOC_02 §5, acceptance §7.3–7.4)
# --------------------------------------------------------------------------- #
async def test_graph_endpoint_node_counts(client: AsyncClient, seeded: None) -> None:
    full = (await client.get("/graph")).json()
    assert len(full["nodes"]) == 47

    core = (await client.get("/graph", params={"is_core_only": True})).json()
    assert len(core["nodes"]) == 38  # 47 minus 9 non-core (T6.6, T7.*, T8.*)
    assert all(n["is_core"] for n in core["nodes"])


async def test_topics_endpoints(client: AsyncClient, seeded: None) -> None:
    page = await client.get("/topics", params={"tier": 0})
    body = page.json()
    assert body["total"] == 5  # tier 0 has 5 topics
    assert {t["id"] for t in body["items"]} == {"T0.1", "T0.2", "T0.3", "T0.4", "T0.5"}

    one = (await client.get("/topics/T6.3")).json()
    assert one["slug"] == "decorators"
    assert set(one["prerequisites"]) == {"T3.1", "T3.4", "T3.6"}

    missing = await client.get("/topics/T9.9")
    assert missing.status_code == 404


# --------------------------------------------------------------------------- #
# 5b (acceptance §7.5). Loader rejects corrupted YAML with a precise message.
# --------------------------------------------------------------------------- #
def test_loader_rejects_duplicate_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.seeds.loader as loader_mod

    good = load_and_validate()[2]
    corrupted = [i.model_dump() for i in good]
    corrupted[1]["order"] = corrupted[0]["order"]  # duplicate diagnostic order

    real_read = loader_mod._read_yaml

    def fake_read(name: str) -> object:
        if name == "diagnostic_items.yaml":
            return corrupted
        return real_read(name)

    monkeypatch.setattr(loader_mod, "_read_yaml", fake_read)
    with pytest.raises(SeedValidationError, match=r"duplicate order"):
        loader_mod.load_and_validate()
