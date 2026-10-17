/**
 * The dungeon grid, and everything derived from it.
 *
 * Coordinate mapping matches the Blender export exactly:
 *   column c -> X = c * CELL   row r -> Z = r * CELL   height -> Y
 *   cell centre = (c * CELL + CELL/2, 0, r * CELL + CELL/2)
 *
 * CELL is 2 metres, set by dungeon/build_level.py when the geometry is built.
 * Corridors are therefore 2 m wide; the maze topology lives in GRID and never
 * changes when CELL does.
 *
 * Collision uses THIS grid, never the GLB mesh geometry.
 */

export type Cell = { col: number; row: number };

/** Metres per grid cell. Must match dungeon/build_level.py. */
export const CELL = 2;

export const GRID: readonly string[] = [
  "#########################################",
  "##....T...#...........#.............#...#",
  "#####.....#.###.##T...#.###.#######.###.#",
  "#E..#...#.E.#...#.....#.#.#.#.....#.....#",
  "#.#####.#####.###....##.#.#.#.T..######.#",
  "#...#...#.....#...#...#.#.#.#..Q......#.#",
  "###.#.###.#####.#####.#.#.#.#.....###.T.#",
  "#...#.#...#...#.......#...#.#.#.#.#.#...#",
  "#.###.#.#.#.#.T...#######.#.#.#.#.#.#...#",
  "#....E#.#.#.#.......#...#.#.#.#...#.#...#",
  "#T.######.#.##....###.#.#.#.#####.#.#####",
  "#.........#.#.#.#.#...#...#.....#.#.....#",
  "#..##.###.#.#.#.###.###########.#.#.###.#",
  "#...#.#...#.#.#...#.#.#...#...#.#.#.#.#.#",
  "###.#.#.###.#.###.#.#.#.#.#.#.#.#.#.#.#.#",
  "#E..#.#.#.....#...#.#.#.#.#.#...#...#...#",
  "#.###.##T..####.T...#.#.#.#.#########.###",
  "#.#...........#.....#.#.#...#.....#...#.#",
  "#.#####.....#.##....#.#.#####.T...#.###.#",
  "#.#BBB#...#.#...#.....#...#.......#.#...#",
  "#.#.#.#####.###.#####.###.#.##...##.T...#",
  "#...#.......#.#.#...#.#...#.#.....#.....#",
  "#############.#.#.#.###.###.#.###.##....#",
  "#...#E........#...#.#...#.#...#.....#.#.#",
  "#.#.#.#######.#####.#.###.#.###.#####.#.#",
  "#H#.#.#...........#.#...#.....#.......#.#",
  "#T..###.##T..######.###.#####.#########.#",
  "#S......#.....#...#...#...#.#.#.......#.#",
  "#..######.....#.#.###.###.#.#.###.###.#.#",
  "#...........#...#.........#.......#.....#",
  "#########################################",
];

export const WIDTH = GRID[0].length;
export const HEIGHT = GRID.length;

/** Characters that are plain walkable floor. */
export const FLOOR_CHARS = [".", "E"] as const;
/** Markers that must never hold an enemy. */
export const MARKER_CHARS = ["#", "Q", "H", "B", "T", "S"] as const;

export function charAt(col: number, row: number): string {
  if (row < 0 || row >= HEIGHT || col < 0 || col >= (GRID[row]?.length ?? 0)) return "#";
  return GRID[row][col];
}

/** Out of bounds counts as solid so the player can never leave the dungeon. */
export function isWall(col: number, row: number): boolean {
  return charAt(col, row) === "#";
}

export function isFloor(col: number, row: number): boolean {
  return (FLOOR_CHARS as readonly string[]).includes(charAt(col, row));
}

/** A cell an enemy may occupy: floor, and not a marker. */
export function isEligible(col: number, row: number): boolean {
  const ch = charAt(col, row);
  return !(MARKER_CHARS as readonly string[]).includes(ch) && ch !== " ";
}

export function findChar(ch: string): Cell | null {
  for (let row = 0; row < HEIGHT; row += 1) {
    const col = GRID[row].indexOf(ch);
    if (col >= 0) return { col, row };
  }
  return null;
}

/** Every cell holding `ch`, in row-major order. */
export function cellsWithChar(ch: string): Cell[] {
  const out: Cell[] = [];
  for (let row = 0; row < HEIGHT; row += 1) {
    for (let col = 0; col < WIDTH; col += 1) {
      if (GRID[row][col] === ch) out.push({ col, row });
    }
  }
  return out;
}

/**
 * A marker the game cannot start without. Derived from the grid only - there are
 * deliberately no hard-coded coordinates to drift out of sync with map.txt.
 */
function requireChar(ch: string): Cell {
  const cell = findChar(ch);
  if (!cell) throw new Error(`map: required marker "${ch}" is missing from the grid`);
  return cell;
}

export const ALTAR: Cell = requireChar("Q");
export const LECTERN: Cell = requireChar("H");
export const SPAWN: Cell = requireChar("S");

/** The three life braziers, left to right as they appear in the grid. */
export const BRAZIERS: readonly Cell[] = cellsWithChar("B");
/** The enemy anchors the Blender export carries. Frontend placement ignores them. */
export const ENEMY_ANCHORS: readonly Cell[] = cellsWithChar("E");

/**
 * Yaw that faces the player down the first open corridor at spawn.
 *
 * Derived from the grid rather than hard-coded: in a maze a fixed heading can
 * easily point straight into a wall. Forward in Player.useFrame is
 * (-sin(yaw), -cos(yaw)), hence the negated components.
 */
export const SPAWN_YAW: number = ((): number => {
  const dirs: readonly [number, number][] = [
    [1, 0],
    [0, 1],
    [-1, 0],
    [0, -1],
  ];
  for (const [dc, dr] of dirs) {
    if (!isWall(SPAWN.col + dc, SPAWN.row + dr)) return Math.atan2(-dc, -dr);
  }
  return 0;
})();

/** Grid cell -> world-space centre on the floor. */
export function cellToWorld(cell: Cell): [number, number, number] {
  return [cell.col * CELL + CELL / 2, 0, cell.row * CELL + CELL / 2];
}

/** World position -> the grid cell that contains it. */
export function worldToCell(worldX: number, worldZ: number): Cell {
  return { col: Math.floor(worldX / CELL), row: Math.floor(worldZ / CELL) };
}

/** Chebyshev distance in cells. */
export function chebyshev(a: Cell, b: Cell): number {
  return Math.max(Math.abs(a.col - b.col), Math.abs(a.row - b.row));
}

/**
 * Flood fill from `start`, treating `blocked` cells as solid.
 * Returns every reachable cell.
 */
export function reachableCells(start: Cell, blocked: ReadonlySet<string> = new Set()): Set<string> {
  const key = (c: number, r: number) => `${c},${r}`;
  if (isWall(start.col, start.row) || blocked.has(key(start.col, start.row))) return new Set();

  const seen = new Set<string>([key(start.col, start.row)]);
  const queue: Cell[] = [start];
  while (queue.length > 0) {
    const cur = queue.pop() as Cell;
    for (const [dc, dr] of [
      [1, 0],
      [-1, 0],
      [0, 1],
      [0, -1],
    ] as const) {
      const col = cur.col + dc;
      const row = cur.row + dr;
      const k = key(col, row);
      if (seen.has(k)) continue;
      if (isWall(col, row) || blocked.has(k)) continue;
      seen.add(k);
      queue.push({ col, row });
    }
  }
  return seen;
}

/** True when the altar can be walked to from spawn. */
export function altarReachableFrom(spawn: Cell = SPAWN, blocked: ReadonlySet<string> = new Set()): boolean {
  return reachableCells(spawn, blocked).has(`${ALTAR.col},${ALTAR.row}`);
}

const NEIGHBOURS: readonly [number, number][] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];

/**
 * Shortest walking distance (in 4-neighbour steps) from `start` to every cell
 * it can reach. Walls are solid; markers (Q, H, B, T, S) are floor, exactly as
 * `reachableCells` treats them.
 */
export function bfsDistances(start: Cell): Map<string, number> {
  const dist = new Map<string, number>();
  if (isWall(start.col, start.row)) return dist;

  const startKey = `${start.col},${start.row}`;
  dist.set(startKey, 0);
  const queue: Cell[] = [start];
  for (let head = 0; head < queue.length; head += 1) {
    const cur = queue[head];
    const step = (dist.get(`${cur.col},${cur.row}`) as number) + 1;
    for (const [dc, dr] of NEIGHBOURS) {
      const col = cur.col + dc;
      const row = cur.row + dr;
      const key = `${col},${row}`;
      if (dist.has(key) || isWall(col, row)) continue;
      dist.set(key, step);
      queue.push({ col, row });
    }
  }
  return dist;
}

/**
 * Every cell that lies on at least one shortest walk from `from` to `to`.
 *
 * A cell is on a shortest path exactly when the walk out from `from` plus the
 * walk back in from `to` is no longer than the shortest `from` -> `to` walk.
 * The enemy scatter is drawn from this set so the road to the altar is
 * guarded, never bypassed.
 */
export function routeCells(from: Cell = SPAWN, to: Cell = ALTAR): Set<string> {
  const out = bfsDistances(from);
  const back = bfsDistances(to);
  const total = out.get(`${to.col},${to.row}`);
  const onRoute = new Set<string>();
  if (total === undefined) return onRoute;

  for (const [key, dist] of out) {
    const remaining = back.get(key);
    if (remaining !== undefined && dist + remaining === total) onRoute.add(key);
  }
  return onRoute;
}

/** How close to the altar's cell centre counts as reaching it. */
export const ALTAR_RANGE = 2.5;

/**
 * The win condition, in one place: standing within ALTAR_RANGE of the altar.
 *
 * Takes the measured distance rather than coordinates because the proximity
 * loop already has it, and the rule is the same either way.
 */
export function reachedAltar(metresFromAltar: number): boolean {
  return metresFromAltar <= ALTAR_RANGE;
}

/**
 * Can a body of `radius` stand with its centre at world (worldX, worldZ)?
 *
 * Takes WORLD coordinates, not cell indices - the player moves continuously.
 * Samples the centre and the four corners of the circular footprint (as the
 * enclosing box) against the grid; out of bounds counts as solid.
 */
export function canStand(worldX: number, worldZ: number, radius: number): boolean {
  const samples: [number, number][] = [
    [worldX, worldZ],
    [worldX - radius, worldZ - radius],
    [worldX + radius, worldZ - radius],
    [worldX - radius, worldZ + radius],
    [worldX + radius, worldZ + radius],
  ];
  return samples.every(([x, z]) => {
    const cell = worldToCell(x, z);
    return !isWall(cell.col, cell.row);
  });
}

/**
 * Grid coords the GLB uses, for cross-checking marker empties against the map.
 */
export function torchCells(): Cell[] {
  return cellsWithChar("T");
}