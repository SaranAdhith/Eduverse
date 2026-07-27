"use client";

import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Choice } from "@/lib/types";

export type ChoiceLabel = "A" | "B" | "C" | "D";

// DOC_07 §4/§6: one multiple-choice item. Choices are REAL radio inputs (visually
// styled), so keyboard + screen-reader behaviour comes for free. Correctness is
// signalled with an icon + label, never colour alone (§6).
export interface McqReveal {
  isCorrect: boolean;
  explanation: string;
}

interface McqItemProps {
  name: string;
  stem: string;
  stemCode: string | null;
  choices: Choice[];
  selected: ChoiceLabel | null;
  onSelect: (label: ChoiceLabel) => void;
  disabled?: boolean;
  reveal?: McqReveal | null;
}

export function McqItem({
  name,
  stem,
  stemCode,
  choices,
  selected,
  onSelect,
  disabled = false,
  reveal = null,
}: McqItemProps) {
  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <p className="text-lg font-medium leading-relaxed">{stem}</p>
        {stemCode ? (
          <pre className="overflow-x-auto rounded-md border bg-muted/60 p-4 font-mono text-sm">
            <code>{stemCode}</code>
          </pre>
        ) : null}
      </div>

      <fieldset
        className="space-y-3"
        disabled={disabled}
        aria-label="Answer choices"
      >
        {choices.map((choice) => {
          const isSelected = selected === choice.label;
          const showReveal = reveal && isSelected;
          return (
            <label
              key={choice.label}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors",
                "hover:bg-accent/40 focus-within:ring-2 focus-within:ring-ring",
                isSelected && !reveal && "border-primary bg-accent/40",
                showReveal &&
                  reveal.isCorrect &&
                  "border-success bg-success/10",
                showReveal &&
                  !reveal.isCorrect &&
                  "border-destructive bg-destructive/10",
                disabled && "cursor-default",
              )}
            >
              <input
                type="radio"
                name={name}
                value={choice.label}
                checked={isSelected}
                onChange={() => onSelect(choice.label)}
                disabled={disabled}
                className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]"
              />
              <span className="flex-1 text-base leading-relaxed">
                <span className="mr-2 font-mono text-sm text-muted-foreground">
                  {choice.label}.
                </span>
                {choice.text}
              </span>
              {showReveal ? (
                <span
                  className={cn(
                    "flex items-center gap-1 text-sm font-medium",
                    reveal.isCorrect ? "text-success" : "text-destructive",
                  )}
                >
                  {reveal.isCorrect ? (
                    <>
                      <Check className="h-4 w-4" aria-hidden />
                      Correct
                    </>
                  ) : (
                    <>
                      <X className="h-4 w-4" aria-hidden />
                      Incorrect
                    </>
                  )}
                </span>
              ) : null}
            </label>
          );
        })}
      </fieldset>

      {reveal ? (
        <div
          className="animate-fade-in rounded-md border bg-muted/40 p-4 text-sm leading-relaxed"
          role="status"
        >
          <span className="font-medium">
            {reveal.isCorrect ? "Nice — " : "Not quite. "}
          </span>
          {reveal.explanation}
        </div>
      ) : null}
    </div>
  );
}
