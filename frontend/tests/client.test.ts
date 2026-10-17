import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { api, messageForStatus } from "../src/api/client";
import { ApiError } from "../src/api/types";

function mockFetch(status: number, body: unknown) {
  return vi.fn(async (_url: string, _init?: RequestInit) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("messageForStatus", () => {
  it("maps every status the backend can return", () => {
    expect(messageForStatus(404)).toMatch(/expired/i);
    expect(messageForStatus(409)).toBe("No active question.");
    expect(messageForStatus(422)).toMatch(/500 characters/);
    expect(messageForStatus(502)).toMatch(/could not produce a question/i);
    expect(messageForStatus(503)).toMatch(/AI is unavailable/i);
    expect(messageForStatus(0)).toMatch(/cannot reach/i);
    expect(messageForStatus(418)).toMatch(/went wrong/i);
  });

  it("never leaks raw JSON or a stack trace", () => {
    const message = messageForStatus(500, '{"traceback": "at foo()"}');
    expect(message).not.toContain("traceback");
    expect(message).not.toContain("{");
  });
});

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs the start payload and returns the session", async () => {
    const fetchMock = mockFetch(200, {
      session_id: "abc",
      age: 30,
      interest: "history",
      lives: 3,
      points: 0,
      level: 1,
      environment: "The dungeon stirs.",
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await api.startGame({ age: 30, interest: "history" });

    expect(res.session_id).toBe("abc");
    expect(res.environment).toBe("The dungeon stirs.");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/game/start");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ age: 30, interest: "history" });
  });

  it("sends only { answer } to answer-check", async () => {
    const fetchMock = mockFetch(200, {
      verdict: "Correct",
      correct: true,
      lives: 3,
      points: 10,
      level: 1,
      game_over: false,
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await api.answer("sid-1", "42");

    expect(res.correct).toBe(true);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ answer: "42" });
  });

  it("turns 409 into a readable ApiError", async () => {
    vi.stubGlobal("fetch", mockFetch(409, { detail: "No active question. Request one first." }));
    await expect(api.answer("sid", "42")).rejects.toMatchObject({
      status: 409,
      message: "No active question.",
    });
  });

  it("turns 503 into a retryable ApiError", async () => {
    vi.stubGlobal("fetch", mockFetch(503, { detail: "The game AI is unavailable right now." }));
    try {
      await api.question("sid");
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(503);
      expect((err as ApiError).retryable).toBe(true);
      expect((err as ApiError).message).toMatch(/AI is unavailable/i);
    }
  });

  it("maps a network failure to status 0", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    try {
      await api.health();
      throw new Error("should have thrown");
    } catch (err) {
      expect((err as ApiError).status).toBe(0);
      expect((err as ApiError).message).toMatch(/cannot reach/i);
    }
  });

  it("does not blow up on a non-JSON error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>502</html>", { status: 502 })),
    );
    await expect(api.hint("sid")).rejects.toMatchObject({ status: 502 });
  });

  it("exposes health without key values", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch(200, {
        status: "ok",
        provider: "groq",
        search_available: false,
        active_sessions: 1,
      }),
    );
    const health = await api.health();
    expect(health.provider).toBe("groq");
    expect(Object.keys(health).sort()).toEqual([
      "active_sessions",
      "provider",
      "search_available",
      "status",
    ]);
  });
});