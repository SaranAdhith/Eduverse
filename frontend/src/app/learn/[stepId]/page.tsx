"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/AppShell";
import { LessonMarkdown } from "@/components/LessonMarkdown";
import { VideoSegment } from "@/components/VideoSegment";
import { useChunk, useCurrentPath, useLogChunkView } from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { tierFromTopicId, tierLabel } from "@/lib/utils";

export default function LearnPage({
  params,
}: {
  params: { stepId: string };
}) {
  const { stepId } = params;
  const { ready } = useRequireCode();
  const chunk = useChunk(stepId);
  const path = useCurrentPath();
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
      <AppShell>
        <div className="max-w-[760px] space-y-6 px-8 py-10 lg:px-14">
          <Skeleton className="h-4 w-52" />
          <Skeleton className="h-10 w-96" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-40 w-full" />
          <p className="text-sm text-muted-foreground">
            Preparing your lesson…
          </p>
        </div>
      </AppShell>
    );
  }

  if (chunk.isError || !chunk.data) {
    return (
      <AppShell>
        <div className="max-w-[760px] space-y-5 px-8 py-10 lg:px-14">
          <h1 className="font-display text-[28px]">
            We couldn&apos;t load this lesson.
          </h1>
          <p className="text-secondary-foreground">
            It may still be being written. Please try again shortly.
          </p>
          <Button asChild variant="secondary">
            <Link href="/dashboard">Back to session</Link>
          </Button>
        </div>
      </AppShell>
    );
  }

  const data = chunk.data;
  const video = data.video;
  const hasVideo = video !== null;
  const gateReady = isReview || !hasVideo || videoDone || finishedManually;
  const tier = tierFromTopicId(data.topic.topic_id);
  const prereqs = data.topic.prerequisite_ids;

  return (
    <AppShell>
      <article className="max-w-[760px] px-8 pb-24 pt-10 lg:px-14">
        <header className="mb-9">
          <div className="kicker mb-2">
            {isReview ? "Review · " : ""}
            {tier !== null ? tierLabel(tier) : data.topic.topic_id}
            {step ? ` · step ${step.step_index + 1}` : ""}
          </div>
          <h1 className="font-display text-4xl">{data.topic.name}</h1>
          {data.topic.description ? (
            <p className="mt-3 max-w-[620px] text-pretty text-base text-secondary-foreground">
              {data.topic.description}
            </p>
          ) : null}
        </header>

        <LessonMarkdown markdown={data.lesson_markdown} />

        {video ? (
          <section className="mt-12 border-t border-border pt-7">
            <div className="kicker kicker-sm mb-4">Watch</div>
            <VideoSegment
              video={video}
              onReachedEnd={() => {
                setVideoDone(true);
                logChunkView.mutate({
                  step_id: stepId,
                  phase: "video_end",
                  video_seconds_watched:
                    video.end_seconds - video.start_seconds,
                });
              }}
              onContinue={() => setVideoDone(true)}
            />
          </section>
        ) : null}

        <footer className="mt-12 flex flex-col items-start gap-4 border-t border-border pt-7">
          {isReview ? (
            <Button asChild variant="secondary">
              <Link href="/dashboard">Back to session</Link>
            </Button>
          ) : (
            <>
              {gateReady ? (
                <Button asChild>
                  <Link href={`/learn/${stepId}/gate`}>
                    I&apos;m ready — take the check
                  </Link>
                </Button>
              ) : (
                <Button disabled>I&apos;m ready — take the check</Button>
              )}
              {hasVideo && !gateReady ? (
                <button
                  type="button"
                  onClick={() => setFinishedManually(true)}
                  className="text-[13.5px] text-muted-foreground underline underline-offset-[3px] hover:text-foreground"
                >
                  I&apos;ve already finished the video
                </button>
              ) : null}
              <p className="text-[13px] text-faint">
                Five questions. Nothing is graded — the check only updates the
                estimate.
              </p>
            </>
          )}
        </footer>

        <section className="mt-11 flex flex-wrap gap-10 border-t border-border pt-5">
          <div className="max-w-[340px]">
            <div className="kicker kicker-sm mb-2">Prerequisites</div>
            <p className="font-mono text-[13px] leading-relaxed text-muted-foreground">
              {prereqs.length > 0
                ? prereqs.join(" · ")
                : "None — this is a foundation topic."}
            </p>
          </div>
          {data.fallback ? (
            <div className="max-w-[340px]">
              <div className="kicker kicker-sm mb-2">Note</div>
              <p className="text-[13.5px] leading-relaxed text-muted-foreground">
                No curated video was available for this topic, so the lesson
                stands on its own.
              </p>
            </div>
          ) : null}
        </section>
      </article>
    </AppShell>
  );
}
