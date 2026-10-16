import type { GameState } from "../game/useGame";

export function EndScreen({
  state,
  onRestart,
}: {
  state: GameState;
  onRestart: () => void;
}) {
  const won = state.endReason === "won";
  return (
    <div className="endscreen" role="dialog" aria-modal="true" data-testid="end-screen">
      <div className="endscreen-inner">
        <h1>{won ? "The dungeon yields to you" : "The dungeon claims you"}</h1>
        <p className="endscreen-sub">
          {won
            ? `${state.playerName || "You"} stands before the altar, unbroken.`
            : `${state.playerName || "You"} falls in the dark.`}
        </p>
        <dl className="endscreen-stats">
          <div>
            <dt>Points</dt>
            <dd data-testid="end-points">{state.points}</dd>
          </div>
          <div>
            <dt>Level</dt>
            <dd>{state.level}</dd>
          </div>
          <div>
            <dt>Orcs slain</dt>
            <dd data-testid="end-orcs">{state.orcs.filter((o) => o.status === "defeated").length}</dd>
          </div>
        </dl>
        <button type="button" className="primary" data-testid="start-new-run" onClick={onRestart}>
          Descend again
        </button>
      </div>
    </div>
  );
}