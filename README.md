# Knowledge Dungeon

An AI-powered quiz dungeon game.

- Backend: FastAPI API that starts a session, generates dungeon flavor text, asks questions, gives hints, and checks answers.
- Frontend: Vite + React (shadcn/ui) client in `quest-master/`.
- Optional CLI: quick terminal version in `main-cli.py`.

## How It Works

- You start a game with an `age` and `interest`.
- The backend uses an LLM (LangChain) to generate:
  - a short in-world environment narration
  - a structured question (`{"question", "answer", "accepted_alternatives"}`)
  - a hint
  - a correctness verdict
- Answers are checked **without trusting the LLM**: a normalized string comparison decides it
  whenever possible, and an LLM judge is only consulted for genuinely different phrasings.
- Game rules (the single source of truth is `core/rules.py`):
  - `3` lives
  - `+10` points per correct answer
  - level up every `30` points (max level `3`)
  - win at `90` points

## Repo Layout

- `main.py` - FastAPI server (default for the web app)
- `main-cli.py` - CLI game loop
- `agents/` - one LangChain agent per LLM task (`question`, `hint`, `answer`, `environment`)
- `core/rules.py` - pure game rules: `GameState`, `apply_answer`
- `core/llm.py` - provider selection, env loading, timeouts, retries
- `core/tools.py` - optional Tavily search tool
- `core/history.py` - capped, atomic question history file
- `core/sessions.py` - in-memory sessions with a TTL
- `core/text.py` - answer/history text normalization
- `tests/` - pytest suite (runs offline, every agent call is stubbed)
- `data/` - runtime state (gitignored apart from `data/.gitkeep`)
- `quest-master/` - React frontend

## Quickstart (Web App)

### 1) Backend (FastAPI)

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt

copy .env.example .env  # Windows PowerShell: Copy-Item .env.example .env
# then edit .env and set GROQ_API_KEY

uvicorn main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

### 2) Frontend (Vite + React)

The frontend is in `quest-master/` and expects the backend at `http://localhost:8000` (see `quest-master/src/lib/api.ts`).

```bash
cd quest-master
npm install
npm run dev
```

Vite runs on `http://localhost:8080` (configured in `quest-master/vite.config.ts`).

## Quickstart (CLI)

```bash
python main-cli.py
```

The CLI uses the same `core/rules.py` as the API, but writes its history to
`data/history_cli.json` so the two never touch the same file.

## Environment Variables

Copy `.env.example` to `.env`. Only the project's own `.env` is loaded - parent directories
are deliberately not searched.

- `LLM_PROVIDER` - `groq` (default), `glm`, or `gemini`
- `GROQ_API_KEY` - required when `LLM_PROVIDER=groq`
- `GLM_API_KEY` - required when `LLM_PROVIDER=glm`
- `GEMINI_API_KEY` - required when `LLM_PROVIDER=gemini`
- `TAVILY_API_KEY` - optional. Without it the game still works: questions come from the
  model's own knowledge instead of search. `GET /health` reports whether it is set.

`.env` is gitignored. Never commit real keys.

## API Endpoints

- `GET /health` - status, provider name, whether search is configured, active session count
- `POST /game/start` body: `{ "age": number, "interest": string }`
- `GET /game/{sid}` / `GET /game/{sid}/state` - lives, points, level, won, game_over
- `GET /game/{sid}/environment`
- `GET /game/{sid}/question` - `{ "question": ... }` only; the answer stays server-side
- `POST /game/{sid}/hint` - body ignored, hints the active question
- `POST /game/{sid}/answer-check` body: `{ "answer": string }` (max 500 chars)

### Question lifecycle

The server owns the active question. Each session stores one `current` question
(`question`, `answer`, `accepted_alternatives`, `asked_at`):

- `GET /question` returns the active question again if one is already in progress.
- `POST /hint` and `POST /answer-check` read the question and answer from the server only;
  anything a client puts in the body is ignored.
- `POST /answer-check` returns `409` when no question is active, and consumes the question, so
  the same question cannot be scored twice.
- The answer and the accepted alternatives are never returned by any endpoint.

### Answer checking

1. The stored answer, the accepted alternatives and the player's answer are normalized
   (casefold, Unicode NFKD, punctuation stripped, whitespace collapsed, leading article removed).
2. A match on any of them is correct with no LLM call - "The Eiffel Tower." matches
   "eiffel tower".
3. Otherwise, if the answer is non-empty, an LLM judge decides. The player's text is wrapped in
   `<player_answer>...</player_answer>` and the prompt tells the judge to treat it strictly as
   data. The judge must return `{"correct": true|false}`; the reply is parsed with `json.loads`
   and a Pydantic model, and **any** parse failure counts as wrong.

### Error codes

| Code | Meaning |
| --- | --- |
| `404` | Unknown or expired session |
| `409` | No active question (hint or answer-check) |
| `400` | Game over or already won |
| `422` | Invalid request body |
| `502` | Question model never produced valid JSON |
| `503` | LLM provider unavailable or misconfigured |
| `500` | Unexpected error - generic message, traceback logged server-side only |

Every model call gets a 15-second timeout and one retry with exponential backoff.

## Sessions and Persistence

- Sessions live in memory only and expire after **2 hours** of inactivity; expired sessions are
  evicted on each request. All access is guarded by a `threading.Lock`.
- Restarting the server resets all sessions.
- `data/history.json` holds the 50 most recent questions, written atomically (temp file plus
  `os.replace`) and used to skip repeats. The CLI uses `data/history_cli.json` instead.
- `data/` is created at startup if missing. Everything in it is safe to delete.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite stubs every agent call and redirects the history file, so it needs no API keys and
makes no network calls. Coverage includes the scoring rules, the 409/anti-replay behaviour,
answer spoofing attempts, normalization, judge robustness, history capping and session expiry.

## Frontend Tests

```bash
cd quest-master
npm run test
```