"""Diagnostic bank endpoint (DOC_02 §5).

``GET /diagnostic/items`` returns the 25 placement items in order, without
answer keys. It requires a participant header (via ``get_participant``) but does
*not* record a response — that is DOC_04's job.
"""
from __future__ import annotations

from app.deps import get_participant, get_session
from app.modules.participants.model import Participant
from app.modules.questions.model import Question
from app.modules.questions.schema import ChoiceOut, DiagnosticItemOut
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter(tags=["diagnostic"])


@router.get("/diagnostic/items", response_model=list[DiagnosticItemOut])
async def diagnostic_items(
    _participant: Participant = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
) -> list[DiagnosticItemOut]:
    questions = list(
        await session.scalars(
            select(Question)
            .where(Question.is_diagnostic.is_(True))
            .order_by(Question.diagnostic_order)
            .options(selectinload(Question.choices))
        )
    )
    return [
        DiagnosticItemOut(
            id=q.id,
            order=q.diagnostic_order,  # always set for diagnostic questions
            topic_id=q.topic_id,
            difficulty=q.difficulty,
            stem=q.stem,
            stem_code=q.stem_code,
            choices=[ChoiceOut(label=c.label, text=c.text) for c in q.choices],
        )
        for q in questions
    ]
