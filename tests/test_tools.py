"""Tests for core/tools.py – increase_points, decrease_lives, dedup guards."""

import pytest
from core.tools import increase_points, decrease_lives, game_state, get_search_tool


# ── Fixtures to reset global state between tests ────────────────────
@pytest.fixture(autouse=True)
def _reset_tool_state():
    """Reset the mutable game_state and dedup tokens before every test."""
    import core.tools as _mod

    _mod.game_state["points"] = 0
    _mod.game_state["lives"] = 3
    _mod._last_score_token = None
    _mod._last_life_token = None
    yield


# ── increase_points ─────────────────────────────────────────────────
class TestIncreasePoints:
    def test_increases_by_10(self):
        result = increase_points.invoke({"token": "t1"})
        assert result == 10
        assert game_state["points"] == 10

    def test_accumulates(self):
        increase_points.invoke({"token": "t1"})
        increase_points.invoke({"token": "t2"})
        assert game_state["points"] == 20

    def test_dedup_same_token(self):
        increase_points.invoke({"token": "dup"})
        increase_points.invoke({"token": "dup"})
        assert game_state["points"] == 10  # only once

    def test_different_tokens_both_count(self):
        increase_points.invoke({"token": "a"})
        increase_points.invoke({"token": "b"})
        assert game_state["points"] == 20

    def test_empty_token_always_increments(self):
        increase_points.invoke({"token": ""})
        increase_points.invoke({"token": ""})
        assert game_state["points"] == 20


# ── decrease_lives ──────────────────────────────────────────────────
class TestDecreaseLives:
    def test_decreases_by_1(self):
        result = decrease_lives.invoke({"token": "t1"})
        assert result == 2
        assert game_state["lives"] == 2

    def test_dedup_same_token(self):
        decrease_lives.invoke({"token": "dup"})
        decrease_lives.invoke({"token": "dup"})
        assert game_state["lives"] == 2  # only once

    def test_does_not_go_below_zero(self):
        for i in range(5):
            decrease_lives.invoke({"token": f"t{i}"})
        assert game_state["lives"] == 0

    def test_different_tokens_both_count(self):
        decrease_lives.invoke({"token": "x"})
        decrease_lives.invoke({"token": "y"})
        assert game_state["lives"] == 1


# ── get_search_tool ─────────────────────────────────────────────────
class TestGetSearchTool:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
            get_search_tool()
