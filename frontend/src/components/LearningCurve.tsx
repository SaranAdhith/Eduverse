"use client";

import { MASTERY_THRESHOLD } from "@/lib/utils";
import type { JournalEntry } from "@/lib/store";

// Mean mastery across attempted topics, per item answered. Dots are coloured by
// whether that item was answered correctly, and the 0.85 threshold is a dashed
// rule so the curve reads against the bar the learner is actually clearing.
const W = 760;
const H = 220;
const LEFT = 46;
const RIGHT = 746;
const TOP = 20; // y for p = 1.0
const BOTTOM = 180; // y for p = 0.0

function y(p: number): number {
  return BOTTOM - Math.min(1, Math.max(0, p)) * (BOTTOM - TOP);
}

export function LearningCurve({ entries }: { entries: JournalEntry[] }) {
  if (entries.length < 2) {
    return (
      <div className="mt-4 flex h-[200px] items-center justify-center border border-dashed border-input text-sm text-faint">
        Answer a few items and your curve will appear here.
      </div>
    );
  }

  const step =
    entries.length > 1 ? (RIGHT - LEFT) / (entries.length - 1) : 0;
  const pts = entries.map((e, i) => ({
    x: LEFT + i * step,
    y: y(e.mean),
    correct: e.correct,
  }));
  const line = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = `${LEFT},${BOTTOM} ${line} ${RIGHT},${BOTTOM}`;

  return (
    <>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block h-[240px] w-full overflow-visible"
        role="img"
        aria-label={`Learning curve across ${entries.length} answered items, ending at a mean mastery estimate of ${entries[entries.length - 1].mean.toFixed(2)}`}
      >
        {[TOP, 60, 100, 140].map((gy) => (
          <line
            key={gy}
            x1={LEFT}
            y1={gy}
            x2={RIGHT}
            y2={gy}
            stroke="hsl(var(--border-soft))"
            strokeWidth={1}
          />
        ))}
        <line
          x1={LEFT}
          y1={BOTTOM}
          x2={RIGHT}
          y2={BOTTOM}
          stroke="hsl(var(--border-strong))"
          strokeWidth={1}
        />
        <line
          x1={LEFT}
          y1={y(MASTERY_THRESHOLD)}
          x2={RIGHT}
          y2={y(MASTERY_THRESHOLD)}
          stroke="hsl(var(--foreground))"
          strokeWidth={1}
          strokeDasharray="3 4"
        />
        <text
          x={RIGHT + 6}
          y={y(MASTERY_THRESHOLD) + 3}
          fontFamily="var(--font-mono), monospace"
          fontSize={10}
          fill="hsl(var(--foreground))"
        >
          {MASTERY_THRESHOLD.toFixed(2)}
        </text>

        {[
          { p: 1, label: "1.0" },
          { p: 0.5, label: "0.5" },
          { p: 0, label: "0.0" },
        ].map(({ p, label }) => (
          <text
            key={label}
            x={LEFT - 10}
            y={y(p) + 4}
            textAnchor="end"
            fontFamily="var(--font-mono), monospace"
            fontSize={10}
            fill="hsl(var(--faint))"
          >
            {label}
          </text>
        ))}

        <polyline points={area} fill="hsl(var(--accent))" stroke="none" />
        <polyline
          points={line}
          fill="none"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {pts.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={3}
            fill={
              p.correct ? "hsl(var(--primary))" : "hsl(var(--destructive))"
            }
            stroke="hsl(var(--card))"
            strokeWidth={1.5}
          />
        ))}

        <text
          x={LEFT}
          y={204}
          fontFamily="var(--font-mono), monospace"
          fontSize={10}
          fill="hsl(var(--faint))"
        >
          item 1
        </text>
        <text
          x={RIGHT}
          y={204}
          textAnchor="end"
          fontFamily="var(--font-mono), monospace"
          fontSize={10}
          fill="hsl(var(--faint))"
        >
          item {entries.length}
        </text>
      </svg>

      <div className="flex gap-6 border-t border-border-soft pt-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-primary" />
          correct response
        </span>
        <span className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-destructive" />
          incorrect response
        </span>
      </div>
    </>
  );
}
