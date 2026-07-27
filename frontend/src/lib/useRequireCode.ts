"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useParticipant } from "./store";

// Guard for participant-only pages: once hydration has run, bounce to the
// landing page if there is no stored code.
export function useRequireCode(): { ready: boolean; code: string | null } {
  const router = useRouter();
  const code = useParticipant((s) => s.code);
  const hydrated = useParticipant((s) => s.hydrated);

  useEffect(() => {
    if (hydrated && !code) {
      router.replace("/");
    }
  }, [hydrated, code, router]);

  return { ready: hydrated && !!code, code };
}
