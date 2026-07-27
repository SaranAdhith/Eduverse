"""Load an export tarball into tables (DOC_08 §7).

The backend export (``app/modules/study/export.py``) is the only contract between
the service and the analysis pipeline. The core reader here is stdlib-only so the
plumbing is testable without the scientific stack; :func:`load_dataframes` layers
pandas on top for the notebooks.

An export tarball contains one directory per participant (``P001/…``) plus, for
``export-all``, a top-level ``participants.csv``.
"""
from __future__ import annotations

import csv
import io
import json
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Table = list[dict[str, str]]

_CSV_FILES = (
    "responses.csv",
    "mastery_trajectory.csv",
    "path_steps.csv",
    "gate_attempts.csv",
)


@dataclass
class ParticipantExport:
    code: str
    participant: dict[str, Any]
    tables: dict[str, Table] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Export:
    participants: dict[str, ParticipantExport] = field(default_factory=dict)
    # Present only for export-all tarballs.
    summary: Table | None = None


def _open(source: bytes | str | Path) -> tarfile.TarFile:
    if isinstance(source, (str, Path)):
        return tarfile.open(source, mode="r:gz")
    return tarfile.open(fileobj=io.BytesIO(source), mode="r:gz")


def _read(tar: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    fh = tar.extractfile(member)
    return fh.read() if fh is not None else b""


def _parse_csv(raw: bytes) -> Table:
    text = raw.decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def read_tarball(source: bytes | str | Path) -> Export:
    """Parse an export tarball into an :class:`Export` (stdlib only)."""
    export = Export()
    with _open(source) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/", 1)
            if len(parts) == 1:
                if member.name == "participants.csv":
                    export.summary = _parse_csv(_read(tar, member))
                continue
            code, filename = parts
            pe = export.participants.get(code)
            if pe is None:
                pe = ParticipantExport(code=code, participant={})
                export.participants[code] = pe
            raw = _read(tar, member)
            if filename == "participant.json":
                pe.participant = json.loads(raw.decode("utf-8"))
            elif filename == "events.jsonl":
                pe.events = [
                    json.loads(line)
                    for line in raw.decode("utf-8").splitlines()
                    if line.strip()
                ]
            elif filename in _CSV_FILES:
                pe.tables[filename.removesuffix(".csv")] = _parse_csv(raw)
    return export


def load_dataframes(source: bytes | str | Path, code: str | None = None) -> dict[str, Any]:
    """A participant's tables as pandas DataFrames (DOC_08 §7).

    ``code`` selects one participant; if omitted, the sole participant is used.
    Requires pandas (``analysis/requirements.txt``); imported lazily so the
    stdlib :func:`read_tarball` stays dependency-free.
    """
    import pandas as pd  # noqa: PLC0415 — optional heavy dep, notebooks only

    export = read_tarball(source)
    if code is None:
        if len(export.participants) != 1:
            raise ValueError("multiple participants in export; pass code=")
        code = next(iter(export.participants))
    pe = export.participants[code]
    frames = {name: pd.DataFrame(rows) for name, rows in pe.tables.items()}
    frames["events"] = pd.DataFrame(pe.events)
    return frames
