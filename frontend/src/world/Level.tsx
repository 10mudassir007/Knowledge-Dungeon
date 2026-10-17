/**
 * Loads the Blender level and exposes its marker empties.
 *
 * Enemy_ nodes that ship in the GLB are hidden and ignored for placement —
 * enemies are placed in code by world/enemySpawn.ts, not read from the model.
 */

import { useEffect, useMemo, useRef } from "react";
import { useGLTF } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { ALTAR, BRAZIERS, LECTERN, SPAWN, cellToWorld, torchCells, type Cell } from "./map";
import { rockMaterial } from "./rockTextures";

export interface Markers {
  altar: [number, number, number];
  spawn: [number, number, number];
  lectern: [number, number, number];
  lives: Record<string, [number, number, number]>;
  flames: Record<string, [number, number, number]>;
  torches: { col: number; row: number; position: [number, number, number] }[];
  /**
   * World position of each torch's *flame mesh* from the GLB. The marker empty
   * sits at the cell centre; the fire is on the sconce, up against a wall, so
   * lights have to follow the mesh or they glow through the stone.
   */
  torchFlames: Record<string, [number, number, number]>;
  /** Names that were not found in the GLB and fell back to the grid. */
  missing: string[];
}

export const GLB_URL = "/assets/dungeon.glb";
const TORCH_RE = /^Torch_(\d+)_(\d+)$/;
const TORCH_FLAME_RE = /^PropFlame_(\d+)_(\d+)$/;

/** Hide every Enemy_ node in a (cloned) scene, keeping it in the file. */
function hideEnemyNodes(root: THREE.Object3D): void {
  root.traverse((obj) => {
    if (obj.name.startsWith("Enemy_")) obj.visible = false;
  });
}

/**
 * Undo the exporter's Z-up -> Y-up conversion.
 *
 * dungeon.glb is exported spec-compliant Y-up, so the Blender axis mapping
 * (X = column, Y = height, Z = row) arrives in glTF as (X, Z, -Y) - the rows end
 * up on glTF's up axis and the ceiling points along -Z. A +90 degree turn about X
 * maps (x, y, z) back to (x, -z, y), restoring three.js to the grid convention:
 * X = column, Y = height, Z = row, which is what cellToWorld and all collision
 * maths assume.
 */
function unskew(root: THREE.Object3D): void {
  root.rotation.x = Math.PI / 2;
}

/**
 * Swap the GLB's baked stone for the sharper runtime rock materials, and push
 * the existing flame/crystal emission harder so bloom has something to catch.
 */
function applyLook(root: THREE.Object3D): void {
  const stoneByName: Record<string, "wall" | "floor" | "ceiling" | "trim"> = {
    Floor: "floor",
    Ceiling: "ceiling",
    Altar_Block: "trim",
    Prop_Crate: "trim",
  };

  // Emissive parts never cast: a flame mesh that throws a hard shadow looks
  // like a hole in the room, and the point light already sells the glow.
  const isEmissive = (name: string): boolean =>
    /^(Flame_|PropFlame_|AltarCrystal)/.test(name);

  // Authored emission strengths, pre-scaled: the GLB ships 9 / 3.2 / 6, but
  // the load path (drei's loader cache) can leave emissiveIntensity far below
  // the authored values, so re-assert them instead of nudging what arrived.
  // The scaling is deliberate: strength 9 with bloom turns close-range flames
  // into a white blob, and the torch point lights already sell the glow.
  const EMISSIVE_HALVED: Record<string, number> = {
    prop_flame: 2.2,
    prop_ember: 1.6,
    prop_crystal: 3.0,
  };

  /**
   * True only for meshes that actually ship the baked COLOR_0 attribute.
   *
   * This is the difference between a lit prop and a black hole: the AO bake
   * writes COLOR_0 for the Walls/Floor/Ceiling only, and three.js multiplies
   * the attribute straight into the base colour when vertexColors is on. A
   * material with vertexColors=true on a geometry with NO `color` attribute
   * binds the missing attribute to (0,0,0) and every prop renders black - which
   * is exactly what happened when this was set unconditionally.
   */
  const hasBakedVertexColor = (mesh: THREE.Mesh): boolean =>
    mesh.geometry?.getAttribute("color") !== undefined;

  root.traverse((obj) => {
    if (!(obj as THREE.Mesh).isMesh) return;
    const mesh = obj as THREE.Mesh;

    // Walls keep the baked ashlar material exported from Blender (basecolor +
    // ORM + normal). It is the only material in the GLB with real texture
    // maps, so leave it intact and give it full environment reflections.
    if (mesh.name === "Walls") {
      mesh.receiveShadow = true;
      // The shell has to occlude, or torch light leaks straight through stone
      // into the next room and the level reads as one bright blob.
      mesh.castShadow = true;
      const wallMats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const mat of wallMats) {
        const m = mat as THREE.MeshStandardMaterial;
        if (m && m.isMeshStandardMaterial) m.envMapIntensity = 0.9;
      }
      return;
    }

    const stone = stoneByName[mesh.name];
    if (stone) {
      const mat = rockMaterial(stone);
      // The GLB carries a COLOR_0 attribute (baked ambient occlusion + torch
      // bounce). three.js only multiplies it in when vertexColors is on, so the
      // runtime canvas materials have to opt in.
      mat.vertexColors = hasBakedVertexColor(mesh);
      mat.needsUpdate = true;
      mesh.material = mat;
      mesh.receiveShadow = true;
      mesh.castShadow = mesh.name !== "Ceiling";
      return;
    }

    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    // Props cast so torches throw real silhouettes instead of an even wash -
    // except sconces bolted flush to a wall: their bracket sits against the
    // stone and low-res torch shadow maps smear a dark smudge around every
    // torch, so sconces and flames never cast shadows themselves.
    const mounted = mesh.name.startsWith("PropTorch") || mesh.name.startsWith("PropFlame");
    if (!isEmissive(mesh.name) && !mounted) {
      mesh.castShadow = true;
      mesh.receiveShadow = true;
    }
    const baked = hasBakedVertexColor(mesh);
    for (const mat of mats) {
      if (!mat) continue;
      const m = mat as THREE.MeshStandardMaterial;
      // vertexColors must track the mesh's actual attributes, in BOTH
      // directions: props in this GLB carry no COLOR_0, so forcing it on
      // multiplied them by the missing attribute's default of (0,0,0).
      if (m.vertexColors !== baked) {
        m.vertexColors = baked;
        m.needsUpdate = true;
      }
      // Emission materials: assert authored strength, kill the fake metal 1
      // default, and skip the dark-base recolor below (their glow does not
      // depend on base colour at all).
      const halved = EMISSIVE_HALVED[m.name];
      if (m.emissive && halved !== undefined) {
        m.emissiveIntensity = halved;
        m.metalness = 0;
      } else if (m.emissive && m.emissiveIntensity > 0) {
        // One-time temper for the remaining lit materials (orc gems etc.).
        if (!m.userData.__kdTempered) {
          m.userData.__kdTempered = true;
          m.emissiveIntensity *= 0.5;
        }
      }
      // A fully metallic surface has nothing to reflect in a torch-lit dungeon,
      // so dial metalness down rather than repainting: the authored colours
      // (rust, wood, iron, bone) are what make the props read as objects
      // instead of grey silhouettes. The old code forced every metal prop to
      // one grey, which is why nothing looked coloured.
      if (m.metalness > 0.55) m.metalness = 0.55;
      if (m.roughness < 0.35) m.roughness = 0.35;
      // Only intervene if a material is physically black: with no light to
      // reflect it can never show colour at all. Emission materials are
      // excluded - their look is carried by emissive, not base.
      if (m.color && halved === undefined && (m.color.r + m.color.g + m.color.b) / 3 < 0.035) {
        m.color = new THREE.Color("#5a584e");
      }
    }
  });
}

function useMarkers(scene: THREE.Group): Markers {
  const warned = useRef(new Set<string>());

return useMemo(() => {
    unskew(scene);
    hideEnemyNodes(scene);
    applyLook(scene);
    // unskew() just changed the root rotation, so every child matrixWorld is
    // stale. Reading geometry bounds against a stale matrix collapses them to
    // a point at the origin - which is exactly where the torch lights ended up.
    scene.updateWorldMatrix(true, true);

    const byName = new Map<string, THREE.Object3D>();
    scene.traverse((obj) => byName.set(obj.name, obj));

    const missing: string[] = [];
    const box = new THREE.Box3();
    const v = new THREE.Vector3();

/**
     * World position of a named node.
     *
     * Two traps here, both of which silently put every torch light on the world
     * origin: prop meshes from Blender bake their vertices in world coordinates
     * so their object transform is (0,0,0), and a multi-material prop arrives as
     * a group node *and* one mesh per material, all sharing the same name.
     * So: scan for every node with this name, union the geometry bounds of the
     * ones that have geometry, and only fall back to the transform for real
     * marker empties (which have none).
     */
    const posOf = (name: string): [number, number, number] | null => {
      let found: THREE.Object3D | null = null;
      let hasGeo = false;
      box.makeEmpty();

      scene.traverse((o) => {
        // The GLB exporter splits a multi-material prop into a group plus one
        // mesh per material, and suffixes them ("PropTorch_1_26_1"). Matching
        // the bare name finds only the geometry-less group, so match the
        // prefix too - with the "_" guard so Torch_1_2 can't swallow Torch_1_26.
        if (o.name !== name && !o.name.startsWith(`${name}_`)) return;
        if (!found) found = o;
        const g = (o as THREE.Mesh).geometry;
        if (!g) return;
        g.computeBoundingBox();
        if (!g.boundingBox) return;
        const b = g.boundingBox.clone();
        b.applyMatrix4(o.matrixWorld);
        box.union(b);
        hasGeo = true;
      });

      if (!found) return null;
      if (hasGeo) {
        box.getCenter(v);
        return [v.x, v.y, v.z];
      }
      const obj = found as THREE.Object3D;
      obj.updateWorldMatrix(true, false);
      v.setFromMatrixPosition(obj.matrixWorld);
      return [v.x, v.y, v.z];
    };

    // Missing marker -> fall back to the grid and warn once, never crash.
    const resolve = (name: string, fallbackCell: { col: number; row: number }) => {
      const p = posOf(name);
      if (p) return p;
      if (!warned.current.has(name)) {
        warned.current.add(name);
        console.warn(`[dungeon] marker "${name}" missing from the GLB - falling back to the grid`);
      }
      missing.push(name);
      return cellToWorld(fallbackCell);
    };

    const altar = resolve("Altar", ALTAR);
    const spawn = resolve("Spawn", SPAWN);
    const lectern = resolve("Hint_Lectern", LECTERN);

    const lives: Record<string, [number, number, number]> = {};
    const flames: Record<string, [number, number, number]> = {};
    const brazier = (i: number): Cell => BRAZIERS[i - 1] ?? ALTAR;
    for (let i = 1; i <= 3; i += 1) {
      const life = posOf(`Life_${i}`);
      if (life) lives[`Life_${i}`] = life;
      else resolve(`Life_${i}`, brazier(i));

      const flame = posOf(`Flame_${i}`);
      if (flame) flames[`Flame_${i}`] = flame;
      else resolve(`Flame_${i}`, brazier(i));
    }

const torches: { col: number; row: number; position: [number, number, number] }[] = [];
    const torchFlames: Record<string, [number, number, number]> = {};
    for (const [name, obj] of byName) {
      const m = TORCH_RE.exec(name);
      if (m) {
        const p = posOf(name) ?? ([obj.position.x, obj.position.y, obj.position.z] as [number, number, number]);
        torches.push({ col: Number(m[1]), row: Number(m[2]), position: p });
        continue;
      }
      const f = TORCH_FLAME_RE.exec(name);
      if (f) {
        const p = posOf(name);
        if (p) torchFlames[`${f[1]}_${f[2]}`] = p;
      }
    }
    if (torches.length === 0) {
      const fallback = torchCells()[0] ?? ALTAR;
      resolve("Torch_*", fallback);
    }

    torches.sort((a, b) => a.row - b.row || a.col - b.col);
    return { altar, spawn, lectern, lives, flames, torches, torchFlames, missing };
  }, [scene]);
}

export function Level({ onReady }: { onReady: (m: Markers) => void }) {
  const gltf = useGLTF(GLB_URL) as unknown as { scene: THREE.Group };
  const { camera } = useThree();
  // Clone: useGLTF caches the scene, so mutating it would leak across mounts.
  const scene = useMemo(() => gltf.scene.clone(true), [gltf.scene]);
  const markers = useMarkers(scene);

  useEffect(() => {
    unskew(scene);
    hideEnemyNodes(scene);
    applyLook(scene);
    onReady(markers);
  }, [markers, onReady, scene]);

  useEffect(() => {
    // Dev-only handles for debugging the loaded level from the console (and
    // for the browser tests): the level group, its scene, the camera, and the
    // resolved markers the rest of the game reads.
    if (import.meta.env.DEV) {
      const dbg = globalThis as unknown as {
        __dungeon?: THREE.Group;
        __dungeonScene?: THREE.Scene;
        __dungeonCamera?: THREE.Camera;
        __dungeonMarkers?: Markers;
      };
      dbg.__dungeon = scene;
      dbg.__dungeonScene = scene.parent as THREE.Scene;
      dbg.__dungeonCamera = camera;
      dbg.__dungeonMarkers = markers;
    }
  }, [camera, scene, markers]);

  return <primitive object={scene} />;
}

useGLTF.preload(GLB_URL);