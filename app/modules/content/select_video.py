"""Video selection for a content chunk (DOC_06 §4).

Picks the single best curated segment to ship for a topic: highest quality among
the top candidates, biased toward the 4–12 minute sweet spot, with a soft
penalty for repeating a channel already seen recently in the participant's path.
"""
from __future__ import annotations

from app.modules.curation.model import VideoResource, VideoSegment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# DOC_06 §4.1: rank the top 5 quality candidates, then apply the soft biases.
TOP_CANDIDATES = 5

# DOC_06 §4.2: sweet spot for a single learning chunk (seconds).
SWEET_SPOT_MIN_SECONDS = 4 * 60
SWEET_SPOT_MAX_SECONDS = 12 * 60


def _duration(segment: VideoSegment) -> int:
    return segment.end_seconds - segment.start_seconds


def _in_sweet_spot(segment: VideoSegment) -> bool:
    return SWEET_SPOT_MIN_SECONDS <= _duration(segment) <= SWEET_SPOT_MAX_SECONDS


async def choose(
    session: AsyncSession,
    topic_id: str,
    *,
    recent_channel_ids: frozenset[str] = frozenset(),
) -> VideoSegment | None:
    """Return the segment to ship for ``topic_id``, or ``None`` for fallback.

    ``recent_channel_ids`` are the channels of segments recently shown in the
    participant's path; matching one is a soft tiebreaker penalty (DOC_06 §4.3),
    never a hard exclusion — the same channel may legitimately own the best
    content across several topics.
    """
    result = await session.scalars(
        select(VideoSegment)
        .join(VideoResource, VideoResource.id == VideoSegment.video_id)
        .where(VideoSegment.topic_id == topic_id)
        .order_by(VideoSegment.quality_score.desc().nulls_last(), VideoSegment.id)
        .limit(TOP_CANDIDATES)
        .options(selectinload(VideoSegment.video))
    )
    candidates = list(result.all())
    if not candidates:
        return None

    def rank_key(segment: VideoSegment) -> tuple[bool, bool, float]:
        # Prefer sweet-spot length, then a fresh channel, then quality — all
        # soft biases layered over the quality ordering (higher tuple wins).
        fresh_channel = segment.video.channel_id not in recent_channel_ids
        return (_in_sweet_spot(segment), fresh_channel, segment.quality_score or 0.0)

    return max(candidates, key=rank_key)
