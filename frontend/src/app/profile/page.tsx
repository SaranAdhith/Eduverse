"use client";

import { useEffect, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/AppShell";
import { LearningCurve } from "@/components/LearningCurve";
import { masteryFill } from "@/components/MasteryBar";
import { useCurrentPath, useMastery } from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { useJournal, useParticipant } from "@/lib/store";
import {
  elapsedText,
  MASTERY_THRESHOLD,
  tierAverages,
  tierName,
  TOTAL_TOPICS,
} from "@/lib/utils";

// The participant's own record of the run. Everything here is read from real
// values: the mastery vector and path come from the server, and the curve and
// per-item correct counts from the local journal (see lib/store.ts).
//
// There is deliberately no name/email/course form. Participants are identified
// by code alone — the backend stores no personal fields, and collecting them
// would break the anonymity the consent text promises.
export default function ProfilePage() {
  const { ready } = useRequireCode();
  const code = useParticipant((s) => s.code);
  const mastery = useMastery(ready);
  const path = useCurrentPath();
  const journal = useJournal();
  const hydrate = useJournal((s) => s.hydrate);

  const [, tick] = useState(0);
  useEffect(() => hydrate(), [hydrate]);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const entries = mastery.data?.entries ?? [];
  const attemptedEntries = entries.filter((e) => e.attempts > 0);
  const mastered = entries.filter(
    (e) => e.p_mastered >= MASTERY_THRESHOLD,
  ).length;
  const items = entries.reduce((n, e) => n + e.attempts, 0);
  const mean =
    attemptedEntries.length > 0
      ? attemptedEntries.reduce((a, e) => a + e.p_mastered, 0) /
        attemptedEntries.length
      : 0;

  const stats = [
    {
      label: "Mastered",
      value: `${mastered}/${TOTAL_TOPICS}`,
      note: `at or past ${MASTERY_THRESHOLD.toFixed(2)}`,
    },
    {
      label: "Items answered",
      value: String(items),
      note: "across the whole run",
    },
    {
      label: "Topics attempted",
      value: String(attemptedEntries.length),
      note: `of ${TOTAL_TOPICS}`,
    },
    {
      label: "Mean estimate",
      value: mean.toFixed(2),
      note: "across attempted topics",
    },
  ];

  const tiers = tierAverages(entries);
  const review = attemptedEntries
    .filter((e) => e.p_mastered < MASTERY_THRESHOLD)
    .sort((a, b) => a.p_mastered - b.p_mastered)
    .slice(0, 5);

  return (
    <AppShell>
      <div className="max-w-[1080px] px-8 pb-24 pt-10 lg:px-14">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="kicker mb-2">Participant {code ?? "—"}</div>
            <h1 className="font-display text-4xl">Your record</h1>
          </div>
          <div className="text-[13px] text-faint">
            {path.data ? `Block ${path.data.block} · ` : null}
            session {elapsedText(journal.startedAt)}
          </div>
        </header>

        {mastery.isLoading ? (
          <div className="space-y-6">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-72 w-full" />
          </div>
        ) : (
          <>
            <div className="mb-9 grid grid-cols-2 border border-border bg-card lg:grid-cols-4">
              {stats.map((s, i) => (
                <div
                  key={s.label}
                  className={`flex flex-col gap-1.5 px-6 py-5 ${
                    i < stats.length - 1 ? "lg:border-r lg:border-border-soft" : ""
                  }`}
                >
                  <span className="text-[11.5px] uppercase tracking-[0.12em] text-faint">
                    {s.label}
                  </span>
                  <span className="font-mono text-[27px] leading-none">
                    {s.value}
                  </span>
                  <span className="text-[12.5px] text-muted-foreground">
                    {s.note}
                  </span>
                </div>
              ))}
            </div>

            <section className="mb-9 border border-border bg-card px-7 pb-5 pt-6">
              <div className="mb-1 flex flex-wrap items-baseline justify-between gap-3">
                <h2 className="font-display text-[22px]">Learning curve</h2>
                <span className="text-[12.5px] text-faint">
                  mean mastery across attempted topics, at each check
                </span>
              </div>
              <LearningCurve entries={journal.entries} />
            </section>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.15fr_0.85fr]">
              <section className="border border-border bg-card">
                <div className="border-b border-border-soft px-6 py-5">
                  <h2 className="font-display text-[22px]">Topics attempted</h2>
                </div>
                <div className="grid grid-cols-[1fr_62px_78px_108px] gap-3 border-b border-border-soft px-6 py-2.5 text-[11px] uppercase tracking-[0.1em] text-faint">
                  <span>Topic</span>
                  <span className="text-right">Items</span>
                  <span className="text-right">Correct</span>
                  <span className="text-right">Mastery</span>
                </div>
                {attemptedEntries.length === 0 ? (
                  <p className="px-6 py-9 text-sm text-faint">
                    Nothing attempted yet.
                  </p>
                ) : (
                  attemptedEntries.map((e) => (
                    <div
                      key={e.topic_id}
                      className="grid grid-cols-[1fr_62px_78px_108px] items-center gap-3 border-b border-border-soft px-6 py-3 last:border-b-0"
                    >
                      <span className="text-sm">{e.topic_name}</span>
                      <span className="text-right font-mono text-[13px] text-muted-foreground">
                        {e.attempts}
                      </span>
                      <span className="text-right font-mono text-[13px] text-muted-foreground">
                        {journal.correctByTopic[e.topic_id] ?? "—"}
                      </span>
                      <span className="flex items-center justify-end gap-2.5">
                        <span className="h-[5px] w-[54px] bg-track">
                          <span
                            className={`block h-full ${masteryFill(e.p_mastered, e.attempts)}`}
                            style={{ width: `${e.p_mastered * 100}%` }}
                          />
                        </span>
                        <span className="min-w-[34px] text-right font-mono text-[13px]">
                          {e.p_mastered.toFixed(2)}
                        </span>
                      </span>
                    </div>
                  ))
                )}
                <p className="px-6 py-3 text-[11.5px] leading-relaxed text-faint">
                  Items and mastery come from the server. Correct counts are
                  tallied in this browser, so they restart if you resume
                  elsewhere.
                </p>
              </section>

              <div className="flex flex-col gap-6">
                <section className="border border-border bg-card px-6 py-5">
                  <h2 className="mb-4 font-display text-[22px]">By tier</h2>
                  <div className="flex flex-col gap-3.5">
                    {tiers.map((t) => (
                      <div key={t.tier}>
                        <div className="mb-1.5 flex justify-between text-[13px]">
                          <span>{tierName(t.tier)}</span>
                          <span className="font-mono text-muted-foreground">
                            {t.average.toFixed(2)}
                          </span>
                        </div>
                        <div className="h-1.5 bg-track">
                          <div
                            className={`h-full ${masteryFill(t.average)}`}
                            style={{ width: `${t.average * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="border border-border bg-card px-6 py-5">
                  <h2 className="mb-1.5 font-display text-[22px]">
                    Worth revisiting
                  </h2>
                  <p className="mb-4 text-[13px] text-muted-foreground">
                    Attempted, but the estimate has not settled yet.
                  </p>
                  {review.length === 0 ? (
                    <p className="text-[13.5px] text-faint">
                      Nothing flagged. Keep going.
                    </p>
                  ) : (
                    <div className="flex flex-col gap-2.5">
                      {review.map((r) => (
                        <div
                          key={r.topic_id}
                          className="flex items-baseline justify-between gap-3 border-b border-border-soft pb-2.5 last:border-b-0"
                        >
                          <span className="text-sm">{r.topic_name}</span>
                          <span className="font-mono text-[13px] text-destructive">
                            {r.p_mastered.toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            </div>

            <section
              id="consent"
              className="note-panel mt-10 max-w-[720px] px-6 py-5"
            >
              <div className="kicker kicker-sm mb-2">Study information</div>
              <p className="text-[13.5px] leading-relaxed text-secondary-foreground">
                You are taking part in a study of adaptive sequencing in
                programming education. Responses, timings and topic order are
                stored against your participant code only — no name, email or
                other identifying detail is collected. You may withdraw at any
                time by contacting the researcher with your code.
              </p>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
