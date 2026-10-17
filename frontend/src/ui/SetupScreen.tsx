import { useState } from "react";
import { DIFFICULTIES, type Difficulty } from "../game/useGame";

/** Quick picks for the topic field; the input itself stays free-form. */
const TOPIC_PRESETS = [
  { id: "myth", label: "Greek myths", value: "greek mythology" },
  { id: "space", label: "Space", value: "space and astronomy" },
  { id: "history", label: "Ancient history", value: "ancient history" },
  { id: "nature", label: "Animals & nature", value: "animals and nature" },
  { id: "science", label: "Science & inventions", value: "science and inventions" },
  { id: "games", label: "Video games", value: "video games" },
];

export function SetupScreen({
  onBegin,
}: {
  onBegin: (name: string, difficulty: Difficulty, topic: string) => void;
}) {
  const [name, setName] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>(DIFFICULTIES[1]);
  const [topic, setTopic] = useState(DIFFICULTIES[1].interest);
  // Once the player touches the topic it stops following the difficulty.
  const [topicEdited, setTopicEdited] = useState(false);
  const trimmed = name.trim();
  const topicTrimmed = topic.trim();
  const nameValid = trimmed.length >= 2 && trimmed.length <= 24;
  const topicValid = topicTrimmed.length >= 1 && topicTrimmed.length <= 80;
  const valid = nameValid && topicValid;

  const pickDifficulty = (d: Difficulty) => {
    setDifficulty(d);
    if (!topicEdited) setTopic(d.interest);
  };

  const pickTopic = (value: string) => {
    setTopicEdited(true);
    setTopic(value);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onBegin(trimmed, difficulty, topicTrimmed);
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
          {name.length > 0 && !nameValid && (
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
              onClick={() => pickDifficulty(d)}
              aria-pressed={difficulty.id === d.id}
            >
              <strong>{d.label}</strong>
              <span>{d.blurb}</span>
              <small>{d.orcs} orcs</small>
            </button>
          ))}
        </fieldset>

        <div className="field">
          <label>
            <span>Topic for the riddles</span>
            <input
              data-testid="topic-input"
              value={topic}
              onChange={(e) => pickTopic(e.target.value.slice(0, 80))}
              placeholder="e.g. greek mythology"
              maxLength={80}
            />
          </label>
          <div className="topic-presets" role="group" aria-label="Topic suggestions">
            {TOPIC_PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                className="topic-chip"
                data-testid={`topic-preset-${p.id}`}
                onClick={() => pickTopic(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>
          {topicTrimmed.length < 1 && (
            <em className="field-error">Give the orcs a topic — anything from history to space.</em>
          )}
        </div>

        <button type="submit" className="primary enter" data-testid="enter-dungeon" disabled={!valid}>
          Enter the dungeon
        </button>
      </form>
    </div>
  );
}
