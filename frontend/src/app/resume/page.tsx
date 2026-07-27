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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/Logo";
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
    <main className="bg-aurora flex min-h-screen flex-col items-center justify-center px-6 py-10">
      <Link
        href="/"
        className="mb-8 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Logo size={34} />
      </Link>
      <Card className="animate-fade-in-up w-full max-w-md">
        <form onSubmit={onSubmit}>
          <CardHeader>
            <CardTitle className="text-2xl">Welcome back</CardTitle>
            <CardDescription>
              Enter the code you were given when you enrolled.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Label htmlFor="code">Participant code</Label>
            <Input
              id="code"
              value={code}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g. AB12CD"
              autoComplete="off"
              autoFocus
            />
            {resume.isError ? (
              <p className="text-sm text-destructive" role="alert">
                We couldn&apos;t find that code. Please check and try again.
              </p>
            ) : null}
          </CardContent>
          <CardFooter className="flex items-center justify-between">
            <Button asChild variant="ghost" type="button">
              <Link href="/">Back</Link>
            </Button>
            <Button
              type="submit"
              variant="brand"
              disabled={!code.trim() || resume.isPending}
            >
              {resume.isPending ? "Checking…" : "Resume"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </main>
  );
}
