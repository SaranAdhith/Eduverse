"""Thin YouTube Data API v3 wrapper (DOC_03 §4).

Search always scopes to an allow-list ``channelId`` — there is no open search.
The client wraps a google-api-python-client resource so tests can inject a fake.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# ISO-8601 duration as returned by videos.list contentDetails.duration, e.g.
# "PT1H2M30S".
_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


class YouTubeError(Exception):
    """Base class for YouTube client errors."""


class QuotaExceededError(YouTubeError):
    """Raised when the daily YouTube API quota is exhausted (DOC_03 §6)."""


@dataclass
class VideoMeta:
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    duration_seconds: int
    view_count: int | None
    published_at: datetime | None


def build_service(api_key: str) -> Any:
    """Construct a real YouTube Data API service (lazy import)."""
    from googleapiclient.discovery import build

    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def parse_duration(iso: str) -> int:
    match = _DURATION_RE.fullmatch(iso or "")
    if not match:
        return 0
    parts = {k: int(v) for k, v in match.groupdict(default="0").items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status == 403 and ("quota" in text or "ratelimit" in text)


class YouTubeClient:
    def __init__(self, service: Any) -> None:
        self._service = service

    def search_channel(self, *, channel_id: str, query: str, max_results: int = 5) -> list[str]:
        """Return candidate video ids for a channel (search.list, channelId always set)."""
        params = {
            "part": "id",
            "channelId": channel_id,  # DOC_03 §4.1: never omit this.
            "q": query,
            "type": "video",
            "videoCaption": "closedCaption",
            "maxResults": max_results,
            "order": "relevance",
        }
        try:
            response = self._service.search().list(**params).execute()
        except Exception as exc:  # noqa: BLE001 — translate transport errors
            if _is_quota_error(exc):
                raise QuotaExceededError(str(exc)) from exc
            raise YouTubeError(str(exc)) from exc
        ids: list[str] = []
        for item in response.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
        return ids

    def list_video_details(self, video_ids: list[str]) -> list[VideoMeta]:
        """Fetch metadata for up to 50 video ids (videos.list)."""
        if not video_ids:
            return []
        try:
            response = (
                self._service.videos()
                .list(part="snippet,contentDetails,statistics", id=",".join(video_ids))
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            if _is_quota_error(exc):
                raise QuotaExceededError(str(exc)) from exc
            raise YouTubeError(str(exc)) from exc

        metas: list[VideoMeta] = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            view_count = stats.get("viewCount")
            metas.append(
                VideoMeta(
                    video_id=item["id"],
                    channel_id=snippet.get("channelId", ""),
                    channel_title=snippet.get("channelTitle", ""),
                    title=snippet.get("title", ""),
                    duration_seconds=parse_duration(
                        item.get("contentDetails", {}).get("duration", "")
                    ),
                    view_count=int(view_count) if view_count is not None else None,
                    published_at=_parse_published(snippet.get("publishedAt")),
                )
            )
        return metas

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        """Resolve a channel by id, or None if it does not exist (for verification)."""
        try:
            response = self._service.channels().list(part="snippet", id=channel_id).execute()
        except Exception as exc:  # noqa: BLE001
            if _is_quota_error(exc):
                raise QuotaExceededError(str(exc)) from exc
            raise YouTubeError(str(exc)) from exc
        items = response.get("items", [])
        return items[0] if items else None
