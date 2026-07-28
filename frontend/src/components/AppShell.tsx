"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Logo } from "@/components/Logo";
import { useCurrentPath, useMastery } from "@/lib/queries";
import { useParticipant } from "@/lib/store";
import { cn, MASTERY_THRESHOLD, TOTAL_TOPICS } from "@/lib/utils";

// The persistent 246px sidebar: brand, the three destinations, curriculum
// progress, and the participant's identity pinned to the bottom. The study
// condition is deliberately absent — the learner must never be able to tell
// which arm they are in.
const NAV = [
  { href: "/dashboard", label: "Session" },
  { href: "/curriculum", label: "Curriculum" },
  { href: "/profile", label: "Profile" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const code = useParticipant((s) => s.code);
  const mastery = useMastery(Boolean(code));
  const path = useCurrentPath();

  const entries = mastery.data?.entries ?? [];
  const mastered = entries.filter(
    (e) => e.p_mastered >= MASTERY_THRESHOLD,
  ).length;
  const attempted = entries.reduce((n, e) => n + e.attempts, 0);
  const current = path.data?.current_step ?? null;
  const currentTier = current
    ? entries.find((e) => e.topic_id === current.topic_id)?.tier
    : undefined;

  const meta: Record<string, string> = {
    "/dashboard": currentTier !== undefined ? `tier ${currentTier}` : "—",
    "/curriculum": `${mastered}/${TOTAL_TOPICS}`,
    "/profile": `${attempted} items`,
  };

  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[246px_1fr]">
      <aside className="sticky top-0 flex h-auto flex-col justify-between border-b border-border py-6 lg:h-screen lg:border-b-0 lg:border-r">
        <div className="flex flex-col gap-8">
          <div className="px-6">
            <Logo />
          </div>

          <nav className="flex flex-row overflow-x-auto lg:flex-col lg:overflow-visible">
            {NAV.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex w-full items-baseline justify-between gap-2 border-l-2 px-6 py-2.5 text-[15px] transition-colors",
                    active
                      ? "border-primary bg-secondary font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span>{item.label}</span>
                  <span className="font-mono text-[11px] text-faint">
                    {meta[item.href]}
                  </span>
                </Link>
              );
            })}
          </nav>

          <div className="hidden flex-col gap-3 px-6 lg:flex">
            <div className="kicker kicker-sm">Curriculum progress</div>
            <div className="h-1.5 w-full bg-track">
              <div
                className="h-full bg-primary transition-[width] duration-500"
                style={{ width: `${(mastered / TOTAL_TOPICS) * 100}%` }}
              />
            </div>
            <div className="font-mono text-xs text-muted-foreground">
              {mastered} of {TOTAL_TOPICS} mastered
            </div>
          </div>
        </div>

        <div className="hidden flex-col gap-2.5 px-6 lg:flex">
          <div className="flex flex-col gap-1 border-t border-border pt-4">
            <div className="text-[11px] uppercase tracking-[0.14em] text-faint">
              Participant
            </div>
            <div className="font-mono text-base tracking-[0.08em]">
              {code ?? "—"}
            </div>
            {path.data ? (
              <div className="text-[12.5px] text-muted-foreground">
                Block {path.data.block} · {path.data.passed_count}/
                {path.data.total_topics} passed
              </div>
            ) : null}
          </div>
          <p className="text-[11.5px] leading-relaxed text-faint">
            Session recorded for research.{" "}
            <Link href="/profile#consent">Study information</Link>
          </p>
        </div>
      </aside>

      <main className="min-w-0">{children}</main>
    </div>
  );
}
