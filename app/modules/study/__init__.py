"""Study instrumentation (DOC_08).

Turns the agent into a study instrument: the block-and-mode assignment rotation,
durable event capture (DB + JSONL), the analysis export, and the LLM replay
cache. Importing this package installs the DB event sink (see :mod:`events`).
"""
from __future__ import annotations

from app.modules.study import events

events.install()
