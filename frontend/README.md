# Knowledge Dungeon — Frontend

The Knowledge Dungeon. React + TypeScript + Vite, rendered with @react-three/fiber, using
the level exported from Blender (`dungeon.glb`).

The backend only generates questions and scores answers. **Orcs are entirely
frontend-side** — placement, identity, naming, weapons and animations all live here.

## On startup

You pick a **name** and a **difficulty** before anything else happens:

| Difficulty | Topic sent as `interest` | Orcs |
| --- | --- | --- |
| Squire | everyday legends and folk tales | 2 |
| Adept | ancient history and warring kingdoms | 3 |
| Legend | arcane, cursed and forbidden lore | 5 |

Difficulty drives both the question topic (the dungeon narrator writes to match)
and how many orcs are seeded into the level.

## Look

The reference mood is deep indigo/violet dark fantasy — near-black blue stone, a
strong violet key at the altar, heavy atmospheric haze.

- **Rock materials are generated at runtime** in `world/rockTextures.ts`: multi-octave
  value noise for grain, a worley layer for masonry joints and fractures, and a normal map
  derived from the height field. Rasterised to a canvas on load — no image files ship.
- The GLB's baked stone is swapped out at load (`applyLook` in `world/Level.tsx`), and the
  flame/crystal emission is halved because strength 8 blooms into a white blob up close.
- Lighting is indigo ambient + hemisphere fill, cold blue-white flickering torches, a violet
  altar key, and exponential violet fog.
- Post: bloom, chromatic aberration, film noise, vignette. All toned down under
  `prefers-reduced-motion`.

## Orcs

`world/Orc.tsx` builds a hulking, tusked, armoured brute from primitives, each with a
medieval weapon drawn from a seeded random (axe, sword, mace, halberd, spear, warhammer)
that stays with it for the whole run. Each gets a stable generated name (`Grukk`, `Thoril`,
`Magril`…) used only in UI text.

Animation states:

| State | Trigger |
| --- | --- |
| `idle` | slow breathing sway, glowing eyes |
| `attack` | **wrong answer** — wind-up, lunge at the player, weapon swing |
| `defeat` | **correct answer** — recoil, sink to a knee, dissolve |

## Controls

| Input | Action |
| --- | --- |
| Click canvas | Start pointer lock (mouse look) |
| `W` `A` `S` `D` | Move |
| Arrow keys | Turn (fallback when pointer lock is unavailable) |
| `E` | Engage an orc within 2 m, or read the lectern within 1.8 m |
| `Esc` | Pause menu |

## Run it

You need **two terminals**.

### 1) Backend (repo root) — one worker

Sessions are held in process memory, so run a **single** worker. With more than
one worker a session created on one worker will 404 on another.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
copy .env.example .env            # Windows: Copy-Item .env.example .env
# edit .env and set GROQ_API_KEY (or another provider key)
uvicorn main:app --port 8000 --workers 1
```

Check it: `curl http://localhost:8000/health`

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Configuration

`.env` (copy from `.env.example`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_API_URL` | `/api` | Backend base URL. `/api` uses the Vite dev proxy, which strips the prefix and forwards to `http://localhost:8000`. Set an absolute URL to bypass the proxy. |

## Controls

| Input | Action |
| --- | --- |
| Click canvas | Start pointer lock (mouse look) |
| `W` `A` `S` `D` | Move |
| Arrow keys | Turn (fallback when pointer lock is unavailable) |
| `E` | Engage a guardian within 2 m, or use the lectern within 1.8 m |
| `Esc` | Pause menu |

## Scripts

```bash
npm run dev      # dev server
npm run build    # typecheck + production build
npm test         # vitest run
npm run preview  # serve the production build
```

## The level

41 columns x 31 rows, 1 m cells, 3 m walls, floor at `y = 0`, ceiling at `y = 3`.
X is the column, Z is the row, and a cell's centre is `(c + 0.5, 0, r + 0.5)`.

The grid lives in two places that must never drift apart:

- `dungeon/map.txt` — the source of truth used by the Blender build
- `src/world/map.ts` — the same 31 rows as an exported string

`tests/map.test.ts` asserts the two files are identical, and `tests/levelMarkers.test.ts`
parses `dungeon.glb` directly and checks every `Altar` / `Spawn` / `Hint_Lectern` /
`Life_*` / `Torch_*` / `Enemy_*` node sits on the cell its name implies.

Markers: `S` spawn (bottom left), `Q` altar (top right), `H` hint lectern, three `B`
life braziers in a row, 8-12 `T` torches (at least one per chamber), and 4-6 `E` enemy
anchors. The spawn-to-altar route is 121 steps and every floor cell is reachable.
`map.ts` derives `SPAWN_YAW` from the grid so the player never starts facing a wall.

`dungeon.glb` is exported Y-up per the glTF spec, which maps Blender's
`(X=col, Y=height, Z=row)` to `(X, Z, -Y)`. `Level.tsx` rotates the loaded scene +90°
about X to restore the grid convention before reading any marker.

## Layout

```
src/
  api/client.ts        typed fetch + status -> message mapping
  api/types.ts         mirrors API_CONTRACT.md
  game/useGame.ts      state machine (setup | loading | playing | dialogue | over)
  world/map.ts         the 41x31 grid, reachability, collision, spawn yaw
  world/enemySpawn.ts  seeded orc placement + naming
  world/rockTextures.ts  runtime procedural rock + normal maps
  world/Level.tsx      loads the GLB, unskews it, reads markers, applies the look
  world/Player.tsx     movement, grid + body collision, pointer lock
  world/Lights.tsx     torches, altar light, fog
  world/Orc.tsx        orc model, weapons, attack/defeat animation
  world/DialogueSlab.tsx  carved stone slab the dialogue sits on
  ui/                  HUD, dialogue, end screen, pause, setup
tests/                 vitest suites
```

See `API_CONTRACT.md` for the exact backend contract this app is built against.