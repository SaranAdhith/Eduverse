"""structlog configuration (DOC_01 §7).

- Console renderer in ``ENV=dev`` (and ``test``).
- JSONL renderer to ``LOG_FILE`` in ``ENV=study``.
- ``request_id`` and ``participant_code`` are bound into a contextvar by the
  request middleware (see :mod:`app.main`) and auto-merged into every record.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

import structlog
from structlog.contextvars import merge_contextvars

from app.config import Settings

_log_file_handle: TextIO | None = None

# DOC_08 §4: every event is dual-written — JSONL (via structlog, below) *and* the
# durable ``events`` table. The study module registers a sink here so it can
# capture every ``log_event`` call without every call site knowing about the DB.
EventSink = Callable[[str, dict[str, Any]], None]
_event_sinks: list[EventSink] = []


def register_event_sink(sink: EventSink) -> None:
    """Register a callback invoked (synchronously) for every ``log_event``."""
    if sink not in _event_sinks:
        _event_sinks.append(sink)


def _open_log_file(path: str) -> TextIO:
    global _log_file_handle
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _log_file_handle = open(path, "a", encoding="utf-8")  # noqa: SIM115
    return _log_file_handle


def configure_logging(settings: Settings) -> None:
    """Wire up structlog + stdlib logging according to the active environment."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.env == "study":
        logger_factory = structlog.PrintLoggerFactory(file=_open_log_file(settings.log_file))
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        logger_factory = structlog.PrintLoggerFactory()
        renderer = structlog.dev.ConsoleRenderer(colors=os.isatty(1))

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=logger_factory,
        cache_logger_on_first_use=True,
    )


def log_event(event_type: str, **kwargs: Any) -> None:
    """Emit a structured event (DOC_01 §7, DOC_08 §4).

    The JSONL line is emitted synchronously via structlog; every registered sink
    (DOC_08's write-behind DB buffer) then receives the same event. ``request_id``
    and ``participant_code`` are merged automatically from contextvars.
    """
    structlog.get_logger("event").info(event_type, event_type=event_type, **kwargs)
    for sink in _event_sinks:
        try:
            sink(event_type, kwargs)
        except Exception:  # noqa: BLE001 — a broken sink must never drop the request
            structlog.get_logger("event").warning("event_sink_failed", event_type=event_type)
