"""Core domain dataclasses for the Eduverse curriculum and mastery model.

These types are intentionally plain data: loaders in `curriculum.py`,
`diagnostic.py`, and `bkt.py` build them from the YAML under `data/`, and the
graph / planning logic operates on them. Keeping them free of behaviour makes
them trivial to serialize to a DB row later (DOC_00 section 6).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    """A single curriculum node. `prerequisites` are direct-parent topic IDs."""

    id: str
    tier: str
    name: str
    prerequisites: tuple[str, ...] = ()
    core: bool = True


@dataclass(frozen=True)
class Tier:
    id: str
    name: str


@dataclass(frozen=True)
class BlueprintEntry:
    """One tier's slice of the diagnostic: which anchors, how many items, mix."""

    tier: str
    anchors: tuple[str, ...]
    items: int
    difficulty: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class BKTParams:
    """Bayesian Knowledge Tracing parameters (DOC_00 section 4)."""

    p_l0: float
    p_transit: float
    p_guess: float
    p_slip: float
    mastery_threshold: float = 0.8

    def __post_init__(self) -> None:
        for name in ("p_l0", "p_transit", "p_guess", "p_slip", "mastery_threshold"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"BKT parameter {name}={value!r} must be in [0, 1]")
        # A well-formed BKT model needs guess + slip < 1, otherwise a correct
        # answer is evidence *against* mastery (the model degenerates).
        if self.p_guess + self.p_slip >= 1.0:
            raise ValueError(
                f"p_guess ({self.p_guess}) + p_slip ({self.p_slip}) must be < 1; "
                "otherwise the mastery update is non-identifiable."
            )
