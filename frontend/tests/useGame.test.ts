import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
  DEFEAT_LINGER_MS,
  DIFFICULTIES,
  HEAL_ON_CORRECT,
  HIT_DAMAGE,
  MAX_HEALTH,
  SUPER_POWER_COST,
  initialState,
  reducer,
  useGame,
} from "../src/game/useGame";
import { pickEnemyCells } from "../src/world/enemySpawn";

const QUESTION_A = "Question A?";

type Routes = {
  question?: () => unknown;
  answer?: (body: { answer: string }) => unknown;
  hint?: () => unknown;
};

function stubFetch(routes: Routes) {
  const calls: { url: string; body?: string }[] = [];
  let questionCount = 0;

  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body as string | undefined });
    const json = (value: unknown, status = 200) =>
      new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

    if (url.includes("/game/start")) {
      return json({
        session_id: "sid-1",
        age: 30,
        interest: "history",
        lives: 3,
        points: 0,
        level: 1,
        environment: "Intro.",
      });
    }
    if (url.endsWith("/question")) {
      questionCount += 1;
      return json({ question: (routes.question?.() as string) ?? QUESTION_A });
    }
    if (url.includes("/answer-check")) {
      return json(
        routes.answer?.(JSON.parse(init?.body as string)) ?? {
          verdict: "Correct",
          correct: true,
          lives: 3,
          points: 10,
          level: 1,
          game_over: false,
        },
      );
    }
    if (url.includes("/hint")) return json({ hint: (routes.hint?.() as string) ?? "A hint." });
    return json({ status: "ok", provider: "groq", search_available: false, active_sessions: 1 });
  });

  vi.stubGlobal("fetch", fetchMock);
  return { calls, getQuestionCount: () => questionCount };
}

const answer = (over: Partial<Record<string, unknown>> = {}) => ({
  verdict: "Correct",
  correct: true,
  lives: 3,
  points: 10,
  level: 1,
  game_over: false,
  ...over,
});

/** Boots a run through the setup screen + first load. */
async function boot(result: { current: ReturnType<typeof useGame> }, seed = 9) {
  await act(async () => {
    result.current.begin("Aric", DIFFICULTIES[1]);
  });
  await waitFor(() => expect(result.current.state.phase).toBe("playing"));
  await act(async () => {
    await result.current.startRun(seed);
  });
  await waitFor(() => expect(result.current.state.phase).toBe("playing"));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("useGame", () => {
  it("starts on the setup screen", () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    expect(result.current.state.phase).toBe("setup");
    expect(result.current.state.sessionId).toBeNull();
  });

  it("stores the player name and difficulty chosen at setup", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await act(async () => {
      result.current.begin("Brynn", DIFFICULTIES[2]);
    });
    await waitFor(() => expect(result.current.state.phase).toBe("playing"));
    expect(result.current.state.playerName).toBe("Brynn");
    expect(result.current.state.difficulty?.id).toBe("legend");
  });

  it("sends the difficulty's topic and orc count", async () => {
    const stub = stubFetch({});
    const { result } = renderHook(() => useGame());
    await act(async () => {
      result.current.begin("Aric", DIFFICULTIES[2]);
    });
    await waitFor(() => expect(result.current.state.phase).toBe("playing"));

    const startCall = stub.calls.find((c) => c.url.includes("/game/start"));
    expect(JSON.parse(startCall?.body ?? "{}").interest).toBe(DIFFICULTIES[2].interest);
    expect(result.current.state.orcs).toHaveLength(DIFFICULTIES[2].orcs);
  });

  it("seeds orcs and enters playing", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result, 1234);

    expect(result.current.state.sessionId).toBe("sid-1");
    expect(result.current.state.runSeed).toBe(1234);
    expect(result.current.state.intro).toBe("Intro.");
    expect(result.current.state.orcs.every((o) => o.status === "alive")).toBe(true);
    expect(result.current.state.orcs.map((o) => o.id)).toEqual(
      pickEnemyCells(1234, DIFFICULTIES[1].orcs).map((c) => `orc_${c.col}_${c.row}`),
    );
  });

  it("names orcs orc_<col>_<row>, not guardian", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result, 5);
    for (const orc of result.current.state.orcs) {
      expect(orc.id).toMatch(/^orc_\d+_\d+$/);
      expect(orc.id).not.toMatch(/guardian/i);
    }
  });

  it("marks only the active orc defeated on a correct answer", async () => {
    stubFetch({ answer: () => answer({ points: 10, level: 1 }) });
    const { result } = renderHook(() => useGame());
    await boot(result);

    const [first, second] = result.current.state.orcs;
    await act(async () => {
      await result.current.engage(first.id);
    });
    await waitFor(() => expect(result.current.state.question).toBe(QUESTION_A));

    await act(async () => {
      await result.current.submit("42");
    });

    const status = (id: string) => result.current.state.orcs.find((o) => o.id === id)?.status;
    expect(status(first.id)).toBe("defeated");
    expect(status(second.id)).toBe("alive");
    expect(result.current.state.points).toBe(10);
    expect(result.current.state.lives).toBe(3);
    expect(result.current.state.activeEnemyId).toBeNull();
    expect(result.current.state.phase).toBe("playing");
  });

  it("puts the defeated orc into the defeat animation", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result);
    const target = result.current.state.orcs[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await act(async () => {
      await result.current.submit("42");
    });
    await waitFor(() =>
      expect(result.current.state.orcs.find((o) => o.id === target.id)?.mood).toBe("defeat"),
    );
  });

  it("keeps a defeated orc for 3 seconds, then takes it out of the scene", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      stubFetch({});
      const { result } = renderHook(() => useGame());
      await boot(result);
      const target = result.current.state.orcs[0];
      const other = result.current.state.orcs[1];
      await act(async () => {
        await result.current.engage(target.id);
      });
      await act(async () => {
        await result.current.submit("42");
      });

      const orc = (id: string) => result.current.state.orcs.find((o) => o.id === id);
      expect(orc(target.id)?.gone).toBeFalsy();

      await act(async () => {
        vi.advanceTimersByTime(DEFEAT_LINGER_MS - 1);
      });
      expect(orc(target.id)?.gone).toBeFalsy();
      expect(orc(other.id)?.gone).toBeFalsy();

      await act(async () => {
        vi.advanceTimersByTime(1);
      });
      expect(orc(target.id)?.gone).toBe(true);
      expect(orc(other.id)?.gone).toBeFalsy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not let a previous run's removal timer blank a new orc", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      stubFetch({});
      const { result } = renderHook(() => useGame());
      await boot(result);
      const doomed = result.current.state.orcs[0];
      await act(async () => {
        await result.current.engage(doomed.id);
      });
      await act(async () => {
        await result.current.submit("42");
      });

      // restart before the dissolve timer lands, on a seed that reuses the cell
      await act(async () => {
        await result.current.startRun(9);
      });
      await act(async () => {
        vi.advanceTimersByTime(DEFEAT_LINGER_MS + 50);
      });
      const reused = result.current.state.orcs.find((o) => o.id === doomed.id);
      if (reused) expect(reused.gone).toBeFalsy();
      expect(result.current.state.orcs.every((o) => !o.gone)).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("puts the orc into the attack animation and costs a life on a wrong answer", async () => {
    stubFetch({ answer: () => answer({ verdict: "Incorrect", correct: false, lives: 2, points: 0 }) });
    const { result } = renderHook(() => useGame());
    await boot(result);
    const target = result.current.state.orcs[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await act(async () => {
      await result.current.submit("nope");
    });

    await waitFor(() => {
      const orc = result.current.state.orcs.find((o) => o.id === target.id);
      expect(orc?.status).toBe("alive");
      expect(orc?.mood).toBe("attack");
    });
    expect(result.current.state.lives).toBe(2);
    expect(result.current.state.points).toBe(0);
    expect(result.current.state.verdict?.good).toBe(false);
  });

  it("does not reassign the question when engaging a second orc", async () => {
    const stub = stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result);

    const [first, second] = result.current.state.orcs;
    await act(async () => {
      await result.current.engage(first.id);
    });
    await waitFor(() => expect(result.current.state.question).toBe(QUESTION_A));
    const after = stub.getQuestionCount();

    await act(async () => {
      await result.current.engage(second.id);
    });

    expect(stub.getQuestionCount()).toBe(after);
    expect(result.current.state.activeEnemyId).toBe(first.id);
    expect(result.current.state.question).toBe(QUESTION_A);
    expect(result.current.state.notice).toBe("Finish the current question first");
  });

  it("retreat clears the active orc without answering", async () => {
    const stub = stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result);
    const target = result.current.state.orcs[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await waitFor(() => expect(result.current.state.activeEnemyId).toBe(target.id));
    const before = stub.calls.filter((c) => c.url.includes("answer-check")).length;

    await act(async () => {
      result.current.retreat();
    });

    expect(result.current.state.activeEnemyId).toBeNull();
    expect(result.current.state.question).toBeNull();
    expect(result.current.state.phase).toBe("playing");
    expect(stub.calls.filter((c) => c.url.includes("answer-check")).length).toBe(before);
  });

  it("will not engage a defeated orc", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result);
    const target = result.current.state.orcs[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await act(async () => {
      await result.current.submit("42");
    });
    await waitFor(() => expect(result.current.state.orcs[0].status).toBe("defeated"));

    await act(async () => {
      await result.current.engage(target.id);
    });
    expect(result.current.state.activeEnemyId).toBeNull();
  });

  it("reaches the over state when lives hit 0", async () => {
    stubFetch({
      answer: () => answer({ verdict: "Incorrect", correct: false, lives: 0, points: 0, game_over: true }),
    });
    const { result } = renderHook(() => useGame());
    await boot(result);
    const target = result.current.state.orcs[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await act(async () => {
      await result.current.submit("no");
    });

    await waitFor(() => expect(result.current.state.phase).toBe("over"));
    expect(result.current.state.endReason).toBe("lost");
  });

  it("keeps playing past 90 points: the altar wins, the score does not", async () => {
    stubFetch({ answer: () => answer({ points: 100, level: 3 }) });
    const { result } = renderHook(() => useGame());
    await boot(result);
    const target = result.current.state.orcs[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await act(async () => {
      await result.current.submit("42");
    });

    expect(result.current.state.phase).toBe("playing");
    expect(result.current.state.points).toBe(100);
    expect(result.current.state.endReason).toBeNull();
  });

  it("reaches the over state when the player reaches the altar", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result);

    await act(async () => {
      result.current.reachAltar();
    });

    expect(result.current.state.phase).toBe("over");
    expect(result.current.state.endReason).toBe("won");
    expect(result.current.state.won).toBe(true);
  });

  it("wins with orcs still standing: clearing them all is optional", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result);
    expect(result.current.state.orcs.some((o) => o.status === "alive")).toBe(true);

    await act(async () => {
      result.current.reachAltar();
    });

    expect(result.current.state.orcs.some((o) => o.status === "alive")).toBe(true);
    expect(result.current.state.endReason).toBe("won");
  });

  it("a new run reshuffles orcs and resets the score", async () => {
    stubFetch({});
    const { result } = renderHook(() => useGame());
    await boot(result, 1);
    const first = result.current.state.orcs;

    const target = first[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await act(async () => {
      await result.current.submit("42");
    });
    await waitFor(() => expect(result.current.state.points).toBe(10));

    await act(async () => {
      await result.current.startRun(2);
    });
    await waitFor(() => expect(result.current.state.phase).toBe("playing"));

    expect(result.current.state.points).toBe(0);
    expect(result.current.state.lives).toBe(3);
    expect(result.current.state.activeEnemyId).toBeNull();
    expect(result.current.state.orcs.every((o) => o.status === "alive")).toBe(true);
    expect(result.current.state.orcs.map((o) => o.id)).toEqual(
      pickEnemyCells(2, DIFFICULTIES[1].orcs).map((c) => `orc_${c.col}_${c.row}`),
    );
    // The name survives the restart.
    expect(result.current.state.playerName).toBe("Aric");
  });

  it("surfaces a readable 409 from the hint endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/game/start")) {
          return new Response(
            JSON.stringify({
              session_id: "s", age: 30, interest: "history",
              lives: 3, points: 0, level: 1, environment: "i",
            }),
            { headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/question")) {
          return new Response(JSON.stringify({ question: QUESTION_A }), {
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify({ detail: "No active question. Request one first." }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const { result } = renderHook(() => useGame());
    await boot(result);
    const target = result.current.state.orcs[0];
    await act(async () => {
      await result.current.engage(target.id);
    });
    await act(async () => {
      await result.current.requestHint();
    });
    expect(result.current.state.notice).toBe("No active question.");
    expect(result.current.state.hinting).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Health and the super power are pure reducer transitions, so they are tested
// against the reducer directly - no API mocking needed.
// ---------------------------------------------------------------------------

const answered = (over: Partial<Parameters<typeof reducer>[1]> = {}) =>
  reducer(initialState(), {
    type: "answer/ok",
    beat: "Silence, briefly earned.",
    correct: false,
    lives: 2,
    points: 0,
    level: 1,
    gameOver: false,
    orcName: "Grukk",
    ...over,
  } as Parameters<typeof reducer>[1]);

describe("health", () => {
  it("starts full", () => {
    const s = initialState();
    expect(s.health).toBe(MAX_HEALTH);
    expect(s.maxHealth).toBe(MAX_HEALTH);
  });

  it("drops on a wrong answer", () => {
    expect(answered().health).toBe(MAX_HEALTH - HIT_DAMAGE);
  });

  it("knits back on a correct answer", () => {
    const spent = reducer(initialState(), { type: "power/start" });
    const healed = answered({ correct: true, lives: 3 });
    // Same starting point, but a correct answer heals instead of biting.
    const direct = reducer(spent, {
      type: "answer/ok",
      beat: "Silence, briefly earned.",
      correct: true, lives: 3, points: 10, level: 1,
      gameOver: false, orcName: "Grukk",
    });
    expect(direct.health).toBe(spent.health + HEAL_ON_CORRECT);
    expect(healed.health).toBeLessThanOrEqual(MAX_HEALTH);
  });

it("heals without ever passing the maximum", () => {
    let s = initialState();
    for (let i = 0; i < 4; i += 1) {
      s = reducer(s, {
        type: "answer/ok", beat: "Silence, briefly earned.", correct: true, lives: 3, points: 10,
        level: 1, gameOver: false, orcName: "Grukk",
      });
    }
    expect(s.health).toBe(MAX_HEALTH);
  });

  it("never goes below zero", () => {
    let s = initialState();
    for (let i = 0; i < 6; i += 1) {
      s = reducer(s, {
        type: "answer/ok", beat: "Silence, briefly earned.", correct: false, lives: 0, points: 0,
        level: 1, gameOver: true, orcName: "Grukk",
      });
    }
    expect(s.health).toBe(0);
  });
});

describe("super power", () => {
  it("spends health and records the reveal", () => {
    const spent = reducer(initialState(), { type: "power/start" });
    expect(spent.health).toBe(MAX_HEALTH - SUPER_POWER_COST);
    expect(spent.powering).toBe(true);
    expect(spent.powerUses).toBe(1);

    const done = reducer(spent, { type: "power/ok", answer: "Paris" });
    expect(done.powering).toBe(false);
    expect(done.revealed).toBe("Paris");
  });

  it("clears the reveal when the next question opens", () => {
    let s = reducer(initialState(), { type: "power/start" });
    s = reducer(s, { type: "power/ok", answer: "Paris" });
    expect(s.revealed).toBe("Paris");
    s = reducer(s, { type: "engage/start", enemyId: "orc_1_1" });
    s = reducer(s, { type: "engage/ok", enemyId: "orc_1_1", question: "Q?" });
    expect(s.revealed).toBeNull();
  });

  it("clears the reveal when the player retreats", () => {
    let s = reducer(initialState(), { type: "power/start" });
    s = reducer(s, { type: "power/ok", answer: "Paris" });
    expect(reducer(s, { type: "retreat" }).revealed).toBeNull();
  });
});