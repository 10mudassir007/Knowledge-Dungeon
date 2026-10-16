/**
 * The dungeon map, drawn from the same GRID the collision system uses.
 *
 * Two presentations share one canvas painter:
 *  - `Minimap`: a compact corner widget that shows where you are and where the
 *    altar (goal), lectern and orcs are.
 *  - `MapOverlay`: the same map, fullscreen, with a legend and every marker
 *    the GLB carries (torches and braziers included).
 *
 * The player's cell/yaw are pushed into a ref every frame by CellTracker in
 * App.tsx; both views poll that ref at a low rate so drawing never re-renders
 * the 3D scene.
 */

import { useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { ALTAR, BRAZIERS, GRID, HEIGHT, LECTERN, SPAWN, WIDTH } from "../world/map";
import type { EnemyInstance } from "../game/useGame";

export interface MapPlayer {
  col: number;
  row: number;
  yaw: number;
}

const CELL = { compact: 7, full: 16 } as const;

export const PALETTE = {
  void: "#0d0819",
  wall: "#1c1531",
  wallTop: "#2a1f48",
  floor: "#312747",
  start: "#63e6a8",
  altar: "#c9a4ff",
  lectern: "#7fc4ff",
  ember: "#ff9a4d",
  torch: "#ffd76a",
  orc: "#ff5a44",
  orcGone: "#4a4160",
  water: "#2f7fa8",
  player: "#66f5ff",
} as const;

function drawMap(
  ctx: CanvasRenderingContext2D,
  size: number,
  detail: "compact" | "full",
  player: MapPlayer,
  orcs: EnemyInstance[],
  pulse: number,
): void {
  ctx.clearRect(0, 0, WIDTH * size, HEIGHT * size);
  ctx.fillStyle = PALETTE.void;
  ctx.fillRect(0, 0, WIDTH * size, HEIGHT * size);

  // Geometry first: floors and walls straight from the collision grid.
  for (let row = 0; row < HEIGHT; row += 1) {
    for (let col = 0; col < WIDTH; col += 1) {
      const ch = GRID[row][col];
      const x = col * size;
      const y = row * size;
      if (ch === "#") {
        ctx.fillStyle = PALETTE.wall;
        ctx.fillRect(x, y, size, size);
        if (detail === "full") {
          ctx.fillStyle = PALETTE.wallTop;
          ctx.fillRect(x, y, size, Math.max(1, Math.round(size * 0.18)));
        }
      } else {
        ctx.fillStyle = PALETTE.floor;
        ctx.fillRect(x, y, size, size);
      }
    }
  }

  const dot = (col: number, row: number, color: string, r: number, glow = 0) => {
    ctx.save();
    if (glow > 0) {
      ctx.shadowColor = color;
      ctx.shadowBlur = glow;
    }
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc((col + 0.5) * size, (row + 0.5) * size, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  };

  if (detail === "full") {
    for (let row = 0; row < HEIGHT; row += 1) {
      for (let col = 0; col < WIDTH; col += 1) {
        const ch = GRID[row][col];
        if (ch === "T") dot(col, row, PALETTE.torch, size * 0.16, size * 0.5);
        else if (ch === "B") dot(col, row, PALETTE.ember, size * 0.22, size * 0.6);
      }
    }
  } else {
    for (const b of BRAZIERS) dot(b.col, b.row, PALETTE.ember, size * 0.2, size * 0.5);
  }

  // Start marker.
  ctx.save();
  ctx.strokeStyle = PALETTE.start;
  ctx.lineWidth = Math.max(1, size * 0.14);
  ctx.shadowColor = PALETTE.start;
  ctx.shadowBlur = size * 0.6;
  ctx.strokeRect((SPAWN.col + 0.18) * size, (SPAWN.row + 0.18) * size, size * 0.64, size * 0.64);
  ctx.restore();

  // Lectern.
  dot(LECTERN.col, LECTERN.row, PALETTE.lectern, size * 0.2, size * 0.7);

  // Altar: the goal star, gently pulsing on the fullscreen view.
  {
    const cx = (ALTAR.col + 0.5) * size;
    const cy = (ALTAR.row + 0.5) * size;
    const R = size * (0.36 + (detail === "full" ? pulse * 0.14 : 0));
    ctx.save();
    ctx.shadowColor = PALETTE.altar;
    ctx.shadowBlur = size * 0.9;
    ctx.fillStyle = PALETTE.altar;
    ctx.beginPath();
    for (let i = 0; i < 10; i += 1) {
      const rad = i % 2 === 0 ? R : R * 0.45;
      const a = -Math.PI / 2 + (i * Math.PI) / 5;
      const px = cx + Math.cos(a) * rad;
      const py = cy + Math.sin(a) * rad;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  // Orcs: hot red while alive, dim once defeated.
  for (const o of orcs) {
    if (o.status === "alive") dot(o.cell.col, o.cell.row, PALETTE.orc, size * 0.28, size * 0.9);
    else dot(o.cell.col, o.cell.row, PALETTE.orcGone, size * 0.16);
  }

  // The player: a wedge showing position and facing.
  {
    const cx = (player.col + 0.5) * size;
    const cy = (player.row + 0.5) * size;
    // World forward is (-sin(yaw), -cos(yaw)) in (x, z); the map draws
    // x to the right and z downwards, so the direction vector carries over.
    const dirX = -Math.sin(player.yaw);
    const dirY = -Math.cos(player.yaw);
    const rot = Math.atan2(dirY, dirX) + Math.PI / 2;
    const R = size * 0.42;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(rot);
    ctx.shadowColor = PALETTE.player;
    ctx.shadowBlur = size * 0.9;
    ctx.fillStyle = PALETTE.player;
    ctx.beginPath();
    ctx.moveTo(0, -R);
    ctx.lineTo(R * 0.75, R * 0.75);
    ctx.lineTo(0, R * 0.3);
    ctx.lineTo(-R * 0.75, R * 0.75);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
}

function MapCanvas({
  detail,
  player,
  orcs,
  pulse,
}: {
  detail: "compact" | "full";
  player: MapPlayer;
  orcs: EnemyInstance[];
  pulse: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    drawMap(ctx, CELL[detail], detail, player, orcs, pulse);
  }, [detail, player, orcs, pulse]);

  return (
    <canvas
      ref={ref}
      width={WIDTH * CELL[detail]}
      height={HEIGHT * CELL[detail]}
      className={detail === "compact" ? "map-canvas compact" : "map-canvas"}
    />
  );
}

export function Minimap({
  playerRef,
  orcs,
  onOpen,
}: {
  playerRef: MutableRefObject<MapPlayer>;
  orcs: EnemyInstance[];
  onOpen: () => void;
}) {
  const [view, setView] = useState<MapPlayer>({ col: SPAWN.col, row: SPAWN.row, yaw: 0 });

  useEffect(() => {
    const id = window.setInterval(() => {
      const p = playerRef.current;
      setView((prev) =>
        prev.col === p.col && prev.row === p.row && Math.abs(prev.yaw - p.yaw) < 0.15
          ? prev
          : { col: p.col, row: p.row, yaw: p.yaw },
      );
    }, 150);
    return () => window.clearInterval(id);
  }, [playerRef]);

  return (
    <div className="minimap-wrap">
      <span className="minimap-title">Map · M</span>
      <button
        type="button"
        className="minimap-frame"
        onClick={onOpen}
        data-testid="minimap"
        aria-label="Open the dungeon map"
      >
        <MapCanvas detail="compact" player={view} orcs={orcs} pulse={0} />
      </button>
    </div>
  );
}

const LEGEND: { color: string; label: string }[] = [
  { color: PALETTE.player, label: "You" },
  { color: PALETTE.altar, label: "Altar — the goal" },
  { color: PALETTE.lectern, label: "Lectern" },
  { color: PALETTE.start, label: "Start" },
  { color: PALETTE.orc, label: "Orc" },
  { color: PALETTE.orcGone, label: "Defeated orc" },
  { color: PALETTE.torch, label: "Torch" },
  { color: PALETTE.ember, label: "Brazier" },
];

export function MapOverlay({
  playerRef,
  orcs,
  onClose,
  reduced,
}: {
  playerRef: MutableRefObject<MapPlayer>;
  orcs: EnemyInstance[];
  onClose: () => void;
  reduced: boolean;
}) {
  const [tick, setTick] = useState(0);
  const [view, setView] = useState<MapPlayer>({ col: SPAWN.col, row: SPAWN.row, yaw: 0 });

  useEffect(() => {
    const id = window.setInterval(() => {
      setTick((t) => t + 1);
      const p = playerRef.current;
      setView((prev) =>
        prev.col === p.col && prev.row === p.row && Math.abs(prev.yaw - p.yaw) < 0.08
          ? prev
          : { col: p.col, row: p.row, yaw: p.yaw },
      );
    }, 120);
    return () => window.clearInterval(id);
  }, [playerRef]);

  const pulse = reduced ? 0 : 0.5 + 0.5 * Math.sin(tick * 0.3);

  return (
    <div className="map-overlay" data-testid="map-fullscreen" onClick={onClose}>
      <div className="map-card" onClick={(e) => e.stopPropagation()}>
        <h2>Dungeon Map</h2>
        <MapCanvas detail="full" player={view} orcs={orcs} pulse={pulse} />
        <div className="map-legend">
          {LEGEND.map((item) => (
            <span key={item.label}>
              <i style={{ background: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
        <button type="button" className="primary" onClick={onClose} data-testid="map-close">
          Close (M)
        </button>
      </div>
    </div>
  );
}
