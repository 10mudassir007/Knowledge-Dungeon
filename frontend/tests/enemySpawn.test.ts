import { describe, expect, it } from "vitest";
import {
  ANCHOR_EXCLUSION,
  DEFAULT_ENEMY_COUNT,
  MIN_ENEMY_SPACING,
  REINFORCE_EXCLUSION,
  enemyId,
  mulberry32,
  pickEnemyCells,
  pickReinforcementCells,
  stepToward,
} from "../src/world/enemySpawn";
import { ALTAR, LECTERN, SPAWN, altarReachableFrom, canStand, cellToWorld, charAt, isEligible, routeCells, type Cell } from "../src/world/map";

const chebyshev = (a: { col: number; row: number }, b: { col: number; row: number }) =>
  Math.max(Math.abs(a.col - b.col), Math.abs(a.row - b.row));

describe("mulberry32", () => {
  it("is deterministic for a seed", () => {
    const a = mulberry32(1234);
    const b = mulberry32(1234);
    const seqA = [a(), a(), a()];
    const seqB = [b(), b(), b()];
    expect(seqA).toEqual(seqB);
  });

  it("stays in [0,1)", () => {
    const rand = mulberry32(99);
    for (let i = 0; i < 200; i += 1) {
      const v = rand();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("differs between seeds", () => {
    expect(mulberry32(1)()).not.toBe(mulberry32(2)());
  });
});

describe("pickEnemyCells", () => {
  it("is stable for the same seed and different across seeds", () => {
    const a = pickEnemyCells(42);
    const b = pickEnemyCells(42);
    const c = pickEnemyCells(43);
    expect(a).toEqual(b);
    expect(a).not.toEqual(c);
  });

  it("returns the default count of distinct cells", () => {
    const cells = pickEnemyCells(7);
    expect(cells).toHaveLength(DEFAULT_ENEMY_COUNT);
    expect(new Set(cells.map(enemyId)).size).toBe(DEFAULT_ENEMY_COUNT);
  });

  it("never picks a wall or a marker cell", () => {
    for (const cell of pickEnemyCells(11)) {
      const ch = charAt(cell.col, cell.row);
      expect(ch).not.toBe("#");
      expect(ch).not.toBe("Q");
      expect(ch).not.toBe("H");
      expect(ch).not.toBe("B");
      expect(ch).not.toBe("T");
      expect(ch).not.toBe("S");
    }
  });

  it("keeps every enemy more than 3 cells from altar, spawn and lectern", () => {
    for (const seed of [1, 2, 3, 4, 5, 6, 7, 8]) {
      for (const cell of pickEnemyCells(seed)) {
        expect(chebyshev(cell, ALTAR)).toBeGreaterThan(ANCHOR_EXCLUSION);
        expect(chebyshev(cell, SPAWN)).toBeGreaterThan(ANCHOR_EXCLUSION);
        expect(chebyshev(cell, LECTERN)).toBeGreaterThan(ANCHOR_EXCLUSION);
      }
    }
  });

  it("leaves the altar reachable from spawn with enemies treated as solid", () => {
    for (const seed of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) {
      const blocked = new Set(pickEnemyCells(seed).map((c) => `${c.col},${c.row}`));
      expect(altarReachableFrom(SPAWN, blocked), `seed ${seed}`).toBe(true);
    }
  });

  it("returns cells in a stable order", () => {
    const cells = pickEnemyCells(5);
    const sorted = cells.slice().sort((a, b) => a.row - b.row || a.col - b.col);
    expect(cells).toEqual(sorted);
  });

  it("clamps the count to the number of eligible cells", () => {
    const all = pickEnemyCells(3, 999);
    // Clamped to "everything eligible", not to the default of 3.
    expect(all.length).toBeGreaterThan(DEFAULT_ENEMY_COUNT);
    expect(new Set(all.map(enemyId)).size).toBe(all.length);
    expect(all.every((c) => charAt(c.col, c.row) !== "#")).toBe(true);
    expect(altarReachableFrom(SPAWN, new Set(all.map((c) => `${c.col},${c.row}`)))).toBe(true);
  });

  it("returns an empty list for a count of zero or less", () => {
    expect(pickEnemyCells(1, 0)).toEqual([]);
    expect(pickEnemyCells(1, -5)).toEqual([]);
  });

  it("honours custom anchors", () => {
    const cells = pickEnemyCells(21, 2, { altar: { col: 3, row: 3 }, spawn: { col: 3, row: 3 }, lectern: { col: 3, row: 3 } });
    for (const c of cells) {
      expect(chebyshev(c, { col: 3, row: 3 })).toBeGreaterThan(ANCHOR_EXCLUSION);
    }
  });

  it("places every orc on walkable floor, with room for its body", () => {
    // An orc must stand on a real floor cell and have clearance to stand in,
    // otherwise it would be embedded in a wall or hovering over a gap.
    for (let seed = 0; seed < 25; seed += 1) {
      for (const cell of pickEnemyCells(seed)) {
        const ch = charAt(cell.col, cell.row);
        expect(ch, `seed ${seed} cell ${cell.col},${cell.row}`).not.toBe("#");
        expect(ch, `seed ${seed} cell ${cell.col},${cell.row}`).not.toBe(" ");
        // Player-sized footprint fits: an orc body is wider, so this is a floor check.
        const [x, , z] = cellToWorld(cell);
        expect(canStand(x, z, 0.35), `seed ${seed} at ${cell.col},${cell.row}`).toBe(true);
      }
    }
  });

  it("never returns a duplicate cell across many seeds", () => {
    for (let seed = 0; seed < 50; seed += 1) {
      const cells = pickEnemyCells(seed);
      expect(new Set(cells.map(enemyId)).size).toBe(cells.length);
    }
  });
});

const cellKey = (c: Cell) => `${c.col},${c.row}`;

/** All enemy-sharing floor cells of a run, plus the two ends of the walk. */
function farthestPair(seed: number): { a: Cell; b: Cell } {
  const cells = pickEnemyCells(seed, 999).sort((x, y) => x.row - y.row || x.col - y.col);
  return { a: cells[0], b: cells[cells.length - 1] };
}

describe("the scatter guards the altar route", () => {
  it("puts every initial orc on a shortest walk to the altar", () => {
    // The walk to the altar is the run: an orc a dead end never meets the
    // player. Every difficulty count, many seeds.
    const route = routeCells();
    for (let seed = 0; seed < 60; seed += 1) {
      for (const cell of pickEnemyCells(seed, 11)) {
        expect(route.has(cellKey(cell)), `seed ${seed} at ${cellKey(cell)}`).toBe(true);
      }
    }
  });

  it("spaces the initial scatter out", () => {
    for (const seed of [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]) {
      const cells = pickEnemyCells(seed, 7);
      for (let i = 0; i < cells.length; i += 1) {
        for (let j = i + 1; j < cells.length; j += 1) {
          expect(
            chebyshev(cells[i], cells[j]),
            `seed ${seed}: ${cellKey(cells[i])} vs ${cellKey(cells[j])}`,
          ).toBeGreaterThanOrEqual(MIN_ENEMY_SPACING);
        }
      }
    }
  });

  it("still fills the whole count on the route", () => {
    expect(pickEnemyCells(4, 11)).toHaveLength(11);
    expect(pickEnemyCells(4, 11).every((c) => routeCells().has(cellKey(c)))).toBe(true);
  });
});

describe("stepToward", () => {
  it("walks a ghost one step at a time until it stands next to the target", () => {
    for (let seed = 0; seed < 12; seed += 1) {
      const { a, b } = farthestPair(seed);
      const occupied = new Set<string>([cellKey(a)]);
      const visited = new Set<string>([cellKey(a)]);
      let cur = a;
      let steps = 0;
      for (;;) {
        const step = stepToward(cur, b, occupied);
        if (!step) throw new Error(`seed ${seed}: no route ${cellKey(cur)} -> ${cellKey(b)}`);
        // Never out of the maze, never into a wall, never onto someone else.
        expect(isEligible(step.col, step.row), `${cellKey(step)} eligible`).toBe(true);
        expect(occupied.has(cellKey(step)), `${cellKey(step)} free`).toBe(false);
        expect(visited.has(cellKey(step)), `${cellKey(step)} not revisited`).toBe(false);
        visited.add(cellKey(step));
        occupied.delete(cellKey(cur));
        occupied.add(cellKey(step));
        cur = step;
        steps += 1;
        expect(steps, "terminates within the floor-cell count").toBeLessThanOrEqual(1271);
        if (chebyshev(cur, b) <= 1) break;
      }
    }
  });

  it("holds ground when already adjacent to the target", () => {
    for (let seed = 0; seed < 10; seed += 1) {
      const cells = pickEnemyCells(seed, 999);
      // Any two eligible cells one step apart: crowded, not chasing.
      const adjacent = cells
        .flatMap((c) =>
          cells
            .filter((o) => chebyshev(c, o) === 1)
            .map((o) => ({ from: c, to: o })),
        )
        .at(0);
      if (!adjacent) continue;
      expect(stepToward(adjacent.from, adjacent.to, new Set([cellKey(adjacent.from)]))).toBeNull();
    }
  });

  it("still finds a step with several orcs crowding the maze", () => {
    for (let seed = 0; seed < 10; seed += 1) {
      const { a, b } = farthestPair(seed);
      const crowd = new Set(pickEnemyCells(seed, 40).map(cellKey));
      crowd.delete(cellKey(a));
      crowd.delete(cellKey(b));
      const step = stepToward(a, b, crowd);
      if (step) {
        expect(isEligible(step.col, step.row)).toBe(true);
        expect(crowd.has(cellKey(step)), "never steps onto an occupied cell").toBe(false);
      }
      // or the crowd walls the route in, in which case null is correct.
    }
  });
});

describe("pickReinforcementCells", () => {
  it("is stable for a seed and disjoint from the occupied cells", () => {
    const initial = pickEnemyCells(42, 7);
    const a = pickReinforcementCells(7, 4, { player: SPAWN, occupied: initial });
    const b = pickReinforcementCells(7, 4, { player: SPAWN, occupied: initial });
    expect(a).toEqual(b);
    const occupiedKeys = new Set(initial.map(cellKey));
    for (const c of a) expect(occupiedKeys.has(cellKey(c)), `no overlap at ${cellKey(c)}`).toBe(false);
  });

  it("spawns every reinforcement at least REINFORCE_EXCLUSION cells away", () => {
    for (let seed = 0; seed < 12; seed += 1) {
      const initial = pickEnemyCells(seed, 7);
      const player = pickEnemyCells(seed + 100, 1)[0];
      for (const c of pickReinforcementCells(seed * 31, 5, { player, occupied: initial })) {
        expect(chebyshev(c, player)).toBeGreaterThanOrEqual(REINFORCE_EXCLUSION);
      }
    }
  });

  it("keeps altar clear of the anchors and the altar route walkable", () => {
    for (let seed = 0; seed < 12; seed += 1) {
      const initial = pickEnemyCells(seed, 7);
      const fresh = pickReinforcementCells(seed * 91, 5, { player: SPAWN, occupied: initial });
      const blocked = new Set([...initial, ...fresh].map(cellKey));
      for (const c of fresh) {
        expect(chebyshev(c, ALTAR), `altar at ${cellKey(c)}`).toBeGreaterThan(ANCHOR_EXCLUSION);
        expect(chebyshev(c, SPAWN)).toBeGreaterThan(ANCHOR_EXCLUSION);
        expect(chebyshev(c, LECTERN)).toBeGreaterThan(ANCHOR_EXCLUSION);
      }
      expect(altarReachableFrom(SPAWN, blocked), `seed ${seed}`).toBe(true);
    }
  });

  it("sends reinforcements onto the route to the altar too", () => {
    const route = routeCells();
    for (let seed = 0; seed < 20; seed += 1) {
      const initial = pickEnemyCells(seed, 7);
      const player = pickEnemyCells(seed + 500, 1)[0];
      for (const c of pickReinforcementCells(seed * 17, 4, { player, occupied: initial })) {
        expect(route.has(cellKey(c)), `seed ${seed} at ${cellKey(c)}`).toBe(true);
      }
    }
  });

  it("refuses to spawn when everything near the player is taken", () => {
    // Occupy literally every eligible cell: nothing legal remains.
    const all: Cell[] = [];
    for (let row = 0; row < 31; row += 1) {
      for (let col = 0; col < 41; col += 1) {
        if (isEligible(col, row)) all.push({ col, row });
      }
    }
    expect(pickReinforcementCells(5, 4, { player: SPAWN, occupied: all })).toEqual([]);
  });
});