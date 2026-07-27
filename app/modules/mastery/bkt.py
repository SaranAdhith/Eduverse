"""Bayesian Knowledge Tracing — pure math (DOC_04 §2.1, normative DOC_00 §4).

No DB. No async. No imports beyond the standard library. Every later component
imports :func:`posterior` and :func:`step` — they are the single source of truth
for the mastery math.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BKTParams:
    p_init: float = 0.30  # P(L0): prior mastery before any evidence
    p_transit: float = 0.15  # P(T): P(unmastered -> mastered) per opportunity
    p_guess: float = 0.25  # P(correct | not mastered), 4-option MCQ baseline
    p_slip: float = 0.10  # P(incorrect | mastered)


def posterior(prior: float, correct: bool, p: BKTParams) -> float:
    """P(mastered | observation), via Bayes."""
    if correct:
        num = prior * (1 - p.p_slip)
        den = num + (1 - prior) * p.p_guess
    else:
        num = prior * p.p_slip
        den = num + (1 - prior) * (1 - p.p_guess)
    return num / den if den > 0 else prior


def step(prior: float, correct: bool, p: BKTParams) -> float:
    """Full BKT update: posterior conditioning + learning transition."""
    post = posterior(prior, correct, p)
    return post + (1 - post) * p.p_transit
