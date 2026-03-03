"""Tests for agents/prompts.py – sanity-check prompt content."""

from agents.prompts import (
    ENV_AGENT_SYSTEM_PROMPT,
    QUESTION_AGENT_SYSTEM_PROMPT,
    HINT_AGENT_SYSTEM_PROMPT,
    ANSWER_CHECKER_SYSTEM_PROMPT,
)


class TestPrompts:
    # ── ENV prompt ──────────────────────────────────────────────────
    def test_env_prompt_is_non_empty_string(self):
        assert isinstance(ENV_AGENT_SYSTEM_PROMPT, str)
        assert len(ENV_AGENT_SYSTEM_PROMPT) > 20

    def test_env_prompt_mentions_narrator(self):
        assert "narrator" in ENV_AGENT_SYSTEM_PROMPT.lower()

    def test_env_prompt_forbids_meta(self):
        lower = ENV_AGENT_SYSTEM_PROMPT.lower()
        assert "openai" in lower  # rule to NOT mention it
        assert "chatgpt" in lower

    def test_env_prompt_handles_previous_context(self):
        lower = ENV_AGENT_SYSTEM_PROMPT.lower()
        assert "previous" in lower

    # ── QUESTION prompt ─────────────────────────────────────────────
    def test_question_prompt_includes_separator(self):
        assert "||" in QUESTION_AGENT_SYSTEM_PROMPT

    def test_question_prompt_mentions_search_tool_policy(self):
        assert "search tool" in QUESTION_AGENT_SYSTEM_PROMPT.lower()

    # ── HINT prompt ─────────────────────────────────────────────────
    def test_hint_prompt_is_non_empty(self):
        assert len(HINT_AGENT_SYSTEM_PROMPT) > 5

    # ── ANSWER CHECKER prompt ───────────────────────────────────────
    def test_answer_checker_mentions_correct_incorrect(self):
        lower = ANSWER_CHECKER_SYSTEM_PROMPT.lower()
        assert "correct" in lower
        assert "incorrect" in lower

    def test_answer_checker_mentions_tools(self):
        lower = ANSWER_CHECKER_SYSTEM_PROMPT.lower()
        assert "increase_points" in lower
        assert "decrease_lives" in lower

    def test_answer_checker_forbids_revealing_answer(self):
        assert "do not reveal" in ANSWER_CHECKER_SYSTEM_PROMPT.lower()
