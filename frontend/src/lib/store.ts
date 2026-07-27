// Zustand store for the ONE piece of ephemeral client state we persist: the
// participant code (DOC_07 §2, §5). Server state never lives here — that's
// TanStack Query's job.
"use client";

import { create } from "zustand";

const STORAGE_KEY = "eduverse.participant_code";

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
