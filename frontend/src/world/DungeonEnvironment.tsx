/**
 * Scene environment used purely for image-based reflections.
 *
 * The concrete walls need something to reflect: a dielectric with a low
 * roughness only shows a sheen when there is an environment to sample. We
 * cannot fetch an HDR (no network dependency), so we paint a small equirect
 * canvas - indigo sky, violet altar bloom, cold torch bands near the horizon -
 * and run it through PMREM to get the roughness-prefiltered mip chain.
 *
 * Cost is one 256x128 canvas and one PMREM bake, once, cached.
 */

import { useEffect } from "react";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";

const W = 256;
const H = 128;

let envTexture: THREE.Texture | null = null;
let envRT: THREE.WebGLRenderTarget | null = null;

/** Paints the equirectangular source once and shares it between mounts. */
function buildSource(): THREE.Texture {
  if (envTexture) return envTexture;

  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;

  // Vertical gradient: near-black floor haze -> deep indigo -> faint violet zenith.
  const sky = ctx.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0.0, "#2a1c52"); // zenith
  sky.addColorStop(0.42, "#150e2c");
  sky.addColorStop(0.55, "#0d0819"); // horizon band
  sky.addColorStop(1.0, "#050308"); // nadir
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, W, H);

  // Cold torch glows scattered along the horizon so reflections have highlights
  // to catch rather than a flat wash.
  const glow = (cx: number, cy: number, r: number, color: string, alpha: number) => {
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0, color);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalAlpha = alpha;
    ctx.fillStyle = g;
    ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
    ctx.globalAlpha = 1;
  };

  for (let i = 0; i < 7; i += 1) {
    const x = (i / 7) * W + 12;
    glow(x, H * 0.58, 24, "#c3d0ff", 0.34);
  }
  // The altar's violet key, the strongest reflector in the scene.
  glow(W * 0.22, H * 0.46, 50, "#c9a4ff", 0.42);
  glow(W * 0.74, H * 0.5, 34, "#8f74ff", 0.2);

  const tex = new THREE.CanvasTexture(canvas);
  tex.mapping = THREE.EquirectangularReflectionMapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  envTexture = tex;
  return tex;
}

export function DungeonEnvironment({ intensity = 0.55 }: { intensity?: number }) {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);

  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    pmrem.compileEquirectangularShader();
    const src = buildSource();
    if (envRT) envRT.dispose();
    envRT = pmrem.fromEquirectangular(src);
    scene.environment = envRT.texture;
    scene.environmentIntensity = intensity;
    pmrem.dispose();
    return () => {
      scene.environment = null;
    };
  }, [gl, scene, intensity]);

  return null;
}