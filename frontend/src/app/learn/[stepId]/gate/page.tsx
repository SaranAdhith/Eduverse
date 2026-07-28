"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/AppShell";
import { McqQuiz } from "@/components/McqQuiz";
import type { ChoiceLabel } from "@/components/McqItem";
import {
  useAdvancePath,
  useCurrentPath,
  useMastery,
  useStartGate,
  useSubmitGate,
} from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { meanAttemptedMastery, useJournal } from "@/lib/store";
import { masteryBucket, MASTERY_THRESHOLD } from "@/lib/utils";
import type { GateAnswerIn, GateResult, GateStart } from "@/lib/types";

export default function GatePage({
  params,
}: {
  params: { stepId: string };
}) {
  const { stepId } = params;
  const router = useRouter();
  const { ready } = useRequireCode();
  const startGate = useStartGate();
  const submitGate = useSubmitGate();
  const advance = useAdvancePath();
  const path = useCurrentPath();
  const mastery = useMastery(ready);
  const recordItem = useJournal((s) => s.recordItem);
  const recordCheckpoint = useJournal((s) => s.recordCheckpoint);

  const [gate, setGate] = useState<GateStart | null>(null);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<ChoiceLabel | null>(null);
  const [answers, setAnswers] = useState<GateAnswerIn[]>([]);
  const [result, setResult] = useState<GateResult | null>(null);
  const [failed, setFailed] = useState(false);

  const shownAt = useRef<number>(Date.now());
  const startedRef = useRef(false);

  useEffect(() => {
    if (!ready || startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const res = await startGate.mutateAsync(stepId);
        setGate(res);
        shownAt.current = Date.now();
      } catch {
        setFailed(true);
      }
    })();
  }, [ready, startGate, stepId]);

  const onSubmit = async () => {
    if (!gate || !selected) return;
    const item = gate.items[index];
    const next: GateAnswerIn[] = [
      ...answers,
      {
        question_id: item.id,
        selected_label: selected,
        response_ms: Date.now() - shownAt.current,
      },
    ];
    setAnswers(next);
    setSelected(null);

    if (index + 1 < gate.items.length) {
      setIndex((i) => i + 1);
      shownAt.current = Date.now();
      return;
    }
    const res = await submitGate.mutateAsync({ stepId, answers: next });
    setResult(res);
    // The gate reports how many of the five landed, and a fresh posterior —
    // both are real server values, so both go in the journal.
    const correct = Math.round(res.score * gate.items.length);
    for (let i = 0; i < gate.items.length; i += 1) {
      recordItem({ correct: i < correct, topicId: gate.topic_id });
    }
    const entries = (await mastery.refetch()).data?.entries;
    recordCheckpoint({
      mean: entries
        ? meanAttemptedMastery(entries)
        : res.posterior_at_gate,
      correct: res.passed,
      topicId: gate.topic_id,
    });
  };

  const onContinue = async () => {
    if (!result) return;
    if (result.next_step) {
      router.push(`/learn/${result.next_step.id}`);
      return;
    }
    // No next step returned — advance explicitly, then go home.
    if (path.data) await advance.mutateAsync(path.data.path_id);
    router.push("/dashboard");
  };

  if (failed) {
    return (
      <AppShell>
        <div className="max-w-[720px] space-y-5 px-8 py-10 lg:px-14">
          <h1 className="font-display text-[28px]">
            This check isn&apos;t available right now.
          </h1>
          <Button asChild variant="secondary">
            <Link href="/dashboard">Back to session</Link>
          </Button>
        </div>
      </AppShell>
    );
  }

  if (!ready || startGate.isPending || !gate) {
    return (
      <AppShell>
        <div className="max-w-[720px] space-y-6 px-8 py-10 lg:px-14">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-9 w-80" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      </AppShell>
    );
  }

  if (result) {
    // DOC_07 §4: the raw posterior is bucketed here so the 0.85 threshold
    // can't be reverse-engineered from a gate result.
    const bucket = masteryBucket(result.posterior_at_gate);
    const correct = Math.round(result.score * gate.items.length);
    return (
      <AppShell>
        <div className="max-w-[720px] px-8 pb-24 pt-10 lg:px-14">
          <div
            className={`animate-paper-in border px-8 py-8 ${
              result.passed
                ? "border-primary bg-accent"
                : "border-border bg-card"
            }`}
          >
            <div
              className={`kicker mb-2.5 ${
                result.passed ? "text-primary" : "text-muted-foreground"
              }`}
            >
              {result.passed ? "Threshold cleared" : "Not yet"}
            </div>
            <h1 className="mb-2.5 font-display text-[28px]">
              {result.passed
                ? "You can move on."
                : "One more pass at this one."}
            </h1>
            <p className="mb-6 max-w-[520px] text-[15px] text-secondary-foreground">
              {result.passed
                ? `You answered ${correct} of ${gate.items.length}, and the estimate cleared the ${MASTERY_THRESHOLD.toFixed(2)} threshold. This topic will resurface later for a short check.`
                : `You answered ${correct} of ${gate.items.length}. The estimate moved, but not far enough yet — that is the normal way through, not a setback. Nothing is lost by going again.`}
            </p>

            <div className="mb-7 flex items-baseline gap-3 border-t border-border-soft pt-4">
              <span className="text-[13px] text-muted-foreground">
                Your mastery of this topic
              </span>
              <span className="font-mono text-[15px]">{bucket}</span>
            </div>

            {result.passed ? (
              <Button onClick={onContinue} disabled={advance.isPending}>
                Continue to next topic
              </Button>
            ) : (
              <div className="flex flex-wrap items-center gap-4">
                <Button asChild>
                  <Link href={`/learn/${stepId}`}>Back to the lesson</Link>
                </Button>
                <span className="text-[13.5px] text-muted-foreground">
                  There is no penalty for trying again.
                </span>
              </div>
            )}
          </div>
        </div>
      </AppShell>
    );
  }

  const item = gate.items[index];
  return (
    <AppShell>
      <div className="max-w-[720px] px-8 pb-24 pt-10 lg:px-14">
        <header className="mb-9">
          <div className="kicker mb-2">Mastery check</div>
          <h1 className="font-display text-[32px]">
            {gate.items.length} questions on this topic
          </h1>
          <p className="mt-2 text-[13.5px] text-muted-foreground">
            Answers are reviewed together at the end — nothing is revealed as
            you go.
          </p>
        </header>
        <McqQuiz
          name={`gate-${item.id}`}
          progressLabel={`Question ${index + 1} of ${gate.items.length}`}
          progressValue={(index / gate.items.length) * 100}
          item={item}
          selected={selected}
          onSelect={setSelected}
          onSubmit={onSubmit}
          submitLabel={
            index + 1 < gate.items.length ? "Next question" : "Submit answers"
          }
          submitting={submitGate.isPending}
        />
      </div>
    </AppShell>
  );
}
