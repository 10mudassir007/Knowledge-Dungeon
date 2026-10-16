"""Shared fixtures.

The suite runs fully offline: every agent call is stubbed, the history file is
redirected into tmp_path, and no API keys are needed.
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from agents.question import QuestionDraft  # noqa: E402


ALL_KEY_VARS = (
    "LLM_PROVIDER",
    "GROQ_API_KEY",
    "GLM_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "TAVILY_API_KEY",
)


@pytest.fixture(autouse=True)
def no_ambient_keys(monkeypatch):
    """Tests must never pick up keys from the developer's environment or .env."""
    for name in ALL_KEY_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def isolated_app(tmp_path, monkeypatch):
    """Redirect history to tmp, clear sessions, restore module globals."""
    history_file = tmp_path / "data" / "history.json"
    monkeypatch.setattr(main, "HISTORY_PATH", str(history_file))
    monkeypatch.setattr(main, "history_store", main.HistoryStore(str(history_file), limit=main.HISTORY_LIMIT))
    monkeypatch.setattr(main, "sessions", main.SessionStore())
    yield history_file
    main.sessions.clear()


@pytest.fixture
def stub_agents(monkeypatch):
    """Deterministic stand-ins for the four LLM agents."""
    calls = {"environment": [], "question": [], "hint": [], "answer": []}

    def generate_environment(interest, age, level):
        calls["environment"].append((interest, age, level))
        return f"The {interest} dungeon awakens."

    def generate_question(interest, age, history=None):
        calls["question"].append((interest, age, history))
        return QuestionDraft(
            question="Which space fact is true?",
            answer="42",
            accepted_alternatives=["the answer to everything"],
        )

    def get_hint(question, answer, interest):
        calls["hint"].append((question, answer, interest))
        return "Consider the answer to everything."

    def check_answer(question, correct_answer, player_answer, accepted_alternatives=None):
        calls["answer"].append((question, correct_answer, player_answer, accepted_alternatives))
        return player_answer.strip().casefold() == correct_answer.strip().casefold()

    monkeypatch.setattr(main, "generate_environment", generate_environment)
    monkeypatch.setattr(main, "generate_question", generate_question)
    monkeypatch.setattr(main, "get_hint", get_hint)
    monkeypatch.setattr(main, "check_answer", check_answer)
    return calls


@pytest.fixture
def client(stub_agents):
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def lenient_client(stub_agents):
    """Client that surfaces the global 500 handler instead of re-raising."""
    with TestClient(main.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def session_id(client):
    response = client.post("/game/start", json={"age": 21, "interest": "space"})
    assert response.status_code == 200
    return response.json()["session_id"]


@pytest.fixture
def read_history(isolated_app):
    def _read():
        if not isolated_app.exists():
            return []
        return json.loads(isolated_app.read_text(encoding="utf-8"))

    return _read
