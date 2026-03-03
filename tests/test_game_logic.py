"""Tests for game-logic helpers in app.py (pure functions, no LLM calls)."""

import json
import os
import pytest

# We import only the pure helpers – they live at module level in app.py,
# but app.py also calls st.set_page_config at import time.  To avoid that
# side-effect we test the logic directly by re-implementing the same tiny
# functions here (they are one-liners) **and** by importing them where safe.

# ── compute_level ───────────────────────────────────────────────────
from app import compute_level, LEVEL_POINTS, MAX_LEVEL, WIN_POINTS, STARTING_LIVES, POINTS_PER_CORRECT


class TestComputeLevel:
    def test_level_1_at_zero_points(self):
        assert compute_level(0) == 1

    def test_level_1_just_below_threshold(self):
        assert compute_level(LEVEL_POINTS - 1) == 1

    def test_level_2_at_threshold(self):
        assert compute_level(LEVEL_POINTS) == 2

    def test_level_3_at_double_threshold(self):
        assert compute_level(LEVEL_POINTS * 2) == 3

    def test_level_capped_at_max(self):
        assert compute_level(999) == MAX_LEVEL

    def test_negative_points_gives_level_below_one(self):
        # edge case – should never happen in practice; with floor division
        # negative values produce 0 which is below 1
        assert compute_level(-10) == 0


# ── Constants sanity ────────────────────────────────────────────────
class TestConstants:
    def test_win_points_equals_level_points_times_max_level(self):
        assert WIN_POINTS == LEVEL_POINTS * MAX_LEVEL

    def test_starting_lives_positive(self):
        assert STARTING_LIVES > 0

    def test_points_per_correct_positive(self):
        assert POINTS_PER_CORRECT > 0


# ── load_history / save_history ─────────────────────────────────────
from app import load_history, save_history


class TestHistory:
    def test_load_missing_file_returns_empty_list(self, tmp_path):
        assert load_history(str(tmp_path / "nope.json")) == []

    def test_save_and_load_roundtrip(self, tmp_history_file):
        data = [{"question": "Q1", "answer": "A1"}]
        save_history(tmp_history_file, data)
        assert load_history(tmp_history_file) == data

    def test_save_creates_parent_dirs(self, tmp_path):
        deep = str(tmp_path / "a" / "b" / "history.json")
        save_history(deep, [{"q": 1}])
        assert os.path.exists(deep)

    def test_load_non_list_json_returns_empty(self, tmp_path):
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            json.dump({"not": "a list"}, f)
        assert load_history(path) == []

    def test_load_corrupt_json_returns_empty(self, tmp_path):
        path = str(tmp_path / "corrupt.json")
        with open(path, "w") as f:
            f.write("{broken json")
        assert load_history(path) == []

    def test_load_preexisting_data(self, tmp_history_with_data):
        data = load_history(tmp_history_with_data)
        assert len(data) == 2
        assert data[0]["answer"] == "4"

    def test_save_overwrites_existing(self, tmp_history_file):
        save_history(tmp_history_file, [{"q": "old"}])
        save_history(tmp_history_file, [{"q": "new"}])
        assert load_history(tmp_history_file) == [{"q": "new"}]

    def test_save_handles_unicode(self, tmp_history_file):
        data = [{"question": "¿Cuál es la capital?", "answer": "Madrid"}]
        save_history(tmp_history_file, data)
        loaded = load_history(tmp_history_file)
        assert loaded[0]["question"] == "¿Cuál es la capital?"
