"""Public caption fetch via youtube-transcript-api (DOC_03 §1, §4.2).

These are the same public caption tracks YouTube renders to every viewer. If a
video has no captions we return ``None`` (the caller marks ``has_captions=false``
and skips) — we never synthesise transcripts or download media.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranscriptSnippet:
    text: str
    start: float
    duration: float


@dataclass
class FetchedCaptions:
    language: str
    snippets: list[TranscriptSnippet]


class TranscriptClient:
    """Wraps youtube-transcript-api; injectable for offline tests."""

    def __init__(self, api: object | None = None, languages: tuple[str, ...] = ("en",)):
        self._api = api
        self._languages = languages

    def _get_api(self) -> object:
        if self._api is None:
            from youtube_transcript_api import YouTubeTranscriptApi

            self._api = YouTubeTranscriptApi()
        return self._api

    def fetch(self, video_id: str) -> FetchedCaptions | None:
        """Return captions, or None when unavailable (disabled / not found)."""
        from youtube_transcript_api import (  # local import: optional at test time
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
        )

        try:
            fetched = self._get_api().fetch(video_id, languages=list(self._languages))  # type: ignore[attr-defined]
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
            return None
        except Exception:  # noqa: BLE001 — any retrieval failure => skip, never crash
            return None

        language = getattr(fetched, "language_code", self._languages[0])
        snippets = [
            TranscriptSnippet(
                text=getattr(s, "text", ""),
                start=float(getattr(s, "start", 0.0)),
                duration=float(getattr(s, "duration", 0.0)),
            )
            for s in fetched
        ]
        if not snippets:
            return None
        return FetchedCaptions(language=language, snippets=snippets)


def to_timestamped_text(captions: FetchedCaptions) -> str:
    """Render captions as ``[HH:MM:SS] text`` lines for the Scribe prompt."""
    lines = []
    for snip in captions.snippets:
        total = int(snip.start)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        lines.append(f"[{h:02d}:{m:02d}:{s:02d}] {snip.text}")
    return "\n".join(lines)
