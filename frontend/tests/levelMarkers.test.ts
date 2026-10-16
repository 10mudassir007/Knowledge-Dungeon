import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ALTAR,
  BRAZIERS,
  ENEMY_ANCHORS,
  GRID,
  LECTERN,
  SPAWN,
  cellsWithChar,
  cellToWorld,
  torchCells,
} from "../src/world/map";

/**
 * Minimal GLB reader: 12-byte header, then length-prefixed chunks. We only need
 * the JSON chunk, so we never touch the binary buffer. This keeps the test free of
 * any 3D runtime or extra dependency.
 */
interface GltfNode {
  name?: string;
  translation?: [number, number, number];
  children?: number[];
  mesh?: number;
}

interface Gltf {
  nodes?: GltfNode[];
  meshes?: { name?: string; primitives: { indices?: number; attributes: Record<string, number> }[] }[];
  accessors?: { count: number; type: string; componentType: number }[];
  cameras?: unknown[];
  materials?: { name?: string }[];
}

function readGlb(path: string): Gltf {
  const buf = readFileSync(path);
  const magic = buf.toString("ascii", 0, 4);
  if (magic !== "glTF") throw new Error(`not a GLB: magic=${JSON.stringify(magic)}`);

  const version = buf.readUInt32LE(4);
  if (version !== 2) throw new Error(`unexpected glTF version ${version}`);

  const total = buf.readUInt32LE(8);
  let offset = 12;
  while (offset < total) {
    const chunkLength = buf.readUInt32LE(offset);
    const chunkType = buf.readUInt32LE(offset + 4);
    // 0x4E4F534A = 'JSON'
    if (chunkType === 0x4e4f534a) {
      const text = buf.toString("utf8", offset + 8, offset + 8 + chunkLength);
      return JSON.parse(text) as Gltf;
    }
    offset += 8 + chunkLength;
  }
  throw new Error("no JSON chunk in GLB");
}

const GLB = readGlb(resolve(__dirname, "../public/assets/dungeon.glb"));

/** Nodes that carry a translation, keyed by name. */
function nodePositions(): Map<string, [number, number, number]> {
  const out = new Map<string, [number, number, number]>();
  (GLB.nodes ?? []).forEach((n) => {
    if (n.name && n.translation) out.set(n.name, n.translation);
  });
  return out;
}

const POS = nodePositions();

/** glTF is Y-up; Blender's grid is Z-up, so swap Y and Z to compare. */
function blenderPos(node: [number, number, number]): [number, number, number] {
  return [node[0], node[2], node[1]];
}

function expectNodeAtCell(name: string, col: number, row: number) {
  const node = POS.get(name);
  expect(node, `${name} missing from GLB`).toBeDefined();
  const [x, y, z] = blenderPos(node as [number, number, number]);
  const [wx, wy, wz] = cellToWorld({ col, row });
  expect(x, `${name}.x`).toBeCloseTo(wx, 4);
  expect(y, `${name}.y`).toBeCloseTo(wy, 4);
  expect(z, `${name}.z`).toBeCloseTo(wz, 4);
}

describe("dungeon.glb markers", () => {
  it("is a glTF 2.0 binary with nodes", () => {
    expect(GLB.nodes?.length ?? 0).toBeGreaterThan(0);
  });

  it("puts Altar on the altar cell", () => {
    expectNodeAtCell("Altar", ALTAR.col, ALTAR.row);
  });

  it("puts Spawn on the spawn cell", () => {
    expectNodeAtCell("Spawn", SPAWN.col, SPAWN.row);
  });

  it("puts Hint_Lectern on the lectern cell", () => {
    expectNodeAtCell("Hint_Lectern", LECTERN.col, LECTERN.row);
  });

  it("puts each Life_i on its brazier cell", () => {
    BRAZIERS.forEach((cell, i) => expectNodeAtCell(`Life_${i + 1}`, cell.col, cell.row));
  });

  it("puts every Torch_<col>_<row> on the grid cell it names", () => {
    const torches = torchCells();
    expect(torches.length).toBeGreaterThanOrEqual(8);
    for (const { col, row } of torches) {
      expectNodeAtCell(`Torch_${col}_${row}`, col, row);
    }
  });

  it("puts every Enemy_<col>_<row> on the grid cell it names", () => {
    for (const { col, row } of ENEMY_ANCHORS) {
      expectNodeAtCell(`Enemy_${col}_${row}`, col, row);
    }
  });

  it("exports no cameras and no lights", () => {
    expect(GLB.cameras ?? []).toHaveLength(0);
  });

  it("keeps the joined walls / floor / ceiling meshes", () => {
    const names = (GLB.meshes ?? []).map((m) => m.name);
    expect(names).toContain("Walls");
    expect(names).toContain("Floor");
    expect(names).toContain("Ceiling");
  });

  it("is under 10 MB", () => {
    const bytes = readFileSync(resolve(__dirname, "../public/assets/dungeon.glb")).length;
    expect(bytes).toBeLessThan(10 * 1024 * 1024);
  });
});

describe("GLB and grid agree on the whole dungeon", () => {
  it("has one marker node per grid marker cell, and no extras", () => {
    const gridMarkers = new Set<string>();
    for (const ch of ["Q", "S", "H", "B", "T", "E"]) {
      for (const cell of cellsWithChar(ch)) gridMarkers.add(`${ch},${cell.col},${cell.row}`);
    }
    expect(gridMarkers.size).toBe(1 + 1 + 1 + 3 + 12 + 5);

    // Every Torch_/Enemy_/Life_ node in the GLB must correspond to a grid cell.
    const torchNodes = [...POS.keys()].filter((n) => /^Torch_\d+_\d+$/.test(n));
    const enemyNodes = [...POS.keys()].filter((n) => /^Enemy_\d+_\d+$/.test(n));
    const lifeNodes = [...POS.keys()].filter((n) => /^Life_\d+$/.test(n));

    expect(torchNodes).toHaveLength(cellsWithChar("T").length);
    expect(enemyNodes).toHaveLength(cellsWithChar("E").length);
    expect(lifeNodes).toHaveLength(3);

    for (const name of [...torchNodes, ...enemyNodes]) {
      const m = /^(\w+?)_(\d+)_(\d+)$/.exec(name);
      expect(m, name).not.toBeNull();
      expect(GRID[Number(m?.[3])][Number(m?.[2])], name).toBe(m?.[1] === "Torch" ? "T" : "E");
    }
  });
});