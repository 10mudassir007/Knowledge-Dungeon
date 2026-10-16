import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ALTAR,
  BRAZIERS,
  CELL,
  ENEMY_ANCHORS,
  GRID,
  HEIGHT,
  LECTERN,
  SPAWN,
  SPAWN_YAW,
  WIDTH,
  type Cell,
  altarReachableFrom,
  canStand,
  cellToWorld,
  charAt,
  cellsWithChar,
  isEligible,
  isFloor,
  isWall,
  reachableCells,
  torchCells,
  worldToCell,
} from "../src/world/map";

/** Breadth-first shortest path in cells, or null when unreachable. */
function shortestPath(from: Cell, to: Cell): Cell[] | null {
  const prev = new Map<string, Cell | null>();
  prev.set(`${from.col},${from.row}`, null);
  let frontier = [from];
  while (frontier.length > 0) {
    const next: Cell[] = [];
    for (const cur of frontier) {
      for (const [dc, dr] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
        const col = cur.col + dc;
        const row = cur.row + dr;
        const k = `${col},${row}`;
        if (prev.has(k)) continue;
        if (isWall(col, row)) continue;
        prev.set(k, cur);
        if (col === to.col && row === to.row) {
          const path: Cell[] = [];
          let node: Cell | null | undefined = { col, row };
          while (node) {
            path.push(node);
            node = prev.get(`${node.col},${node.row}`);
          }
          return path.reverse();
        }
        next.push({ col, row });
      }
    }
    frontier = next;
  }
  return null;
}

describe("grid shape", () => {
  it("is 41x31 with every row exactly 41 characters", () => {
    expect(WIDTH).toBe(41);
    expect(HEIGHT).toBe(31);
    expect(GRID).toHaveLength(31);
    GRID.forEach((row, i) => {
      expect(row.length, `row ${i}`).toBe(41);
    });
  });

  it("is identical to dungeon/map.txt", () => {
    // The Blender build and the frontend must never drift apart.
    const txt = readFileSync(resolve(__dirname, "../../dungeon/map.txt"), "utf8");
    const rows = txt.split(/\r?\n/).filter((line) => line.length > 0);
    expect(rows).toEqual([...GRID]);
    expect(rows.every((r) => r.length === 41)).toBe(true);
    expect(rows).toHaveLength(31);
  });

  it("has a solid outer border", () => {
    for (let col = 0; col < WIDTH; col += 1) {
      expect(isWall(col, 0), `top ${col}`).toBe(true);
      expect(isWall(col, HEIGHT - 1), `bottom ${col}`).toBe(true);
    }
    for (let row = 0; row < HEIGHT; row += 1) {
      expect(isWall(0, row), `left ${row}`).toBe(true);
      expect(isWall(WIDTH - 1, row), `right ${row}`).toBe(true);
    }
  });
});

describe("marker counts", () => {
  it("has exactly one spawn, altar and lectern", () => {
    expect(cellsWithChar("S")).toHaveLength(1);
    expect(cellsWithChar("Q")).toHaveLength(1);
    expect(cellsWithChar("H")).toHaveLength(1);
  });

  it("has three braziers in a row", () => {
    const braziers = cellsWithChar("B");
    expect(braziers).toHaveLength(3);
    expect(new Set(braziers.map((c) => c.row)).size).toBe(1);
    const cols = braziers.map((c) => c.col).sort((a, b) => a - b);
    expect(cols[1]).toBe(cols[0] + 1);
    expect(cols[2]).toBe(cols[1] + 1);
  });

  it("has between 8 and 12 torches and 4 to 6 enemy anchors", () => {
    expect(torchCells().length).toBeGreaterThanOrEqual(8);
    expect(torchCells().length).toBeLessThanOrEqual(12);
    expect(ENEMY_ANCHORS.length).toBeGreaterThanOrEqual(4);
    expect(ENEMY_ANCHORS.length).toBeLessThanOrEqual(6);
  });

  it("places spawn bottom-left and altar top-right", () => {
    expect(SPAWN).toEqual({ col: 1, row: 27 });
    expect(ALTAR).toEqual({ col: 31, row: 5 });
    expect(LECTERN).toEqual({ col: 1, row: 25 });
    expect(SPAWN.row).toBeGreaterThan(HEIGHT / 2);
    expect(ALTAR.row).toBeLessThan(HEIGHT / 2);
    expect(ALTAR.col).toBeGreaterThan(WIDTH / 2);
  });

  it("places the lectern within 5 cells of spawn", () => {
    const d = Math.max(Math.abs(LECTERN.col - SPAWN.col), Math.abs(LECTERN.row - SPAWN.row));
    expect(d).toBeLessThanOrEqual(5);
  });

  it("lists braziers in grid order", () => {
    expect(BRAZIERS).toEqual([
      { col: 3, row: 19 },
      { col: 4, row: 19 },
      { col: 5, row: 19 },
    ]);
  });
});

describe("reachability", () => {
  it("can flood fill from spawn to the altar", () => {
    const seen = reachableCells(SPAWN);
    expect(seen.has(`${ALTAR.col},${ALTAR.row}`)).toBe(true);
    expect(altarReachableFrom(SPAWN)).toBe(true);
  });

  it("reaches every floor cell - no unreachable pockets", () => {
    const seen = reachableCells(SPAWN);
    const total = GRID.join("").split("").filter((ch) => ch !== "#").length;
    expect(seen.size).toBe(total);
  });

  it("makes the walk from spawn to altar at least 60 steps", () => {
    expect(shortestPath(SPAWN, ALTAR)?.length ?? 0).toBeGreaterThanOrEqual(60);
  });

  it("can physically walk the whole route - the body never overlaps a wall", () => {
    // Cell-centre connectivity is not enough: a player has a 0.35 m radius, so a
    // corridor has to be wide enough for the footprint box at every point along
    // the way. Walk the path in 5 cm increments and check canStand at each one.
    const path = shortestPath(SPAWN, ALTAR);
    expect(path).not.toBeNull();
    const RADIUS = 0.35;
    const STEP = 0.05;
    let checks = 0;
    for (let i = 0; i < (path?.length ?? 0) - 1; i += 1) {
      const a = path![i];
      const b = path![i + 1];
      const [ax, , az] = cellToWorld(a);
      const [bx, , bz] = cellToWorld(b);
      const dist = Math.hypot(bx - ax, bz - az);
      for (let t = 0; t <= dist; t += STEP) {
        const x = ax + ((bx - ax) * t) / dist;
        const z = az + ((bz - az) * t) / dist;
        const cell = `${Math.floor(x)},${Math.floor(z)}`;
        if (!canStand(x, z, RADIUS)) {
          throw new Error(`blocked at ${cell} on leg ${a.col},${a.row} -> ${b.col},${b.row}`);
        }
        checks += 1;
      }
    }
    expect(checks).toBeGreaterThan(1000);
  });

  it("can physically walk to the lectern and to every brazier", () => {
    const RADIUS = 0.35;
    const walkable = (from: Cell, to: Cell) => {
      const path = shortestPath(from, to);
      expect(path, `no route ${from.col},${from.row} -> ${to.col},${to.row}`).not.toBeNull();
      for (const c of path ?? []) {
        const [x, , z] = cellToWorld(c);
        expect(canStand(x, z, RADIUS), `cell ${c.col},${c.row}`).toBe(true);
      }
    };
    for (const b of BRAZIERS) walkable(SPAWN, b);
  });

  it("treats blocked cells as solid", () => {
    expect(altarReachableFrom({ col: 0, row: 0 }, new Set(["0,0"]))).toBe(false);
  });

  it("refuses to flood fill out of a wall", () => {
    expect(reachableCells({ col: 0, row: 0 }).size).toBe(0);
  });
});

describe("coordinates", () => {
  it("maps cells to Blender world coordinates", () => {
    // CELL = 2 m: the altar at cell (31,5) lands on world (63, 0, 11).
    expect(cellToWorld(ALTAR)).toEqual([63, 0, 11]);
    expect(cellToWorld(SPAWN)).toEqual([3, 0, 55]);
  });

  it("round-trips world positions back to their cell", () => {
    for (const cell of [SPAWN, ALTAR, LECTERN, ...BRAZIERS]) {
      const [x, , z] = cellToWorld(cell);
      expect(worldToCell(x, z)).toEqual(cell);
    }
  });

  it("finds every torch cell in row-major order", () => {
    expect(torchCells()).toHaveLength(12);
    expect(torchCells()[0]).toEqual({ col: 6, row: 1 });
    expect(torchCells()).toContainEqual({ col: 38, row: 6 });
    expect(torchCells()).toContainEqual({ col: 36, row: 20 });
  });

  it("faces the player down an open corridor at spawn", () => {
    // Forward is (-sin, -cos); the heading must land on a non-wall cell.
    const dx = -Math.sin(SPAWN_YAW);
    const dz = -Math.cos(SPAWN_YAW);
    const col = SPAWN.col + Math.round(dx);
    const row = SPAWN.row + Math.round(dz);
    expect(isWall(col, row)).toBe(false);
  });
});

describe("collision", () => {
  it("rejects wall cells", () => {
    expect(isWall(0, 0)).toBe(true);
    expect(isWall(2, 1)).toBe(false);
    expect(canStand(CELL / 2, CELL / 2, 0.35)).toBe(false);
    const [fx, , fz] = cellToWorld({ col: 2, row: 1 });
    expect(canStand(fx, fz, 0.35)).toBe(true);
  });

  it("treats everything outside the grid as solid", () => {
    expect(isWall(-1, 1)).toBe(true);
    expect(isWall(41, 1)).toBe(true);
    expect(isWall(1, 31)).toBe(true);
    expect(canStand(-1, 1, 0.35)).toBe(false);
    expect(canStand(CELL, 99 * CELL, 0.35)).toBe(false);
    expect(canStand(999 * CELL, 999 * CELL, 0.35)).toBe(false);
  });

  it("rejects a body that would clip a corner wall", () => {
    // (2,2) is a wall cell; (2.05, 2.05) is just inside its cell on a 1 m grid.
    expect(isWall(2, 2)).toBe(true);
    expect(canStand(2 * CELL + 0.05, 2 * CELL + 0.05, 0.35)).toBe(false);
  });

  it("refuses a body straddling the outer border", () => {
    // (2,1) is floor, but a corner sample slipping into the wall row 0 is not.
    expect(isWall(2, 1)).toBe(false);
    expect(canStand(2 * CELL + 0.5, 1 * CELL + 0.02, 0.35)).toBe(false);
    expect(canStand(2 * CELL + 0.5, 1 * CELL + 0.4, 0.35)).toBe(true);
  });

  it("leaves room to walk: corridors are two cell widths", () => {
    // A 0.35 m radius body must fit anywhere the grid says is floor.
    const [x, , z] = cellToWorld({ col: 2, row: 1 });
    expect(canStand(x - CELL / 2 + 0.4, z, 0.35)).toBe(true);
    expect(canStand(x + CELL / 2 - 0.4, z, 0.35)).toBe(true);
  });

  it("keeps floor and eligibility distinct from markers", () => {
    expect(isFloor(2, 1)).toBe(true);
    expect(isFloor(ALTAR.col, ALTAR.row)).toBe(false);
    expect(isEligible(ALTAR.col, ALTAR.row)).toBe(false);
    expect(isEligible(LECTERN.col, LECTERN.row)).toBe(false);
    expect(isEligible(SPAWN.col, SPAWN.row)).toBe(false);
    expect(isEligible(BRAZIERS[0].col, BRAZIERS[0].row)).toBe(false);
    expect(isEligible(6, 1)).toBe(false);
    expect(isEligible(0, 0)).toBe(false);
    expect(isEligible(5, 3)).toBe(true);
  });

  it("reads characters safely outside the grid", () => {
    expect(charAt(-5, -5)).toBe("#");
    expect(charAt(999, 999)).toBe("#");
  });
});