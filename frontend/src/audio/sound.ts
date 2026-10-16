/**
 * Sound: synthesised effects plus an ambient score, all from the Web Audio API,
 * with three recorded clips layered on top (orc interaction, orc attack, the
 * opening welcome).
 *
 * The synthesised palette keeps the bundle small and lets the dungeon colours
 * (cold stone, violet arcane light, ember torches) drive the timbre. The three
 * clips are voice/creature audio that has to sound authored, so they ship as
 * mp3s and are decoded once on first use.
 *
 * Browsers only allow audio after a user gesture, so nothing starts until the
 * player clicks "Enter the dungeon"; `unlock()` is called from that click.
 *
 * The mute toggle is exposed through `subscribe()` and persisted in
 * localStorage, so the choice survives a reload.
 */

export type Sfx =
  | "footstep"
  | "sprint"
  | "water"
  | "click"
  | "engage"
  | "correct"
  | "wrong"
  | "power"
  | "defeat"
  | "death"
  | "victory";

/** Recorded clips under /audio. Decoded lazily, cached forever after. */
export type Sample = "welcome" | "orcInteract" | "orcAttack";

const SAMPLE_URLS: Record<Sample, string> = {
  welcome: "/audio/welcome.mp3",
  orcInteract: "/audio/orc-interact.mp3",
  orcAttack: "/audio/orc-attack.mp3",
};

/** Gap after the welcome clip before the score fades back in. */
export const MUSIC_RESUME_DELAY = 3;
/** Seconds the score takes to fade back up. */
export const MUSIC_FADE_IN = 2.5;

type Listener = (muted: boolean) => void;

const STORAGE_KEY = "kd.sound.muted";

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let sfxBus: GainNode | null = null;
let musicBus: GainNode | null = null;
let noiseBuffer: AudioBuffer | null = null;
let muted = false;
let started = false;
let musicTimer: number | null = null;
let musicStep = 0;
const listeners = new Set<Listener>();

try {
  muted = localStorage.getItem(STORAGE_KEY) === "1";
} catch {
  muted = false;
}

function notify(): void {
  for (const fn of listeners) fn(muted);
}

export function subscribeSound(fn: Listener): () => void {
  listeners.add(fn);
  fn(muted);
  return () => listeners.delete(fn);
}

export function isMuted(): boolean {
  return muted;
}

export function setMuted(next: boolean): void {
  muted = next;
  try {
    localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
  } catch {
    /* private mode - keep the in-memory value */
  }
  if (master && ctx) {
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.setTargetAtTime(next ? 0 : 0.9, ctx.currentTime, 0.08);
  }
  notify();
}

export function toggleMuted(): boolean {
  setMuted(!muted);
  return muted;
}

function noise(): AudioBuffer {
  const c = ensureContext();
  if (noiseBuffer) return noiseBuffer;
  const len = Math.floor(c.sampleRate * 2);
  const buf = c.createBuffer(1, len, c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < len; i += 1) data[i] = Math.random() * 2 - 1;
  noiseBuffer = buf;
  return buf;
}

function ensureContext(): AudioContext {
  if (ctx) return ctx;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  ctx = new Ctor();
  master = ctx.createGain();
  master.gain.value = muted ? 0 : 0.9;
  master.connect(ctx.destination);

  sfxBus = ctx.createGain();
  sfxBus.gain.value = 0.9;
  sfxBus.connect(master);

  musicBus = ctx.createGain();
  musicBus.gain.value = MUSIC_LEVEL;
  musicBus.connect(master);
  return ctx;
}

/** Call from a user gesture (the Enter click). */
export function unlock(): void {
  const c = ensureContext();
  if (c.state === "suspended") void c.resume();
  if (!started) {
    started = true;
    startMusic();
  }
}

interface ToneOpts {
  freq: number;
  type?: OscillatorType;
  dur?: number;
  gain?: number;
  sweepTo?: number;
  delay?: number;
  attack?: number;
  bus?: GainNode | null;
  detune?: number;
}

function tone(o: ToneOpts): void {
  const c = ensureContext();
  const t0 = c.currentTime + (o.delay ?? 0);
  const dur = o.dur ?? 0.25;
  const osc = c.createOscillator();
  osc.type = o.type ?? "sine";
  osc.frequency.setValueAtTime(o.freq, t0);
  if (o.sweepTo) osc.frequency.exponentialRampToValueAtTime(Math.max(20, o.sweepTo), t0 + dur);
  if (o.detune) osc.detune.setValueAtTime(o.detune, t0);
  const g = c.createGain();
  const peak = o.gain ?? 0.2;
  const atk = o.attack ?? 0.008;
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(peak, t0 + atk);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g).connect(o.bus ?? (sfxBus as GainNode));
  osc.start(t0);
  osc.stop(t0 + dur + 0.05);
}

interface NoiseOpts {
  dur?: number;
  gain?: number;
  freq?: number;
  q?: number;
  type?: BiquadFilterType;
  sweepTo?: number;
  delay?: number;
  bus?: GainNode | null;
}

function noiseBurst(o: NoiseOpts): void {
  const c = ensureContext();
  const t0 = c.currentTime + (o.delay ?? 0);
  const dur = o.dur ?? 0.2;
  const src = c.createBufferSource();
  src.buffer = noise();
  src.loop = true;
  const filter = c.createBiquadFilter();
  filter.type = o.type ?? "bandpass";
  filter.frequency.setValueAtTime(o.freq ?? 900, t0);
  if (o.sweepTo) filter.frequency.exponentialRampToValueAtTime(Math.max(60, o.sweepTo), t0 + dur);
  filter.Q.value = o.q ?? 1.1;
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(o.gain ?? 0.15, t0 + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  src.connect(filter).connect(g).connect(o.bus ?? (sfxBus as GainNode));
  src.start(t0);
  src.stop(t0 + dur + 0.05);
}

export function playSfx(name: Sfx): void {
  if (muted || !started) return;
  const c = ensureContext();
  if (c.state === "suspended") return;

  switch (name) {
    case "footstep":
      noiseBurst({ dur: 0.11, gain: 0.075, freq: 420 + Math.random() * 90, q: 1.5 });
      tone({ freq: 78 + Math.random() * 12, type: "sine", dur: 0.09, gain: 0.05 });
      break;
    case "sprint":
      noiseBurst({ dur: 0.15, gain: 0.1, freq: 700 + Math.random() * 140, q: 1.8, sweepTo: 260 });
      tone({ freq: 120, type: "triangle", dur: 0.12, gain: 0.07 });
      break;
    case "water":
      // splash: bright noise burst with a falling filter plus a droplet
      noiseBurst({ dur: 0.26, gain: 0.11, freq: 2600, q: 0.8, sweepTo: 420 });
      tone({ freq: 620, type: "sine", dur: 0.16, gain: 0.05, sweepTo: 220, delay: 0.02 });
      break;
    case "click":
      tone({ freq: 620, type: "square", dur: 0.05, gain: 0.045 });
      break;
    case "engage":
      // an orc noticing you: low growl with a growl-formant sweep
      tone({ freq: 96, type: "sawtooth", dur: 0.5, gain: 0.11, sweepTo: 74, attack: 0.06 });
      noiseBurst({ dur: 0.45, gain: 0.06, freq: 240, q: 2.4, type: "lowpass" });
      break;
    case "correct":
      // bright ascending triad, bell-like
      [523.25, 659.25, 783.99].forEach((f, i) =>
        tone({ freq: f, type: "triangle", dur: 0.5, gain: 0.09, delay: i * 0.07 }));
      noiseBurst({ dur: 0.5, gain: 0.03, freq: 3200, q: 0.7, type: "highpass" });
      break;
    case "wrong":
      tone({ freq: 196, type: "sawtooth", dur: 0.42, gain: 0.11, sweepTo: 82 });
      tone({ freq: 185, type: "square", dur: 0.42, gain: 0.05, detune: -18, sweepTo: 78 });
      noiseBurst({ dur: 0.3, gain: 0.07, freq: 380, q: 1.2 });
      break;
    case "power":
      // arcane reveal: rising shimmer
      noiseBurst({ dur: 0.8, gain: 0.06, freq: 600, q: 0.9, sweepTo: 5200, type: "highpass" });
      [392, 523.25, 659.25, 880].forEach((f, i) =>
        tone({ freq: f, type: "sine", dur: 0.7, gain: 0.07, delay: i * 0.05 }));
      break;
    case "defeat":
      noiseBurst({ dur: 0.7, gain: 0.09, freq: 900, q: 0.6, sweepTo: 120 });
      tone({ freq: 160, type: "triangle", dur: 0.6, gain: 0.07, sweepTo: 60 });
      break;
    case "death":
      tone({ freq: 140, type: "sawtooth", dur: 2.2, gain: 0.13, sweepTo: 38, attack: 0.05 });
      tone({ freq: 93, type: "sine", dur: 2.4, gain: 0.1, sweepTo: 30, attack: 0.08 });
      noiseBurst({ dur: 1.6, gain: 0.06, freq: 500, q: 0.8, sweepTo: 90 });
      break;
    case "victory":
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) =>
        tone({ freq: f, type: "triangle", dur: 1.0, gain: 0.09, delay: i * 0.12 }));
      break;
  }
}

// ------------------------------------------------------------------- music --
/**
 * A slow modal loop: a drone in D minor, a plucked-ish ostinato and a distant
 * bell every few bars. Scheduled a bar at a time so it stays in time even if
 * the tab throttles.
 */
const DRONE_HZ = 73.42;                       // D2
const LEAD = [293.66, 311.13, 349.23, 440.0, 349.23, 311.13]; // D minor-ish figures

function musicBar(): void {
  const c = ensureContext();
  const now = c.currentTime;
  const bar = 4.0;

  // drone: two detuned saws through a low-pass, swelling slowly
  for (const detune of [-7, 6]) {
    const osc = c.createOscillator();
    osc.type = "sawtooth";
    osc.frequency.value = DRONE_HZ;
    osc.detune.value = detune;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.setValueAtTime(220, now);
    lp.frequency.linearRampToValueAtTime(420, now + bar * 0.5);
    lp.frequency.linearRampToValueAtTime(200, now + bar);
    const g = c.createGain();
    g.gain.setValueAtTime(0.0001, now);
    g.gain.linearRampToValueAtTime(0.16, now + bar * 0.35);
    g.gain.linearRampToValueAtTime(0.0001, now + bar);
    osc.connect(lp).connect(g).connect(musicBus as GainNode);
    osc.start(now);
    osc.stop(now + bar + 0.1);
  }

  // wind/air bed
  noiseBurst({ dur: bar, gain: 0.035, freq: 340, q: 0.6, type: "bandpass", bus: musicBus });

  // ostinato: two notes per bar
  const step = musicStep % LEAD.length;
  tone({ freq: LEAD[step], type: "triangle", dur: 0.9, gain: 0.07, bus: musicBus, attack: 0.05 });
  tone({ freq: LEAD[(step + 2) % LEAD.length] * 2, type: "sine", dur: 0.7, gain: 0.04, bus: musicBus, delay: 1.9, attack: 0.06 });

  // distant bell every 4th bar
  if (musicStep % 8 === 0) {
    tone({ freq: 146.83, type: "sine", dur: 2.6, gain: 0.09, bus: musicBus, attack: 0.02 });
    tone({ freq: 220.0, type: "sine", dur: 2.2, gain: 0.05, bus: musicBus, attack: 0.02 });
  }
  musicStep += 1;
}

export function startMusic(): void {
  if (musicTimer !== null) return;
  ensureContext();
  musicBar();
  musicTimer = window.setInterval(() => {
    if (!muted) musicBar();
  }, 4000);
}

export function stopMusic(): void {
  if (musicTimer !== null) {
    window.clearInterval(musicTimer);
    musicTimer = null;
  }
  musicResumeTimers.forEach((id) => window.clearTimeout(id));
  musicResumeTimers.clear();
}

/** Duck the music while a dialogue is open so the question reads clearly. */
export function setMusicIntensity(v: number): void {
  if (!musicBus || !ctx) return;
  musicBus.gain.setTargetAtTime(MUSIC_LEVEL * v, ctx.currentTime, 0.3);
}

// --------------------------------------------------------------- samples ---

const sampleCache = new Map<Sample, AudioBuffer>();
const samplePending = new Map<Sample, Promise<AudioBuffer | null>>();
const musicResumeTimers = new Set<number>();
const MUSIC_LEVEL = 0.34;

/** Decodes a clip once; a failed fetch resolves null so callers can fall back. */
function loadSample(name: Sample): Promise<AudioBuffer | null> {
  const cached = sampleCache.get(name);
  if (cached) return Promise.resolve(cached);
  const inflight = samplePending.get(name);
  if (inflight) return inflight;

  const job = (async () => {
    try {
      const c = ensureContext();
      const res = await fetch(SAMPLE_URLS[name]);
      if (!res.ok) return null;
      const bytes = await res.arrayBuffer();
      const buf = await c.decodeAudioData(bytes);
      sampleCache.set(name, buf);
      return buf;
    } catch {
      return null;
    } finally {
      samplePending.delete(name);
    }
  })();
  samplePending.set(name, job);
  return job;
}

/**
 * Play a recorded clip. Resolves when it finishes (or immediately if muted,
 * blocked, or the file will not load), so callers can sequence on it.
 */
export async function playSample(name: Sample, gain = 1): Promise<void> {
  if (muted) return;
  const buf = await loadSample(name);
  if (!buf || muted) return;
  const c = ensureContext();
  if (c.state === "suspended") return;

  const g = c.createGain();
  g.gain.value = gain;
  g.connect(sfxBus as GainNode);
  const src = c.createBufferSource();
  src.buffer = buf;
  src.connect(g);
  src.start();
  await new Promise<void>((resolve) => {
    src.onended = () => {
      g.disconnect();
      resolve();
    };
  });
}

/**
 * Prefetch + decode every clip without playing anything.
 *
 * The first dialogue does a fetch + decodeAudioData at exactly the moment the
 * player is staring at the panel waiting - warm the cache while the intro is
 * still on screen instead, so the first orcInteraction is instant.
 */
export function warmSamples(): Promise<(AudioBuffer | null)[]> {
  return Promise.all((Object.keys(SAMPLE_URLS) as Sample[]).map((name) => loadSample(name)));
}

/**
 * Opening sequence: the welcome clip owns the mix, the score stays silent, and
 * three seconds after the clip ends the score fades back up.
 */
export async function playWelcomeSequence(): Promise<void> {
  musicResumeTimers.forEach((id) => window.clearTimeout(id));
  musicResumeTimers.clear();

  // Hard mute rather than a duck: the clip is long and a score playing under
  // it would read as a mistake.
  if (musicBus && ctx) {
    musicBus.gain.cancelScheduledValues(ctx.currentTime);
    musicBus.gain.setValueAtTime(0, ctx.currentTime);
  }

  await playSample("welcome", 1);

  const fade = window.setTimeout(() => {
    if (musicBus && ctx) {
      const now = ctx.currentTime;
      musicBus.gain.cancelScheduledValues(now);
      musicBus.gain.setValueAtTime(0, now);
      musicBus.gain.linearRampToValueAtTime(MUSIC_LEVEL, now + MUSIC_FADE_IN);
    }
    musicResumeTimers.delete(fade);
  }, MUSIC_RESUME_DELAY * 1000);
  musicResumeTimers.add(fade);
}

// Dev-only diagnostic handle (stripped from production builds), mirroring the
// __dungeon handle in world/Level.tsx: lets the console - and the browser tests
// - check that the graph is really running.
if (import.meta.env.DEV) {
  (globalThis as unknown as { __kdSound?: unknown }).__kdSound = {
    get contextState() {
      return ctx ? ctx.state : "none";
    },
    get musicRunning() {
      return musicTimer !== null;
    },
    get muted() {
      return muted;
    },
    get musicStep() {
      return musicStep;
    },
  };
}