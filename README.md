# Knowledge Dungeon

An AI-powered quiz dungeon game built with **Streamlit**.

- **App**: Streamlit single-page application (`app.py`)
- **Optional CLI**: quick terminal version in `main-cli.py`

## How It Works

- You start a game by entering your **name**, **age**, and **interest**.
- The app uses an LLM (LangChain) to generate:
  - a short in-world environment narration
  - a quiz question (returned as `question || answer` internally)
  - a hint (on request)
  - a correctness verdict ("Correct" / "Incorrect")
- Game rules:
  - `3` lives
  - `+10` points per correct answer
  - level up every `30` points (max level `3`)
  - win at `90` points

## Repo Layout

- `app.py` - Streamlit application (main entry point)
- `main-cli.py` - CLI game loop
- `agents/` - LLM-driven environment / question / hint / answer-check logic
- `core/llm.py` - LLM provider selection + env var loading
- `core/tools.py` - point / life tools + optional search tool
- `data/history.json` - persisted question history (auto-created)

## Quickstart

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt

copy .env.example .env  # Windows PowerShell: Copy-Item .env.example .env
# then edit .env and set GROQ_API_KEY

streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

## Quickstart (CLI)

```bash
python main-cli.py
```

Note: the CLI and Streamlit app share the same persisted question history file: `data/history.json`.

## Environment Variables

Create a `.env` (see `.env.example`).

Required (default configuration):

- `GROQ_API_KEY` - used by `core/llm.py` (default provider: `groq`)

Optional (only if you switch providers in code):

- `GLM_API_KEY`
- `GOOGLE_API_KEY`

Optional (only if the question generator ends up using the search tool):

- `TAVILY_API_KEY`
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
