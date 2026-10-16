import { useEffect, useRef, useState } from "react";
import { MAX_ANSWER_LENGTH } from "../api/types";
import { SUPER_POWER_COST } from "../game/useGame";

export interface EnemyDialogueProps {
  question: string | null;
  /** True while the backend is still writing the question. */
  loading: boolean;
  hint: string | null;
  hinting: boolean;
  submitting: boolean;
  /** True while the super power is tearing the answer loose. */
  powering: boolean;
  /** The answer the super power revealed, once used. */
  revealed: string | null;
  canUseSuperPower: boolean;
  health: number;
  /** Projected screen position of the 3D slab, so the panel sits on it. */
  anchor: { x: number; y: number } | null;
  orcName: string;
  onSubmit: (answer: string) => void;
  onHint: () => void;
  onSuperPower: () => void;
  onRetreat: () => void;
}

export function EnemyDialogue({
  question,
  loading,
  hint,
  hinting,
  submitting,
  powering,
  revealed,
  canUseSuperPower,
  health,
  anchor,
  orcName,
  onSubmit,
  onHint,
  onSuperPower,
  onRetreat,
}: EnemyDialogueProps) {
  const [answer, setAnswer] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = submitting || loading;

  // Re-focus when a new question opens so the player can type immediately.
  useEffect(() => {
    if (question) inputRef.current?.focus();
  }, [question]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    // After the super power fires, the revealed answer is what gets submitted.
    const value = revealed ?? answer;
    if (submitting || value.length === 0) return;
    onSubmit(value);
    setAnswer("");
  };

  const style = anchor
    ? { left: `${anchor.x}px`, top: `${anchor.y}px` }
    : { left: "50%", top: "50%" };

  return (
    <div className="dialogue-anchor" style={style}>
      <div className="dialogue" role="dialog" aria-label="Orc challenge" data-testid="dialogue">
        <p className="dialogue-speaker" data-testid="orc-name">
          {orcName} challenges you
        </p>

        {loading ? (
          <p className="dialogue-question loading" data-testid="question-loading">
            <span className="pulse" /> The orc is working the words out of its skull…
          </p>
        ) : (
          <p className="dialogue-question" data-testid="question">
            {question}
          </p>
        )}

        {hint && (
          <p className="dialogue-hint" data-testid="hint">
            <span className="hint-mark">✦</span> {hint}
          </p>
        )}

        {revealed ? (
          <p className="dialogue-revealed" data-testid="revealed">
            <span className="reveal-mark">✷</span> The orc&apos;s mind breaks open:{" "}
            <strong>{revealed}</strong>
          </p>
        ) : (
          <button
            type="button"
            className="super-power"
            data-testid="super-power"
            onClick={onSuperPower}
            disabled={!canUseSuperPower || busy || health <= 0}
          >
            {powering ? "Tearing it loose…" : `✷ Super power — costs ${SUPER_POWER_COST} health`}
          </button>
        )}

        <form onSubmit={submit}>
          <input
            ref={inputRef}
            className="dialogue-input"
            data-testid="answer-input"
            value={revealed ?? answer}
            onChange={(e) => setAnswer(e.target.value.slice(0, MAX_ANSWER_LENGTH))}
            placeholder="Speak your answer…"
            maxLength={MAX_ANSWER_LENGTH}
            disabled={busy}
            aria-label="Your answer"
          />
          <div className="dialogue-actions">
            <button
              type="submit"
              className="primary"
              data-testid="submit"
              disabled={busy || (revealed ?? answer).length === 0}
            >
              {submitting ? "Judging…" : "Answer"}
            </button>
            <button type="button" data-testid="hint-button" onClick={onHint} disabled={hinting || busy}>
              {hinting ? "Whispering…" : "Hint"}
            </button>
            <button type="button" data-testid="retreat-button" onClick={onRetreat} disabled={busy}>
              Flee
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}