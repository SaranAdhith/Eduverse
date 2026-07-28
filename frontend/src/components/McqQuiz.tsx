"use client";

import { Button } from "@/components/ui/button";
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
  /** Right-hand mono note on the progress rule, e.g. "estimate 0.42 → 0.55". */
  progressNote?: string;
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
  progressNote,
}: McqQuizProps) {
  return (
    <div className="w-full animate-paper-in">
      <div className="mb-8">
        <div className="mb-2.5 flex items-baseline justify-between gap-4">
          <span className="kicker kicker-sm">{progressLabel}</span>
          {progressNote ? (
            <span className="font-mono text-[11px] text-faint">
              {progressNote}
            </span>
          ) : null}
        </div>
        <div
          className="h-1 w-full bg-track"
          role="progressbar"
          aria-valuenow={Math.round(progressValue)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={progressLabel}
        >
          <div
            className="h-full bg-primary transition-[width] duration-300"
            style={{ width: `${progressValue}%` }}
          />
        </div>
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

      <div className="mt-8 flex justify-start">
        {reveal && onNext ? (
          <Button variant="ink" onClick={onNext}>
            {nextLabel}
          </Button>
        ) : (
          <Button
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
