# Knowledge Dungeon — API Contract

Derived by reading `main.py` and `core/rules.py` at the repo root. Every type in
`src/api/types.ts` mirrors this file. Do not invent fields that are not here.

Base URL: `VITE_API_URL` if set, otherwise `/api` (Vite dev proxy strips the prefix).

## Shared rules

- All responses are JSON. Errors are `{ "detail": "..." }`.
- Sessions are **in-memory** and expire after **2 hours** of inactivity → `404`.
- The backend knows **nothing about enemies**. Enemy placement, identity and
  "who is asking" are frontend-only concepts.
- The backend also models **no win**. A run is won in the client by reaching the
  altar; the server only ever ends a game at **0 lives**.
- The answer and accepted alternatives are **never** returned by any endpoint.
- Game rules (`core/rules.py`): 3 lives, +100 points per correct answer,
  level = `min(3, 1 + points // 300)`, game over at **0** lives. Points keep
  accumulating (there is no score cap and no finish line), but a game over
  never changes further.

## Status codes

| Code | Meaning | Where it happens |
| --- | --- | --- |
| `200` | success | every endpoint |
| `400` | Game over (no lives left) | `question`, `hint`, `answer-check`, `environment` |
| `404` | Invalid or expired `session_id` | every `/game/{sid}` endpoint |
| `409` | No active question on the server | `hint`, `answer-check` |
| `422` | Request body failed validation | `start`, `answer-check` |
| `502` | Question model never returned valid JSON | `question` |
| `503` | LLM provider unavailable / not configured | any endpoint calling the model |
| `500` | Unexpected server error, generic detail | any endpoint |

---

## POST /game/start

Creates a session and returns the opening narration.

**Request**

| Field | Type | Rules |
| --- | --- | --- |
| `age` | number | integer, `1..120` |
| `interest` | string | `1..80` chars |

**Response `200`**

| Field | Type | Notes |
| --- | --- | --- |
| `session_id` | string | UUID, sent as `{sid}` below |
| `age` | number | echoed |
| `interest` | string | echoed |
| `lives` | number | always `3` |
| `points` | number | always `0` |
| `level` | number | always `1` |
| `environment` | string | in-world narration, 2–3 lines |

> The backend **does** return narration. Use `environment` as the intro; do not
> invent one.

**Errors** `422` invalid body · `503` narration model unavailable

---

## GET /game/{sid}  ·  GET /game/{sid}/state

Both paths are aliases for the same handler.

**Response `200`**

| Field | Type |
| --- | --- |
| `lives` | number |
| `points` | number |
| `level` | number (1–3) |
| `game_over` | boolean (`lives <= 0`) |

**Errors** `404`

---

## GET /game/{sid}/question

Returns the active question. If one is already active it is **returned again**
rather than regenerated.

**Response `200`**

| Field | Type |
| --- | --- |
| `question` | string |

> Only `question`. There is no `correct_answer`, no alternatives, no enemy id.

**Errors** `404` · `400` game over · `502` model never produced a valid
question · `503` provider unavailable

---

## POST /game/{sid}/hint

Body is **ignored** — the hint is written from the server's own active question.

**Request** optional, empty JSON object accepted

**Response `200`**

| Field | Type |
| --- | --- |
| `hint` | string |

**Errors** `404` · `400` game over · **`409` no active question** · `503`

---

## POST /game/{sid}/answer-check

Scores the player's answer. **Consumes the active question**, so one question
can never be scored twice; a second submit for the same question gets `409`.

**Request**

| Field | Type | Rules |
| --- | --- | --- |
| `answer` | string | required, max **500** chars |

Extra keys (e.g. a client-supplied `question` or `correct_answer`) are dropped
by the server and ignored.

**Response `200`**

| Field | Type | Notes |
| --- | --- | --- |
| `verdict` | string | `"Correct"` or `"Incorrect"` |
| `correct` | boolean | authoritative; prefer this over string matching |
| `lives` | number | updated |
| `points` | number | updated |
| `level` | number | updated |
| `game_over` | boolean | |

**Errors** `404` · `400` game over · **`409` no active question** · `422`
answer over 500 chars · `503` answer checker unavailable

---

## GET /health

Never returns key values.

**Response `200`**

| Field | Type | Notes |
| --- | --- | --- |
| `status` | string | `"ok"` |
| `provider` | string | provider **name** only, e.g. `"groq"` |
| `search_available` | boolean | whether Tavily is configured |
| `active_sessions` | number | |

---

## Also available (not used by this frontend)

- `GET /game/{sid}/environment` → `{ environment, lives, points, level, game_over }`.

---

## Gaps this frontend works around

| Gap | How the frontend handles it |
| --- | --- |
| No `Spawn` empty exists in `dungeon.glb` | falls back to the grid (`S` cell if present, else `H`) and logs a warning |
| No enemy concept in the backend | enemies are placed in `src/world/enemySpawn.ts` from a seeded RNG; the backend only scores answers |
| No win condition in the backend | the run is won in the client when the player reaches the altar (`reachedAltar` in `src/world/map.ts`); the server only ends a game at 0 lives |
| "Which enemy is asking" is not tracked server-side | tracked purely in `src/game/useGame.ts` as `activeEnemyId` |
| `409` after submitting | the question is already consumed; reopening the same enemy starts a *new* question |