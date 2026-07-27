"use client";

import Link from "next/link";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";
import type { PathStep } from "@/lib/types";

// DOC_07 §4: horizontal stepper of past / current / lightly-previewed upcoming
// topics. Passed steps link to a read-only review of their chunk.
interface PathProgressProps {
  steps: PathStep[];
  currentStepId: string | null;
  totalTopics: number;
}

export function PathProgress({
  steps,
  currentStepId,
  totalTopics,
}: PathProgressProps) {
  const upcoming = Math.max(0, totalTopics - steps.length);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((step) => {
        const isCurrent = step.id === currentStepId;
        const isPassed = step.status === "passed";
        const chip = (
          <div
            className={cn(
              "flex min-w-[5.5rem] flex-col items-center gap-1 rounded-lg border px-3 py-2 text-center transition-colors",
              isCurrent && "border-primary bg-accent/50",
              isPassed && !isCurrent && "border-success/40 bg-success/5",
            )}
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
              {isPassed ? (
                <Check className="h-3.5 w-3.5 text-success" aria-hidden />
              ) : (
                step.step_index + 1
              )}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {step.topic_id}
            </span>
          </div>
        );
        return isPassed ? (
          <Link
            key={step.id}
            href={`/learn/${step.id}`}
            aria-label={`Review ${step.topic_id}`}
            className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {chip}
          </Link>
        ) : (
          <div key={step.id} aria-current={isCurrent ? "step" : undefined}>
            {chip}
          </div>
        );
      })}
      {Array.from({ length: upcoming }).map((_, i) => (
        <div
          key={`upcoming-${i}`}
          aria-hidden
          className="flex min-w-[5.5rem] flex-col items-center gap-1 rounded-lg border border-dashed px-3 py-2 text-center opacity-50"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
            {steps.length + i + 1}
          </span>
          <span className="font-mono text-xs text-muted-foreground">·····</span>
        </div>
      ))}
    </div>
  );
}
