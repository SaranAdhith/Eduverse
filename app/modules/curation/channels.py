"""Channel allow-list loading + verification (DOC_03 §3)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, TypeAdapter

CHANNELS_PATH = Path(__file__).resolve().parents[2] / "seeds" / "youtube_channels.yaml"


class Channel(BaseModel):
    channel_id: str
    title: str
    reputation: float = Field(ge=0.0, le=1.0)
    notes: str = ""


class ChannelAllowListError(Exception):
    """Raised when the allow-list is invalid or a channel_id fails to resolve."""


def load_channels() -> list[Channel]:
    """Parse + validate the allow-list YAML (no network)."""
    raw = yaml.safe_load(CHANNELS_PATH.read_text())
    channels = TypeAdapter(list[Channel]).validate_python(raw)
    ids = [c.channel_id for c in channels]
    if len(set(ids)) != len(ids):
        raise ChannelAllowListError("duplicate channel_id in youtube_channels.yaml")
    return channels


def reputation_map() -> dict[str, float]:
    return {c.channel_id: c.reputation for c in load_channels()}
