"use client";

import { useEffect } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/AppShell";
import { MasteryEstimate } from "@/components/MasteryBar";
import { PathProgress } from "@/components/PathProgress";
import { useCreatePath, useCurrentPath, useMastery } from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { MASTERY_THRESHOLD, tierLabel, tierName } from "@/lib/utils";

// The Session screen: what you are working on now, how close the estimate is to
// the threshold, and the way in to the lesson. The study condition is never
// shown — only the topic that was chosen.
export default function DashboardPage() {
  const { ready } = useRequireCode();
  const path = useCurrentPath();
  const mastery = useMastery(ready);
  const createPath = useCreatePath();

  // Get-or-create: a fresh participant has no path for the block yet.
  useEffect(() => {
    if (
      path.isSuccess &&
      path.data === null &&
      !createPath.isPending &&
      !createPath.isSuccess
    ) {
      createPath.mutate({});
    }
  }, [path.isSuccess, path.data, createPath]);

  const loading =
    !ready || path.isLoading || (path.data === null && !createPath.isError);

  const current = path.data?.current_step ?? null;
  const entries = mastery.data?.entries ?? [];
  const currentEntry = current
    ? entries.find((e) => e.topic_id === current.topic_id)
    : undefined;
  const passedSteps = path.data?.steps.filter((s) => s.status === "passed") ?? [];
  const nextStep = path.data?.steps.find(
    (s) => current && s.step_index === current.step_index + 1,
  );
  const nextName = nextStep
    ? (entries.find((e) => e.topic_id === nextStep.topic_id)?.topic_name ??
      nextStep.topic_id)
    : "block complete";

  return (
    <AppShell>
      <div className="max-w-[880px] px-8 pb-24 pt-10 lg:px-14">
        {loading ? (
          <div className="space-y-6">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-10 w-96" />
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : path.data?.completed ? (
          <div className="animate-paper-in">
            <div className="kicker mb-2">Block {path.data.block} complete</div>
            <h1 className="mb-3 font-display text-4xl">
              Every topic in this block is cleared.
            </h1>
            <p className="max-w-[560px] text-base text-secondary-foreground">
              All {path.data.total_topics} topics reached the{" "}
              {MASTERY_THRESHOLD.toFixed(2)} threshold. Your next block begins
              when the researcher opens it.
            </p>
            <div className="mt-7 flex gap-3">
              <Button asChild>
                <Link href="/profile">See your profile</Link>
              </Button>
              <Button asChild variant="secondary">
                <Link href="/curriculum">Review the curriculum</Link>
              </Button>
            </div>
          </div>
        ) : current ? (
          <div className="animate-paper-in">
            <header className="mb-9 flex flex-wrap items-baseline justify-between gap-4">
              <div>
                <div className="kicker mb-2">
                  Current topic
                  {currentEntry ? ` · ${tierLabel(currentEntry.tier)}` : null}
                </div>
                <h1 className="font-display text-4xl">
                  {currentEntry?.topic_name ?? current.topic_id}
                </h1>
              </div>
              <div className="flex flex-col gap-1 text-right">
                <span className="kicker kicker-sm">Progress</span>
                <span className="font-mono text-sm text-secondary-foreground">
                  {path.data?.passed_count}/{path.data?.total_topics} passed ·
                  step {current.step_index + 1}
                </span>
              </div>
            </header>

            {currentEntry ? (
              <MasteryEstimate
                value={currentEntry.p_mastered}
                attempts={currentEntry.attempts}
                className="mb-7"
              />
            ) : null}

            <div className="flex flex-wrap items-center gap-4">
              <Button asChild>
                <Link href={`/learn/${current.id}`}>
                  {current.attempts > 0 ? "Resume lesson" : "Open lesson"}
                </Link>
              </Button>
              <span className="text-[13.5px] text-muted-foreground">
                Next: {nextName}
              </span>
            </div>

            <section className="mt-12 border-t border-border pt-5">
              <div className="kicker kicker-sm mb-3">Your path</div>
              <PathProgress
                steps={path.data?.steps ?? []}
                currentStepId={current.id}
                totalTopics={path.data?.total_topics ?? 0}
                masteryByTopic={entries}
              />
            </section>

            <section className="mt-11 flex flex-wrap gap-10 border-t border-border pt-5">
              <div className="max-w-[340px]">
                <div className="kicker kicker-sm mb-2">Why this topic</div>
                <p className="text-[13.5px] leading-relaxed text-muted-foreground">
                  Chosen from the topics whose prerequisites you have already
                  cleared.
                </p>
              </div>
              <div className="max-w-[340px]">
                <div className="kicker kicker-sm mb-2">Cleared so far</div>
                <p className="text-[13.5px] leading-relaxed text-muted-foreground">
                  {passedSteps.length > 0
                    ? passedSteps
                        .slice(-3)
                        .map(
                          (s) =>
                            entries.find((e) => e.topic_id === s.topic_id)
                              ?.topic_name ?? s.topic_id,
                        )
                        .join(" · ")
                    : "Nothing yet — this is your first topic."}
                </p>
              </div>
              <div className="max-w-[340px]">
                <div className="kicker kicker-sm mb-2">Tier</div>
                <p className="text-[13.5px] leading-relaxed text-muted-foreground">
                  {currentEntry
                    ? `${tierLabel(currentEntry.tier)} · ${tierName(currentEntry.tier)}`
                    : "—"}
                </p>
              </div>
            </section>
          </div>
        ) : (
          <div className="animate-paper-in">
            <h1 className="mb-3 font-display text-[32px]">
              Setting up your path…
            </h1>
            <p className="text-base text-secondary-foreground">
              {createPath.isError
                ? "Something went wrong building your path. Please refresh."
                : "This only takes a moment."}
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
