/**
 * Orcs: the dungeon's inhabitants.
 *
 * The body, rig, weapons and the attack animation all come from orc.glb, built
 * in Blender (see dungeon/orc.glb). This component drives it:
 *
 *  - AnimationMixer plays the authored "OrcAttack" clip, so the swing has real
 *    weight: anticipation, a fast strike, a forward lunge and a slow recover.
 *  - The orc always turns to face the player.
 *  - Exactly one of the six baked weapons is shown, chosen per cell so it stays
 *    the same for the whole run.
 *
 * Orientation note: orc.glb is exported Y-up per the glTF spec, which turns
 * Blender's (X, Y-up, Z-forward) into (X, Z, -Y). The orc therefore arrives
 * lying face-down and rotated -90 degrees about X, and the wrapper below puts it
 * back upright facing -Z.
 *
 * Animation states
 *   idle    - the rest pose, with a slow breathing sway
 *   attack  - the baked attack clip (wrong answer)
 *   defeat  - sink to a knee and dissolve (correct answer)
 */

import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { QualityTier } from "../game/graphics";
import * as SkeletonUtils from "three/examples/jsm/utils/SkeletonUtils.js";
import { cellToWorld, type Cell } from "./map";
import { mulberry32 } from "./enemySpawn";

export const ENGAGE_RANGE = 2.0;
export const LECTERN_RANGE = 1.8;

export const ORC_URL = "/assets/orc.glb";
/** The orc is authored 2.3 m tall and 1.37 m wide; corridors are 1 m, so scale down. */
export const ORC_SCALE = 0.75;
const ATTACK_CLIP = "OrcAttack";
const DEFEAT_FADE = 1.8;

export type OrcMood = "idle" | "attack" | "defeat";

export type WeaponKind = "axe" | "sword" | "mace" | "halberd" | "spear" | "warhammer";

const WEAPONS: WeaponKind[] = ["axe", "sword", "mace", "halberd", "spear", "warhammer"];

/** Stable per-cell weapon, so it does not change between renders. */
export function weaponForCell(cell: Cell, salt: number): WeaponKind {
  const rand = mulberry32(cell.col * 73856093 + cell.row * 19349663 + salt);
  return WEAPONS[Math.floor(rand() * WEAPONS.length) % WEAPONS.length];
}

const weaponNodeName = (kind: WeaponKind) =>
  `Weapon_${kind.charAt(0).toUpperCase()}${kind.slice(1)}`;

export interface OrcProps {
  cell: Cell;
  id: string;
  active: boolean;
  mood: OrcMood;
  /** Bumped by useGame when an answer comes back, to restart the animation. */
  eventTick: number;
  weaponSalt: number;
  reducedMotion: boolean;
  defeated: boolean;
  /** Frozen while the setup screen is up: no sway, no animation, no turning. */
  frozen?: boolean;
  /**
   * Graphics tier. With a dozen orcs in the dungeon, every extra point light
   * and shadow caster costs real frames, so the cheap tiers drop them.
   */
  quality?: QualityTier;
}

/** Clone the materials so fading one defeated orc does not fade the others. */
function isolateMaterials(root: THREE.Object3D, castShadow: boolean): THREE.Material[] {
  const out: THREE.Material[] = [];
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    const src = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const cloned = src.map((m) => {
      const c = m.clone();
      // Transparent from the very first render, never flipped at defeat time.
      // `transparent` selects the OPAQUE shader variant, so toggling it when a
      // dissolve starts recompiles every material on the orc mid-frame - the
      // "slight lag, like stuck" on every kill. Paying for the transparent
      // variant up front costs one program compiled while the level loads.
      c.transparent = true;
      out.push(c);
      return c;
    });
    mesh.material = Array.isArray(mesh.material) ? cloned : cloned[0];
    mesh.castShadow = castShadow;
  });
  return out;
}

/**
 * How far an orc's face/fill lights reach. Beyond this the lights are switched
 * off entirely: a forward renderer pays for every light in the shader, and a
 * dozen orcs each carrying two lights is what made Ultra crawl.
 */
const ORC_LIGHT_RANGE = 16;

export function Orc({ cell, active, mood, eventTick, weaponSalt, reducedMotion, defeated, frozen = false, quality = "high" }: OrcProps) {
  const group = useRef<THREE.Group>(null);
  const sway = useRef<THREE.Group>(null);
  const faceLight = useRef<THREE.PointLight>(null);
  const fillLight = useRef<THREE.PointLight>(null);
  const lastTick = useRef(eventTick);
  const t = useRef(0);
  const { camera } = useThree();

  const gltf = useGLTF(ORC_URL) as unknown as {
    scene: THREE.Group;
    animations: THREE.AnimationClip[];
  };

  const model = useMemo(() => SkeletonUtils.clone(gltf.scene), [gltf.scene]);

  const mixer = useMemo(() => new THREE.AnimationMixer(model), [model]);
  const clip = useMemo(
    () => gltf.animations.find((a) => a.name === ATTACK_CLIP) ?? gltf.animations[0],
    [gltf.animations],
  );
  const action = useMemo(
    () => (clip ? mixer.clipAction(clip) : null),
    [mixer, clip],
  );

  const [x, , z] = useMemo(() => cellToWorld(cell), [cell]);
  const weaponKind = useMemo(() => weaponForCell(cell, weaponSalt), [cell, weaponSalt]);

  // Shadow casting is only worth its cost on the top two tiers.
const castShadow = quality === "high" || quality === "ultra";
const materials = useMemo(() => isolateMaterials(model, castShadow), [model, castShadow]);

  // Show only this orc's weapon; all six are baked into the file.
  useEffect(() => {
    const wanted = weaponNodeName(weaponKind);
    model.traverse((obj: THREE.Object3D) => {
      if (obj.name.startsWith("Weapon_")) obj.visible = obj.name === wanted;
    });
  }, [model, weaponKind]);

  // Drive the clip from `mood`, restarting it whenever the event ticks.
  useEffect(() => {
    if (!action) return;
    if (mood === "attack") {
      action.reset();
      action.setLoop(THREE.LoopOnce, 1);
      action.clampWhenFinished = false;
      action.play();
    } else if (action.isRunning()) {
      action.stop();
      action.reset();
    }
  }, [action, mood, eventTick]);

  useEffect(() => () => {
    mixer.stopAllAction();
    mixer.uncacheRoot(model);
  }, [mixer, model]);

  useFrame(({ clock }, delta) => {
    const g = group.current;
    const s = sway.current;
    if (!g || !s) return;
    // Frozen behind the setup screen: hold the rest pose exactly as authored.
    if (frozen) return;

    if (eventTick !== lastTick.current) {
      lastTick.current = eventTick;
      t.current = 0;
    }
    const now = clock.elapsedTime;
    t.current += Math.min(delta, 0.05);
    mixer.update(delta);

    // Always turn to the player - they should never be able to sneak behind it.
    const toPlayerX = camera.position.x - x;
    const toPlayerZ = camera.position.z - z;
    const facing = Math.atan2(-toPlayerX, -toPlayerZ);
    g.rotation.y = facing;

    let sink = 0;
    let fade = 1;
    if (mood === "defeat" || defeated) {
      const p = clamp01(t.current / DEFEAT_FADE);
      sink = p * 0.42;
      fade = 1 - smoothstep(0.35, 1, p);
      g.visible = fade > 0.01;
    }

    g.position.set(x, -sink, z);

    // Lights follow the viewer, not the orc: only orcs near the camera carry
    // point lights at all, so a dozen of them never add 22 live lights to
    // every material in the level. Intensity fades out before the cut so the
    // toggle is invisible.
    const lightDist = Math.hypot(toPlayerX, toPlayerZ);
    const lightScale = clamp01(1 - (lightDist - (ORC_LIGHT_RANGE - 6)) / 6);
    const fl = faceLight.current;
    if (fl) {
      fl.visible = lightScale > 0.01;
      fl.intensity = (active ? 9 : 5) * lightScale;
    }
    const fill = fillLight.current;
    if (fill) {
      fill.visible = lightScale > 0.01;
      fill.intensity = 2.2 * lightScale;
    }

    // Breathing keeps the idle pose alive without bobbing the camera.
    if (!reducedMotion) {
      s.position.y = Math.sin(now * 1.5 + x * 0.7) * 0.022;
      s.rotation.z = Math.sin(now * 0.9 + z * 0.3) * 0.012;
    }

    // Opacity and depthWrite only: both are uniforms/state, so animating them
    // never touches the shader. `transparent` was set true at clone time.
    const fading = fade < 1;
    for (const mat of materials) {
      mat.opacity = fade;
      mat.depthWrite = !fading;
    }

    // Glowing eyes: the horror read. Brighter when it is the active orc.
    for (const mat of materials) {
      const m = mat as THREE.MeshStandardMaterial;
      if (m.name === "emissive_crystal") {
        m.emissiveIntensity = reducedMotion
          ? active ? 9 : 4
          : active ? 10 + Math.sin(now * 5.5) * 3.5 : 4 + Math.sin(now * 2.1) * 1.2;
      }
    }
  });

  return (
    <group ref={group} position={[x, 0, z]}>
      {/* Key light on the orc's face. Without this it is a black silhouette in
          a black corridor - the dungeon is deliberately too dark to light it.
          useFrame switches it off past ORC_LIGHT_RANGE. */}
      <pointLight
        ref={faceLight}
        position={[0, 1.45, -0.9]}
        color={active ? "#c39cff" : "#8fa2e8"}
        intensity={active ? 9 : 5}
        distance={5.5}
        decay={2}
      />
      {/* Low fill so the legs and weapon read against the floor. With a dozen
          orcs in the dungeon this is the first light to go on the cheap tiers. */}
      {quality !== "low" && (
        <pointLight
          ref={fillLight}
          position={[0.7, 0.7, -1.1]}
          color="#5b6bb0"
          intensity={2.2}
          distance={3.6}
          decay={2}
        />
      )}
      <group ref={sway}>
        <primitive object={model} scale={ORC_SCALE} rotation={[Math.PI / 2, 0, 0]} />
      </group>
    </group>
  );
}

useGLTF.preload(ORC_URL);

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smoothstep = (a: number, b: number, t: number) => {
  const x = clamp01((t - a) / (b - a));
  return x * x * (3 - 2 * x);
};