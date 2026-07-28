import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// DOC_07 §4: never show the raw p_mastered in a gate result — bucket it so
// participants can't reverse-engineer and game the 0.85 threshold. The exact
// number is fine on the dashboard overview.
export const MASTERY_THRESHOLD = 0.85;

/** 47 topics is canonical — see README "Research notes". */
export const TOTAL_TOPICS = 47;

export type MasteryBucket =
  | "Not yet"
  | "Getting there"
  | "Almost"
  | "Solid"
  | "Mastered";

export function masteryBucket(p: number): MasteryBucket {
  if (p >= MASTERY_THRESHOLD) return "Mastered";
  if (p >= 0.7) return "Solid";
  if (p >= 0.5) return "Almost";
  if (p >= 0.3) return "Getting there";
  return "Not yet";
}

// The nine tiers of data/curriculum.yaml, keyed by the integer the API returns.
export const TIER_NAMES: Record<number, string> = {
  0: "Foundations",
  1: "Control flow",
  2: "Core data structures",
  3: "Functions",
  4: "Modules & error handling",
  5: "Object-oriented programming",
  6: "Advanced language features",
  7: "Concurrency & async",
  8: "Tooling",
};

export const TIER_COUNT = Object.keys(TIER_NAMES).length;

export function tierName(tier: number): string {
  return TIER_NAMES[tier] ?? `Tier ${tier}`;
}

export function tierLabel(tier: number): string {
  return `Tier ${tier}`;
}

// Topic ids are `T<tier>.<n>` throughout data/curriculum.yaml. Endpoints that
// return a topic without its tier (e.g. the content chunk) can recover it here.
export function tierFromTopicId(topicId: string): number | null {
  const m = /^T(\d+)\./.exec(topicId);
  return m ? Number(m[1]) : null;
}

/** Estimates always read as two decimals, in mono. */
export function formatP(p: number): string {
  return p.toFixed(2);
}

// group mastery entries by tier -> average p_mastered
export function tierAverages(
  entries: { tier: number; p_mastered: number }[],
): { tier: number; average: number }[] {
  const byTier = new Map<number, number[]>();
  for (const e of entries) {
    const arr = byTier.get(e.tier) ?? [];
    arr.push(e.p_mastered);
    byTier.set(e.tier, arr);
  }
  return [...byTier.entries()]
    .map(([tier, ps]) => ({
      tier,
      average: ps.reduce((a, b) => a + b, 0) / ps.length,
    }))
    .sort((a, b) => a.tier - b.tier);
}

/** "12m 04s" — the session clock shown in the Session and Profile headers. */
export function elapsedText(since: number | null): string {
  if (!since) return "0m";
  const secs = Math.max(0, Math.floor((Date.now() - since) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}
