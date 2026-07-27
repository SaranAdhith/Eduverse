"use client";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { McqItem, type ChoiceLabel, type McqReveal } from "@/components/McqItem";
import type { Choice } from "@/lib/types";

// DOC_07 §4: shared one-item-at-a-time quiz frame for the diagnostic and the
// gate. It owns layout only — the pages own the submit semantics (the diagnostic
// reveals per-item correctness; the gate batches answers and reveals nothing).
interface QuizItemView {
  id: string;
  stem: string;
  stem_code: string | null;
  choices: Choice[];
}

interface McqQuizProps {
  name: string;
  progressLabel: string;
  progressValue: number;
  item: QuizItemView;
  selected: ChoiceLabel | null;
  onSelect: (label: ChoiceLabel) => void;
  onSubmit: () => void;
  submitLabel: string;
  submitting?: boolean;
  reveal?: McqReveal | null;
  onNext?: () => void;
  nextLabel?: string;
}

export function McqQuiz({
  name,
  progressLabel,
  progressValue,
  item,
  selected,
  onSelect,
  onSubmit,
  submitLabel,
  submitting = false,
  reveal = null,
  onNext,
  nextLabel = "Next",
}: McqQuizProps) {
  return (
    <div className="mx-auto w-full max-w-2xl space-y-8">
      <div className="space-y-2">
        <p className="text-sm font-medium text-muted-foreground">
          {progressLabel}
        </p>
        <Progress
          value={progressValue}
          aria-label={progressLabel}
        />
      </div>

      <McqItem
        name={name}
        stem={item.stem}
        stemCode={item.stem_code}
        choices={item.choices}
        selected={selected}
        onSelect={onSelect}
        disabled={reveal !== null}
        reveal={reveal}
      />

      <div className="flex justify-end">
        {reveal && onNext ? (
          <Button size="lg" variant="brand" onClick={onNext}>
            {nextLabel}
          </Button>
        ) : (
          <Button
            size="lg"
            variant="brand"
            onClick={onSubmit}
            disabled={selected === null || submitting}
          >
            {submitting ? "Saving…" : submitLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
