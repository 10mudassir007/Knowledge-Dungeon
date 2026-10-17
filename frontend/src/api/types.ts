/**
 * Types mirroring frontend/API_CONTRACT.md.
 * Nothing here may be invented — it is all read off the backend.
 */

/** POST /game/start */
export interface StartGameRequest {
  age: number;
  interest: string;
}

export interface StartGameResponse {
  session_id: string;
  age: number;
  interest: string;
  lives: number;
  points: number;
  level: number;
  /** In-world narration. The backend does return this. */
  environment: string;
}

/** GET /game/{sid} */
export interface StateResponse {
  lives: number;
  points: number;
  level: number;
  game_over: boolean;
}

/** GET /game/{sid}/question — the answer is never returned. */
export interface QuestionResponse {
  question: string;
}

/** POST /game/{sid}/hint — request body is ignored by the server. */
export interface RevealResponse {
  answer: string;
}

export interface HintResponse {
  hint: string;
}

/** POST /game/{sid}/answer-check — { answer } only, max 500 chars. */
export interface AnswerCheckRequest {
  answer: string;
}

export interface AnswerCheckResponse {
  verdict: "Correct" | "Incorrect";
  correct: boolean;
  lives: number;
  points: number;
  level: number;
  game_over: boolean;
}

/** GET /health — key values are never exposed. */
export interface HealthResponse {
  status: string;
  provider: string;
  search_available: boolean;
  active_sessions: number;
}

/**
 * Backend rules, mirrored from core/rules.py for HUD purposes only.
 *
 * MAX_SCORE is the score band (3 levels x 30 points) the HUD bar fills
 * against - not a win condition: a run is won by reaching the altar, and
 * points keep accumulating past it while the lives last.
 */
export const MAX_SCORE = 90;
export const MAX_LEVEL = 3;
export const MAX_LIVES = 3;
export const MAX_ANSWER_LENGTH = 500;

/** A friendlier error carrying the status code the UI can branch on. */
export class ApiError extends Error {
  readonly status: number;
  /** True when retrying might plausibly succeed (503 / network). */
  readonly retryable: boolean;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryable = status === 503 || status === 502 || status === 0;
  }
}