"use client";

import { cn } from "@/lib/utils";
import type { Choice } from "@/lib/types";

export type ChoiceLabel = "A" | "B" | "C" | "D";

// DOC_07 §4/§6: one multiple-choice item. Choices are REAL radio inputs (the
// native control is visually hidden but still focused and announced), so
// keyboard + screen-reader behaviour comes for free. Correctness is signalled
// with a text mark and the verdict line, never colour alone (§6).
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
  /** Mono kicker above the stem, e.g. "Predict the output". */
  kind?: string;
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
  kind,
}: McqItemProps) {
  return (
    <div>
      <div className="kicker kicker-sm mb-3.5">
        {kind ?? (stemCode ? "Predict the output" : "Concept check")}
      </div>
      <h2 className="mb-5 max-w-[700px] font-display text-[25px] leading-[1.35] text-pretty">
        {stem}
      </h2>
      {stemCode ? (
        <pre className="mb-[22px] overflow-x-auto border border-border bg-card px-5 py-[18px] font-mono text-sm leading-[1.75]">
          <code>{stemCode}</code>
        </pre>
      ) : null}

      <fieldset
        className="flex flex-col gap-2.5"
        disabled={disabled}
        aria-label="Answer choices"
      >
        {choices.map((choice) => {
          const isSelected = selected === choice.label;
          const isAnswer = reveal ? reveal.isCorrect && isSelected : false;
          // After the reveal we know only whether the participant's own pick
          // was right — the API withholds the key for the other options.
          const wrongPick = reveal ? !reveal.isCorrect && isSelected : false;
          const mark = isAnswer
            ? "correct"
            : wrongPick
              ? "your answer"
              : "";
          return (
            <label
              key={choice.label}
              className={cn(
                "flex w-full cursor-pointer items-center gap-3 border px-4 py-3.5 text-[15px] leading-[1.45] transition-colors",
                "focus-within:outline focus-within:outline-2 focus-within:outline-offset-1 focus-within:outline-ring",
                isSelected && !reveal
                  ? "border-primary bg-accent"
                  : "border-input bg-card",
                !reveal && !isSelected && "hover:border-primary",
                isAnswer && "border-primary bg-accent",
                wrongPick && "border-destructive bg-destructive-tint",
                reveal && !isSelected && "text-faint",
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
                className="sr-only"
              />
              <span
                aria-hidden
                className="min-w-4 font-mono text-xs text-faint"
              >
                {choice.label}
              </span>
              <span className="flex-1">{choice.text}</span>
              {mark ? (
                <span className="font-mono text-[11.5px] text-muted-foreground">
                  {mark}
                </span>
              ) : null}
            </label>
          );
        })}
      </fieldset>

      {reveal ? (
        <div
          className="mt-[26px] animate-paper-in border-t border-border pt-[22px]"
          role="status"
        >
          <div className="mb-2 flex items-baseline gap-2.5">
            <span
              className={cn(
                "font-display text-[19px]",
                reveal.isCorrect ? "text-primary" : "text-destructive",
              )}
            >
              {reveal.isCorrect ? "Correct" : "Not quite"}
            </span>
          </div>
          <p className="max-w-[640px] text-pretty text-[15.5px] leading-relaxed text-secondary-foreground">
            {reveal.explanation}
          </p>
        </div>
      ) : null}
    </div>
  );
}
