/**
 * FPS guard: measures real frame time and trims resolution to hold the tier's
 * target, so "high" stays around 40 FPS on a mid-range machine instead of
 * silently dropping to 20.
 *
 * Two knobs, in order of how invisible they are:
 *   1. render scale - the canvas is drawn smaller and stretched by the browser
 *   2. a step down   - only when scaling cannot recover the frame (and only
 *                     while the setting is "auto", never against a pinned tier)
 */

import { useEffect, useRef, useState } from "react";
import { useFrame, useThree } from "@react-three/fiber";

export interface FpsSample {
  fps: number;
  scale: number;
  /** True when the guard asked for a smaller canvas. */
  scaled: boolean;
}

interface Props {
  targetFps: number;
  /** Ceiling the guard may scale down to. */
  minScale?: number;
  /** The tier's own DPR cap; the guard scales within it, never past it. */
  baseDpr?: [number, number];
  onSample?: (s: FpsSample) => void;
  enabled?: boolean;
}

/**
 * Lives inside the Canvas: it needs the render loop to count frames.
 * Reports a smoothed FPS to the DOM (settings panel) and drives the canvas
 * pixel ratio through R3F's setDpr.
 */
export function FpsGuard({
  targetFps,
  minScale = 0.6,
  baseDpr = [1, 1.25],
  onSample,
  enabled = true,
}: Props) {
  const gl = useThree((s) => s.gl);
  const setDpr = useThree((s) => s.setDpr);
  const frames = useRef(0);
  const windowStart = useRef(0);
  const smoothed = useRef(targetFps);
  const scale = useRef(1);
  const holdUntil = useRef(0);
  const [current, setCurrent] = useState<number>(targetFps);

  // The tier's ceiling: the guard may only ever go below this.
  const cap = useRef(1);
  cap.current = Math.max(minScale, Math.min(window.devicePixelRatio || 1, baseDpr[1]));

  useEffect(() => {
    scale.current = 1;
    setDpr(cap.current);
    windowStart.current = performance.now();
  }, [setDpr]);

  useFrame(() => {
    if (!enabled) return;
    frames.current += 1;
    const now = performance.now();
    const elapsed = now - windowStart.current;
    if (elapsed < 1000) return;

    const fps = (frames.current * 1000) / elapsed;
    frames.current = 0;
    windowStart.current = now;
    // Smooth so a single stutter (a GC pause, a level load) does not move it.
    smoothed.current += (fps - smoothed.current) * 0.35;
    setCurrent(Math.round(smoothed.current));

    if (now < holdUntil.current) return;

    const target = targetFps;
    if (smoothed.current < target * 0.85 && scale.current > minScale) {
      scale.current = Math.max(minScale, scale.current - 0.15);
      setDpr(cap.current * scale.current);
      holdUntil.current = now + 2500;
    } else if (smoothed.current > target * 1.25 && scale.current < 1) {
      scale.current = Math.min(1, scale.current + 0.1);
      setDpr(cap.current * scale.current);
      holdUntil.current = now + 4000;
    }

    onSample?.({ fps: Math.round(smoothed.current), scale: scale.current, scaled: scale.current < 0.99 });
  });

  // Keep the gl informated about the pixel ratio the guard just changed.
  useEffect(() => {
    gl.setPixelRatio(gl.getPixelRatio());
  }, [gl, current]);

  return null;
}

/** DOM-side hook: polls the value FpsGuard reports, for the settings panel. */
export function useFps(sample: FpsSample | null): FpsSample {
  const [value, setValue] = useState<FpsSample>({ fps: 0, scale: 1, scaled: false });
  useEffect(() => {
    if (!sample) return;
    setValue(sample);
  }, [sample]);
  return value;
}