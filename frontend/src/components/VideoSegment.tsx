"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import type { VideoDeepLink } from "@/lib/types";

// DOC_07 §4: embedded YouTube segment with start/end. We deliberately do NOT try
// to auto-pause at `end` (the player won't honour it reliably). Instead a
// "Continue to quiz" CTA appears ~30s before the end mark and stays visible.
// The parent still offers an "I've already finished" escape so nobody is trapped.
const REVEAL_LEAD_SECONDS = 30;

interface VideoSegmentProps {
  video: VideoDeepLink;
  onReachedEnd?: () => void;
  onContinue?: () => void;
}

export function VideoSegment({
  video,
  onReachedEnd,
  onContinue,
}: VideoSegmentProps) {
  const duration = Math.max(0, video.end_seconds - video.start_seconds);
  const [showContinue, setShowContinue] = useState(duration <= REVEAL_LEAD_SECONDS);

  useEffect(() => {
    const revealMs = Math.max(0, duration - REVEAL_LEAD_SECONDS) * 1000;
    const revealTimer = setTimeout(() => setShowContinue(true), revealMs);
    const endTimer = setTimeout(() => onReachedEnd?.(), duration * 1000);
    return () => {
      clearTimeout(revealTimer);
      clearTimeout(endTimer);
    };
  }, [duration, onReachedEnd]);

  return (
    <div className="space-y-4">
      <div className="border border-border bg-foreground">
        <div className="relative aspect-video">
          <iframe
            className="absolute inset-0 h-full w-full"
            src={video.embed_url}
            title={video.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[13px] text-muted-foreground">
          <span className="text-foreground">{video.title}</span>
          {" · "}
          {video.channel_title}
        </div>
        {showContinue && onContinue ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={onContinue}
            className="animate-paper-in"
          >
            Continue to the check
          </Button>
        ) : null}
      </div>
    </div>
  );
}
