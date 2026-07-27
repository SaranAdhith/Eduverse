"use client";

import { useEffect } from "react";
import Link from "next/link";
import { BlockMath } from "react-katex";
import { ArrowRight, Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { MasteryBar } from "@/components/MasteryBar";
import { PathProgress } from "@/components/PathProgress";
import { ParticipantHeader } from "@/components/ParticipantHeader";
import { useCreatePath, useCurrentPath, useMastery } from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { tierAverages, tierLabel } from "@/lib/utils";

const BLOCK = process.env.NEXT_PUBLIC_DEFAULT_BLOCK ?? "A";

export default function DashboardPage() {
  const { ready } = useRequireCode();
  const path = useCurrentPath(BLOCK);
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
  const masteryByTopic = new Map(
    (mastery.data?.entries ?? []).map((e) => [e.topic_id, e]),
  );
  const currentEntry = current
    ? masteryByTopic.get(current.topic_id)
    : undefined;
  const tiers = tierAverages(mastery.data?.entries ?? []);

  return (
    <div className="bg-aurora min-h-screen">
      <ParticipantHeader
        block={path.data?.block ?? BLOCK}
        passedCount={path.data?.passed_count}
        totalTopics={path.data?.total_topics}
      />

      <main className="container grid gap-8 py-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-8">
          {loading ? (
            <Skeleton className="h-52 w-full" />
          ) : path.data?.completed ? (
            <Card>
              <CardHeader>
                <CardTitle>Block complete 🎉</CardTitle>
                <CardDescription>
                  You&apos;ve passed every topic in this block. Well done.
                </CardDescription>
              </CardHeader>
            </Card>
          ) : current ? (
            <Card className="relative overflow-hidden">
              <div className="absolute inset-x-0 top-0 h-1 bg-brand-gradient" />
              <CardHeader>
                <CardDescription className="flex items-center gap-2">
                  <span className="inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
                  Current topic
                </CardDescription>
                <CardTitle className="text-2xl">
                  {currentEntry?.topic_name ?? current.topic_id}
                </CardTitle>
                <p className="font-mono text-xs text-muted-foreground">
                  {current.topic_id} · step {current.step_index + 1}
                </p>
              </CardHeader>
              <CardContent className="space-y-6">
                {currentEntry ? (
                  <MasteryBar
                    label="Your mastery of this topic"
                    value={currentEntry.p_mastered}
                  />
                ) : null}
                <Button asChild size="lg" variant="brand">
                  <Link href={`/learn/${current.id}`}>
                    Open lesson
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Setting up your path…</CardTitle>
                <CardDescription>
                  This only takes a moment.
                </CardDescription>
              </CardHeader>
            </Card>
          )}

          {path.data ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Your path</CardTitle>
                <CardDescription>
                  {path.data.passed_count} of {path.data.total_topics} topics
                  passed ({Math.round(path.data.completion_pct)}%)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PathProgress
                  steps={path.data.steps}
                  currentStepId={current?.id ?? null}
                  totalTopics={path.data.total_topics}
                />
              </CardContent>
            </Card>
          ) : null}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Mastery by tier</CardTitle>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="How mastery is measured">
                    <Info className="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="text-sm">
                  <p className="mb-2 font-medium">How mastery is measured</p>
                  <p className="mb-3 text-muted-foreground">
                    Each answer updates a belief that you&apos;ve mastered a
                    topic, using Bayesian knowledge tracing:
                  </p>
                  <BlockMath math={"P(L_t) = P(L_{t-1} \\mid \\text{obs}) + \\bigl(1 - P(L_{t-1} \\mid \\text{obs})\\bigr)\\, P(T)"} />
                </PopoverContent>
              </Popover>
            </CardHeader>
            <CardContent className="space-y-4">
              {mastery.isLoading ? (
                <Skeleton className="h-32 w-full" />
              ) : tiers.length ? (
                tiers.map((t) => (
                  <MasteryBar
                    key={t.tier}
                    label={tierLabel(t.tier)}
                    value={t.average}
                  />
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  Complete the diagnostic to see your mastery.
                </p>
              )}
            </CardContent>
          </Card>
        </aside>
      </main>
    </div>
  );
}
