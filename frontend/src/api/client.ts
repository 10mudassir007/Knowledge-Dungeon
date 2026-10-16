/**
 * Typed fetch wrapper. Every non-2xx becomes an ApiError carrying a readable
 * message — raw JSON and stack traces never reach the UI.
 */

import {
  ApiError,
  type AnswerCheckResponse,
  type HealthResponse,
  type HintResponse,
  type RevealResponse,
  type QuestionResponse,
  type StartGameRequest,
  type StartGameResponse,
  type StateResponse,
} from "./types";

/** VITE_API_URL, else the dev proxy. The proxy strips the /api prefix. */
/**
 * API base URL.
 *
 * In dev, Vite proxies `/api/*` to the backend on :8000 with the prefix
 * stripped. In a production build the app is served BY the backend (`python
 * main.py`), so the API is same-origin at the root and `/api` would 405.
 */
export const BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined)?.trim() ||
  (import.meta.env.DEV ? "/api" : "");

export function messageForStatus(status: number, detail?: string): string {
  switch (status) {
    case 400:
      return detail?.trim() || "This run is already finished.";
    case 404:
      return "Your session expired. Start a new run.";
    case 409:
      return "No active question.";
    case 422:
      return "That answer is not valid. Keep it under 500 characters.";
    case 502:
      return "The dungeon could not produce a question just now. Try again.";
    case 503:
      return "The game AI is unavailable right now. Please try again.";
    case 0:
      return "Cannot reach the dungeon server. Check your connection.";
    default:
      return "Something went wrong inside the dungeon.";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      ...init,
    });
  } catch {
    throw new ApiError(0, messageForStatus(0));
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body: fall through to the status-based message.
    }
    throw new ApiError(response.status, messageForStatus(response.status, detail));
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, "The dungeon sent something unreadable.");
  }
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  startGame: (body: StartGameRequest) =>
    request<StartGameResponse>("/game/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  state: (sid: string) => request<StateResponse>(`/game/${sid}`),

  question: (sid: string) => request<QuestionResponse>(`/game/${sid}/question`),

  // The backend ignores this body; we still send an empty object for clarity.
  hint: (sid: string) => request<HintResponse>(`/game/${sid}/hint`, { method: "POST", body: "{}" }),
  /** Super power: rips the answer out of the orc's head. Costs health, frontend-side. */
  reveal: (sid: string) => request<RevealResponse>(`/game/${sid}/reveal`, { method: "POST", body: "{}" }),

  answer: (sid: string, answer: string) =>
    request<AnswerCheckResponse>(`/game/${sid}/answer-check`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
};