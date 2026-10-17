import { useEffect, useState } from "react";
import { useGLTF, useProgress } from "@react-three/drei";

import { warmSamples } from "../audio/sound";
import { GLB_URL } from "./Level";
import { ORC_URL } from "./Orc";

/** A stalled fetch must not hold the player on the boot card forever. */
const BOOT_TIMEOUT_MS = 20000;

/**
 * Warms the level and orc models (and the recorded audio) before the setup
 * menu shows.
 *
 * The URLs are the ones `Level` and `Orc` will ask for, so by the time either
 * mounts its `useGLTF` call the resource is already in the loader cache - no
 * second fetch, no pop-in while the player is picking a difficulty. This runs
 * from outside the Canvas on purpose: drei's `useProgress` reads the global
 * `DefaultLoadingManager` and needs no React Three context.
 */
export function useAssetPreload() {
  const { active, loaded, total, errors, progress } = useProgress();
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    useGLTF.preload(GLB_URL);
    useGLTF.preload(ORC_URL);
    // Decoding the welcome clip now keeps the narration instant on entry.
    void warmSamples();
    const id = window.setTimeout(() => setTimedOut(true), BOOT_TIMEOUT_MS);
    return () => window.clearTimeout(id);
  }, []);

  // `total > 0` keeps the first frame (nothing registered yet) on the boot
  // card; `errors` covers a model that will never arrive.
  const done = errors.length > 0 || (total > 0 && !active && loaded === total);
  return { ready: done || timedOut, progress: Math.min(100, Math.round(progress)) };
}
