"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/Logo";
import { useEnroll } from "@/lib/queries";
import { useParticipant } from "@/lib/store";

export default function EnrollPage() {
  const router = useRouter();
  const enroll = useEnroll();
  const setCode = useParticipant((s) => s.setCode);
  const [consent, setConsent] = useState(false);

  const onSubmit = async () => {
    const result = await enroll.mutateAsync(true);
    setCode(result.code);
    router.push("/diagnostic");
  };

  return (
    <main className="bg-aurora flex min-h-screen flex-col items-center px-6 py-10">
      <Link
        href="/"
        className="mb-8 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Logo size={34} />
      </Link>
      <Card className="animate-fade-in-up w-full max-w-2xl">
        <CardHeader>
          <CardTitle className="text-2xl">Consent to take part</CardTitle>
          <CardDescription>
            Please read the study information before you begin.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* The consent *structure* is settled; the exact IRB-approved wording
              is substituted at deployment — ethics paperwork is institutional
              and out of scope for this codebase (DOC_08 §11). The data-use text
              below reflects the DOC_08 instrumentation that is now live. */}
          <div className="space-y-3 rounded-md border bg-muted/30 p-4 text-sm leading-relaxed text-muted-foreground">
            <p>
              <strong className="text-foreground">What this is.</strong> You are
              invited to take part in a study of an adaptive learning agent for
              Python. You will complete a short placement quiz, then work through
              two blocks of learning topics. The order of the blocks and the way
              each is taught are set by the study and are not shown to you.
            </p>
            <p>
              <strong className="text-foreground">Voluntariness.</strong> Taking
              part is entirely voluntary. You may stop at any time without giving
              a reason and without any consequence.
            </p>
            <p>
              <strong className="text-foreground">Data use.</strong> Your quiz
              answers, learning progress, and interactions with the lessons
              (including timing) are recorded as timestamped events under an
              anonymous code and used only for research. No personal identifying
              information is collected.
            </p>
            <p>
              <strong className="text-foreground">Contact.</strong> For questions
              about the study, contact the research team (details to be provided).
            </p>
          </div>

          <div className="flex items-start gap-3">
            <Checkbox
              id="consent"
              checked={consent}
              onCheckedChange={(v) => setConsent(v === true)}
            />
            <Label htmlFor="consent" className="leading-relaxed">
              I have read the above and consent to take part.
            </Label>
          </div>

          {enroll.isError ? (
            <p className="text-sm text-destructive" role="alert">
              Something went wrong creating your code. Please try again.
            </p>
          ) : null}
        </CardContent>
        <CardFooter className="flex items-center justify-between">
          <Button asChild variant="ghost">
            <Link href="/">Back</Link>
          </Button>
          <Button
            variant="brand"
            onClick={onSubmit}
            disabled={!consent || enroll.isPending}
          >
            {enroll.isPending ? "Generating…" : "Generate my code"}
          </Button>
        </CardFooter>
      </Card>
    </main>
  );
}
