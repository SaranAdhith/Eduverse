"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, CheckCircle2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { McqQuiz } from "@/components/McqQuiz";
import type { ChoiceLabel } from "@/components/McqItem";
import {
  useAdvancePath,
  useCurrentPath,
  useStartGate,
  useSubmitGate,
} from "@/lib/queries";
import { useRequireCode } from "@/lib/useRequireCode";
import { masteryBucket } from "@/lib/utils";
import type { GateAnswerIn, GateResult, GateStart } from "@/lib/types";

const BLOCK = process.env.NEXT_PUBLIC_DEFAULT_BLOCK ?? "A";

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
  const path = useCurrentPath(BLOCK);

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
      <main className="container max-w-2xl space-y-4 py-16 text-center">
        <p className="text-muted-foreground">
          This gate isn&apos;t available right now.
        </p>
        <Button asChild variant="outline">
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </main>
    );
  }

  if (!ready || startGate.isPending || !gate) {
    return (
      <main className="container max-w-2xl space-y-6 py-16">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-16 w-full" />
      </main>
    );
  }

  if (result) {
    const bucket = masteryBucket(result.posterior_at_gate);
    return (
      <main className="bg-aurora flex min-h-screen items-center justify-center px-6 py-16">
        <Card className="animate-fade-in-up w-full max-w-lg">
          <CardHeader className="items-center text-center">
            {result.passed ? (
              <span className="mb-1 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
                <CheckCircle2 className="h-8 w-8" aria-hidden />
              </span>
            ) : (
              <span className="mb-1 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <RotateCcw className="h-8 w-8" aria-hidden />
              </span>
            )}
            <CardTitle className="text-2xl">
              {result.passed ? "Passed!" : "Not yet — let's review"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6 text-center">
            <div className="flex flex-col items-center gap-2">
              <span className="text-sm text-muted-foreground">
                Your mastery of this topic
              </span>
              <Badge variant={result.passed ? "success" : "muted"}>
                {bucket}
              </Badge>
            </div>
            {result.passed ? (
              <Button
                size="lg"
                variant="brand"
                onClick={onContinue}
                disabled={advance.isPending}
              >
                Continue to next topic
                <ArrowRight className="h-4 w-4" />
              </Button>
            ) : (
              <div className="space-y-3">
                <p className="text-sm leading-relaxed text-muted-foreground">
                  You&apos;re close. A quick review of the lesson will get you
                  over the line — there&apos;s no penalty for trying again.
                </p>
                <Button asChild size="lg" variant="outline">
                  <Link href={`/learn/${stepId}`}>Back to the lesson</Link>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    );
  }

  const item = gate.items[index];
  return (
    <main className="bg-aurora min-h-screen py-10">
      <div className="mx-auto mb-8 flex max-w-2xl items-center gap-3 px-6 sm:px-0">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground">
          <CheckCircle2 className="h-5 w-5" />
        </span>
        <div>
          <h1 className="font-display text-xl font-semibold">
            Gate quiz · {gate.topic_id}
          </h1>
          <p className="text-sm text-muted-foreground">
            Pass to continue to the next topic.
          </p>
        </div>
      </div>
      <McqQuiz
        name={`gate-${item.id}`}
        progressLabel={`Question ${index + 1} of ${gate.items.length}`}
        progressValue={(index / gate.items.length) * 100}
        item={item}
        selected={selected}
        onSelect={setSelected}
        onSubmit={onSubmit}
        submitLabel={
          index + 1 < gate.items.length ? "Next question" : "Submit quiz"
        }
        submitting={submitGate.isPending}
      />
    </main>
  );
}
