"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Moon, Sun } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Logo";
import { useParticipant } from "@/lib/store";

// Visible state at all times — the participant's code, current block, and topics
// passed are always on screen. No hidden modes.
interface ParticipantHeaderProps {
  block?: string;
  passedCount?: number;
  totalTopics?: number;
}

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("eduverse.theme", next ? "dark" : "light");
    } catch {
      /* ignore private-mode storage errors */
    }
    setDark(next);
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

export function ParticipantHeader({
  block,
  passedCount,
  totalTopics,
}: ParticipantHeaderProps) {
  const code = useParticipant((s) => s.code);

  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-background/70 backdrop-blur-md">
      <div className="container flex h-16 items-center justify-between gap-4">
        <Link href="/dashboard" className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Logo size={30} />
        </Link>
        <div className="flex items-center gap-2 sm:gap-3">
          {block ? <Badge variant="secondary">Block {block}</Badge> : null}
          {typeof passedCount === "number" && typeof totalTopics === "number" ? (
            <Badge variant="muted" className="hidden sm:inline-flex">
              {passedCount}/{totalTopics} passed
            </Badge>
          ) : null}
          {code ? (
            <span className="rounded-md border border-border bg-muted/60 px-2.5 py-1 font-mono text-xs font-medium text-muted-foreground">
              {code}
            </span>
          ) : null}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
