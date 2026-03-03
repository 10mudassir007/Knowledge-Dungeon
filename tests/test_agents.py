"""Tests for agent wrappers (environment, question, hint, answer).

All LLM calls are mocked via monkeypatching langchain.agents.create_agent
so these tests run instantly and don't need API keys.
"""

import pytest


# ══════════════════════════════════════════════════════════════════════
# generate_environment
# ══════════════════════════════════════════════════════════════════════
class TestGenerateEnvironment:
    def test_returns_string(self, patch_create_agent):
        patch_create_agent("Welcome to the dark dungeon, traveler…")
        from agents.environment import generate_environment

        result = generate_environment("Science", 25, 1)
        assert isinstance(result, str)
        assert "dungeon" in result.lower()

    def test_first_round_no_previous_context(self, patch_create_agent):
        """When called without optional kwargs it should still work."""
        patch_create_agent("The shadows whisper your name.")
        from agents.environment import generate_environment

        result = generate_environment("History", 30, 1)
        assert len(result) > 0

    def test_with_previous_context(self, patch_create_agent):
        patch_create_agent("You survived… barely.")
        from agents.environment import generate_environment

        result = generate_environment(
            "Math",
            20,
            2,
            last_verdict="Correct",
            points=30,
            previous_environment="The dark corridor opens before you.",
        )
        assert isinstance(result, str)

    def test_handles_list_content(self, monkeypatch):
        """If the LLM returns a list of content blocks, pick the last text."""
        from tests.conftest import FakeAIMessage

        class FakeAgentList:
            def invoke(self, _):
                return {
                    "messages": [
                        FakeAIMessage([{"text": "block one"}, {"text": "block two"}])
                    ]
                }

        import agents.environment as _env

        monkeypatch.setattr(_env, "create_agent", lambda **kw: FakeAgentList())

        from agents.environment import generate_environment

        result = generate_environment("Art", 18, 1)
        assert result == "block two"


# ══════════════════════════════════════════════════════════════════════
# generate_question
# ══════════════════════════════════════════════════════════════════════
class TestGenerateQuestion:
    def test_returns_pipe_separated_string(self, patch_create_agent, monkeypatch):
        patch_create_agent("What is the speed of light? || 300,000 km/s")
        # Patch get_search_tool so it doesn't need TAVILY_API_KEY
        import core.tools as _tools

        monkeypatch.setattr(
            _tools, "get_search_tool", lambda: None
        )

        from agents.question import generate_question

        result = generate_question("Physics", 22, [])
        assert "||" in result

    def test_with_history(self, patch_create_agent, monkeypatch):
        patch_create_agent("Who painted the Mona Lisa? || Leonardo da Vinci")
        import core.tools as _tools

        monkeypatch.setattr(_tools, "get_search_tool", lambda: None)

        from agents.question import generate_question

        history = [{"question": "old q", "answer": "old a"}]
        result = generate_question("Art", 30, history)
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════
# get_hint
# ══════════════════════════════════════════════════════════════════════
class TestGetHint:
    def test_returns_hint_string(self, patch_create_agent):
        patch_create_agent("Think about Sir Isaac and an apple…")
        from agents.hint import get_hint

        result = get_hint("Who discovered gravity?", "Newton", "Science")
        assert isinstance(result, str)
        assert len(result) > 0


# ══════════════════════════════════════════════════════════════════════
# check_answer
# ══════════════════════════════════════════════════════════════════════
class TestCheckAnswer:
    def test_correct_verdict(self, patch_create_agent):
        patch_create_agent("Correct")
        from agents.answer import check_answer

        result = check_answer("Capital of France?", "Paris", "Paris")
        assert result.strip().lower() == "correct"

    def test_incorrect_verdict(self, patch_create_agent):
        patch_create_agent("Incorrect")
        from agents.answer import check_answer

        result = check_answer("Capital of France?", "Paris", "London")
        assert result.strip().lower() == "incorrect"
