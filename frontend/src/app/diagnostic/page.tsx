"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Logo } from "@/components/Logo";
import { McqQuiz } from "@/components/McqQuiz";
import { MasteryBar } from "@/components/MasteryBar";
import type { ChoiceLabel, McqReveal } from "@/components/McqItem";
import { ApiError } from "@/lib/api";
import {
  useAnswerDiagnostic,
  useCompleteDiagnostic,
  useStartDiagnostic,
} from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { tierAverages, tierLabel } from "@/lib/utils";
import type { MasteryVector, StartDiagnostic } from "@/lib/types";

const REVEAL_MS = 6000;

type Phase = "loading" | "answering" | "complete";

export default function DiagnosticPage() {
  const router = useRouter();
  const { ready } = useRequireCode();
  const start = useStartDiagnostic();
  const answer = useAnswerDiagnostic();
  const complete = useCompleteDiagnostic();

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

  const finish = useCallback(async () => {
    const vec = await complete.mutateAsync();
    setMastery(vec);
    setPhase("complete");
  }, [complete]);

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
    setReveal({ isCorrect: res.is_correct, explanation: res.explanation });
    setRemaining(res.items_remaining);
    autoTimer.current = setTimeout(() => advance(res.items_remaining), REVEAL_MS);
  };

  if (phase === "loading") {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </main>
    );
  }

  if (phase === "complete" && mastery) {
    const tiers = tierAverages(mastery.entries);
    return (
      <main className="bg-aurora flex min-h-screen flex-col items-center justify-center gap-8 px-6 py-10">
        <div className="animate-fade-in-up space-y-3 text-center">
          <span className="mx-auto inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
            <Sparkles className="h-7 w-7" />
          </span>
          <h1 className="text-4xl font-semibold tracking-tight">
            <span className="text-gradient">Diagnostic complete</span>
          </h1>
          <p className="text-muted-foreground">
            Here&apos;s your starting picture — average mastery per tier.
          </p>
        </div>
        <Card className="animate-fade-in-up w-full max-w-2xl">
          <CardContent className="space-y-4 p-6">
            {tiers.map((t) => (
              <MasteryBar
                key={t.tier}
                label={tierLabel(t.tier)}
                value={t.average}
              />
            ))}
          </CardContent>
        </Card>
        <Button
          size="xl"
          variant="brand"
          onClick={() => router.push("/dashboard")}
        >
          Begin learning
        </Button>
      </main>
    );
  }

  if (!data) return null;
  const total = data.items.length;
  const item = data.items[index];

  return (
    <main className="bg-aurora flex min-h-screen flex-col items-center px-6 py-10">
      <div className="mb-8 flex w-full max-w-2xl items-center justify-between">
        <Logo size={28} />
        <span className="rounded-full border border-border bg-card/70 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
          Placement quiz
        </span>
      </div>
      <McqQuiz
        name={`diagnostic-${item.id}`}
        progressLabel={`Question ${index + 1} of ${total}`}
        progressValue={(index / total) * 100}
        item={item}
        selected={selected}
        onSelect={setSelected}
        onSubmit={onSubmit}
        submitLabel="Submit answer"
        submitting={answer.isPending}
        reveal={reveal}
        onNext={() => advance(remaining)}
        nextLabel={remaining <= 0 ? "See results" : "Next question"}
      />
    </main>
  );
}
