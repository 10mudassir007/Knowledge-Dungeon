/**
 * The pause / settings surface, opened with P.
 *
 * Once the pointer is locked the cursor is gone, so every in-game control is a
 * keyboard shortcut rather than a button. That makes the pause menu the only
 * place a cursor ever comes back, so it carries everything: sound, graphics,
 * the FPS readout, and the full shortcut list.
 */

import {
  PRESETS,
  QUALITY_TIERS,
  type QualitySetting,
  type QualityTier,
  type SystemProfile,
} from "../game/graphics";
import type { FpsSample } from "../game/FpsGuard";
import { feedbackHref } from "./feedback";

/** Single source of truth for the key list shown here and in the HUD hint. */
export const SHORTCUTS: { keys: string; action: string }[] = [
  { keys: "W A S D", action: "Move" },
  { keys: "Left Shift", action: "Sprint" },
  { keys: "Mouse", action: "Look around" },
  { keys: "Arrow keys", action: "Turn (fallback)" },
  { keys: "E", action: "Read the lectern / face an orc again" },
  { keys: "M", action: "Dungeon map" },
  { keys: "P", action: "Pause menu (sound, graphics, shortcuts)" },
  { keys: "I", action: "Hide / show the interface" },
  { keys: "F", action: "Toggle the FPS readout" },
  { keys: "Esc", action: "Close the open overlay, else pause" },
];

/**
 * The opening narration, fixed rather than generated.
 *
 * The backend's per-run `environment` was a different place name every time,
 * which undercut the intro clip and the map legend. The script now stays put so
 * the welcome audio always matches what is on screen.
 */
export const WELCOME_TEXT = [
  "So, you have crossed the threshold. There is no turning back now. These ancient halls have swallowed kings, scholars, and warriors far greater than you. Their bones lie beneath the stones, their names lost to time.",
  "The orcs that roam this labyrinth are no mere beasts; they are keepers of forgotten knowledge, and they will not surrender their secrets freely.",
  "Each will test your mind before allowing you passage. Answer wisely, for ignorance carries a price in these halls.",
];

export interface PauseMenuProps {
  onResume: () => void;
  onRestart: () => void;
  onQuit: () => void;
  muted: boolean;
  onToggleSound: () => void;
  setting: QualitySetting;
  tier: QualityTier;
  profile: SystemProfile;
  onSetting: (next: QualitySetting) => void;
  fps: FpsSample | null;
  showFps: boolean;
  onToggleFps: () => void;
}

export function PauseMenu({
  onResume,
  onRestart,
  onQuit,
  muted,
  onToggleSound,
  setting,
  tier,
  profile,
  onSetting,
  fps,
  showFps,
  onToggleFps,
}: PauseMenuProps) {
  const preset = PRESETS[tier];
  const fpsColor = !fps || fps.fps === 0
    ? "var(--parchment-dim)"
    : fps.fps >= preset.targetFps
      ? "#8ce8a8"
      : fps.fps >= preset.targetFps * 0.75
        ? "var(--ember-hot)"
        : "#ff9d8a";

  return (
    <div className="pausemenu" role="dialog" aria-modal="true" data-testid="pause-menu">
      <div className="pausemenu-inner">
        <h2>Paused</h2>

        <section className="pause-block">
          <h3>Objective</h3>
          <p className="settings-note" data-testid="objective-copy">
            <strong>Reach the altar</strong> on the far side of the maze. The orcs that stand on
            the way test you as you come near; every answer you get right knits a little health
            back, every one you miss costs a life. Cut through them or slip past them — reaching
            the altar is what wins the run.
          </p>
        </section>

        <section className="pause-block">
          <h3>Sound</h3>
          <button
            type="button"
            className={`quality-chip${muted ? "" : " chosen"}`}
            data-testid="pause-sound"
            aria-pressed={!muted}
            onClick={onToggleSound}
          >
            <strong>{muted ? "Off" : "On"}</strong>
            <span>Music and effects</span>
          </button>
        </section>

        <section className="pause-block">
          <h3>Graphics</h3>
          <div className="quality-row">
            <button
              type="button"
              className={`quality-chip${setting === "auto" ? " chosen" : ""}`}
              data-testid="quality-auto"
              aria-pressed={setting === "auto"}
              onClick={() => onSetting("auto")}
            >
              <strong>Auto</strong>
              <span>Suggested: {PRESETS[profile.suggested].label}</span>
            </button>
            {QUALITY_TIERS.map((id) => (
              <button
                key={id}
                type="button"
                className={`quality-chip${setting === id ? " chosen" : ""}`}
                data-testid={`quality-${id}`}
                aria-pressed={setting === id}
                onClick={() => onSetting(id)}
              >
                <strong>{PRESETS[id].label}</strong>
                <span>{PRESETS[id].blurb}</span>
              </button>
            ))}
          </div>
          <p className="settings-note">
            Active: <strong>{preset.label}</strong> · target {preset.targetFps} FPS · render
            scale {fps ? `${Math.round(fps.scale * 100)}%` : "auto"}
          </p>
        </section>

        <section className="pause-block">
          <h3>Performance</h3>
          <p className="settings-fps" data-testid="fps-readout" style={{ color: fpsColor }}>
            {fps && fps.fps > 0 ? `${fps.fps} FPS` : "measuring…"}
            {fps?.scaled ? " (resolution auto-trimmed to hold the target)" : ""}
          </p>
          <button
            type="button"
            className={`quality-chip${showFps ? " chosen" : ""}`}
            data-testid="fps-toggle"
            aria-pressed={showFps}
            onClick={onToggleFps}
          >
            <strong>{showFps ? "FPS shown" : "FPS hidden"}</strong>
            <span>Toggle the readout with F</span>
          </button>
        </section>

        <section className="pause-block">
          <h3>Shortcuts</h3>
          <dl className="pausemenu-keys" data-testid="shortcut-list">
            {SHORTCUTS.map((s) => (
              <div key={s.keys}>
                <dt>{s.keys}</dt>
                <dd>{s.action}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="pause-block">
          <h3>Report a bug · Suggest a feature</h3>
          <p className="settings-note">
            Opens the project tracker on GitHub in a new tab, with this page's context attached.
          </p>
          <div className="feedback-row">
            <a
              className="quality-chip"
              data-testid="report-bug"
              href={feedbackHref("bug")}
              target="_blank"
              rel="noreferrer"
            >
              <strong>Report a bug</strong>
              <span>Something broke or reads wrong</span>
            </a>
            <a
              className="quality-chip"
              data-testid="suggest-feature"
              href={feedbackHref("feature")}
              target="_blank"
              rel="noreferrer"
            >
              <strong>Suggest a feature</strong>
              <span>An idea for the dungeon</span>
            </a>
          </div>
        </section>

        <div className="pausemenu-actions">
          <button type="button" className="primary" data-testid="resume" onClick={onResume}>
            Resume (P)
          </button>
          <button type="button" data-testid="pause-restart" onClick={onRestart}>
            Start new run
          </button>
          <button type="button" data-testid="quit" onClick={onQuit}>
            Quit to title
          </button>
        </div>
      </div>
    </div>
  );
}