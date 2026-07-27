"""Diagnostic blueprint loading and validation (DOC_00 section 2).

The blueprint is a placement instrument, not a per-topic test: it probes anchor
topics per tier and the result seeds the BKT prior for every topic in that tier.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import BlueprintEntry


class Blueprint:
    def __init__(self, items_total: int, entries: list[BlueprintEntry]):
        self.items_total = items_total
        self.entries = entries

    @classmethod
    def load(cls, path: str | Path) -> Blueprint:
        data = yaml.safe_load(Path(path).read_text())
        entries = [
            BlueprintEntry(
                tier=row["tier"],
                anchors=tuple(row.get("anchors") or ()),
                items=int(row["items"]),
                difficulty=dict(row.get("difficulty") or {}),
            )
            for row in data.get("tiers", [])
        ]
        return cls(items_total=int(data["items_total"]), entries=entries)

    def total_items(self) -> int:
        return sum(e.items for e in self.entries)

    def all_anchors(self) -> list[str]:
        return [a for e in self.entries for a in e.anchors]
