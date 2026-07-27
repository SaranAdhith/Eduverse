"""Bayesian Knowledge Tracing update rule (DOC_00 section 4).

Pure functions over a `BKTParams` and a current mastery belief `p_l`. The
diagnostic engine seeds beliefs from anchor responses; gate quizzes later
re-apply the exact same update with topic-specific evidence, overwriting the
anchor-based estimate.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import BKTParams


def posterior(p_l: float, params: BKTParams, correct: bool) -> float:
    """P(mastered | observation) for a single response, before the learning step.

    correct:   P(L)(1-slip) / [P(L)(1-slip) + (1-P(L))guess]
    incorrect: P(L)(slip)    / [P(L)(slip)   + (1-P(L))(1-guess)]
    """
    if not 0.0 <= p_l <= 1.0:
        raise ValueError(f"p_l={p_l!r} must be in [0, 1]")
    if correct:
        num = p_l * (1.0 - params.p_slip)
        den = num + (1.0 - p_l) * params.p_guess
    else:
        num = p_l * params.p_slip
        den = num + (1.0 - p_l) * (1.0 - params.p_guess)
    # den is > 0 for any p_l in [0,1] given the guess+slip<1 invariant enforced
    # on BKTParams, so no zero-division guard is needed here.
    return num / den


def update(p_l: float, params: BKTParams, correct: bool) -> float:
    """Full BKT step: posterior conditioning followed by the learning transition.

    P(L_next) = posterior + (1 - posterior) * P(T)
    """
    post = posterior(p_l, params, correct)
    return post + (1.0 - post) * params.p_transit


def is_mastered(p_l: float, params: BKTParams) -> bool:
    """Whether a belief clears the routing threshold the path planner uses."""
    return p_l >= params.mastery_threshold


def load_params(path: str | Path) -> BKTParams:
    """Load BKT cold-start parameters from a YAML file."""
    data = yaml.safe_load(Path(path).read_text())
    return BKTParams(
        p_l0=float(data["p_l0"]),
        p_transit=float(data["p_transit"]),
        p_guess=float(data["p_guess"]),
        p_slip=float(data["p_slip"]),
        mastery_threshold=float(data.get("mastery_threshold", 0.8)),
    )
