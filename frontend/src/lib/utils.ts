import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// DOC_07 §4: never show the raw p_mastered in a gate result — bucket it so
// participants can't reverse-engineer and game the 0.85 threshold. The exact
// number is fine on the dashboard overview.
export const MASTERY_THRESHOLD = 0.85;

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

export function tierLabel(tier: number): string {
  return `Tier ${tier}`;
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
