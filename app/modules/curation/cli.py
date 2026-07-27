"""Curation CLI (DOC_03 §5).

python -m app.modules.curation.cli curate [--topic T6.3 | --tier 5] [--force]
python -m app.modules.curation.cli status
python -m app.modules.curation.cli refresh-channel UC...
python -m app.modules.curation.cli seed-channels
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog
from app.config import get_settings
from app.db import session_scope
from app.modules.curation.channels import ChannelAllowListError, load_channels
from app.modules.curation.client_transcripts import TranscriptClient
from app.modules.curation.client_youtube import YouTubeClient, build_service
from app.modules.curation.embed import make_embedder
from app.modules.curation.model import TopicVideoCoverage
from app.modules.curation.orchestrator import curate
from app.modules.topics.model import Topic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger("curation.cli")


def _require_youtube() -> YouTubeClient:
    settings = get_settings()
    if not settings.youtube_api_key:
        raise SystemExit("error: YOUTUBE_API_KEY is required for this command")
    return YouTubeClient(build_service(settings.youtube_api_key))


async def _cmd_curate(topic: str | None, tier: int | None, force: bool) -> None:
    import anthropic

    settings = get_settings()
    yt = _require_youtube()
    async for session in session_scope():
        report = await curate(
            session,
            yt=yt,
            transcripts=TranscriptClient(),
            scribe_client=anthropic.AsyncAnthropic(),
            embedder=make_embedder(settings),
            model=settings.anthropic_model_reasoning,
            topic_ids=[topic] if topic else None,
            tier=tier,
            force=force,
        )
    for r in report.results:
        flag = " (skipped)" if r.skipped else ""
        print(f"{r.topic_id}: {r.status} — {r.segments_added} segment(s){flag}")
    if report.aborted:
        print(f"ABORTED: {report.abort_reason}", file=sys.stderr)


async def _cmd_status() -> None:
    async for session in session_scope():
        await _print_status(session)


async def _print_status(session: AsyncSession) -> None:
    rows = list(
        await session.execute(
            select(
                Topic.id, Topic.tier, TopicVideoCoverage.status, TopicVideoCoverage.segment_count
            )
            .join(TopicVideoCoverage, TopicVideoCoverage.topic_id == Topic.id, isouter=True)
            .order_by(Topic.tier, Topic.display_order, Topic.id)
        )
    )
    by_tier: dict[int, list[tuple[str, str, int]]] = {}
    for topic_id, tier, status, count in rows:
        by_tier.setdefault(tier, []).append((topic_id, status or "pending", count or 0))
    print("Coverage report (DOC_03 §5)")
    for tier in sorted(by_tier):
        covered = sum(1 for _, s, _ in by_tier[tier] if s == "covered")
        print(f"\nTier {tier}: {covered}/{len(by_tier[tier])} covered")
        for topic_id, status, count in by_tier[tier]:
            print(f"  {topic_id:6} {status:10} {count} segment(s)")


def _cmd_seed_channels() -> None:
    try:
        channels = load_channels()
    except ChannelAllowListError as exc:
        raise SystemExit(f"error: {exc}") from exc

    settings = get_settings()
    if not settings.youtube_api_key:
        print(f"loaded {len(channels)} channels; verification skipped (no YOUTUBE_API_KEY)")
        return
    yt = YouTubeClient(build_service(settings.youtube_api_key))
    for ch in channels:
        if yt.get_channel(ch.channel_id) is None:
            raise SystemExit(f"error: channel_id {ch.channel_id} ({ch.title}) does not resolve")
    print(f"verified {len(channels)} channel(s)")


def _cmd_refresh_channel(channel_id: str) -> None:
    yt = _require_youtube()
    channel = yt.get_channel(channel_id)
    if channel is None:
        raise SystemExit(f"error: channel {channel_id} not found")
    snippet = channel.get("snippet", {})
    print(f"{channel_id}: {snippet.get('title')} — {snippet.get('description', '')[:80]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eduverse curation CLI (DOC_03)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_curate = sub.add_parser("curate")
    p_curate.add_argument("--topic", default=None)
    p_curate.add_argument("--tier", type=int, default=None)
    p_curate.add_argument("--force", action="store_true")

    sub.add_parser("status")
    sub.add_parser("seed-channels")

    p_refresh = sub.add_parser("refresh-channel")
    p_refresh.add_argument("channel_id")

    args = parser.parse_args()
    if args.command == "curate":
        asyncio.run(_cmd_curate(args.topic, args.tier, args.force))
    elif args.command == "status":
        asyncio.run(_cmd_status())
    elif args.command == "seed-channels":
        _cmd_seed_channels()
    elif args.command == "refresh-channel":
        _cmd_refresh_channel(args.channel_id)


if __name__ == "__main__":
    main()
