"""Scout: per-topic search over the allow-list -> candidate videos (DOC_03 §4.1)."""

from __future__ import annotations

import re

from app.modules.curation.channels import Channel
from app.modules.curation.client_youtube import VideoMeta, YouTubeClient
from app.modules.curation.model import VideoResource
from app.modules.topics.model import Topic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# DOC_03 §4.1 duration bounds: too thin below 90s, too unwieldy above 60 min.
MIN_DURATION_SECONDS = 90
MAX_DURATION_SECONDS = 60 * 60

_STOPWORDS = {"the", "and", "for", "with", "that", "covers", "how", "into", "other"}


def build_query(topic: Topic) -> str:
    """topic.name + 1-2 salient terms from the description (DOC_03 §4.1)."""
    words = re.findall(r"[A-Za-z]{4,}", topic.description or "")
    key_terms = [w for w in words if w.lower() not in _STOPWORDS][:2]
    return " ".join(["python", topic.name, *key_terms]).strip()


async def scout(
    session: AsyncSession,
    client: YouTubeClient,
    *,
    topic: Topic,
    channels: list[Channel],
    max_per_channel: int = 5,
) -> list[VideoResource]:
    """Search each allow-list channel, filter by duration, persist candidates.

    Candidates are written to ``video_resources`` *before* transcript fetch so a
    partial pipeline run is recoverable (DOC_03 §4.1).
    """
    query = build_query(topic)

    # Collect distinct candidate video ids across all channels.
    candidate_ids: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        for vid in client.search_channel(
            channel_id=channel.channel_id, query=query, max_results=max_per_channel
        ):
            if vid not in seen:
                seen.add(vid)
                candidate_ids.append(vid)

    metas = client.list_video_details(candidate_ids)
    kept: list[VideoResource] = []
    for meta in metas:
        if not (MIN_DURATION_SECONDS <= meta.duration_seconds <= MAX_DURATION_SECONDS):
            continue
        resource = await _upsert_resource(session, meta)
        kept.append(resource)
    return kept


async def _upsert_resource(session: AsyncSession, meta: VideoMeta) -> VideoResource:
    resource = await session.scalar(
        select(VideoResource).where(VideoResource.video_id == meta.video_id)
    )
    if resource is None:
        # Search already filtered to closedCaption; Scribe corrects has_captions
        # to False if the transcript turns out to be unavailable.
        resource = VideoResource(video_id=meta.video_id, has_captions=True)
        session.add(resource)
    resource.channel_id = meta.channel_id
    resource.channel_title = meta.channel_title
    resource.title = meta.title
    resource.duration_seconds = meta.duration_seconds
    resource.view_count = meta.view_count
    resource.published_at = meta.published_at
    await session.flush()
    return resource
