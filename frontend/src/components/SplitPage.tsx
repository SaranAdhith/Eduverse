import Link from "next/link";

import { Logo } from "@/components/Logo";
import { MASTERY_THRESHOLD, TIER_COUNT, TOTAL_TOPICS } from "@/lib/utils";

// The pre-session layout: a standing left column that states what Eduverse is,
// and a right column carrying whatever action the page is for.
//
// The ethics reference is a real-world institutional claim, so it is only
// rendered when the deployment supplies one.
const ETHICS_REF = process.env.NEXT_PUBLIC_ETHICS_REF;

const FACTS = [
  { value: String(TOTAL_TOPICS), label: "topics" },
  { value: String(TIER_COUNT), label: "tiers" },
  { value: MASTERY_THRESHOLD.toFixed(2), label: "mastery threshold" },
];

export function SplitPage({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[1.05fr_0.95fr]">
      <div className="flex flex-col justify-between gap-14 border-b border-border px-8 py-14 lg:border-b-0 lg:border-r lg:px-16 lg:py-[72px]">
        <Link href="/" aria-label="Eduverse home">
          <Logo />
        </Link>

        <div className="flex max-w-[520px] flex-col gap-[22px]">
          <h1 className="font-display text-[40px] leading-[1.08] tracking-[-0.015em] lg:text-[52px]">
            An adaptive path through Python.
          </h1>
          <p className="max-w-[460px] text-pretty text-[17px] text-secondary-foreground">
            Eduverse estimates how well you understand each of {TOTAL_TOPICS}{" "}
            Python topics and chooses what you work on next. Nothing is graded.
            The estimate moves with every answer, and you move on when it is
            confident enough.
          </p>
          <div className="flex gap-7 pt-1.5">
            {FACTS.map((f) => (
              <div key={f.label} className="flex flex-col gap-[3px]">
                <span className="font-mono text-[26px] leading-none">
                  {f.value}
                </span>
                <span className="text-xs tracking-[0.06em] text-muted-foreground">
                  {f.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        <p className="max-w-[460px] text-[12.5px] text-faint">
          MSc research prototype
          {ETHICS_REF ? ` · Ethics ref. ${ETHICS_REF}` : null}
        </p>
      </div>

      <div className="flex items-center px-8 py-14 lg:px-16 lg:py-[72px]">
        <div className="w-full max-w-[420px]">{children}</div>
      </div>
    </div>
  );
}
