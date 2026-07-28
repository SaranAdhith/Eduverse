"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";
import type { MasteryEntry, PathStep } from "@/lib/types";

// A ruled strip of the block's steps: passed, current, and the count still to
// come. Passed steps link to a read-only review of their chunk. Status is
// carried by a text mark as well as the rule colour, never colour alone.
interface PathProgressProps {
  steps: PathStep[];
  currentStepId: string | null;
  totalTopics: number;
  masteryByTopic?: MasteryEntry[];
}

export function PathProgress({
  steps,
  currentStepId,
  totalTopics,
  masteryByTopic = [],
}: PathProgressProps) {
  const upcoming = Math.max(0, totalTopics - steps.length);
  const nameOf = (topicId: string) =>
    masteryByTopic.find((e) => e.topic_id === topicId)?.topic_name ?? topicId;

  return (
    <div className="border border-border bg-card">
      {steps.map((step) => {
        const isCurrent = step.id === currentStepId;
        const isPassed = step.status === "passed";
        const body = (
          <div
            className={cn(
              "grid grid-cols-[30px_1fr_auto] items-center gap-4 border-b border-border-soft border-l-2 px-4 py-3 text-sm transition-colors",
              isCurrent
                ? "border-l-primary bg-accent"
                : "border-l-transparent",
              isPassed && !isCurrent && "hover:bg-secondary",
            )}
          >
            <span className="font-mono text-xs text-faint">
              {String(step.step_index + 1).padStart(2, "0")}
            </span>
            <span className={cn(isCurrent && "font-medium")}>
              {nameOf(step.topic_id)}
            </span>
            <span
              className={cn(
                "font-mono text-[11px] uppercase tracking-[0.12em]",
                isPassed ? "text-primary" : "text-faint",
              )}
            >
              {isPassed ? "cleared" : isCurrent ? "current" : step.status}
            </span>
          </div>
        );
        return isPassed ? (
          <Link
            key={step.id}
            href={`/learn/${step.id}`}
            aria-label={`Review ${nameOf(step.topic_id)}`}
            className="block"
          >
            {body}
          </Link>
        ) : (
          <div key={step.id} aria-current={isCurrent ? "step" : undefined}>
            {body}
          </div>
        );
      })}
      {upcoming > 0 ? (
        <div className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.12em] text-faint">
          + {upcoming} more to come
        </div>
      ) : null}
    </div>
  );
}
