"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SplitPage } from "@/components/SplitPage";
import { useResume } from "@/lib/queries";
import { useParticipant } from "@/lib/store";

export default function ResumePage() {
  const router = useRouter();
  const resume = useResume();
  const setCode = useParticipant((s) => s.setCode);
  const [code, setInput] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim();
    if (!trimmed) return;
    const participant = await resume.mutateAsync(trimmed);
    setCode(participant.code);
    router.push("/dashboard");
  };

  return (
    <SplitPage>
      <form
        onSubmit={onSubmit}
        className="border border-border bg-card px-[34px] pb-[30px] pt-[34px]"
      >
        <div className="kicker">Return</div>
        <h2 className="mb-2 mt-3 font-display text-[25px]">
          Enter your participant code
        </h2>
        <p className="mb-[22px] text-sm text-muted-foreground">
          No account, no email address. Your code is the only identifier stored
          with your responses.
        </p>

        <Label htmlFor="code" className="mb-[7px] block">
          Participant code
        </Label>
        <Input
          id="code"
          value={code}
          onChange={(e) => setInput(e.target.value)}
          placeholder="P001"
          autoComplete="off"
          autoFocus
          className="h-auto py-3 font-mono text-xl tracking-[0.1em]"
        />

        {resume.isError ? (
          <p className="mt-4 text-[13px] text-destructive" role="alert">
            We couldn&apos;t find that code. Please check and try again.
          </p>
        ) : null}

        <Button
          type="submit"
          className="mt-6 w-full"
          disabled={!code.trim() || resume.isPending}
        >
          {resume.isPending ? "Checking…" : "Resume session"}
        </Button>
        <p className="mt-3.5 text-center text-xs text-faint">
          New here? <Link href="/enroll">Enrol instead</Link>
        </p>
      </form>
    </SplitPage>
  );
}
