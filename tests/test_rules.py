"""core.rules: the single scoring path."""

import dataclasses

import pytest

from core.rules import (
    LEVEL_POINTS,
    MAX_LEVEL,
    POINTS_PER_CORRECT,
    STARTING_LIVES,
    GameState,
    apply_answer,
    level_for_points,
    new_state,
)


def test_rule_constants():
    assert STARTING_LIVES == 3
    assert POINTS_PER_CORRECT == 100
    assert LEVEL_POINTS == 300
    assert MAX_LEVEL == 3


def test_new_state():
    state = new_state()
    assert (state.points, state.lives, state.level) == (0, 3, 1)
    assert state.game_over is False


# --- correct answers ----------------------------------------------------------

def test_correct_answer_adds_a_hundred_points():
    state = apply_answer(new_state(), True)
    assert state.points == 100
    assert state.lives == 3
    assert state.level == 1


def test_correct_answer_keeps_lives():
    state = apply_answer(GameState(points=100, lives=1), True)
    assert state.lives == 1
    assert state.points == 200


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
    [(0, 1), (100, 1), (299, 1), (300, 2), (599, 2), (600, 3), (899, 3), (900, 3), (5000, 3)],
)
def test_level_for_points(points, expected):
    assert level_for_points(points) == expected


def test_level_up_at_300_points():
    state = new_state()
    for _ in range(3):
        state = apply_answer(state, True)
    assert state.points == 300
    assert state.level == 2


def test_level_up_at_600_points():
    state = new_state()
    for _ in range(6):
        state = apply_answer(state, True)
    assert state.points == 600
    assert state.level == 3


def test_level_is_capped_at_three():
    assert level_for_points(10_000) == 3
    state = new_state()
    for _ in range(20):
        state = apply_answer(state, True)
    assert state.level == MAX_LEVEL


def test_negative_points_stay_level_one():
    assert level_for_points(-50) == 1


# --- no server-side win -------------------------------------------------------

def test_points_keep_accumulating_past_the_level_cap():
    # The run is won in the client by reaching the altar, so scoring never
    # "completes" a game: 900 points is a full level 3, not a finish line.
    state = new_state()
    for _ in range(12):
        state = apply_answer(state, True)
    assert state.points == 1200
    assert state.level == MAX_LEVEL
    assert state.game_over is False


def test_only_the_last_life_finishes_a_game():
    state = new_state()
    for _ in range(20):
        state = apply_answer(state, True)
    assert state.game_over is False
    state = apply_answer(GameState(points=state.points, lives=1), False)
    assert state.game_over is True


# --- game over ----------------------------------------------------------------

def test_game_over_at_zero_lives():
    state = new_state()
    for _ in range(3):
        state = apply_answer(state, False)
    assert state.lives == 0
    assert state.game_over is True


def test_game_over_state_ignores_further_answers():
    dead = GameState(points=100, lives=0)
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
    state = GameState(points=700, lives=2)
    assert state.level == 3
    assert state.game_over is False


def test_hands_off_the_same_scoring_path_for_both_callers():
    # The API and CLI both import this function; nothing else may score.
    from core import rules

    source = rules.apply_answer.__module__
    assert source == "core.rules"
