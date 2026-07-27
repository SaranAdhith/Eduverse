"""Ranker: combine signals into a per-segment quality_score (DOC_03 §4.4).

quality_score = 0.5 * confidence
              + 0.3 * channel_reputation
              + 0.2 * normalized_view_count
"""

from __future__ import annotations

from dataclasses import dataclass

W_CONFIDENCE = 0.5
W_REPUTATION = 0.3
W_VIEWS = 0.2


@dataclass
class RankItem:
    confidence: float
    reputation: float
    view_count: int | None


def _normalized_views(items: list[RankItem]) -> list[float]:
    views = [float(it.view_count or 0) for it in items]
    lo, hi = min(views), max(views)
    if hi <= lo:
        return [0.0 for _ in views]
    return [(v - lo) / (hi - lo) for v in views]


def quality_scores(items: list[RankItem]) -> list[float]:
    """Quality score per item, aligned to the input order."""
    nv = _normalized_views(items)
    return [
        W_CONFIDENCE * it.confidence + W_REPUTATION * it.reputation + W_VIEWS * nv[i]
        for i, it in enumerate(items)
    ]


def rank(items: list[RankItem]) -> list[int]:
    """Indices of ``items`` ordered best-first (stable on ties)."""
    scores = quality_scores(items)
    return sorted(range(len(items)), key=lambda i: (-scores[i], i))
