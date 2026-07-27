"""Paper-quality matplotlib helpers (DOC_08 §7).

No seaborn defaults — the paper uses a restrained matplotlib style so figures are
reproducible from this file alone. matplotlib is imported lazily so importing the
module doesn't require the plotting stack.
"""
from __future__ import annotations

from typing import Any

PAPER_RC: dict[str, Any] = {
    "figure.figsize": (5.0, 3.2),
    "figure.dpi": 150,
    "font.size": 9,
    "font.family": "serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "lines.linewidth": 1.4,
    "savefig.bbox": "tight",
}


def apply_style() -> None:
    """Apply the paper's matplotlib rcParams (call once per notebook)."""
    import matplotlib.pyplot as plt  # noqa: PLC0415 — optional heavy dep

    plt.rcParams.update(PAPER_RC)


def mastery_trajectory(ax: Any, ts: list[float], posterior: list[float]) -> Any:
    """Plot a single topic's posterior over time onto ``ax``."""
    ax.plot(ts, posterior, marker="o", markersize=3)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("P(mastered)")
    ax.set_ylim(0, 1)
    return ax
