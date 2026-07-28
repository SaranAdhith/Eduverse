"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { SplitPage } from "@/components/SplitPage";
import { useEnroll } from "@/lib/queries";
import { useParticipant } from "@/lib/store";

export default function EnrollPage() {
  const router = useRouter();
  const enroll = useEnroll();
  const setCode = useParticipant((s) => s.setCode);
  const [consent, setConsent] = useState(false);
  const [issued, setIssued] = useState<string | null>(null);

  const onSubmit = async () => {
    const result = await enroll.mutateAsync(true);
    setCode(result.code);
    // The code is the only way back in, so it gets a screen of its own before
    // the placement paper starts.
    setIssued(result.code);
  };

  return (
    <SplitPage>
      {issued ? (
        <div className="animate-paper-in border border-border bg-card px-[34px] pb-[30px] pt-[34px]">
          <div className="kicker">Enrolled</div>
          <h2 className="mb-2 mt-3 font-display text-[25px]">
            This is your participant code
          </h2>
          <p className="mb-[22px] text-sm text-muted-foreground">
            Write it down. It is the only way to return to your session — there
            is no account and no password to recover.
          </p>
          <div className="border border-input bg-secondary px-3.5 py-4 text-center font-mono text-[28px] tracking-[0.2em]">
            {issued}
          </div>
          <Button
            className="mt-6 w-full"
            onClick={() => router.push("/diagnostic")}
          >
            Begin placement paper
          </Button>
          <p className="mt-3.5 text-center text-xs text-faint">
            Takes about 15 minutes.
          </p>
        </div>
      ) : (
        <div className="border border-border bg-card px-[34px] pb-[30px] pt-[34px]">
          <div className="kicker">Enrolment</div>
          <h2 className="mb-2 mt-3 font-display text-[25px]">
            Consent to take part
          </h2>
          <p className="mb-[22px] text-sm text-muted-foreground">
            No account, no email address. A code is issued to you and it is the
            only identifier stored with your responses.
          </p>

          {/* The consent *structure* is settled; the exact IRB-approved wording
              is substituted at deployment — ethics paperwork is institutional
              and out of scope for this codebase (DOC_08 §11). */}
          <div className="note-panel mb-6 flex flex-col gap-2.5 p-4 text-[13px] leading-relaxed text-secondary-foreground">
            <p>
              You will complete a short placement paper, then work through two
              blocks of topics. The order of the blocks and the way each is
              taught are set by the study and are not shown to you.
            </p>
            <p>
              Your answers, response times and topic sequence are recorded for
              research purposes.
            </p>
            <p>
              Taking part is voluntary. You may stop at any point, and withdrawn
              data is deleted within 30 days.
            </p>
          </div>

          <label className="mb-6 flex cursor-pointer items-start gap-3 text-[13px] leading-relaxed">
            <Checkbox
              id="consent"
              className="mt-0.5"
              checked={consent}
              onCheckedChange={(v) => setConsent(v === true)}
            />
            <span>I have read the above and consent to take part.</span>
          </label>

          {enroll.isError ? (
            <p className="mb-4 text-[13px] text-destructive" role="alert">
              Something went wrong creating your code. Please try again.
            </p>
          ) : null}

          <Button
            className="w-full"
            onClick={onSubmit}
            disabled={!consent || enroll.isPending}
          >
            {enroll.isPending ? "Enrolling…" : "Consent and begin placement"}
          </Button>
          <p className="mt-3.5 text-center text-xs text-faint">
            Already have a code? <Link href="/resume">Resume your session</Link>
          </p>
        </div>
      )}
    </SplitPage>
  );
}
