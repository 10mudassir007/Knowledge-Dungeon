/**
 * Seeded enemy placement — frontend only.
 *
 * The backend has no concept of enemies. Every run picks its own layout from a
 * seed so the dungeon is stable within a run and reshuffles between runs.
 */

import {
  ALTAR,
  HEIGHT,
  LECTERN,
  SPAWN,
  WIDTH,
  type Cell,
  altarReachableFrom,
  isEligible,
  routeCells,
} from "./map";

export const DEFAULT_ENEMY_COUNT = 5;
/** Enemies never spawn this close (Chebyshev, in cells) to these anchors. */
export const ANCHOR_EXCLUSION = 3;
/** Preferred Chebyshev gap between two enemies of the same wave, in cells. */
export const MIN_ENEMY_SPACING = 4;

function key(c: number, r: number): string {
  return `${c},${r}`;
}

/** Small, fast, deterministic PRNG. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function next(): number {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffle<T>(items: T[], rand: () => number): T[] {
  const out = items.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function chebyshev(a: Cell, b: Cell): number {
  return Math.max(Math.abs(a.col - b.col), Math.abs(a.row - b.row));
}

/** Exported for the pursuit loop in App.tsx: cells are Chebyshev distances. */
export { chebyshev };

/**
 * Weave up to `wanted` cells out of `pool` into `chosen`.
 *
 * Deterministic (the caller shuffles), never repeats a cell, never seats two
 * enemies closer than `gap` cells unless nothing else is left, and never picks
 * a cell whose removal would strand the altar from spawn.
 */
function takeCells(
  pool: Cell[],
  wanted: number,
  gap: number,
  chosen: Cell[],
  blocked: Set<string>,
  spawn: Cell,
): void {
  const taken = new Set(chosen.map((c) => key(c.col, c.row)));
  for (const cell of pool) {
    if (chosen.length >= wanted) return;
    const k = key(cell.col, cell.row);
    if (taken.has(k)) continue;
    if (gap > 0 && chosen.some((c) => chebyshev(c, cell) < gap)) continue;
    // Tentatively occupy it and confirm the altar is still walkable.
    blocked.add(k);
    if (!altarReachableFrom(spawn, blocked)) {
      blocked.delete(k);
      continue;
    }
    chosen.push(cell);
    taken.add(k);
  }
}

/**
 * Scatter `wanted` cells across the maze, guarding the altar route first.
 *
 * The walk to the altar is the run, so the scatter is drawn from
 * `routeCells()`: an enemy the path cannot avoid tests the player, one in a
 * dead end never does. Off-route cells are only used if the route cannot seat
 * everyone, and everything is returned in stable (row, col) order.
 */
function scatter(
  seed: number,
  wanted: number,
  candidates: Cell[],
  blocked: Set<string>,
  spawn: Cell,
): Cell[] {
  const onRoute = routeCells(spawn, ALTAR);
  const rand = mulberry32(seed);
  const onPath = shuffle(
    candidates.filter((c) => onRoute.has(key(c.col, c.row))),
    rand,
  );
  const offPath = shuffle(
    candidates.filter((c) => !onRoute.has(key(c.col, c.row))),
    rand,
  );

  const chosen: Cell[] = [];
  takeCells(onPath, wanted, MIN_ENEMY_SPACING, chosen, blocked, spawn);
  takeCells(onPath, wanted, 0, chosen, blocked, spawn);
  takeCells(offPath, wanted, 0, chosen, blocked, spawn);
  return chosen.sort((a, b) => a.row - b.row || a.col - b.col);
}

/**
 * Pick `count` distinct, reachable enemy cells, on the route to the altar.
 *
 * - Floor cells only; `#`, `Q`, `H`, `B`, `T`, `S` are excluded.
 * - Nothing within ANCHOR_EXCLUSION cells (Chebyshev) of the altar, spawn or lectern.
 * - Enemies are treated as solid, so any cell whose removal would strand the
 *   altar from spawn is rejected — they can never block the only way through.
 * - Deterministic for a given seed; returned in stable (row, col) order.
 */
export function pickEnemyCells(
  seed: number,
  count: number = DEFAULT_ENEMY_COUNT,
  anchors: { altar?: Cell; spawn?: Cell; lectern?: Cell } = {},
): Cell[] {
  const altar = anchors.altar ?? ALTAR;
  const spawn = anchors.spawn ?? SPAWN;
  const lectern = anchors.lectern ?? LECTERN;

  const candidates: Cell[] = [];
  for (let row = 0; row < HEIGHT; row += 1) {
    for (let col = 0; col < WIDTH; col += 1) {
      if (!isEligible(col, row)) continue;
      const cell = { col, row };
      if (
        chebyshev(cell, altar) <= ANCHOR_EXCLUSION ||
        chebyshev(cell, spawn) <= ANCHOR_EXCLUSION ||
        chebyshev(cell, lectern) <= ANCHOR_EXCLUSION
      ) {
        continue;
      }
      candidates.push(cell);
    }
  }

  const wanted = Math.max(0, Math.min(count, candidates.length));
  if (wanted === 0) return [];

  return scatter(seed, wanted, candidates, new Set<string>(), spawn);
}

/** Stable, human-readable id for an orc cell. */
export function enemyId(cell: Cell): string {
  return `orc_${cell.col}_${cell.row}`;
}

/**
 * One BFS step from an orc's cell toward the player.
 *
 * `occupied` holds every cell an orc already stands on (plus cells taken by
 * earlier moves in the same tick) - orcs never share a cell. Returns null when
 * the orc is already adjacent (it crowds the player's last cell but never steps
 * onto it) or when no walkable route exists. BFS so an orc rounds corners
 * instead of grinding against whichever wall happens to face the player.
 */
export function stepToward(from: Cell, to: Cell, occupied: Set<string>): Cell | null {
  const fromKey = key(from.col, from.row);
  if (chebyshev(from, to) <= 1) return null;

  // Search outward from the player's cell so the answer we need is simply
  // `from`'s predecessor: whichever cell BFS walked *through* to reach `from`.
  const prev = new Map<string, string>();
  const target = key(to.col, to.row);
  prev.set(target, target);
  const queue: string[] = [target];
  while (queue.length > 0) {
    const cur = queue.shift() as string;
    const [c, r] = cur.split(",").map(Number);
    for (const [dc, dr] of [
      [0, 1],
      [0, -1],
      [1, 0],
      [-1, 0],
    ] as const) {
      const nc = c + dc;
      const nr = r + dr;
      const nextKey = key(nc, nr);
      if (prev.has(nextKey)) continue;
      // `from` itself may be occupied; it is the starting point, not a barrier.
      if (occupied.has(nextKey) && nextKey !== fromKey) continue;
      if (!isEligible(nc, nr)) continue;
      prev.set(nextKey, cur);
      queue.push(nextKey);
    }
  }

  // Unreachable (blocked or out of bounds): the orc holds its ground.
  if (!prev.has(fromKey)) return null;
  let node = fromKey;
  for (;;) {
    const pred = prev.get(node);
    if (pred === undefined) return null;
    if (pred === target) {
      const [c, r] = node.split(",").map(Number);
      return { col: c, row: r };
    }
    node = pred;
  }
}

/** Reinforcements want more breathing room than the initial scatter. */
export const REINFORCE_EXCLUSION = 6;

export interface ReinforceOptions {
  /** The player's current cell; spawns this far away and never closer. */
  player: Cell;
  /** Every existing orc cell (alive, defeated or already removed). */
  occupied: Cell[];
  /** Minimum Chebyshev distance in cells from the player (default 6). */
  exclusion?: number;
}

/**
 * Cells for a reinforcement wave, seeded like the initial scatter.
 *
 * Same rules as `pickEnemyCells` - eligible floor, clear of the anchors,
 * guarding the altar route, never blocking it - but on top of that it avoids
 * every occupied cell and everything within REINFORCE_EXCLUSION cells of the
 * player, so new orcs never materialise in view or on top of an existing one.
 */
export function pickReinforcementCells(
  seed: number,
  count: number,
  opts: ReinforceOptions,
): Cell[] {
  const { player, occupied } = opts;
  const exclusion = opts.exclusion ?? REINFORCE_EXCLUSION;

  const takenKeys = new Set<string>(occupied.map((c) => `${c.col},${c.row}`));
  const playerKey = key(player.col, player.row);

  const candidates: Cell[] = [];
  for (let row = 0; row < HEIGHT; row += 1) {
    for (let col = 0; col < WIDTH; col += 1) {
      if (!isEligible(col, row)) continue;
      const cell = { col, row };
      const k = key(col, row);
      if (takenKeys.has(k) || k === playerKey) continue;
      if (chebyshev(cell, player) < exclusion) continue;
      if (
        chebyshev(cell, ALTAR) <= ANCHOR_EXCLUSION ||
        chebyshev(cell, SPAWN) <= ANCHOR_EXCLUSION ||
        chebyshev(cell, LECTERN) <= ANCHOR_EXCLUSION
      ) {
        continue;
      }
      candidates.push(cell);
    }
  }

  const wanted = Math.max(0, Math.min(count, candidates.length));
  if (wanted === 0) return [];

  return scatter(seed, wanted, candidates, new Set<string>(takenKeys), SPAWN);
}

const ORC_STARTS = ["Gru", "Mog", "Urz", "Kra", "Tho", "Zug", "Gor", "Brug", "Shag", "Khel", "Ur", "Mag"];
const ORC_ENDS = ["nak", "gash", "ruk", "mar", "dush", "ka", "gorath", "nash", "ril", "zug"];
/** Epithets, so two orcs never read as the same syllable soup. */
const ORC_TITLES = [
  "the Unbroken",
  "the Bone-Talker",
  "the Quieter",
  "the Ashen",
  "the Half-Blind",
  "the Patient",
  "the Oathkeeper",
  "the Starved",
  "the Sleepless",
  "the Thorned",
];

/**
 * A stable orc name for a cell *within a run*.
 *
 * Seeded by the run seed as well as the cell, so the same cell is "Grukka" one
 * run and "Shagmir" the next, while staying stable for the whole run (the UI
 * must not re-roll a name between the dialogue and the verdict). Used only for
 * flavour text - the backend knows nothing about it.
 */
export function orcNameForCell(cell: Cell, runSeed = 0): string {
  const rand = mulberry32((runSeed ^ (cell.col * 2654435761) ^ (cell.row * 40503) ^ 7) >>> 0);
  const a = ORC_STARTS[Math.floor(rand() * ORC_STARTS.length) % ORC_STARTS.length];
  const b = ORC_ENDS[Math.floor(rand() * ORC_ENDS.length) % ORC_ENDS.length];
  return a + b;
}

/** The same name with an epithet, for the dialogue header. */
export function orcTitleForCell(cell: Cell, runSeed = 0): string {
  const rand = mulberry32((runSeed ^ (cell.col * 97) ^ (cell.row * 7919) ^ 0x5f3a) >>> 0);
  const title = ORC_TITLES[Math.floor(rand() * ORC_TITLES.length) % ORC_TITLES.length];
  return `${orcNameForCell(cell, runSeed)}, ${title}`;
}

/**
 * Short environment beats shown after each kill.
 *
 * Deliberately one line and under ~12 words: the opening narration is a long
 * fixed script, and anything longer here fights the HUD for attention. Seeded
 * per run + cell so a run feels authored but never repeats the same order.
 */
const BEATS = [
  "Dust settles. Something else takes its place.",
  "The dark drinks the last of the light.",
  "Silence, briefly earned.",
  "A draught finds the corridor again.",
  "The stones remember it too.",
  "Footsteps, somewhere ahead of you.",
  "The flame leans, as if listening.",
  "Another secret spills into the floor.",
  "The hall exhales.",
  "Not quiet. Never quite quiet.",
  "Cold air moves past you.",
  "Something answers from deeper in.",
];

export function defeatBeat(cell: Cell, runSeed = 0, defeated = 0): string {
  const rand = mulberry32((runSeed ^ (cell.col * 31) ^ (cell.row * 131) ^ (defeated * 7919)) >>> 0);
  return BEATS[Math.floor(rand() * BEATS.length) % BEATS.length];
}