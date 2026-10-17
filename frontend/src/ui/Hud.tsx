import { MAX_LEVEL } from "../api/types";

export interface HudProps {
  playerName: string;
  health: number;
  maxHealth: number;
  powerUses: number;
  points: number;
  level: number;
  /** The score band the bar fills against - not a win condition. */
  maxScore: number;
  /** Whole metres to the altar, or null before the level reports its markers. */
  altarMetres: number | null;
  prompt: { text: string } | null;
  notice: string | null;
  verdict: { text: string; good: boolean } | null;
  /**
   * Player pressed I. Hides every HUD element including the minimap, leaving a
   * clean screenshot. Nothing here should render at all while this is true.
   */
  hidden?: boolean;
}

/**
 * Health bar instead of three discrete pips, so damage reads continuously.
 *
 * Deliberately button-free: once the pointer is locked the cursor is gone, so
 * every control is a shortcut instead (P pause, M map, I hide). The minimap
 * lives in App.tsx and toggles with M rather than being a button.
 *
 * The objective line spells the win condition out in play, because nothing in
 * the dungeon itself says "the altar is the goal, the orcs are not".
 */
export function Hud({
  playerName,
  health,
  maxHealth,
  powerUses,
  points,
  level,
  maxScore,
  altarMetres,
  prompt,
  notice,
  verdict,
  hidden = false,
}: HudProps) {
  if (hidden) return null;

  const pct = Math.max(0, Math.min(100, (points / maxScore) * 100));
  const hp = Math.max(0, Math.min(100, (health / maxHealth) * 100));
  const rounded = Math.ceil(health);
  // Low health pulses so the player can feel the run slipping.
  const critical = hp <= 34;

  return (
    <div className="hud" data-testid="hud">
      <div className="hud-top">
        <div className="hud-left">
          {playerName && (
            <div className="player-name" data-testid="player-name">
              {playerName}
            </div>
          )}
          <div
            className={`health ${critical ? "critical" : ""}`}
            role="progressbar"
            aria-label={`Health: ${rounded} of ${maxHealth}`}
            aria-valuenow={rounded}
            aria-valuemin={0}
            aria-valuemax={maxHealth}
          >
            <div className="health-fill" data-testid="health-bar" style={{ width: `${hp}%` }} />
            <span className="health-label" data-testid="health-value">
              {rounded}
            </span>
          </div>
          <div className="objective" data-testid="objective">
            Reach the altar
            {altarMetres !== null && <span className="objective-range"> · {altarMetres} m</span>}
          </div>
          {powerUses > 0 && (
            <div className="power-uses" data-testid="power-uses">
              super power x{powerUses}
            </div>
          )}
        </div>

        <div className="score">
          <span className="points" data-testid="points">
            {points}
          </span>
          <span className="points-label">/ {maxScore}</span>
        </div>

        <div className="level" data-testid="level">
          Level {level} / {MAX_LEVEL}
        </div>
      </div>

      <div
        className="progress"
        role="progressbar"
        aria-valuenow={points}
        aria-valuemin={0}
        aria-valuemax={maxScore}
      >
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>

      {notice && (
        <div className="notice" role="status" data-testid="notice">
          {notice}
        </div>
      )}

      {verdict && (
        <div
          className={`verdict ${verdict.good ? "good" : "bad"}`}
          role="status"
          data-testid={verdict.good ? "verdict-good" : "verdict-bad"}
        >
          {verdict.text}
        </div>
      )}

      {prompt && (
        <div className="prompt" data-testid="prompt">
          {prompt.text}
        </div>
      )}
    </div>
  );
}