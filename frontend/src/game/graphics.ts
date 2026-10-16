/**
 * Graphics quality: presets, first-run detection, and an FPS guard.
 *
 * Tiers differ along independent axes, not just one resolution slider, so the
 * jump from Low to Ultra is actually visible:
 *
 *   axis          low        medium       high            ultra
 *   render scale  0.5-0.7    0.75-1       1-1.5           1-2
 *   anti-alias    off        off          MSAA            MSAA
 *   shadows       off        hard, 2 cast  PCF soft, 4     PCF soft, 6 @2048
 *   screen AO     off        half-res     full res        full res, tightest
 *   draw distance short     near full    full            longer
 *   torch lights  3          5            7               10
 *
 * Shadow *stability* matters as much as shadow count: a shadow that crawls as
 * the camera moves is worse than no shadow, which is why the presets carry
 * explicit bias/normalBias/radius rather than leaving WebGL's defaults.
 *
 * On first run the tier is guessed from the GPU string, CPU thread count and
 * device memory, and the player can override it from the settings panel.
 */

export const QUALITY_TIERS = ["low", "medium", "high", "ultra"] as const;
export type QualityTier = (typeof QUALITY_TIERS)[number];
/** "auto" keeps following the machine; picking a tier pins it. */
export type QualitySetting = QualityTier | "auto";

/** WebGLRenderer shadow filtering, cheapest first. */
export type ShadowType = "off" | "basic" | "pcf" | "pcfsoft";

export interface QualityPreset {
  id: QualityTier;
  label: string;
  blurb: string;
  /** Device pixel ratio cap for the canvas. */
  dpr: [number, number];
  antialias: boolean;
  shadowType: ShadowType;
  shadowMapSize: number;
  /** How many torches cast real shadows (0 = none). */
  shadowCasters: number;
  /** Negative bias slides the sample depth; too small = acne, too large = peter-panning. */
  shadowBias: number;
  /**
   * Offset along the surface normal. This is the one that stops shadows
   * *swimming* across a surface as the camera moves, so it is never 0.
   */
  shadowNormalBias: number;
  /** PCF spread in texels. 0 = hard edge. */
  shadowRadius: number;
  /** Screen-space ambient occlusion. */
  ao: boolean;
  aoQuality: "low" | "medium" | "high";
  aoRadius: number;
  aoIntensity: number;
  /** Render AO at half resolution (cheap, blocky). */
  aoHalfRes: boolean;
  /**
   * N8AO needs view-space normals to work. Without the normal pass it has to
   * guess, and the result slides around as the camera moves.
   */
  normalPass: boolean;
  bloom: boolean;
  bloomIntensity: number;
  chromaticAberration: boolean;
  filmGrain: boolean;
  vignette: boolean;
  /** Extra torches lit at once (beyond the altar). */
  torchBudget: number;
  /** Per-torch point light intensity. */
  torchIntensity: number;
  /** How far a torch's light carries, metres. */
  torchRange: number;
  ambientIntensity: number;
  hemiIntensity: number;
  /** Environment map intensity, i.e. how wet/metallic things read. */
  envIntensity: number;
  anisotropy: number;
  /** Fog density multiplier. Below 1 thins the haze for a longer draw distance. */
  fogScale: number;
  /** Target frame rate the FPS guard aims for. */
  targetFps: number;
}

export const PRESETS: Record<QualityTier, QualityPreset> = {
  low: {
    id: "low",
    label: "Low",
    blurb: "No effects, low resolution, short draw distance.",
    dpr: [0.5, 0.7],
    antialias: false,
    shadowType: "off",
    shadowMapSize: 512,
    shadowCasters: 0,
    shadowBias: 0,
    shadowNormalBias: 0,
    shadowRadius: 1,
    ao: false,
    aoQuality: "low",
    aoRadius: 0.5,
    aoIntensity: 1,
    aoHalfRes: true,
    normalPass: false,
    bloom: false,
    bloomIntensity: 0,
    chromaticAberration: false,
    filmGrain: false,
    vignette: false,
    torchBudget: 5,
    torchIntensity: 34,
    torchRange: 19,
    ambientIntensity: 0.95,
    hemiIntensity: 1.0,
    envIntensity: 1.0,
    anisotropy: 1,
    fogScale: 1.0,
    targetFps: 30,
  },
  medium: {
    id: "medium",
    label: "Medium",
    blurb: "Hard shadows and cheap AO. No anti-aliasing.",
    dpr: [0.75, 1],
    antialias: false,
    shadowType: "basic",
    shadowMapSize: 512,
    shadowCasters: 2,
    shadowBias: -0.004,
    shadowNormalBias: 0.05,
    shadowRadius: 1,
    ao: true,
    aoQuality: "low",
    aoRadius: 0.7,
    aoIntensity: 1,
    aoHalfRes: true,
    normalPass: true,
    bloom: true,
    bloomIntensity: 0.4,
    chromaticAberration: false,
    filmGrain: true,
    vignette: true,
    torchBudget: 6,
    torchIntensity: 30,
    torchRange: 17,
    ambientIntensity: 1.0,
    hemiIntensity: 1.05,
    envIntensity: 1.05,
    anisotropy: 2,
    fogScale: 1.05,
    targetFps: 45,
  },
  high: {
    id: "high",
    label: "High",
    blurb: "Anti-aliased, soft shadows, full AO. The 40 FPS target.",
    dpr: [1, 1.25],
    antialias: true,
    shadowType: "pcfsoft",
    shadowMapSize: 1024,
    shadowCasters: 3,
    shadowBias: -0.0022,
    shadowNormalBias: 0.035,
    shadowRadius: 2,
    ao: true,
    aoQuality: "medium",
    aoRadius: 0.55,
    aoIntensity: 1.25,
    aoHalfRes: false,
    normalPass: true,
    bloom: true,
    bloomIntensity: 0.55,
    chromaticAberration: true,
    filmGrain: true,
    vignette: true,
    torchBudget: 7,
    torchIntensity: 26,
    torchRange: 18,
    ambientIntensity: 0.75,
    hemiIntensity: 0.88,
    envIntensity: 1.05,
    anisotropy: 8,
    fogScale: 1,
    targetFps: 40,
  },
  ultra: {
    id: "ultra",
    label: "Ultra",
    blurb: "Soft shadows, tight AO, long draw distance. Needs a strong GPU.",
    dpr: [1, 1.5],
    antialias: true,
    shadowType: "pcfsoft",
    // Point-light shadows are cube maps: every extra light at 2K meant six
    // more 2048x2048 depth renders per frame, and six casters x six faces is
    // what made Ultra unplayable. The nearest few torches cast; 1024 is plenty
    // for flame light anyway, and the caster set follows the player.
    shadowMapSize: 1024,
    shadowCasters: 4,
    shadowBias: -0.0015,
    shadowNormalBias: 0.025,
    shadowRadius: 3,
    ao: true,
    aoQuality: "high",
    aoRadius: 0.45,
    aoIntensity: 1.5,
    aoHalfRes: false,
    normalPass: true,
    bloom: true,
    bloomIntensity: 0.62,
    chromaticAberration: true,
    filmGrain: true,
    vignette: true,
    torchBudget: 8,
    torchIntensity: 27,
    torchRange: 21,
    ambientIntensity: 0.8,
    hemiIntensity: 0.95,
    envIntensity: 1.25,
    anisotropy: 16,
    fogScale: 1.18,
    targetFps: 60,
  },
};

/** Maps a tier onto three's shadow filter constants. */
export const SHADOW_MAP_TYPE: Record<ShadowType, number> = {
  off: 0,      // THREE.BasicShadowMap
  basic: 1,    // THREE.PCFShadowMap
  pcf: 1,      // THREE.PCFShadowMap
  pcfsoft: 2,  // THREE.PCFSoftShadowMap
};

/** Presets where any light casts shadows at all. */
export const tierHasShadows = (q: QualityPreset): boolean =>
  q.shadowType !== "off" && q.shadowCasters > 0;

// ---------------------------------------------------------------- detection --

export interface SystemProfile {
  gpu: string;
  cores: number;
  memoryGb: number;
  screen: string;
  dpr: number;
  mobile: boolean;
  /** Tier the detector settled on. */
  suggested: QualityTier;
  /** Why it picked that tier, for the settings panel. */
  reason: string;
}

const GPU_HINTS: { pattern: RegExp; tier: QualityTier; note: string }[] = [
  { pattern: /rtx\s*(40|50)\d{2}|radeon\s*rx\s*(7|9)\d{3}|apple\s*m[1-9]|arc\s*a/i, tier: "ultra", note: "flagship GPU" },
  { pattern: /rtx\s*(20|30)\d{2}|radeon\s*rx\s*[56]0\d{2}|geforce\s*(gtx\s*)?(16|20)\d{2}/i, tier: "high", note: "modern gaming GPU" },
  { pattern: /rtx|radeon\s*rx|geforce\s*(gtx\s*)?\d{3}|quadro|arc\s*b/i, tier: "medium", note: "older or discrete GPU" },
  // Integrated parts report without a model number; they are the reason the
  // detector exists, so name them rather than falling through to the default.
  { pattern: /amd\s+radeon(\(tm\))?\s*(tm\s*)?graphics|amd\s+radeon\s+integrated/i, tier: "medium", note: "integrated AMD graphics" },
  { pattern: /intel|uhd|iris|hd graphics|apple gpu|mali|adreno|powervr/i, tier: "low", note: "integrated graphics" },
  { pattern: /swiftshader|llvmpipe|software|microsoft basic/i, tier: "low", note: "software renderer" },
];

/** Reads the unmasked GPU string; falls back to the plain renderer string. */
function readGpu(): string {
  try {
    const canvas = document.createElement("canvas");
    const gl = (canvas.getContext("webgl2") ??
      canvas.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return "unknown";
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    const raw = ext
      ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
      : gl.getParameter(gl.RENDERER);
    const lose = gl.getExtension("WEBGL_lose_context");
    lose?.loseContext();
    return String(raw ?? "unknown");
  } catch {
    return "unknown";
  }
}

/**
 * Guess a tier from the machine. Deliberately conservative: it is better to
 * start one notch low (and let the user raise it) than to start at 20 FPS.
 */
export function detectQuality(): SystemProfile {
  const gpu = readGpu();
  const cores = navigator.hardwareConcurrency ?? 4;
  const memoryGb = (navigator as unknown as { deviceMemory?: number }).deviceMemory ?? 4;
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const screen = `${window.screen?.width ?? 0}x${window.screen?.height ?? 0}`;
  const mobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent ?? "");

  let tier: QualityTier = "medium";
  let reason = "no strong signal, assuming a mid-range machine";
  for (const hint of GPU_HINTS) {
    if (hint.pattern.test(gpu)) {
      tier = hint.tier;
      reason = `${hint.note} (${gpu.slice(0, 48)})`;
      break;
    }
  }

  // CPU / memory can only push the tier down, never up: a fast GPU behind a
  // weak CPU still stutters on 12 torches and a big level.
  if (cores <= 2 || memoryGb <= 2) {
    tier = "low";
    reason = `${reason}; ${cores} cores / ${memoryGb} GB RAM`;
  } else if (cores <= 4 && tier === "ultra") {
    tier = "high";
    reason = `${reason}; only ${cores} cores`;
  }
  if (mobile) {
    tier = tier === "ultra" ? "high" : "low";
    reason = `${reason}; mobile device`;
  }

  return { gpu, cores, memoryGb, screen, dpr, mobile, suggested: tier, reason };
}

// ------------------------------------------------------------- persistence --

const KEY = "kd.quality";

export function loadQuality(): QualitySetting | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw === "auto") return "auto";
    if (raw !== null && (QUALITY_TIERS as readonly string[]).includes(raw)) return raw as QualitySetting;
    return null;
  } catch {
    return null;
  }
}

export function saveQuality(setting: QualitySetting): void {
  try {
    localStorage.setItem(KEY, setting);
  } catch {
    /* private mode */
  }
}

/** Resolve "auto" against a detection result. */
export function resolveTier(setting: QualitySetting, profile: SystemProfile): QualityTier {
  return setting === "auto" ? profile.suggested : setting;
}