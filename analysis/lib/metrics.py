"""Study metrics (DOC_08 §7).

Pure-python (stdlib + math) implementations of the quantities the paper reports,
so the primitives are testable without the scientific stack. The notebooks build
DataFrame-level aggregations on top of these.
"""
from __future__ import annotations

import math
from collections.abc import Sequence


def learning_gain(pre: float, post: float) -> float:
    """Post − pre on a topic's anchor mastery (DOC_08 §7 primary analysis)."""
    return post - pre


def time_to_mastery(
    posteriors: Sequence[tuple[float, float]], threshold: float = 0.85
) -> float | None:
    """First timestamp (seconds) at which the posterior crosses ``threshold``.

    ``posteriors`` is a sequence of ``(t_seconds, posterior)`` in time order.
    Returns ``None`` if mastery is never reached.
    """
    for t, p in posteriors:
        if p >= threshold:
            return t
    return None


def brier_score(predicted: Sequence[float], observed: Sequence[int]) -> float:
    """Mean squared error of probabilistic predictions vs 0/1 outcomes (§7)."""
    if len(predicted) != len(observed):
        raise ValueError("predicted and observed must be the same length")
    if not predicted:
        return math.nan
    return sum((p - o) ** 2 for p, o in zip(predicted, observed, strict=True)) / len(predicted)


def predicted_correct(prior: float, slip: float, guess: float) -> float:
    """BKT's predicted P(correct): prior*(1-slip) + (1-prior)*guess (§7)."""
    return prior * (1.0 - slip) + (1.0 - prior) * guess


def auc(predicted: Sequence[float], observed: Sequence[int]) -> float | None:
    """Area under the ROC curve via the Mann–Whitney U statistic (§7).

    Returns ``None`` when only one class is present (AUC undefined). Ties in the
    predicted score contribute 0.5, matching the standard rank-based estimator.
    """
    pos = [p for p, o in zip(predicted, observed, strict=False) if o == 1]
    neg = [p for p, o in zip(predicted, observed, strict=False) if o == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    for pp in pos:
        for pn in neg:
            if pp > pn:
                wins += 1.0
            elif pp == pn:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def cohens_d_paired(pre: Sequence[float], post: Sequence[float]) -> float:
    """Cohen's d for a paired design: mean(diff) / sd(diff) (§7)."""
    if len(pre) != len(post):
        raise ValueError("pre and post must be the same length")
    diffs = [b - a for a, b in zip(pre, post, strict=True)]
    n = len(diffs)
    if n < 2:
        return math.nan
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    sd = math.sqrt(var)
    return mean / sd if sd else math.nan
