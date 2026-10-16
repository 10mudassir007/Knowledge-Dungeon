/**
 * Procedural surface materials, generated at runtime on a 2D canvas.
 *
 * The GLB ships flat-ish baked stone; these replace it with layered detail:
 * multi-octave value noise for grain, a worley layer for aggregate, formwork
 * banding for poured concrete, and a height-derived normal map.
 *
 * Walls are poured concrete: they carry a RUGNESS MAP whose dark patches are
 * slick, so they pick up specular reflection from the scene environment
 * (see DungeonEnvironment). Roughness varies per-texel rather than being a
 * single constant, which is what stops a reflection from looking like a decal.
 *
 * Colours are graded toward the deep indigo/violet of the reference look.
 * Nothing is downloaded - every pixel is computed here.
 */

import * as THREE from "three";

const SIZE = 512;

function hash2(x: number, y: number, seed: number): number {
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed, 2246822519);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

const smooth = (t: number) => t * t * (3 - 2 * t);

function valueNoise(x: number, y: number, seed: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const xf = smooth(x - xi);
  const yf = smooth(y - yi);
  const a = hash2(xi, yi, seed);
  const b = hash2(xi + 1, yi, seed);
  const c = hash2(xi, yi + 1, seed);
  const d = hash2(xi + 1, yi + 1, seed);
  return (a * (1 - xf) + b * xf) * (1 - yf) + (c * (1 - xf) + d * xf) * yf;
}

function fbm(x: number, y: number, freq: number, octaves: number, seed: number): number {
  let sum = 0;
  let amp = 1;
  let norm = 0;
  let f = freq;
  for (let o = 0; o < octaves; o += 1) {
    sum += amp * valueNoise(x * f, y * f, seed + o * 131);
    norm += amp;
    amp *= 0.5;
    f *= 2;
  }
  return sum / norm;
}

/** Worley F1/F2 over a jittered grid. Edge proximity: 0 on a boundary, 1 deep inside. */
function worley(x: number, y: number, seed: number): { f1: number; f2: number } {
  const cx = Math.floor(x);
  const cy = Math.floor(y);
  let f1 = 8;
  let f2 = 8;
  for (let dy = -1; dy <= 1; dy += 1) {
    for (let dx = -1; dx <= 1; dx += 1) {
      const gx = cx + dx;
      const gy = cy + dy;
      const px = gx + 0.5 + (hash2(gx, gy, seed) - 0.5) * 0.85;
      const py = gy + 0.5 + (hash2(gx, gy, seed + 77) - 0.5) * 0.85;
      const d = Math.hypot(x - px, y - py);
      if (d < f1) {
        f2 = f1;
        f1 = d;
      } else if (d < f2) {
        f2 = d;
      }
    }
  }
  return { f1, f2 };
}

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const smoothstep = (a: number, b: number, t: number) => {
  const x = clamp01((t - a) / (b - a));
  return x * x * (3 - 2 * x);
};

export type SurfaceVariant = "concrete" | "wall" | "floor" | "ceiling" | "trim";

interface RockOptions {
  /** Linear-ish base colour of the stone. */
  base: [number, number, number];
  /** Colour settled into the cracks / recesses. */
  dark: [number, number, number];
  /** Colour of the highlights catching the violet key light. */
  light: [number, number, number];
  seed: number;
  /** Worley cell density for the aggregate / masonry layer. */
  cells: number;
  normalScale: number;
  /** [slickest, driest] roughness written into the roughness map. */
  roughnessRange: [number, number];
  /** Strength of the horizontal formwork lift lines (0 = smooth). */
  banding: number;
  /** Multiplier on the environment reflection. */
  envMapIntensity: number;
  metalness: number;
  repeat: [number, number];
}

/** Builds the height field once and derives albedo, normal and roughness from it. */
function buildFields(o: RockOptions) {
  const n = SIZE * SIZE;
  const height = new Float32Array(n);
  const tone = new Float32Array(n);
  const gloss = new Float32Array(n);

  for (let py = 0; py < SIZE; py += 1) {
    for (let px = 0; px < SIZE; px += 1) {
      const i = py * SIZE + px;
      const u = px / SIZE;
      const v = py / SIZE;

      const grain = fbm(u, v, 9, 5, o.seed);
      const coarse = fbm(u, v, 3, 3, o.seed + 31);
      const { f1, f2 } = worley(u * o.cells, v * o.cells, o.seed + 97);
      // Edges between aggregate clusters: pits and chips in the poured surface.
      const chip = 1 - smoothstep(0.0, 0.09, f2 - f1);

      // Horizontal shuttering lifts every half texture-height.
      const bandPhase = Math.sin(v * Math.PI * 2 * 4 + fbm(u, v, 2, 2, o.seed + 5) * 1.4);
      const band = smoothstep(0.55, 1.0, Math.abs(bandPhase)) * o.banding;

      const h = grain * 0.45 + coarse * 0.3 - chip * 0.5 - band * 0.35;
      height[i] = clamp01(h * 0.5 + 0.5);
      tone[i] = clamp01(grain * 0.6 + coarse * 0.4);
      // Smooth, low-lying patches are polished by footfall and damp: they shine.
      gloss[i] = clamp01((coarse - 0.42) * 2.2 - chip * 0.8 - band * 0.6);
    }
  }
  return { height, tone, gloss };
}

function makeCanvas(data: Uint8ClampedArray): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;
  ctx.putImageData(new ImageData(data, SIZE, SIZE), 0, 0);
  return canvas;
}

function texture(canvas: HTMLCanvasElement, srgb: boolean, repeat: [number, number]) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeat[0], repeat[1]);
  tex.anisotropy = 8;
  tex.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  tex.needsUpdate = true;
  return tex;
}

const cache = new Map<string, THREE.MeshStandardMaterial>();

const PRESETS: Record<SurfaceVariant, RockOptions> = {
  // Poured concrete: grey-violet, fine aggregate, formwork bands, and a
  // roughness map whose slick patches reflect the torch and altar light.
  // Kept dark on purpose - the environment map is the only thing that lifts it,
  // and pushing envMapIntensity higher turns the whole level into blue card.
  concrete: {
    base: [0.072, 0.068, 0.088],
    dark: [0.022, 0.021, 0.032],
    light: [0.170, 0.166, 0.196],
    seed: 11,
    cells: 13,
    normalScale: 1.6,
    roughnessRange: [0.30, 0.92],
    banding: 0.55,
    envMapIntensity: 0.7,
    metalness: 0.03,
    repeat: [1, 1],
  },
  wall: {
    base: [0.155, 0.135, 0.215],
    dark: [0.045, 0.036, 0.082],
    light: [0.33, 0.30, 0.46],
    seed: 11,
    cells: 4,
    normalScale: 2.6,
    roughnessRange: [0.72, 0.98],
    banding: 0.0,
    envMapIntensity: 0.5,
    metalness: 0.02,
    repeat: [1, 1],
  },
  floor: {
    base: [0.225, 0.210, 0.290],
    dark: [0.070, 0.062, 0.110],
    light: [0.38, 0.37, 0.52],
    seed: 27,
    cells: 6,
    normalScale: 2.0,
    roughnessRange: [0.55, 0.95],
    banding: 0.0,
    envMapIntensity: 0.95,
    metalness: 0.03,
    repeat: [1, 1],
  },
  ceiling: {
    base: [0.165, 0.152, 0.225],
    dark: [0.048, 0.042, 0.085],
    light: [0.28, 0.27, 0.40],
    seed: 43,
    cells: 3,
    normalScale: 1.2,
    roughnessRange: [0.80, 1.0],
    banding: 0.0,
    envMapIntensity: 0.4,
    metalness: 0.02,
    repeat: [1, 1],
  },
  trim: {
    base: [0.19, 0.172, 0.265],
    dark: [0.04, 0.034, 0.075],
    light: [0.30, 0.28, 0.42],
    seed: 59,
    cells: 5,
    normalScale: 0.9,
    roughnessRange: [0.40, 0.86],
    banding: 0.0,
    envMapIntensity: 0.9,
    metalness: 0.05,
    repeat: [1, 1],
  },
};

/**
 * Returns a cached surface material. `variant` keeps concrete / floor / ceiling
 * visually distinct while sharing the same generator.
 */
export function rockMaterial(variant: SurfaceVariant): THREE.MeshStandardMaterial {
  const hit = cache.get(variant);
  if (hit) return hit;

  const o = PRESETS[variant];
  const { height, tone, gloss } = buildFields(o);

  // --- albedo ------------------------------------------------------------
  const albedo = new Uint8ClampedArray(SIZE * SIZE * 4);
  for (let i = 0; i < SIZE * SIZE; i += 1) {
    const h = height[i];
    const t = tone[i];
    const crack = smoothstep(0.62, 0.2, h);
    let r = mix(o.dark[0], o.light[0], t);
    let g = mix(o.dark[1], o.light[1], t);
    let b = mix(o.dark[2], o.light[2], t);
    r = mix(r, o.base[0] + 0.03 * (1 - t), 0.35);
    g = mix(g, o.base[1] + 0.03 * (1 - t), 0.35);
    b = mix(b, o.base[2] + 0.05 * (1 - t), 0.35);
    r = mix(r, o.dark[0], crack * 0.85);
    g = mix(g, o.dark[1], crack * 0.85);
    b = mix(b, o.dark[2] * 1.15, crack * 0.85);
    const j = i * 4;
    albedo[j] = Math.sqrt(clamp01(r)) * 255;
    albedo[j + 1] = Math.sqrt(clamp01(g)) * 255;
    albedo[j + 2] = Math.sqrt(clamp01(b)) * 255;
    albedo[j + 3] = 255;
  }

  // --- normal from the height gradient -----------------------------------
  const normal = new Uint8ClampedArray(SIZE * SIZE * 4);
  const at = (x: number, y: number) => height[((y + SIZE) % SIZE) * SIZE + ((x + SIZE) % SIZE)];
  for (let y = 0; y < SIZE; y += 1) {
    for (let x = 0; x < SIZE; x += 1) {
      const dx = (at(x + 1, y) - at(x - 1, y)) * o.normalScale;
      const dy = (at(x, y + 1) - at(x, y - 1)) * o.normalScale;
      const len = Math.hypot(-dx, -dy, 1);
      const j = (y * SIZE + x) * 4;
      normal[j] = ((-dx / len) * 0.5 + 0.5) * 255;
      normal[j + 1] = ((-dy / len) * 0.5 + 0.5) * 255;
      normal[j + 2] = (1 / len) * 0.5 * 255 + 127.5;
      normal[j + 3] = 255;
    }
  }

  // --- roughness: per-texel, so reflections break up naturally -----------
  const rough = new Uint8ClampedArray(SIZE * SIZE * 4);
  for (let i = 0; i < SIZE * SIZE; i += 1) {
    const [lo, hi] = o.roughnessRange;
    const r = clamp01(mix(hi, lo, gloss[i]));
    const j = i * 4;
    rough[j] = rough[j + 1] = rough[j + 2] = r * 255;
    rough[j + 3] = 255;
  }

  const mat = new THREE.MeshStandardMaterial({
    map: texture(makeCanvas(albedo), true, o.repeat),
    normalMap: texture(makeCanvas(normal), false, o.repeat),
    roughnessMap: texture(makeCanvas(rough), false, o.repeat),
    roughness: 1.0,
    metalness: o.metalness,
    envMapIntensity: o.envMapIntensity,
    dithering: true,
  });

  cache.set(variant, mat);
  return mat;
}

/** Recycle/cache guard for StrictMode double-mounts. */
export function disposeRockMaterials() {
  for (const mat of cache.values()) {
    mat.map?.dispose();
    mat.normalMap?.dispose();
    mat.roughnessMap?.dispose();
    mat.dispose();
  }
  cache.clear();
}