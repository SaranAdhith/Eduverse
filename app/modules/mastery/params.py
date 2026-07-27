"""BKT parameter resolution (DOC_04 §2.2).

``default_params()`` returns the cold-start defaults. ``params_for(topic_id)``
consults an optional ``app/seeds/bkt_overrides.yaml`` so the team can hand-tune
parameters per topic after the EM-fitting pass (DOC_00 §4, out of scope here).
Until that file exists, every topic uses the defaults.
"""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import yaml
from app.modules.mastery.bkt import BKTParams

# app/modules/mastery/params.py -> parents[2] == app/
_OVERRIDES_PATH = Path(__file__).resolve().parents[2] / "seeds" / "bkt_overrides.yaml"

_OVERRIDABLE = {"p_init", "p_transit", "p_guess", "p_slip"}


def default_params() -> BKTParams:
    return BKTParams()


@lru_cache(maxsize=1)
def _overrides() -> dict[str, BKTParams]:
    """Per-topic parameter overrides merged onto the defaults; {} if no file."""
    if not _OVERRIDES_PATH.exists():
        return {}
    raw = yaml.safe_load(_OVERRIDES_PATH.read_text()) or {}
    defaults = BKTParams()
    resolved: dict[str, BKTParams] = {}
    for topic_id, fields in raw.items():
        unknown = set(fields) - _OVERRIDABLE
        if unknown:
            raise ValueError(
                f"bkt_overrides.yaml: topic {topic_id} has unknown keys {sorted(unknown)}"
            )
        resolved[topic_id] = replace(defaults, **fields)
    return resolved


def params_for(topic_id: str) -> BKTParams:
    """Parameters for a topic: its override if present, else the defaults."""
    return _overrides().get(topic_id, default_params())
