/**
 * The whole game state machine.
 *
 * Orcs are a frontend concept: the backend only generates questions and scores
 * answers, so "who is asking" lives here and nowhere else.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { ApiError, MAX_ANSWER_LENGTH, WIN_POINTS } from "../api/types";
import { api } from "../api/client";
import {
  DEFAULT_ENEMY_COUNT,
  defeatBeat,
  enemyId,
  orcNameForCell,
  pickEnemyCells,
  pickReinforcementCells,
} from "../world/enemySpawn";
import type { Cell } from "../world/map";

/** One pursuit step: orc identity plus the cell it walks into. */
export interface OrcMove {
  id: string;
  cell: Cell;
}

export type Phase = "setup" | "loading" | "playing" | "dialogue" | "over";
export type EnemyStatus = "alive" | "defeated";
/** Drives the orc animation: idle, a strike (wrong answer), or a rout (correct). */
export type OrcMood = "idle" | "attack" | "defeat";

export interface Difficulty {
  id: "squire" | "adept" | "legend";
  label: string;
  blurb: string;
  /** Topic sent to the backend as `interest`. */
  interest: string;
  age: number;
  orcs: number;
}

export const DIFFICULTIES: Difficulty[] = [
  { id: "squire", label: "Squire", blurb: "Common lore. Few orcs.", interest: "everyday legends and folk tales", age: 30, orcs: 4 },
  { id: "adept", label: "Adept", blurb: "War history and empire.", interest: "ancient history and warring kingdoms", age: 30, orcs: 7 },
  { id: "legend", label: "Legend", blurb: "Forbidden lore. The dungeon stirs.", interest: "arcane, cursed and forbidden lore", age: 30, orcs: 11 },
];

export interface EnemyInstance {
  id: string;
  cell: Cell;
  status: EnemyStatus;
  mood: OrcMood;
  /** Bumped whenever an answer resolves, to restart the animation. */
  eventTick: number;
  /**
   * Set once the defeat dissolve has played: the orc is unmounted entirely.
   * It stays in state so "did we beat them all?" checks keep working.
   */
  gone?: boolean;
}

export interface GameState {
  phase: Phase;
  playerName: string;
  difficulty: Difficulty | null;
  sessionId: string | null;
  intro: string;
  points: number;
  lives: number;
  /** Frontend health meter, 0-100. See MAX_HEALTH above. */
  health: number;
  maxHealth: number;
  /** Times the super power has been spent this run. */
  powerUses: number;
  /** True while the super power is tearing the answer out of the orc. */
  powering: boolean;
  /** The answer the super power ripped loose, if it has been used. */
  revealed: string | null;
  level: number;
  gameOver: boolean;
  won: boolean;
  endReason: "won" | "lost" | null;
  runSeed: number;
  orcs: EnemyInstance[];
  /** How many orcs the run started with; reinforcement waves scale off it. */
  initialOrcs: number;
  activeEnemyId: string | null;
  question: string | null;
  hint: string | null;
  /** True while the backend is generating the question (E gives instant feedback). */
  engaging: boolean;
  submitting: boolean;
  hinting: boolean;
  notice: string | null;
  /** Last verdict banner, shown briefly after an answer. */
  verdict: { text: string; good: boolean } | null;
  error: string | null;
}

export const BUSY_NOTICE = "Finish the current question first";
export const NO_QUESTION = "No active question.";

/**
 * Health
 *
 * The backend's `lives` is a hard 3-strike counter (documented in
 * API_CONTRACT.md) and cannot be extended without changing the contract, so
 * health is a frontend layer on top of it:
 *
 *   - A wrong answer burns a whole life's worth of health (100 / 3).
 *   - A correct answer KNITS IT BACK, so a good answer feels like recovery.
 *   - The super power is the real spend: it costs health to tear the answer
 *     out of the orc's head, so you trade survival margin for knowledge.
 *
 * health is clamped to the backend's remaining lives, so the bar can never
 * claim more lives than the server will actually grant.
 */
export const MAX_HEALTH = 100;
/** How long a defeated orc's dissolve plays before it is removed from the scene. */
export const DEFEAT_LINGER_MS = 3000;
export const HIT_DAMAGE = 34;
export const HEAL_ON_CORRECT = 12;
export const SUPER_POWER_COST = 15;

type Action =
  | { type: "setup"; playerName: string; difficulty: Difficulty }
  | { type: "start/loading" }
  | { type: "start/ok"; sessionId: string; intro: string; seed: number; cells: Cell[]; orcs: number }
  | { type: "start/fail"; message: string }
  | { type: "engage/start"; enemyId: string }
  | { type: "engage/ok"; enemyId: string; question: string }
  | { type: "engage/busy" }
  | { type: "engage/fail"; message: string }
  | { type: "hint/start" }
  | { type: "hint/ok"; hint: string }
  | { type: "hint/fail"; message: string }
  | { type: "power/start" }
  | { type: "power/ok"; answer: string }
  | { type: "power/fail"; message: string }
  | { type: "answer/start" }
  | {
      type: "answer/ok";
      correct: boolean;
      /** Short environment beat shown after a correct answer. */
      beat: string;
      lives: number;
      points: number;
      level: number;
      gameOver: boolean;
      won: boolean;
      orcName: string;
    }
  | { type: "answer/fail"; message: string }
  | { type: "orc/remove"; id: string }
  | { type: "orcs/reinforce"; cells: Cell[] }
  | { type: "orcs/move"; moves: OrcMove[] }
  | { type: "notice"; text: string }
  | { type: "retreat" }
  | { type: "clear-verdict" };

export function initialState(): GameState {
  return {
    phase: "setup",
    playerName: "",
    difficulty: null,
    sessionId: null,
    intro: "",
    points: 0,
    lives: 3,
    health: MAX_HEALTH,
    maxHealth: MAX_HEALTH,
    powerUses: 0,
    powering: false,
    revealed: null,
    level: 1,
    gameOver: false,
    won: false,
    endReason: null,
    runSeed: 0,
    orcs: [],
    initialOrcs: 0,
    activeEnemyId: null,
    question: null,
    hint: null,
    engaging: false,
    submitting: false,
    hinting: false,
    notice: null,
    verdict: null,
    error: null,
  };
}

export function reducer(state: GameState, action: Action): GameState {
  switch (action.type) {
    case "setup":
      return {
        ...initialState(),
        phase: "loading",
        playerName: action.playerName,
        difficulty: action.difficulty,
      };

    case "start/loading":
      return { ...state, phase: "loading", error: null, verdict: null };

    case "start/ok":
      return {
        ...state,
        phase: "playing",
        sessionId: action.sessionId,
        intro: action.intro,
        runSeed: action.seed,
        points: 0,
        lives: 3,
        health: MAX_HEALTH,
        maxHealth: MAX_HEALTH,
        powerUses: 0,
        powering: false,
        revealed: null,
        level: 1,
        gameOver: false,
        won: false,
        endReason: null,
        activeEnemyId: null,
        question: null,
        hint: null,
        verdict: null,
        orcs: action.cells.map((cell) => ({
          id: enemyId(cell),
          cell,
          status: "alive" as const,
          mood: "idle" as const,
          eventTick: 0,
        })),
        initialOrcs: action.orcs,
      };

    case "start/fail":
      return { ...state, phase: "playing", error: action.message };

    case "engage/busy":
      return { ...state, notice: BUSY_NOTICE };

    case "engage/start":
      // Show the panel immediately; the model can take several seconds.
      return {
        ...state,
        phase: "dialogue",
        engaging: true,
        activeEnemyId: action.enemyId,
        question: null,
        hint: null,
        revealed: null,
        notice: null,
        verdict: null,
        submitting: false,
        orcs: state.orcs.map((o) =>
          o.id === action.enemyId ? { ...o, mood: "idle" as const, eventTick: o.eventTick + 1 } : o,
        ),
      };

    case "engage/ok":
      return {
        ...state,
        phase: "dialogue",
        engaging: false,
        activeEnemyId: action.enemyId,
        question: action.question,
        hint: null,
        notice: null,
        submitting: false,
        orcs: state.orcs.map((o) =>
          o.id === action.enemyId ? { ...o, mood: "idle" as const, eventTick: o.eventTick + 1 } : o,
        ),
      };

    case "engage/fail":
      return {
        ...state,
        engaging: false,
        notice: action.message,
        activeEnemyId: null,
        question: null,
        phase: "playing",
      };

    case "hint/start":
      return { ...state, hinting: true, notice: null };

    case "hint/ok":
      return { ...state, hinting: false, hint: action.hint };

    case "hint/fail":
      return { ...state, hinting: false, notice: action.message };

    case "power/start":
      // Spend the health up front so the button cannot be double-pressed.
      return {
        ...state,
        powering: true,
        notice: null,
        powerUses: state.powerUses + 1,
        health: Math.max(0, state.health - SUPER_POWER_COST),
      };

    case "power/ok":
      return { ...state, powering: false, revealed: action.answer };

    case "power/fail":
      return { ...state, powering: false, notice: action.message };

    case "answer/ok": {
      const activeId = state.activeEnemyId;
      const finished = action.gameOver || action.won;

      const orcs = state.orcs.map((o) => {
        if (o.id !== activeId) return o;
        return {
          ...o,
          status: action.correct ? ("defeated" as const) : o.status,
          mood: action.correct ? ("defeat" as const) : ("attack" as const),
          eventTick: o.eventTick + 1,
        };
      });

      return {
        ...state,
        submitting: false,
        // The question is consumed server-side either way, so clear it locally.
        activeEnemyId: null,
        question: null,
        hint: null,
        revealed: null,
        orcs,
        lives: action.lives,
        // Health is a vitality meter in [0, MAX_HEALTH]: wrong answers bite,
        // correct ones knit back. Clamped both ends so it can never go negative.
        health: Math.max(
          0,
          Math.min(
            MAX_HEALTH,
            action.correct ? state.health + HEAL_ON_CORRECT : state.health - HIT_DAMAGE,
          ),
        ),
        points: action.points,
        level: action.level,
        gameOver: action.gameOver,
        won: action.won,
        verdict: action.correct
          ? { text: `${action.orcName} cowers and dissolves.`, good: true }
          : { text: `${action.orcName} strikes you!`, good: false },
        // A short, per-orc environment beat. The long opening narration is a
        // fixed welcome only; replaying it after every kill is noise.
        notice: action.correct ? action.beat : state.notice,
        endReason: finished ? (action.won ? "won" : "lost") : state.endReason,
        phase: finished ? "over" : "playing",
      };
    }

    case "answer/fail":
      return { ...state, submitting: false, notice: action.message };

    // The dissolve has finished; take the orc out of the scene for good.
    case "orc/remove":
      return {
        ...state,
        orcs: state.orcs.map((o) => (o.id === action.id ? { ...o, gone: true } : o)),
      };

    // Every orc is down and the run is not won: the dungeon sends more. Without
    // this a run with finite orcs and few points would strand the player - no
    // orcs left to ask questions, no way to reach 90, no way to lose either.
    case "orcs/reinforce":
      if (action.cells.length === 0) return state;
      return {
        ...state,
        orcs: [
          ...state.orcs,
          ...action.cells.map((cell) => ({
            id: enemyId(cell),
            cell,
            status: "alive" as const,
            mood: "idle" as const,
            eventTick: 0,
          })),
        ],
        notice: "War-drums in the dark. They keep coming.",
      };

    // Per-tick pursuit steps. Orc ids are identity, not addresses, so moving is
    // safe for the dialogue/defeat timers that pin an id.
    case "orcs/move": {
      const go = new Map(action.moves.map((m) => [m.id, m.cell]));
      return {
        ...state,
        orcs: state.orcs.map((o) => (go.has(o.id) ? { ...o, cell: go.get(o.id) as Cell } : o)),
      };
    }

    case "notice":
      return { ...state, notice: action.text };

    case "retreat":
      // NOTE: the backend keeps the question active when we walk away, so
      // re-engaging the same orc shows the SAME question again.
      return {
        ...state,
        phase: "playing",
        activeEnemyId: null,
        question: null,
        hint: null,
        revealed: null,
        engaging: false,
        notice: null,
        verdict: null,
      };

    case "clear-verdict":
      return { ...state, verdict: null };

    default:
      return state;
  }
}

export interface UseGameOptions {
  interest?: string;
  age?: number;
  orcCount?: number;
}

export function useGame({ interest, age, orcCount }: UseGameOptions = {}) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);

  const difficulty = state.difficulty;

  // Pending "this orc has dissolved, drop it" timers. Orc ids are per cell, so
  // a timer left over from a finished run would delete a fresh orc that spawns
  // in the same cell; every new run drops them.
  const lingerTimers = useRef<number[]>([]);
  useEffect(
    () => () => {
      lingerTimers.current.forEach((id) => window.clearTimeout(id));
      lingerTimers.current = [];
    },
    [],
  );

  const startRun = useCallback(
    async (seed?: number, override?: Difficulty) => {
      lingerTimers.current.forEach((id) => window.clearTimeout(id));
      lingerTimers.current = [];

      const diff = override ?? difficulty;
      const useInterest = interest ?? diff?.interest ?? DIFFICULTIES[1].interest;
      const useAge = age ?? diff?.age ?? 30;
      const useOrcs = orcCount ?? diff?.orcs ?? DEFAULT_ENEMY_COUNT;

      dispatch({ type: "start/loading" });
      const runSeed = seed ?? Math.floor(Math.random() * 2 ** 31);
      try {
        const res = await api.startGame({ age: useAge, interest: useInterest });
        dispatch({
          type: "start/ok",
          sessionId: res.session_id,
          intro: res.environment,
          seed: runSeed,
          cells: pickEnemyCells(runSeed, useOrcs),
          orcs: useOrcs,
        });
      } catch (err) {
        dispatch({ type: "start/fail", message: err instanceof ApiError ? err.message : "Could not start a run." });
      }
    },
    [age, difficulty, interest, orcCount],
  );

  /** Called by the setup screen once the player has entered a name + difficulty. */
  const begin = useCallback(
    async (playerName: string, chosen: Difficulty) => {
      dispatch({ type: "setup", playerName, difficulty: chosen });
      await startRun(undefined, chosen);
    },
    [startRun],
  );

  const engage = useCallback(
    async (id: string) => {
      const target = state.orcs.find((e) => e.id === id);
      if (!target || target.status === "defeated" || state.engaging) return;
      // One orc at a time; never reassign a question already in flight.
      if (state.activeEnemyId && state.activeEnemyId !== id) {
        dispatch({ type: "engage/busy" });
        return;
      }
      if (!state.sessionId) return;

      dispatch({ type: "engage/start", enemyId: id });
      try {
        const res = await api.question(state.sessionId);
        dispatch({ type: "engage/ok", enemyId: id, question: res.question });
      } catch (err) {
        dispatch({ type: "engage/fail", message: err instanceof ApiError ? err.message : NO_QUESTION });
      }
    },
    [state.orcs, state.activeEnemyId, state.engaging, state.sessionId],
  );

  const submit = useCallback(
    async (answer: string) => {
      const trimmed = answer.slice(0, MAX_ANSWER_LENGTH);
      if (!state.sessionId || state.submitting || !state.activeEnemyId) return;
      dispatch({ type: "answer/start" });
      try {
        const res = await api.answer(state.sessionId, trimmed);
        const orc = state.orcs.find((o) => o.id === state.activeEnemyId);
        dispatch({
          type: "answer/ok",
          correct: res.correct,
          lives: res.lives,
          points: res.points,
          level: res.level,
          gameOver: res.game_over,
          won: res.won,
          orcName: orc ? orcNameForCell(orc.cell, state.runSeed) : "The orc",
          beat: orc
            ? defeatBeat(orc.cell, state.runSeed, state.orcs.filter((o) => o.status === "defeated").length)
            : "Silence, briefly earned.",
        });
        // "cowes and dissolves" is only half the story: once the dissolve has
        // played out, take the orc out of the scene entirely so it stops
        // costing draw calls and stops standing there as a ghost.
        if (res.correct) {
          const id = state.activeEnemyId;
          const timer = window.setTimeout(() => {
            dispatch({ type: "orc/remove", id });
            lingerTimers.current = lingerTimers.current.filter((t) => t !== timer);
          }, DEFEAT_LINGER_MS);
          lingerTimers.current.push(timer);
        }
      } catch (err) {
        dispatch({ type: "answer/fail", message: err instanceof ApiError ? err.message : "That did not go through." });
      }
    },
    [state.sessionId, state.submitting, state.activeEnemyId, state.orcs],
  );

  const requestHint = useCallback(async () => {
    if (!state.sessionId || state.hinting) return;
    dispatch({ type: "hint/start" });
    try {
      const res = await api.hint(state.sessionId);
      dispatch({ type: "hint/ok", hint: res.hint });
    } catch (err) {
      dispatch({ type: "hint/fail", message: err instanceof ApiError ? err.message : NO_QUESTION });
    }
  }, [state.sessionId, state.hinting]);

  const retreat = useCallback(() => dispatch({ type: "retreat" }), []);
  const clearNotice = useCallback(() => dispatch({ type: "clear-verdict" }), []);

  /**
   * The super power: spend health to tear the answer out of the orc.
   * The question stays active server-side, so it still has to be submitted.
   */
  const useSuperPower = useCallback(async () => {
    if (!state.sessionId || state.powering || state.revealed || state.health <= 0) return;
    dispatch({ type: "power/start" });
    try {
      const res = await api.reveal(state.sessionId);
      dispatch({ type: "power/ok", answer: res.answer });
    } catch (err) {
      dispatch({ type: "power/fail", message: err instanceof ApiError ? err.message : NO_QUESTION });
    }
  }, [state.sessionId, state.powering, state.revealed, state.health]);

  const activeEnemy = useMemo(
    () => state.orcs.find((e) => e.id === state.activeEnemyId) ?? null,
    [state.orcs, state.activeEnemyId],
  );

  // ...And a mirror of state for the App's own interval loop, so the pursuit
  // interval never has to be re-armed when orcs shuffle (which the interval
  // itself causes - re-arming on your own output is a live-lock of resets).
  const live = useRef(state);
  live.current = state;

  /** Dispatch a batch of pursuit steps computed by the App's tick loop. */
  const moveOrcs = useCallback((moves: OrcMove[]) => {
    if (moves.length === 0) return;
    dispatch({ type: "orcs/move", moves });
  }, []);

  /** One-line system message; the App's notice timer clears it. */
  const showNotice = useCallback((text: string) => {
    dispatch({ type: "notice", text });
  }, []);

  /**
   * Spawn a reinforcement wave away from the player and every existing orc.
   * Returns how many spawned. Reads live state, so its identity never changes.
   */
  const reinforceWave = useCallback((player: Cell): number => {
    const s = live.current;
    if (!s.sessionId || s.won || s.gameOver) return 0;
    const seed = (s.runSeed ^ (s.orcs.length * 0x9e3779b9)) >>> 0;
    const count = Math.max(2, Math.ceil(s.initialOrcs / 2));
    const cells = pickReinforcementCells(seed, count, {
      player,
      occupied: s.orcs.map((o) => o.cell),
    });
    if (cells.length === 0) return 0;
    dispatch({ type: "orcs/reinforce", cells });
    return cells.length;
  }, []);

  return {
    state,
    activeEnemy,
    begin,
    startRun,
    engage,
    submit,
    requestHint,
    useSuperPower,
    retreat,
    clearNotice,
    moveOrcs,
    reinforceWave,
    showNotice,
    winPoints: WIN_POINTS,
    healthPct: Math.max(0, Math.min(100, (state.health / state.maxHealth) * 100)),
    canUseSuperPower: !state.powering && !state.revealed && state.health > 0,
  };
}