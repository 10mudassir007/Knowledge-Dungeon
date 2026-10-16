/**
 * Lighting, fog and atmosphere.
 *
 * Palette is keyed to the reference look: deep indigo ambient, a violet key at
 * the altar, cold blue-white practicals at the torches, and dense violet haze
 * so the dungeon reads as depth rather than flat darkness.
 *
 * Total point lights stay under 8 (4 torches + 1 altar + spares).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Vector3, type PointLight } from "three";
import type { Markers } from "./Level";
import { tierHasShadows, type QualityPreset } from "../game/graphics";

/** Hard ceiling on point lights: WebGL forward rendering pays for every one. */
export const MAX_POINT_LIGHTS = 12;

const FLICKER_HZ = [7.3, 11.7, 5.9, 13.1];
const TORCH_COLOR = "#9fb4ff";
/** Fallback only: modern levels read the flame position from the GLB. */
export const TORCH_HEIGHT = 1.55;
const ALTAR_COLOR = "#b98bff";
const ALTAR_INTENSITY = 44;

/**
 * Exponential fog density. The 41x31 grid is 82 x 62 m at 2 m per cell, so
 * 0.024 (visibility ~40 m) would swallow the whole level. 0.013 carries
 * ~75 m - long enough to see a corridor bending away, short enough that the
 * far halls stay black.
 */
const FOG_DENSITY = 0.013;
const FOG_DENSITY_REDUCED = 0.008;

/**
 * Choose `limit` torches to actually light.
 *
 * Two rules, in order:
 *  1. The nearest torch to the spawn, the lectern and the altar is always lit, so
 *     the places the player must go are never pitch black.
 *  2. The remaining slots are filled by farthest-point sampling, so the pools stay
 *     spread over a 41x31 level instead of clustering in one corner.
 */
function pickTorches<T extends { position: [number, number, number] }>(
  items: T[],
  limit: number,
  mustCover: readonly [number, number][],
): T[] {
  if (items.length <= limit) return items.slice();

  const chosen: T[] = [];
  const pool = items.slice();

  for (const [ax, az] of mustCover) {
    if (chosen.length >= limit) break;
    let bestIndex = 0;
    let bestDistance = Infinity;
    for (let i = 0; i < pool.length; i += 1) {
      const p = pool[i].position;
      const d = Math.hypot(p[0] - ax, p[2] - az);
      if (d < bestDistance) {
        bestDistance = d;
        bestIndex = i;
      }
    }
    if (!Number.isFinite(bestDistance)) break;
    chosen.push(pool[bestIndex]);
    pool.splice(bestIndex, 1);
  }

  while (chosen.length < limit && pool.length > 0) {
    let bestIndex = 0;
    let bestDistance = -1;
    for (let i = 0; i < pool.length; i += 1) {
      const p = pool[i].position;
      let nearest = Infinity;
      for (const c of chosen) {
        nearest = Math.min(nearest, Math.hypot(p[0] - c.position[0], p[2] - c.position[2]));
      }
      if (nearest > bestDistance) {
        bestDistance = nearest;
        bestIndex = i;
      }
    }
    chosen.push(pool[bestIndex]);
    pool.splice(bestIndex, 1);
  }
  return chosen;
}

/** Cheap deterministic flicker in [0,1]; no allocations. */
function flicker(t: number, i: number): number {
  const h = FLICKER_HZ[i % FLICKER_HZ.length];
  const a = Math.sin(t * h);
  const b = Math.sin(t * h * 2.37 + i) * 0.5;
  const c = Math.sin(t * h * 0.61 + i * 2.1) * 0.25;
  return 0.5 + 0.5 * (a * 0.6 + b * 0.3 + c * 0.2);
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

function TorchLight({
  position,
  index,
  reduced,
  quality,
  lightRef,
}: {
  position: [number, number, number];
  index: number;
  reduced: boolean;
  quality: QualityPreset;
  /** Registered with the shadow director, which decides who casts. */
  lightRef: (light: PointLight | null) => void;
}) {
  const base = quality.torchIntensity;
  const range = quality.torchRange;
  const self = useRef<PointLight | null>(null);

  useFrame(({ clock }) => {
    const light = self.current;
    if (!light) return;
    const n = flicker(clock.elapsedTime, index);
    light.intensity = reduced ? base : base * (0.62 + n * 0.7);
  });

  const register = (light: PointLight | null) => {
    self.current = light;
    lightRef(light);
  };

  return (
    <pointLight
      ref={register}
      position={position}
      color={TORCH_COLOR}
      intensity={base}
      distance={range}
      decay={2}
      castShadow={false}
      shadow-mapSize-width={quality.shadowMapSize}
      shadow-mapSize-height={quality.shadowMapSize}
      // Without a normal bias the shadow map's depth comparison crawls across
      // surfaces as the camera moves - the "shadows that follow you" artefact.
      shadow-normalBias={quality.shadowNormalBias}
      shadow-bias={quality.shadowBias}
      shadow-radius={quality.shadowRadius}
      shadow-camera-near={0.08}
      shadow-camera-far={range}
    />
  );
}

/**
 * Keeps the expensive shadow casters on the torches the player can see.
 *
 * Point-light shadows are cube maps - six depth renders per light per frame.
 * Casting from a fixed set of torches far away is money burned on nothing the
 * player can observe, so every half second the director picks the nearest
 * `shadowCasters` torches and switches those on. The choice only changes when
 * the *set* changes, so an equidistant pair never flickers.
 */
function ShadowDirector({
  lights,
  budget,
  enabled,
}: {
  lights: React.MutableRefObject<(PointLight | null)[]>;
  budget: number;
  enabled: boolean;
}) {
  const active = useRef<number[]>([]);
  const next = useRef(0);
  const scratch = useRef(new Vector3());

  const clear = () => {
    for (const i of active.current) {
      const l = lights.current[i];
      if (l) l.castShadow = false;
    }
    active.current = [];
  };

  useFrame(({ clock, camera }) => {
    if (!enabled) {
      if (active.current.length > 0) clear();
      return;
    }
    const t = clock.elapsedTime;
    if (t < next.current) return;
    next.current = t + 0.5;

    const ranked: { i: number; d: number }[] = [];
    for (let i = 0; i < lights.current.length; i += 1) {
      const l = lights.current[i];
      if (!l) continue;
      l.getWorldPosition(scratch.current);
      ranked.push({
        i,
        d: Math.hypot(scratch.current.x - camera.position.x, scratch.current.z - camera.position.z),
      });
    }
    ranked.sort((a, b) => a.d - b.d);
    const wanted = ranked
      .slice(0, budget)
      .map((r) => r.i)
      .sort((a, b) => a - b);
    const same =
      wanted.length === active.current.length &&
      wanted.every((v, idx) => v === active.current[idx]);
    if (same) return;

    for (const i of active.current) {
      if (!wanted.includes(i)) {
        const l = lights.current[i];
        if (l) l.castShadow = false;
      }
    }
    for (const i of wanted) {
      const l = lights.current[i];
      if (l) l.castShadow = true;
    }
    active.current = wanted;
  });

  return null;
}

export function Lights({ markers, quality }: { markers: Markers; quality: QualityPreset }) {
  const reduced = usePrefersReducedMotion();
  const torchBudget = Math.min(MAX_POINT_LIGHTS - 2, Math.max(1, quality.torchBudget));

  // Spawn, lectern and altar first, then spread whatever budget is left.
  const torches = useMemo(
    () =>
      pickTorches(markers.torches, torchBudget, [
        [markers.spawn[0], markers.spawn[2]],
        [markers.lectern[0], markers.lectern[2]],
        [markers.altar[0], markers.altar[2]],
      ]),
    [markers.torches, markers.spawn, markers.lectern, markers.altar, torchBudget],
  );

  // Live point-light handles; the shadow director ranks these by distance.
  const lightRefs = useRef<(PointLight | null)[]>([]);
  useEffect(() => {
    lightRefs.current.length = torches.length;
  }, [torches.length]);

  return (
    <>
      {/* Deep indigo fill - low, but the rock is dark so it needs some. */}
      <ambientLight intensity={quality.ambientIntensity} color="#3b2f6b" />
      {/* Cool sky / warm-violet ground bounce. */}
      <hemisphereLight args={["#5a4a9e", "#1a1024", quality.hemiIntensity]} />

      {torches.map((t, i) => {
        // The marker empty is at the cell centre; the fire is on the sconce.
        // Fall back to the old centre-plus-height guess for old assets.
        const flame = markers.torchFlames[`${t.col}_${t.row}`];
        const position: [number, number, number] = flame
          ? flame
          : [t.position[0], TORCH_HEIGHT, t.position[2]];
        return (
          <TorchLight
            key={`torch_${t.col}_${t.row}`}
            position={position}
            index={i}
            reduced={reduced}
            quality={quality}
            lightRef={(l) => {
              lightRefs.current[i] = l;
            }}
          />
        );
      })}

      <ShadowDirector
        lights={lightRefs}
        budget={quality.shadowCasters}
        enabled={tierHasShadows(quality)}
      />

      {/* Violet key at the altar - the focal point of the room. */}
      <pointLight
        position={[markers.altar[0], markers.altar[1] + 1.5, markers.altar[2]]}
        color={ALTAR_COLOR}
        intensity={reduced ? ALTAR_INTENSITY * 1.2 : ALTAR_INTENSITY}
        distance={16}
        decay={2}
      />

      <fogExp2
        attach="fog"
        args={["#120a22", (reduced ? FOG_DENSITY_REDUCED : FOG_DENSITY) / quality.fogScale]}
      />
    </>
  );
}