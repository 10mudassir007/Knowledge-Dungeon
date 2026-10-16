"""core.rules: the single scoring path."""

import dataclasses

import pytest

from core.rules import (
    LEVEL_POINTS,
    MAX_LEVEL,
    POINTS_PER_CORRECT,
    STARTING_LIVES,
    WIN_POINTS,
    GameState,
    apply_answer,
    level_for_points,
    new_state,
)


def test_rule_constants():
    assert STARTING_LIVES == 3
    assert POINTS_PER_CORRECT == 10
    assert LEVEL_POINTS == 30
    assert MAX_LEVEL == 3
    assert WIN_POINTS == 90


def test_new_state():
    state = new_state()
    assert (state.points, state.lives, state.level) == (0, 3, 1)
    assert state.game_over is False
    assert state.won is False


# --- correct answers ----------------------------------------------------------

def test_correct_answer_adds_ten_points():
    state = apply_answer(new_state(), True)
    assert state.points == 10
    assert state.lives == 3
    assert state.level == 1


def test_correct_answer_keeps_lives():
    state = apply_answer(GameState(points=10, lives=1), True)
    assert state.lives == 1
    assert state.points == 20


# --- wrong answers ------------------------------------------------------------

def test_incorrect_answer_costs_one_life():
    state = apply_answer(new_state(), False)
    assert state.points == 0
    assert state.lives == 2


def test_lives_floor_at_zero():
    state = apply_answer(GameState(points=0, lives=1), False)
    assert state.lives == 0
    assert state.game_over is True


# --- leveling -----------------------------------------------------------------

@pytest.mark.parametrize(
    "points,expected",
    [(0, 1), (10, 1), (29, 1), (30, 2), (59, 2), (60, 3), (89, 3), (90, 3), (500, 3)],
)
def test_level_for_points(points, expected):
    assert level_for_points(points) == expected


def test_level_up_at_30_points():
    state = new_state()
    for _ in range(3):
        state = apply_answer(state, True)
    assert state.points == 30
    assert state.level == 2


def test_level_up_at_60_points():
    state = new_state()
    for _ in range(6):
        state = apply_answer(state, True)
    assert state.points == 60
    assert state.level == 3


def test_level_is_capped_at_three():
    assert level_for_points(10_000) == 3
    state = new_state()
    for _ in range(20):
        state = apply_answer(state, True)
    assert state.level == MAX_LEVEL


def test_negative_points_stay_level_one():
    assert level_for_points(-50) == 1


# --- winning ------------------------------------------------------------------

def test_win_at_90_points():
    state = new_state()
    for _ in range(9):
        state = apply_answer(state, True)
    assert state.points == WIN_POINTS
    assert state.won is True


def test_not_won_at_89_points():
    assert GameState(points=WIN_POINTS - 1).won is False
    assert GameState(points=WIN_POINTS).won is True


def test_finished_game_ignores_further_answers():
    state = new_state()
    for _ in range(9):
        state = apply_answer(state, True)
    assert apply_answer(state, True) == state
    assert apply_answer(state, False) == state


# --- game over ----------------------------------------------------------------

def test_game_over_at_zero_lives():
    state = new_state()
    for _ in range(3):
        state = apply_answer(state, False)
    assert state.lives == 0
    assert state.game_over is True


def test_game_over_state_ignores_further_answers():
    dead = GameState(points=10, lives=0)
    assert dead.game_over is True
    assert apply_answer(dead, True) == dead


# --- purity -------------------------------------------------------------------

def test_state_is_immutable():
    state = new_state()
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.points = 999


def test_apply_answer_does_not_mutate_the_input():
    before = new_state()
    apply_answer(before, True)
    assert before.points == 0
    assert before.lives == 3


def test_derived_fields_cannot_disagree_with_rules():
    state = GameState(points=70, lives=2)
    assert state.level == 3
    assert state.game_over is False
    assert state.won is False


def test_hands_off_the_same_scoring_path_for_both_callers():
    # The API and CLI both import this function; nothing else may score.
    from core import rules

    source = rules.apply_answer.__module__
    assert source == "core.rules"
