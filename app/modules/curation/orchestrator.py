"""Orchestrator: the resumable per-topic curation batch job (DOC_03 §4.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from app.logging import log_event
from app.modules.curation import scribe
from app.modules.curation.channels import Channel, reputation_map
from app.modules.curation.client_transcripts import TranscriptClient, to_timestamped_text
from app.modules.curation.client_youtube import QuotaExceededError, YouTubeClient
from app.modules.curation.embed import Embedder, EmbeddingError
from app.modules.curation.model import TopicVideoCoverage, VideoSegment
from app.modules.curation.ranker import RankItem, quality_scores
from app.modules.curation.scout import scout
from app.modules.graph import service as graph_service
from app.modules.graph.service import Graph
from app.modules.topics.model import Topic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger("curation")

COVERED_MIN_SEGMENTS = 2
COVERED_MIN_QUALITY = 0.6


@dataclass
class TopicResult:
    topic_id: str
    candidates: int = 0
    segments_added: int = 0
    status: str = "pending"
    skipped: bool = False


@dataclass
class CurationReport:
    results: list[TopicResult] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str | None = None


async def _build_topics_context(session: AsyncSession, graph: Graph, topic_id: str) -> str:
    """Topic + direct prereqs + direct dependents, as id/name/description lines."""
    prereqs = graph.edges.get(topic_id, set())
    dependents = {t for t, e in graph.edges.items() if topic_id in e}
    ids = {topic_id, *prereqs, *dependents}
    rows = list(await session.scalars(select(Topic).where(Topic.id.in_(ids))))
    lines = []
    for t in sorted(rows, key=lambda r: r.id):
        desc = " ".join((t.description or "").split())
        lines.append(f"- {t.id} | {t.name} | {desc}")
    return "\n".join(lines)


async def _video_has_segments(session: AsyncSession, video_pk: Any) -> bool:
    count = await session.scalar(
        select(func.count()).select_from(VideoSegment).where(VideoSegment.video_id == video_pk)
    )
    return bool(count)


async def _refresh_coverage(session: AsyncSession, topic_id: str) -> str:
    """Recompute segment_count + status for a topic (DOC_03 §4.5)."""
    seg_rows = list(
        await session.scalars(select(VideoSegment).where(VideoSegment.topic_id == topic_id))
    )
    count = len(seg_rows)
    has_quality = any((s.quality_score or 0.0) >= COVERED_MIN_QUALITY for s in seg_rows)
    if count == 0:
        status = "no_content"
    elif count >= COVERED_MIN_SEGMENTS and has_quality:
        status = "covered"
    else:
        status = "pending"

    coverage = await session.get(TopicVideoCoverage, topic_id)
    if coverage is None:
        coverage = TopicVideoCoverage(topic_id=topic_id)
        session.add(coverage)
    coverage.segment_count = count
    coverage.status = status
    coverage.last_curated_at = datetime.now(UTC)
    await session.flush()
    return status


async def _curate_topic(
    session: AsyncSession,
    *,
    topic: Topic,
    graph: Graph,
    channels: list[Channel],
    reputations: dict[str, float],
    yt: YouTubeClient,
    transcripts: TranscriptClient,
    scribe_client: Any,
    embedder: Embedder,
    model: str,
    allowed_topic_ids: set[str],
) -> TopicResult:
    result = TopicResult(topic_id=topic.id)
    candidates = await scout(session, yt, topic=topic, channels=channels)
    result.candidates = len(candidates)
    topics_context = await _build_topics_context(session, graph, topic.id)

    # (segment, confidence, reputation, view_count) for later ranking.
    pending: list[tuple[VideoSegment, float, float, int | None]] = []

    for video in candidates:
        if await _video_has_segments(session, video.id):
            continue  # idempotent: already segmented (DOC_03 §4.2)
        captions = transcripts.fetch(video.video_id)
        if captions is None:
            video.has_captions = False
            await session.flush()
            continue
        video.has_captions = True
        video.caption_lang = captions.language
        log.debug("transcript_fetched", video_id=video.video_id, snippets=len(captions.snippets))

        segments = await scribe.segment_transcript(
            scribe_client,
            transcript=to_timestamped_text(captions),
            topics_context=topics_context,
            allowed_topic_ids=allowed_topic_ids,
            model=model,
        )
        for seg in segments:
            try:
                embedding = embedder.embed([seg.transcript_excerpt])[0]
            except EmbeddingError:
                log.warning("embed_failed_skip_segment", video_id=video.video_id)
                continue
            row = VideoSegment(
                video_id=video.id,
                topic_id=seg.topic_id,
                start_seconds=seg.start_seconds,
                end_seconds=seg.end_seconds,
                sub_topic_label=seg.sub_topic_label,
                transcript=seg.transcript_excerpt,
                embedding=embedding,
            )
            session.add(row)
            pending.append(
                (row, seg.confidence, reputations.get(video.channel_id, 0.5), video.view_count)
            )
    await session.flush()

    # Rank this topic's newly-added segments and assign quality_score.
    topic_pending = [p for p in pending if p[0].topic_id == topic.id]
    if topic_pending:
        items = [RankItem(confidence=c, reputation=r, view_count=v) for _, c, r, v in topic_pending]
        for (row, *_), score in zip(topic_pending, quality_scores(items), strict=True):
            row.quality_score = score
        await session.flush()

    result.segments_added = len([p for p in pending if p[0].topic_id == topic.id])
    result.status = await _refresh_coverage(session, topic.id)
    return result


async def _select_topics(
    session: AsyncSession, topic_ids: list[str] | None, tier: int | None
) -> list[Topic]:
    stmt = select(Topic).order_by(Topic.tier, Topic.display_order, Topic.id)
    if topic_ids:
        stmt = stmt.where(Topic.id.in_(topic_ids))
    elif tier is not None:
        stmt = stmt.where(Topic.tier == tier)
    return list(await session.scalars(stmt))


async def curate(
    session: AsyncSession,
    *,
    yt: YouTubeClient,
    transcripts: TranscriptClient,
    scribe_client: Any,
    embedder: Embedder,
    model: str,
    topic_ids: list[str] | None = None,
    tier: int | None = None,
    force: bool = False,
    channels: list[Channel] | None = None,
) -> CurationReport:
    """Walk topics: Scout -> Scribe -> embed -> rank -> update coverage."""
    from app.modules.curation.channels import load_channels

    channels = channels if channels is not None else load_channels()
    reputations = reputation_map()
    graph = await graph_service.load_graph(session)
    allowed_topic_ids = set(graph.nodes)

    topics = await _select_topics(session, topic_ids, tier)
    report = CurationReport()

    for topic in topics:
        coverage = await session.get(TopicVideoCoverage, topic.id)
        if not force and coverage is not None and coverage.status == "covered":
            report.results.append(TopicResult(topic_id=topic.id, status="covered", skipped=True))
            continue
        try:
            result = await _curate_topic(
                session,
                topic=topic,
                graph=graph,
                channels=channels,
                reputations=reputations,
                yt=yt,
                transcripts=transcripts,
                scribe_client=scribe_client,
                embedder=embedder,
                model=model,
                allowed_topic_ids=allowed_topic_ids,
            )
        except QuotaExceededError as exc:
            # DOC_03 §6: log + abort cleanly, don't crash.
            log.warning("youtube_quota_exhausted", error=str(exc))
            report.aborted = True
            report.abort_reason = "youtube_quota_exhausted"
            break
        report.results.append(result)

    log_event(
        "curation_report",
        topics=len(report.results),
        aborted=report.aborted,
        segments_added=sum(r.segments_added for r in report.results),
    )
    return report
