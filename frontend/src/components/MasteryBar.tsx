"use client";

import { cn } from "@/lib/utils";

// DOC_07 §4: a single mastery bar. Colour is never the only signal — the numeric
// percentage is always shown alongside.
interface MasteryBarProps {
  label: string;
  value: number; // 0..1
  sublabel?: string;
  className?: string;
}

export function MasteryBar({
  label,
  value,
  sublabel,
  className,
}: MasteryBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{pct}%</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} mastery ${pct} percent`}
      >
        <div
          className="h-full rounded-full bg-brand-gradient transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {sublabel ? (
        <p className="text-xs text-muted-foreground">{sublabel}</p>
      ) : null}
    </div>
  );
}
