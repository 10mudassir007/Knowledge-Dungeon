"""Pure game rules. No I/O, no LLM, no globals - the single scoring authority.

Both the API (`main.py`) and the CLI (`main-cli.py`) call `apply_answer`, so
there is exactly one place where points, lives and level are decided.
"""

from dataclasses import dataclass, field

LEVEL_POINTS = 30
MAX_LEVEL = 3
STARTING_LIVES = 3
POINTS_PER_CORRECT = 10
WIN_POINTS = LEVEL_POINTS * MAX_LEVEL


def level_for_points(points: int) -> int:
    """0-29 => 1, 30-59 => 2, 60+ => 3."""
    return min(MAX_LEVEL, 1 + max(0, points) // LEVEL_POINTS)


@dataclass(frozen=True)
class GameState:
    """Immutable snapshot of a player's progress.

    `level` and `game_over` are derived in __post_init__ so a hand-built state
    can never disagree with the rules. `won` is a read-only property.
    """

    points: int = 0
    lives: int = STARTING_LIVES
    level: int = field(init=False)
    game_over: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", level_for_points(self.points))
        object.__setattr__(self, "game_over", self.lives <= 0)

    @property
    def won(self) -> bool:
        return self.points >= WIN_POINTS


def new_state() -> GameState:
    """A fresh game: 0 points, full lives, level 1."""
    return GameState(points=0, lives=STARTING_LIVES)


def apply_answer(state: GameState, correct: bool) -> GameState:
    """Score one answer and return the resulting state.

    Correct -> +10 points. Wrong -> -1 life. A finished game (no lives left, or
    the 90-point win reached) never changes further, so replaying an answer
    after the fact cannot move the score.
    """
    if state.game_over or state.won:
        return state

    if correct:
        return GameState(points=state.points + POINTS_PER_CORRECT, lives=state.lives)

    return GameState(points=state.points, lives=max(0, state.lives - 1))
