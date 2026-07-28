"use client";

import { cn, MASTERY_THRESHOLD } from "@/lib/utils";

// Colour is never the only signal — the numeric estimate is always shown, and
// the 0.85 threshold is drawn as a hairline tick so the bar reads against it.
//
// Green = at or past threshold, sage = under way, sand = untouched.
export function masteryFill(value: number, attempts = 1): string {
  if (value >= MASTERY_THRESHOLD) return "bg-primary";
  if (attempts > 0) return "bg-accent-mid";
  return "bg-border-strong";
}

interface MasteryBarProps {
  label?: string;
  value: number; // 0..1
  attempts?: number;
  sublabel?: string;
  className?: string;
  /** Draw the 0.85 tick. */
  showThreshold?: boolean;
  height?: "sm" | "md";
}

export function MasteryBar({
  label,
  value,
  attempts = 1,
  sublabel,
  className,
  showThreshold = false,
  height = "sm",
}: MasteryBarProps) {
  const v = Math.min(1, Math.max(0, value));
  const pct = Math.round(v * 100);
  return (
    <div className={cn("space-y-2", className)}>
      {label ? (
        <div className="flex items-baseline justify-between gap-3 text-[13px]">
          <span>{label}</span>
          <span className="font-mono text-[13px] text-muted-foreground">
            {v.toFixed(2)}
          </span>
        </div>
      ) : null}
      <div
        className={cn(
          "relative w-full bg-track",
          height === "md" ? "h-2.5" : "h-1.5",
        )}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={
          label ? `${label} mastery estimate ${pct} percent` : undefined
        }
      >
        <div
          className={cn(
            "h-full transition-[width] duration-500",
            masteryFill(v, attempts),
          )}
          style={{ width: `${pct}%` }}
        />
        {showThreshold ? (
          <span
            aria-hidden
            className="absolute -top-1 bottom-[-4px] w-px bg-foreground"
            style={{ left: `${MASTERY_THRESHOLD * 100}%` }}
          />
        ) : null}
      </div>
      {sublabel ? (
        <p className="text-xs text-muted-foreground">{sublabel}</p>
      ) : null}
    </div>
  );
}

// The full estimate panel used on the Session screen: the number, the bar with
// its threshold tick, and the scale beneath it.
export function MasteryEstimate({
  value,
  attempts,
  delta,
  className,
}: {
  value: number;
  attempts?: number;
  delta?: string;
  className?: string;
}) {
  const v = Math.min(1, Math.max(0, value));
  return (
    <div className={cn("border border-border bg-card px-6 py-5", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <span className="text-[13px] text-muted-foreground">
          Estimated probability you have mastered this topic
        </span>
        <span className="font-mono text-[22px] leading-none">
          {v.toFixed(2)}
        </span>
      </div>
      <MasteryBar value={v} attempts={attempts} height="md" showThreshold />
      <div className="mt-2 flex justify-between font-mono text-[11px] text-faint">
        <span>0.00</span>
        <span>{delta ?? "updates after each answer"}</span>
        <span>threshold {MASTERY_THRESHOLD.toFixed(2)} &rarr;</span>
      </div>
    </div>
  );
}
