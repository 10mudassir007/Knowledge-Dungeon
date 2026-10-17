import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents import (
    AnswerCheckError,
    QuestionGenerationError,
    check_answer,
    generate_environment,
    generate_question,
    get_hint,
)
from core.history import HISTORY_LIMIT, HistoryStore
from core.llm import ProviderUnavailable
from core.rules import GameState, apply_answer
from core.sessions import SESSION_TTL_SECONDS, ActiveQuestion, Session, SessionStore
from core.text import normalize_answer
from core.tools import is_search_configured, warn_if_search_unconfigured

logger = logging.getLogger(__name__)

MAX_ANSWER_LENGTH = 500
DUPLICATE_GENERATION_ATTEMPTS = 2

DATA_DIR = os.environ.get("DATA_DIR", "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")

# The built frontend. `python main.py` serves the game from here.
REPO_ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

sessions = SessionStore()
history_store = HistoryStore(HISTORY_PATH, limit=HISTORY_LIMIT)
_startup_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(DATA_DIR, exist_ok=True)
    with _startup_lock:
        warn_if_search_unconfigured()
    logger.info(
        "Knowledge Dungeon started: data dir=%s history=%s session TTL=%ss",
        DATA_DIR,
        HISTORY_PATH,
        SESSION_TTL_SECONDS,
    )
    yield


# -----------------------------
# API models
# -----------------------------
class StartGameRequest(BaseModel):
    age: int = Field(..., ge=1, le=120)
    interest: str = Field(..., min_length=1, max_length=80)


class StartGameResponse(BaseModel):
    session_id: str
    age: int
    interest: str
    lives: int
    points: int
    level: int
    environment: str


class EnvironmentResponse(BaseModel):
    environment: str
    lives: int
    points: int
    level: int
    won: bool
    game_over: bool


class QuestionResponse(BaseModel):
    """Only the question text. The answer never leaves the server."""

    question: str


class HintResponse(BaseModel):
    hint: str


class HintRequest(BaseModel):
    """The body is ignored: hints are answered from the server's own question."""


class AnswerCheckRequest(BaseModel):
    """The player's answer, and nothing else. Any question/answer fields sent
    by a client are ignored; extra keys are dropped by pydantic."""

    answer: str = Field(..., max_length=MAX_ANSWER_LENGTH)


class CheckAnswerResponse(BaseModel):
    verdict: str
    correct: bool
    lives: int
    points: int
    level: int
    won: bool
    game_over: bool


class StateResponse(BaseModel):
    lives: int
    points: int
    level: int
    won: bool
    game_over: bool


class HealthResponse(BaseModel):
    status: str
    provider: str
    search_available: bool
    active_sessions: int


# -----------------------------
# Helpers
# -----------------------------
def state_response(state: GameState) -> StateResponse:
    return StateResponse(
        lives=state.lives,
        points=state.points,
        level=state.level,
        won=state.won,
        game_over=state.game_over,
    )


def require_session(session_id: str) -> Session:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Invalid or expired session_id")
    return session


def require_playable(session: Session) -> None:
    if session.state.game_over:
        raise HTTPException(status_code=400, detail="Game over")
    if session.state.won:
        raise HTTPException(status_code=400, detail="Game already won")


def require_active_question(session: Session) -> ActiveQuestion:
    current = session.current
    if current is None:
        raise HTTPException(status_code=409, detail="No active question. Request one first.")
    return current


def record_question(session: Session, draft, known_keys: set) -> bool:
    """Store the active question and remember it in history.

    Returns False (and writes nothing) if the normalized question text is
    already in history, so repeats are skipped.
    """
    key = normalize_answer(draft.question)
    is_duplicate = bool(key) and key in known_keys

    session.current = ActiveQuestion(
        question=draft.question,
        answer=draft.answer,
        accepted_alternatives=list(draft.accepted_alternatives),
        asked_at=time.time(),
    )
    if is_duplicate:
        return False

    entry = {"question": draft.question, "answer": draft.answer}
    session.history.append(entry)
    del session.history[:-HISTORY_LIMIT]
    history_store.append(entry)
    known_keys.add(key)
    return True


# -----------------------------
# App
# -----------------------------
# The interactive API docs and schema are never exposed. Only the game at "/"
# is meant to be discoverable; the API and its docs stay private.
app = FastAPI(
    title="Knowledge Dungeon API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class ApiPrefixStripMiddleware:
    """Accept both ``/health`` and ``/api/health``.

    The Vite dev server proxies ``/api/*`` to the backend with the prefix
    stripped, while production (Vercel) forwards the full ``/api/*`` path.
    Normalising here means the routes below match either way.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                scope["path"] = path[4:] or "/"
                raw = scope.get("raw_path")
                if isinstance(raw, bytes) and raw.startswith(b"/api"):
                    scope["raw_path"] = raw[4:] or b"/"
        await self.app(scope, receive, send)


app.add_middleware(ApiPrefixStripMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ProviderUnavailable)
async def provider_unavailable_handler(request: Request, exc: ProviderUnavailable):
    logger.warning("LLM provider unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "The game AI is unavailable right now. Please try again."})


@app.exception_handler(AnswerCheckError)
async def answer_check_error_handler(request: Request, exc: AnswerCheckError):
    logger.warning("Answer check failed: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "The answer checker is unavailable right now. Please try again."})


@app.exception_handler(QuestionGenerationError)
async def question_generation_error_handler(request: Request, exc: QuestionGenerationError):
    logger.error("Question generation failed: %s", exc)
    return JSONResponse(status_code=502, content={"detail": "Could not generate a question right now. Please try again."})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # Full traceback stays server-side; the client only sees a generic message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        provider=(os.getenv("LLM_PROVIDER") or "groq").strip().lower(),
        search_available=is_search_configured(),
        active_sessions=sessions.active_count(),
    )


@app.post("/game/start", response_model=StartGameResponse)
def start_game(payload: StartGameRequest):
    session = sessions.create(payload.age, payload.interest)
    environment = generate_environment(session.interest, session.age, session.state.level)

    return StartGameResponse(
        session_id=session.session_id,
        age=session.age,
        interest=session.interest,
        lives=session.state.lives,
        points=session.state.points,
        level=session.state.level,
        environment=environment,
    )


@app.get("/game/{session_id}", response_model=StateResponse)
@app.get("/game/{session_id}/state", response_model=StateResponse)
def get_state(session_id: str):
    return state_response(require_session(session_id).state)


@app.get("/game/{session_id}/environment", response_model=EnvironmentResponse)
def get_environment(session_id: str):
    session = require_session(session_id)
    require_playable(session)

    return EnvironmentResponse(
        environment=generate_environment(session.interest, session.age, session.state.level),
        **state_response(session.state).model_dump(),
    )


@app.get("/game/{session_id}/question", response_model=QuestionResponse)
def get_question(session_id: str):
    session = require_session(session_id)

    # An unanswered question is served again rather than replaced.
    if session.current is not None:
        return QuestionResponse(question=session.current.question)

    require_playable(session)

    known_keys = history_store.known_question_keys()
    known_keys.update(normalize_answer(entry.get("question", "")) for entry in session.history)

    draft = None
    for _ in range(DUPLICATE_GENERATION_ATTEMPTS):
        candidate = generate_question(session.interest, session.age, session.history)
        draft = candidate
        if normalize_answer(candidate.question) not in known_keys:
            break

    # record_question writes nothing to history when the question is a repeat.
    record_question(session, draft, known_keys)
    return QuestionResponse(question=draft.question)


@app.post("/game/{session_id}/hint", response_model=HintResponse)
def hint(session_id: str, payload: HintRequest = None):
    session = require_session(session_id)
    require_playable(session)
    current = require_active_question(session)

    return HintResponse(hint=get_hint(current.question, current.answer, session.interest))


@app.post("/game/{session_id}/answer-check", response_model=CheckAnswerResponse)
def answer_check(session_id: str, payload: AnswerCheckRequest):
    session = require_session(session_id)
    require_playable(session)
    current = require_active_question(session)

    # Consume the question up front so one question can never be scored twice,
    # even if two requests race.
    session.current = None

    correct = check_answer(
        current.question,
        current.answer,
        payload.answer,
        current.accepted_alternatives,
    )
    session.state = apply_answer(session.state, correct)

    return CheckAnswerResponse(
        verdict="Correct" if correct else "Incorrect",
        correct=correct,
        lives=session.state.lives,
        points=session.state.points,
        level=session.state.level,
        won=session.state.won,
        game_over=session.state.game_over,
    )


# -----------------------------
# Super power
# -----------------------------
class RevealResponse(BaseModel):
    """The answer to the active question. Additive: no existing route changed."""

    answer: str


@app.post("/game/{session_id}/reveal", response_model=RevealResponse)
def reveal_answer(session_id: str):
    session = require_session(session_id)
    require_playable(session)
    current = require_active_question(session)
    # The question stays active, so the player still has to submit it.
    return RevealResponse(answer=current.answer)


# -----------------------------
# Static frontend
# -----------------------------
# Mounted last so it never shadows /game or /health.
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve the built SPA, falling back to index.html for client routes."""
        # Reserved namespaces must never fall through to the SPA, or the API,
        # docs and schema would surface as duplicate copies of the game page.
        if full_path.startswith(("game", "health", "api", "docs", "redoc", "openapi")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:  # pragma: no cover - developer has not run the frontend build yet
    logger.warning(
        "frontend/dist not found at %s - run `npm run build` in frontend/ to serve the game.",
        FRONTEND_DIST,
    )


if __name__ == "__main__":
    import uvicorn

    # Sessions live in process memory, so this must stay a single worker.
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        workers=1,
    )
