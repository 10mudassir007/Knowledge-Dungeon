from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import json
import os
import uuid

from agents.agent import generate_question, check_answer, get_hint, generate_environment

# -----------------------------
# Persistence (question history)
# -----------------------------
HISTORY_PATH = os.path.join("data", "history.json")


def load_history(path: str):
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(path: str, history_list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history_list, f, ensure_ascii=False, indent=2)


# -----------------------------
# Game rules
# -----------------------------
LEVEL_POINTS = 30
MAX_LEVEL = 3
STARTING_LIVES = 3
POINTS_PER_CORRECT = 10
WIN_POINTS = LEVEL_POINTS * MAX_LEVEL


def compute_level(points: int) -> int:
    # 0-29 => L1, 30-59 => L2, 60-89 => L3
    return min(MAX_LEVEL, (points // LEVEL_POINTS) + 1)


# -----------------------------
# In-memory session store
# -----------------------------
# NOTE: This stores state in memory. If you restart the server, all sessions reset.
SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_session_or_404(session_id: str) -> Dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Invalid session_id")
    return session


def sync_level_and_status(session: Dict[str, Any]) -> None:
    points = int(session.get("points", 0))
    session["level"] = compute_level(points)
    session["won"] = points >= WIN_POINTS
    session["game_over"] = int(session.get("lives", 0)) <= 0


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
    question: str
    # The frontend needs this to call /hint and /answer-check.
    correct_answer: str
    lives: int
    points: int
    level: int


class HintRequest(BaseModel):
    question: str
    correct_answer: str


class HintResponse(BaseModel):
    hint: str


class CheckAnswerRequest(BaseModel):
    question: str
    correct_answer: str
    user_answer: str


class CheckAnswerResponse(BaseModel):
    verdict: str
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


# -----------------------------
# App
# -----------------------------
app = FastAPI(title="Knowledge Dungeon API")

# Allow browser clients (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/game/start", response_model=StartGameResponse)
def start_game(payload: StartGameRequest):
    session_id = str(uuid.uuid4())

    session = {
        "age": payload.age,
        "interest": payload.interest,
        "points": 0,
        "lives": STARTING_LIVES,
        "level": 1,
        "won": False,
        "game_over": False,
    }
    sync_level_and_status(session)
    SESSIONS[session_id] = session

    environment = generate_environment(payload.interest, payload.age, session["level"])

    return StartGameResponse(
        session_id=session_id,
        age=payload.age,
        interest=payload.interest,
        lives=session["lives"],
        points=session["points"],
        level=session["level"],
        environment=environment,
    )


@app.get("/game/{session_id}/state", response_model=StateResponse)
def get_state(session_id: str):
    session = get_session_or_404(session_id)
    sync_level_and_status(session)
    return StateResponse(
        lives=session["lives"],
        points=session["points"],
        level=session["level"],
        won=session["won"],
        game_over=session["game_over"],
    )


@app.get("/game/{session_id}/environment", response_model=EnvironmentResponse)
def get_environment(session_id: str):
    session = get_session_or_404(session_id)
    sync_level_and_status(session)

    if session["game_over"]:
        raise HTTPException(status_code=400, detail="Game over")
    if session["won"]:
        raise HTTPException(status_code=400, detail="Game already won")

    environment = generate_environment(session["interest"], session["age"], session["level"])

    return EnvironmentResponse(
        environment=environment,
        lives=session["lives"],
        points=session["points"],
        level=session["level"],
        won=session["won"],
        game_over=session["game_over"],
    )


@app.get("/game/{session_id}/question", response_model=QuestionResponse)
def get_question(session_id: str):
    session = get_session_or_404(session_id)
    sync_level_and_status(session)

    if session["game_over"]:
        raise HTTPException(status_code=400, detail="Game over")
    if session["won"]:
        raise HTTPException(status_code=400, detail="Game already won")

    # Persisted global history is used only to avoid repeating questions, same as CLI.
    history = load_history(HISTORY_PATH)

    raw = generate_question(session["interest"], session["age"], history)
    parts = raw.split("||", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=500, detail="Question format error from model")

    q_text = parts[0].strip()
    q_answer = parts[1].strip()

    history.append({"question": q_text, "answer": q_answer})
    save_history(HISTORY_PATH, history)

    return QuestionResponse(
        question=q_text,
        correct_answer=q_answer,
        lives=session["lives"],
        points=session["points"],
        level=session["level"],
    )


@app.post("/game/{session_id}/hint", response_model=HintResponse)
def hint(session_id: str, payload: HintRequest):
    session = get_session_or_404(session_id)
    sync_level_and_status(session)

    if session["game_over"]:
        raise HTTPException(status_code=400, detail="Game over")
    if session["won"]:
        raise HTTPException(status_code=400, detail="Game already won")

    hint_text = get_hint(payload.question, payload.correct_answer, session["interest"])
    return HintResponse(hint=hint_text)


@app.post("/game/{session_id}/answer-check", response_model=CheckAnswerResponse)
def answer_check(session_id: str, payload: CheckAnswerRequest):
    session = get_session_or_404(session_id)
    sync_level_and_status(session)

    if session["game_over"]:
        raise HTTPException(status_code=400, detail="Game over")
    if session["won"]:
        raise HTTPException(status_code=400, detail="Game already won")

    verdict = check_answer(payload.question, payload.correct_answer, payload.user_answer)
    verdict_norm = (verdict or "").strip().lower()

    # IMPORTANT: update session state deterministically based on verdict.
    # NOTE: do NOT use substring matching ("correct" in "incorrect" is True).
    if verdict_norm == "correct":
        session["points"] = int(session.get("points", 0)) + POINTS_PER_CORRECT
    else:
        session["lives"] = max(0, int(session.get("lives", 0)) - 1)

    sync_level_and_status(session)

    return CheckAnswerResponse(
        verdict="Correct" if verdict_norm == "correct" else "Incorrect",
        lives=session["lives"],
        points=session["points"],
        level=session["level"],
        won=session["won"],
        game_over=session["game_over"],
    )
