"""BKT property + replayability invariants (DOC_09 §2.4).

The pure-math properties use hypothesis; the replayability invariant is DB-backed
— it proves the stored ``responses`` fully determine a participant's ``mastery``
row, which is what lets the analysis pipeline reconstruct trajectories.
"""
from __future__ import annotations

from app.modules.mastery import bkt
from app.modules.mastery import service as mastery_service
from app.modules.mastery.model import Mastery, Response
from app.modules.mastery.params import default_params
from app.modules.participants import service as participants_service
from app.modules.planner.gate import MASTERY_THRESHOLD
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PARAMS = default_params()


# --------------------------------------------------------------------------- #
# Pure-math properties (hypothesis)
# --------------------------------------------------------------------------- #
@given(st.lists(st.booleans(), max_size=60))
def test_mastery_stays_in_unit_interval(sequence: list[bool]) -> None:
    p = PARAMS.p_init
    for correct in sequence:
        p = bkt.step(p, correct, PARAMS)
        assert 0.0 <= p <= 1.0


@given(st.integers(min_value=5, max_value=40))
@settings(max_examples=25)
def test_all_correct_reaches_mastery(n: int) -> None:
    p = PARAMS.p_init
    for _ in range(n):
        p = bkt.step(p, True, PARAMS)
    assert p > MASTERY_THRESHOLD


@given(st.integers(min_value=5, max_value=40))
@settings(max_examples=25)
def test_all_incorrect_stays_low(n: int) -> None:
    p = PARAMS.p_init
    for _ in range(n):
        p = bkt.step(p, False, PARAMS)
    assert p < 0.3


# --------------------------------------------------------------------------- #
# Replayability (DB-backed): responses fully determine the mastery row.
# --------------------------------------------------------------------------- #
async def test_replay_reproduces_mastery_row(
    session: AsyncSession, seeded: None
) -> None:
    from app.modules.questions.model import Choice, Question

    participant = await participants_service.enroll(session, consent_given=True)

    # One topic, gate context only (no diagnostic tier-propagation), so this
    # topic's mastery is a pure function of its own responses.
    topic_id = "T2.1"
    question = Question(
        topic_id=topic_id,
        difficulty="medium",
        stem="stub",
        explanation="because",
        is_diagnostic=False,
        source="generated",
    )
    session.add(question)
    await session.flush()
    session.add_all(
        [
            Choice(question_id=question.id, label="A", text="a", is_correct=True),
            Choice(question_id=question.id, label="B", text="b", is_correct=False),
        ]
    )
    await session.flush()

    outcomes = [True, False, True, True, False, True, True, True]
    for correct in outcomes:
        await mastery_service.record_response(
            session,
            participant,
            question_id=question.id,
            selected_label="A" if correct else "B",
            response_ms=None,
            context="gate",
        )
        # Commit per response so each row gets a distinct transaction timestamp —
        # exactly as production does (one request per answer), making the stored
        # order replayable.
        await session.commit()

    stored = await session.scalar(
        select(Mastery.p_mastered).where(
            Mastery.participant_id == participant.id, Mastery.topic_id == topic_id
        )
    )

    # Replay BKT over the stored responses, in order, from p_init.
    rows = list(
        await session.scalars(
            select(Response)
            .where(
                Response.participant_id == participant.id,
                Response.topic_id == topic_id,
            )
            .order_by(Response.created_at, Response.id)
        )
    )
    replay = default_params().p_init
    for r in rows:
        replay = bkt.step(replay, r.is_correct, default_params())

    assert stored is not None
    # mastery/responses are stored as Postgres REAL (float32), so the tightest
    # honest tolerance is float32 epsilon (~1e-6), not the doc's aspirational
    # 1e-9 which assumes double-precision storage.
    assert abs(replay - stored) < 1e-6
    # The last response's posterior snapshot also equals the final mastery.
    assert abs(rows[-1].posterior_mastery - stored) < 1e-6


async def test_replay_matches_stored_snapshots_chain(
    session: AsyncSession, seeded: None
) -> None:
    """Each response's prior equals the previous response's posterior (chain)."""
    from app.modules.questions.model import Choice, Question

    participant = await participants_service.enroll(session, consent_given=True)
    question = Question(
        topic_id="T2.2",
        difficulty="easy",
        stem="stub",
        explanation="because",
        is_diagnostic=False,
        source="generated",
    )
    session.add(question)
    await session.flush()
    session.add_all(
        [
            Choice(question_id=question.id, label="A", text="a", is_correct=True),
            Choice(question_id=question.id, label="B", text="b", is_correct=False),
        ]
    )
    await session.flush()

    for correct in [True, True, False, True]:
        await mastery_service.record_response(
            session,
            participant,
            question_id=question.id,
            selected_label="A" if correct else "B",
            response_ms=None,
            context="gate",
        )
        await session.commit()

    rows = list(
        await session.scalars(
            select(Response)
            .where(Response.participant_id == participant.id)
            .order_by(Response.created_at, Response.id)
        )
    )
    for earlier, later in zip(rows, rows[1:], strict=False):
        assert abs(earlier.posterior_mastery - later.prior_mastery) < 1e-6
    assert abs(rows[0].prior_mastery - default_params().p_init) < 1e-6
