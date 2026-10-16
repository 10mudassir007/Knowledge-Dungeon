import { useState } from "react";
import { DIFFICULTIES, type Difficulty } from "../game/useGame";

export function SetupScreen({ onBegin }: { onBegin: (name: string, difficulty: Difficulty) => void }) {
  const [name, setName] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>(DIFFICULTIES[1]);
  const trimmed = name.trim();
  const valid = trimmed.length >= 2 && trimmed.length <= 24;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onBegin(trimmed, difficulty);
  };

  return (
    <div className="setup screen over-dungeon" data-testid="setup">
      <form className="setup-card" onSubmit={submit}>
        <h1 className="setup-title">Knowledge Dungeon</h1>
        <p className="setup-tag">The orcs are already awake.</p>

        <label className="field">
          <span>Your name</span>
          <input
            data-testid="name-input"
            value={name}
            onChange={(e) => setName(e.target.value.slice(0, 24))}
            placeholder="e.g. Aric"
            autoFocus
            maxLength={24}
          />
          {name.length > 0 && !valid && (
            <em className="field-error">Use between 2 and 24 characters.</em>
          )}
        </label>

        <fieldset className="difficulty">
          <legend>Difficulty</legend>
          {DIFFICULTIES.map((d) => (
            <button
              key={d.id}
              type="button"
              className={`difficulty-card${difficulty.id === d.id ? " chosen" : ""}`}
              data-testid={`difficulty-${d.id}`}
              onClick={() => setDifficulty(d)}
              aria-pressed={difficulty.id === d.id}
            >
              <strong>{d.label}</strong>
              <span>{d.blurb}</span>
              <small>{d.orcs} orcs · {d.interest}</small>
            </button>
          ))}
        </fieldset>

        <button type="submit" className="primary enter" data-testid="enter-dungeon" disabled={!valid}>
          Enter the dungeon
        </button>
      </form>
    </div>
  );
}