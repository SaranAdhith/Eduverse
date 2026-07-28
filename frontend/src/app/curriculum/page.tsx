"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/AppShell";
import { masteryFill } from "@/components/MasteryBar";
import { useCurrentPath, useMastery } from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import {
  MASTERY_THRESHOLD,
  TIER_NAMES,
  TOTAL_TOPICS,
  tierName,
} from "@/lib/utils";
import type { MasteryEntry } from "@/lib/types";

// The whole curriculum at a glance: every topic grouped under its tier, the
// fill showing the current estimate. The legend carries the three states in
// words as well as colour.
const LEGEND = [
  { className: "bg-primary", label: "mastered" },
  { className: "bg-accent-mid", label: "in progress" },
  { className: "bg-border", label: "not started" },
];

export default function CurriculumPage() {
  const { ready } = useRequireCode();
  const mastery = useMastery(ready);
  const path = useCurrentPath();

  const entries = mastery.data?.entries ?? [];
  const currentTopicId = path.data?.current_step?.topic_id ?? null;

  const byTier = new Map<number, MasteryEntry[]>();
  for (const e of entries) {
    byTier.set(e.tier, [...(byTier.get(e.tier) ?? []), e]);
  }
  const tiers = [...byTier.keys()].sort((a, b) => a - b);

  return (
    <AppShell>
      <div className="px-8 pb-24 pt-10 lg:px-14">
        <div className="mb-2 flex flex-wrap items-end justify-between gap-4">
          <h1 className="font-display text-4xl">Curriculum</h1>
          <div className="flex flex-wrap items-center gap-[18px] text-[12.5px] text-muted-foreground">
            {LEGEND.map((l) => (
              <span key={l.label} className="flex items-center gap-2">
                <span className={`inline-block h-2.5 w-2.5 ${l.className}`} />
                {l.label}
              </span>
            ))}
          </div>
        </div>
        <p className="mb-9 max-w-[620px] text-[15px] text-muted-foreground">
          {TOTAL_TOPICS} topics across {Object.keys(TIER_NAMES).length} tiers.
          Each topic opens once its prerequisites are in hand; the fill is the
          current mastery estimate, and {MASTERY_THRESHOLD.toFixed(2)} is the
          bar to clear.
        </p>

        {mastery.isLoading ? (
          <div className="space-y-8">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-40 w-full" />
            ))}
          </div>
        ) : entries.length === 0 ? (
          <p className="text-[15px] text-muted-foreground">
            Complete the placement paper to see your curriculum.
          </p>
        ) : (
          <div className="flex flex-col gap-[30px]">
            {tiers.map((tier) => {
              const topics = byTier.get(tier) ?? [];
              const done = topics.filter(
                (t) => t.p_mastered >= MASTERY_THRESHOLD,
              ).length;
              return (
                <section
                  key={tier}
                  className="grid grid-cols-1 gap-7 border-b border-border-soft pb-7 lg:grid-cols-[180px_1fr]"
                >
                  <div className="lg:sticky lg:top-6 lg:self-start">
                    <div className="kicker kicker-sm">Tier {tier}</div>
                    <h2 className="mt-1 font-display text-[21px] leading-tight">
                      {tierName(tier)}
                    </h2>
                    <div className="mt-2 font-mono text-xs text-muted-foreground">
                      {done}/{topics.length} mastered
                    </div>
                  </div>

                  <ul className="grid grid-cols-[repeat(auto-fill,minmax(196px,1fr))] gap-2.5">
                    {topics.map((t) => {
                      const isCurrent = t.topic_id === currentTopicId;
                      return (
                        <li
                          key={t.topic_id}
                          className={`border px-3.5 py-3 ${
                            isCurrent
                              ? "border-primary bg-accent"
                              : "border-border bg-card"
                          }`}
                        >
                          <div className="flex items-baseline justify-between gap-2.5">
                            <span className="text-left text-[13.5px] leading-[1.35]">
                              {t.topic_name}
                            </span>
                            <span className="font-mono text-xs text-muted-foreground">
                              {t.p_mastered.toFixed(2)}
                            </span>
                          </div>
                          <div className="mt-2.5 h-1 bg-track">
                            <div
                              className={`h-full ${masteryFill(t.p_mastered, t.attempts)}`}
                              style={{ width: `${t.p_mastered * 100}%` }}
                            />
                          </div>
                          <div className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-faint">
                            {t.p_mastered >= MASTERY_THRESHOLD
                              ? "mastered"
                              : t.attempts > 0
                                ? "in progress"
                                : "not started"}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
