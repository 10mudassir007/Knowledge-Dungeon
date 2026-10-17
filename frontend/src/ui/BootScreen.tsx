interface BootScreenProps {
  /** 0-100, best effort; 0 until the first model starts downloading. */
  progress: number;
}

/**
 * Full-cover card between page load and the setup menu: the dungeon is already
 * rendering below it, and the form only appears once its models are in memory.
 */
export function BootScreen({ progress }: BootScreenProps) {
  return (
    <div className="screen boot" data-testid="boot">
      <div className="spinner" />
      <h1>The dungeon is waking…</h1>
      <p>Carving stone and rousing the orcs{progress > 0 ? ` · ${progress}%` : "…"}</p>
    </div>
  );
}
