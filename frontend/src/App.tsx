import { Component, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, ChromaticAberration, EffectComposer, N8AO, Noise, Vignette } from "@react-three/postprocessing";
import { BlendFunction } from "postprocessing";
import * as THREE from "three";

import { DIFFICULTIES, useGame, type Difficulty, type EnemyInstance } from "./game/useGame";
import {
  PRESETS,
  SHADOW_MAP_TYPE,
  detectQuality,
  loadQuality,
  resolveTier,
  saveQuality,
  tierHasShadows,
  type QualitySetting,
  type QualityTier,
  type SystemProfile,
} from "./game/graphics";
import { FpsGuard, type FpsSample } from "./game/FpsGuard";
import { DEFEAT_LINGER_MS } from "./game/useGame";
import { Level, type Markers } from "./world/Level";
import { chebyshev, orcTitleForCell, stepToward } from "./world/enemySpawn";
import { Player } from "./world/Player";
import { Lights, usePrefersReducedMotion } from "./world/Lights";
import { ENGAGE_RANGE, LECTERN_RANGE, Orc } from "./world/Orc";

/** How long the defeat line and its environment beat stay up before fading. */
const DEFEAT_TEXT_MS = DEFEAT_LINGER_MS;
import { DialogueSlab } from "./world/DialogueSlab";
import { DungeonEnvironment } from "./world/DungeonEnvironment";
import { SPAWN, SPAWN_YAW, cellToWorld, worldToCell, type Cell } from "./world/map";
import {
  playSample,
  playSfx,
  playWelcomeSequence,
  setMusicIntensity,
  subscribeSound,
  toggleMuted,
  unlock,
  warmSamples,
} from "./audio/sound";
import { Hud } from "./ui/Hud";
import { MapOverlay, Minimap, type MapPlayer } from "./ui/Minimap";
import { EnemyDialogue } from "./ui/EnemyDialogue";
import { EndScreen } from "./ui/EndScreen";
import { PauseMenu, WELCOME_TEXT } from "./ui/PauseMenu";
import { SetupScreen } from "./ui/SetupScreen";

/** Face east, down the row-1 corridor, rather than straight at the north wall. */

export interface Proximity {
  enemyId: string | null;
  enemyDistance: number;
  enemyWorld: [number, number, number] | null;
  lecternDistance: number;
}

const EMPTY_PROXIMITY: Proximity = {
  enemyId: null,
  enemyDistance: Infinity,
  enemyWorld: null,
  lecternDistance: Infinity,
};

/** Catches a GLB load failure and offers a retry instead of a blank canvas. */
class GLBErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };

  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[dungeon] level failed to load", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="screen" data-testid="glb-error">
          <h1>The level failed to load</h1>
          <p className="error">{this.state.error}</p>
          <button type="button" className="primary" onClick={() => this.setState({ error: null })}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function Effects({ reduced, quality }: { reduced: boolean; quality: QualityTier }) {
  // Fringing is easily overdone: full 0.0009 painted rainbow edges on every
  // bloomed torch flame, which reads as a defect rather than a lens. Half keeps
  // the lens feel without the bands.
  const aberration = useMemo(() => new THREE.Vector2(0.00035, 0.00035), []);
  const q = PRESETS[quality];

  // Low tier draws no composer at all: the scene is already dark, so the
  // effects are the first thing to go when frames are tight.
  if (quality === "low") return null;

  // EffectComposer only accepts element children, so the disabled passes are
  // filtered out of an array rather than left as `false` in the JSX.
  const effects: JSX.Element[] = [];
  // Filled once the N8AO effect mounts: its render method is wrapped so the
  // sceneNormal uniform always points at our normal target (see below).
  const n8aoRef = useRef<any>(null);
    if (q.ao) {
      // Contact darkening on top of the AO baked into the meshes' vertex colours:
      // this catches the small, moving stuff the bake cannot. Kept tight and
      // gentle - a wide, strong SSAO pass on top of baked AO is what makes
      // occlusion look like it slides across the stone as you move.
      // postprocessing 2.16.3's N8AO only consumes real normals from its
      // half-res depth-downsample pass (N8AOPostPass reads texture[1]); at
      // full resolution sceneNormal stays null and N8AO rebuilds normals from
      // depth with texel fetches, which makes the occlusion crawl across
      // surfaces as the camera moves. renderNormalTarget below feeds N8AO a
      // full-resolution world-normal buffer so the AO stays locked to the
      // geometry instead of swimming.
      effects.push(
        <N8AO
          ref={n8aoRef}
          key="ao"
          aoRadius={reduced ? q.aoRadius * 0.7 : q.aoRadius}
          distanceFalloff={1}
          intensity={reduced ? q.aoIntensity * 0.8 : q.aoIntensity}
          quality={reduced ? "low" : q.aoQuality}
          color="#0a0714"
          halfRes={reduced || q.aoHalfRes}
        />,
      );
    }
    if (q.bloom) {
      effects.push(
        <Bloom
          key="bloom"
          intensity={reduced ? Math.min(q.bloomIntensity, 0.3) : q.bloomIntensity}
          // Threshold above the torchlight specular range so unlit sconce
          // glints stay matte; only flame cores and the altar crystal bloom.
          luminanceThreshold={0.85}
          luminanceSmoothing={0.22}
          mipmapBlur
          radius={0.32}
        />,
      );
    }
  if (q.chromaticAberration) {
    effects.push(
      <ChromaticAberration
        key="ca"
        blendFunction={BlendFunction.NORMAL}
        offset={aberration}
        radialModulation={false}
        modulationOffset={0}
      />,
    );
  }
  if (q.filmGrain) {
    effects.push(
      <Noise
        key="grain"
        premultiply
        blendFunction={BlendFunction.OVERLAY}
        opacity={reduced ? 0.03 : 0.055}
      />,
    );
  }
  if (q.vignette) {
    effects.push(
      <Vignette key="vignette" eskil={false} offset={0.22} darkness={reduced ? 0.6 : 1.05} />,
    );
  }

  // ------------------------------------------------------------------ normals --

  // World-space normal render target fed to N8AO every frame. The library's
  // N8AO only consumes real normals from its half-res depth-downsample pass
  // (texture[1] of DepthDownSample); at full resolution sceneNormal stays
  // null and N8AO rebuilds normals from depth with texel fetches, which makes
  // occlusion crawl across surfaces as the camera moves. We render our own
  // full-resolution normal buffer and re-inject it into N8AO's render pass
  // after the effect mounts (its render resets the uniform to null).
  const normalTarget = useMemo(() => {
    const rt = new THREE.WebGLRenderTarget(1, 1, {
      type: THREE.HalfFloatType,
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
      depthBuffer: false,
      stencilBuffer: false,
    });
    rt.texture.name = "kdNormalTarget";
    return rt;
  }, []);

  const normalMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: [
          "varying vec3 vWorldNormal;",
          "void main() {",
          "  vWorldNormal = normalize(normalMatrix * normal);",
          "  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);",
          "}",
        ].join("\n"),
        fragmentShader: [
          "varying vec3 vWorldNormal;",
          "void main() {",
          "  gl_FragColor = vec4(vWorldNormal, 1.0);",
          "}",
        ].join("\n"),
      }),
    [],
  );

  const tempSize = useRef(new THREE.Vector2());
  const { gl, scene, camera } = useThree();

  // Render world-space normals once per frame (no-op when AO is off).
  useFrame(() => {
    if (!q.ao || !n8aoRef.current) return;
    const size = tempSize.current;
    gl.getSize(size);
    if (size.x !== normalTarget.width || size.y !== normalTarget.height) {
      normalTarget.setSize(size.x, size.y);
    }
    const override = scene.overrideMaterial;
    scene.overrideMaterial = normalMaterial;
    gl.setRenderTarget(normalTarget);
    gl.render(scene, camera);
    gl.setRenderTarget(null);
    scene.overrideMaterial = override;
  });

  useEffect(() => {
    const pass = n8aoRef.current;
    if (!pass || pass.__kdNormalInjected) return;
    pass.__kdNormalInjected = true;
    const base = pass.render.bind(pass);
    pass.render = (
      renderer: any,
      inputBuffer: any,
      outputBuffer: any,
      delta: any,
      active?: boolean,
    ) => {
      pass.effectShaderQuad.material.uniforms["sceneNormal"].value = normalTarget.texture;
      return base(renderer, inputBuffer, outputBuffer, delta, active);
    };
  }, [n8aoRef]);

  return (
    // enableNormalPass stays off: the built-in normal pass only covers the
    // library's half-res path, and N8AO here is fed normals directly through
    // renderNormalTarget instead.
    <EffectComposer enableNormalPass={false} multisampling={quality === "ultra" ? 4 : 0}>
      {effects}
    </EffectComposer>
  );
}

/** Tracks the player against orcs/lectern every frame; writes to a ref (no re-render). */
function ProximityTracker({
  orcs,
  markers,
  frozen,
  out,
}: {
  orcs: EnemyInstance[];
  markers: Markers | null;
  frozen: boolean;
  out: React.MutableRefObject<Proximity>;
}) {
  const { camera } = useThree();

  useFrame(() => {
    if (frozen || !markers) {
      out.current = EMPTY_PROXIMITY;
      return;
    }

    let bestId: string | null = null;
    let bestDist = Infinity;
    let bestWorld: [number, number, number] | null = null;

    for (const o of orcs) {
      if (o.status !== "alive") continue;
      const w = cellToWorld(o.cell);
      const d = Math.hypot(camera.position.x - w[0], camera.position.z - w[2]);
      if (d < bestDist) {
        bestDist = d;
        bestId = o.id;
        bestWorld = w;
      }
    }

    out.current = {
      enemyId: bestId,
      enemyDistance: bestDist,
      enemyWorld: bestWorld,
      lecternDistance: Math.hypot(camera.position.x - markers.lectern[0], camera.position.z - markers.lectern[2]),
    };
  });

  return null;
}

/** Publishes the player's cell and yaw into a ref for the DOM minimap. */
function CellTracker({ frozen, out }: { frozen: boolean; out: React.MutableRefObject<MapPlayer> }) {
  const { camera } = useThree();
  const last = useRef("");

  useFrame(() => {
    if (frozen) return;
    // worldToCell knows about CELL (2 m); doing the divide here by hand is how
    // the marker drifted off the player's true cell.
    const { col, row } = worldToCell(camera.position.x, camera.position.z);
    const yaw = camera.rotation.y;
    const key = `${col},${row}`;
    if (key === last.current && Math.abs(yaw - out.current.yaw) < 0.12) return;
    last.current = key;
    out.current = { col, row, yaw };
  });

  return null;
}

/** Projects the active orc's head height into screen space each frame. */
function SlabAnchor({
  orcs,
  activeId,
  frozen,
  onChange,
}: {
  orcs: EnemyInstance[];
  activeId: string | null;
  frozen: boolean;
  onChange: (v: { pos: [number, number, number] | null; screen: { x: number; y: number } | null }) => void;
}) {
  const { camera, size } = useThree();
  const vec = useMemo(() => new THREE.Vector3(), []);
  const out = useRef({ pos: null as [number, number, number] | null, screen: null as { x: number; y: number } | null });

  useFrame(() => {
    if (frozen || !activeId) {
      if (out.current.pos !== null) {
        out.current = { pos: null, screen: null };
        onChange(out.current);
      }
      return;
    }
    const orc = orcs.find((o) => o.id === activeId);
    if (!orc) return;
    const [x, , z] = cellToWorld(orc.cell);
    vec.set(x, 1.75, z);
    vec.project(camera);
    const next = {
      pos: [x, 1.75, z] as [number, number, number],
      screen: {
        x: ((vec.x + 1) / 2) * size.width,
        y: ((1 - vec.y) / 2) * size.height,
      },
    };
    // Only re-render when it moves meaningfully.
    const prev = out.current.screen;
    if (!prev || Math.abs(prev.x - next.screen.x) > 0.5 || Math.abs(prev.y - next.screen.y) > 0.5) {
      out.current = next;
      onChange(next);
    }
  });

  return null;
}

function Scene({
  orcs,
  activeEnemyId,
  markers,
  onMarkers,
  proximityRef,
  slabRef,
  playerStart,
  frozen,
  reduced,
  onSlab,
  weaponSalt,
  dead,
  playerMapRef,
  quality,
  onFps,
}: {
  orcs: EnemyInstance[];
  activeEnemyId: string | null;
  markers: Markers | null;
  onMarkers: (m: Markers) => void;
  proximityRef: React.MutableRefObject<Proximity>;
  slabRef: React.MutableRefObject<[number, number, number] | null>;
  playerStart: [number, number, number];
  frozen: boolean;
  reduced: boolean;
  onSlab: (v: { pos: [number, number, number] | null; screen: { x: number; y: number } | null }) => void;
  weaponSalt: number;
  dead: boolean;
  playerMapRef: React.MutableRefObject<MapPlayer>;
  quality: QualityTier;
  onFps: (s: FpsSample) => void;
}) {
// Orcs whose defeat dissolve has finished are dropped from the scene entirely
// (they stay in game state so "beat them all" checks still see them).
const visibleOrcs = useMemo(() => orcs.filter((o) => !o.gone), [orcs]);

const blockers = useMemo(
  () =>
    visibleOrcs
      .filter((o) => o.status === "alive")
      .map((o) => {
        const [bx, , bz] = cellToWorld(o.cell);
        return { x: bx, z: bz };
      }),
  [visibleOrcs],
);

  return (
    <>
      <DungeonEnvironment intensity={PRESETS[quality].envIntensity} />
      <Level onReady={onMarkers} />
      {markers && <Lights markers={markers} quality={PRESETS[quality]} />}
      <Player
        start={playerStart}
        yaw={SPAWN_YAW}
        locked={frozen}
        blockers={blockers}
        dead={dead}
        resetKey={weaponSalt}
      />
      {visibleOrcs.map((o) => (
        <Orc
          key={o.id}
          cell={o.cell}
          id={o.id}
          active={o.id === activeEnemyId}
          mood={o.mood}
          eventTick={o.eventTick}
          weaponSalt={weaponSalt}
          reducedMotion={reduced}
          defeated={o.status === "defeated"}
          frozen={frozen}
          quality={quality}
        />
      ))}
      <ProximityTracker orcs={visibleOrcs} markers={markers} frozen={frozen} out={proximityRef} />
      <CellTracker frozen={frozen} out={playerMapRef} />
      <SlabAnchor orcs={visibleOrcs} activeId={activeEnemyId} frozen={frozen} onChange={onSlab} />
      <DialogueSlab anchorRef={slabRef} height={0.95} reducedMotion={reduced} />
      <Effects reduced={reduced} quality={quality} />
      <FpsGuard
        targetFps={PRESETS[quality].targetFps}
        baseDpr={PRESETS[quality].dpr}
        minScale={quality === "ultra" ? 0.7 : 0.6}
        onSample={onFps}
      />
    </>
  );
}

export default function App() {
  const game = useGame({});
  const {
    state,
    engage,
    submit,
    requestHint,
    retreat,
    begin,
    startRun,
    useSuperPower,
    clearNotice,
    moveOrcs,
    reinforceWave,
    showNotice,
  } = game;

  const [markers, setMarkers] = useState<Markers | null>(null);
  const [paused, setPaused] = useState(false);
  const [prompt, setPrompt] = useState<{ text: string } | null>(null);
  const [slab, setSlab] = useState<{ pos: [number, number, number] | null; screen: { x: number; y: number } | null }>({
    pos: null,
    screen: null,
  });
  const [introVisible, setIntroVisible] = useState(false);
  // "blur" while the setup form is up, "clear" while the reveal transition
  // plays, null once the dungeon is fully live.
  const [veil, setVeil] = useState<"blur" | "clear" | null>("blur");
  const [mapOpen, setMapOpen] = useState(false);
  /** I: strip every overlay for a clean screenshot. */
  const [uiHidden, setUiHidden] = useState(false);
  /** F: FPS readout in the corner. */
  const [showFps, setShowFps] = useState(false);

  // Graphics: first run asks the machine what it can handle, after that the
  // player pins a tier (or stays on auto and lets the FPS guard trim).
  const [profile] = useState<SystemProfile>(() => detectQuality());
  const [setting, setSetting] = useState<QualitySetting>(() => loadQuality() ?? "auto");
  const quality: QualityTier = useMemo(() => resolveTier(setting, profile), [setting, profile]);
  const preset = PRESETS[quality];
  const [fps, setFps] = useState<FpsSample | null>(null);
  const onFps = useCallback((s: FpsSample) => setFps(s), []);
  const changeSetting = useCallback((next: QualitySetting) => {
    setSetting(next);
    saveQuality(next);
  }, []);

  const proximityRef = useRef<Proximity>(EMPTY_PROXIMITY);
  const slabRef = useRef<[number, number, number] | null>(null);
  const playerMapRef = useRef<MapPlayer>({ col: SPAWN.col, row: SPAWN.row, yaw: SPAWN_YAW });
  const canvasWrap = useRef<HTMLDivElement>(null);
  const reduced = usePrefersReducedMotion();

  // Everything outside active play is frozen: the setup tableau, loading,
  // dialogue, pause, and the death screen.
  const frozen = state.phase !== "playing" || paused;
  const dead = state.phase === "over" && state.endReason === "lost";

  // The defeat line ("Grukk cowers and dissolves.") and the short environment beat
  // each hold for 3 s, then the CSS fade-out takes over. `clearNotice` is a
  // stable dispatch wrapper - depending on the whole `game` object here re-armed
  // the timers on every render, so a notice could outlive itself.
  useEffect(() => {
    if (state.verdict) {
      const id = window.setTimeout(() => clearNotice(), DEFEAT_TEXT_MS);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [state.verdict, clearNotice]);

  useEffect(() => {
    if (!state.notice) return undefined;
    const id = window.setTimeout(() => clearNotice(), DEFEAT_TEXT_MS);
    return () => window.clearTimeout(id);
  }, [state.notice, clearNotice]);

  // The opening narration is a fixed script and a *welcome* only - it must never
  // replay when phase returns to "playing" after a question. Keyed on the session
  // so it fires exactly once per run.
  const introShown = useRef<string | null>(null);
  useEffect(() => {
    if (state.phase !== "playing") return;
    if (state.sessionId && introShown.current === state.sessionId) return;
    if (state.sessionId) introShown.current = state.sessionId;
    setIntroVisible(true);
    // Failsafe in case the welcome clip never loads.
    const id = window.setTimeout(() => setIntroVisible(false), 60000);
    return () => window.clearTimeout(id);
  }, [state.phase, state.sessionId]);

  const lockPointer = useCallback(() => {
    if (document.pointerLockElement) return;
    canvasWrap.current?.querySelector("canvas")?.requestPointerLock?.();
  }, []);

  // The setup veil: blurred over the frozen dungeon until the run begins, then
  // a one-way reveal transition into live play.
  useEffect(() => {
    if (state.phase === "setup") {
      setVeil("blur");
      return;
    }
    setVeil((v) => (v === "blur" ? "clear" : v));
  }, [state.phase]);

  useEffect(() => {
    if (veil !== "clear") return undefined;
    const id = window.setTimeout(() => setVeil(null), 1500);
    return () => window.clearTimeout(id);
  }, [veil]);

  // Entering the dungeon is a user gesture: this is where audio is allowed to
  // start, and where we claim pointer lock so the player can look as the blur lifts.
  const handleBegin = useCallback(
    (name: string, difficulty: Difficulty) => {
      unlock();
      playSfx("click");
      lockPointer();
      // The welcome clip owns the mix; the score fades back in after it ends,
      // and the on-screen narration leaves with the clip.
      void playWelcomeSequence().then(() => setIntroVisible(false));
      // Decode the combat clips while the veil is still up: otherwise the first
      // orc interaction stalls on a fetch + decode in mid-dialogue.
      void warmSamples();
      void begin(name, difficulty);
    },
    [begin, lockPointer],
  );

  // ---- sound -------------------------------------------------------------
  const [muted, setMutedState] = useState(() => false);
  useEffect(() => subscribeSound(setMutedState), []);

  // one-shot cues from game events
  const lastVerdict = useRef<string | null>(null);
  const [hitTick, setHitTick] = useState(0);
  useEffect(() => {
    const v = state.verdict;
    if (!v || v.text === lastVerdict.current) return;
    lastVerdict.current = v.text;
    playSfx(v.good ? "correct" : "wrong");
    // A wrong answer is the orc's swing: the recorded clip lands with it, and
    // the vignette flash makes the hit land without moving the camera.
    if (!v.good) {
      void playSample("orcAttack", 0.9);
      setHitTick((t) => t + 1);
    }
  }, [state.verdict]);

  // The recorded orc greeting when a dialogue opens.
  const lastEngaged = useRef<string | null>(null);
  useEffect(() => {
    const id = state.activeEnemyId;
    if (!id || id === lastEngaged.current) return;
    lastEngaged.current = id;
    void playSample("orcInteract", 0.85);
  }, [state.activeEnemyId]);

  const lastEndReason = useRef<string | null>(null);
  useEffect(() => {
    if (state.phase !== "over" || !state.endReason) return;
    if (state.endReason === lastEndReason.current) return;
    lastEndReason.current = state.endReason;
    playSfx(state.endReason === "lost" ? "death" : "victory");
  }, [state.phase, state.endReason]);

  useEffect(() => {
    if (state.revealed) playSfx("power");
  }, [state.revealed]);

  // duck the score while a question is on screen
  useEffect(() => {
    setMusicIntensity(state.phase === "dialogue" ? 0.35 : 1);
  }, [state.phase]);

  const onToggleSound = useCallback(() => {
    const next = toggleMuted();
    if (!next) playSfx("click");
  }, []);

  // Poll the proximity ref at 10Hz so the prompt doesn't re-render every frame.
  useEffect(() => {
    if (frozen) {
      setPrompt(null);
      return;
    }
    const tick = () => {
      const p = proximityRef.current;
      if (p.enemyId && p.enemyDistance <= ENGAGE_RANGE) {
        setPrompt({ text: "Press E to face the orc" });
      } else if (p.lecternDistance <= LECTERN_RANGE) {
        setPrompt({ text: "Press E to read the lectern" });
      } else {
        setPrompt(null);
      }
    };
    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
  }, [frozen]);

  const interact = useCallback(async () => {
    if (state.phase !== "playing" || paused) return;
    const p = proximityRef.current;
    if (p.enemyId && p.enemyDistance <= ENGAGE_RANGE) {
      await engage(p.enemyId);
      return;
    }
    if (p.lecternDistance <= LECTERN_RANGE) await requestHint();
  }, [engage, paused, requestHint, state.phase]);

  // ---- the dungeon is not passive: orcs stalk, and fresh ones pour in -------
  const live = useRef(state);
  live.current = state;

  /** Orcs within PURSUIT_RANGE cells of the player walk one step toward them. */
  const PURSUIT_MS = 700;
  const PURSUIT_RANGE = 6;

  // "Hunted" flashes once per run, not once per session.
  const hunted = useRef(false);
  useEffect(() => {
    hunted.current = false;
  }, [state.sessionId]);

  const pursuitTick = useCallback(() => {
    const s = live.current;
    if (s.won || s.gameOver) return;
    const pc: Cell = { col: playerMapRef.current.col, row: playerMapRef.current.row };
    const alive = s.orcs.filter((o) => o.status === "alive");

    if (alive.length === 0) {
      // Reinforcements only when the last dissolve has fully played out, so
      // nothing pops in over a fading body. Fresh orcs always land 6+ cells
      // away and their ids cannot collide with an existing one.
      if (s.orcs.length > 0 && s.orcs.every((o) => o.gone)) reinforceWave(pc);
      return;
    }

    const nearby = alive.filter((o) => {
      const d = chebyshev(o.cell, pc);
      return d <= PURSUIT_RANGE && d > 1;
    });
    if (nearby.length === 0) return;

    const occupied = new Set(alive.map((o) => `${o.cell.col},${o.cell.row}`));
    const moves: { id: string; cell: Cell }[] = [];
    let closest = Infinity;
    for (const o of nearby) {
      const step = stepToward(o.cell, pc, occupied);
      if (!step) continue;
      occupied.delete(`${o.cell.col},${o.cell.row}`);
      occupied.add(`${step.col},${step.row}`);
      moves.push({ id: o.id, cell: step });
      closest = Math.min(closest, chebyshev(step, pc));
    }
    if (moves.length === 0) return;
    moveOrcs(moves);
    // Heavy feet, close by: one footfall of marching per tick sells the hunt.
    if (closest <= 2) playSfx("footstep");
    if (!hunted.current) {
      hunted.current = true;
      showNotice("You are being hunted.");
    }
  }, [moveOrcs, reinforceWave, showNotice]);

  useEffect(() => {
    if (frozen) return undefined;
    const id = window.setInterval(pursuitTick, PURSUIT_MS);
    return () => window.clearInterval(id);
  }, [frozen, pursuitTick]);


  useEffect(() => {
    // The map is useful whenever a run exists - including mid-dialogue and on
    // the death screen - so it is never silently swallowed by a missing handler.
    const runActive = state.phase !== "setup" && state.phase !== "loading";
    const onKey = (e: KeyboardEvent) => {
      // Anything typed into a text field belongs to that field.
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

      if (e.code === "Escape") {
        if (mapOpen) {
          setMapOpen(false);
          return;
        }
        setPaused((prev) => !prev);
        return;
      }
      if (e.code === "KeyM" && runActive) {
        setMapOpen((v) => !v);
        return;
      }
      // P is the pause/settings menu. G used to open settings on its own; the
      // menu is now the single place with sound, graphics and the key list.
      if (e.code === "KeyP" && runActive) {
        setMapOpen(false);
        setPaused((prev) => !prev);
        return;
      }
      if (e.code === "KeyG" && runActive) {
        setMapOpen(false);
        setPaused((prev) => !prev);
        return;
      }
      // I clears the whole interface for screenshots; the minimap is part of it.
      if (e.code === "KeyI" && runActive) {
        setUiHidden((v) => !v);
        return;
      }
      if (e.code === "KeyF" && runActive) {
        setShowFps((v) => !v);
        return;
      }
      if (e.code === "KeyE") void interact();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [interact, mapOpen, paused, state.phase]);

  // Release pointer lock whenever movement is locked.
  useEffect(() => {
    if (frozen && document.pointerLockElement) document.exitPointerLock?.();
  }, [frozen]);

  const playerStart = useMemo<[number, number, number]>(() => markers?.spawn ?? cellToWorld(SPAWN), [markers]);

  const handleMarkers = useCallback((m: Markers) => setMarkers(m), []);
  const handleSlab = useCallback((v: { pos: [number, number, number] | null; screen: { x: number; y: number } | null }) => {
    slabRef.current = v.pos;
    setSlab(v);
  }, []);

  const newRun = useCallback(() => {
    setPaused(false);
    void startRun();
  }, [startRun]);

  const orcLabel = useMemo(() => {
    const orc = game.activeEnemy;
    return orc ? orcTitleForCell(orc.cell, state.runSeed) : "Orc";
  }, [game.activeEnemy, state.runSeed]);

  // ---- Setup screen sits OVER the live dungeon ---------------------------
  // The canvas renders behind the form, so the first thing you see is the
  // dungeon itself rather than a black void.
  const showSetup = state.phase === "setup";

  if (state.phase === "loading" && !markers && !showSetup) {
    return (
      <div className="screen" data-testid="loading">
        <div className="spinner" />
        <h1>The gates grind open…</h1>
        <p>{state.playerName ? `${state.playerName}, the dungeon is waiting.` : "The dungeon is waiting."}</p>
      </div>
    );
  }

  return (
    <div
      className="app"
      ref={canvasWrap}
      onClick={() => {
        // Never grab the cursor while a menu, form or dialogue owns it.
        if (state.phase === "playing" && !paused) lockPointer();
      }}
    >
      <GLBErrorBoundary>
        <Canvas
          dpr={preset.dpr}
          shadows={tierHasShadows(preset) ? "soft" : false}
          gl={{
            antialias: preset.antialias,
            powerPreference: quality === "low" ? "low-power" : "high-performance",
            stencil: false,
          }}
          camera={{ fov: 78, near: 0.05, far: 120, position: [playerStart[0], 1.6, playerStart[2]] }}
          onCreated={({ gl, camera, scene }) => {
            gl.setClearColor(new THREE.Color("#07050e"), 1);
            camera.position.set(playerStart[0], 1.6, playerStart[2]);
            // Three's default PCF is fine on its own; per-light bias and map
            // size are set in Lights.tsx, where the stability story lives.
            gl.shadowMap.type = SHADOW_MAP_TYPE[preset.shadowType] as THREE.ShadowMapType;
            gl.shadowMap.enabled = tierHasShadows(preset);
            scene.matrixWorldAutoUpdate = true;
          }}
        >
          <Suspense fallback={null}>
            <Scene
              orcs={state.orcs}
              activeEnemyId={state.activeEnemyId}
              markers={markers}
              onMarkers={handleMarkers}
              proximityRef={proximityRef}
              slabRef={slabRef}
              playerStart={playerStart}
              frozen={frozen}
              reduced={reduced}
              onSlab={handleSlab}
              weaponSalt={state.runSeed}
              dead={dead}
              playerMapRef={playerMapRef}
              quality={quality}
              onFps={onFps}
            />
          </Suspense>
        </Canvas>
      </GLBErrorBoundary>

      {/* Blurred setup tableau -> clear dungeon. Pointer-events stay off so the
          form above it and the canvas below it both keep working. */}
      {veil && (
        <div
          className={veil === "clear" ? "veil clear" : "veil"}
          data-testid={`veil-${veil}`}
          aria-hidden
        />
      )}

      <div className="crosshair" />

      {introVisible && !uiHidden && (
        <div className="intro" data-testid="intro">
          {WELCOME_TEXT.map((line) => (
            <p key={line.slice(0, 24)}>{line}</p>
          ))}
        </div>
      )}

      {/* The HUD belongs to the run, not to the setup form. */}
      {!showSetup && (
        <Hud
          playerName={state.playerName}
          health={state.health}
          maxHealth={state.maxHealth}
          powerUses={state.powerUses}
          points={state.points}
          level={state.level}
          winPoints={game.winPoints}
          prompt={prompt}
          notice={state.notice}
          verdict={state.verdict}
          hidden={uiHidden}
        />
      )}

      {showFps && !uiHidden && (
        <div className="fps-readout" data-testid="fps-overlay">
          {fps && fps.fps > 0 ? `${fps.fps} FPS · ${preset.label}` : `… · ${preset.label}`}
          {fps?.scaled ? ` · ${Math.round(fps.scale * 100)}%` : ""}
        </div>
      )}

      {state.phase === "dialogue" && (
        <EnemyDialogue
          question={state.question}
          loading={state.engaging}
          hint={state.hint}
          hinting={state.hinting}
          submitting={state.submitting}
          powering={state.powering}
          revealed={state.revealed}
          canUseSuperPower={game.canUseSuperPower}
          health={state.health}
          anchor={slab.screen}
          orcName={orcLabel}
          onSubmit={(a) => void submit(a)}
          onHint={() => void requestHint()}
          onSuperPower={() => void useSuperPower()}
          onRetreat={retreat}
        />
      )}

      {showSetup && <SetupScreen onBegin={handleBegin} />}

      {/* Run map: corner widget during play, fullscreen on demand. */}
      {!showSetup && !uiHidden && state.phase !== "over" && (
        <Minimap playerRef={playerMapRef} orcs={state.orcs} onOpen={() => setMapOpen(true)} />
      )}
      {mapOpen && !showSetup && (
        <MapOverlay
          playerRef={playerMapRef}
          orcs={state.orcs}
          onClose={() => setMapOpen(false)}
          reduced={reduced}
        />
      )}

      {/* Death: the screen floods red as the camera hits the floor. */}
      {dead && <div className="death-overlay" data-testid="death-overlay" />}

      {/* Wrong answer: the screen takes the hit, camera stays put. Re-keyed so
          a second hit restarts the animation. */}
      {hitTick > 0 && state.phase === "playing" && (
        <div key={hitTick} className="hit-flash" data-testid="hit-flash" />
      )}

      {state.phase === "over" && state.endReason && <EndScreen state={state} onRestart={newRun} />}

      {paused && (
        <PauseMenu
          onResume={() => setPaused(false)}
          onRestart={newRun}
          onQuit={() => setPaused(false)}
          muted={muted}
          onToggleSound={onToggleSound}
          setting={setting}
          tier={quality}
          profile={profile}
          onSetting={changeSetting}
          fps={fps}
          showFps={showFps}
          onToggleFps={() => setShowFps((v) => !v)}
        />
      )}

      {state.phase === "playing" && !paused && (
        // Not a button: with the pointer locked the cursor is gone, so every
        // control is a shortcut. Clicking the canvas re-captures the pointer,
        // which the wrapper above already handles.
        <div className="lock-hint" aria-hidden>
          WASD move · Shift sprint · E interact · M map · P menu · I hide UI · F fps
        </div>
      )}

      {state.error && (
        <div className="screen" data-testid="start-error">
          <h1>The dungeon will not open</h1>
          <p className="error">{state.error}</p>
          <button type="button" className="primary" onClick={() => void startRun()}>
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

export { DIFFICULTIES };