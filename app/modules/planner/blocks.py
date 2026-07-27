"""Study block membership (DOC_05 §6).

Reads ``app/seeds/blocks.yaml`` once and answers "which topics belong to block
X". A topic's out-of-block prerequisites are treated as pre-mastered, so the
planners only ever reason about within-block structure.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

# app/modules/planner/blocks.py -> parents[2] == app/
_BLOCKS_PATH = Path(__file__).resolve().parents[2] / "seeds" / "blocks.yaml"

VALID_BLOCKS = ("A", "B")


class UnknownBlockError(ValueError):
    """Raised when a block id is not defined in blocks.yaml."""


@lru_cache(maxsize=1)
def _blocks() -> dict[str, frozenset[str]]:
    raw = yaml.safe_load(_BLOCKS_PATH.read_text()) or {}
    return {block: frozenset(topic_ids) for block, topic_ids in raw.items()}


def allowed_topics(block: str) -> frozenset[str]:
    """The topic ids assigned to a block (raises on an unknown block)."""
    blocks = _blocks()
    if block not in blocks:
        raise UnknownBlockError(block)
    return blocks[block]
