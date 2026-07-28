// TanStack Query hooks over apiFetch (DOC_07 §5). Stale times per the spec:
// mastery 30s, path/step 5s, chunk infinity (content is addressed by
// content_version, so a served chunk never changes).
"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "./api";
import { useParticipant } from "./store";
import {
  advanceResponseSchema,
  answerResponseSchema,
  enrollResponseSchema,
  eventAckSchema,
  gateResultSchema,
  gateStartSchema,
  masteryVectorSchema,
  participantSchema,
  pathCreateResponseSchema,
  pathCurrentResponseSchema,
  startDiagnosticSchema,
  stepContentSchema,
  type AnswerRequest,
  type GateAnswerIn,
  type MasteryVector,
  type PathCurrentResponse,
  type StepContent,
} from "./types";

const DEFAULT_BLOCK = process.env.NEXT_PUBLIC_DEFAULT_BLOCK ?? "A";

export const queryKeys = {
  mastery: ["mastery"] as const,
  currentPath: (block: string) => ["path", block] as const,
  chunk: (stepId: string) => ["chunk", stepId] as const,
};

// --- identity -------------------------------------------------------------- //
export function useEnroll() {
  return useMutation({
    mutationFn: (consent_given: boolean) =>
      apiFetch("/enroll", enrollResponseSchema, {
        method: "POST",
        body: { consent_given },
        auth: false,
      }),
  });
}

export function useResume() {
  return useMutation({
    mutationFn: (code: string) =>
      apiFetch("/resume", participantSchema, {
        method: "POST",
        body: { code },
        auth: false,
      }),
  });
}

// --- diagnostic ------------------------------------------------------------ //
export function useStartDiagnostic() {
  return useMutation({
    mutationFn: () =>
      apiFetch("/diagnostic/start", startDiagnosticSchema, { method: "POST" }),
  });
}

export function useAnswerDiagnostic() {
  return useMutation({
    mutationFn: (body: AnswerRequest) =>
      apiFetch("/diagnostic/answer", answerResponseSchema, {
        method: "POST",
        body,
      }),
  });
}

export function useCompleteDiagnostic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch("/diagnostic/complete", masteryVectorSchema, { method: "POST" }),
    onSuccess: (data) => qc.setQueryData(queryKeys.mastery, data),
  });
}

// --- mastery --------------------------------------------------------------- //
export function useMastery(enabled = true) {
  return useQuery<MasteryVector>({
    queryKey: queryKeys.mastery,
    queryFn: () => apiFetch("/mastery", masteryVectorSchema),
    staleTime: 30_000,
    enabled,
  });
}

// --- path ------------------------------------------------------------------ //
/** Current path for the block, or null if none exists yet (404). */
export function useCurrentPath(block: string = DEFAULT_BLOCK) {
  // Hold the request until the code has hydrated out of localStorage —
  // firing early sends an unauthenticated GET, and apiFetch treats the
  // resulting 401 as a lost session and bounces to /resume.
  const code = useParticipant((s) => s.code);
  return useQuery<PathCurrentResponse | null>({
    queryKey: queryKeys.currentPath(block),
    queryFn: async () => {
      try {
        return await apiFetch(
          `/paths/current?block=${block}`,
          pathCurrentResponseSchema,
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    staleTime: 5_000,
    enabled: Boolean(code),
  });
}

export function useCreatePath() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (opts?: { block?: string }) =>
      apiFetch("/paths", pathCreateResponseSchema, {
        method: "POST",
        // Mode is a study condition assigned server-side at enrollment (DOC_08
        // §3). The client sends only the block and never a mode, so the UI can
        // neither reveal nor influence the participant's condition (§8.3).
        body: { block: opts?.block ?? DEFAULT_BLOCK },
      }),
    onSuccess: (data) =>
      qc.invalidateQueries({ queryKey: queryKeys.currentPath(data.block) }),
  });
}

export function useAdvancePath() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pathId: string) =>
      apiFetch(`/paths/${pathId}/advance`, advanceResponseSchema, {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.currentPath(DEFAULT_BLOCK) });
      qc.invalidateQueries({ queryKey: queryKeys.mastery });
    },
  });
}

// --- content chunk --------------------------------------------------------- //
export function useChunk(stepId: string) {
  return useQuery<StepContent>({
    queryKey: queryKeys.chunk(stepId),
    queryFn: () => apiFetch(`/steps/${stepId}/content`, stepContentSchema),
    staleTime: Infinity,
    // 404 means pre-generation hasn't finished (DOC_06 §9); poll patiently.
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) {
        return failureCount < 40;
      }
      return failureCount < 2;
    },
    retryDelay: 1500,
  });
}

// --- gate ------------------------------------------------------------------ //
export function useStartGate() {
  return useMutation({
    mutationFn: (stepId: string) =>
      apiFetch(`/steps/${stepId}/gate/start`, gateStartSchema, {
        method: "POST",
      }),
  });
}

export function useSubmitGate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      stepId,
      answers,
    }: {
      stepId: string;
      answers: GateAnswerIn[];
    }) =>
      apiFetch(`/steps/${stepId}/gate/submit`, gateResultSchema, {
        method: "POST",
        body: { answers },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.currentPath(DEFAULT_BLOCK) });
      qc.invalidateQueries({ queryKey: queryKeys.mastery });
    },
  });
}

// --- study telemetry (DOC_08 §5) ------------------------------------------- //
// Events the backend can't observe itself: lesson viewing time and idle gaps.
// Tagged source='client' server-side so analysts can tell them apart.
export function useLogChunkView() {
  return useMutation({
    mutationFn: (body: {
      step_id: string;
      video_seconds_watched?: number;
      phase?: "load" | "unload" | "video_end";
    }) =>
      apiFetch("/events/chunk_view", eventAckSchema, { method: "POST", body }),
  });
}

export function useLogIdle() {
  return useMutation({
    mutationFn: (body: { step_id?: string; idle_seconds?: number }) =>
      apiFetch("/events/idle", eventAckSchema, { method: "POST", body }),
  });
}
