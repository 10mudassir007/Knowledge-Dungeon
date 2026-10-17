# AGENTS.md

Python/FastAPI quiz backend + a React Three Fiber dungeon client. Assets are authored in
Blender and exported as GLB.

## Truth sources (when docs disagree, trust these)

- `frontend/API_CONTRACT.md` — the backend contract `src/api/types.ts` mirrors.
- `dungeon/map.txt` — the maze source of truth (41 cols x 31 rows).
- `pytest.ini`, `frontend/package.json`, `frontend/vite.config.ts` — actual test/config.

**Both `README.md` and `frontend/README.md` are stale in places**: they say the frontend lives
in `quest-master/` (it is `frontend/`), cells are 1 m (they are 2 m), difficulty orc counts are
2/3/5 (4/7/11), and that `Orc.tsx` builds orcs from primitives (it loads `orc.glb`). Port
5173, not 8080. Prefer the files above over prose.

## Commands

```bash
# backend — MUST use the venv; bare `python` lacks fastapi/uvicorn
.\.venv\Scripts\python.exe -m pytest                 # 109 passed
.\.venv\Scripts\python.exe -m uvicorn main:app --port 8000 --workers 1
# single worker: sessions are in-process memory, a 2nd worker 404s your session

cd frontend
npm test          # vitest run — 101 passed
npm run build     # tsc -b && vite build; this IS the typecheck gate (no lint/format configured)
npm run dev       # :5173, proxies /api -> :8000 (prefix stripped)
```

Single vitest file: `npx vitest run tests/puddles.test.ts`. Single pytest: `-k answer_check`.

## Two dev servers, and the backend is optional

The dungeon renders and plays with no backend. Only answering needs it. To smoke-test
play without an LLM key, drive the render and assert on `window.__dungeonScene` /
`window.__dungeonCamera` via `playwright_browser_run_code_unsafe`.

## Blender is the asset pipeline

```bash
blender --background dungeon/dungeon.blend --python dungeon/build_level.py   # dungeon.glb + puddle.glb
blender --background dungeon/dungeon.blend --python dungeon/build_orc.py     # orc.glb
```

- `dungeon/build_props.py` holds every prop (torch sconce/stand, brazier, altar, lectern,
  skeleton remains) and is called by `build_level.py`. `build_props.preview([...])` renders
  isolated Workbench stills — far more reliable than eyeballing a viewport.
- **The step that gets forgotten:** exports land in `dungeon/`, but the client loads
  `frontend/public/assets/`. They must be copied by hand; nothing does it for you.
- `tests/levelMarkers.test.ts` parses `frontend/public/assets/dungeon.glb` — the *copy*.
  Rebuild in Blender, forget the copy, and the suite happily passes against the stale asset.
- `dungeon/validate_map.py` and `dungeon/build_dungeon.py` are legacy (15x8 map, 1 m cells).
  The live pipeline is `build_level.py`.
- User preference: model/build in Blender first, then migrate to the frontend, then verify.
  Blender MCP is available and is the expected way to iterate on models.

### Blender traps that silently produce wrong geometry

- **The dungeon is Y-up, but `bmesh.ops.create_cone`/`create_cube`/`create_icosphere` are
  Z-up.** Anything meant to stand must pass `build_props.UP` (which is a **-90 deg** turn about
  X; +90 maps +Z onto world -Y and turns parts upside down). Symmetric cylinders hide the
  mistake — a flipped flame cone or a sconce log hanging below its own bracket is what gives
  it away.
- Matrix order matters: to stand a local frame up and then swing it, use `Ry(facing) @ UP`.
  `UP @ Ry` does not commute and gives the wrong facing.
- Prop vertices are authored in **world** coordinates, so the objects sit at the origin.
  Parent them with `parent_to()` (sets `matrix_parent_inverse`) or they land at double their
  intended position. `parent_to` must run `bpy.context.view_layer.update()` first: right after
  the parent is created its `matrix_world` is still identity, so the inverse is identity too and
  the prop exports at **double its cell** (the altar once floated ~60 m past the south wall).
  `levelMarkers.test.ts` cannot catch it — the empty nodes were always correct; only the meshes
  doubled.
- `bmesh.ops.bevel` rebuilds verts: tag `material_index` **before** the bevel and pass
  `material=-1` so chamfer faces inherit.
- Blender's `to_track_quat("-Z","Y")` rolls the camera frame in a Y-up world, which makes
  every prop look like it is lying down. Build the camera basis explicitly instead.

## Layout invariants that break silently

- **Cell size is duplicated.** `CELL = 2` in `dungeon/build_level.py` and `frontend/src/world/map.ts`.
  Change one, change the other, or collision/collision-with-walls and marker tests drift.
- **The grid is duplicated.** `dungeon/map.txt` is re-exported as the `GRID` string array in
  `map.ts`; `tests/map.test.ts` asserts they are byte-identical. Edit both.
- **glTF is Y-up.** Blender `(X=col, Y=height, Z=row)` exports to `(X, Z, -Y)`; `Level.tsx`
  compensates with `unskew()` (+90 deg about X) before reading any marker.
- **Prop positions must come from geometry bounds, never `matrixWorld`.** The exporter splits a
  multi-material prop into a group plus suffixed meshes (`PropTorch_1_26`, `PropTorch_1_26_1`),
  and because the vertices are world-space the group transform is `(0,0,0)`. Reading it that
  way parks every torch light on the world origin. `Level.tsx` unions the bounding boxes of
  `name` and `name_*`, and calls `scene.updateWorldMatrix(true, true)` after `unskew()` —
  without that the stale matrices collapse the bounds to a point.
- **Orcs, cells and run placement are frontend-only** — the backend knows nothing about them.
  Difficulty drives `interest` (topic) and orc count together.
- Orc ids are per-cell (`orc_<col>_<row>`), so timers that outlive a run can hit a *new* orc
  in the same cell. `useGame` clears pending defeat-removal timers in `startRun`.

## Lighting, shadows and occlusion

- Moving occlusion is almost always one of three things, in order of likelihood:
  1. N8AO guessing normals from depth — it crawls as the camera moves. `App.tsx` renders a
     world-space normal buffer and `patchAONormals` makes the AO shader consume it. A plain
     uniform assignment is silently a no-op: the pass resets `sceneNormal` to null every
     render, and the full-res shader only reads it under `#ifdef HALFRES`. Skinned meshes are
     hidden from that pass (bind-pose silhouettes); their pixels fall back to depth normals.
  2. A shadow-casting light with no `normalBias` — the depth comparison crawls across surfaces.
  3. AO stacked on top of the baked vertex AO in `COLOR_0`. The bake is the base layer; keep
     screen AO tight (radius ~0.5) and gentle.
- Walls must `castShadow`. Otherwise torch light leaks through stone and the level reads as one
  bright blob. Point-light shadows are cube maps, so cap `shadowCasters` (2/4/6 per tier) and
  measure before raising it. `ShadowDirector` gates set swaps with hysteresis (a newcomer must
  be 25% closer) — a swap pops one torch's shadows in and another's out, and plain
  nearest-N re-rolls the set every tick as the player crosses equidistant points.
- Tiers drive independent axes in `game/graphics.ts` — render scale, AA, shadow type/size/casters/
  bias, AO radius/intensity/resolution, fog density (draw distance), anisotropy, torch count.
  Changing a field means touching `Effects`, `Lights`, `Orc`, `Puddles` and `App` together.

## Frontend conventions

- **There are no buttons in play.** The pointer is locked, so everything is a shortcut:
  `WASD` move, `Shift` sprint, `E` engage/lectern, `M` map, `P` pause (sound + graphics + FPS +
  full shortcut list), `I` hide all UI including the minimap, `F` FPS readout, `Esc` close
  overlay then pause. Key handlers must ignore events targeting `INPUT`/`TEXTAREA`.
- `SHORTCUTS` and `WELCOME_TEXT` live in `ui/PauseMenu.tsx`. The opening narration is a fixed
  script, not the backend's per-run `environment`.
- Audio: synthesised in `audio/sound.ts` (Web Audio) **plus three recorded clips** in
  `frontend/public/audio/` (`welcome`, `orcInteract`, `orcAttack`), decoded lazily and cached.
  `playWelcomeSequence()` mutes the score for the clip, then fades it back in after
  `MUSIC_RESUME_DELAY` seconds. Mute persists as `kd.sound.muted`; graphics as `kd.quality`.
- Tests stub `fetch`; the `useGame` harness is `boot(result, seed)` in `tests/useGame.test.ts`.
  Use fake timers for the 3 s defeated-orphan removal.

## Gotchas that cost real time

- **Encounter suppression rides on the proximity read, and `frozen` must not blank it.**
  `ProximityTracker` keeps its last reading while `frozen`; it used to write `EMPTY_PROXIMITY`
  every frozen frame, so the first 10 Hz tick after a dialogue closed read "no orc in range",
  dropped the cooldown, and the same orc re-engaged a tick later - one duel, two questions.
  An answered duel (`state.verdict` set) now suppresses until the player walks clear or presses
  E; a retreat keeps the 4 s beat.
- **Exported GLBs are not render-ready.** `puddle.glb` had no UVs (alphaMap sampled the
  corner -> alpha 0 -> invisible), arrived as a dished mesh standing off-plane, and dipped
  below the floor. `Puddles.tsx` now derives UVs, orientation and lift from the geometry's
  own bounding box. If a GLB looks wrong, measure it in-browser instead of guessing signs.
- **glTF winding is not guaranteed.** A floor exported with inverted faces renders as a
  black void; fix in Blender, not with a material hack.
- The opening narration deliberately covers the scene for 9 s (`App.tsx`), and the entry
  veil clears on `state.phase`. Screenshot after waiting for `[data-testid="intro"]` to
  disappear or you will debug a blur that is just the intro card.
- Headless pointer lock is unavailable: stub `document.pointerLockElement` and dispatch
  `mousemove` with `movementX/movementY` defined, or the camera will not turn.
- PowerShell here has no `rg`; use `Select-String`/`grep`.