import Link from "next/link";
import { ArrowRight, Compass, GraduationCap, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Logo";

const FEATURES = [
  {
    icon: Compass,
    title: "Finds where you are",
    body: "A short placement quiz maps your Python knowledge across every tier — no starting from zero if you don't need to.",
  },
  {
    icon: Sparkles,
    title: "Teaches one thing at a time",
    body: "An adaptive planner picks your next best topic and pairs it with a short video and a focused, written lesson.",
  },
  {
    icon: GraduationCap,
    title: "Checks before you move on",
    body: "A quick mastery gate confirms the idea really landed — you only advance once it has.",
  },
];

// Landing — the front door. Hero with the brand, one clear value line, two CTAs,
// and three feature cards explaining the loop.
export default function LandingPage() {
  return (
    <div className="bg-aurora min-h-screen">
      <header className="container flex items-center justify-between py-6">
        <Logo size={34} />
        <Button asChild variant="ghost" size="sm">
          <Link href="/resume">I have a code</Link>
        </Button>
      </header>

      <main className="container flex flex-col items-center pb-24 pt-10 text-center sm:pt-20">
        <span className="animate-fade-in-up mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-card/70 px-4 py-1.5 text-sm text-muted-foreground shadow-soft backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          Adaptive Python tutoring, one topic at a time
        </span>

        <h1 className="animate-fade-in-up mx-auto max-w-3xl text-balance text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
          Learn Python in your own{" "}
          <span className="text-gradient">learning universe</span>
        </h1>

        <p className="animate-fade-in-up mx-auto mt-6 max-w-xl text-balance text-lg leading-relaxed text-muted-foreground">
          Eduverse is a patient tutor that finds exactly where you are, then
          teaches one well-chosen topic at a time — video, lesson, and a quick
          check before you move on.
        </p>

        <div className="animate-fade-in-up mt-9 flex w-full flex-col items-center gap-3 sm:w-auto sm:flex-row">
          <Button asChild size="xl" variant="brand" className="w-full sm:w-auto">
            <Link href="/enroll">
              Start learning
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild size="xl" variant="outline" className="w-full sm:w-auto">
            <Link href="/resume">Resume with my code</Link>
          </Button>
        </div>

        <div className="mt-20 grid w-full max-w-4xl gap-4 sm:grid-cols-3">
          {FEATURES.map((f, i) => (
            <div
              key={f.title}
              className="animate-fade-in-up hover-lift rounded-xl border border-border bg-card/80 p-6 text-left shadow-card backdrop-blur"
              style={{ animationDelay: `${120 + i * 90}ms` }}
            >
              <span className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <f.icon className="h-5 w-5" />
              </span>
              <h3 className="text-base font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                {f.body}
              </p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
