"""DOC_03 §7 curation tests — fully offline (mocked YouTube / transcripts / Claude)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.modules.curation import scribe
from app.modules.curation.channels import Channel
from app.modules.curation.client_transcripts import FetchedCaptions, TranscriptSnippet
from app.modules.curation.client_youtube import YouTubeClient
from app.modules.curation.embed import HashEmbedder
from app.modules.curation.model import VideoResource, VideoSegment
from app.modules.curation.orchestrator import curate
from app.modules.curation.ranker import RankItem, quality_scores, rank
from app.modules.curation.scout import scout
from app.modules.topics.model import Topic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

MODEL = "claude-opus-4-7"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeList:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]], name: str, response: dict):
        self._calls, self._name, self._response = calls, name, response

    def list(self, **params: Any) -> Any:
        self._calls.append((self._name, params))
        return SimpleNamespace(execute=lambda: self._response)


class FakeYouTubeService:
    def __init__(self, *, search_items: list, video_items: list, channel_items: list):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._search = search_items
        self._videos = video_items
        self._channels = channel_items

    def search(self) -> _FakeList:
        return _FakeList(self.calls, "search", {"items": self._search})

    def videos(self) -> _FakeList:
        return _FakeList(self.calls, "videos", {"items": self._videos})

    def channels(self) -> _FakeList:
        return _FakeList(self.calls, "channels", {"items": self._channels})


def _video_item(video_id: str, *, channel_id: str, duration: str, views: str) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "channelId": channel_id,
            "channelTitle": "Test Channel",
            "title": f"Title {video_id}",
            "publishedAt": "2021-05-01T00:00:00Z",
        },
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": views},
    }


class FakeTranscripts:
    def __init__(self, captions: dict[str, FetchedCaptions | None]):
        self._captions = captions

    def fetch(self, video_id: str) -> FetchedCaptions | None:
        return self._captions.get(video_id)


def _captions() -> FetchedCaptions:
    return FetchedCaptions(
        language="en",
        snippets=[TranscriptSnippet(text="hello decorators", start=10.0, duration=5.0)],
    )


class FakeMessages:
    def __init__(self, responses: list[Any]):
        self._responses = responses
        self.calls = 0

    async def create(self, **kwargs: Any) -> Any:
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response


class FakeAnthropic:
    def __init__(self, responses: list[Any]):
        self.messages = FakeMessages(responses)


def _tool_response(segments: list[dict]) -> Any:
    block = SimpleNamespace(type="tool_use", name="record_segments", input={"segments": segments})
    return SimpleNamespace(content=[block])


def _text_response(text: str = "no tool call here") -> Any:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _seg(topic_id: str, start: int, end: int, conf: float = 0.8) -> dict:
    return {
        "topic_id": topic_id,
        "sub_topic_label": "label",
        "start_seconds": start,
        "end_seconds": end,
        "transcript_excerpt": "excerpt text",
        "confidence": conf,
        "reasoning": "because",
    }


_ALLOWLIST_CHANNEL = "UC8butISFwT-Wl7EV0hUK0BQ"
_FAKE_CHANNELS = [Channel(channel_id=_ALLOWLIST_CHANNEL, title="Test", reputation=0.9)]


# --------------------------------------------------------------------------- #
# 1. Scout always sets channelId
# --------------------------------------------------------------------------- #
async def test_scout_always_sets_channel_id(session: AsyncSession, seeded: None) -> None:
    service = FakeYouTubeService(
        search_items=[{"id": {"videoId": "vidA"}}],
        video_items=[
            _video_item("vidA", channel_id=_ALLOWLIST_CHANNEL, duration="PT5M", views="1000")
        ],
        channel_items=[],
    )
    client = YouTubeClient(service)
    topic = await session.get(Topic, "T6.3")
    candidates = await scout(session, client, topic=topic, channels=_FAKE_CHANNELS)

    search_calls = [params for name, params in service.calls if name == "search"]
    assert search_calls, "scout made no search.list calls"
    assert all(c.get("channelId") for c in search_calls)  # DOC_03 §4.1
    assert {c["channelId"] for c in search_calls} == {_ALLOWLIST_CHANNEL}
    assert len(candidates) == 1
    assert candidates[0].video_id == "vidA"


async def test_scout_filters_out_too_short_videos(session: AsyncSession, seeded: None) -> None:
    service = FakeYouTubeService(
        search_items=[{"id": {"videoId": "tiny"}}],
        video_items=[
            _video_item("tiny", channel_id=_ALLOWLIST_CHANNEL, duration="PT30S", views="10")
        ],
        channel_items=[],
    )
    topic = await session.get(Topic, "T6.3")
    candidates = await scout(session, YouTubeClient(service), topic=topic, channels=_FAKE_CHANNELS)
    assert candidates == []  # 30s < 90s floor


# --------------------------------------------------------------------------- #
# 2. No-captions video is persisted but never sent to Scribe
# --------------------------------------------------------------------------- #
async def test_no_captions_video_skips_scribe(session: AsyncSession, seeded: None) -> None:
    service = FakeYouTubeService(
        search_items=[{"id": {"videoId": "nocap"}}],
        video_items=[
            _video_item("nocap", channel_id=_ALLOWLIST_CHANNEL, duration="PT5M", views="500")
        ],
        channel_items=[],
    )
    scribe_client = FakeAnthropic([_tool_response([_seg("T6.3", 0, 120)])])

    await curate(
        session,
        yt=YouTubeClient(service),
        transcripts=FakeTranscripts({"nocap": None}),  # no captions
        scribe_client=scribe_client,
        embedder=HashEmbedder(dim=1024),
        model=MODEL,
        topic_ids=["T6.3"],
        channels=_FAKE_CHANNELS,
    )

    video = await session.scalar(select(VideoResource).where(VideoResource.video_id == "nocap"))
    assert video is not None
    assert video.has_captions is False
    assert scribe_client.messages.calls == 0  # never sent to Scribe


# --------------------------------------------------------------------------- #
# 3. Scribe validation
# --------------------------------------------------------------------------- #
def test_filter_rejects_unknown_topic_and_short_segments() -> None:
    response = scribe.ScribeResponse.model_validate(
        {
            "segments": [
                _seg("T6.3", 0, 120),  # valid
                _seg("T999", 0, 120),  # unknown topic
                _seg("T6.3", 0, 20),  # 20s < 30s floor
                _seg("T6.3", 0, 120, conf=0.2),  # confidence < 0.5
            ]
        }
    )
    kept = scribe.filter_segments(response, allowed_topic_ids={"T6.3", "T3.1"})
    assert len(kept) == 1
    assert kept[0].topic_id == "T6.3"


async def test_scribe_malformed_response_retries_then_skips() -> None:
    client = FakeAnthropic([_text_response(), _text_response()])  # never a tool_use
    result = await scribe.segment_transcript(
        client,
        transcript="[00:00:10] hi",
        topics_context="- T6.3 | Decorators | ...",
        allowed_topic_ids={"T6.3"},
        model=MODEL,
    )
    assert result == []
    assert client.messages.calls == 2  # retried once, then gave up


def test_parse_response_without_tool_use_raises() -> None:
    with pytest.raises(scribe.ScribeParseError):
        scribe.parse_response(_text_response())


# --------------------------------------------------------------------------- #
# 4. Idempotency
# --------------------------------------------------------------------------- #
async def test_curate_is_idempotent(session: AsyncSession, seeded: None) -> None:
    def fresh_service() -> FakeYouTubeService:
        return FakeYouTubeService(
            search_items=[{"id": {"videoId": "vidA"}}],
            video_items=[
                _video_item("vidA", channel_id=_ALLOWLIST_CHANNEL, duration="PT8M", views="2000")
            ],
            channel_items=[],
        )

    scribe_client = FakeAnthropic([_tool_response([_seg("T6.3", 0, 120), _seg("T6.3", 130, 260)])])
    transcripts = FakeTranscripts({"vidA": _captions()})
    embedder = HashEmbedder(dim=1024)

    async def run() -> None:
        await curate(
            session,
            yt=YouTubeClient(fresh_service()),
            transcripts=transcripts,
            scribe_client=scribe_client,
            embedder=embedder,
            model=MODEL,
            topic_ids=["T6.3"],
            force=True,  # bypass the covered-skip so we exercise the segment path twice
            channels=_FAKE_CHANNELS,
        )

    await run()
    await run()

    count = await session.scalar(
        select(func.count()).select_from(VideoSegment).where(VideoSegment.topic_id == "T6.3")
    )
    assert count == 2  # no duplicates on the second run
    assert scribe_client.messages.calls == 1  # video already segmented => Scribe skipped


async def test_curate_sets_quality_score_and_coverage(session: AsyncSession, seeded: None) -> None:
    service = FakeYouTubeService(
        search_items=[{"id": {"videoId": "vidA"}}],
        video_items=[
            _video_item("vidA", channel_id=_ALLOWLIST_CHANNEL, duration="PT8M", views="2000")
        ],
        channel_items=[],
    )
    scribe_client = FakeAnthropic(
        [_tool_response([_seg("T6.3", 0, 120, conf=0.9), _seg("T6.3", 130, 260, conf=0.9)])]
    )
    report = await curate(
        session,
        yt=YouTubeClient(service),
        transcripts=FakeTranscripts({"vidA": _captions()}),
        scribe_client=scribe_client,
        embedder=HashEmbedder(dim=1024),
        model=MODEL,
        topic_ids=["T6.3"],
        channels=_FAKE_CHANNELS,
    )
    (result,) = report.results
    assert result.segments_added == 2
    segs = list(await session.scalars(select(VideoSegment).where(VideoSegment.topic_id == "T6.3")))
    assert all(s.quality_score is not None for s in segs)


# --------------------------------------------------------------------------- #
# 5. Ranker order matches the closed-form expectation
# --------------------------------------------------------------------------- #
def test_ranker_order_matches_closed_form() -> None:
    items = [
        RankItem(confidence=0.9, reputation=0.5, view_count=0),  # A
        RankItem(confidence=0.6, reputation=0.9, view_count=1000),  # B
        RankItem(confidence=0.5, reputation=0.5, view_count=500),  # C
    ]
    # normalized views: A=0.0, B=1.0, C=0.5
    # A = .5*.9 + .3*.5 + .2*0   = 0.60
    # B = .5*.6 + .3*.9 + .2*1   = 0.77
    # C = .5*.5 + .3*.5 + .2*.5  = 0.50
    scores = quality_scores(items)
    assert scores[0] == pytest.approx(0.60)
    assert scores[1] == pytest.approx(0.77)
    assert scores[2] == pytest.approx(0.50)
    assert rank(items) == [1, 0, 2]  # B, A, C
