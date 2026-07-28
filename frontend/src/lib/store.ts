// Zustand store for the ephemeral client state we persist: the participant code
// (DOC_07 §2, §5) and a local progress journal. Server state never lives here —
// that's TanStack Query's job.
"use client";

import { create } from "zustand";

const STORAGE_KEY = "eduverse.participant_code";
const JOURNAL_KEY = "eduverse.journal";

function readStorage(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

interface ParticipantState {
  code: string | null;
  hydrated: boolean;
  setCode: (code: string) => void;
  clear: () => void;
  hydrate: () => void;
}

export const useParticipant = create<ParticipantState>((set) => ({
  // Start null on both server and client render; `hydrate()` fills it in a
  // client effect to avoid hydration mismatches.
  code: null,
  hydrated: false,
  setCode: (code) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, code);
    }
    set({ code, hydrated: true });
  },
  clear: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY);
      window.localStorage.removeItem(JOURNAL_KEY);
    }
    set({ code: null, hydrated: true });
  },
  hydrate: () => set({ code: readStorage(), hydrated: true }),
}));

// Non-hook accessor for the api layer (runs at fetch time, outside React).
export function getParticipantCode(): string | null {
  return useParticipant.getState().code ?? readStorage();
}

export function clearParticipantCode(): void {
  useParticipant.getState().clear();
}

// --- local progress journal ------------------------------------------------ //
// The backend keeps a per-response BKT prior/posterior snapshot, but exposes no
// participant-facing trajectory endpoint (`GET /mastery` is the current vector
// only). So the Profile view journals the real values this browser observed, in
// two separate series — neither is interpolated or synthesised:
//
//   checkpoints  — a mean mastery reading taken at each moment the server hands
//                  us a fresh vector (diagnostic complete, every gate submit).
//                  This is what the learning curve plots.
//   per-item     — correct/attempted tallies per topic, counted as each item is
//                  answered. This is what the "Correct" column reports.
//
// It is a local convenience view, never a substitute for `POST /admin/export` —
// analysis still reads the server's durable record.
export interface JournalEntry {
  /** 1-based index of the checkpoint. */
  n: number;
  /** Mean mastery across attempted topics, as reported by the server. */
  mean: number;
  /** Whether the event that produced this checkpoint went well. */
  correct: boolean;
  topicId: string;
  at: number;
}

interface Journal {
  code: string | null;
  /** Mastery checkpoints — the learning curve. */
  entries: JournalEntry[];
  /** topic_id -> correct answers counted in this browser. */
  correctByTopic: Record<string, number>;
  /** topic_id -> items answered in this browser. */
  itemsByTopic: Record<string, number>;
  startedAt: number | null;
}

const EMPTY: Journal = {
  code: null,
  entries: [],
  correctByTopic: {},
  itemsByTopic: {},
  startedAt: null,
};

function readJournal(): Journal {
  if (typeof window === "undefined") return EMPTY;
  try {
    const raw = window.localStorage.getItem(JOURNAL_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Journal;
    // A journal from a different participant is not ours to show.
    if (parsed.code && parsed.code !== readStorage()) return EMPTY;
    return { ...EMPTY, ...parsed };
  } catch {
    return EMPTY;
  }
}

function writeJournal(j: Journal): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(JOURNAL_KEY, JSON.stringify(j));
  } catch {
    /* ignore private-mode storage errors */
  }
}

interface JournalState extends Journal {
  hydrated: boolean;
  hydrate: () => void;
  /** Count one answered item. */
  recordItem: (e: { correct: boolean; topicId: string }) => void;
  /** Record a mastery reading the server just gave us. */
  recordCheckpoint: (e: {
    mean: number;
    correct: boolean;
    topicId: string;
  }) => void;
}

// A page may record before anything has called `hydrate()` (the gate, for
// instance, is reachable without the Profile ever being opened). Writing from
// the empty initial state would clobber the stored journal, so read it back
// first if we haven't yet.
function current(
  get: () => JournalState,
  set: (p: Partial<JournalState>) => void,
): JournalState {
  const s = get();
  if (s.hydrated) return s;
  const loaded = { ...readJournal(), hydrated: true };
  set(loaded);
  return { ...s, ...loaded };
}

function persist(s: Journal, patch: Partial<Journal>): Journal {
  const next: Journal = {
    ...s,
    ...patch,
    code: getParticipantCode(),
    startedAt: s.startedAt ?? Date.now(),
  };
  writeJournal(next);
  return next;
}

export const useJournal = create<JournalState>((set, get) => ({
  ...EMPTY,
  hydrated: false,
  hydrate: () => set({ ...readJournal(), hydrated: true }),
  recordItem: ({ correct, topicId }) => {
    const s = current(get, set);
    const correctByTopic = { ...s.correctByTopic };
    const itemsByTopic = { ...s.itemsByTopic };
    itemsByTopic[topicId] = (itemsByTopic[topicId] ?? 0) + 1;
    if (correct) {
      correctByTopic[topicId] = (correctByTopic[topicId] ?? 0) + 1;
    }
    set(persist(s, { correctByTopic, itemsByTopic }));
  },
  recordCheckpoint: ({ mean, correct, topicId }) => {
    const s = current(get, set);
    const entries = [
      ...s.entries,
      { n: s.entries.length + 1, mean, correct, topicId, at: Date.now() },
    ];
    set(persist(s, { entries }));
  },
}));

/** Mean mastery across topics the participant has actually attempted. */
export function meanAttemptedMastery(
  entries: { p_mastered: number; attempts: number }[],
): number {
  const seen = entries.filter((e) => e.attempts > 0);
  const pool = seen.length > 0 ? seen : entries;
  if (pool.length === 0) return 0;
  return pool.reduce((a, e) => a + e.p_mastered, 0) / pool.length;
}
