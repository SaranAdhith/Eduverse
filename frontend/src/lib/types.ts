// Zod schemas mirroring the backend pydantic models (DOC_04/05/06). The frontend
// validates every response so a backend contract change surfaces loudly instead
// of as a silent `undefined` deep in the UI.
import { z } from "zod";

export const choiceSchema = z.object({
  label: z.enum(["A", "B", "C", "D"]),
  text: z.string(),
});
export type Choice = z.infer<typeof choiceSchema>;

// --- participants (DOC_01) ------------------------------------------------- //
export const enrollResponseSchema = z.object({
  code: z.string(),
  id: z.string().uuid(),
  // Assigned at enrollment (DOC_08 §3). The mode stays hidden from the client.
  block_order: z.string().nullable().optional(),
});
export type EnrollResponse = z.infer<typeof enrollResponseSchema>;

// --- study telemetry (DOC_08 §5) ------------------------------------------- //
export const eventAckSchema = z.object({ ok: z.boolean() });
export type EventAck = z.infer<typeof eventAckSchema>;

export const participantSchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  enrolled_at: z.string(),
  block_order: z.string().nullable().optional(),
});
export type Participant = z.infer<typeof participantSchema>;

// --- diagnostic (DOC_02/04) ------------------------------------------------ //
export const diagnosticItemSchema = z.object({
  id: z.string().uuid(),
  order: z.number(),
  topic_id: z.string(),
  difficulty: z.string(),
  stem: z.string(),
  stem_code: z.string().nullable(),
  choices: z.array(choiceSchema),
});
export type DiagnosticItem = z.infer<typeof diagnosticItemSchema>;

export const startDiagnosticSchema = z.object({
  session_id: z.string().uuid(),
  items_answered: z.number(),
  items: z.array(diagnosticItemSchema),
});
export type StartDiagnostic = z.infer<typeof startDiagnosticSchema>;

export const answerResponseSchema = z.object({
  is_correct: z.boolean(),
  explanation: z.string(),
  items_remaining: z.number(),
});
export type AnswerResponse = z.infer<typeof answerResponseSchema>;

// --- mastery (DOC_04) ------------------------------------------------------ //
export const masteryEntrySchema = z.object({
  topic_id: z.string(),
  topic_name: z.string(),
  tier: z.number(),
  p_mastered: z.number(),
  attempts: z.number(),
});
export type MasteryEntry = z.infer<typeof masteryEntrySchema>;

export const masteryVectorSchema = z.object({
  participant_code: z.string(),
  completed: z.boolean(),
  entries: z.array(masteryEntrySchema),
});
export type MasteryVector = z.infer<typeof masteryVectorSchema>;

// --- planner + gate (DOC_05) ----------------------------------------------- //
export const pathStepSchema = z.object({
  id: z.string().uuid(),
  topic_id: z.string(),
  step_index: z.number(),
  status: z.string(),
  attempts: z.number(),
  planner_reasoning: z.string().nullable(),
});
export type PathStep = z.infer<typeof pathStepSchema>;

export const pathCreateResponseSchema = z.object({
  path_id: z.string().uuid(),
  block: z.string(),
  mode: z.string(),
  current_step: pathStepSchema.nullable(),
});
export type PathCreateResponse = z.infer<typeof pathCreateResponseSchema>;

export const pathCurrentResponseSchema = z.object({
  path_id: z.string().uuid(),
  block: z.string(),
  mode: z.string(),
  completed: z.boolean(),
  completion_pct: z.number(),
  passed_count: z.number(),
  total_topics: z.number(),
  current_step: pathStepSchema.nullable(),
  steps: z.array(pathStepSchema),
});
export type PathCurrentResponse = z.infer<typeof pathCurrentResponseSchema>;

export const advanceResponseSchema = z.object({
  path_id: z.string().uuid(),
  completed: z.boolean(),
  current_step: pathStepSchema.nullable(),
});
export type AdvanceResponse = z.infer<typeof advanceResponseSchema>;

export const gateItemSchema = z.object({
  id: z.string().uuid(),
  topic_id: z.string(),
  difficulty: z.string(),
  stem: z.string(),
  stem_code: z.string().nullable(),
  choices: z.array(choiceSchema),
});
export type GateItem = z.infer<typeof gateItemSchema>;

export const gateStartSchema = z.object({
  attempt_id: z.string().uuid(),
  path_step_id: z.string().uuid(),
  topic_id: z.string(),
  items: z.array(gateItemSchema),
});
export type GateStart = z.infer<typeof gateStartSchema>;

export const gateResultSchema = z.object({
  passed: z.boolean(),
  score: z.number(),
  posterior_at_gate: z.number(),
  step: pathStepSchema,
  next_step: pathStepSchema.nullable(),
});
export type GateResult = z.infer<typeof gateResultSchema>;

// --- content (DOC_06) ------------------------------------------------------ //
export const videoDeepLinkSchema = z.object({
  video_id: z.string(),
  embed_url: z.string(),
  start_seconds: z.number(),
  end_seconds: z.number(),
  title: z.string(),
  channel_title: z.string(),
  sub_topic_label: z.string(),
});
export type VideoDeepLink = z.infer<typeof videoDeepLinkSchema>;

export const topicContextSchema = z.object({
  topic_id: z.string(),
  name: z.string(),
  description: z.string(),
  prerequisite_ids: z.array(z.string()),
});
export type TopicContext = z.infer<typeof topicContextSchema>;

export const stepContentSchema = z.object({
  chunk_id: z.string().uuid(),
  topic: topicContextSchema,
  fallback: z.boolean(),
  lesson_markdown: z.string(),
  video: videoDeepLinkSchema.nullable(),
});
export type StepContent = z.infer<typeof stepContentSchema>;

// --- request bodies -------------------------------------------------------- //
export interface AnswerRequest {
  session_id: string;
  question_id: string;
  selected_label: "A" | "B" | "C" | "D";
  response_ms: number | null;
}

export interface GateAnswerIn {
  question_id: string;
  selected_label: "A" | "B" | "C" | "D";
  response_ms: number | null;
}
