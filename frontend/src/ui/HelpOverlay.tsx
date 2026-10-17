/**
 * The lectern's pages: what the dungeon asks of you, and how to answer.
 *
 * Pressing E at the lectern opens this instead of spending a hint. It is a
 * full screen overlay rather than a corner card so it can carry everything a
 * first-time player needs: the objective, the duel rules, the two tools and
 * their price, every shortcut, and the feedback links to the project tracker.
 */

import { SHORTCUTS } from "./PauseMenu";
import { feedbackHref } from "./feedback";

export interface HelpOverlayProps {
  onClose: () => void;
}

export function HelpOverlay({ onClose }: HelpOverlayProps) {
  return (
    <div
      className="help"
      data-testid="help"
      role="dialog"
      aria-modal="true"
      aria-label="How to play"
      onClick={onClose}
    >
      <section className="help-card" onClick={(e) => e.stopPropagation()}>
        <h2>How to play</h2>

        <p className="help-lead">
          <strong>Reach the altar</strong> on the far side of the maze. The orcs that stand on
          the way test you as you come near — answer them, slip past them, or cut through.
          Reaching the altar is what wins the run.
        </p>

        <section className="help-block">
          <h3>The orcs</h3>
          <p>
            Step within a few paces of an orc and it challenges you with a question from the
            field you chose. A right answer dissolves it and knits a little health back. A wrong
            one costs health; run out and the run is over. <strong>Retreat</strong> buys you a
            breath. An orc that has already asked leaves you in peace until you walk clear of
            it — press E to face it again.
          </p>
          <ul className="help-tools">
            <li>
              <strong>Hint</strong> — the orc drops a clue. The question stays.
            </li>
            <li>
              <strong>Super power</strong> — the orc's mind breaks open and the answer shows,
              for a price in health.
            </li>
          </ul>
        </section>

        <section className="help-block">
          <h3>Controls</h3>
          <dl className="pausemenu-keys" data-testid="help-shortcuts">
            {SHORTCUTS.map((s) => (
              <div key={s.keys}>
                <dt>{s.keys}</dt>
                <dd>{s.action}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="help-block">
          <h3>Report a bug · Suggest a feature</h3>
          <p className="settings-note">
            The dungeon is still being carved. If something breaks or you have an idea for what
            should stand in it next, the tracker below takes it — the page you are on and the
            time are attached.
          </p>
          <div className="feedback-row">
            <a
              className="quality-chip"
              data-testid="help-report-bug"
              href={feedbackHref("bug")}
              target="_blank"
              rel="noreferrer"
            >
              <strong>Report a bug</strong>
              <span>Something broke or reads wrong</span>
            </a>
            <a
              className="quality-chip"
              data-testid="help-suggest-feature"
              href={feedbackHref("feature")}
              target="_blank"
              rel="noreferrer"
            >
              <strong>Suggest a feature</strong>
              <span>An idea for the dungeon</span>
            </a>
          </div>
        </section>

        <div className="help-actions">
          <button type="button" className="primary" data-testid="help-close" onClick={onClose}>
            Back to the halls (Esc)
          </button>
        </div>
      </section>
    </div>
  );
}
