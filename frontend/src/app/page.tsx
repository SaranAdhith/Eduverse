import Link from "next/link";

import { Button } from "@/components/ui/button";
import { SplitPage } from "@/components/SplitPage";

const STEPS = [
  {
    n: "01",
    title: "A placement paper",
    body: "Twenty-five questions that set a starting estimate for every topic. Nothing is graded.",
  },
  {
    n: "02",
    title: "One topic at a time",
    body: "A short written lesson and a clipped video segment for the topic chosen for you next.",
  },
  {
    n: "03",
    title: "A check before moving on",
    body: "Five questions. You advance when the estimate is confident enough — not before.",
  },
];

// Landing — the front door. The standing left column carries the pitch; this
// column carries the two ways in and the shape of a session.
export default function LandingPage() {
  return (
    <SplitPage>
      <div className="border border-border bg-card px-[34px] pb-[30px] pt-[34px]">
        <div className="kicker">How a session runs</div>
        <div className="mb-7 mt-4 flex flex-col">
          {STEPS.map((s, i) => (
            <div
              key={s.n}
              className={`grid grid-cols-[32px_1fr] gap-4 py-4 ${
                i > 0 ? "border-t border-border-soft" : ""
              }`}
            >
              <span className="font-mono text-[13px] text-faint">{s.n}</span>
              <div>
                <div className="mb-1 font-display text-[19px] leading-tight">
                  {s.title}
                </div>
                <p className="text-[13.5px] leading-relaxed text-muted-foreground">
                  {s.body}
                </p>
              </div>
            </div>
          ))}
        </div>

        <Button asChild className="w-full">
          <Link href="/enroll">Enrol and begin</Link>
        </Button>
        <p className="mt-3.5 text-center text-xs text-faint">
          Already have a code? <Link href="/resume">Resume your session</Link>
        </p>
      </div>
    </SplitPage>
  );
}
