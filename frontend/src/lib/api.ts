// Typed fetch wrapper (DOC_07 §5). Adds the X-Participant-Code header, throws
// typed ApiError, and on 401 clears the stored code and bounces to /resume.
import { z } from "zod";

import { clearParticipantCode, getParticipantCode } from "./store";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public payload: unknown,
  ) {
    super(
      typeof payload === "object" && payload && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `Request failed with status ${status}`,
    );
    this.name = "ApiError";
  }
}

interface FetchOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  // When false, an absent participant code does not abort the request (used by
  // enroll/resume, the only unauthenticated endpoints).
  auth?: boolean;
  signal?: AbortSignal;
}

async function rawFetch(path: string, opts: FetchOptions): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const code = getParticipantCode();
  if (code) headers["X-Participant-Code"] = code;

  return fetch(`${API_URL}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
}

function handleUnauthorized() {
  clearParticipantCode();
  if (typeof window !== "undefined" && window.location.pathname !== "/resume") {
    window.location.assign("/resume");
  }
}

/**
 * Fetch + validate. Pass a zod schema to parse (and type) the response.
 */
export async function apiFetch<T>(
  path: string,
  schema: z.ZodType<T>,
  opts: FetchOptions = {},
): Promise<T> {
  const res = await rawFetch(path, opts);

  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError(401, await safeJson(res));
  }
  if (!res.ok) {
    throw new ApiError(res.status, await safeJson(res));
  }
  const data = await safeJson(res);
  return schema.parse(data);
}

async function safeJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
