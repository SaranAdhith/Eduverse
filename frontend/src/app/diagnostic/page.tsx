"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { McqQuiz } from "@/components/McqQuiz";
import { masteryFill } from "@/components/MasteryBar";
import type { ChoiceLabel, McqReveal } from "@/components/McqItem";
import { ApiError } from "@/lib/api";
import {
  useAnswerDiagnostic,
  useCompleteDiagnostic,
  useStartDiagnostic,
} from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { meanAttemptedMastery, useJournal, useParticipant } from "@/lib/store";
import { tierAverages, tierLabel, tierName } from "@/lib/utils";
import type { MasteryVector, StartDiagnostic } from "@/lib/types";

const REVEAL_MS = 6000;

type Phase = "loading" | "answering" | "complete";

// The placement paper. Items are delivered and scored one at a time (each answer
// runs a BKT update server-side, and the response time is study data), so the
// paper metaphor is the frame — not a batch submit.
export default function DiagnosticPage() {
  const router = useRouter();
  const { ready } = useRequireCode();
  const code = useParticipant((s) => s.code);
  const start = useStartDiagnostic();
  const answer = useAnswerDiagnostic();
  const complete = useCompleteDiagnostic();
  const recordItem = useJournal((s) => s.recordItem);
  const recordCheckpoint = useJournal((s) => s.recordCheckpoint);
  const hydrateJournal = useJournal((s) => s.hydrate);

  const [phase, setPhase] = useState<Phase>("loading");
  const [data, setData] = useState<StartDiagnostic | null>(null);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<ChoiceLabel | null>(null);
  const [reveal, setReveal] = useState<McqReveal | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [mastery, setMastery] = useState<MasteryVector | null>(null);

  const shownAt = useRef<number>(Date.now());
  const autoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedRef = useRef(false);

  useEffect(() => hydrateJournal(), [hydrateJournal]);

  const finish = useCallback(async () => {
    const vec = await complete.mutateAsync();
    setMastery(vec);
    // First real mastery reading of the run — the curve starts here.
    recordCheckpoint({
      mean: meanAttemptedMastery(vec.entries),
      correct: true,
      topicId: "diagnostic",
    });
    setPhase("complete");
  }, [complete, recordCheckpoint]);

  const advance = useCallback(
    (left: number) => {
      if (autoTimer.current) clearTimeout(autoTimer.current);
      if (left <= 0) {
        void finish();
        return;
      }
      setIndex((i) => i + 1);
      setSelected(null);
      setReveal(null);
      shownAt.current = Date.now();
    },
    [finish],
  );

  // Start (or resume) the diagnostic once, after hydration.
  useEffect(() => {
    if (!ready || startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const res = await start.mutateAsync();
        setData(res);
        if (res.items_answered >= res.items.length) {
          await finish();
        } else {
          setIndex(res.items_answered);
          shownAt.current = Date.now();
          setPhase("answering");
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          router.replace("/dashboard"); // already completed
        }
      }
    })();
  }, [ready, start, finish, router]);

  useEffect(
    () => () => {
      if (autoTimer.current) clearTimeout(autoTimer.current);
    },
    [],
  );

  const onSubmit = async () => {
    if (!data || !selected) return;
    const item = data.items[index];
    const res = await answer.mutateAsync({
      session_id: data.session_id,
      question_id: item.id,
      selected_label: selected,
      response_ms: Date.now() - shownAt.current,
    });
    recordItem({ correct: res.is_correct, topicId: item.topic_id });
    setReveal({ isCorrect: res.is_correct, explanation: res.explanation });
    setRemaining(res.items_remaining);
    autoTimer.current = setTimeout(
      () => advance(res.items_remaining),
      REVEAL_MS,
    );
  };

  if (phase === "loading") {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-[860px] flex-col gap-6 px-8 py-14">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </main>
    );
  }

  if (phase === "complete" && mastery) {
    const tiers = tierAverages(mastery.entries);
    return (
      <main className="flex min-h-screen flex-col items-center px-8 pb-20 pt-14">
        <div className="w-full max-w-[860px] animate-paper-in">
          <h2 className="mb-3 font-display text-[32px]">
            Starting estimates set.
          </h2>
          <p className="mb-7 max-w-[560px] text-base text-secondary-foreground">
            These are first guesses, not verdicts. They will move as soon as you
            start answering.
          </p>
          <div className="border border-border bg-card">
            {tiers.map((t) => (
              <div
                key={t.tier}
                className="grid grid-cols-[26px_1fr_120px_56px] items-center gap-4 border-b border-border-soft px-[18px] py-3.5 last:border-b-0"
              >
                <span className="font-mono text-xs text-faint">
                  T{t.tier}
                </span>
                <span className="text-sm">{tierName(t.tier)}</span>
                <span className="h-[5px] bg-track">
                  <span
                    className={`block h-full ${masteryFill(t.average)}`}
                    style={{ width: `${t.average * 100}%` }}
                  />
                </span>
                <span className="text-right font-mono text-[13px] text-secondary-foreground">
                  {t.average.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
          <Button className="mt-7" onClick={() => router.push("/dashboard")}>
            Start learning
          </Button>
        </div>
      </main>
    );
  }

  if (!data) return null;
  const total = data.items.length;
  const item = data.items[index];
  const answered = index + (reveal ? 1 : 0);

  const META = [
    { label: "Questions", value: String(total) },
    { label: "Time limit", value: "None" },
    { label: "Marks", value: "Not graded" },
    { label: "Answered", value: `${answered} of ${total}` },
  ];

  return (
    <main className="flex min-h-screen flex-col items-center px-8 pb-20 pt-14">
      <div className="w-full max-w-[860px]">
        <div className="animate-paper-in border border-border bg-card shadow-sheet">
          <header className="border-b-2 border-foreground px-8 pb-[26px] pt-11 lg:px-14">
            <div className="flex items-start justify-between gap-6">
              <div>
                <div className="kicker">Eduverse · Placement diagnostic</div>
                <h1 className="mt-3 font-display text-[34px]">
                  Python placement paper
                </h1>
              </div>
              <div className="flex flex-col gap-[3px] pt-1 text-right">
                <span className="text-[11px] uppercase tracking-[0.14em] text-faint">
                  Participant
                </span>
                <span className="font-mono text-[17px] tracking-[0.08em]">
                  {code ?? "—"}
                </span>
              </div>
            </div>
          </header>

          <div className="grid grid-cols-2 border-b border-border md:grid-cols-4">
            {META.map((m, i) => (
              <div
                key={m.label}
                className={`px-5 py-3.5 ${
                  i < META.length - 1 ? "border-r border-border-soft" : ""
                } ${i === 0 ? "lg:pl-14" : ""}`}
              >
                <div className="mb-[3px] text-[10.5px] uppercase tracking-[0.14em] text-faint">
                  {m.label}
                </div>
                <div className="font-mono text-sm">{m.value}</div>
              </div>
            ))}
          </div>

          <div className="px-8 pt-[26px] lg:px-14">
            <p className="note-panel px-[18px] py-[15px] text-[13.5px] leading-relaxed text-secondary-foreground">
              <strong className="font-medium">Instructions.</strong> Answer each
              question in turn. Nothing here is graded; the paper only sets a
              starting point for your curriculum. If you have not met the
              material, answer as best you can and move on — the estimate will
              correct itself as you learn.
            </p>
          </div>

          <div className="px-8 pb-11 pt-8 lg:px-14">
            <McqQuiz
              name={`diagnostic-${item.id}`}
              progressLabel={`Question ${index + 1} of ${total}`}
              progressValue={(index / total) * 100}
              progressNote={tierLabel(
                Number(item.topic_id.replace(/^T/, "").split(".")[0]),
              )}
              item={item}
              selected={selected}
              onSelect={setSelected}
              onSubmit={onSubmit}
              submitLabel="Submit answer"
              submitting={answer.isPending}
              reveal={reveal}
              onNext={() => advance(remaining)}
              nextLabel={remaining <= 0 ? "See starting estimates" : "Continue"}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
