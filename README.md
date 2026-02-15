# Knowledge Dungeon

An AI-powered quiz dungeon game.

- Backend: FastAPI API that starts a session, generates dungeon flavor text, asks questions, gives hints, and checks answers.
- Frontend: Vite + React (shadcn/ui) client in `quest-master/`.
- Optional CLI: quick terminal version in `main-cli.py`.

## How It Works

- You start a game with an `age` and `interest`.
- The backend uses an LLM (LangChain) to generate:
  - a short in-world environment narration
  - a question (returned as `question || answer` internally)
  - a hint
  - a correctness verdict ("Correct" / "Incorrect")
- Game rules:
  - `3` lives
  - `+10` points per correct answer
  - level up every `30` points (max level `3`)
  - win at `90` points

## Repo Layout

- `main.py` - FastAPI server (default for the web app)
- `main-cli.py` - CLI game loop
- `agents/agent.py` - LLM-driven environment/question/hint/check logic
- `core/llm.py` - LLM provider selection + env var loading
- `core/tools.py` - point/life tools + optional search tool
- `data/history.json` - persisted question history (auto-created)
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

Note: the CLI and API share the same persisted question history file: `data/history.json`.

## Environment Variables

Create a `.env` (see `.env.example`).

Required (default configuration):

- `GROQ_API_KEY` - used by `core/llm.py` (default provider: `groq`)

Optional (only if you switch providers in code):

- `GLM_API_KEY`
- `GOOGLE_API_KEY`

Optional (only if the question generator ends up using the search tool):

- `TAVILY_API_KEY`

## API Endpoints

- `GET /health`
- `POST /game/start` body: `{ "age": number, "interest": string }`
- `GET /game/{session_id}/question`
- `POST /game/{session_id}/hint` body: `{ "question": string, "correct_answer": string }`
- `POST /game/{session_id}/answer-check` body: `{ "question": string, "correct_answer": string, "user_answer": string }`
- `GET /game/{session_id}/environment`
- `GET /game/{session_id}/state`

## Notes / Gotchas

- Sessions are in-memory in `main.py` (`SESSIONS` dict). Restarting the server resets all sessions.
- Question history is persisted globally in `data/history.json` to reduce repeats.
- CORS is currently wide open (`allow_origins=["*"]`) for local development.

## Frontend Tests

```bash
cd quest-master
npm run test
```
