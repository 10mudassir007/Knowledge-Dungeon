"""HTTP surface: session lifecycle, question/answer flow, spoofing, errors."""

import json

import pytest

import main
from agents.answer import check_answer as real_check_answer


@pytest.fixture
def judged(monkeypatch):
    """Keep the real check_answer, but replace the LLM judge with a spy."""
    seen = []

    def fake_judge(question, correct_answer, player_answer):
        seen.append((question, correct_answer, player_answer))
        return False

    monkeypatch.setattr(main, "check_answer", real_check_answer)
    import agents.answer as answer_module

    monkeypatch.setattr(answer_module, "judge_answer", fake_judge)
    return seen


def _start(client, interest="space", age=21):
    response = client.post("/game/start", json={"age": age, "interest": interest})
    assert response.status_code == 200
    return response.json()


def _answer(client, sid, player_answer, **extra):
    body = {"answer": player_answer, **extra}
    return client.post(f"/game/{sid}/answer-check", json=body)


# --- health -------------------------------------------------------------------

def test_health_reports_provider_search_and_sessions(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["provider"] == "glm"
    assert isinstance(body["search_available"], bool)


def test_health_never_leaks_key_values(client, monkeypatch):
    key_secrets = {
        "GROQ_API_KEY": "super-secret-groq",
        "GLM_API_KEY": "super-secret-glm",
        "GEMINI_API_KEY": "super-secret-gemini",
        "TAVILY_API_KEY": "super-secret-tavily",
    }
    for key, value in key_secrets.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LLM_PROVIDER", "groq")

    body = client.get("/health").json()
    raw = json.dumps(body)

    for secret in key_secrets.values():
        assert secret not in raw
    assert "api_key" not in raw.lower()
    assert set(body) == {"status", "provider", "search_available", "active_sessions"}
    # Only the provider *name* is exposed, never a key.
    assert body["provider"] == "groq"


def test_health_counts_active_sessions(client):
    _start(client, interest="space")
    _start(client, interest="dinosaurs")
    assert client.get("/health").json()["active_sessions"] == 2


# --- start & validation -------------------------------------------------------

def test_start_returns_initial_state(client):
    body = _start(client, interest="dinosaurs", age=15)
    assert body["age"] == 15
    assert body["interest"] == "dinosaurs"
    assert body["lives"] == 3
    assert body["points"] == 0
    assert body["level"] == 1
    assert body["environment"]
    assert body["session_id"] in main.sessions._sessions


@pytest.mark.parametrize(
    "payload",
    [{"age": 0, "interest": "x"}, {"age": 121, "interest": "x"}, {"age": 20, "interest": ""}],
)
def test_start_rejects_invalid_payloads(client, payload):
    assert client.post("/game/start", json=payload).status_code == 422


def test_sessions_are_unique(client):
    assert _start(client)["session_id"] != _start(client)["session_id"]


# --- unknown / expired sessions -----------------------------------------------

def test_endpoints_reject_unknown_session(client):
    ghost = "nope"
    assert client.get(f"/game/{ghost}").status_code == 404
    assert client.get(f"/game/{ghost}/state").status_code == 404
    assert client.get(f"/game/{ghost}/question").status_code == 404
    assert client.get(f"/game/{ghost}/environment").status_code == 404
    assert client.post(f"/game/{ghost}/hint").status_code == 404
    assert _answer(client, ghost, "42").status_code == 404


def test_expired_sessions_are_evicted(client, monkeypatch):
    clock = {"now": 1_000_000.0}
    store = main.SessionStore(ttl_seconds=3600, time_func=lambda: clock["now"])
    monkeypatch.setattr(main, "sessions", store)

    sid = store.create(21, "space").session_id
    assert store.get(sid) is not None

    clock["now"] += 3601  # one second past the TTL
    assert store.get(sid) is None
    assert store.active_count() == 0
    assert client.get(f"/game/{sid}/state").status_code == 404


def test_session_within_ttl_is_kept(client, monkeypatch):
    clock = {"now": 1_000_000.0}
    store = main.SessionStore(ttl_seconds=3600, time_func=lambda: clock["now"])
    monkeypatch.setattr(main, "sessions", store)

    sid = store.create(21, "space").session_id
    clock["now"] += 3599
    assert store.get(sid) is not None


# --- questions ----------------------------------------------------------------

def test_question_returns_only_the_question(client, session_id):
    body = client.get(f"/game/{session_id}/question").json()
    assert body == {"question": "Which space fact is true?"}


def test_question_never_leaks_the_answer(client, session_id):
    raw = client.get(f"/game/{session_id}/question").text
    assert "42" not in raw
    assert "accepted_alternatives" not in raw


def test_active_question_is_served_again_not_regenerated(client, session_id, stub_agents):
    first = client.get(f"/game/{session_id}/question").json()
    second = client.get(f"/game/{session_id}/question").json()
    assert first == second
    assert len(stub_agents["question"]) == 1


def test_new_question_generated_after_answering(client, session_id, monkeypatch, stub_agents):
    from agents.question import QuestionDraft

    counter = {"n": 0}

    def unique_question(interest, age, history=None):
        counter["n"] += 1
        return QuestionDraft(question=f"Question {counter['n']}?", answer="42")

    monkeypatch.setattr(main, "generate_question", unique_question)

    client.get(f"/game/{session_id}/question")
    _answer(client, session_id, "42")
    client.get(f"/game/{session_id}/question")

    assert counter["n"] == 2


def test_asking_a_question_writes_history(client, session_id, read_history):
    client.get(f"/game/{session_id}/question")
    assert read_history() == [{"question": "Which space fact is true?", "answer": "42"}]


def test_history_is_capped_at_fifty(client, session_id, monkeypatch, read_history):
    from agents.question import QuestionDraft

    counter = {"n": 0}

    def unique_question(interest, age, history=None):
        counter["n"] += 1
        return QuestionDraft(question=f"Question number {counter['n']}?", answer="yes")

    monkeypatch.setattr(main, "generate_question", unique_question)

    for _ in range(55):
        sid = _start(client)["session_id"]
        client.get(f"/game/{sid}/question")
        _answer(client, sid, "no")

    assert len(read_history()) == 50


def test_duplicate_question_is_not_written_twice(client, session_id, monkeypatch, read_history):
    from agents.question import QuestionDraft

    monkeypatch.setattr(main, "generate_question", lambda *a, **k: QuestionDraft(question="Same question?", answer="x"))
    sid = _start(client)["session_id"]

    client.get(f"/game/{sid}/question")
    _answer(client, sid, "no")
    client.get(f"/game/{sid}/question")
    _answer(client, sid, "no")

    assert read_history() == [{"question": "Same question?", "answer": "x"}]


# --- hints --------------------------------------------------------------------

def test_hint_uses_the_server_question(client, session_id, stub_agents):
    client.get(f"/game/{session_id}/question")
    body = client.post(f"/game/{session_id}/hint").json()
    assert body["hint"]
    assert stub_agents["hint"][-1][:2] == ("Which space fact is true?", "42")


def test_hint_body_cannot_override_the_question(client, session_id, stub_agents):
    client.get(f"/game/{session_id}/question")
    client.post(
        f"/game/{session_id}/hint",
        json={"question": "hacked question?", "correct_answer": "hacked answer"},
    )
    sent_question, sent_answer, _ = stub_agents["hint"][-1]
    assert sent_question == "Which space fact is true?"
    assert sent_answer == "42"


def test_hint_without_active_question_is_conflict(client, session_id):
    assert client.post(f"/game/{session_id}/hint").status_code == 409


# --- answer checking ----------------------------------------------------------

def test_answer_check_without_active_question_returns_409(client, session_id):
    assert _answer(client, session_id, "42").status_code == 409
    assert _answer(client, session_id, "42").status_code == 409


def test_second_answer_to_the_same_question_is_rejected(client, session_id):
    client.get(f"/game/{session_id}/question")
    first = _answer(client, session_id, "42")
    assert first.status_code == 200
    assert first.json()["points"] == 10

    second = _answer(client, session_id, "42")
    assert second.status_code == 409
    assert client.get(f"/game/{session_id}/state").json()["points"] == 10


def test_answer_is_rejected_after_a_wrong_answer_too(client, session_id):
    client.get(f"/game/{session_id}/question")
    assert _answer(client, session_id, "nope").json()["lives"] == 2
    assert _answer(client, session_id, "42").status_code == 409
    assert client.get(f"/game/{session_id}/state").json()["points"] == 0


def test_correct_answer_scores_ten_points(client, session_id):
    client.get(f"/game/{session_id}/question")
    body = _answer(client, session_id, "42").json()
    assert body == {
        "verdict": "Correct",
        "correct": True,
        "lives": 3,
        "points": 10,
        "level": 1,
        "won": False,
        "game_over": False,
    }


def test_wrong_answer_costs_a_life(client, session_id):
    client.get(f"/game/{session_id}/question")
    body = _answer(client, session_id, "7").json()
    assert body["verdict"] == "Incorrect"
    assert body["correct"] is False
    assert body["lives"] == 2


def test_client_supplied_answer_and_question_are_ignored(client, session_id, judged):
    client.get(f"/game/{session_id}/question")
    _answer(
        client,
        session_id,
        "definitely not right",
        question="hacked question?",
        correct_answer="definitely not right",
        accepted_alternatives=["definitely not right"],
    )
    # The judge saw the server's question and answer, not the client's.
    assert judged == [("Which space fact is true?", "42", "definitely not right")]
    assert client.get(f"/game/{session_id}/state").json()["points"] == 0


def test_normalized_match_scores_without_calling_the_judge(client, session_id, monkeypatch):
    import agents.answer as answer_module

    def explode(*args, **kwargs):
        raise AssertionError("the judge must not be called for an exact normalized match")

    monkeypatch.setattr(main, "check_answer", real_check_answer)
    monkeypatch.setattr(answer_module, "judge_answer", explode)
    client.get(f"/game/{session_id}/question")

    # "The Eiffel Tower." vs the stored "eiffel tower"
    main.sessions.get(session_id).current.answer = "eiffel tower"
    body = _answer(client, session_id, "The Eiffel Tower.").json()
    assert body["correct"] is True
    assert body["points"] == 10


def test_malformed_judge_output_counts_as_wrong(client, session_id, monkeypatch):
    import agents.answer as answer_module

    # The real judge receives the agent's reply and parses it; a garbage reply
    # parses to False (covered end-to-end in test_agents.py).
    monkeypatch.setattr(main, "check_answer", real_check_answer)
    monkeypatch.setattr(answer_module, "judge_answer", lambda *a, **k: False)

    client.get(f"/game/{session_id}/question")
    body = _answer(client, session_id, "something plausible").json()
    assert body["correct"] is False
    assert body["lives"] == 2


def test_answer_is_capped_at_500_characters(client, session_id):
    client.get(f"/game/{session_id}/question")
    assert _answer(client, session_id, "x" * 500).status_code == 200
    assert _answer(client, session_id, "x" * 501).status_code == 422


def test_blank_answer_is_not_scored_as_correct(client, session_id, judged):
    client.get(f"/game/{session_id}/question")
    body = _answer(client, session_id, "   ").json()
    assert body["correct"] is False
    assert judged == []  # the judge is skipped for an empty answer


# --- progression --------------------------------------------------------------

def test_level_up_at_30_points(client, session_id):
    for _ in range(3):
        client.get(f"/game/{session_id}/question")
        _answer(client, session_id, "42")
    assert client.get(f"/game/{session_id}/state").json() == {
        "lives": 3,
        "points": 30,
        "level": 2,
        "won": False,
        "game_over": False,
    }


def test_level_up_at_60_points(client, session_id):
    for _ in range(6):
        client.get(f"/game/{session_id}/question")
        _answer(client, session_id, "42")
    assert client.get(f"/game/{session_id}/state").json()["level"] == 3


def test_nine_correct_answers_wins(client, session_id):
    for _ in range(9):
        client.get(f"/game/{session_id}/question")
        body = _answer(client, session_id, "42").json()

    assert body["points"] == 90
    assert body["level"] == 3
    assert body["won"] is True
    assert body["game_over"] is False


def test_won_game_refuses_further_play(client, session_id):
    for _ in range(9):
        client.get(f"/game/{session_id}/question")
        _answer(client, session_id, "42")

    assert client.get(f"/game/{session_id}/question").status_code == 400
    assert client.get(f"/game/{session_id}/environment").status_code == 400
    assert client.post(f"/game/{session_id}/hint").status_code == 400
    assert _answer(client, session_id, "42").status_code == 400


def test_three_wrong_answers_ends_the_game(client, session_id):
    lives = []
    for _ in range(3):
        client.get(f"/game/{session_id}/question")
        lives.append(_answer(client, session_id, "nope").json()["lives"])

    assert lives == [2, 1, 0]
    assert client.get(f"/game/{session_id}/state").json()["game_over"] is True


def test_game_over_refuses_further_play(client, session_id):
    for _ in range(3):
        client.get(f"/game/{session_id}/question")
        _answer(client, session_id, "nope")

    assert client.get(f"/game/{session_id}/question").status_code == 400
    assert client.get(f"/game/{session_id}/environment").status_code == 400
    assert client.post(f"/game/{session_id}/hint").status_code == 400
    assert _answer(client, session_id, "42").status_code == 400


def test_state_alias_matches_short_path(client, session_id):
    assert client.get(f"/game/{session_id}").json() == client.get(f"/game/{session_id}/state").json()


# --- isolation ----------------------------------------------------------------

def test_two_sessions_do_not_share_points(client):
    first = _start(client, interest="space")["session_id"]
    second = _start(client, interest="space")["session_id"]

    client.get(f"/game/{first}/question")
    _answer(client, first, "42")

    assert client.get(f"/game/{first}/state").json()["points"] == 10
    assert client.get(f"/game/{second}/state").json()["points"] == 0
    assert client.get(f"/game/{second}/state").json()["lives"] == 3


def test_active_questions_are_per_session(client):
    first = _start(client)["session_id"]
    second = _start(client)["session_id"]
    client.get(f"/game/{first}/question")

    assert main.sessions.get(first).current is not None
    assert main.sessions.get(second).current is None


# --- failures -----------------------------------------------------------------

def test_provider_failure_returns_503(client, session_id, monkeypatch):
    from core.llm import ProviderUnavailable

    def boom(*args, **kwargs):
        raise ProviderUnavailable("provider down")

    monkeypatch.setattr(main, "generate_question", boom)
    response = client.get(f"/game/{session_id}/question")
    assert response.status_code == 503
    assert "traceback" not in response.text.lower()
    assert response.json() == {"detail": "The game AI is unavailable right now. Please try again."}


def test_question_generation_failure_returns_502(client, session_id, monkeypatch):
    from agents import QuestionGenerationError

    def boom(*args, **kwargs):
        raise QuestionGenerationError("model kept returning junk")

    monkeypatch.setattr(main, "generate_question", boom)
    response = client.get(f"/game/{session_id}/question")
    assert response.status_code == 502


def test_answer_checker_failure_returns_503(client, session_id, monkeypatch):
    from agents import AnswerCheckError

    client.get(f"/game/{session_id}/question")
    monkeypatch.setattr(main, "check_answer", lambda *a, **k: (_ for _ in ()).throw(AnswerCheckError("down")))
    assert _answer(client, session_id, "42").status_code == 503


def test_unexpected_error_returns_500_without_traceback(lenient_client, session_id, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(main, "check_answer", boom)
    lenient_client.get(f"/game/{session_id}/question")

    response = _answer(lenient_client, session_id, "42")
    assert response.status_code == 500
    body = response.text
    assert "Traceback" not in body
    assert "secret internal detail" not in body
    assert "RuntimeError" not in body
    assert json.loads(body) == {"detail": "Internal server error."}


def test_search_tool_returns_none_without_key(monkeypatch):
    from core.tools import get_search_tool, is_search_configured

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert is_search_configured() is False
    assert get_search_tool() is None
