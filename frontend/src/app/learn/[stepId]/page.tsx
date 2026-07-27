"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { LessonMarkdown } from "@/components/LessonMarkdown";
import { VideoSegment } from "@/components/VideoSegment";
import { useChunk, useCurrentPath, useLogChunkView } from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";

const BLOCK = process.env.NEXT_PUBLIC_DEFAULT_BLOCK ?? "A";

export default function LearnPage({
  params,
}: {
  params: { stepId: string };
}) {
  const { stepId } = params;
  const { ready } = useRequireCode();
  const chunk = useChunk(stepId);
  const path = useCurrentPath(BLOCK);
  const logChunkView = useLogChunkView();

  const [videoDone, setVideoDone] = useState(false);
  const [finishedManually, setFinishedManually] = useState(false);

  // DOC_08 §5: tell the backend when the lesson is opened and closed — it can't
  // observe on-lesson time itself. Fire once per mount (a ref guards the dev
  // strict-mode double-invoke), and fire `unload` on the way out.
  const loaded = chunk.isSuccess;
  const loggedRef = useRef(false);
  const logMutate = logChunkView.mutate;
  useEffect(() => {
    if (!loaded || loggedRef.current) return;
    loggedRef.current = true;
    logMutate({ step_id: stepId, phase: "load" });
    return () => {
      logMutate({ step_id: stepId, phase: "unload" });
    };
  }, [loaded, stepId, logMutate]);

  const step = path.data?.steps.find((s) => s.id === stepId);
  const isReview = step?.status === "passed";

  if (!ready || chunk.isLoading) {
    return (
      <main className="container max-w-3xl space-y-6 py-10">
        <Skeleton className="h-4 w-52" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
        <p className="text-center text-sm text-muted-foreground">
          Preparing your lesson…
        </p>
      </main>
    );
  }

  if (chunk.isError || !chunk.data) {
    return (
      <main className="container max-w-3xl space-y-4 py-10 text-center">
        <p className="text-muted-foreground">
          We couldn&apos;t load this lesson. Please try again shortly.
        </p>
        <Button asChild variant="outline">
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </main>
    );
  }

  const data = chunk.data;
  const video = data.video;
  const hasVideo = video !== null;
  const gateReady = isReview || !hasVideo || videoDone || finishedManually;

  return (
    <main className="container max-w-3xl space-y-8 py-10">
      <nav
        className="flex items-center gap-1 text-sm text-muted-foreground"
        aria-label="Breadcrumb"
      >
        <Link href="/dashboard" className="hover:text-foreground">
          Dashboard
        </Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">{data.topic.name}</span>
        {step ? (
          <>
            <ChevronRight className="h-4 w-4" />
            <span>Step {step.step_index + 1}</span>
          </>
        ) : null}
      </nav>

      {isReview ? (
        <Badge variant="success">Reviewing a completed topic</Badge>
      ) : null}

      <article>
        <LessonMarkdown markdown={data.lesson_markdown} />
      </article>

      {video ? (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Watch</h2>
          <VideoSegment
            video={video}
            onReachedEnd={() => {
              setVideoDone(true);
              logChunkView.mutate({
                step_id: stepId,
                phase: "video_end",
                video_seconds_watched: video.end_seconds - video.start_seconds,
              });
            }}
            onContinue={() => setVideoDone(true)}
          />
        </section>
      ) : null}

      <footer className="flex flex-col items-start gap-3 border-t pt-6">
        {isReview ? (
          <Button asChild size="lg" variant="outline">
            <Link href="/dashboard">Back to dashboard</Link>
          </Button>
        ) : (
          <>
            {gateReady ? (
              <Button asChild size="lg" variant="brand">
                <Link href={`/learn/${stepId}/gate`}>
                  Ready for the gate quiz
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            ) : (
              <Button size="lg" disabled>
                Ready for the gate quiz
                <ArrowRight className="h-4 w-4" />
              </Button>
            )}
            {hasVideo && !gateReady ? (
              <button
                type="button"
                onClick={() => setFinishedManually(true)}
                className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
              >
                I&apos;ve already finished the video
              </button>
            ) : null}
          </>
        )}
      </footer>
    </main>
  );
}
